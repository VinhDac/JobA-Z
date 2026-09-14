"""The derived layer — recomputable, only recomputes what is stale, and it is
ONE transaction.

The architecture:

    raw_posting   exactly what was fetched. NEVER edited.
    posting       normalised + judged. Fully recomputable from raw.

Three properties that must hold:

1. **Recomputable.** `rebuild()` rebuilds every judgement from raw. Without
   it, one bug in the rules is damage that never goes away.

2. **Versioned.** Every judgement records which profile version and which
   rule version produced it. Change the profile or the rules and old
   postings become stale automatically, not silently.

3. **One transaction.** A web request reading half-way through must see the
   whole OLD state, never a half-built one.
"""

from __future__ import annotations

import json
import sqlite3

from ..dedup import group
from ..ingest import filter as jobfilter
from ..ingest.base import Posting
from ..ingest.web.agency import judge as judge_agency
from ..profile import store
from ..scoring.realism import assess, find_deadline
from ..scoring.score import score_job
from . import versions
from .journal import SCORE, log as jlog


def _row_to_posting(row: sqlite3.Row) -> Posting:
    return Posting(source_id="", title=row["title"], company=row["company"],
                   location=row["location"], remote=bool(row["remote"]),
                   description=row["description"] or "")


def stale_count(conn: sqlite3.Connection) -> int:
    """How many postings carry a stale judgement — FILTERING or SCORING.

    Counting only the filter half is a lie: change SCORE_RULES and every
    score is stale while the screen still says "nothing to recompute".
    """
    pv = store.latest_version_id(conn) or 0
    return int(conn.execute(
        "SELECT COUNT(*) FROM posting"
        " WHERE judged_profile != ? OR judged_rules != ?"
        "    OR (kept = 1 AND (scored_rules != ? OR scored_profile != ?))",
        (pv, versions.FILTER_RULES, versions.SCORE_RULES, pv)).fetchone()[0])


def derive(conn: sqlite3.Connection, force: bool = False,
           log=lambda _m: None) -> dict:
    """Re-judge stale postings. Returns the counts."""
    answers = store.load(conn)
    profile_version = store.latest_version_id(conn) or 0

    if force:
        rows = conn.execute("SELECT * FROM posting").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM posting WHERE judged_profile != ? OR judged_rules != ?",
            (profile_version, versions.FILTER_RULES)).fetchall()

    # Python's sqlite3 opens a transaction on the first write and holds it
    # until commit(). So simply NOT committing in the middle makes this whole
    # block one transaction.
    try:
        judged = kept = agencies = 0
        for index, row in enumerate(rows, 1):
            if index % 25 == 0 or index == len(rows):
                jlog.progress(SCORE, "filtering", index, len(rows))
            item = _row_to_posting(row)
            keep, reason = jobfilter.judge(item, answers)
            # THE HUMAN OVERRIDES THE MACHINE. This is the ONLY place that
            # knows it, so Vin's decision survives every recompute —
            # including across a profile change or a filter-rule change,
            # which is exactly when a manual fix would otherwise be eaten.
            #
            # Keeps the old invariant: empty drop_reason <=> the posting is
            # kept. Why it is in the list is what the "you kept this" badge
            # says; do not overload drop_reason with a second meaning.
            if row["user_keep"]:
                keep, reason = True, ""
            is_agency, _ = judge_agency(row["company"], row["description"] or "")
            conn.execute(
                "UPDATE posting SET kept=?, drop_reason=?, via_agency=?,"
                " judged_profile=?, judged_rules=? WHERE id=?",
                (int(keep), "" if keep else reason, int(is_agency),
                 profile_version, versions.FILTER_RULES, row["id"]))
            if not keep:
                # A dropped posting has its old score DELETED. Leave it and
                # it keeps a number produced by old rules, with no version,
                # which is never recomputed because the scoring pass only
                # runs over kept postings.
                # Do NOT add "score IS NOT NULL": a posting scored with
                # confidence 'none' has score=NULL but still carries a stale
                # realism and scored_rules.
                conn.execute(
                    "UPDATE posting SET score=NULL, score_conf='', score_json='',"
                    " scored_rules='', scored_profile=0, realism='', realism_why='',"
                    " deadline='', deadline_ts=0 WHERE id=?", (row["id"],))
            judged += 1
            kept += int(keep)
            agencies += int(is_agency)

        jlog.progress(SCORE, "grouping duplicates")
        n_rows, n_groups = group.regroup(conn, commit=False)

        # Scoring depends on BOTH the scoring rules AND the profile
        # (score_job reads answers), so stale on either side means rescore.
        # scored_rules='' != SCORE_RULES, so a never-scored posting is
        # already covered by this condition.
        # force has to reach here too — otherwise a posting scored while its
        # description was still empty stays at score=NULL even under
        # derive(force=True).
        to_score = conn.execute(
            "SELECT id, title, description FROM posting WHERE kept = 1"
            + ("" if force else
               " AND (scored_rules != ? OR scored_profile != ?)"),
            () if force else (versions.SCORE_RULES, profile_version)).fetchall()
        scored = 0
        for index, row in enumerate(to_score, 1):
            if index % 25 == 0 or index == len(to_score):
                jlog.progress(SCORE, "scoring", index, len(to_score))
            text = row["description"] or ""
            result = score_job(row["title"], text, answers)
            # "does it match" and "do you stand a chance" are two different
            # questions — computed separately
            chance = assess(row["title"], text, result, answers)
            deadline, deadline_ts = find_deadline(text)
            conn.execute(
                "UPDATE posting SET score=?, score_conf=?, score_json=?, scored_rules=?,"
                " scored_profile=?, realism=?, realism_why=?, deadline=?, deadline_ts=?"
                " WHERE id=?",
                (result["score"], result["confidence"],
                 json.dumps(result, ensure_ascii=False), versions.SCORE_RULES,
                 profile_version, chance["band"], chance["why"],
                 deadline, deadline_ts, row["id"]))
            scored += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # The counts must be the CURRENT totals, not what this pass judged.
    # Nothing stale -> judged=0, and reporting "keeping 0" reads as "all the
    # data is gone".
    totals = conn.execute(
        "SELECT COUNT(*) AS n, SUM(via_agency) AS ag FROM posting WHERE kept = 1"
    ).fetchone()
    kept_total = totals["n"] or 0
    agency_total = totals["ag"] or 0

    jlog.done(SCORE)
    if judged or scored:
        jlog.ok(SCORE, f"re-judged {judged} · scored {scored} · keeping "
                       f"{kept_total} · {n_groups} distinct jobs")
    log(f"  derive: re-judged {judged} · keeping {kept_total} "
        f"({agency_total} agency) · {n_groups} distinct jobs · scored {scored}")
    return {"judged": judged, "kept": kept_total, "agencies": agency_total,
            "kept_new": kept, "groups": n_groups, "scored": scored}


def rebuild(conn: sqlite3.Connection, log=lambda _m: None) -> dict:
    """Rebuild the WHOLE derived layer from the raw layer.

    Use it after changing rules, changing the HTML stripper, or whenever the
    derived data looks wrong. Nothing is lost: raw is untouched.
    """
    from ..ingest.base import strip_html
    rows = conn.execute(
        "SELECT p.id, r.body FROM posting p JOIN raw_posting r ON p.raw_id = r.id"
        " WHERE length(COALESCE(r.body,'')) > 0").fetchall()
    conn.executemany("UPDATE posting SET description = ? WHERE id = ?",
                     [(strip_html(r["body"])[:20000], r["id"]) for r in rows])
    conn.execute("UPDATE posting SET judged_rules = '', scored_rules = ''")
    conn.commit()
    log(f"  re-extracted descriptions from raw: {len(rows)} postings")
    return derive(conn, force=True, log=log)
