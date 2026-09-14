"""One scan — shared by the command line and the background loop.

This logic used to live in scripts/scan.py. It was pulled out so the
scheduler can call it without spawning a subprocess.
"""

from __future__ import annotations

import tomllib
from typing import Callable

from .core import db, halt, postings
from .core.journal import INFO, OK, SEARCH, log as jlog
from .core.paths import PROJECT_ROOT

STAGE = "search"      # the stage name, shared with the stop flag and the deck button
from .ingest import ashby, greenhouse, lever
from .ingest import filter as jobfilter
from .profile import store
from .profile.schema import all_questions

Log = Callable[[str], None]


def seed_boards() -> dict[str, list[str]]:
    """Boards Vin picked himself, typed into config/boards.toml."""
    path = PROJECT_ROOT / "config" / "boards.toml"
    raw = tomllib.loads(path.read_text()) if path.exists() else {}
    return {k: v.get("boards", []) for k, v in raw.items()}


def load_boards(conn) -> dict[str, list[str]]:
    """MERGE the two board sources: hand-picked + machine-learned.

    A BUG THAT WAS FIXED: the file used to be a FALLBACK for when the company
    table was empty. The table holds 53 rows, so the file was never read —
    5 hand-typed boards (aqr, cohere, palantir, ramp, synthesia) had never
    been scanned once. Editing boards.toml did nothing, and said nothing.

    The hand-picked list must ALWAYS be honoured: it is the only place Vin
    can say "I want to watch this company", even if it has never posted.
    """
    from .ingest.web import companies as co
    out = {k: list(v) for k, v in seed_boards().items()}
    for ats, slugs in co.boards(conn).items():
        out.setdefault(ats, [])
        out[ats] += [s for s in slugs if s not in out[ats]]
    return out


def _nguon_hong(conn, name: str, khuc: str, exc: Exception, log: Log) -> None:
    """Record a broken source — and THIS RECORDING PATH MUST NOT ITSELF FAIL.

    `record_run()` writes into the very DB that just made `save_batch()`
    raise. If it raises too, the exception escapes FROM INSIDE the except
    block and kills the whole scan — exactly what its caller exists to
    prevent. So both writes are wrapped.
    """
    cau = f"{type(exc).__name__}: {exc}"
    try:
        postings.record_run(conn, name, ok=False, error=f"{khuc}: {cau}"[:500])
    except Exception:                                 # noqa: BLE001,S110
        pass
    try:
        jlog.error(SEARCH, f"{name}: {khuc} failed — {cau[:60]}")
    except Exception:                                 # noqa: BLE001,S110
        pass
    log(f"  {name:26} FAILED  {khuc}: {cau[:50]}")


def _run_source(conn, name: str, fn, *args, log: Log) -> tuple[int, int]:
    """One broken source must NOT break the whole scan.

    BOTH PHASES are inside the try, and that is the point of this function.
    The old version only wrapped the fetch: a source that returned cleanly
    but whose `save_batch()` raised (DB locked, a posting missing a field, a
    UNIQUE constraint) sent the exception straight out to the caller and the
    40 sources after it did NOT run — with no `source_run` row recording that
    this source had failed either. One junk source killed the whole pass,
    silently.

    `khuc` exists so the error names the RIGHT place. "greenhouse failed"
    sends the reader to check the network; "greenhouse: writing to the DB
    failed" sends them to check the disk.
    """
    seen = new = 0
    khuc = "fetching"
    try:
        items = fn(*args)
        khuc = "writing to the DB"
        seen, new = postings.save_batch(conn, name, items)
        postings.record_run(conn, name, ok=True, fetched=seen, new_rows=new)
        khuc = "writing the journal"
        # LOG THE "nothing new" LINE TOO. The old rule was to log only when
        # something was new, for fear 62 boards an hour would turn the
        # journal into noise — but the measured cost, on the 19:22 scan: 21
        # boards ran and the journal held exactly 3 lines. The user had no
        # way to know whether the other 18 had finished or died half-way.
        # Silence is not tidiness. Silence is blindness.
        jlog.emit(SEARCH, f"{name}: {seen} fetched, {new} new",
                  level=OK if new else INFO)
        log(f"  {name:26} {seen:5} fetched, {new:5} new")
    except Exception as exc:                          # noqa: BLE001
        _nguon_hong(conn, name, khuc, exc, log)
    # Return what WAS actually achieved. A failure in the journal phase means
    # the postings are already in the DB, and reporting 0 would be a lie.
    return seen, new


# Three kinds of scan, three completely different jobs.
DAU, TIEP, MOI = "dau", "tiep", "moi"


def _cap(answers: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """(every title × place pair, the levels) — built EXACTLY as the search
    will build it.

    It has to go through the MAX_QUERIES ceiling too: if `scan_mode` counts
    27 titles while the search only queries 20, those other 7 pairs are
    "never scanned" forever and the button says "Run" forever.
    """
    from .ingest.web import linkedin as li
    titles = [t.strip() for t in (answers.get("job_titles") or "").splitlines()
              if t.strip()][:li.MAX_QUERIES]
    places = li.places_for(answers.get("markets") or [],
                           answers.get("location") or "")
    levels = sorted(answers.get("seniority") or ["grad", "junior"])
    return [(q, p) for q in titles for p in places], levels


def da_quet(conn) -> tuple[set[str], list[str]]:
    """The pairs fully scanned, and the levels at the time. Unreadable counts
    as never."""
    import json as _json
    from .core import prefs
    try:
        xong = set(_json.loads(prefs.get(conn, prefs.LI_DONE) or "[]"))
        muc = list(_json.loads(prefs.get(conn, prefs.LI_LEVELS) or "[]"))
    except (ValueError, TypeError):
        return set(), []
    return xong, muc


def con_thieu(conn, answers: dict) -> tuple[list[tuple[str, str]], int]:
    """Which pairs have NEVER been fully scanned, and the total count.

    This is the whole rule in one function: what has never been asked gets
    asked fully, what has been asked only gets asked for what is new. Drop a
    title -> fewer pairs -> nothing missing -> nothing rescanned. Add a title
    -> exactly the new pairs are missing, and only they get a full scan.
    """
    cap, muc = _cap(answers)
    xong, muc_cu = da_quet(conn)
    # WIDENING the levels changes f_E for every pair -> treat nothing as
    # covered. NARROWING does not: removing a level cannot produce a new
    # posting.
    if not set(muc) <= set(muc_cu):
        xong = set()
    return [c for c in cap if f"{c[0]}|{c[1]}" not in xong], len(cap)


def scan_mode(conn) -> dict:
    """What the NEXT scan will do. ONE place decides; the Run button only
    reads it back to name itself.

    IT ONLY TALKS ABOUT CHROME. The board APIs finish in 22 seconds and run
    every pass, with no state worth reporting; the thing that costs half an
    hour and can be left half-done is LinkedIn.

        Run       pairs never scanned       -> FULLY scan exactly those pairs
        Continue  work left half-done       -> search NOTHING, finish the rest
        Update    everything covered        -> only ask for recent postings

    NOTHING IS RUN TWICE. The unit is the PAIR (title × place), so dropping a
    title rescans nothing, and adding a title fully scans only the new pairs
    — the rest still only asks for what is new.

    A button that guesses one thing while the scan does another is a button
    that lies, and the user learns not to trust it.
    """
    from datetime import datetime, timezone
    from .core import prefs
    from .core.postings import HAVE_DESC
    from .ingest.web import linkedin as li
    from .profile import store

    one = lambda q, a=(): conn.execute(q, a).fetchone()[0]      # noqa: E731

    # 1. ANYTHING HALF-DONE? Checked first: half-done work is work already
    #    half paid for, and abandoning it to search again pays twice.
    #
    # Count EXACTLY the queue the deep-read pass will run, so only ENABLED
    # sources: counting disabled ones makes the button offer "finish reading
    # 107 postings" and then read 0.
    doc = nguon_doc(conn)
    do_dang = one("SELECT COUNT(*) FROM posting WHERE source IN"
                  f" ({','.join('?' * len(doc))})"
                  " AND length(COALESCE(description,'')) < ?"
                  " AND (kept = 1 OR user_keep = 1)",
                  (*doc, HAVE_DESC)) if doc else 0
    if do_dang:
        return {"mode": TIEP, "label": "Continue", "recent": 0, "todo": do_dang,
                "note": f"{do_dang:,} postings still unread — finish those,"
                        f" do not search again from the top"}

    # 2. LINKEDIN OFF -> THERE IS NO GRID TO COVER. The title × place grid
    #    belongs to the linkedin source alone; boards and alert mail run
    #    every pass and finish in seconds, with nothing "never scanned" to
    #    report. A button still reading "Run — 80 queries never scanned"
    #    while the search does not run is a lie, and the user learns not to
    #    trust that button.
    bat_li = prefs.flag(conn, prefs.SRC_LINKEDIN)
    if not bat_li:
        con = ", ".join(n for n in ("board", "alert")
                        if prefs.flag(conn, getattr(prefs, f"SRC_{n.upper()}")))
        return {"mode": MOI, "label": "Update", "recent": 0, "todo": 0,
                "note": ("LinkedIn is off — only asking for new postings from " + con)
                        if con else "every source is off — nothing can be scanned"}

    # 3. ARE THERE PAIRS NEVER ASKED?
    thieu, tong = con_thieu(conn, store.load(conn))
    if not tong:
        # No pairs to ask = the profile has no job titles. "Update" here is
        # meaningless — there is nothing to update. And run_scan will refuse
        # to run, so the button has to say what is about to happen.
        return {"mode": DAU, "label": "Run", "recent": 0, "todo": 0,
                "note": "the profile has no job titles yet — nothing to scan"}
    if thieu:
        rieng = "" if len(thieu) == tong else " (the rest only asks for new postings)"
        return {"mode": DAU, "label": "Run", "recent": 0, "todo": len(thieu),
                "note": f"{len(thieu)}/{tong} queries never scanned — "
                        f"fully scanning exactly those{rieng}"}

    # 4. Everything covered -> only ask for new postings. The window stretches
    #    with the gap itself: scanning regularly means 24 hours, a few days
    #    off widens it to 7. A hardcoded number misses things exactly when the
    #    user has been away longest.
    row = conn.execute(
        "SELECT started_at FROM source_run WHERE source = 'linkedin' AND ok = 1"
        " ORDER BY id DESC LIMIT 1").fetchone()
    cach = 0.0
    if row and row[0]:
        try:
            cach = (datetime.now(timezone.utc)
                    - datetime.fromisoformat(row[0])).total_seconds()
        except (ValueError, TypeError):
            cach = 0.0
    if cach <= li.NGAY:
        return {"mode": MOI, "label": "Update", "recent": li.NGAY, "todo": 0,
                "note": "the grid is fully covered — only asking for the last 24 hours"}
    return {"mode": MOI, "label": "Update", "recent": li.TUAN, "todo": 0,
            "note": "a few days off — asking for the last 7 days"}


# TWO SOURCES, TWO ROUTES, TWO SWITCHES. Both point at the same LinkedIn
# `/jobs/view/<id>` page, but the route that carries the id back is entirely
# different:
#
#     linkedin   typing keywords into a guest endpoint — 80 queries, half an
#                hour, outside Terms §8.2 (see ingest/web/linkedin.py)
#     alert      reading alert mail in YOUR OWN mailbox — 6 seconds, clean
#
# So they are not merged. Turn `linkedin` off and `alert` still goes through
# the WHOLE pipeline: fetch, filter, deep-read, score. Switching off one
# source must not kill another.
#
# CHROME IS A TOOL, NOT A SOURCE. The job description lives on a web page, so
# a posting from any source has to have its page opened — including postings
# that arrived by alert mail, because alert mail only gives the title,
# company, place and id. The whole Chrome section used to sit behind the
# `linkedin` switch, so turning it off left 107 alert postings sitting
# unscored: one switch silently switching off another source.
DOC_KY = ("linkedin", "alert")

# The switch for each deep-read source. A table rather than if/else: a fourth
# source adds one line instead of edits in four places.
CONG_TAC = {"linkedin": "SRC_LINKEDIN", "alert": "SRC_ALERT"}


def nguon_doc(conn) -> tuple[str, ...]:
    """Which sources are ENABLED and need a deep read. Each source decides
    for itself."""
    from .core import prefs
    return tuple(n for n in DOC_KY
                 if prefs.flag(conn, getattr(prefs, CONG_TAC[n])))


def _tin_do_dang(conn, nguon: tuple[str, ...] = DOC_KY) -> dict:
    """{source: [postings]} — postings worth deep-reading that still have no
    description, rebuilt from the DB.

    Returned PER SOURCE rather than in one bucket: `save_batch` writes by the
    (source, id) pair, so merging them and saving under one name creates new
    rows instead of patching the description into the existing ones. And
    because the two sources switch independently, `nguon` has to be able to
    filter — the queue of a disabled source is not this pass's work.
    """
    from .core.postings import HAVE_DESC
    from .ingest.base import Posting
    if not nguon:
        return {}
    rows = conn.execute(
        "SELECT r.source, r.source_id, p.title, p.company, p.location, p.url"
        "  FROM raw_posting r JOIN posting p ON p.raw_id = r.id"
        f" WHERE r.source IN ({','.join('?' * len(nguon))})"
        "   AND length(COALESCE(p.description,'')) < ?"
        "   AND (p.kept = 1 OR p.user_keep = 1)",
        (*nguon, HAVE_DESC)).fetchall()
    out: dict = {}
    for r in rows:
        out.setdefault(r["source"], []).append(
            Posting(source_id=r["source_id"], title=r["title"] or "",
                    company=r["company"] or "", location=r["location"] or "",
                    url=r["url"] or "", payload={"guest": True}))
    return out


def _chrome_pass(conn, answers: dict, log: Log, deep: bool,
                 manual: bool = False) -> tuple[int, int]:
    """The work that needs A WEB PAGE. Runs after the API sources, only
    inside the human window.

    CHROME IS A SHARED TOOL. Two different jobs need it:

        search     typing keywords into a guest endpoint -> linkedin only
        deep-read  open /jobs/view/<id> for the description -> EVERY enabled source

    So the `linkedin` switch only turns off the SEARCH. Alert postings still
    get deep-read, because `alert` is a different source and it is on.

    Each source runs independently: one source blocked or broken must NOT
    kill the others.
    """
    from .browser import cdp, chrome
    from .core import prefs
    from .core.scheduler import in_human_window
    from .ingest.web import linkedin as li
    from .ingest.web.base import Blocked

    # titles[:5] WAS REMOVED: it silently cut 7 of the profile's 12 titles,
    # and it only existed because the deep-read pass took too long. With the
    # root cause fixed the cut is unnecessary — the ceiling now lives at
    # li.MAX_QUERIES and writes a journal line when it is hit.
    # eFinancialCareers WAS DROPPED: 67% of its postings are agencies
    # (LinkedIn 24%), and it yielded 5 postings at 75+ against LinkedIn's 20.
    # Three times dirtier, four times less.
    titles = [t.strip() for t in (answers.get("job_titles") or "").splitlines() if t.strip()]
    levels = answers.get("seniority") or ["grad", "junior"]
    nhip = prefs.get(conn, prefs.PACE) or "thuong"
    bat_li = prefs.flag(conn, prefs.SRC_LINKEDIN)

    # WHAT THIS PASS DOES — asked of the same place that named the Run
    # button, so what the machine does and what the button promises can never
    # drift apart.
    kieu = scan_mode(conn)

    # BUILD THE WORK LIST BEFORE OPENING CHROME. All DB reads, costing
    # nothing — and in exchange: no work means no window opens at all. Chrome
    # used to open first and only then discover there was nothing to do, and
    # the user saw a window flash up and vanish without knowing why.
    viec: list[tuple[str, object]] = []
    dem: dict[str, int] = {}

    if kieu["mode"] == TIEP:
        # SEARCH FOR NOTHING. The half-done work is already in the DB;
        # re-running the search reopens the same 2,296 postings over 30
        # minutes only to finish reading the ones we already knew about.
        #
        # ONE SAVE PER SOURCE. save_batch writes by the (source, id) pair:
        # read an alert posting and save it under the name "linkedin" and you
        # create a new row, while the alert row keeps its empty description.
        do_dang = _tin_do_dang(conn, nguon_doc(conn))
        dem = {n: len(v) for n, v in do_dang.items()}

        def _doc(_ten, _items):
            def chay(tab):
                suc = li.read_deep(tab, _items, pace=nhip, ten=_ten,
                                   stop=lambda: halt.wanted(STAGE))
                return _items, suc
            return chay
        viec = [(ten, _doc(ten, items)) for ten, items in sorted(do_dang.items())]

    places = li.places_for(answers.get("markets") or [],
                           answers.get("location") or "")
    # `vua_phu` must exist even when the search does not run: the save loop
    # below reads it to know whether any pair was just covered. Define it
    # inside the else branch and pressing "Continue" raises NameError —
    # caught by `except Exception`, so descriptions were saved successfully
    # while the pass was still recorded as FAILED. No source reported an error.
    vua_phu: set[str] = set()
    phu, _muc_cu = da_quet(conn)
    seen: set[str] = set()
    tu_giu: set[str] = set()

    if kieu["mode"] != TIEP and bat_li and titles:
        # Already read means skip — computed across BOTH sources, because
        # the same id is the same page. This is NOT merging the sources: it
        # is only declining to reopen a page already read. Asking about
        # "linkedin" alone would reopen an alert posting that already has a
        # description.
        seen = postings.already_read(conn, DOC_KY)

        # Plus the postings Vin KEPT BY HAND: the filter drops them, so
        # asking the filter alone means they are never deep-read — keeping a
        # posting only for it to sit at "the machine has not read this"
        # forever is the Keep button betraying itself.
        tu_giu = {r[0] for r in conn.execute(
            "SELECT r.source_id FROM raw_posting r JOIN posting p ON p.raw_id = r.id"
            " WHERE r.source IN ({}) AND p.user_keep = 1".format(
                ",".join("?" * len(DOC_KY))), DOC_KY)}

        # IS IT WORTH DEEP-READING. Answered with the exact filter derive()
        # will use afterwards, so there are never two parallel rules waiting
        # to disagree.
        def dang_doc(item) -> bool:
            if item.source_id in tu_giu:
                return True
            giu, _ = jobfilter.judge(item, answers)
            return giu

        # A covered pair only asks for what is new; an uncovered pair asks
        # fully. `vua_phu` is where the search records the pairs it just
        # asked fully and completely — only those are added to the memory.
        # The window applies to COVERED pairs; with no complete pass ever
        # done (phu empty) every pair asks fully.
        cua_so = kieu["recent"] or li.NGAY
        viec.append((li.NAME, lambda tab: li.fetch(
            tab, titles, location=places, levels=levels, pages=4, deep=deep,
            skip=frozenset(seen), worth=dang_doc, pace=nhip, recent=cua_so,
            covered=frozenset(phu), done_out=vua_phu,
            stop=lambda: halt.wanted(STAGE))))

    if not viec:
        # Say why it is empty. "Nothing happened" in silence leaves the user
        # seeing a suspiciously fast scan with no idea what they turned off.
        jlog.emit(SEARCH, "no work needs a web page"
                          + ("" if bat_li else " · LinkedIn is off")
                          + ("" if titles else " · the profile has no job titles"))
        return 0, 0

    # The human window exists because browsing at 3am EVERY NIGHT is a
    # machine's rhythm, not a person's. But when the user presses Run
    # themselves, that IS a real person.
    if not manual and not in_human_window():
        log("  chrome: outside the human window, deferred to the next pass")
        jlog.warn(SEARCH, f"outside the human window — {len(viec)} jobs deferred")
        return 0, 0

    jlog.progress(SEARCH, "launching Chrome")
    try:
        chrome.launch(headless=False)          # headed: the site blocks headless
    except chrome.ChromeError as exc:
        jlog.error(SEARCH, f"could not launch Chrome: {exc}")
        log(f"  chrome                     FAILED  {exc}")
        return 0, 0

    # From here to the end of the function Chrome IS OPEN. So every exit has
    # to pass through finally: close Chrome when the work is done, and
    # ESPECIALLY when it fails.
    #
    # The close used to sit at the end of the function, outside any try. One
    # error in the middle — the DB locked while reading `already_read`, a
    # dead socket after the machine woke — and the Chrome window stayed on
    # screen until the app was quit. And this app runs 24/7: "until the app
    # is quit" means forever.
    try:
        # SAY WHAT THIS PASS IS DOING, job by job. "scanning" is one word
        # hiding three different jobs; the user has to be able to read what
        # they are paying for.
        jlog.emit(SEARCH, f"{kieu['label'].upper()} — {kieu['note']}")
        if kieu["mode"] == TIEP:
            jlog.emit(SEARCH, f"finishing {sum(dem.values()):,} unread postings,"
                              " skipping the search · "
                              + " · ".join(f"{n} {c}" for n, c in sorted(dem.items())))
        else:
            jlog.emit(SEARCH, f"linkedin: {len(titles)} titles × {len(places)} places"
                              f" · skipping {len(seen)} already read"
                              + (f" · {len(tu_giu)} you kept by hand" if tu_giu else ""))

        total_seen = total_new = 0
        for name, run in viec:
            tab = None
            try:
                tab = cdp.open_tab()
                items, health = run(tab)
                seen, new = postings.save_batch(conn, name, items)
                # health.ok rather than a hardcoded True: a source blocked
                # part-way still returns postings (the ones it got through),
                # but that run was NOT healthy.
                postings.record_run(conn, name, ok=health.ok, fetched=seen, new_rows=new,
                                    error="" if health.ok else f"blocked: {health.summary}",
                                    attempted=health.attempted, failed=health.failed)
                # REMEMBER THE PAIRS JUST COVERED. Accumulated, not
                # overwritten: a pass stopped part-way still covered its
                # first few pairs, and there is no reason to redo those.
                #
                # A pair only asked over the 24-hour window is NOT in here —
                # glancing at the newest slice is not coverage.
                if health.ok and vua_phu:
                    import json as _json
                    cu_phu, _ = da_quet(conn)
                    prefs.put(conn, prefs.LI_DONE,
                              _json.dumps(sorted(cu_phu | vua_phu)))
                    prefs.put(conn, prefs.LI_LEVELS, _json.dumps(sorted(levels)))
                    jlog.emit(SEARCH, f"covered {len(vua_phu - cu_phu)} more queries"
                                      f" · {len(cu_phu | vua_phu)} in total")
                bad = f"  ⚠ {health.summary}" if health.failed else ""
                (jlog.ok if health.ok else jlog.warn)(
                    SEARCH, f"{name}: {seen} fetched, {new} new"
                            + (f" · {health.summary}" if health.summary else ""))
                log(f"  {name:26} {seen:5} fetched, {new:5} new{bad}")
                total_seen += seen; total_new += new
            except Blocked as exc:
                # The site refused automated access. Record it and stop — do
                # not argue back.
                postings.record_run(conn, name, ok=False, error=f"blocked: {exc}")
                postings.log(conn, "source_blocked", f"{name}: {exc}")
                jlog.warn(SEARCH, f"{name}: BLOCKED — {str(exc)[:60]}")
                log(f"  {name:26} BLOCKED {str(exc)[:44]}")
            except Exception as exc:                # noqa: BLE001
                postings.record_run(conn, name, ok=False,
                                    error=f"{type(exc).__name__}: {exc}")
                jlog.error(SEARCH, f"{name}: {type(exc).__name__} — {str(exc)[:60]}")
                log(f"  {name:26} FAILED  {type(exc).__name__}: {str(exc)[:40]}")
            finally:
                if tab is not None:
                    tab.close()

        return total_seen, total_new
    finally:
        # Relaunching costs ~2 seconds, nowhere near worth a window squatting
        # on screen for an hour.
        if not chrome.shutdown():
            jlog.warn(SEARCH, "could not close Chrome — it is still open")



def run_scan(log: Log | None = None, chrome_sources: bool = True,
             deep: bool = True, manual: bool = False) -> dict:
    say: Log = log or (lambda _msg: None)
    conn = db.connect()
    try:
        answers = store.load(conn)
        if not store.can_ingest(answers):
            # IT HAS TO SAY SO. This used to `return` in silence: press Run
            # and the API still answered "running…", the journal stayed
            # empty, no postings came back, and the user waited forever. A
            # refusal nobody can see the reason for is worse than no button.
            thieu = store.missing_for_ingest(answers)
            hoi = all_questions()
            ten = " · ".join(hoi[q].text for q in thieu if q in hoi)
            jlog.warn(SEARCH, f"cannot scan yet — the profile is missing: {ten}")
            say(f"the profile is incomplete: {ten}")
            return {"ok": False, "summary": "the profile is incomplete", "missing": thieu}

        # A TIMESTAMP, not a total: "new jobs" means the jobs THIS pass
        # brought in, not the difference between two counts. Take the
        # difference and a pass that brings 10 new jobs while 10 old ones get
        # dropped reports 0, and the user is told nothing.
        started_at = postings.now()
        boards = load_boards(conn)
        postings.log(conn, "scan_started")

        # arbeitnow + remotive WERE DROPPED: the wrong market. Arbeitnow is a
        # European job board, Remotive is global remote — between them they
        # pulled 1,992 postings to keep exactly 1. Vin is in the UK and is
        # not asking for sponsorship.
        # Company boards stay: their hit rate is low because the whole board
        # is pulled before filtering, but they are the employer DIRECTLY and
        # cost only HTTP.
        todo = [(f"{key}:{board}", mod.fetch_board, (board,))
                for mod, key in ((greenhouse, "greenhouse"), (lever, "lever"),
                                 (ashby, "ashby"))
                # dict.fromkeys: two differently named companies can produce
                # the SAME slug ("Ocado" and "Ocado Group" -> ocadogroup) ->
                # two HTTP calls for one board and a doubled "fetched" total.
                for board in dict.fromkeys(boards.get(key, []))]
        # THE SOURCE SWITCHES. The two ways of searching produce very
        # different postings, so sometimes you only want one. Read here and
        # not at the call site: the automatic pass and the manual Run button
        # must both obey the same switch.
        from .core import prefs
        bat_board = prefs.flag(conn, prefs.SRC_BOARD)
        bat_li = prefs.flag(conn, prefs.SRC_LINKEDIN)
        if not bat_board:
            jlog.warn(SEARCH, f"boards are OFF — skipping {len(todo)} API sources")
            todo = []
        else:
            # Per ATS. The big switch (boards) and the small switches (each
            # ATS) are two layers: either can stop it, and it has to SAY
            # which one — skipping in silence means far fewer postings with
            # nobody able to work out why.
            tat = [k for k, key in prefs.SRC_ATS.items() if not prefs.flag(conn, key)]
            if tat:
                truoc = len(todo)
                todo = [t for t in todo if t[0].split(":")[0] not in tat]
                jlog.warn(SEARCH, f"{', '.join(tat)} off — skipping"
                                  f" {truoc - len(todo)}/{truoc} API sources")
        if not bat_li:
            # LINKEDIN OFF = KEYWORD SEARCH OFF. Not Chrome off: Chrome is
            # also the route to the DESCRIPTION for other sources' postings,
            # and alert mail is a different source with its own switch.
            #
            # Merging those two into one switch already had a measured cost:
            # 107 alert postings sat unscored, the journal correctly said
            # "LinkedIn is OFF", and still nobody connected that to the
            # consequence, because the consequence belonged to another source.
            jlog.warn(SEARCH, "LinkedIn is OFF — no keyword search this pass"
                              + (" · alert mail still runs the whole pipeline"
                                 if prefs.flag(conn, prefs.SRC_ALERT) else ""))

        # JOB-ALERT MAIL — the third source. Grouped with the API boards
        # because it is just as cheap and needs no Chrome either: 69 jobs in
        # 6 seconds, measured on the real mailbox. It carries no description,
        # so the deep-read pass still has to open each posting — but it
        # reports far faster, and it is clean in principle.
        if prefs.flag(conn, prefs.SRC_ALERT):
            from .ingest import alerts
            from .track import mail as _mail
            dia_chi, mat_khau = _mail.account()
            if dia_chi and mat_khau:
                ngay = prefs.num(conn, prefs.MAIL_DAYS, 1, 365)
                todo.append((alerts.NAME, alerts.fetch,
                             (dia_chi, mat_khau, ngay)))
            else:
                jlog.warn(SEARCH, "job-alert mail: no mailbox connected — skipped")

        # `chrome_sources` is the CALLER's flag (a light cron pass, a test) —
        # it turns Chrome off entirely. What work needs a web page is
        # _chrome_pass's own decision from the per-source switches, so here
        # it only says "open Chrome or not".
        jlog.emit(SEARCH, f"scan started — {len(todo)} fast sources"
                          + (" + the Chrome pass" if chrome_sources else ""))

        total_seen = total_new = 0
        stopped = False
        for index, (name, fn, args) in enumerate(todo, 1):
            # The break point: BETWEEN two sources, never mid-transaction.
            # Half a transaction written to the DB is worse than finishing
            # the source in hand.
            if halt.wanted(STAGE):
                stopped = True
                break
            jlog.progress(SEARCH, f"API source — {name}", index, len(todo))
            s, n = _run_source(conn, name, fn, *args, log=say)
            total_seen += s; total_new += n

        if chrome_sources and not stopped and not halt.wanted(STAGE):
            s, n = _chrome_pass(conn, answers, say, deep, manual)
            total_seen += s; total_new += n
        elif chrome_sources:
            jlog.warn(SEARCH, "skipping the Chrome pass — a stop was requested")

        if halt.wanted(STAGE):
            stopped = True

        # --- the derived layer: filter + group + score, ONE transaction ---
        from .core.derive import derive
        result = derive(conn, log=say)
        kept, n_groups = result["kept"], result["groups"]
        agencies, marks = result["agencies"], {"scored": result["scored"]}

        # --- the company list grows on its own ---
        from .ingest.web import companies as co
        learned = co.learn_from_postings(conn)
        found = co.resolve_pending(conn, limit=12)
        if learned or found["found"]:
            say(f"  companies: +{learned} new, resolved {found['found']}/{found['checked']}")

        fresh_matches = int(conn.execute(
            "SELECT COUNT(*) FROM posting p JOIN raw_posting r ON p.raw_id = r.id"
            " WHERE p.kept = 1 AND r.fetched_at >= ?", (started_at,)).fetchone()[0])

        summary = (f"fetched {total_seen} · new {total_new} · kept {kept} · "
                   f"{n_groups} distinct jobs · {agencies} via agencies")
        postings.log(conn, "scan_finished", summary)
        jlog.done(SEARCH)
        jlog.ok(SEARCH, f"scan finished — {summary}")
        return {"ok": True, "summary": summary, "seen": total_seen, "new": total_new,
                "kept": kept, "groups": n_groups, "scored": marks["scored"],
                "new_matches": fresh_matches}
    finally:
        conn.close()
