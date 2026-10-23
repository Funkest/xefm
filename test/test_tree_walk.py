"""The search walk (``xefm.tree_walk``): depth-first one listing at a time, or
several listings at once where the backend says so (SSH).

Run with: python -m pytest test/test_tree_walk.py -v
"""

import threading
import time
import uuid

import pytest

from xefm import tree_walk
from xefm.path import Path, listing_concurrency


class FakeDir:
    """A directory answering ``_listdir_attrs`` from a nested dict, with a
    delay per listing so overlap is measurable."""

    def __init__(self, name, tree, concurrency=1, delay=0.0, log=None):
        self.name = name
        self.tree = tree
        self.concurrency = concurrency
        self.delay = delay
        self.log = log if log is not None else []

    def _listing_concurrency(self):
        return self.concurrency

    def _listdir_attrs(self):
        self.log.append(self.name)
        time.sleep(self.delay)
        if self.tree is None:
            raise PermissionError(self.name)
        return [(FakeDir(f"{self.name}/{k}", v, self.concurrency, self.delay, self.log),
                 {"is_dir": isinstance(v, dict) or v is None})
                for k, v in self.tree.items()]


def _tree(depth, width):
    if depth == 0:
        return {f"f{i}": "file" for i in range(width)}
    return {**{f"d{i}": _tree(depth - 1, width) for i in range(width)}, "file": "file"}


def _names(concurrency, tree, **kw):
    root = FakeDir("r", tree, concurrency, **kw)
    return sorted(e.name for e, _a in tree_walk.walk(
        root, threading.Event(), lambda e, a: a["is_dir"]))


@pytest.mark.parametrize("concurrency", [1, 8])
def test_every_entry_once(concurrency):
    tree = _tree(3, 3)
    assert _names(concurrency, tree) == _names(1, tree)
    assert len(_names(concurrency, tree)) == 3 + 1 + 9 + 3 + 27 + 9 + 81


@pytest.mark.parametrize("concurrency", [1, 8])
def test_a_directory_that_cannot_be_listed_is_skipped(concurrency):
    tree = {"locked": None, "open": {"x": "file"}}
    assert _names(concurrency, tree) == ["r/locked", "r/open", "r/open/x"]


@pytest.mark.parametrize("concurrency", [1, 8])
def test_only_what_descend_allows_is_listed(concurrency):
    log = []
    root = FakeDir("r", {"skip": {"a": "file"}, "go": {"b": "file"}}, concurrency, log=log)
    list(tree_walk.walk(root, threading.Event(),
                        lambda e, a: a["is_dir"] and not e.name.endswith("skip")))
    assert sorted(log) == ["r", "r/go"]


def test_listings_overlap_when_the_backend_allows():
    """The point of it: a tree of 1 + 4 + 16 directories at 50 ms a listing is
    over a second one at a time, and a fraction of that eight at once."""
    tree = _tree(2, 4)
    start = time.monotonic()
    _names(1, tree, delay=0.05)
    sequential = time.monotonic() - start
    start = time.monotonic()
    _names(8, tree, delay=0.05)
    parallel = time.monotonic() - start
    assert sequential > 1.0
    assert parallel < sequential / 3


def test_cancel_stops_the_parallel_walk():
    cancel = threading.Event()
    log = []
    root = FakeDir("r", _tree(4, 4), 4, delay=0.01, log=log)
    seen = 0
    for _ in tree_walk.walk(root, cancel, lambda e, a: a["is_dir"]):
        seen += 1
        if seen == 5:
            cancel.set()
    listed = len(log)
    time.sleep(0.1)
    assert len(log) <= listed + 4  # at most the listings already running


def test_backends_declare_their_concurrency(tmp_path):
    assert listing_concurrency(Path(str(tmp_path))) == 1
    from xefm.ssh import SSHPathImpl
    assert SSHPathImpl.LISTING_CONCURRENCY > 1


def test_an_ssh_tree_walk_over_a_real_sftp_server(tmp_path, monkeypatch):
    """The parallel walk against one real SFTP session finds what a local walk
    of the same tree finds."""
    from sftp_server_helper import SFTP_SERVER, remote
    if SFTP_SERVER is None:
        pytest.skip("no local sftp-server")
    from xefm import ssh_connection as SC
    spawn = SC._spawn_ssh
    monkeypatch.setattr(SC, "_spawn_ssh", lambda cmd: spawn([SFTP_SERVER]))
    for i in range(6):
        for j in range(6):
            d = tmp_path / f"d{i}" / f"e{j}"
            d.mkdir(parents=True)
            (d / "leaf.txt").write_text("x")
    host = f"test-{uuid.uuid4().hex[:8]}"
    try:
        root = Path(f"ssh://{host}{remote(tmp_path)}")
        found = sorted(str(e)[len(str(root)):] for e, _a in tree_walk.walk(
            root, threading.Event(), lambda e, a: a["is_dir"]))
        local = sorted("/" + str(e)[len(str(tmp_path)) + 1:].replace("\\", "/")
                       for e, _a in tree_walk.walk(
                           Path(str(tmp_path)), threading.Event(),
                           lambda e, a: a["is_dir"]))
        assert found == local and len(found) == 6 + 36 + 36
    finally:
        SC.SSHConnectionManager.get_instance().close_connection(host)
