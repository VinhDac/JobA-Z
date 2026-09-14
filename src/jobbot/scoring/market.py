"""Which skills the market is ASKING FOR, counted over the kept postings.

One number, one purpose: the CV tab asks "how many postings does this block
of mine reach". A block that reaches 0 is a block taking up space — it is on
the CV because there was room, not because it proves anything.

It used to live in `projects/inventory.py`. It never belonged to that
feature: this code knows nothing about projects, it only adds up
`posting.score_json`. The personal-project feature was dropped (see
docs/changes); this count stayed — and now sits in the right layer, next
to the vocabulary it uses.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter

from ..ingest.base import norm
from .vocab import alias_hits


def demand(conn: sqlite3.Connection) -> Counter:
    """How many POSTINGS ask for each skill.

    Counted per POSTING, not per requirement line — a posting that mentions
    'python' five times is still one posting.

    Reads the extracted REQUIREMENTS, not the full text: the full text also
    contains the company blurb and the benefits, and reading that makes every
    posting appear to ask for everything.
    """
    dem: Counter = Counter()
    for row in conn.execute(
            "SELECT score_json FROM posting"
            " WHERE kept = 1 AND score_json != ''"):
        try:
            reqs = json.loads(row["score_json"]).get("requirements", [])
        except (TypeError, ValueError):
            continue
        dem.update({h for r in reqs for h in alias_hits(norm(r.get("text", "")))})
    return dem
