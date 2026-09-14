"""Test the background loop — above all that OPENING THE APP MUST NOT START A
RUN.

The real bug: last_scan was initialised to 0.0, so the condition

    time.time() - self.last_scan >= self.scan_every

was true from the very first tick -> opening the app meant Chrome starting 5
seconds later and LinkedIn being scanned, while the user had not yet reached
Settings. With the configuration unfinished, whatever is scanned is junk.

    python3 tests/test_scheduler.py
"""

import os, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}{' — ' + extra if extra else ''}")


with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    from jobbot.core import db, prefs
    from jobbot.core.scheduler import SCAN_EVERY_MIN, Scheduler

    db.connect().close()

    print("[opening the app for the first time: it must NOT run by itself]")
    s = Scheduler()
    scans = []
    s.scan_once = lambda: scans.append(time.time())    # count, do not really scan
    s.start(); time.sleep(0.3)
    check("paused by default", s.paused)
    check("state says paused outright", s.state() == "paused")
    check("it scanned NOT ONCE", scans == [], f"scanned {len(scans)} times")
    s.stop()

    print("\n[turned on it remembers, turned off it remembers too]")
    s.resume()
    conn = db.connect()
    check("on -> written to prefs", prefs.flag(conn, prefs.AUTORUN))
    conn.close()
    s.pause()
    conn = db.connect()
    check("off -> also written to prefs", not prefs.flag(conn, prefs.AUTORUN))
    conn.close()

    print("\n[reopening with it on: it runs on schedule, NOT immediately]")
    conn = db.connect(); prefs.set_flag(conn, prefs.AUTORUN, True); conn.close()
    s2 = Scheduler()
    scans2 = []
    s2.scan_once = lambda: scans2.append(time.time())
    s2.start(); time.sleep(0.3)
    check("the choice is read back -> no longer paused", not s2.paused)
    # This is the most important check here: auto-scan ON still does NOT mean
    # scanning the moment the app opens. The clock has to start at open time,
    # not at 0.
    check("it still does NOT scan the moment the app opens", scans2 == [],
          f"scanned {len(scans2)} times")
    check("the first scan is pushed back nearly a full cycle",
          SCAN_EVERY_MIN - 1 <= s2.next_in() // 60 <= SCAN_EVERY_MIN,
          f"{s2.next_in() // 60} min to go")
    s2.stop()

    print("\n[pressing Run still runs, even with auto-scan off]")
    s3 = Scheduler()
    ran = []
    s3.scan_once = lambda: ran.append(1)
    s3.start(); time.sleep(0.1)
    s3.pause()
    s3.scan_once()                                  # the user pressed it
    check("the manual button is not blocked by 'auto-scan off'", ran == [1])
    s3.stop()

    print("\n[an overnight window]")
    from datetime import datetime as _dt
    from jobbot.core import prefs as _prefs
    from jobbot.core.db import connect as _connect
    from jobbot.core.scheduler import in_human_window as _win
    _c = _connect()
    # 22:00–08:00 is a VALID window (scanning overnight). The formula `low <=
    # h < high` yields EMPTY — the scan loop silently runs at no hour at all,
    # with no warning.
    _prefs.put(_c, _prefs.HOURS_FROM, "22"); _prefs.put(_c, _prefs.HOURS_TO, "8")
    _night = [h for h in range(24) if _win(_dt(2026, 9, 10, h, 0))]
    check("an overnight window scans", len(_night) == 10, str(len(_night)))
    check("and at the right night hours", 23 in _night and 2 in _night and 12 not in _night)
    _prefs.put(_c, _prefs.HOURS_FROM, "8"); _prefs.put(_c, _prefs.HOURS_TO, "22")
    check("an ordinary window still works",
          len([h for h in range(24) if _win(_dt(2026, 9, 10, h, 0))]) == 14)
    # HOURS_TO is clamped to [1,24] so "0/0" gives 0–1; 5/5 is needed to reach
    # the both-ends-equal branch.
    _prefs.put(_c, _prefs.HOURS_FROM, "5"); _prefs.put(_c, _prefs.HOURS_TO, "5")
    check("both ends equal = all day",
          len([h for h in range(24) if _win(_dt(2026, 9, 10, h, 0))]) == 24)
    _c.close()

    print("\n[two scan rounds never overlap]")
    s4 = Scheduler()
    # "A scan in progress" is simulated with THE LOCK ITSELF, not a separate
    # flag: the truth lives in the lock. The old version used `if
    # self.running: ... running = True` — two steps — so pressing RUN exactly
    # as the schedule fired let both threads in.
    s4._gate.acquire()
    try:
        out = Scheduler.scan_once(s4)
        check("a scan in progress makes a new request a no-op", out == s4.last_result)
        check("and it still reports as running", s4.running is True)
    finally:
        s4._gate.release()
    check("releasing the lock ends the busy state", s4.running is False)

    # A real race: two threads entering at once, only ONE allowed to run.
    import threading as _th
    s5 = Scheduler()
    entered = []
    def _slow():
        entered.append(1)
        time.sleep(0.25)
    s5._real = _slow
    orig = Scheduler.scan_once
    def _wrapped(self):
        return orig(self)
    import jobbot.scan_runner as _sr
    _sr.run_scan = lambda: (_slow(), {"summary": "x", "kept": 0, "new": 0})[1]
    threads = [_th.Thread(target=lambda: _wrapped(s5)) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    check("two threads at once -> only one scan runs", len(entered) == 1,
          str(len(entered)))

    os.environ.pop("JOBBOT_DATA_DIR", None)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
