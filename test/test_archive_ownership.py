"""Tests for archive ownership in the archive cache (issue #516): an archive is
open while a pane shows it or a read / task holds it, closes soon after nobody
does, and an operation that would delete, move or overwrite one in use fails
naming who uses it instead of with a bare sharing violation."""

import io
import os
import tarfile
import tempfile
import threading
import zipfile

import pytest

from xefm import _config
from xefm import archive as A
from xefm.archive import ArchiveCache, ArchiveInUseError, release_archives_under
from xefm.file_operations import FileOperationService
from xefm.path import Path


@pytest.fixture
def tmp(tmp_path):
    # realpath: on macOS the sandbox TMPDIR hides a /var -> /private/var link,
    # and cache keys are compared as strings.
    return os.path.realpath(str(tmp_path))


def _zip(path, members=("a.txt",)):
    with zipfile.ZipFile(path, "w") as zf:
        for name in members:
            zf.writestr(name, f"content of {name}")
    return path


def _tar_gz(path):
    with tarfile.open(path, "w:gz") as tf:
        data = b"x" * 200_000
        info = tarfile.TarInfo("big.bin")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return path


@pytest.fixture
def cache(monkeypatch):
    """A fresh global cache with no idle grace, so a sweep closes at once."""
    c = ArchiveCache(max_open=5, ttl=300, idle_close=0)
    monkeypatch.setattr(A, "_archive_cache", c)
    yield c
    c.clear()


def _member(zip_path, internal=""):
    return Path(f"archive://{zip_path}#{internal}")


def test_idle_archive_closes_after_listing(tmp, cache):
    z = _zip(os.path.join(tmp, "a.zip"))
    list(_member(z).iterdir())
    handler = cache._handlers[str(Path(z).absolute())]
    assert handler._archive_obj is not None
    assert cache.sweep() == 1
    assert cache._handlers == {}
    assert handler._archive_obj is None


def test_idle_grace_keeps_archive_briefly(tmp):
    c = ArchiveCache(idle_close=60)
    z = _zip(os.path.join(tmp, "a.zip"))
    c.get_handler(Path(z))
    assert c.sweep() == 0
    assert len(c._handlers) == 1
    c.clear()


def test_pane_pin_keeps_archive_open(tmp, cache):
    z = _zip(os.path.join(tmp, "a.zip"))
    shown = {"path": _member(z)}
    cache.add_pin_source(
        lambda: [("shown in the left pane", A.get_member_archive_path(shown["path"]))])
    list(shown["path"].iterdir())
    assert cache.sweep() == 0
    assert len(cache._handlers) == 1
    # The pane leaves: the next sweep closes it.
    shown["path"] = Path(tmp)
    assert cache.sweep() == 1


def test_release_under_closes_idle_archive(tmp, monkeypatch):
    z = _zip(os.path.join(tmp, "a.zip"))
    c = ArchiveCache(idle_close=60)  # grace long enough that only release closes it
    monkeypatch.setattr(A, "_archive_cache", c)
    try:
        c.get_handler(Path(z))
        release_archives_under(Path(z))
        assert c._handlers == {}
    finally:
        c.clear()


def test_release_under_reports_pane(tmp, cache):
    z = _zip(os.path.join(tmp, "a.zip"))
    cache.add_pin_source(lambda: [("shown in the right pane", Path(z))])
    with pytest.raises(ArchiveInUseError) as info:
        release_archives_under(Path(z))
    assert "'a.zip' is shown in the right pane" in str(info.value)
    # An OSError, so rename paths that already catch OSError report it.
    assert isinstance(info.value, OSError)


def test_release_under_reports_lease(tmp, cache):
    z = _zip(os.path.join(tmp, "a.zip"))
    with cache.lease(Path(z)):
        with pytest.raises(ArchiveInUseError, match="being read"):
            release_archives_under(Path(z))
    release_archives_under(Path(z))
    assert cache._handlers == {}


def test_release_under_directory_and_not_sibling(tmp, cache):
    os.makedirs(os.path.join(tmp, "d", "sub"))
    os.makedirs(os.path.join(tmp, "dx"))
    inner = _zip(os.path.join(tmp, "d", "sub", "in.zip"))
    sibling = _zip(os.path.join(tmp, "dx", "out.zip"))
    cache.add_pin_source(lambda: [("shown in the left pane", Path(sibling))])
    cache.get_handler(Path(inner))
    cache.get_handler(Path(sibling))
    release_archives_under(Path(os.path.join(tmp, "d")))  # sibling not under "d"
    assert list(cache._handlers) == [str(Path(sibling).absolute())]


def test_pin_does_not_open(tmp, cache):
    z = _zip(os.path.join(tmp, "a.zip"))
    unpin = cache.pin(Path(z), "used by a running copy")
    assert cache._handlers == {}
    with pytest.raises(ArchiveInUseError, match="used by a running copy"):
        release_archives_under(Path(z))
    unpin()
    release_archives_under(Path(z))


def test_lease_survives_tar_stream(tmp, cache):
    """The lease spans the whole member stream: a release mid-copy must not close
    the tar under it (tarfile would fail with 'seek of closed file')."""
    t = _tar_gz(os.path.join(tmp, "a.tar.gz"))
    member = Path(f"archive://{t}#big.bin")

    out = io.BytesIO()
    errors = []

    def progress(done, total):
        if done == len(out.getvalue()) and not errors:
            try:
                release_archives_under(Path(t))
            except ArchiveInUseError as exc:
                errors.append(exc)

    member._impl.extract_to_stream(out, progress)
    assert len(out.getvalue()) == 200_000
    assert errors and "being read" in str(errors[0])


def test_slow_open_does_not_block_other_archives(tmp, cache, monkeypatch):
    slow = _zip(os.path.join(tmp, "slow.zip"))
    fast = _zip(os.path.join(tmp, "fast.zip"))
    started, go = threading.Event(), threading.Event()
    real_open = A.ZipHandler.open

    def gated_open(self):
        if self._archive_path.name == "slow.zip":
            started.set()
            go.wait(5)
        real_open(self)

    monkeypatch.setattr(A.ZipHandler, "open", gated_open)
    t = threading.Thread(target=lambda: cache.get_handler(Path(slow)))
    t.start()
    assert started.wait(5)
    try:
        cache.get_handler(Path(fast))  # would deadlock under one global open lock
        assert str(Path(fast).absolute()) in cache._handlers
    finally:
        go.set()
        t.join(5)


# --- file operations ---------------------------------------------------------

@pytest.fixture
def svc():
    c = _config.Config()
    c.CONFIRM_COPY = c.CONFIRM_MOVE = c.CONFIRM_DELETE = False
    return FileOperationService(c)


def _run(method, *args, **kw):
    result = {}
    method(None, *args, on_complete=lambda r: result.update(r), background=False, **kw)
    return result


def test_delete_browsed_archive_closes_it_first(tmp, svc, monkeypatch):
    c = ArchiveCache(idle_close=60)
    monkeypatch.setattr(A, "_archive_cache", c)
    try:
        z = _zip(os.path.join(tmp, "a.zip"))
        list(_member(z).iterdir())
        result = _run(svc.delete, [Path(z)])
        assert result["done"] == 1 and not result["errors"]
        assert not os.path.exists(z)
        assert c._handlers == {}
    finally:
        c.clear()


def test_delete_archive_shown_in_pane_fails_with_reason(tmp, svc, cache):
    z = _zip(os.path.join(tmp, "a.zip"))
    other = _zip(os.path.join(tmp, "b.zip"))
    cache.add_pin_source(lambda: [("shown in the left pane", Path(z))])
    result = _run(svc.delete, [Path(z), Path(other)])
    assert result["failed"] == 1 and result["done"] == 1
    assert "shown in the left pane" in result["errors"][0][1]
    assert os.path.exists(z) and not os.path.exists(other)


def test_overwrite_archive_in_use_fails_with_reason(tmp, svc, cache):
    src_dir = os.path.join(tmp, "src")
    dst_dir = os.path.join(tmp, "dst")
    os.makedirs(src_dir)
    os.makedirs(dst_dir)
    _zip(os.path.join(src_dir, "a.zip"), members=("new.txt",))
    dest = _zip(os.path.join(dst_dir, "a.zip"))
    cache.add_pin_source(lambda: [("shown in the right pane", Path(dest))])
    plan = [(Path(os.path.join(src_dir, "a.zip")), Path(dest), True)]
    result = {"errors": [], "failed": 0}
    kept = svc._release_archives("copy", plan, result, None)
    assert kept == [] and result["failed"] == 1
    assert "shown in the right pane" in result["errors"][0][1]


def test_copy_out_of_archive_pins_it_for_the_task(tmp, svc, cache, monkeypatch):
    z = _zip(os.path.join(tmp, "a.zip"))
    dest = os.path.join(tmp, "out")
    os.makedirs(dest)
    seen = []
    real_run = svc._run

    def spy(task, kind, targets, dest_dir, panel, log, z_):
        try:
            release_archives_under(Path(z))
        except ArchiveInUseError as exc:
            seen.append(str(exc))
        return real_run(task, kind, targets, dest_dir, panel, log, z_)

    monkeypatch.setattr(svc, "_run", spy)
    result = _run(svc.copy, [_member(z, "a.txt")], Path(dest))
    assert result["done"] == 1
    assert seen and "used by a running copy" in seen[0]
    assert cache._owners == {}  # released when the task ended
