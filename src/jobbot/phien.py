"""A SESSION — one pass through the whole pipeline.

Each stage used to have its own button, and the user had to remember the
order: run Search, switch to CV and press Run, then switch to Manage and
press Scan mail. Three presses for one job, and forgetting a step said
nothing — it just meant fewer CV versions in the morning.

A session merges those three into ONE, and the background loop repeats it
24/7.

    Search       find new postings, filter, score
    Make CV      re-lay the CV against each posting in the store
    Manage mail  read the mailbox and update the table

THE ORDER IS PART OF THE DEFINITION, not an accident. Building CVs reads the
posting store, so it must run AFTER the search; run it before and it lays out
against the previous loop's store, and every loop is one beat behind. Mail
goes last because it depends on neither of the others — but going last means
the Manage table is always the freshest thing the user sees on opening the
app.

SEQUENTIAL, NOT PARALLEL. All three write one SQLite file, and Search also
drives Chrome. Overlapping them buys exactly one thing: two places locking
one table, and no speed at all, because the bottleneck is the network.

ONE BROKEN STAGE MUST NOT KILL THE SESSION. If the mailbox loses the network
the search still has to finish — so each stage has its own fence, and a
failure is logged before moving on to the next.
"""

from __future__ import annotations

import sqlite3

from .core import prefs
from .core.journal import SYSTEM, log as jlog


def dang_bat(conn: sqlite3.Connection) -> list[str]:
    """The names of the stages that are ON, in execution order.

    The order comes from `prefs.PHIEN` rather than being retyped here:
    retyping is two sources for one truth, and one day the Adjust panel will
    list one order while the session runs another.
    """
    return [khuc for khoa, (khuc, _ten, _y) in prefs.PHIEN.items()
            if prefs.flag(conn, khoa)]


def _search(conn: sqlite3.Connection) -> str:
    from .scan_runner import run_scan
    return (run_scan() or {}).get("summary", "")


def _cv(conn: sqlite3.Connection) -> str:
    from .cv import batch
    ra = batch.run(conn) or {}
    return f"{len(ra.get('versions') or [])} CV versions"


def _mail(conn: sqlite3.Connection) -> str:
    from .track import scan as tscan
    tscan.run(conn)
    tscan.noi_lai(conn)
    return "mailbox read"


CHAY = {"search": _search, "cv": _cv, "track": _mail}


def chay(conn: sqlite3.Connection | None = None) -> dict:
    """Run one loop. Returns which stages ran, which failed, and why.

    NEVER raises out. This is called from the scheduler's background thread,
    and an exception escaping it kills the 24/7 loop — the app silently stops
    working with nothing on screen saying so.
    """
    from .core import db, halt

    tu_mo = conn is None
    conn = conn or db.connect()
    xong, hong = [], []
    try:
        khuc = dang_bat(conn)
        if not khuc:
            # ALL THREE OFF has to be said out loud. A session that runs and
            # does nothing, in silence, is the fastest way to convince a user
            # the app is broken.
            jlog.warn(SYSTEM, "session ran but all three stages are OFF — "
                              "turn one back on with ⚟ on the Overview bar")
            return {"xong": [], "hong": [], "tat": True}
        ten = {khuc: nhan for _k, (khuc, nhan, _y) in prefs.PHIEN.items()}
        # CLEAR THE STOP FLAGS AT THE START OF EVERY SESSION.
        #
        # "Stop" means stop THE LOOP IN FLIGHT, not poison every future one.
        # The previous version only cleared them in /api/session/start, so
        # restarting from the background loop or from /batphien on Telegram
        # left the flags set: every later session ran 0/3 stages and reported
        # "done" — a textbook silent failure.
        #
        # Cleared HERE because this is the ONE place a session begins,
        # whoever called it. Doing it per entry point means remembering on
        # the next entry point, and that will be forgotten.
        for s in khuc:
            halt.clear(s)
        jlog.ok(SYSTEM, "session started — " + " → ".join(ten[s] for s in khuc))
        for s in khuc:
            if halt.wanted(s):
                # The user pressed Stop mid-session: drop the remaining
                # stages rather than running them and asking afterwards.
                jlog.warn(SYSTEM, f"session stopped early — skipping {ten[s]}")
                break
            try:
                ra = CHAY[s](conn)
                xong.append(s)
                jlog.ok(SYSTEM, f"session · {ten[s]} done{' — ' + ra if ra else ''}")
            except Exception as exc:            # noqa: BLE001
                hong.append(s)
                jlog.error(SYSTEM, f"session · {ten[s]} failed — "
                                   f"{type(exc).__name__}: {str(exc)[:70]}")
        # SAY WHAT ACTUALLY HAPPENED. "done — 0/3" reads like an ordinary
        # loop that found nothing; being cut short by the user is something
        # else entirely.
        if not xong and not hong:
            jlog.warn(SYSTEM, "session ran NO stages — it was stopped")
        else:
            jlog.ok(SYSTEM, f"session done — {len(xong)}/{len(khuc)} stages ran")
        # NOTIFY THE PHONE — one call site, right after the loop finishes.
        # Scattering the calls into each stage means a new kind of
        # notification has to be remembered in three places.
        from .bao import sau_phien
        sau_phien(conn, {"xong": xong, "hong": hong})
    finally:
        if tu_mo:
            conn.close()
    return {"xong": xong, "hong": hong, "tat": False}
