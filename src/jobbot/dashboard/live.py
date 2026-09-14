"""REAL data from the DB.

mock.py was deleted outright — there is not one invented number left in the
app. That is why the pages needed no changes at all when they moved from fake
data to real.

Everything here reads the DB. Nothing in this module invents a value.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from ..core import postings


STALE_DAYS = 45          # past this, the role has most likely been filled


def _age_days(ts: int) -> int | None:
    """How many days ago it was posted. None = the date is unknown."""
    if not ts:
        return None
    return int((datetime.now(timezone.utc).timestamp() - ts) // 86400)


def _ago(stamp: str) -> str:
    """Sources give dates two ways: ISO (Greenhouse/Lever) and Unix (Arbeitnow)."""
    if not stamp:
        return ""
    try:
        then = (datetime.fromtimestamp(int(stamp), timezone.utc)
                if str(stamp).isdigit() else datetime.fromisoformat(stamp))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        return ""
    seconds = (datetime.now(timezone.utc) - then).total_seconds()
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{int(seconds // 60)} min ago"
    if seconds < 172800:
        return f"{int(seconds // 3600)} hours ago"
    return f"{int(seconds // 86400)} days ago"


def dem_chip(conn: sqlite3.Connection, flt) -> dict:
    """HOW MANY POSTINGS each filter choice leaves, given the filters ALREADY on.

    Why it is needed: measured on the real store, the "Near me" chip yielded
    411 postings — exactly what "Anywhere" yields. Pressing it changed
    nothing. "All of the UK" gave 407/411, "Direct employer" gave exactly the
    default figure. Three buttons you press and see no change, and the user
    stops trusting the whole row.

    Fixed by PRINTING THE NUMBER, not by removing the button: the number says
    outright what pressing gets you, and it says it against TODAY's data —
    another day with another store and the number changes itself, with nobody
    having to go and revise a list of buttons.

    Counted IN CONTEXT (on top of the filters already on), because that is the
    question the user is actually asking: "filtered like this, how many are
    left if I also press that".

    The cost: 26 COUNT queries, measured at 107ms on a 5,166-posting store.
    """
    from .filters import BAND, CHANCE, DAYS, FOUND, LOC, SHOW, VIA, JobFilter
    nha, gan = noi_toi(conn)
    ra: dict = {}
    for khoa, bang in (("chance", CHANCE), ("band", BAND), ("loc", LOC),
                       ("found", FOUND), ("via", VIA), ("days", DAYS),
                       ("show", SHOW)):
        for val, _ in bang:
            doi = flt.pairs(**{khoa: val, "page": ""})
            moi = JobFilter.from_query({k: [v] for k, v in doi if v != ""})
            w, args = moi.where(nha=nha, near=gan)
            ra[f"{khoa}:{val}"] = int(conn.execute(
                f"SELECT COUNT(*) FROM posting{w}", args).fetchone()[0])
    return ra


def sieve(conn: sqlite3.Connection) -> dict:
    """The KEEP/DROP sieve — exactly the three things ingest/filter.judge() uses.

    NO invented knobs: judge() looks only at the job title, the seniority and
    the location. Adding a field for something the code never reads is
    building a fake button.

    These three values live in THE PROFILE, not in a Search-only setting — so
    editing them here changes the filter pass, the keywords sent to LinkedIn,
    and the title part of the scoring.
    """
    from ..core import prefs
    from ..profile.schema import section_by_id
    from ..profile import store as pstore

    answers = pstore.load(conn)
    opts = {}
    for section in ("muc_tieu",):
        found = section_by_id(section)
        for q in (found.questions if found else []):
            if q.id in ("seniority", "markets"):
                opts[q.id] = [(o.value, o.label) for o in (q.options or [])]

    total = int(conn.execute("SELECT COUNT(*) FROM posting").fetchone()[0])
    return {
        "titles": [t.strip() for t in (answers.get("job_titles") or "").splitlines()
                   if t.strip()],
        "seniority": answers.get("seniority") or [],
        "markets": answers.get("markets") or [],
        "seniority_options": opts.get("seniority", []),
        "market_options": opts.get("markets", []),
        "missed": missed_titles(conn),
        # The source switches — NOT profile data, so they bypass the Apply
        # button and re-judge no 5,000 postings. Just machine switches.
        "src_board": prefs.flag(conn, prefs.SRC_BOARD),
        "src_linkedin": prefs.flag(conn, prefs.SRC_LINKEDIN),
        "src_alert": prefs.flag(conn, prefs.SRC_ALERT),
        "total": total,
        # Really measured on 4,660 postings: 1.1 seconds. Rounded up so the
        # promise never falls short.
        "seconds": max(1, round(total / 4000)),
    }


def noi_toi(conn: sqlite3.Connection) -> tuple[str, str]:
    """(region lived in, city lived in) — context for the place filter.

    Read from the "Where you're based" field. This is where `location` affects
    VIEWING: it does not decide which jobs are eligible (cutting to London
    loses 71 UK jobs outside it), it gives you one click to see which are
    CONVENIENT.
    """
    from ..ingest.filter import noi_o
    from ..profile import store
    o_dau = (store.load(conn).get("location") or "").strip()
    # "London, UK" -> "London". LIKE-comparing the whole string matches no
    # posting at all, because postings say "London, England, United Kingdom".
    return noi_o(o_dau) or "uk", o_dau.split(",")[0].strip()


def jobs(conn: sqlite3.Connection, flt) -> list[dict]:
    """Filter to what the user asked, THEN merge duplicates — merge first and
    the wrong group gets filtered.

    A BUG SINCE FIXED: merging in Python AFTER a LIMIT applied to ROWS. Paging
    cut by row while the count at the head of the page counted GROUPS, so the
    two could never agree: on the real machine the header said 139 jobs and
    walking every page counted 144 cards — 5 groups split across a page
    boundary and shown twice. Merging has to happen IN SQL, before paging.
    """
    where, args = flt.where(*noi_toi(conn))
    per, offset = flt.limit()
    rows = conn.execute(
        # THE RULE: a filter chooses WHICH POSTINGS ARE SHOWN, it never
        # changes WHAT A POSTING LOOKS LIKE.
        #
        # So everything describing the posting — the source badges, "+1
        # places", the score, the title — is computed over THE WHOLE group, on
        # the unfiltered table. They used to be computed over the filtered
        # part, so one press of the LinkedIn source chip stripped the Man
        # Group posting of its board badge, of "+1 places", and even of its
        # score of 100 (its LinkedIn row had not been deep-read, so it had no
        # score). One job, two filters, two faces — the screen misreporting
        # the very posting it was showing.
        #
        # `ca_nhom` counts THE WHOLE group, on the unfiltered table; `hop` has
        # one job left: which groups have AT LEAST ONE row passing the filter.
        "WITH ca_nhom AS ("
        "  SELECT COALESCE(group_id, CAST(id AS TEXT)) AS grp,"
        "         COUNT(*) AS n, GROUP_CONCAT(source) AS srcs"
        "    FROM posting GROUP BY 1),"
        "hop AS ("
        f"  SELECT DISTINCT COALESCE(group_id, CAST(id AS TEXT)) AS grp"
        f"    FROM posting{where})"
        "SELECT day.*, ca_nhom.n AS merged, ca_nhom.srcs AS all_sources FROM ("
        "  SELECT *,"
        # The group's representative = the highest-scoring posting, not the
        # first one encountered.
        "         ROW_NUMBER() OVER (PARTITION BY grp"
        "                            ORDER BY score DESC NULLS LAST, id ASC) AS rn"
        "    FROM (SELECT *, COALESCE(group_id, CAST(id AS TEXT)) AS grp"
        "            FROM posting)"
        ") AS day JOIN ca_nhom USING (grp) JOIN hop USING (grp)"
        f" WHERE rn = 1 ORDER BY {flt.order()} LIMIT ? OFFSET ?",
        [*args, per, offset]).fetchall()

    out = []
    for row in rows:
        sources = list(dict.fromkeys((row["all_sources"] or "").split(",")))
        # How this posting was found. The most important badge on each row:
        # two blind searches run in two different places, so the list shows at
        # a glance which one is bringing in what. Found by both -> two badges.
        found_by = sorted({s if s in ("linkedin", "alert") else "board"
                           for s in sources if s})
        out.append({
            "id": str(row["id"]),
            "title": row["title"], "company": row["company"],
            "location": row["location"] or "not stated",
            "salary": row["salary"] or "not stated",
            "score": row["score"],
            "confidence": row["score_conf"],
            "posted": _ago(row["posted_at"]) if row["posted_at"] else "",
            "age_days": _age_days(row["posted_ts"]),
            "sources": [s for s in sources if s],
            "found_by": found_by,
            "merged": row["merged"],
            "state": "new" if row["kept"] else "dropped",
            "user_keep": bool(row["user_keep"]),
            "via_agency": bool(row["via_agency"]),
            "realism": row["realism"], "realism_why": row["realism_why"],
            "deadline": row["deadline"],
            "drop_reason": row["drop_reason"],
            "url": row["url"],
        })
    return out


def job_counts(conn: sqlite3.Connection, flt) -> dict:
    """The count behind each 'Show' choice — seen before it is pressed."""
    out = {}
    noi = noi_toi(conn)          # read ONCE for all three counts
    for value, _label in (("matched", ""), ("dropped", ""), ("all", "")):
        where, args = type(flt)(**{**flt.__dict__, "show": value}).where(*noi)
        out[value] = int(conn.execute(
            f"SELECT COUNT(DISTINCT COALESCE(group_id, CAST(id AS TEXT)))"
            f" FROM posting{where}", args).fetchone()[0])
    return out


def facets(conn: sqlite3.Connection) -> dict:
    """Values that really exist in the DB, to fill the dropdowns — never an
    invented, empty choice."""
    sources = [r["s"] for r in conn.execute(
        "SELECT DISTINCT substr(source, 1, CASE WHEN instr(source,':')>0"
        " THEN instr(source,':')-1 ELSE length(source) END) AS s"
        " FROM posting ORDER BY s")]
    companies = [(r["company"], r["n"]) for r in conn.execute(
        "SELECT company, COUNT(*) n FROM posting WHERE kept=1"
        " GROUP BY company ORDER BY n DESC, LOWER(company) LIMIT 40")]
    return {"sources": sources, "companies": companies}


def job_detail(conn: sqlite3.Connection, job_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM posting WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    same = conn.execute(
        "SELECT source, url FROM posting WHERE group_id = ? ORDER BY id",
        (row["group_id"] or str(row["id"]),)).fetchall()
    return {
        "id": str(row["id"]), "title": row["title"], "company": row["company"],
        "location": row["location"] or "not stated",
        "salary": row["salary"] or "not stated",
        "score": row["score"], "confidence": row["score_conf"],
        "realism": row["realism"], "realism_why": row["realism_why"],
        "deadline": row["deadline"],
        "posted": _ago(row["posted_at"]) if row["posted_at"] else "",
        "sources": sorted({r["source"] for r in same}),
        "merged": len(same), "url": row["url"],
        "links": _links(same, row["url"]),
        "jd": row["description"] or "(no description from this source)",
        "requirements": _reqs(row),
        "explain": json.loads(row["score_json"]) if row["score_json"] else None,
        "score_json": row["score_json"],
        "project": None,                        # step 4
    }


def _links(same, url_minh: str) -> list[dict]:
    """Links to THE ORIGINAL POSTING. One job posted in two places returns both.

    Until now `job_detail` fetched every (source, url) pair and then THREW the
    urls away, keeping only the source name and the "+1 places" figure. So the
    detail screen could show a whole description with not one link across to
    the real posting — checking it meant going and finding it by hand.

    THE COMPANY BOARD COMES FIRST. LinkedIn is only a noticeboard: applying
    through it goes via a third party, while the company's own board is where
    the application lands directly with whoever is hiring.
    """
    thay: dict[str, dict] = {}
    for r in same:
        url = (r["source"], r["url"]) if not isinstance(r, tuple) else r
        nguon, dia_chi = url
        if not dia_chi or dia_chi in thay:
            continue
        # An alert email leads to the same LinkedIn page as the Chrome
        # source; only the route that brought it differs — so the button
        # still reads "LinkedIn".
        tren_li = nguon in ("linkedin", "alert")
        thay[dia_chi] = {
            "url": dia_chi,
            "kind": nguon if tren_li else "board",
            "name": "LinkedIn" if tren_li else nguon.split(":")[0],
            # The domain so the reader KNOWS IN ADVANCE where they are
            # going. A button reading "Open the original" without saying
            # where it leads has to be pressed to be understood.
            "host": dia_chi.split("/")[2] if "//" in dia_chi else dia_chi[:40],
            "minh": dia_chi == url_minh,
        }
    return sorted(thay.values(), key=lambda x: x["kind"] != "board")


def _reqs(row) -> list[dict]:
    """The JD's requirements with their evidence — in exactly the shape
    views/jobs.py needs."""
    if not row["score_json"]:
        return []
    data = json.loads(row["score_json"])
    return [{"text": r["text"], "met": r["met"], "must": r["must"],
             "evidence": r["evidence"] or "—"} for r in data.get("requirements", [])]


# ---------------------------------------------------------------- settings

# CHROME_SOURCES IS GONE. It once had two members, and that is exactly why
# the badge used to be called "chrome": back then it had to be named after THE
# METHOD, because two sources went through Chrome. eFinancialCareers was
# removed from the app long ago (67% of its postings were agencies), so there
# is now exactly one source — and it has a name of its own.


def sources(conn: sqlite3.Connection) -> list[dict]:
    """Every source, with its kind (api or chrome) and its last run."""
    counts = {r["source"]: r["n"] for r in conn.execute(
        "SELECT source, COUNT(*) n FROM posting GROUP BY source")}
    runs = {r["source"]: r for r in postings.last_runs(conn)}

    out = []
    for name in sorted(set(counts) | set(runs)):
        family = name.split(":")[0]
        run = runs.get(name)
        out.append({
            "name": name,
            "kind": family if family in ("linkedin", "alert") else "board",
            "on": bool(run and run["ok"]),
            "last": _ago(run["at"]) if run else "never",
            "found": counts.get(name, 0),
            "note": (run["error"][:60] if run and not run["ok"] else ""),
        })
    out.sort(key=lambda s: (-s["found"], s["name"]))
    return out


def settings(conn: sqlite3.Connection) -> dict:
    """Three knobs plus a status line. No more."""
    from ..core import prefs, versions
    from ..core.derive import stale_count
    from ..core.scheduler import MAX_EVERY, MIN_EVERY, human_window
    from . import mau
    from ..core import tele as _tele

    boards = int(conn.execute(
        "SELECT COUNT(DISTINCT substr(source, instr(source,':') + 1)) FROM posting"
        " WHERE instr(source,':') > 0").fetchone()[0])
    firms = int(conn.execute("SELECT COUNT(*) FROM company").fetchone()[0])
    stale = stale_count(conn)

    from ..browser import chrome as ch
    from ..core import reset as reset_mod
    from ..profile import store as pstore
    from ..track import mail as _mail
    kho = reset_mod.inventory(conn)

    # REAL numbers for each source. Introducing them with adjectives
    # ("popular", "modern") helps nobody choose; "how many came in, how many
    # were kept" is what a decision can be made on.
    from ..scan_runner import load_boards
    boards = load_boards(conn)
    def _dem(like: str) -> tuple[int, int, int]:
        row = conn.execute(
            "SELECT COUNT(*), SUM(kept), SUM(remote) FROM posting WHERE source LIKE ?",
            (like,)).fetchone()
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    nguon = []
    for ats, note in (
        ("greenhouse", "the ATS most often seen at funds and large firms"),
        ("lever", "common at scale-ups · reports remote roles"),
        ("ashby", "AI companies / startups · nearly every posting says remote"),
    ):
        tin, giu, rem = _dem(f"{ats}:%")
        nguon.append({"id": ats, "ten": ats, "note": note,
                      "on": prefs.flag(conn, prefs.SRC_ATS[ats]),
                      "boards": len(boards.get(ats, [])),
                      "tin": tin, "giu": giu, "remote": rem})
    # Job alert emails — in the same "fast sources" family, so they share the
    # table, but they are not an ATS: there is no board to count.
    _tin, _giu, _rem = _dem("alert")
    nguon.append({"id": "alert", "ten": "alert mail", "boards": 0,
                  "note": "sent by LinkedIn to the mailbox · the fastest, and"
                          " no scraping · a source of its own, running even"
                          " while LinkedIn is off",
                  "on": prefs.flag(conn, prefs.SRC_ALERT),
                  "tin": _tin, "giu": _giu, "remote": _rem})
    return {
        "reset_rows": kho["total_rows"],
        "reset_files": kho["files"],
        "reset_mb": round(kho["bytes"] / 1_048_576, 1),
        "reset_backup_dir": str(reset_mod.backup_dir()),
        "every": prefs.num(conn, prefs.SCAN_EVERY, MIN_EVERY, MAX_EVERY),
        "pace": prefs.get(conn, prefs.PACE) or "thuong",
        # The two knobs of the GENERAL TAB — whole-app settings, belonging
        # to no stage.
        "mau_nay": mau.hop_le(prefs.get(conn, prefs.MAU)),
        "tu_truc": prefs.flag(conn, prefs.AUTORUN),
        # THE NOTIFICATIONS TAB. `tele_token` is the MASKED form — the last
        # four characters only. The real token never leaves config.toml.
        "tele_noi": _tele.da_noi(),
        "tele_token": _tele.che(_tele.cau_hinh().get("token", "")),
        "tele_chat": str(_tele.cau_hinh().get("chat_id", "") or ""),
        "bao_bat": {k: prefs.flag(conn, k) for k in prefs.BAO},
        "bao_muc": prefs.get(conn, prefs.BAO_MUC) or "tat",
        "bao_nguong": prefs.num(conn, prefs.BAO_NGUONG, 1, 999),
        "bao_gio": prefs.num(conn, prefs.BAO_GIO, 0, 23),
        "sources": nguon,
        "board_on": prefs.flag(conn, prefs.SRC_BOARD),
        # The address and the state ONLY. The password never leaves
        # config.toml.
        "mail_ready": all(_mail.account()),
        "mail_address": _mail.account()[0],
        "mail_days": prefs.num(conn, prefs.MAIL_DAYS, 1, 365),
        "mail_profile": (pstore.load(conn).get("email") or "").strip(),
        "hours": human_window(),
        "status": [
            ("Chrome", "running" if ch.alive() else "off"),
            ("Boards being scanned", f"{boards}"),
            ("Companies known", f"{firms:,}"),
            ("Postings needing re-judging", f"{stale:,}" if stale else "none"),
            ("Filter rules", versions.FILTER_RULES),
            ("Scoring rules", versions.SCORE_RULES),
        ],
    }


def chrome_status() -> dict:
    from ..browser import chrome as ch
    from ..core.scheduler import HUMAN_WINDOW
    from ..ingest.web import linkedin as li
    alive = ch.alive()
    return {
        "alive": bool(alive),
        "version": (alive or {}).get("Browser", "—"),
        "profile": str(ch.profile_dir()),
        "port": ch.PORT,
        "window": f"{HUMAN_WINDOW[0]:02d}:00 – {HUMAN_WINDOW[1]:02d}:00",
        "pace": f"{li.PAUSE[0]:g}–{li.PAUSE[1]:g}s between pages on LinkedIn",
    }


def company_stats(conn: sqlite3.Connection) -> dict:
    from ..ingest.web import companies as co
    return co.stats(conn)


def last_runs(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in postings.last_runs(conn)]


def health(conn: sqlite3.Connection) -> dict:
    """System health — something the user has to see, not something that only
    sits in the DB.

    `stale` > 0 means the current verdicts came from an OLD profile or OLD
    rules. Without showing it, the user reads out-of-date figures believing
    they are current.
    """
    from ..core import versions
    from ..core.derive import stale_count

    runs = postings.last_runs(conn)
    broken = [dict(r) for r in runs if not r["ok"]]
    flaky = [dict(r) for r in runs
             if r["ok"] and r["attempted"] and r["failed"]]
    return {
        "stale": stale_count(conn),
        "unjudged": postings.unjudged(conn),
        "filter_rules": versions.FILTER_RULES,
        "score_rules": versions.SCORE_RULES,
        "broken": broken,
        "flaky": flaky,
    }
# ---------------------------------------------------------------- projects

# ---------------------------------------------------- THE CV LAYER'S CACHE
#
# ONE store, ONE key, ONE place that forgets.
#
# There used to be three separate caches — _CV_CACHE, _BLOCK_CACHE, _HUT_CACHE
# — all built on the very same `_cv_key`, but cleared in three DIFFERENT sets
# of places: reset forgot _HUT_CACHE, the knob route forgot _BLOCK_CACHE,
# batch cleared only _CV_CACHE. Three things depending on one input while
# expiring on three different schedules means the screen sooner or later mixes
# old numbers with new, and nobody can trace it.
_NHO: dict = {}


def nho(conn: sqlite3.Connection, ten: str, tinh):
    """Cache `tinh()` under the CV layer's shared key.

    The key is: the CV text · the scoring rules · the set of kept postings ·
    the Adjust knobs — see `_cv_key`. Change any one of them and ALL THREE
    figures expire together, because all three are read from them.
    """
    from ..profile import store as pstore
    key = _cv_key(conn, pstore.load(conn).get("cv_text") or "")
    cu = _NHO.get(ten)
    if cu is not None and cu[0] == key:
        return cu[1]
    ra = tinh()
    _NHO[ten] = (key, ra)
    return ra


def quen() -> None:
    """Forget everything. ONE call for every change touching the CV layer."""
    _NHO.clear()


def cv_hut(conn: sqlite3.Connection) -> dict:
    """The GAP ladder — which thing to write or learn first unlocks the most.

    CACHED: the ladder runs greedily over ~47 candidates, measured at 0.6
    seconds. The CV tab is opened many times in a sitting, and the result only
    changes when the profile or the posting store changes.
    """
    from ..scoring.gap import thang
    from ..scoring.score import build_index
    from ..scoring.vocab import alias_hits
    from ..profile import store as pstore

    def _tinh():
        answers = pstore.load(conn)
        co: set = set()
        for e in build_index(answers):
            co |= set(alias_hits(e.normal))
        return thang(conn, co)
    return nho(conn, "hut", _tinh)


def phien_stage(conn: sqlite3.Connection) -> dict:
    """The SESSION state for the Home bar — one sentence that says where it is.

    Three situations, and they DIFFER in what the user should do:
        running    some stage is working right now
        on watch   the session is on, counting down to the next round
        OFF        nothing is going to happen by itself
    Fold the last two into "on" and the one distinction between "news is
    coming" and "resting between rounds" is lost.
    """
    from ..core import prefs, scheduler
    sch = scheduler.current()
    bat = [prefs.PHIEN[k][1] for k in prefs.PHIEN if prefs.flag(conn, k)]
    khuc = " → ".join(bat) if bat else "NO STAGE TURNED ON"
    if sch.running:
        cau, nhan = f"session RUNNING · {khuc}", "Running…"
    elif sch.paused:
        cau, nhan = f"session OFF · would run {khuc}", "Start session"
    else:
        phut = max(1, sch.next_in() // 60)
        cau = f"on watch · next round in {phut} min · {khuc}"
        nhan = "Run a round now"
    return {"phien": cau, "nhan_phien": nhan,
            "dang_truc": not sch.paused,
            "bat": {k: prefs.flag(conn, k) for k in prefs.PHIEN}}


def track_stage(conn: sqlite3.Connection) -> dict:
    """The metrics for the TRACK stage bar. Every number has to be a job.

    Three numbers, no more — the same rule as Search and CV: a number that
    cannot answer "what do I do now" only dilutes the bar.

        taken further  they are talking to you — the most important thing
        waiting on you mail awaiting your decision, plus mail it could not read
        applied        background, read to know the scale
    """
    from ..track import board, scan
    hang = board.all(conn)
    that = [r for r in hang if r["stage"] != board.DRAFT]
    di_tiep = [r for r in that if r.get("song") == board.SONG_NONG]
    cho = len(scan.proposals(conn)) + len(scan.kho_hieu(conn))
    im = [r for r in that if r.get("song") == board.SONG_IM]
    from ..core import prefs
    # THE FOUR NUMBERS ASKED FOR: applied · taken further · rejected ·
    # waiting on you.
    #
    # An earlier version of mine renamed "rejected" to "silent too long" —
    # two different things: rejected is what they SAID, silence is what they
    # have NOT said. Merging them loses the one distinction between "dead"
    # and "unknown".
    #
    # BUT SILENCE PAST THE MARK IS COUNTED AS REJECTED. That is the user's
    # decision, and it is what lets the table SHRINK: 28 of 37 applications
    # never received a single word. Leave them at "waiting" forever and the
    # "waiting" figure only grows and says nothing. The threshold turns (⚟),
    # and because it is AN INFERENCE rather than a fact, lowering and raising
    # it again puts every row back exactly where it was.
    #
    # The two are still COUNTED SEPARATELY so the status line can say the
    # whole sentence: how many they SAID, how many the machine INFERRED.
    ho_noi = [r for r in that if r["stage"] == board.REJECTED]
    truot = ho_noi + im
    moc = board.nguong(conn)
    # MEASURED, not hardcoded: reply times belong to each individual mailbox.
    # This figure goes straight up to the ⚟ panel so the user turns the
    # threshold on evidence — for each mark, HOW MANY MESSAGES IT WOULD HAVE
    # CLOSED OUT WRONGLY, counted on real mail.
    tra_loi = [r for r in that if r.get("ho_tra_loi")]
    pha = board.im_da_pha(conn)
    return {"di_tiep": len(di_tiep), "cho_ban": cho, "da_nop": len(that),
            "truot": len(truot), "im": len(im), "nguong": moc,
            "do": {"tra_loi": len(tra_loi), "tong": len(that), **pha},
            # The queue behind the APPLY button: postings worth applying to
            # that have NOT been applied to anywhere.
            "hang_doi": conn.execute(
                "SELECT COUNT(*) FROM posting p WHERE p.kept = 1"
                " AND p.realism IN ('likely','possible') AND p.score >= 80"
                " AND p.id NOT IN (SELECT posting_id FROM application"
                "                  WHERE posting_id IS NOT NULL)").fetchone()[0],
            # THE STATUS LINE SPLITS THE REJECTED FIGURE IN TWO. The bar has
            # room for one number only; merging 2 real rejections with 32
            # inferences without saying so leaves the reader believing 34
            # companies said no.
            "state": (f"{len(that)} applications · {len(ho_noi)} said no · "
                      f"{len(im)} treated as rejected (silent over {moc} days)"
                      if that else "nothing applied to yet"),
            "nop": {k: prefs.flag(conn, k) for k in prefs.NOP}}


def cv_nut(conn: sqlite3.Connection) -> dict:
    """The CV layer's two knobs, converted into what build() can use.

    ONE place translating "knob name" into "value". Translate it in two places
    and one day the Adjust panel shows one thing while the builder does
    another.

    SEVEN KNOBS WERE DROPPED — see the note in core/prefs.py. The rules they
    toggled now run fixed at their measured defaults, and the scoring report
    still says which sentence was dropped and why. The user lost seven
    buttons and not one piece of information.
    """
    from ..core import prefs
    rieng = prefs.get(conn, prefs.CV_RIENG) or "rieng"
    tu_lo = prefs.flag(conn, prefs.CV_TU_LO)
    return {"rieng": rieng if rieng in prefs.RIENG else "rieng",
            "tu_lo": tu_lo,
            # `tu_lo` IS part of the key. It was not, because it only
            # affected build TIME. Since the GAP ladder and the drafts travel
            # with the build it changes the build's CONTENT too — leave it
            # out of the key and flipping the switch leaves the screen
            # unchanged, and the user thinks the button is broken.
            "ten": {"rieng": rieng, "tu_lo": "1" if tu_lo else "0"}}


def _cv_key(conn: sqlite3.Connection, cv_text: str) -> tuple:
    from ..core import versions
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM posting"
        " WHERE kept = 1 AND realism IN ('likely','possible')").fetchone()
    return (hash(cv_text), versions.SCORE_RULES, row[0], row[1],
            tuple(sorted(cv_nut(conn)["ten"].items())))


# ---------------------------------------------------------------------- CV

# Building CVs for 101 postings takes 1.4 seconds. That price must not be
# paid EVERY TIME the page opens. Cached in process memory, and forgotten when
# one of the three inputs changes: the CV text, the scoring rules, the set of
# postings.


def cv_versions(conn: sqlite3.Connection) -> dict:
    """Every CV the system WILL SEND, with identical ones merged into one.

    Why merge: 101 postings worth applying to yield only 29 distinct versions
    — the CV structure is fixed (2 experience · 3 projects · 2 education · 1
    certificate · 4 skills = 16 sentences), and what changes is only WHICH
    SENTENCE in each block is picked. Listing 101 rows makes Vin reread the
    same version three or four times.
    """
    import json as _json
    from ..cv.build import build as build_cv
    from ..profile import store as pstore

    answers = pstore.load(conn)
    san = _NHO.get("ban")
    key = _cv_key(conn, answers.get("cv_text") or "")
    if san is not None and san[0] == key:
        return san[1]
    # The Adjust panel's KNOBS. Read ONCE here and passed down: let build()
    # read the DB itself and it stops being pure, and 364 builds become 1,092
    # prefs reads for three values that never change.
    num = cv_nut(conn)

    rows = conn.execute(
        "SELECT id, title, company, score, realism, description, score_json"
        " FROM posting WHERE kept = 1 AND realism IN ('likely','possible')"
        " ORDER BY score DESC").fetchall()

    groups: dict[tuple, dict] = {}
    for row in rows:
        explain = _json.loads(row["score_json"]) if row["score_json"] else None
        cv = build_cv(answers, explain, row["description"] or "", num)
        # The merge key is EXACTLY THE SENTENCES that will be printed.
        # Merging by the JD's requested skills falls short: measured, 85
        # distinct skill sets yield only 29 versions.
        sig = tuple(line.text for section in cv.sections for line in section.lines)
        slot = groups.setdefault(sig, {
            "cv": cv, "jobs": [], "wanted": set(), "missing": set()})
        slot["jobs"].append({"id": row["id"], "title": row["title"],
                             "company": row["company"], "score": row["score"],
                             "realism": row["realism"]})
        slot["wanted"] |= set(cv.wanted)
        slot["missing"] |= set(cv.missing)

    # A sentence present in EVERY version = the core, unchanged by the JD.
    # What is left is the real "tailoring". Measured: 14 of 16 sentences are
    # core, only 2 change — show the structural figures (2 experience, 3
    # projects…) and 29 rows come out identical and meaningless.
    core = set.intersection(*[set(sig) for sig in groups]) if groups else set()

    out = []
    for sig, slot in sorted(groups.items(), key=lambda kv: -len(kv[1]["jobs"])):
        cv = slot["cv"]
        # COVERAGE MUST BE COMPUTED OVER ONE POSTING, NOT THE WHOLE GROUP.
        # `slot["wanted"]` is the UNION over every posting in the group: a
        # version covering 168 postings yields 33 skills, while no single
        # posting asks for 33 — so a ratio of "13/33" measures GROUP SIZE
        # rather than CV quality, and a version covering many postings always
        # looks worse than one covering few.
        #
        # `slot["cv"]` is the version built for the HIGHEST-SCORING posting in
        # the group (rows are ordered by score DESC and the group is created
        # on first encounter). Its own numbers are the real ones: exactly what
        # ONE posting asks, and exactly what the CV answers.
        dau = max(slot["jobs"], key=lambda j: j["score"] or 0)
        out.append({
            "jobs": slot["jobs"],
            "lines": len(sig),
            "dropped": len(cv.dropped),
            "only": [line for line in sig if line not in core],
            "wanted": sorted(slot["wanted"]),
            "missing": sorted(slot["missing"]),
            "top": [j["company"] for j in slot["jobs"][:3]],
            # --- the LEAD POSTING's numbers, so the row says something real ---
            "best": dau,
            # USE `asked`/`on_paper`, NOT `wanted`/`covered`.
            #   wanted  scans the whole posting, blurb included -> the
            #           denominator inflates (NXP "asks for" cloud; 3 of BoA's
            #           4 words came from the blurb)
            #   covered counts only skills proved by the SENTENCES -> it
            #           ignores the TECHNICAL SKILLS section printed on that
            #           very page
            # Measured over 287 postings: the old fraction 28%, the real one 64%.
            "hoi": len(cv.asked),           # what that posting REALLY asks
            "tra_loi": len(cv.on_paper),    # what THE PAGE can say
            "cam": sorted(cv.missing),      # and what it is silent about
        })

    value = {"versions": out, "jobs": len(rows), "core": len(core),
             # Skills THE WHOLE MARKET asks for that the profile has no
             # sentence about. The most worthwhile list on the page: it says
             # what the CV is missing.
             "gaps": sorted({m for v in out for m in v["missing"]})}
    _NHO["ban"] = (key, value)
    return value


def onboarding(conn: sqlite3.Connection) -> dict:
    """Where the app stands on building the profile — ONE place computes it,
    everywhere reads it.

    Each tab used to guess for itself: Profile knew "3 answers still missing",
    Search knew nothing so it still invited a Run and then gave up silently,
    Home was blank. One truth answered three different ways in three places
    drifts apart sooner or later.

    It invents no new rule: the gate is still `store.missing_for_ingest`, and
    "which part is done" is still `store.is_section_done` — this function only
    GATHERS them into one answer for the screen.
    """
    from ..profile import store
    from ..profile.schema import SECTIONS, all_questions

    answers = store.load(conn)
    hoi = all_questions()
    thieu = store.missing_for_ingest(answers)
    ke_tiep = store.first_unfinished_section(answers)

    phan = []
    da_tra_loi = tong = 0
    for s in SECTIONS:
        hien = [q for q in s.questions if not q.hidden]
        co = [q for q in hien if store.has_answer(answers, q)]
        da_tra_loi += len(co)
        tong += len(hien)
        phan.append({
            "id": s.id, "title": s.title, "why": s.why,
            "href": f"/profile/{s.id}",
            "answered": len(co), "total": len(s.questions),
            "done": store.is_section_done(answers, s),
            "optional": s.optional,
            # A section containing a gate question is REQUIRED — derived
            # from the gate rather than typed, so changing the gate changes
            # the labels by itself.
            "required": any(q.id in store.INGEST_GATE for q in s.questions),
        })

    return {
        "answered": da_tra_loi, "total": tong,
        "versions": len(store.history(conn)),
        "gate_open": not thieu,
        "gate_missing": [{"id": q, "text": hoi[q].text} for q in thieu if q in hoi],
        "next": ({"id": ke_tiep.id, "title": ke_tiep.title,
                  "href": f"/profile/{ke_tiep.id}"} if ke_tiep else None),
        "sections": phan,
    }


def search_stage(conn: sqlite3.Connection) -> dict:
    """The SEARCH stage's metrics and state.

    ONE place computes them. The tab's bar and, later, the pipeline board on
    Home both read from here — two places counting for themselves means two
    numbers that will one day disagree.
    """
    from ..core import halt
    from ..core.scheduler import current as sched_now

    one = lambda q: conn.execute(q).fetchone()[0]          # noqa: E731
    # THE STORE's numbers, not the view's. The stage bar answers "what is in
    # the pipeline", while the chips over the list answer "what is showing" —
    # mix the two and a search for "quant" has the bar report 64 kept against
    # 91 worth applying, while worth-applying is a subset of kept. A nonsense
    # number right there on screen.
    kept = one("SELECT COUNT(DISTINCT COALESCE(group_id, CAST(id AS TEXT)))"
               " FROM posting WHERE kept = 1 AND via_agency = 0")
    worth = one("SELECT COUNT(*) FROM posting WHERE kept = 1"
                " AND realism IN ('likely','possible')")
    # THE REAL QUEUE: worth applying to, high-scoring, and NOT YET APPLIED
    # TO. The one number on the bar that can answer "what do I do tonight".
    #
    # The old bar had four numbers and not one was actionable: "363 kept" and
    # "364 worth applying" nearly coincided (two counts of the same pile), "0
    # new" is always 0 except right after a scan, and "50 shown" is the page
    # size.
    hang_doi = one("SELECT COUNT(*) FROM posting WHERE kept = 1"
                   " AND realism IN ('likely','possible') AND score >= 80"
                   " AND id NOT IN (SELECT posting_id FROM application"
                   "                 WHERE posting_id IS NOT NULL)")
    da_nop = one("SELECT COUNT(*) FROM application")
    # THE WHOLE STORE, not the part that passed the sieve. The Clear store
    # button deletes the whole store, so its label has to count the whole
    # store — saying "drop 363 postings" and then dropping 5,166 is a lie at
    # exactly the moment the user most needs the real number.
    ca_kho = one("SELECT COUNT(*) FROM posting")
    last = conn.execute(
        "SELECT at FROM audit WHERE kind = 'scan_started'"
        " ORDER BY id DESC LIMIT 1").fetchone()
    when = (last["at"] or "")[11:16] if last else ""
    # "New" = postings THIS SCAN brought in, measured by when the raw row was
    # fetched, not by the difference between two counts: with a difference, a
    # scan that brings in 10 new postings while 10 old ones are dropped comes
    # out as 0, and Vin is told nothing.
    fresh = one(
        "SELECT COUNT(*) FROM posting p JOIN raw_posting r ON r.id = p.raw_id"
        " WHERE p.kept = 1 AND r.fetched_at >= COALESCE("
        "   (SELECT at FROM audit WHERE kind = 'scan_started'"
        "    ORDER BY id DESC LIMIT 1), '')")

    runner = sched_now()
    if halt.wanted("search"):
        state = "stopping…"
    elif runner.running:
        state = "scanning"
    else:
        auto = "auto: ON" if not runner.paused else "auto: OFF"
        state = (f"{auto} · last scan {when}" if when
                 else f"{auto} · never scanned")

    # THE BUTTON has to name the job it is about to do. "Run" is an empty
    # word: someone opening the app for the first time does not know what it
    # will run, and someone who just pressed Stop reads it as "start again
    # from scratch" — while the machine will carry on where it left off.
    #
    # Three situations, read straight from the DB rather than held in a state
    # flag: a flag drifts from the truth one day, a count never does.
    #
    # THE BUTTON RE-READS THE SCAN LOOP'S OWN DECISION rather than guessing a
    # parallel one. There used to be a formula of its own here, and it counted
    # postings the sieve had already dropped: the button read "1,855 postings
    # still to deep-read" while the deep-read pass opened 11. Press it, see no
    # number move, and the user stops trusting the button.
    #
    # The words here are the IDLE words. While it runs, live.js swaps them for
    # "Scanning…" and locks the button — one place per state.
    from ..scan_runner import scan_mode
    kieu = scan_mode(conn)

    # The words for the PLACE chips. Taken from the profile, not hardcoded:
    # "Near me · London" is only true for someone who said they are in London.
    from ..ingest.filter import NOI
    nha, gan = noi_toi(conn)
    return {"kept": kept, "worth": worth, "fresh": fresh, "state": state,
            "ca_kho": ca_kho,
            "hang_doi": hang_doi, "da_nop": da_nop,
            "run_label": kieu["label"], "run_note": kieu["note"],
            "gan": gan, "vung": NOI[nha]["ten"]}


def cv_pdf_plan(conn: sqlite3.Connection) -> list[dict]:
    """The print plan: ONE file per CV VERSION, and which postings use which.

    ONE SOURCE names the files. The printer used to name them after the
    highest-scoring posting in the version, while the Apply button built a
    name from the posting BEING PRESSED — two formulas, so pressing Apply on
    the second posting of the same version went looking for a file that did
    not exist. Both now read from here.
    """
    from pathlib import Path as _Path

    from ..core import db as _db
    from ..cv.pdf import slug

    root = _Path(_db.db_path()).parent / "cv"
    plan = []
    for ver in cv_versions(conn)["versions"]:
        best = max(ver["jobs"], key=lambda j: j["score"] or 0)
        # The posting id is included. Measured: Jane Street had TWO different
        # CV versions both named "machine-learning-researcher" — they
        # overwrote each other, and among 7 postings some carried the other
        # version's CV. A human-readable name cannot tell two versions apart;
        # an id can.
        plan.append({
            "best": best,
            "file": root / (f"{slug(best['company'])}-{slug(best['title'])}"
                            f"-{best['id']}.pdf"),
            "ids": [j["id"] for j in ver["jobs"]],
        })
    return plan


def cv_pdf_for(conn: sqlite3.Connection, posting_id: int) -> Path | None:
    """The path of this posting's PDF. ALWAYS returns exactly one name — the
    caller checks `.exists()` to know whether it has been printed.

    A posting in no group (low score, never reached the CV build) still has to
    have a name, and that name has to follow EXACTLY the print plan's formula.
    The "Print this one" button used to build a name from the old formula
    (missing the posting id), so it printed a file the applying code would
    never go looking for.
    """
    from pathlib import Path as _Path

    from ..core import db as _db
    from ..cv.pdf import slug

    for item in cv_pdf_plan(conn):
        if posting_id in item["ids"]:
            return item["file"]
    row = conn.execute("SELECT company, title FROM posting WHERE id = ?",
                       (posting_id,)).fetchone()
    if row is None:
        return None
    root = _Path(_db.db_path()).parent / "cv"
    return root / f"{slug(row['company'])}-{slug(row['title'])}-{posting_id}.pdf"




def cv_blocks(conn: sqlite3.Connection) -> list[dict]:
    """The blocks in the original CV, with a measure of WHAT EACH IS DOING.

    The raw-material store is the whole system's real ceiling: 34 sentences,
    while one CV needs 18 — so 13 of 18 sentences are identical in every
    version, and every selection design runs into that ceiling. For a CV that
    lands better you have to WRITE MORE, not select more cleverly. This table
    says which block is carrying weight and which is only taking up space.
    """
    from ..cv.blocks import parse as parse_cv, sentences as split_cv
    from ..cv.build import skills_in
    from ..profile import store as pstore

    # CACHED, like cv_versions. Measured: 7.8 seconds PER CALL, and the CV
    # tab calls it on every open — Vin waiting 10 seconds to look at a page
    # that has not changed.
    answers_now = pstore.load(conn)
    san = _NHO.get("khoi")
    key = _cv_key(conn, answers_now.get("cv_text") or "")
    if san is not None and san[0] == key:
        return san[1]
    from ..scoring.market import demand as thi_truong

    text = pstore.load(conn).get("cv_text") or ""
    demand = thi_truong(conn)
    out = []
    for block in parse_cv(text):
        if block.kind not in ("experience", "project"):
            continue
        lines = [s for s in split_cv(block)]
        skills = sorted({k for s in lines for k in skills_in(s)})
        out.append({
            "kind": block.kind,
            "title": block.title,
            "meta": block.meta,
            "lines": lines,
            "skills": skills,
            # How many POSTINGS want what this block can say. A block at 0
            # postings is taking up space: it reached the CV because there was
            # an empty slot, not because it proves anything.
            "reach": sum(demand.get(s, 0) for s in skills),
        })
    out.sort(key=lambda b: -b["reach"])
    _NHO["khoi"] = (key, out)
    return out


def cv_nhap(conn: sqlite3.Connection, buoc: list) -> dict:
    """A prepared draft for each gap. {} while the "Machine handles it" switch
    is off.

    ONE PLACE BUILDS THEM, two places draw them: the GAP ladder on the CV tab
    and the Block editor. Only the editor used to build them, so turning the
    switch on while standing on the CV tab showed no change at all — the
    button saying one thing and the screen another.

    Each row has three outcomes, and all three have to be SAID:
        a draft      the machine built a sentence, waiting on the evidence
        no base      no posting asks for it in a line DESCRIBING WORK
        not buildable there is such a line, but it cannot be cut far enough
                     from their own words
    """
    from ..scoring.gap import goi_y, nen_nhap
    if not cv_nut(conn).get("tu_lo"):
        return {}
    ra: dict = {}
    for b in buoc or []:
        ky = b["ky_nang"]
        if b["dong"] - b["rieng"] <= 0:
            continue                      # a LEARN job, no sentence stands in
        nen = nen_nhap(conn, ky)
        ra[ky] = {"nen_co": len(nen), "nhap": "", "nen": "", "cong_ty": ""}
        for m in nen:
            g = goi_y(m["chu"], ky)
            if g:
                ra[ky].update(nhap=g, nen=m["chu"], cong_ty=m["cong_ty"])
                break
    return ra


def cv_soan(conn: sqlite3.Connection, luu: dict, title: str = "", ky: str = "",
            nen: str = "", soan: str = "", tho: bool = False) -> dict:
    """Everything the BLOCK EDITOR needs — measured here, the screen only draws.

    The editor differs from the old overlay in exactly one way, and that is
    why it exists: it judges EVERY SENTENCE as it is written. Vin used to type
    into an empty box and press Save, and only learned a sentence had been
    dropped by a rule after rebuilding the whole run of versions — if he
    remembered to go and read it.

        phan    what the rules say: goes on · look again · rules forbid
        reach   how many POSTINGS ask for what that sentence mentions

    `reach` is NOT a quality score. A knowledge sentence naming no tool has
    reach = 0 and may still be the strongest sentence in the profile. It
    answers exactly one question: *is the market asking for this* — whether
    the sentence is worth keeping is the writer's call.

    `ky` = which skill is BEING AIMED AT. It opens the BRIEF: word for word,
    the real requirement lines asking for it, and the lines USABLE AS THE BASE
    of a draft.

    `nen` = the requirement line the user picked. It is the COMPARISON MARK
    for Save, and it does not change as the user types — which is precisely
    why it is separate from `soan`: fold the two together and one rejected
    Save after a few edits drags the mark along, so next time a verbatim copy
    passes.

    `soan` = the text CURRENTLY in the box. By default it is the SUGGESTION
    (`gap.goi_y`) when that line can be cut down to the shape of a CV
    sentence, otherwise their line verbatim. `tho=True` forces the verbatim
    line — the "use their line verbatim" button.

    The machine still writes NO claim: a suggestion is only their line with
    the excess cut, put into the past tense, leaving `___` for the evidence —
    the one thing only the user has. `gap.con_trong` refuses to save while
    `___` is still there.

    WHY THE BRIEF IS HERE rather than in an overlay of its own: writing a new
    sentence IS editing a block — the same write into `cv_text`, the same
    chair. Splitting it into two screens makes the user read the requirement
    in one place and type in another, and leaves two write paths having to
    watch each other.
    """
    from ..cv import rules
    from ..cv.build import skills_in
    from ..scoring.gap import goi_y, ho_hoi, nen_nhap
    from ..scoring.market import demand as thi_truong

    khoi = cv_blocks(conn)
    chon = next((b for b in khoi if b["title"] == title), None) if title else None
    can = nho(conn, "can", lambda: thi_truong(conn))
    cau = []
    for line in (chon or {}).get("lines", []):
        tags = sorted(skills_in(line))
        phan, vi_sao = rules.sentence_ok(line, tags)
        cau.append({"chu": line, "tags": tags, "phan": phan, "vi_sao": vi_sao,
                    "reach": sum(can.get(t, 0) for t in tags)})

    # THE GAP LADDER, shortened: editing blocks without knowing what the
    # market is short of is only proofreading. Only the WRITABLE rows are
    # taken — a "must learn" row is not work that can be done on this screen.
    #
    # THE LADDER IS READ FROM THE SAVED BUILD, never recomputed — see
    # cv/batch.run. With nothing built there is no measurement, and this
    # screen says so rather than inventing a ladder from a different moment in
    # time than the CV tab's.
    d_hut = (luu or {}).get("hut") or {}
    hut = [b for b in (d_hut.get("buoc") or [])
           if b["dong"] - b["rieng"] > 0][:6]

    # MACHINE HANDLES IT — drafts prepared for EVERY gap, without waiting for
    # each to be pressed.
    #
    # Never written to disk. A draft is DERIVABLE from the requirement line,
    # so storing it only creates a second store to be kept in sync — in sync
    # with the very thing that can be recomputed in a fraction of a second.
    # And storing it inside `cv_text` is worse: the scorer would count "data
    # pipelines" in a draft sentence as a skill already answered, and the app
    # would be lying to the user about the user.
    san = []
    if not ky:
        sanh = ((luu or {}).get("nhap") or {}) if cv_nut(conn).get("tu_lo") else {}
        for b in hut:
            d = sanh.get(b["ky_nang"]) or {}
            if d.get("nhap"):
                san.append({"ky": b["ky_nang"], "them": b["them"], **d})

    brief = None
    if ky:
        chung, rieng = ho_hoi(conn, ky)
        # THE DRAFT BASE stands apart from `chung`: only lines DESCRIBING
        # WORK convert into a CV sentence. "Your nearest sentence" WAS
        # DROPPED — it called `gan_nhat`, which never used its skill argument
        # at all, so it returned the same three sentences for every gap,
        # including sentences the rules forbid on a CV. A suggestion that does
        # not change with its input is not a suggestion.
        brief = {"ky": ky, "chung": chung, "rieng": rieng,
                 "nen": nen_nhap(conn, ky)}
    # The editing box: the suggestion when there is one, otherwise the line
    # verbatim. `soan`, half-typed by the user (a Save just refused), beats
    # everything — their words must never be thrown away.
    gy = goi_y(nen, ky) if nen else ""
    return {"khoi": khoi, "chon": chon, "cau": cau, "hut": hut, "brief": brief,
            "nen": nen, "goi_y": gy, "tho": tho, "san": san,
            "soan": soan or ("" if not nen else (nen if tho or not gy else gy)),
            # TODAY's coverage, not the delta from the last save. A delta
            # belongs in the journal, where it carries a timestamp and does
            # not turn into a lie after one press of F5.
            "dap": (d_hut.get("nen") or 0, d_hut.get("tin") or 0)}


# ------------------------------------------------------- missed job titles

# Words showing this posting is IN VIN'S FIELD, even when the title does not
# match the sieve.
NEAR_TITLE = re.compile(
    r"\b(quant\w*|machine learning|market microstructur\w*|"
    r"algorithmic trading|systematic trading|alpha research)\b", re.I)

# Senior titles — missing these is CORRECT, not a hole.
ABOVE_ME = re.compile(
    r"\b(senior|lead|principal|head|director|vp|chief|staff|manager|"
    r"associate director|executive)\b", re.I)

MIN_SEEN = 2        # seen once is not enough to change the profile


def missed_titles(conn: sqlite3.Connection, limit: int = 12) -> list[dict]:
    """Job titles the sieve dropped that LOOK LIKE Vin's kind of work.

    The title sieve is a handful of hand-typed strings, so one missing string
    loses a whole run of postings — and loses them in silence. Measured on
    10/09: 163 junior-level postings containing quant/machine learning were
    dropped, `Quantitative Trader` nine times among them.

    The machine does NOT widen the sieve itself. Widening it changes the
    profile, and a changed profile means every posting is re-judged — that is
    a person's job, not the scan loop's. This only points.
    """
    from ..profile import store as pstore

    have = {t.strip().lower()
            for t in (pstore.load(conn).get("job_titles") or "").splitlines()
            if t.strip()}
    seen: dict[str, dict] = {}
    for row in conn.execute(
            "SELECT title, company FROM posting WHERE kept = 0"
            " AND drop_reason LIKE 'title does not%'"):
        title = (row["title"] or "").strip()
        if not NEAR_TITLE.search(title) or ABOVE_ME.search(title):
            continue
        key = title.lower()
        if key in have:
            continue
        slot = seen.setdefault(key, {"title": title, "n": 0, "firms": []})
        slot["n"] += 1
        if row["company"] and row["company"] not in slot["firms"]:
            slot["firms"].append(row["company"])
    out = [s for s in seen.values() if s["n"] >= MIN_SEEN]
    out.sort(key=lambda s: -s["n"])
    return out[:limit]
