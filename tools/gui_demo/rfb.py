"""Minimal RFB (VNC) client: raw frames in, keys and pointer out."""
import socket, struct, threading, time
import numpy as np
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes


def _des(key8: bytes, data: bytes) -> bytes:
    k = bytes(int(f"{b:08b}"[::-1], 2) for b in key8)   # VNC mirrors each key byte
    enc = Cipher(TripleDES(k * 3), modes.ECB()).encryptor()
    return enc.update(data) + enc.finalize()


class RFB:
    def __init__(self, host, port, password):
        self.s = socket.create_connection((host, port))
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        ver = self._recv(12)
        self.s.sendall(b"RFB 003.008\n")
        n = self._recv(1)[0]
        types = list(self._recv(n))
        if 2 in types:
            self.s.sendall(b"\x02")
            ch = self._recv(16)
            key = (password.encode() + b"\0" * 8)[:8]
            self.s.sendall(_des(key, ch))
        elif 1 in types:
            self.s.sendall(b"\x01")
        else:
            raise RuntimeError(f"security types {types}")
        res = struct.unpack(">I", self._recv(4))[0]
        if res != 0:
            raise RuntimeError("auth failed")
        self.s.sendall(b"\x01")  # shared
        w, h = struct.unpack(">HH", self._recv(4))
        self._recv(16)
        name_len = struct.unpack(">I", self._recv(4))[0]
        self.name = self._recv(name_len).decode(errors="replace")
        self.w, self.h = w, h
        # 32bpp, little endian, true colour, r<<16 g<<8 b: BGRX in memory.
        pf = struct.pack(">BBBBHHHBBB3x", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        self.s.sendall(b"\x00\x00\x00\x00" + pf)
        # Raw, plus DesktopSize / ExtendedDesktopSize: the Virtualization
        # framework's server asserts on a client without them.
        encodings = [0, -223, -308]
        self.s.sendall(struct.pack(">BxH", 2, len(encodings))
                       + b"".join(struct.pack(">i", e) for e in encodings))
        self.fb = np.zeros((h, w, 4), np.uint8)
        self.lock = threading.Lock()
        self.updates = 0
        self.ver = ver

    def _recv(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return bytes(buf)

    def _recv_into(self, view):
        got = 0
        while got < len(view):
            r = self.s.recv_into(view[got:])
            if not r:
                raise ConnectionError("closed")
            got += r

    def request(self, incremental=True):
        self.s.sendall(struct.pack(">BBHHHH", 3, int(incremental), 0, 0, self.w, self.h))

    def read_message(self):
        t = self._recv(1)[0]
        if t == 0:
            (n,) = struct.unpack(">xH", self._recv(3))
            for _ in range(n):
                x, y, w, h, enc = struct.unpack(">HHHHi", self._recv(12))
                if enc in (-223, -308):
                    if enc == -308:
                        screens = self._recv(4)[0]
                        self._recv(16 * screens)
                    with self.lock:
                        self.w, self.h = w, h
                        self.fb = np.zeros((h, w, 4), np.uint8)
                    self.resized = (w, h)
                elif enc == 0:
                    buf = bytearray(w * h * 4)
                    self._recv_into(memoryview(buf))
                    with self.lock:
                        self.fb[y:y + h, x:x + w] = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
                else:
                    raise RuntimeError(f"encoding {enc}")
            self.updates += 1
            return "update"
        if t == 1:
            first, n = struct.unpack(">xHH", self._recv(5))
            self._recv(6 * n)
            return "colormap"
        if t == 2:
            return "bell"
        if t == 3:
            _, ln = struct.unpack(">3sI", self._recv(7))
            self._recv(ln)
            return "cut"
        raise RuntimeError(f"message {t}")

    def key(self, keysym, down):
        self.s.sendall(struct.pack(">BBxxI", 4, int(down), keysym))

    def pointer(self, x, y, buttons=0):
        self.s.sendall(struct.pack(">BBHH", 5, buttons, x, y))

    def snapshot(self):
        with self.lock:
            return self.fb.copy()
