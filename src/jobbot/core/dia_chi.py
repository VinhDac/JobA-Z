"""The address of the live run — written to a file so the OUTSIDE can read it.

Why it is needed: the server no longer sits on a fixed 8765. `serve()` lets
the operating system hand out a free port, so the port changes from run to
run. Meanwhile `start.command` (double-click to open) was asking for exactly
8765 — measured: with the app alive on 8766, a double-click does NOT open it,
it boots a SECOND run on top of the same SQLite file.

A flat two-line file, deliberately:

    http://127.0.0.1:8766/
    54321

Line 1 the address, line 2 the PID. A shell reads it with `head -1` — no
Python needed, and whoever edits `start.command` later does not have to learn
a format.

AN OLD FILE IS NOT TRUSTWORTHY, and that is the design, not an oversight. If
the app is kill -9'd or the power drops, nobody gets to delete the file. So
the READER has to verify for itself: ask `/api/alive` whether it really is
jobbot answering. Deleting the file only on a clean exit is a trap — it
teaches the reader that "file exists means running".
"""

from __future__ import annotations

import os

from .paths import data_dir

TEN = "dang-chay.txt"


def tep():
    return data_dir() / TEN


def ghi(url: str) -> None:
    """Write address + PID. On failure stay quiet — not worth killing a boot."""
    try:
        tep().write_text(f"{url}\n{os.getpid()}\n", encoding="utf-8")
    except OSError:
        pass


def doc() -> tuple[str, int] | None:
    """(url, pid) if readable. Does NOT promise it is still alive — see the
    module docstring."""
    try:
        dong = tep().read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not dong or not dong[0].startswith("http://127.0.0.1:"):
        return None
    try:
        pid = int(dong[1]) if len(dong) > 1 else 0
    except ValueError:
        pid = 0
    return dong[0].strip(), pid


def xoa() -> None:
    try:
        tep().unlink()
    except OSError:
        pass
