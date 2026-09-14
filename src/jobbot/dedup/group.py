"""Group duplicate postings — one job posted on several boards.

Step 1 uses a fingerprint: normalised company + normalised title.
Enough to catch most duplicates, and ALWAYS explicable.

Not yet caught: the same job with a completely different title ("Grad
Analyst 2027" vs "Graduate Analyst Programme"). Left to step 2, once there
is real data to measure against.
"""

from __future__ import annotations

import sqlite3


def regroup(conn: sqlite3.Connection, commit: bool = True) -> tuple[int, int]:
    """Assign a group_id to every kept posting. Returns (rows, groups).

    `commit=False` when the caller holds a larger transaction — committing
    here would cut that transaction short and lose its atomicity.
    """
    rows = conn.execute(
        "SELECT id, fingerprint FROM posting WHERE kept = 1 ORDER BY id").fetchall()
    first_seen: dict[str, int] = {}
    for row in rows:
        first_seen.setdefault(row["fingerprint"], row["id"])
    conn.executemany(
        "UPDATE posting SET group_id = ? WHERE id = ?",
        [(str(first_seen[r["fingerprint"]]), r["id"]) for r in rows],
    )
    if commit:
        conn.commit()
    return len(rows), len(first_seen)


def groups(conn: sqlite3.Connection) -> list[dict]:
    """One row per group, with the list of sources that saw it."""
    rows = conn.execute(
        "SELECT group_id, COUNT(*) AS n, GROUP_CONCAT(DISTINCT source) AS sources,"
        " MIN(id) AS lead_id FROM posting WHERE kept = 1"
        " GROUP BY group_id ORDER BY n DESC, lead_id").fetchall()
    out = []
    for row in rows:
        lead = conn.execute("SELECT * FROM posting WHERE id = ?", (row["lead_id"],)).fetchone()
        out.append({"group_id": row["group_id"], "count": row["n"],
                    "sources": sorted((row["sources"] or "").split(",")),
                    "posting": dict(lead)})
    return out
