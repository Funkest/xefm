"""Reading files for a content search.

Two things keep a search across many small files from being bound by round
trips (issue #539):

- **One open per file.** The encoding sniff reads the first bytes and the
  search goes on from the same handle (:func:`open_text`), instead of opening
  the file a second time to read it as text. Over SFTP an open is round trips
  of its own, and ``SSHPathImpl.open`` fetches the whole file each time.
- **Reading ahead.** On a remote storage, :func:`read_ahead` reads the next
  small files on the operation's pool while the search greps the current one,
  as many at once as the walk lists directories. Results still come in walk
  order. A large file is not read ahead; the search streams it itself when it
  gets there, as before.

The memory a read-ahead may hold is capped in bytes, not only in files: at most
:data:`READ_AHEAD_BYTES` of files requested and not yet searched.
"""

from __future__ import annotations

import io
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, wait
from typing import Callable, Iterable, Iterator, Optional, Tuple

from xefm.text_encoding import sniff_bom

#: How much of a file decides its encoding (and whether it is text at all).
SNIFF_SIZE = 1024

#: The largest file read ahead whole. Bigger ones are streamed by the search.
READ_AHEAD_FILE_MAX = 1024 * 1024

#: Bytes of read-ahead requested and not yet handed to the search, at most.
READ_AHEAD_BYTES = 16 * 1024 * 1024

#: Files queued ahead of the search, at most, per worker — what bounds the
#: queue when the files are empty or too large to read ahead.
_QUEUE_PER_WORKER = 4


def text_encoding(head: bytes) -> Optional[str]:
    """The codec a search reads a file with, from its first bytes ``head``, or
    ``None`` for a file with nothing to grep (binary, empty). A Unicode BOM names
    the text outright and must be honored *before* the NUL sniff — UTF-16/32
    text is full of NULs by construction and used to be skipped as binary
    (issue #305); the self-detecting codec consumes the BOM so it never shadows
    a line-1 match. Without a BOM, a NUL in the first chunk means binary, and
    clean bytes read as UTF-8."""
    if not head:
        return None
    bom = sniff_bom(head)
    if bom is not None:
        codec = bom[1]
        if codec.startswith("utf-16"):
            return "utf-16"
        if codec.startswith("utf-32"):
            return "utf-32"
        return "utf-8-sig"
    if b"\x00" in head:
        return None
    return "utf-8"


class _Prefixed(io.RawIOBase):
    """The bytes already read off ``f``, then the rest of ``f``: a binary
    stream that starts where ``f`` started, without seeking it back."""

    def __init__(self, head: bytes, f):
        super().__init__()
        self._head = head
        self._f = f

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        if self._head:
            n = min(len(buffer), len(self._head))
            buffer[:n] = self._head[:n]
            self._head = self._head[n:]
            return n
        data = self._f.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def close(self) -> None:
        if not self.closed:
            try:
                self._f.close()
            finally:
                super().close()


def open_text(path) -> Optional[io.TextIOBase]:
    """``path`` opened once and read as text — lines in universal-newline
    mode, undecodable bytes dropped — or ``None`` for a file with nothing to
    grep (:func:`text_encoding`). The caller closes what it gets."""
    f = path.open("rb")
    try:
        head = f.read(SNIFF_SIZE)
        encoding = text_encoding(head)
    except BaseException:
        f.close()
        raise
    if encoding is None:
        f.close()
        return None
    return io.TextIOWrapper(io.BufferedReader(_Prefixed(head, f)),
                            encoding=encoding, errors="ignore")


def text_of(data: bytes) -> Optional[io.TextIOBase]:
    """A file's bytes, already read, as :func:`open_text` would read them."""
    encoding = text_encoding(data[:SNIFF_SIZE])
    if encoding is None:
        return None
    return io.TextIOWrapper(io.BytesIO(data), encoding=encoding, errors="ignore")


def _read_whole(path) -> Optional[bytes]:
    """All of ``path``, or ``None`` when it turns out larger than
    :data:`READ_AHEAD_FILE_MAX` (it grew since it was listed) — the search
    then streams it like any large file."""
    with path.open("rb") as f:
        data = f.read(READ_AHEAD_FILE_MAX + 1)
    return None if len(data) > READ_AHEAD_FILE_MAX else data


def read_ahead(candidates: Iterable[Tuple[object, dict]], cancel,
               pool, workers: int,
               worth_reading: Callable[[object, dict], bool]
               ) -> Iterator[Tuple[object, dict, Optional[Future]]]:
    """Yield ``(entry, attrs, read)`` for each of ``candidates``, in their
    order. ``read`` is a future of the whole file's bytes (``None`` once it
    turned out too large) for an entry ``worth_reading`` and no larger than
    :data:`READ_AHEAD_FILE_MAX`, read on ``pool`` (a
    :class:`~xefm.worker_pool.DaemonPool`); ``None`` for one the caller reads
    itself. Wait on it with :func:`finished`.

    The read never waits on anything but the storage, and the consumer holds
    nothing while it waits on a read, so sharing ``pool`` with the walk's
    listings cannot deadlock. Stops when ``cancel`` is set or the consumer
    stops iterating; reads not started are dropped then."""
    queue: deque = deque()
    queued_bytes = 0
    limit = max(1, workers) * _QUEUE_PER_WORKER
    source = iter(candidates)
    exhausted = False
    try:
        while True:
            while (not exhausted and len(queue) < limit
                   and queued_bytes < READ_AHEAD_BYTES):
                if cancel.is_set():
                    return
                try:
                    entry, attrs = next(source)
                except StopIteration:
                    exhausted = True
                    break
                size = attrs.get("size") or 0
                read = None
                if 0 < size <= READ_AHEAD_FILE_MAX and worth_reading(entry, attrs):
                    read = pool.submit(_read_whole, entry)
                    queued_bytes += size
                queue.append((entry, attrs, read, size))
            if not queue or cancel.is_set():
                return
            entry, attrs, read, size = queue.popleft()
            if read is not None:
                queued_bytes -= size
            yield entry, attrs, read
    finally:
        for _entry, _attrs, read, _size in queue:
            if read is not None:
                read.cancel()


#: How often a wait on a read looks at the cancel flag.
_CANCEL_POLL = 0.1


def finished(read: Future, cancel) -> bool:
    """Wait for ``read`` until it is done — True — or ``cancel`` is set —
    False — so a cancelled search does not sit on a read of a slow storage."""
    while not read.done():
        if cancel.is_set():
            return False
        wait([read], timeout=_CANCEL_POLL, return_when=FIRST_COMPLETED)
    return not cancel.is_set()
