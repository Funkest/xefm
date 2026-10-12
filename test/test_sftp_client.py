"""SFTP protocol edge cases a real server does not produce on demand.

``test_ssh_sftp_session.py`` runs the client against OpenSSH's sftp-server;
this file drives it against a scripted server in the same process, to reach
what that cannot: short reads, a server that stops answering, one without
``posix-rename``, a session that ends mid-request.

Run with: python -m pytest test/test_sftp_client.py -v
"""

import os
import struct
import threading

import pytest

from xefm import sftp_client as S


def _u32(n):
    return struct.pack(">I", n)


def _string(b):
    return _u32(len(b)) + b


class FakeServer:
    """Just enough of an SFTP server over two pipes: version handshake, a
    single in-memory file to open/fstat/read, rename, and a switch to stop
    answering. ``max_read`` caps what one READ returns, to force short reads."""

    def __init__(self, *, data=b"", max_read=None, extensions=(), silent=False):
        self.data = data
        self.max_read = max_read
        self.extensions = extensions
        self.silent = silent
        self.requests = []
        c_r, s_w = os.pipe()   # server -> client
        s_r, c_w = os.pipe()   # client -> server
        self.client_rfile = os.fdopen(c_r, "rb", buffering=0)
        self.client_wfile = os.fdopen(c_w, "wb", buffering=0)
        self._in = os.fdopen(s_r, "rb", buffering=0)
        self._out = os.fdopen(s_w, "wb", buffering=0)
        threading.Thread(target=self._serve, daemon=True).start()

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self._in.read(n - len(buf))
            if not chunk:
                raise EOFError
            buf += chunk
        return buf

    def _reply(self, ptype, payload):
        packet = bytes([ptype]) + payload
        self._out.write(_u32(len(packet)) + packet)

    def _status(self, rid, code, msg=b""):
        self._reply(S.FXP_STATUS, _u32(rid) + _u32(code) + _string(msg) + _string(b""))

    def _serve(self):
        try:
            while True:
                packet = self._read(struct.unpack(">I", self._read(4))[0])
                ptype, body = packet[0], packet[1:]
                if ptype == S.FXP_INIT:
                    ext = b"".join(_string(n.encode()) + _string(b"1")
                                   for n in self.extensions)
                    self._reply(S.FXP_VERSION, _u32(3) + ext)
                    continue
                rid = struct.unpack_from(">I", body)[0]
                self.requests.append(ptype)
                if self.silent:
                    continue
                self._handle(ptype, rid, S._Reader(body[4:]))
        except (EOFError, OSError, ValueError):
            pass
        finally:
            self._out.close()

    def _handle(self, ptype, rid, r):
        if ptype == S.FXP_OPEN:
            self._reply(S.FXP_HANDLE, _u32(rid) + _string(b"h"))
        elif ptype == S.FXP_FSTAT:
            self._reply(S.FXP_ATTRS, _u32(rid) + _u32(S.ATTR_SIZE) +
                        struct.pack(">Q", len(self.data)))
        elif ptype == S.FXP_READ:
            r.bytes()
            offset, length = r.u64(), r.u32()
            if offset >= len(self.data):
                self._status(rid, S.FX_EOF)
                return
            length = min(length, self.max_read or length)
            self._reply(S.FXP_DATA, _u32(rid) + _string(self.data[offset:offset + length]))
        elif ptype in (S.FXP_CLOSE, S.FXP_RENAME, S.FXP_EXTENDED):
            self._status(rid, S.FX_OK)
        else:
            self._status(rid, S.FX_OP_UNSUPPORTED, b"unsupported")

    def client(self, timeout=5.0):
        c = S.SFTPClient(self.client_rfile, self.client_wfile, timeout=timeout)
        c.start(timeout=5)
        return c


def test_short_reads_still_assemble_the_whole_file():
    """A server may return less than asked for at any offset; everything
    already in flight assumed a full chunk, so it must be re-asked from where
    the short reply ended."""
    data = os.urandom(S.CHUNK * 5 + 77)
    server = FakeServer(data=data, max_read=1000)
    assert server.client().read_file("/f") == data


def test_progress_ends_at_the_full_size():
    data = os.urandom(S.CHUNK * 3)
    seen = []
    FakeServer(data=data).client().read_file("/f", lambda d, t: seen.append((d, t)))
    assert seen[0] == (0, len(data)) and seen[-1] == (len(data), len(data))


def test_rename_uses_posix_rename_when_offered():
    server = FakeServer(extensions=[S.POSIX_RENAME])
    server.client().rename("/a", "/b")
    assert server.requests == [S.FXP_EXTENDED]


def test_rename_falls_back_to_plain_rename():
    server = FakeServer()
    server.client().rename("/a", "/b")
    assert server.requests == [S.FXP_RENAME]


def test_a_failure_status_is_an_sftp_error_with_its_code():
    with pytest.raises(S.SFTPError) as info:
        FakeServer().client().remove("/x")
    assert info.value.code == S.FX_OP_UNSUPPORTED
    assert "unsupported" in str(info.value)


def test_no_reply_is_a_timeout():
    client = FakeServer(silent=True).client(timeout=0.2)
    with pytest.raises(S.SFTPTimeout):
        client.stat("/x")


def test_the_session_ending_fails_what_is_waiting():
    server = FakeServer(silent=True)
    client = server.client(timeout=5)
    result = {}

    def ask():
        try:
            client.stat("/x")
        except Exception as e:  # noqa: BLE001
            result["error"] = e

    t = threading.Thread(target=ask)
    t.start()
    while not server.requests:
        pass
    server._out.close()  # the server goes away mid-request
    t.join(5)
    assert isinstance(result.get("error"), S.SFTPClosed)
    assert not client.alive
    with pytest.raises(S.SFTPClosed):
        client.stat("/y")


def test_names_that_are_not_utf8_survive_the_round_trip():
    raw = b"caf\xe9.txt"  # Latin-1, not UTF-8
    assert S.encode_name(S.decode_name(raw)) == raw
