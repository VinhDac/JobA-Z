"""Store and read job postings. Four separated layers (design.md §4).

    raw_posting  exactly what was fetched — never touched, refetchable
    posting      normalised — recomputable from raw
    source_run   one row per source run: how many, what broke
    audit        what was done and when — the source of every later statistic

The cache is UNIQUE(source, source_id): a posting already there is not
written again, so re-running a source many times produces no junk and costs
no processing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from ..ingest.base import Posting, to_ts


# The ONE place that maps the Posting type onto table columns.
#
# The INSERT used to be hand-written, listing column names and values in two
# separate places, so adding a field to Posting meant editing three places
# with nothing to warn you if you forgot. Now only this table changes — and
# a test fails if Posting grows a field nobody declared.
FIELD_MAP: dict[str, str] = {
    "title": "title", "company": "company", "location": "location",
    "salary": "salary", "url": "url", "posted_at": "posted_at",
    "description": "description",
}

# Posting fields that do NOT go straight into the posting table, with why
NOT_COLUMNS: dict[str, str] = {
    "source_id": "the key on raw_posting",
    "raw_body": "stored in raw_posting.body",
    "payload": "stored in raw_posting.payload",
    "remote": "has to be cast to int, handled separately",
}


def _row_values(source: str, raw_id: int, item: Posting) -> tuple[list[str], list]:
    """Build (columns, values) from FIELD_MAP instead of hand-writing INSERT."""
    columns = ["raw_id", "source", "remote", "fingerprint", "posted_ts"]
    values: list = [raw_id, source, int(item.remote), item.fingerprint(),
                    to_ts(item.posted_at)]
    for attr, column in FIELD_MAP.items():
        columns.append(column)
        values.append(getattr(item, attr))
    return columns, values


def xoa_kho(conn: sqlite3.Connection) -> dict:
    """Wipe the POSTING STORE for a fresh scan. Returns what was dropped.

    KEEPS ANYTHING TOUCHED. A posting with an application (`application`) or
    a pinned sentence (`cv_pick`) is work the user did, not something the
    machine scraped — deleting it erases the trace of an application, and no
    rescan can bring that back.

    COMPLETELY DIFFERENT from the Delete button on the CV side. A CV build
    takes 15 seconds to recreate; the posting store takes a full scan, with
    Chrome. So this confirmation has to state how many postings are about to
    go, not just ask "are you sure".

    Does NOT touch: the profile, applications sent, mail, settings, filters.
    """
    # FILTER NULLS INSIDE THE SUBQUERY. `NOT IN` against a NULL makes the
    # whole clause NULL, not TRUE — three-valued SQL, and this is its most
    # classic trap.
    #
    # Measured on the real store: 32 of 37 applications have posting_id =
    # NULL (applications reconstructed from mail, with no original posting).
    # So this statement deleted EXACTLY 0 postings — while source_run (204
    # scans) and cv_build were wiped clean right below. The user pressed
    # "Clear store", saw the store untouched, and lost their scan history.
    giu = ("SELECT posting_id FROM application WHERE posting_id IS NOT NULL"
           " UNION SELECT posting_id FROM cv_pick WHERE posting_id IS NOT NULL")
    n = conn.execute(f"SELECT COUNT(*) FROM posting WHERE id NOT IN ({giu})"
                     ).fetchone()[0]
    # raw_posting is deleted by the `raw_id` of the postings being dropped —
    # wiping the table would also lose the original text of postings that
    # have an application against them.
    conn.execute(
        f"DELETE FROM raw_posting WHERE id IN ("
        f"  SELECT raw_id FROM posting WHERE id NOT IN ({giu}) AND raw_id IS NOT NULL)")
    conn.execute(f"DELETE FROM posting WHERE id NOT IN ({giu})")
    lan = conn.execute("SELECT COUNT(*) FROM source_run").fetchone()[0]
    conn.execute("DELETE FROM source_run")
    # CV BUILDS MADE FROM THIS STORE. Keeping them means keeping 157 builds
    # that talk about 5,000 postings that just vanished — see cv/batch.py.
    ban = conn.execute("SELECT COUNT(*) FROM cv_build").fetchone()[0]
    conn.execute("DELETE FROM cv_build")
    conn.commit()
    con = conn.execute("SELECT COUNT(*) FROM posting").fetchone()[0]
    return {"tin": n, "giu": con, "lan_quet": lan, "ban_cv": ban}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- the audit log

def log(conn: sqlite3.Connection, kind: str, detail: str = "") -> None:
    conn.execute("INSERT INTO audit (at, kind, detail) VALUES (?,?,?)", (now(), kind, detail))
    conn.commit()


def recent_audit(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT at, kind, detail FROM audit ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


# ---------------------------------------------------------------- writing

# A description shorter than this counts as NOT READ — try again next time.
# The same threshold save_batch uses to decide whether to fill one in.
HAVE_DESC = 200


def already_read(conn: sqlite3.Connection, source) -> set[str]:
    """The source-side ids of postings that ALREADY have a real description.

    The deep-read pass uses this to SKIP. Without it, every scan reopens
    every page already read: measured on the real machine, 194 of 196
    LinkedIn postings already had a description, so 97% of the deep-read
    pass was redoing done work — and that waste dragged the whole chain with
    it: 8-16 minutes per hour -> ~4,600 calls per day -> throttled 40-82% ->
    longer cool-downs -> having to cut job titles from the search.

    Postings that failed to read (empty description) are NOT in here — they
    get another try next time.
    """
    # Takes ONE name or MANY. Alert mail and the Chrome scan point at the
    # same LinkedIn page, only the route the id arrived by differs — read it
    # under one source and the other has no reason to open it again.
    ten = (source,) if isinstance(source, str) else tuple(source)
    return {r[0] for r in conn.execute(
        "SELECT r.source_id FROM raw_posting r JOIN posting p ON p.raw_id = r.id"
        f" WHERE r.source IN ({','.join('?' * len(ten))})"
        "   AND length(COALESCE(p.description,'')) >= ?",
        (*ten, HAVE_DESC))}


def save_batch(conn: sqlite3.Connection, source: str,
               items: Iterable[Posting]) -> tuple[int, int]:
    """Write a batch of postings. Returns (seen, new).

    The cache blocks DUPLICATES, it does not block FILLING IN.

    A bug that was fixed: an existing posting used to be skipped entirely —
    so the fast pass wrote postings with no description, and when the
    deep-read pass finally got one there was nowhere to put it. Now: already
    there but missing a description, and this time we have one -> update.
    """
    seen = new = 0
    for item in items:
        seen += 1
        cur = conn.execute(
            "INSERT OR IGNORE INTO raw_posting"
            " (source, source_id, url, fetched_at, payload, body) VALUES (?,?,?,?,?,?)",
            (source, item.source_id, item.url, now(),
             json.dumps(item.payload, ensure_ascii=False),
             item.raw_body or item.description),      # verbatim, untouched
        )
        if not cur.rowcount:            # already there
            if item.raw_body:           # we have the original this time -> store if missing
                conn.execute(
                    "UPDATE raw_posting SET body = ? WHERE source = ? AND source_id = ?"
                    "  AND length(COALESCE(body,'')) < 200",
                    (item.raw_body, source, item.source_id))
            if item.description:        # and the extracted description, if missing
                # A description arriving late means the old judgement was
                # made from NOTHING. Clear the version stamps so derive()
                # sees the posting as stale and re-judges — without that it
                # sits at score=NULL forever.
                conn.execute(
                    "UPDATE posting SET description = ?, salary = COALESCE(NULLIF(?,''), salary),"
                    " posted_at = COALESCE(NULLIF(?,''), posted_at),"
                    " posted_ts = CASE WHEN ? > 0 THEN ? ELSE posted_ts END,"
                    " judged_rules = '', scored_rules = ''"
                    " WHERE raw_id = (SELECT id FROM raw_posting WHERE source=? AND source_id=?)"
                    "   AND length(COALESCE(description,'')) < 200",
                    (item.description, item.salary, item.posted_at,
                     to_ts(item.posted_at), to_ts(item.posted_at),
                     source, item.source_id))
            continue
        raw_id = int(cur.lastrowid)
        columns, values = _row_values(source, raw_id, item)
        marks = ",".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO posting ({','.join(columns)}) VALUES ({marks})", values)
        new += 1
    conn.commit()
    return seen, new


# Fail more than this fraction and the source counts as broken, even if a
# few postings did come back.
FAIL_THRESHOLD = 0.3


def record_run(conn: sqlite3.Connection, source: str, ok: bool,
               fetched: int = 0, new_rows: int = 0, error: str = "",
               attempted: int = 0, failed: int = 0) -> None:
    """Record one run of one source.

    If more than 30% of the postings it meant to read failed, mark ok=0 EVEN
    IF a few came back — a source that changed its markup usually breaks
    almost-but-not-quite completely, and looking only at "did anything come
    back" never catches it.
    """
    if ok and attempted and failed / attempted > FAIL_THRESHOLD:
        ok = False
        error = error or (f"{failed}/{attempted} postings failed to read "
                          f"({failed * 100 // attempted}%) — the page may have changed")
    conn.execute(
        "INSERT INTO source_run (source, started_at, ok, fetched, new_rows, error,"
        " attempted, failed) VALUES (?,?,?,?,?,?,?,?)",
        (source, now(), int(ok), fetched, new_rows, error, attempted, failed),
    )
    conn.commit()


# ---------------------------------------------------------------- reading

def unjudged(conn: sqlite3.Connection) -> int:
    """Postings loaded but never filtered. Should be 0 after every scan."""
    return int(conn.execute(
        "SELECT COUNT(*) FROM posting WHERE drop_reason = 'not judged yet'").fetchone()[0])


def count(conn: sqlite3.Connection, kept_only: bool = False) -> int:
    sql = "SELECT COUNT(*) FROM posting" + (" WHERE kept = 1" if kept_only else "")
    return int(conn.execute(sql).fetchone()[0])


def count_groups(conn: sqlite3.Connection) -> int:
    return int(conn.execute(
        "SELECT COUNT(DISTINCT COALESCE(group_id, CAST(id AS TEXT)))"
        " FROM posting WHERE kept = 1").fetchone()[0])


def all_postings(conn: sqlite3.Connection, kept_only: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM posting" + (" WHERE kept = 1" if kept_only else "") + " ORDER BY id"
    return conn.execute(sql).fetchall()


def source_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT source, COUNT(*) AS n, SUM(kept) AS kept FROM posting"
        " GROUP BY source ORDER BY n DESC").fetchall()


def last_runs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT source, MAX(started_at) AS at, ok, fetched, new_rows, error,"
        " attempted, failed FROM source_run GROUP BY source ORDER BY source").fetchall()
