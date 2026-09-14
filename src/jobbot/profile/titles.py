"""The job-title store — extracted from REAL POSTINGS, never typed by hand.

The profile question says it outright: "write them EXACTLY as they appear on
postings". So the only correct source is those postings. A hand-typed list in
the source code is wrong on the day it is written and rots from there: the
market invents new titles constantly ("Forward Deployed Engineer" did not
exist a few years ago), and nobody remembers to come back and edit the file.

Two routes in, one extractor:

    from the DB   if `posting` already holds postings, use them — free, and
                  refreshed after every scan with no separate update
                  mechanism.
    from boards   on day one there are no postings, so call the company
                  boards directly. Measured: 9 boards -> 1,471 postings ->
                  1,107 titles in ~4 seconds, pure HTTP, no Chrome and NO
                  profile needed (the gate only blocks a filtered scan, not
                  reading a board).

It extracts the ROLE PHRASE rather than the whole title: a real title is
"2027 Point72 Academy Investment Analyst Summer Internship Program - Japan
(BCF)" — useless as a suggestion. What finds jobs is the phrase "Investment
Analyst".
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter

# The last word of a role phrase. A phrase has to END with one of these —
# "Senior Quantitative" is not a job title, "Quantitative Researcher" is.
ROLE_TAIL = re.compile(
    r"^(analyst|engineer|scientist|developer|researcher|manager|trader|"
    r"strategist|consultant|associate|specialist|architect|lead|intern|"
    r"quant|technologist|administrator)$", re.I)
WORD = re.compile(r"[A-Za-z+#][A-Za-z+#'&.]*")
CACHE_KEY = "title_vocab"


def extract(titles: list[str], least: int = 3, top: int = 60) -> list[tuple[str, int]]:
    """Real titles -> usable role phrases, with how many postings hold each.

    `least` is a floor: a phrase appearing once or twice is usually one
    company's own programme name, not something to type into a search box.
    """
    dem: Counter = Counter()
    for raw in titles:
        t = re.sub(r"\s*[\(\[].*?[\)\]]", "", raw or "")      # drop brackets
        t = re.split(r"\s+[-–—,|/]\s+", t)[0]                 # drop the location tail
        w = WORD.findall(t)
        for n in (2, 3):
            for i in range(len(w) - n + 1):
                cum = w[i:i + n]
                if not ROLE_TAIL.match(cum[-1]):
                    continue
                dem[" ".join(cum)] += 1

    thuong = [(k, v) for k, v in dem.most_common() if v >= least]

    # Drop a LONGER phrase that is no more common: "Academy Investment
    # Analyst" (15) sits inside "Investment Analyst" (15) — the same count
    # means the longer one is just one company's name for it. The shorter
    # phrase searches wider.
    #
    # The other way round, "Machine Learning Researcher" (13) contains
    # "Learning Researcher" (13) — here the SHORTER one is the fragment. So
    # the rule is: drop any phrase that is a MIDDLE/TAIL slice of another
    # with the same count, and keep the one that starts it.
    giu: list[tuple[str, int]] = []
    for cum, n in thuong:
        thua = False
        for khac, m in thuong:
            if khac == cum or n != m:
                continue
            if cum in khac and not khac.startswith(cum):
                thua = True       # cum is a tail of khac -> a fragment
                break
            if khac in cum and cum.endswith(khac):
                thua = True       # cum is longer but no more common
                break
        if not thua:
            giu.append((cum, n))
    return giu[:top]


def from_postings(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    rows = conn.execute("SELECT title FROM posting WHERE title <> ''").fetchall()
    return extract([r[0] for r in rows]) if rows else []


def fetch_boards(boards: dict[str, list[str]], log=None) -> list[str]:
    """Call the company boards for titles. Saves NO postings — borrows words.

    A broken board is skipped: a title store missing a few lines is still
    usable, while raising would kill the whole button because one board is
    under maintenance.
    """
    from ..ingest import ashby, greenhouse, lever
    mods = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
    out: list[str] = []
    for ten, danh_sach in boards.items():
        mod = mods.get(ten)
        if mod is None:
            continue
        for board in danh_sach:
            try:
                out += [p.title for p in mod.fetch_board(board)]
            except Exception as exc:                       # noqa: BLE001
                if log:
                    log(f"{ten}:{board} — {type(exc).__name__}")
    return out


def cached(conn: sqlite3.Connection) -> list[str]:
    """The store the screen uses. Scanned postings first, the saved copy
    second."""
    from ..core import prefs
    tu_tin = from_postings(conn)
    if tu_tin:
        return [c for c, _ in tu_tin]
    try:
        return json.loads(prefs.get(conn, CACHE_KEY) or "[]")
    except (ValueError, TypeError):
        return []


def save(conn: sqlite3.Connection, cum: list[tuple[str, int]]) -> int:
    from ..core import prefs
    prefs.put(conn, CACHE_KEY, json.dumps([c for c, _ in cum]))
    return len(cum)
