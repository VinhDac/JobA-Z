"""STOP flags — one place, one flag per stage.

Why this exists: the scheduler's `stop()` only blocks the NEXT run. A scan
already under way takes 8-16 minutes because it opens Chrome and reads each
posting; pressing Stop and watching it carry on is a button that lies — the
exact kind of button this project has had to kill three times.

Why PER STAGE rather than one shared flag: stopping the scan must not also
stop the mailbox pass running alongside it. Each function has its own Stop
button, so each needs its own flag.

Work in flight checks `wanted(stage)` at the points where it can break —
between two sources, between two pages — then stops cleanly and says so. It
does NOT kill a thread mid-flight: half a transaction written to the DB is
worse than finishing the one in hand.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_flags: dict[str, threading.Event] = {}


def _flag(stage: str) -> threading.Event:
    with _lock:
        return _flags.setdefault(stage, threading.Event())


def ask(stage: str) -> None:
    """Ask this stage to stop at its next break point."""
    _flag(stage).set()


def clear(stage: str) -> None:
    """Starting a fresh run — clear the old flag, or this run stops at once."""
    _flag(stage).clear()


def wanted(stage: str) -> bool:
    return _flag(stage).is_set()
