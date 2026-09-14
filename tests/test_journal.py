"""Test the runtime journal — what a 24/7 app lives and dies by.

    python3 tests/test_journal.py
"""

import os, sqlite3, sys, tempfile, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}{' — ' + extra if extra else ''}")


with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    from jobbot.core import db, postings
    from jobbot.core.journal import (ERROR, SEARCH, SCORE, SYSTEM,
                                     Journal, RING)

    db.connect().close()                      # create the audit table

    print("[events: appended, never edited]")
    j = Journal()
    j.emit(SEARCH, "scan started")
    j.warn(SEARCH, "linkedin blocked")
    j.ok(SCORE, "scored 208 postings")
    check("it keeps every line", len(j.tail(limit=99)) == 3)
    check("newest first", j.tail(limit=99)[0].text == "scored 208 postings")
    check("the level is recorded correctly",
          [e.level for e in j.tail(SEARCH, 9)] == ["warn", "info"])

    print("\n[streams: each tab sees only its own work]")
    check("filtered to the search stream", len(j.tail(SEARCH, 99)) == 2)
    check("filtered to the score stream", len(j.tail(SCORE, 99)) == 1)
    check("an unused stream is empty", j.tail(SYSTEM, 99) == [])
    check("unfiltered shows everything", len(j.tail(None, 99)) == 3)

    print("\n[progress: overwritten, NEVER written to disk]")
    j.progress(SEARCH, "deep-reading LinkedIn", 47, 192)
    j.progress(SEARCH, "deep-reading LinkedIn", 48, 192)
    check("only the latest value is kept", j.running()[SEARCH]["done"] == 48)
    check("the percentage is computed", j.running()[SEARCH]["percent"] == 25)
    check("progress does NOT leak into the event journal", len(j.tail(limit=99)) == 3)
    check("running means busy", j.busy())
    j.done(SEARCH)
    check("finished clears the progress bar", SEARCH not in j.running())
    check("and it is no longer busy", not j.busy())
    j.progress(SCORE, "scoring", 5, 0)
    check("with no total the percentage is 0", j.running()[SCORE]["percent"] == 0)
    j.done(SCORE)

    print("\n[pushed to the interface]")
    chan = j.subscribe()
    j.emit(SEARCH, "a new posting")
    j.progress(SEARCH, "running", 1, 10)
    got = [chan.get_nowait(), chan.get_nowait()]
    check("the event is pushed", got[0]["type"] == "event" and got[0]["text"] == "a new posting")
    check("progress is pushed too", got[1]["type"] == "progress")
    check("with the stream, so the interface can filter", got[1]["stream"] == SEARCH)
    j.unsubscribe(chan)
    j.emit(SEARCH, "after leaving")
    check("once gone it receives nothing more", chan.empty())

    print("\n[a slow reader must NOT stall the work in progress]")
    # A scan loop stopping because it is waiting on a full queue is a real
    # failure; the interface losing a few lines is trivial.
    slow = j.subscribe()
    for n in range(400):                       # more than maxsize=200
        j.progress(SEARCH, "overflowing", n, 400)
    check("a full queue drops messages, it does not hang", slow.qsize() <= 200)
    check("and the work still runs to the end", j.running()[SEARCH]["done"] == 399)
    j.unsubscribe(slow)
    j.done(SEARCH)

    print("\n[memory has a ceiling — running 24/7 must not bloat]")
    k = Journal()
    for n in range(RING + 250):
        k.emit(SYSTEM, f"line {n}", persist=False)
    check(f"at most {RING} lines kept", len(k.tail(limit=99999)) == RING)
    check("it keeps the NEW lines and drops the old",
          k.tail(limit=1)[0].text == f"line {RING + 249}")

    print("\n[what survives the app closing]")
    m = Journal()
    m.open()                                # attach to the temp DB
    m.emit(SCORE, "before shutdown")
    m.error(SCORE, "an error worth remembering")
    after = Journal()                          # "the app reopened"
    after.open()
    texts = [e.text for e in after.tail(SCORE, 99)]
    check("events are reloaded from disk", "before shutdown" in texts)
    check("and the level is preserved", after.tail(SCORE, 1)[0].level == ERROR)
    check("attaching a second time does not duplicate", after.open() == 0)

    # Lines from a previous life were written with postings.log(), which has
    # only `kind` and an empty detail — loaded straight, the journal fills
    # with blank lines carrying nothing but a time.
    conn = db.connect()
    conn.execute("INSERT INTO audit (at, kind, detail) VALUES (?,?,?)",
                 ("2026-01-01T00:00:00+00:00", "scan_started", ""))
    conn.commit(); conn.close()
    legacy = Journal(); legacy.open()
    old_line = [e for e in legacy.tail(limit=999) if e.at.startswith("2026-01-01")]
    check("an old line with no detail falls back to kind", bool(old_line))
    check("and it reads as text", old_line and old_line[0].text == "scan started")

    print("\n[not attached to a DB means NOT touching the disk]")
    # This is why 24 lines from the test suite reached the real journal: the
    # journal wrote straight to db_path() by default, whatever temp DB the
    # test was using.
    quiet = Journal()
    quiet.emit(SEARCH, "in memory only")
    check("without open() it opens no connection", quiet._db() is None)
    check("but it still records in memory", len(quiet.tail(SEARCH, 9)) == 1)

    print("\n[how much longer]")
    from jobbot.core.journal import remain_text
    check("under 90 seconds it says seconds", remain_text(45) == "~45s")
    check("over 90 seconds it switches to minutes", remain_text(600) == "~10 min")
    check("over an hour it says hours + minutes", remain_text(11520) == "~3h 12min")
    check("on the hour it does not write '0 min'", remain_text(7200) == "~2h")
    check("not knowing, it stays silent rather than guessing", remain_text(0) == "")

    eta = Journal()
    eta.progress(SEARCH, "deep-read · posting A", 1, 100)
    check("one tick is NOT enough to estimate", eta.running()[SEARCH]["eta"] == 0)
    eta.progress(SEARCH, "deep-read · posting B", 2, 100)
    check("two ticks still not", eta.running()[SEARCH]["eta"] == 0)
    time.sleep(0.05)
    eta.progress(SEARCH, "deep-read · posting C", 3, 100)
    check("three ticks and it speaks", eta.running()[SEARCH]["eta"] > 0)
    check("and it says it in words too", eta.running()[SEARCH]["eta_text"] != "")
    check("the same figure as the progress bar",
          eta.remaining(SEARCH) == eta.running()[SEARCH]["eta_text"])

    # This is the real trap: the LinkedIn search writes the job title being
    # searched into `what`, so EVERY TICK CARRIES DIFFERENT TEXT. If the clock
    # reset on the text, it would reset constantly and never estimate
    # anything.
    moc = eta.running()[SEARCH]["started"]
    eta.progress(SEARCH, "deep-read · posting D — completely different text", 4, 100)
    check("changing THE TEXT keeps the clock running",
          eta.running()[SEARCH]["started"] == moc)
    eta.progress(SEARCH, "on to another job", 1, 7)
    check("changing THE JOB (a different total) resets the clock",
          eta.running()[SEARCH]["started"] != moc)
    check("and it goes quiet again until it has enough ticks", eta.running()[SEARCH]["eta"] == 0)

    print("\n[the journal has to FOLLOW the newest line]")
    # A two-ended contract: the server sends OLDEST FIRST, the browser inserts
    # each line AT THE TOP — so once loaded the newest is on top, the same way
    # round as the lines that follow. Reverse either end and the list is
    # upside down with nobody noticing at once, because on a freshly opened
    # app any journal looks plausible.
    xep = Journal()
    for n in range(4):
        xep.emit(SEARCH, f"line {n}")
    trong_bo_nho = [e.text for e in xep.tail(SEARCH, 10)]
    check("tail() returns NEWEST first", trong_bo_nho[0] == "line 3", str(trong_bo_nho))
    gui_di = trong_bo_nho[::-1]            # exactly what server.py does for 'hello'
    check("the packet sent to the browser is OLDEST first", gui_di[0] == "line 0")
    tren_man = []
    for e in gui_di:                       # live.js: each line inserted at the top
        tren_man.insert(0, e)
    check("inserting at the top leaves the newest on top",
          tren_man[0] == "line 3", str(tren_man))

    # THE REAL BUG: inserting ABOVE what is being read leaves scrollTop
    # unchanged, so every new line pushes the view one notch further down —
    # the longer it runs the further it drifts from the newest. Measured on
    # the real machine: an 877px journal inside a 60px frame, an apply run in
    # progress while the screen sat on old lines.
    js = (Path(__file__).resolve().parent.parent
          / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    than = js.split("function addLine")[1].split("\n  const journal")[0]
    check("inserting a line handles scrolling", "scrollTop" in than, "")
    check("following the top -> pulled back to the newest", "sc.scrollTop = 0" in than)
    check("reading an old line -> the place is kept, with no jump",
          "sc.scrollTop += row.offsetHeight" in than)
    # The scrollbar is NOT on .journal but on the .jfeed around it. Set
    # scrollTop on the wrong element and nothing happens, with no error
    # either.
    check("it finds the real scroll frame rather than guessing", "function scroller" in js)

    print("\n[a scan: EVERY source has to leave a trace]")
    # The 19:22 scan ran 21 boards and left exactly 3 journal lines, because
    # the old rule was "only log when something new came in". The user had no
    # way to know whether the other 18 boards had finished or had died.
    # Silence is not tidiness — silence is blindness.
    from jobbot.core.journal import log as chung
    from jobbot import scan_runner as _sr
    _c = db.connect()
    _truoc = len(chung.tail(SEARCH, 999))
    _sr._run_source(_c, "greenhouse:rong", lambda: [], log=lambda _m: None)
    _sau = chung.tail(SEARCH, 999)
    check("a source with NO new postings still writes a line", len(_sau) == _truoc + 1)
    check("and that line says 0 new outright", "0 new" in _sau[0].text, _sau[0].text)
    check("level 'info', not 'ok' — there is nothing to celebrate",
          _sau[0].level == "info")
    _c.close()

    print("\n[one bad source must NOT kill the whole scan]")
    # The old version wrapped only the fetch. A source returning properly
    # while save_batch() blew up (the DB locked, a posting missing a field)
    # sent the exception out to the calling loop and every later source did
    # NOT run — and it did not even record that it had broken.
    _c2 = db.connect()
    _that_save = postings.save_batch
    _lan = []
    def _no(*_a, **_k):
        _lan.append(1)
        raise sqlite3.OperationalError("database is locked")
    postings.save_batch = _no
    try:
        _kq = _sr._run_source(_c2, "greenhouse:khoa", lambda: [1, 2, 3],
                              log=lambda _m: None)
        check("save_batch blows up -> NOTHING is raised out", True)
        check("and it returns (0, 0) so the scan carries on", _kq == (0, 0), str(_kq))
    except Exception as exc:                   # noqa: BLE001
        check("save_batch blows up -> NOTHING is raised out", False,
              f"{type(exc).__name__}: {exc}")
    finally:
        postings.save_batch = _that_save
    check("it really did reach the DB-writing stage", _lan == [1])
    _dong = _c2.execute("SELECT ok, error FROM source_run"
                        " WHERE source='greenhouse:khoa'").fetchone()
    check("a FAILED run is still recorded, never silent", _dong is not None)
    if _dong:
        check("marked ok=0", _dong[0] == 0)
        # The error sentence has to name THE RIGHT stage: a generic "failed"
        # sends the reader off checking the network while the fault is on
        # disk.
        check("and it says the DB-writing stage failed, not the fetch",
              "writing to the DB" in (_dong[1] or ""), str(_dong[1]))
    _hong = chung.tail(SEARCH, 999)
    check("the journal carries a red line too", any("greenhouse:khoa" in r.text and
                                         r.level == "error" for r in _hong))

    # THE ERROR-RECORDING PATH also has to survive a dead DB — record_run()
    # writes into the very DB that just made save_batch() blow up.
    postings.save_batch = _no
    _that_rec = postings.record_run
    postings.record_run = _no
    try:
        _kq2 = _sr._run_source(_c2, "greenhouse:chet", lambda: [1],
                               log=lambda _m: None)
        check("the error path failing too is still not raised out", _kq2 == (0, 0))
    except Exception as exc:                   # noqa: BLE001
        check("the error path failing too is still not raised out", False,
              f"{type(exc).__name__}: {exc}")
    finally:
        postings.save_batch, postings.record_run = _that_save, _that_rec
    _c2.close()

    print("\n[a broken journal must NOT kill the work in progress]")
    broken = Journal()
    broken.open()
    broken._conn = "not a connection"          # force every disk operation to blow up
    try:
        broken.emit(SEARCH, "it still has to run")
        check("a broken disk write still emits", True)
    except Exception as exc:                   # noqa: BLE001
        check("a broken disk write still emits", False, f"{type(exc).__name__}: {exc}")
    check("and that line is still in memory", len(broken.tail(SEARCH, 9)) == 1)

    os.environ.pop("JOBBOT_DATA_DIR", None)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
