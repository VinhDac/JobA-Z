"""The background loop — what makes this an APP rather than a web page you
have to press yourself.

The cadence (design.md §3):
  - Sources with a public API: 24/7, there is no reason to hold back.
  - Sources through Chrome: only inside the human window. Nobody browses at
    3am every night — it is that rhythm that gives you away, not click speed.

Every run writes an audit row. One broken source must never kill the run.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

from . import notify, postings
from . import prefs
from .journal import SEARCH, SYSTEM, log as jlog
from .db import connect

# Defaults. The user changes these in Settings; these two constants are only
# the starting values while the pref table is still empty.
SCAN_EVERY_MIN = 60
HUMAN_WINDOW = (8, 22)          # local hours, for sources that go through Chrome

MIN_EVERY, MAX_EVERY = 5, 1440  # 5 minutes to 24 hours


def _pref(key: str, low: int, high: int) -> int:
    """Read AT CALL TIME, not at import time.

    Importing by value freezes the number: changing 60 -> 15 minutes would
    need an app restart to take effect. A failed read returns the default —
    whatever the user types into a box must not kill the background loop.
    """
    try:
        conn = connect()
        try:
            return prefs.num(conn, key, low, high)
        finally:
            conn.close()
    except Exception:                       # noqa: BLE001
        return int(prefs.DEFAULTS.get(key, low))


def scan_every_min() -> int:
    return _pref(prefs.SCAN_EVERY, MIN_EVERY, MAX_EVERY)


def human_window() -> tuple[int, int]:
    return (_pref(prefs.HOURS_FROM, 0, 23), _pref(prefs.HOURS_TO, 1, 24))


def in_human_window(now: datetime | None = None) -> bool:
    """Is this hour inside the window where scanning is allowed.

    A window that CROSSES MIDNIGHT is a legitimate window: 22:00-08:00 means
    scan at night, exactly when the machine is free. The old formula
    `low <= hour < high` yields EMPTY for such a window — the scan silently
    never ran at any hour, with no warning anywhere.

    low == high means ALL DAY: someone setting both ends equal meant "any
    time", not "never".
    """
    hour = (now or datetime.now()).hour
    low, high = human_window()
    if low == high:
        return True
    if low < high:
        return low <= hour < high
    return hour >= low or hour < high


class Scheduler:
    """Runs on a background thread. Never raises out — the app must live on."""

    def __init__(self, scan_every_min: int = SCAN_EVERY_MIN):
        self.scan_every = scan_every_min * 60
        self.stop_flag = threading.Event()
        self.last_scan: float = 0.0
        self.last_result: str = "never run"
        # `running` is NOT stored separately — it is whether the lock is
        # held. Keeping both a flag and a lock is two sources of truth, and
        # they will drift apart.
        self._gate = threading.Lock()
        # PAUSED by default. Opening the app and having it scan while the
        # user is still configuring is wrong — an unfinished configuration
        # only scrapes rubbish. The previous choice is reloaded; absent, off.
        self.paused = True
        self._thread: threading.Thread | None = None

    # --- control ----------------------------------------------------------
    def start(self) -> None:
        self.paused = not self._autorun()
        # The clock starts AT BOOT, not at 0. Left at 0, "now - 0 >= 3600"
        # is always true and the scan fires 5 seconds in — Chrome launching
        # while the window has not finished drawing.
        self.last_scan = time.time()
        jlog.emit(SYSTEM,
                  "app started — the station is OFF, press Start session on Overview"
                  if self.paused else
                  f"app started — the station is ON, first loop in {self.scan_every // 60} min")
        self._thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self._thread.start()

    @staticmethod
    def _autorun() -> bool:
        try:
            conn = connect()
            try:
                return prefs.flag(conn, prefs.AUTORUN)
            finally:
                conn.close()
        except Exception:                       # noqa: BLE001
            return False                        # unreadable -> do NOT auto-run

    def stop(self) -> None:
        self.stop_flag.set()

    def pause(self) -> None:
        """Stop auto-scanning, and REMEMBER that choice for the next boot.

        NOT stop(): the thread stays alive, press again and it runs.
        It does not interrupt a scan in flight — cutting mid-way leaves
        Chrome with a hung tab and derive()'s transaction half rolled back.
        """
        self.paused = True
        self._remember(False)
        jlog.warn(SYSTEM, "THE STATION IS OFF — no further loops will run on their own")

    def resume(self) -> None:
        self.paused = False
        self._remember(True)
        jlog.ok(SYSTEM, f"the station is ON — next loop in {self.next_in() // 60} min")

    @staticmethod
    def _remember(on: bool) -> None:
        """Remember the choice. Without it the next boot auto-runs again —
        exactly what was just switched off."""
        try:
            conn = connect()
            try:
                prefs.set_flag(conn, prefs.AUTORUN, on)
            finally:
                conn.close()
        except Exception:                       # noqa: BLE001
            pass

    def state(self) -> str:
        """One word for the UI: running / paused / idle."""
        if self.running:
            return "running"
        return "paused" if self.paused else "idle"

    def next_in(self) -> int:
        """Seconds until the next scan."""
        if not self.last_scan:
            return 0
        return max(0, int(self.scan_every - (time.time() - self.last_scan)))

    # --- the loop ---------------------------------------------------------
    def _loop(self) -> None:
        time.sleep(5)                       # let the server come up first
        while not self.stop_flag.is_set():
            # Re-read the cadence EVERY loop, not at construction: changing
            # 60 -> 15 minutes in Settings takes effect at once, with no
            # restart.
            self.scan_every = scan_every_min() * 60
            if not self.paused and time.time() - self.last_scan >= self.scan_every:
                self.phien_once()
            self.stop_flag.wait(30)

    @property
    def running(self) -> bool:
        """Scan in flight? Derived from the lock, not stored separately."""
        return self._gate.locked()

    def scan_once(self) -> str:
        """One scan. Swallows every error — a dead source must not kill the app."""
        # A lock, NOT check-then-set. `if self.running: ... self.running =
        # True` is two steps: press RUN at the moment the scheduler also
        # fires and both threads see False and both set True — two scans
        # writing one DB and both launching Chrome.
        if not self._gate.acquire(blocking=False):
            jlog.warn(SYSTEM, "a scan is already in flight — ignoring the overlapping request")
            return self.last_result
        self.last_scan = time.time()
        try:
            from ..scan_runner import run_scan          # late import, avoids a cycle
            result = run_scan()
            self.last_result = result["summary"]
            self._maybe_notify(result)
        except Exception as exc:                        # noqa: BLE001
            self.last_result = f"error: {type(exc).__name__}: {exc}"
            jlog.error(SYSTEM, f"scan failed: {type(exc).__name__} — {str(exc)[:70]}")
            try:
                conn = connect()
                postings.log(conn, "scan_error", str(exc)[:300])
                conn.close()
            except Exception:                           # noqa: BLE001
                pass
        finally:
            self._gate.release()
            jlog.done(SEARCH)
            jlog.done(SYSTEM)
        return self.last_result

    def phien_once(self) -> str:
        """ONE SESSION: run each enabled stage in turn (see jobbot/phien.py).

        Different from `scan_once` in that it runs the WHOLE pipeline, not
        just the search pass. The 24/7 loop calls this, and so does the
        «Start session» button on Home — two entry points, ONE job. Two
        definitions of "one loop" means that one day pressing the button and
        letting it run do different things.

        SHARES THE LOCK with scan_once: two overlapping sessions would have
        two places writing one SQLite file and both launching Chrome.
        """
        if not self._gate.acquire(blocking=False):
            jlog.warn(SYSTEM, "already running — ignoring the overlapping request")
            return self.last_result
        self.last_scan = time.time()
        try:
            from ..phien import chay
            ra = chay()
            self.last_result = ("all three stages are off" if ra.get("tat") else
                                f"{len(ra['xong'])} stage(s) done"
                                + (f", {len(ra['hong'])} failed" if ra["hong"] else ""))
        except Exception as exc:                        # noqa: BLE001
            self.last_result = f"error: {type(exc).__name__}: {exc}"
            jlog.error(SYSTEM, f"session failed: {type(exc).__name__} — {str(exc)[:70]}")
        finally:
            self._gate.release()
            jlog.done(SEARCH)
            jlog.done(SYSTEM)
        return self.last_result

    @staticmethod
    def _maybe_notify(result: dict) -> None:
        """Only notify when there is NEW work worth seeing. Not every scan.

        Swallowing the return value is why the AppleScript quoting bug
        survived the whole project: every notification failed and nobody
        knew. On failure, WRITE IT TO THE JOURNAL so it shows up on Settings.
        """
        fresh = result.get("new_matches", 0)
        if fresh <= 0:
            return
        sent = notify.send("jobbot",
                           f"{fresh} new jobs matching your profile",
                           subtitle="Open the dashboard to see them")
        try:
            conn = connect()
            postings.log(conn, "notify" if sent else "notify_failed",
                         f"{fresh} new jobs" if sent
                         else f"{fresh} new jobs — the notification did NOT appear")
            conn.close()
        except Exception:                               # noqa: BLE001
            pass


# One shared instance: app.py builds the loop, server.py needs it for the
# RUN/PAUSE buttons. Threading it through arguments would mean serve() ->
# Handler -> every route, and Handler is constructed by http.server, which
# takes no arguments of ours.
_current: Scheduler | None = None


def current() -> Scheduler:
    global _current
    if _current is None:
        _current = Scheduler()
    return _current
