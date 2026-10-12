"""Walking a directory tree, listing several directories at once where the
storage rewards it.

A walk costs one listing per directory. On a local disk that is a syscall and
the walk is bound by the disk; on a remote one each listing is round trips, and
a walk that waits for one directory before asking for the next is bound by
latency times the number of directories — a deep tree over SFTP spent nearly
all its time waiting. :func:`walk` keeps up to the backend's
``LISTING_CONCURRENCY`` listings in flight instead (see
:meth:`xefm.path.PathImpl`), which an SFTP session serves side by side. A
backend that leaves it at 1 gets the plain depth-first walk it always had.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, Iterator, Tuple

#: How often a parallel walk waiting on listings looks at its cancel flag.
_CANCEL_POLL = 0.1


def walk(root, cancel, descend: Callable[[object, dict], bool]
         ) -> Iterator[Tuple[object, dict]]:
    """Yield ``(entry, attrs)`` for every entry under ``root``
    (:meth:`Path.listdir_attrs` records), descending into each entry for which
    ``descend(entry, attrs)`` is true. A directory that cannot be listed is
    skipped. Stops as soon as ``cancel`` (a ``threading.Event``) is set, and
    when the consumer stops iterating.

    Order: each directory's entries come together and in its listing order.
    With one listing at a time the walk is depth-first; with several, a
    directory's entries come when its listing does, so the order across
    directories follows the storage, not the tree."""
    workers = root.listing_concurrency()
    if workers <= 1:
        yield from _walk_sequential(root, cancel, descend)
    else:
        yield from _walk_parallel(root, cancel, descend, workers)


def _walk_sequential(root, cancel, descend):
    stack = [root]
    while stack:
        if cancel.is_set():
            return
        try:
            entries = stack.pop().listdir_attrs()
        except Exception:
            continue
        for entry, attrs in entries:
            if cancel.is_set():
                return
            if descend(entry, attrs):
                stack.append(entry)
            yield entry, attrs


def _walk_parallel(root, cancel, descend, workers: int):
    """Up to ``workers`` listings in flight. A directory is queued the moment
    its parent's listing names it — before its siblings are handed to the
    consumer — so the listings keep running while the consumer works."""
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="xefm-walk")
    pending = {pool.submit(root.listdir_attrs)}
    try:
        while pending:
            done, _ = wait(pending, timeout=_CANCEL_POLL, return_when=FIRST_COMPLETED)
            if cancel.is_set():
                return
            for future in done:
                pending.discard(future)
                try:
                    entries = future.result()
                except Exception:
                    continue
                subdirs = [entry for entry, attrs in entries if descend(entry, attrs)]
                pending.update(pool.submit(d.listdir_attrs) for d in subdirs)
                for item in entries:
                    if cancel.is_set():
                        return
                    yield item
    finally:
        # Listings not started are dropped; ones running finish on their own
        # and are discarded.
        pool.shutdown(wait=False, cancel_futures=True)
