"""The run journal — the single most important thing in a 24/7 app.

The machine runs all the time; the person does not sit and watch. So the
first question on opening the app is always "what did it JUST do, and what is
it doing NOW". Without an answer to that, every other number on the screen is
dead weight.

Two DIFFERENT things, do not mix them:

    EVENTS    appended, never edited. "linkedin blocked at posting 47".
              Survives a restart -> written to SQLite.

    PROGRESS  overwritten, only meaningful right now. "deep-read 47/192".
              Meaningless once the app closes -> memory ONLY, never disk.
              Writing 192 progress lines to disk per scan is self-harm.

Every event belongs to a STREAM. That is what lets the Search tab show only
Search's work, not Score's — while Home still merges everything.
"""

from __future__ import annotations

import queue
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .paths import db_path

# A stream = a subsystem with real running time. Add a stream here, never as
# a free string at the call site — one typo and it vanishes from the UI.
SYSTEM = "system"
SEARCH = "search"
SCORE = "score"
# The CV tab has real running time now that it has its own Run button:
# building versions for 364 postings takes 5 seconds, and the user has to be
# able to read what it is doing.
CV = "cv"
STREAMS = (SYSTEM, SEARCH, SCORE, CV)

INFO, OK, WARN, ERROR = "info", "ok", "warn", "error"

RING = 400              # lines held in memory to draw instantly without the disk
LOAD_ON_START = 120     # old lines reloaded at boot so the journal is not empty


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Event:
    at: str
    stream: str
    level: str
    text: str

    def as_dict(self) -> dict:
        return asdict(self)


def remain_text(seconds: int) -> str:
    """Seconds -> a sentence a person can read. ONE formatter for the app.

    Journal lines are written in Python, the progress bar is drawn in
    JavaScript. Let each side format for itself and the same number appears
    in two different wordings on the same screen — so this turns it into text
    here and ships the text down.

    Always carries ~: this is an estimate at the current pace, not a promise.
    """
    if seconds <= 0:
        return ""
    if seconds < 90:
        return f"~{seconds}s"
    phut = round(seconds / 60)
    if phut < 60:
        return f"~{phut} min"
    gio, le = divmod(phut, 60)
    return f"~{gio}h {le}min" if le else f"~{gio}h"


@dataclass
class Progress:
    """What it is doing, how far along, how long until it finishes."""
    what: str
    done: int = 0
    total: int = 0
    started: float = 0.0

    @property
    def percent(self) -> int:
        return int(self.done * 100 / self.total) if self.total else 0

    @property
    def eta(self) -> int:
        """SECONDS left. 0 when it cannot be estimated yet.

        Measured from the REAL pace of the loop in flight, never a guessed
        constant: the LinkedIn deep-read pass speeds up and slows down with
        the network, with cool-downs, and with how many postings were
        already read — a hardcoded number is wrong by the next day.

        It waits for 3 ticks before saying anything. The first tick still
        carries the cost of launching Chrome and opening a page; divide by
        that and the first minute announces "9 hours left" then falls away,
        and a number that jumps around is worse than no number at all.
        """
        if not self.total or self.done < 3 or not self.started:
            return 0
        troi = _monotonic() - self.started
        return max(0, int(troi / self.done * (self.total - self.done)))

    def as_dict(self) -> dict:
        out = asdict(self)
        out["percent"] = self.percent
        out["eta"] = self.eta
        out["eta_text"] = remain_text(self.eta)
        return out


class Journal:
    """One instance per process. Several threads write to it, hence the lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ring: list[Event] = []
        self._progress: dict[str, Progress] = {}
        self._subs: list[queue.Queue] = []
        self._conn: sqlite3.Connection | None = None
        self._path = None          # None = not attached to a file -> memory only
        self._loaded = False

    # --- persistence ------------------------------------------------------
    def _db(self) -> sqlite3.Connection | None:
        """The journal's own connection, opened once and kept.

        Before open() it returns None -> memory only, no file touched.

        check_same_thread=False because a background thread writes while the
        web thread reads. Safe because every entry point goes through
        self._lock.
        """
        if self._path is None:
            return None
        if self._conn is None:
            try:
                self._conn = sqlite3.connect(self._path, check_same_thread=False)
                self._conn.execute("PRAGMA busy_timeout = 3000")
            except Exception:                   # noqa: BLE001
                return None
        return self._conn

    def _persist(self, event: Event) -> None:
        conn = self._db()
        if conn is None:
            return
        try:
            conn.execute(
                "INSERT INTO audit (at, kind, detail, stream, level) VALUES (?,?,?,?,?)",
                (event.at, event.text[:60], event.text, event.stream, event.level))
            conn.commit()
        except Exception:       # noqa: BLE001
            # Catching BROADLY is deliberate. Losing one journal line is a
            # small thing; the journal raising and killing a scan half-way
            # through is the real failure. sqlite3.Error alone is not enough:
            # a full disk, a dead connection, and a DB locked too long all
            # raise something else.
            pass

    def open(self, path=None) -> int:
        """Attach the journal to a DB file and reload history. Called once
        at boot.

        Until it is called the journal lives in memory only. That is
        deliberate: if the default were to write straight to db_path(), every
        test that calls derive() would pour its lines into the user's REAL
        journal — which happened, 24 lines of "keeping 1 posting". Making
        each test file remember to set an environment variable is waiting for
        the next failure; a silent default means nobody has to remember.
        """
        with self._lock:
            if self._loaded:
                return 0
            self._loaded = True
            self._path = str(path or db_path())
            conn = self._db()
            if conn is None:
                return 0
            try:
                rows = conn.execute(
                    "SELECT at, stream, level, detail, kind FROM audit"
                    " ORDER BY id DESC LIMIT ?", (LOAD_ON_START,)).fetchall()
            except Exception:                   # noqa: BLE001
                return 0
            # Empty detail falls back to kind: lines written by the older
            # postings.log() only have a kind ('scan_started'), and would
            # render as a completely blank row.
            self._ring = [Event(at=r[0], stream=r[1] or SYSTEM,
                                level=r[2] or INFO,
                                text=r[3] or (r[4] or "").replace("_", " "))
                          for r in reversed(rows)]
            return len(self._ring)

    # --- writing -----------------------------------------------------------
    def emit(self, stream: str, text: str, level: str = INFO,
             persist: bool = True) -> Event:
        event = Event(at=_now(), stream=stream, level=level, text=text)
        with self._lock:
            self._ring.append(event)
            if len(self._ring) > RING:
                del self._ring[:-RING]
            subs = list(self._subs)
        if persist:
            self._persist(event)
        self._push(subs, {"type": "event", **event.as_dict()})
        return event

    def ok(self, stream: str, text: str) -> Event:
        return self.emit(stream, text, OK)

    def warn(self, stream: str, text: str) -> Event:
        return self.emit(stream, text, WARN)

    def error(self, stream: str, text: str) -> Event:
        return self.emit(stream, text, ERROR)

    def progress(self, stream: str, what: str, done: int = 0, total: int = 0) -> None:
        """How far along. NEVER written to disk — call it as often as you like."""
        with self._lock:
            found = self._progress.get(stream)
            # The clock restarts on a DIFFERENT JOB — recognised by the
            # TOTAL changing or the counter going backwards, NOT by the text
            # changing. The LinkedIn search writes the job title it is
            # querying into `what`, so every tick is a different string;
            # keying on the text resets the clock each tick and "how long
            # left" can never be computed.
            if found is None or found.total != total or done < found.done:
                found = Progress(what=what, started=_monotonic())
                self._progress[stream] = found
            found.what, found.done, found.total = what, done, total
            payload = {"type": "progress", "stream": stream, **found.as_dict()}
            subs = list(self._subs)
        self._push(subs, payload)

    def done(self, stream: str) -> None:
        """Finished — clear the bar so the UI does not freeze at 47/192."""
        with self._lock:
            self._progress.pop(stream, None)
            subs = list(self._subs)
        self._push(subs, {"type": "progress", "stream": stream, "what": ""})

    # --- reading -----------------------------------------------------------
    def tail(self, stream: str | None = None, limit: int = 60) -> list[Event]:
        with self._lock:
            rows = [e for e in self._ring if stream is None or e.stream == stream]
        return rows[-limit:][::-1]          # newest first

    def running(self) -> dict[str, dict]:
        with self._lock:
            return {k: v.as_dict() for k, v in self._progress.items()}

    def remaining(self, stream: str) -> str:
        """How long is left, already as text. Empty when it cannot be told.

        So a JOURNAL line quotes the same number as the PROGRESS BAR. Two
        places computing it are two numbers, and one day they disagree on the
        same screen.
        """
        with self._lock:
            found = self._progress.get(stream)
        return remain_text(found.eta) if found else ""

    def busy(self) -> bool:
        with self._lock:
            return bool(self._progress)

    # --- pushing to the UI -------------------------------------------------
    def subscribe(self) -> queue.Queue:
        chan: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._subs.append(chan)
        return chan

    def unsubscribe(self, chan: queue.Queue) -> None:
        with self._lock:
            if chan in self._subs:
                self._subs.remove(chan)

    @staticmethod
    def _push(subs: list[queue.Queue], payload: dict) -> None:
        """A slow viewer DROPS messages; it must never block the work.

        The UI missing a tick is a small thing; the scan stalling because it
        is waiting on a full queue is the real failure.
        """
        for chan in subs:
            try:
                chan.put_nowait(payload)
            except queue.Full:
                pass


def _monotonic() -> float:
    import time
    return time.monotonic()


# One shared instance for the whole process.
log = Journal()
