"""The SSH layer against a real ``sftp-server`` (#532).

Each host is one SFTP session over one process, and every operation is a
request on it. These run the real OpenSSH server program over a pipe (see
``sftp_server_helper``), so what is checked is what a remote host would do —
paths with spaces, symlinks, renames onto an existing file, transfers bigger
than the pipelining window, cancels, and the session going away.

Run with: python -m pytest test/test_ssh_sftp_session.py -v
"""

import os
import sys
import uuid

import pytest

from sftp_server_helper import SFTP_SERVER, connect, remote
from xefm import ssh_connection as SC
from xefm.path import Path
from xefm.sftp_client import CHUNK, WINDOW

pytestmark = pytest.mark.skipif(SFTP_SERVER is None, reason="no local sftp-server")


@pytest.fixture
def conn():
    # A host name of its own per test: the listing cache is process-wide.
    c = connect(f"test-{uuid.uuid4().hex[:8]}")
    yield c
    c.disconnect()


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "sub dir").mkdir()
    (tmp_path / "sub dir" / "a file.txt").write_bytes(b"alpha")
    (tmp_path / "b.txt").write_bytes(b"bravo!")
    return tmp_path


def test_connecting_learns_the_starting_directory(conn):
    assert conn.is_connected()
    assert conn.default_directory.startswith("/")


def test_ssh_is_asked_for_the_sftp_subsystem():
    """What runs in production: ssh with the subsystem, not an sftp batch, and
    no connection sharing to depend on."""
    cmd = SC.ssh_command("myhost", port="2222", identity_file="~/.ssh/k")
    assert cmd[0] == "ssh"
    assert cmd[-3:] == ["-s", "myhost", "sftp"]
    assert cmd[cmd.index("-p") + 1] == "2222"
    assert cmd[cmd.index("-i") + 1] == "~/.ssh/k"
    assert "BatchMode=yes" in cmd
    assert not any("Control" in arg for arg in cmd)


def test_a_listing_has_names_types_and_sizes(conn, tree):
    entries = {e["name"]: e for e in conn.list_directory(remote(tree))}
    assert set(entries) == {"sub dir", "b.txt"}  # no "." / ".."
    assert entries["sub dir"]["is_dir"] and not entries["sub dir"]["is_file"]
    assert entries["b.txt"]["is_file"] and entries["b.txt"]["size"] == 6
    assert entries["b.txt"]["mtime"] == pytest.approx(
        os.stat(tree / "b.txt").st_mtime, abs=1)


def test_a_listing_caches_every_entry_for_stat(conn, tree):
    conn.list_directory(remote(tree))
    conn._client = None  # any request now would fail
    assert conn.stat(remote(tree) + "/b.txt")["size"] == 6


def test_paths_are_normalized(conn, tree):
    messy = remote(tree) + "/./sub dir/../sub dir//"
    assert [e["name"] for e in conn.list_directory(messy)] == ["a file.txt"]


def test_a_missing_path_is_path_not_found_and_remembered(conn, tree):
    with pytest.raises(SC.SSHPathNotFoundError):
        conn.list_directory(remote(tree) + "/nope")
    conn._client = None
    with pytest.raises(SC.SSHPathNotFoundError):  # from the cache, no request
        conn.list_directory(remote(tree) + "/nope")


def test_round_trip_larger_than_the_window(conn, tree):
    data = os.urandom(CHUNK * WINDOW * 2 + 1234)
    target = remote(tree) + "/sub dir/big.bin"
    seen = []
    conn.write_file(target, data, progress=lambda done, total: seen.append((done, total)))
    assert seen[0] == (0, len(data)) and seen[-1] == (len(data), len(data))
    assert (tree / "sub dir" / "big.bin").read_bytes() == data
    seen.clear()
    assert conn.read_file(target, progress=lambda d, t: seen.append(d)) == data
    assert seen[0] == 0 and seen[-1] == len(data)
    assert seen == sorted(seen)


def test_an_empty_file(conn, tree):
    conn.write_file(remote(tree) + "/empty", b"")
    assert conn.read_file(remote(tree) + "/empty") == b""


def test_a_cancel_reaches_the_caller_unchanged(conn, tree):
    """The progress callback is the cancel point: what it raises comes out of
    read_file / write_file as is, not as an SSHError, and the session lives on."""
    class Cancelled(Exception):
        pass

    def cancel(done, total):
        if done > CHUNK:
            raise Cancelled()

    data = os.urandom(CHUNK * 8)
    with pytest.raises(Cancelled):
        conn.write_file(remote(tree) + "/c.bin", data, progress=cancel)
    (tree / "d.bin").write_bytes(data)
    with pytest.raises(Cancelled):
        conn.read_file(remote(tree) + "/d.bin", progress=cancel)
    assert conn.is_connected()
    assert conn.read_file(remote(tree) + "/b.txt") == b"bravo!"


def test_rename_replaces_an_existing_target(conn, tree):
    conn.rename(remote(tree) + "/b.txt", remote(tree) + "/sub dir/a file.txt")
    assert (tree / "sub dir" / "a file.txt").read_bytes() == b"bravo!"
    assert not (tree / "b.txt").exists()


def test_create_and_delete(conn, tree):
    base = remote(tree)
    conn.create_directory(base + "/new dir")
    conn.write_file(base + "/new dir/x", b"x")
    with pytest.raises(SC.SSHError):
        conn.delete_directory(base + "/new dir")  # not empty
    conn.delete_file(base + "/new dir/x")
    conn.delete_directory(base + "/new dir")
    assert not (tree / "new dir").exists()
    with pytest.raises(SC.SSHPathNotFoundError):
        conn.delete_file(base + "/new dir/x")


def test_writes_invalidate_the_cached_listing(conn, tree):
    base = remote(tree)
    assert len(conn.list_directory(base)) == 2
    conn.write_file(base + "/c.txt", b"c")
    assert len(conn.list_directory(base)) == 3


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_a_symlink_reports_its_target_but_stays_a_link(conn, tree):
    """As for a local directory: a link to a directory can be browsed into."""
    os.symlink(tree / "sub dir", tree / "link")
    os.symlink(tree / "gone", tree / "broken")
    entries = {e["name"]: e for e in conn.list_directory(remote(tree))}
    assert entries["link"]["is_dir"] and entries["link"]["is_symlink"]
    assert entries["broken"]["is_symlink"] and not entries["broken"]["is_dir"]
    conn._cache.clear()
    assert conn.stat(remote(tree) + "/link")["is_dir"]


def test_requests_from_many_threads_share_the_session(conn, tree):
    from concurrent.futures import ThreadPoolExecutor
    for i in range(20):
        (tree / f"f{i}").write_bytes(bytes([i]) * (CHUNK + i))
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(
            lambda i: conn.read_file(remote(tree) + f"/f{i}"), range(20)))
    assert results == [bytes([i]) * (CHUNK + i) for i in range(20)]


@pytest.fixture
def via_sftp_server(monkeypatch):
    """Every connection the manager opens runs over a local sftp-server."""
    spawn = SC._spawn_ssh
    monkeypatch.setattr(SC, "_spawn_ssh", lambda cmd: spawn([SFTP_SERVER]))


def test_a_dead_session_is_a_lost_connection_and_is_replaced(tree, via_sftp_server):
    host = f"test-{uuid.uuid4().hex[:8]}"
    manager = SC.SSHConnectionManager.get_instance()
    try:
        conn = manager.get_connection(host, {})
        conn._process.kill()
        conn._process.wait()
        with pytest.raises(SC.SSHConnectionLostError):
            conn.read_file(remote(tree) + "/b.txt")
        assert not conn.is_connected()
        again = manager.get_connection(host, {})
        assert again is not conn and again.is_connected()
        assert again.read_file(remote(tree) + "/b.txt") == b"bravo!"
    finally:
        manager.close_connection(host)


def test_the_path_layer_end_to_end(tree, via_sftp_server):
    """``ssh://`` paths reach the session through the manager."""
    host = f"test-{uuid.uuid4().hex[:8]}"
    manager = SC.SSHConnectionManager.get_instance()
    try:
        root = Path(f"ssh://{host}{remote(tree)}")
        assert sorted(p.name for p in root.iterdir()) == ["b.txt", "sub dir"]
        assert (root / "sub dir").is_dir()
        assert (root / "b.txt").read_bytes() == b"bravo!"
        (root / "sub dir" / "n.txt").write_bytes(b"new")
        assert (tree / "sub dir" / "n.txt").read_bytes() == b"new"
        assert not (root / "nope").exists()
    finally:
        manager.close_connection(host)


def test_a_login_that_fails_says_why():
    """ssh exiting before the session starts is a login failure; what it
    printed decides which one."""
    script = "import sys; sys.stderr.write('user@host: Permission denied (publickey).\\n')"
    conn = SC.SSHConnection("h", {},
                            spawn=lambda cmd: SC._spawn_ssh([sys.executable, "-c", script]))
    with pytest.raises(SC.SSHAuthenticationError):
        conn.connect()
    script = "import sys; sys.stderr.write('Host key verification failed.\\n')"
    conn = SC.SSHConnection("h", {},
                            spawn=lambda cmd: SC._spawn_ssh([sys.executable, "-c", script]))
    with pytest.raises(SC.SSHError, match="Host key verification failed"):
        conn.connect()
    assert not conn.is_connected()
