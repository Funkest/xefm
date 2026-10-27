"""A thread pool for work that is dropped when XeFM quits.

``concurrent.futures.ThreadPoolExecutor`` joins its workers when the
interpreter exits, after they finish every job they have started or queued.
For a walk or a content search on a slow remote storage that kept XeFM's
process alive after the window was gone, until every request in flight came
back. Those results have nowhere to go once the app is quitting, so
:class:`DaemonPool` runs its jobs on daemon threads, the way the search
dialog's own worker already runs: exit does not wait for them.

Only for work that has nothing left to do once the app is gone — reading and
listing. A copy keeps the executor that finishes what it started.
"""

from __future__ import annotations

import queue
import threading
from concurrent.futures import Future
from typing import Callable


class DaemonPool:
    """``size`` daemon threads running submitted jobs in order. The part of
    the ``ThreadPoolExecutor`` interface the walk and the search use:
    :meth:`submit` and :meth:`shutdown`."""

    def __init__(self, size: int, name: str = "xefm-pool"):
        self.size = max(1, size)
        self._name = name
        self._jobs: "queue.SimpleQueue" = queue.SimpleQueue()
        self._threads: list = []
        self._lock = threading.Lock()
        self._closed = False

    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        future: Future = Future()
        with self._lock:
            if self._closed:
                raise RuntimeError("cannot schedule new jobs after shutdown")
            self._jobs.put((future, fn, args, kwargs))
            if len(self._threads) < self.size:
                thread = threading.Thread(
                    target=self._work, daemon=True,
                    name=f"{self._name}_{len(self._threads)}")
                self._threads.append(thread)
                thread.start()
        return future

    def shutdown(self, wait: bool = False, cancel_futures: bool = True) -> None:
        """Stop taking jobs. Queued ones are cancelled (``cancel_futures``);
        running ones finish on their own and are discarded."""
        with self._lock:
            self._closed = True
            threads = list(self._threads)
        if cancel_futures:
            while True:
                try:
                    job = self._jobs.get_nowait()
                except queue.Empty:
                    break
                if job is not None:
                    job[0].cancel()
        for _ in threads:
            self._jobs.put(None)
        if wait:
            for thread in threads:
                thread.join()

    def __enter__(self) -> "DaemonPool":
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()

    def _work(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            future, fn, args, kwargs = job
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = fn(*args, **kwargs)
            except BaseException as e:  # handed to whoever waits on it
                future.set_exception(e)
            else:
                future.set_result(result)
