"""Build the WHOLE BATCH of CV versions — and SAVE it, because it costs 5s.

WHY IT HAS TO BE SAVED. Measured on the real store: building CV versions for
364 worthwhile postings takes 5.3 seconds. The CV tab used to call it during
the page render, so opening the tab meant waiting 5 seconds — waiting to see
something you had not asked for. Someone who just finished a search is
nowhere near making a CV; throwing 28 versions at them is the wrong beat.

So it works like Search: IT RUNS WHEN YOU PRESS IT. It saves when done, and
opening the tab shows it instantly.

THE FRESHNESS STAMP HAS TO BE STABLE ACROSS RUNS. `live._cv_key` uses
`hash(str)` — Python re-salts that per process, so it is correct for an
in-memory cache and completely wrong for a stamp written to disk: restart the
app and the stamp changes, and a build finished a second ago is suddenly
stale. This uses sha1.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict

from ..core import versions
from ..core.journal import CV, log as jlog


def stamp(conn: sqlite3.Connection, cv_text: str) -> str:
    """The stamp over EVERYTHING a build depends on.

    Five components, and leaving any one out leaves a wrong path open:
        the CV text   edit a block and the old build stays, button unchanged
        writing rules change rules.py without rebuilding and the old build
                      follows the old rules
        scoring rules change the score and "what they ask" changes, so the
                      build has to change
        the posting set  new postings scanned means new versions to build
        the knobs     turn a knob while the button still says "Rebuild" and
                      the knob is decoration
    """
    from ..dashboard.live import cv_nut
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM posting"
        " WHERE kept = 1 AND realism IN ('likely','possible')").fetchone()
    num = cv_nut(conn)["ten"]
    thanh_phan = (hashlib.sha1(cv_text.encode("utf-8")).hexdigest()[:16],
                  versions.CV_RULES, versions.SCORE_RULES,
                  str(row[0]), str(row[1]),
                  ",".join(f"{k}={v}" for k, v in sorted(num.items())))
    return "|".join(thanh_phan)


def _phang(o):
    """dataclass -> dict. Line/Section/Sua/Yeu are nested dataclasses."""
    try:
        return asdict(o)
    except TypeError:
        return str(o)


def save(conn: sqlite3.Connection, payload: dict, dau: str) -> None:
    """Save the build. EXACTLY ONE ROW — the table has CHECK(id = 1).

    No history: the "before" in a comparison is Vin's ORIGINAL CV, not the
    previous build. Keeping history here is keeping what nobody reads.
    """
    from ..core.postings import now
    conn.execute(
        "INSERT INTO cv_build (id, made_at, stamp, payload) VALUES (1, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET made_at = excluded.made_at,"
        " stamp = excluded.stamp, payload = excluded.payload",
        (now(), dau, json.dumps(payload, default=_phang)))
    conn.commit()


def saved(conn: sqlite3.Connection) -> dict | None:
    """The saved build, or None if nothing has been built."""
    row = conn.execute(
        "SELECT made_at, stamp, payload FROM cv_build WHERE id = 1").fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row["payload"])
    except (TypeError, ValueError):
        return None                   # a corrupt row counts as never built
    data["made_at"] = row["made_at"]
    data["stamp"] = row["stamp"]
    return data


def xoa(conn: sqlite3.Connection) -> int:
    """Throw the build away. Returns how many versions went.

    IT ONLY TOUCHES WHAT THE MACHINE MADE. `cv_text` — the user's own words —
    is not touched at all, so deleting by mistake costs one press of Run.
    That is also why the confirmation here is lighter than /api/reset's: that
    one deletes what cannot be rebuilt.
    """
    cu = len((saved(conn) or {}).get("versions") or [])
    conn.execute("DELETE FROM cv_build")
    conn.commit()
    return cu


def stage(conn: sqlite3.Connection) -> dict:
    """What the NEXT build will do. ONE place decides; the Run button only
    reads it back to name itself.

        Run       never built
        Update    built, but the CV text / rules / posting set have changed
        Rebuild   in sync — pressing it is allowed, there is just nothing new

    A button that guesses one thing while the machine does another is a
    button that lies.
    """
    from ..profile import store as pstore
    answers = pstore.load(conn)
    cv_text = answers.get("cv_text") or ""
    co_cv = bool(cv_text.strip())
    dang = conn.execute(
        "SELECT COUNT(*) FROM posting WHERE kept = 1"
        " AND realism IN ('likely','possible')").fetchone()[0]

    cu = saved(conn)
    ban = len((cu or {}).get("versions") or [])
    chung = {"kept": ban, "worth": dang, "state": "nothing built yet"}

    if not co_cv:
        # No CV means nothing can be built. Say so, rather than offering a
        # button that does nothing when pressed.
        return {**chung, "mode": "chua_cv", "label": "Run", "todo": 0,
                "note": "the profile has no CV — paste one on the Profile tab first"}
    if not dang:
        return {**chung, "mode": "chua_tin", "label": "Run", "todo": 0,
                "note": "no posting is worth applying to yet — run Search first"}
    if cu is None:
        return {**chung, "mode": "dau", "label": "Run", "todo": dang,
                "note": f"never built — building versions for {dang:,} worthwhile postings"}

    moi = stamp(conn, cv_text)
    xong = f"{ban} versions · built at {str(cu.get('made_at') or '')[11:16]}"
    if cu.get("stamp") != moi:
        vi_sao = _vi_sao_cu(cu.get("stamp") or "", moi)
        return {**chung, "mode": "moi", "label": "Update", "todo": dang,
                "state": xong, "note": f"what you have is stale — {vi_sao}"}
    return {**chung, "mode": "khop", "label": "Rebuild", "todo": 0,
            "state": xong, "note": "what you have is still in sync — rebuilding gives the same"}


def _vi_sao_cu(cu: str, moi: str) -> str:
    """Stale because of WHAT. A bare "stale" leaves the user with no idea
    what they just changed."""
    a, b = cu.split("|"), moi.split("|")
    if len(a) != len(b):
        return "the build rules changed"
    ten = ("the CV text was edited", "the CV writing rules changed",
           "the scoring rules changed", "the set of worthwhile postings changed",
           "new postings arrived", "you turned a knob on the Adjust panel")
    doi = [ten[i] for i in range(len(b)) if a[i] != b[i]]
    return " · ".join(doi) or "the inputs changed"


def run(conn: sqlite3.Connection, log=None) -> dict:
    """Build every version and save it. This is what Run calls, in the
    BACKGROUND.

    Returns the build it just saved, so the caller need not re-read the disk.
    """
    say = log or (lambda _m: None)
    from ..profile import store as pstore
    answers = pstore.load(conn)
    cv_text = answers.get("cv_text") or ""
    if not cv_text.strip():
        jlog.warn(CV, "no CV in the profile — nothing can be built")
        return {}

    jlog.emit(CV, "building CV versions — reading each posting, asking the "
                  "profile what it can answer")
    from ..dashboard import live
    live.quen()            # force a real build, not the in-memory copy
    data = live.cv_versions(conn)
    # THE GAP LADDER AND THE DRAFTS TRAVEL WITH THE BUILD; they are not
    # recomputed during a page render.
    #
    # They used to be computed on every page load, which turned the CV tab
    # into two clocks showing different times: edit a block and the "what to
    # write to close the gap" panel updated at once while "what will be sent"
    # was still the old build. Delete the build and the other panel was still
    # full, so "delete everything" did not. One input, one measurement, one
    # expiry.
    data["hut"] = live.cv_hut(conn)
    data["nhap"] = live.cv_nhap(conn, data["hut"].get("buoc"))
    dau = stamp(conn, cv_text)
    save(conn, data, dau)

    n_ban = len(data.get("versions") or [])
    n_tin = sum(len(v.get("jobs") or []) for v in data.get("versions") or [])
    tom = f"{n_ban} versions for {n_tin:,} postings"
    jlog.ok(CV, f"build finished — {tom}")
    jlog.done(CV)
    say(f"  CV: {tom}")
    return data
