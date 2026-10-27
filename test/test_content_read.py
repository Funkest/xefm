"""Reading files for a content search (``xefm.content_read``, issue #539): one
open per file, and on a remote storage several small files read ahead while
the search greps the current one — in walk order, within a byte budget.

Run with: python -m pytest test/test_content_read.py -v
"""

import codecs
import io
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from xefm import content_read
from xefm import app as xefm_app
from xefm.path import Path


class _Counted:
    """A path stand-in that counts its opens, with an optional delay per read
    so overlap is measurable."""

    def __init__(self, name, data, delay=0.0, log=None):
        self.name = name
        self.data = data
        self.delay = delay
        self.opens = 0
        self.log = log if log is not None else []

    def open(self, mode="r"):
        assert mode == "rb"
        self.opens += 1
        self.log.append(self.name)
        time.sleep(self.delay)
        return io.BytesIO(self.data)


def _lines(stream):
    with stream:
        return list(stream)


# --- one open, the same text ---------------------------------------------------

@pytest.mark.parametrize("data", [
    b"alpha\nneedle\n",
    b"crlf\r\nlines\r\n",
    b"old mac\rlines\r",
    codecs.BOM_UTF8 + b"needle on line one\n",
    codecs.BOM_UTF16_LE + "needle\nzwei\n".encode("utf-16-le"),
    codecs.BOM_UTF32_BE + "needle\n".encode("utf-32-be"),
    b"long " * 1000 + b"\nend\n",  # crosses the sniffed head
    "日本語\nテキスト\n".encode("utf-8"),
])
def test_open_text_reads_what_a_second_open_read(tmp_path, data):
    """The text the search sees is what opening the file again with the
    sniffed codec used to give it."""
    f = tmp_path / "f"
    f.write_bytes(data)
    encoding = content_read.text_encoding(data[:content_read.SNIFF_SIZE])
    with open(f, "r", encoding=encoding, errors="ignore") as reopened:
        expected = list(reopened)
    assert _lines(content_read.open_text(Path(str(f)))) == expected
    assert _lines(content_read.text_of(data)) == expected


def test_open_text_opens_the_file_once():
    path = _Counted("f", b"one\ntwo\n")
    assert _lines(content_read.open_text(path)) == ["one\n", "two\n"]
    assert path.opens == 1


@pytest.mark.parametrize("data", [b"", b"bin\x00ary"])
def test_nothing_to_grep_is_none(data):
    path = _Counted("f", data)
    assert content_read.open_text(path) is None
    assert content_read.text_of(data) is None


# --- read-ahead ----------------------------------------------------------------

def _candidates(paths):
    return [(p, {"size": len(p.data)}) for p in paths]


def _drain(paths, workers=4, worth=lambda e, a: True, cancel=None):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        out = []
        for entry, _attrs, read in content_read.read_ahead(
                _candidates(paths), cancel or threading.Event(), pool, workers,
                worth):
            out.append((entry.name, read.result() if read is not None else None))
        return out


def test_read_ahead_keeps_the_walk_order():
    paths = [_Counted(f"f{i}", f"{i}\n".encode(), delay=0.02 * (5 - i))
             for i in range(5)]
    assert _drain(paths) == [(f"f{i}", f"{i}\n".encode()) for i in range(5)]


def test_read_ahead_overlaps_the_reads():
    paths = [_Counted(f"f{i}", b"x\n", delay=0.05) for i in range(16)]
    start = time.monotonic()
    _drain(paths, workers=8)
    assert time.monotonic() - start < 16 * 0.05 / 3


def test_large_empty_and_unwanted_files_are_left_to_the_caller():
    big = _Counted("big", b"x" * (content_read.READ_AHEAD_FILE_MAX + 1))
    empty = _Counted("empty", b"")
    doc = _Counted("doc.pdf", b"%PDF")
    small = _Counted("small", b"x\n")
    out = _drain([big, empty, doc, small],
                 worth=lambda e, a: not e.name.endswith(".pdf"))
    assert out == [("big", None), ("empty", None), ("doc.pdf", None),
                   ("small", b"x\n")]
    assert big.opens == empty.opens == doc.opens == 0


def test_read_ahead_holds_to_its_byte_budget(monkeypatch):
    """At most READ_AHEAD_BYTES requested and not yet searched: with a budget
    of three files, the fourth is not read before the first is handed over."""
    monkeypatch.setattr(content_read, "READ_AHEAD_BYTES", 30)
    log = []
    paths = [_Counted(f"f{i}", b"x" * 10, log=log) for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        it = content_read.read_ahead(_candidates(paths), threading.Event(),
                                     pool, 8, lambda e, a: True)
        next(it)
        time.sleep(0.1)
        assert len(log) == 3
        list(it)
    assert len(log) == 8


def test_stopping_drops_the_reads_not_started():
    log = []
    paths = [_Counted(f"f{i}", b"x\n", delay=0.05, log=log) for i in range(40)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        it = content_read.read_ahead(_candidates(paths), threading.Event(),
                                     pool, 2, lambda e, a: True)
        next(it)
        it.close()
        started = len(log)
    assert started < 40
    assert len(log) == started


def test_waiting_on_a_read_gives_up_when_the_search_is_cancelled():
    from concurrent.futures import Future
    cancel = threading.Event()
    threading.Timer(0.1, cancel.set).start()
    start = time.monotonic()
    assert content_read.finished(Future(), cancel) is False
    assert time.monotonic() - start < 1


# --- the pool ------------------------------------------------------------------

def test_the_daemon_pool_runs_jobs_and_hands_back_failures():
    from xefm.worker_pool import DaemonPool
    with DaemonPool(3) as pool:
        assert [pool.submit(lambda i=i: i * 2).result() for i in range(5)] \
            == [0, 2, 4, 6, 8]
        with pytest.raises(ZeroDivisionError):
            pool.submit(lambda: 1 / 0).result()
        assert all(t.daemon for t in pool._threads) and len(pool._threads) <= 3


def test_shutting_the_daemon_pool_down_cancels_what_has_not_started():
    from xefm.worker_pool import DaemonPool
    pool = DaemonPool(1)
    gate = threading.Event()
    running = pool.submit(gate.wait)
    queued = [pool.submit(lambda: None) for _ in range(5)]
    time.sleep(0.05)
    pool.shutdown()
    assert all(f.cancelled() for f in queued)
    gate.set()
    assert running.result(timeout=1) is True
    with pytest.raises(RuntimeError):
        pool.submit(lambda: None)


# --- the search itself, over a real SFTP session ------------------------------

def _bare_app():
    app = xefm_app.XeFMApp.__new__(xefm_app.XeFMApp)
    app.flm = type("_FLM", (), {"show_hidden": False})()
    return app


def test_a_content_search_over_a_real_sftp_server(tmp_path, monkeypatch):
    """The read-ahead search of one real SFTP session finds what a local
    search of the same tree finds, line for line, in a file larger than the
    read-ahead too."""
    from sftp_server_helper import SFTP_SERVER, remote
    if SFTP_SERVER is None:
        pytest.skip("no local sftp-server")
    from xefm import ssh_connection as SC
    spawn = SC._spawn_ssh
    monkeypatch.setattr(SC, "_spawn_ssh", lambda cmd: spawn([SFTP_SERVER]))
    for i in range(5):
        for j in range(5):
            d = tmp_path / f"d{i}" / f"e{j}"
            d.mkdir(parents=True)
            (d / "a.txt").write_text(f"one\nneedle {i}{j}\nthree\n")
            (d / "b.bin").write_bytes(b"needle\x00")
    (tmp_path / "big.txt").write_text(
        "x\n" * (content_read.READ_AHEAD_FILE_MAX // 2) + "needle big\n")
    pattern = re.compile("needle")
    host = f"test-{uuid.uuid4().hex[:8]}"
    try:
        root = Path(f"ssh://{host}{remote(tmp_path)}")
        found = sorted((str(h["path"])[len(str(root)):], h["line"], h["text"])
                       for h in _bare_app()._iter_content_matches(
                           root, pattern, threading.Event()))
        local = sorted(
            ("/" + str(h["path"])[len(str(tmp_path)) + 1:].replace("\\", "/"),
             h["line"], h["text"])
            for h in _bare_app()._iter_content_matches(
                Path(str(tmp_path)), pattern, threading.Event()))
        assert found == local and len(found) == 25 + 1
    finally:
        SC.SSHConnectionManager.get_instance().close_connection(host)
