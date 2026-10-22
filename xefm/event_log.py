"""An event log for whoever is driving XeFM from outside (#682).

A driver that reads XeFM's screen as text sees what the screen seems to show:
a message can scroll out of the log pane before the next look, and an
exception that only reaches the log is easy to miss among other lines. When
the environment names a file in ``QUALITY_LOOP_EVENTS`` (the name quality-loop
starts every app with; ``xefm try --keys`` sets it too), XeFM appends one
JSON object per line to it:

- ``{"t": ..., "kind": "message", "source": "info"|"error"|..., "text": ...}``
  for every line the log pane gets, in the order it gets them;
- ``{"t": ..., "kind": "exception", "logger": ..., "text": ..., "traceback": ...}``
  for every logged exception.

``t`` is seconds since the epoch. Nothing is written, and nothing costs more
than one dictionary lookup, when the variable is unset.
"""

from __future__ import annotations

import json
import os
import threading
import time

#: The variable quality-loop names a product's event log by.
EVENTS_ENV = "QUALITY_LOOP_EVENTS"

_lock = threading.Lock()


def enabled() -> bool:
    return bool(os.environ.get(EVENTS_ENV))


def write(kind: str, **fields) -> None:
    """Append one event. Never raises: a driver's log may not take down the
    file manager it is watching."""
    path = os.environ.get(EVENTS_ENV)
    if not path:
        return
    line = json.dumps({"t": round(time.time(), 3), "kind": kind, **fields},
                      ensure_ascii=False)
    try:
        with _lock, open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
