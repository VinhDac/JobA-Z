"""The target company list — and it grows on its own over time.

Go straight to the employer rather than through a board. The `company` table
holds: the name, which ATS, which slug, when it was last probed, how many

postings it yielded. Growing on its own: every scan that sees a REAL employer
(not an agency) in a fetched posting adds that name to the queue to probe.
The list grows without anyone typing.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..base import norm_company
from .careers import resolve_ats


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add(conn: sqlite3.Connection, name: str, note: str = "") -> bool:
    name = (name or "").strip()
    key = norm_company(name)
    if not key or len(key) < 2:
        return False
    cur = conn.execute(
        "INSERT OR IGNORE INTO company (name, key, note) VALUES (?,?,?)",
        (name, key, note))
    return bool(cur.rowcount)


def seed(conn: sqlite3.Connection, names: list[str], note: str = "seed") -> int:
    added = sum(add(conn, n, note) for n in names)
    conn.commit()
    return added


def learn_from_postings(conn: sqlite3.Connection) -> int:
    """Real employers seen in postings -> queued to be probed.

    Agency postings are skipped: the name on them is the middleman, not the employer.
    """
    rows = conn.execute(
        "SELECT DISTINCT company FROM posting"
        " WHERE kept = 1 AND via_agency = 0 AND company != '' AND company != 'unknown'"
    ).fetchall()
    added = sum(add(conn, r["company"], "seen in a posting") for r in rows)
    conn.commit()
    return added


def pending(conn: sqlite3.Connection, limit: int = 40) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM company WHERE checked_at = '' ORDER BY id LIMIT ?", (limit,)
    ).fetchall()


def resolve_pending(conn: sqlite3.Connection, limit: int = 40,
                    log=lambda _m: None) -> dict:
    """Probe the ATS of companies not yet checked. HTTP only, no Chrome."""
    found = checked = 0
    for row in pending(conn, limit):
        ats, slug, count = resolve_ats(row["name"])
        conn.execute(
            "UPDATE company SET ats=?, ats_slug=?, roles_found=?, checked_at=? WHERE id=?",
            (ats, slug, count, _now(), row["id"]))
        checked += 1
        if ats:
            found += 1
            log(f"    {row['name'][:26]:28} {ats:11} {slug:24} {count:3} tin")
    conn.commit()
    return {"checked": checked, "found": found}


def boards(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """{ats: [slug...]} for the scan to use. Replaces a hand-typed boards.toml."""
    out: dict[str, list[str]] = {}
    for row in conn.execute(
            "SELECT ats, ats_slug FROM company WHERE ats != '' AND ats_slug != ''"
            " AND is_agency = 0 ORDER BY roles_found DESC"):
        out.setdefault(row["ats"], []).append(row["ats_slug"])
    return out


def mark_agencies(conn: sqlite3.Connection, names: set[str]) -> int:
    keys = [norm_company(n) for n in names]
    if not keys:
        return 0
    marks = ",".join("?" for _ in keys)
    cur = conn.execute(f"UPDATE company SET is_agency = 1 WHERE key IN ({marks})", keys)
    conn.commit()
    return cur.rowcount


def stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) total, SUM(checked_at != '') checked,"
        " SUM(ats != '') resolved, SUM(is_agency) agencies FROM company").fetchone()
    return {k: row[k] or 0 for k in ("total", "checked", "resolved", "agencies")}
