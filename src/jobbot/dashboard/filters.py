"""Filters THE USER drives, with the state living in the URL.

Not the same as `ingest/filter.py`: that runs during a scan and decides what
is KEPT in the DB. This runs while viewing and decides what is SHOWN —
nothing is deleted, and changing your mind is one more click.

The whole state is in the URL (`/search?q=quant&show=dropped`), so:
  - the browser's Back button behaves correctly
  - a link can be saved to exactly the filter being viewed
  - no JavaScript, no session storage

Queries ALWAYS use bound parameters — nothing is ever concatenated into SQL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# FOUR DIFFERENT KINDS OF CONTROL — do not draw them alike:
#
#   STORE   which pile to view      -> chips, mutually exclusive
#   SCALE   has an ORDER            -> a LEVEL BAR, picking a floor
#   TAG     a kind, no order        -> chips
#   SORT    filters nothing at all  -> chips, on their own row
#
# All four used to be identical grey pills mixed across three rows: 20
# controls with no way to see which related to which. The worst were the two
# with an order — "Worth applying / Maybe / Long shot" is a SCALE, and drawn
# as three separate buttons you have to read all three to infer the order.

SHOW = [("matched", "Kept"), ("dropped", "Dropped"), ("all", "All")]
# PLACE — computed from THE PROFILE, with no hardcoded city name.
#
# "london" and "uk" used to sit here literally, which made the filter correct
# for exactly ONE user. The ids are now RELATIONS — near me / my country /
# elsewhere — and the label on the button comes from "Where you're based".
#
# This is where `location` should act: it does not decide which jobs are
# VALID (cutting to London loses 71 UK jobs outside London, measured 12 Sep),
# it gives one click to see which are CONVENIENT.
LOC = [("", "Anywhere"), ("near", "Near me"), ("home", "My country"),
       ("remote", "Remote"), ("other", "Elsewhere")]
DAYS = [("", "Any time"), ("7", "7 days"), ("30", "30 days"), ("90", "90 days")]
SORT = [("score", "Best match"), ("new", "Newest"), ("old", "Oldest"),
        ("company", "Company"), ("title", "Title")]

# --- SCALE: the value is a FLOOR, not one isolated level -----------------
# Picking "Possible" means possible AND ABOVE — so it includes "Worth it".
#
# It used to be equality: picking "Maybe" hid "Worth applying", which is
# exactly the best postings. Nobody wants that. What the user actually does
# is cut off the bottom, so a floor is the right operation — and a floor can
# be drawn as a bar.
CHANCE = [("", "All"), ("unlikely", "Unlikely"), ("possible", "Possible"),
          ("likely", "Worth it")]
CHANCE_RANK = {"unlikely": 1, "possible": 2, "likely": 3}
BAND = [("", "All"), ("60", "60+"), ("75", "75+")]

# --- TAG ------------------------------------------------------------------
# Uses "all", NOT an empty string: an empty string reads as "not chosen" and
# falls back to the default, leaving the user no way to say "show me both".
VIA = [("direct", "Direct employer"), ("all", "Include agencies"),
       ("agency", "Agencies only")]
# HOW it was found. The two search routes are blind in different places and
# produce very different postings: a company board carries the full
# description, while LinkedIn needs each posting opened. Filtering by route
# shows at a glance which route is producing the noise.
FOUND = [("", "Every source"), ("board", "board"), ("linkedin", "linkedin"),
         ("alert", "alert")]

# UK_LIKE WAS REMOVED. It was the THIRD copy of the same place list
# (ingest/filter.UK_WORDS, ingest/web/linkedin.MARKET_PLACE, and this) —
# three separate copies drifting apart with nobody noticing. They now all
# read `ingest.filter.NOI`.


PER_PAGE = 50


@dataclass
class JobFilter:
    """company/source allow MULTIPLE choices (checkboxes). The rest are
    overlapping or mutually exclusive ranges, so they pick one (chips)."""
    q: str = ""
    show: str = "matched"
    source: list[str] = field(default_factory=list)
    company: list[str] = field(default_factory=list)
    loc: str = ""
    days: str = ""
    band: str = ""
    via: str = "direct"
    found: str = ""            # how it was found: api / chrome
    raw: str = ""              # "1" = show ONLY postings the machine could not read
    chance: str = ""
    sort: str = "score"
    page: int = 1

    # --- reading from the URL ---------------------------------------------
    @staticmethod
    def from_query(query: dict[str, list[str]]) -> "JobFilter":
        def one(key: str, default: str = "") -> str:
            return (query.get(key, [default])[0] or default).strip()

        def many(key: str, cap: int) -> list[str]:
            seen, out = set(), []
            for value in query.get(key, []):
                value = value.strip()[:cap]
                if value and value.lower() not in seen:
                    seen.add(value.lower())
                    out.append(value)
            return out[:30]                       # stops an endlessly stuffed URL

        found = JobFilter(
            q=one("q")[:120],
            show=one("show", "matched"),
            source=many("source", 60),
            company=many("company", 80),
            loc=one("loc"),
            days=one("days"),
            band=one("band"),
            via=one("via", "direct"),
            found=one("found"),
            raw="1" if one("raw") else "",
            chance=one("chance"),
            sort=one("sort", "score"),
        )
        try:
            found.page = max(1, int(one("page", "1")))
        except ValueError:
            found.page = 1
        # only accepts values from the list — the rest is discarded
        valid = lambda value, options: value if value in {v for v, _ in options} else ""
        found.show = valid(found.show, SHOW) or "matched"
        found.loc = valid(found.loc, LOC)
        found.days = valid(found.days, DAYS)
        found.band = valid(found.band, BAND)
        found.via = found.via if found.via in {v for v, _ in VIA} else "direct"
        found.found = valid(found.found, FOUND)
        found.chance = valid(found.chance, CHANCE)
        found.sort = valid(found.sort, SORT) or "score"
        return found

    # --- building the SQL -------------------------------------------------
    def where(self, nha: str = "uk", near: str = "") -> tuple[str, list]:
        """`nha` = the region the user is in, `near` = the city they are in.

        These two are CONTEXT rather than user choices, so they do not live
        in the URL — they come from the profile. Left at their defaults they
        behave as the UK, exactly as before.
        """
        clauses: list[str] = []
        args: list = []

        if self.show == "matched":
            clauses.append("kept = 1")
        elif self.show == "dropped":
            clauses.append("kept = 0")

        if self.q:
            clauses.append("(LOWER(title) LIKE ? OR LOWER(company) LIKE ?)")
            needle = f"%{self.q.lower()}%"
            args += [needle, needle]

        if self.source:
            clauses.append("(" + " OR ".join("source LIKE ?" for _ in self.source) + ")")
            args += [f"{s}%" for s in self.source]

        if self.company:
            marks = ",".join("?" for _ in self.company)
            clauses.append(f"LOWER(company) IN ({marks})")
            args += [c.lower() for c in self.company]

        if self.loc in ("near", "home", "other"):
            from ..ingest.filter import NOI
            vung = NOI.get(nha) or NOI["uk"]
            ca_nuoc = sorted(vung["manh"] | vung["thanh"])
            if self.loc == "near":
                # The profile has no location -> "near me" means nothing.
                # Better not to filter than to filter by an invented place.
                if near:
                    clauses.append("LOWER(location) LIKE ?")
                    args.append(f"%{near.lower()}%")
            elif self.loc == "home":
                clauses.append("(" + " OR ".join("LOWER(location) LIKE ?"
                                                 for _ in ca_nuoc) + ")")
                args += [f"%{w}%" for w in ca_nuoc]
            else:
                clauses.append("NOT (" + " OR ".join("LOWER(location) LIKE ?"
                                                     for _ in ca_nuoc) + ")")
                args += [f"%{w}%" for w in ca_nuoc]
        elif self.loc == "remote":
            clauses.append("remote = 1")

        if self.via == "direct":
            clauses.append("via_agency = 0")
        elif self.via == "agency":
            clauses.append("via_agency = 1")
        # "all" -> adds no condition

        # SCALE = FLOOR. "Possible" means possible AND ABOVE, including
        # "Worth it". Postings the machine could not read (realism empty or
        # 'unknown') rank 0, so picking any level other than "All" drops them
        # on its own — no extra condition needed, and that is what the user
        # expects anyway.
        if self.chance in CHANCE_RANK:
            clauses.append(
                "CASE realism WHEN 'likely' THEN 3 WHEN 'possible' THEN 2"
                " WHEN 'unlikely' THEN 1 ELSE 0 END >= ?")
            args.append(CHANCE_RANK[self.chance])

        if self.band:
            clauses.append("score >= ?")
            args.append(int(self.band))

        if self.found == "alert":
            clauses.append("source = 'alert'")
        elif self.found == "linkedin":
            clauses.append("source = 'linkedin'")
        elif self.found == "board":
            clauses.append("source <> 'linkedin'")

        # ONE control instead of two. "Can't tell" (no chance estimated) and
        # "Not scorable" (no score computed) sat on two different rows, while
        # on the real store they are almost the same pile: 185 postings
        # missing both, 0 missing only the chance. One cause — the deep-read
        # pass has not reached that posting, so there is no description to
        # read.
        if self.raw:
            clauses.append("(score IS NULL OR COALESCE(realism,'')"
                           " IN ('', 'unknown'))")

        if self.days:
            clauses.append("posted_ts >= ?")
            args.append(int(time.time()) - int(self.days) * 86400)

        return (" WHERE " + " AND ".join(clauses)) if clauses else "", args

    def limit(self) -> tuple[int, int]:
        return PER_PAGE, (self.page - 1) * PER_PAGE

    def order(self) -> str:
        return {"score": "CASE realism WHEN 'likely' THEN 0 WHEN 'possible' THEN 1"
                         " WHEN 'unknown' THEN 2 ELSE 3 END, score DESC NULLS LAST",
                "new": "posted_ts DESC, id DESC", "old": "posted_ts ASC, id ASC",
                "company": "LOWER(company) ASC, LOWER(title) ASC",
                "title": "LOWER(title) ASC"}[self.sort]

    # --- building URLs ----------------------------------------------------
    def pairs(self, **changes) -> list[tuple[str, str]]:
        """The filter state as key/value pairs. ONE builder, two consumers.

        `url()` joins them into a query string for the chips; the SEARCH box
        pours them into <input hidden> so a GET form does not lose the active
        filters. Two places listing them separately are two lists, and adding
        a filter eventually means forgetting one of them — at which point
        typing a search wipes every selected chip.
        """
        state: dict = {"q": self.q, "show": self.show, "source": list(self.source),
                       "company": list(self.company), "loc": self.loc,
                       "days": self.days, "band": self.band, "via": self.via,
                       "found": self.found, "raw": self.raw,
                       "chance": self.chance, "sort": self.sort, "page": self.page}
        # changing a filter returns to page 1 — unless it is the page changing
        if "page" not in changes:
            state["page"] = ""
        state.update(changes)
        if str(state.get("page", "")) in ("", "1"):
            state["page"] = ""
        default = {"show": "matched", "sort": "score", "via": "direct"}

        out: list[tuple[str, str]] = []
        for key, value in state.items():
            if isinstance(value, list):
                out += [(key, v) for v in value]
            elif value and default.get(key) != value:
                out.append((key, str(value)))
        return out

    def url(self, **changes) -> str:
        from urllib.parse import urlencode
        got = self.pairs(**changes)
        # The job list lives in the Search tab — the Jobs tab is gone.
        return "/search" + (f"?{urlencode(got)}" if got else "")

    def toggle(self, key: str, value: str) -> str:
        """The URL after toggling one checkbox."""
        current = list(getattr(self, key))
        low = [c.lower() for c in current]
        if value.lower() in low:
            current.pop(low.index(value.lower()))
        else:
            current.append(value)
        return self.url(**{key: current})

    def has(self, key: str, value: str) -> bool:
        return value.lower() in [c.lower() for c in getattr(self, key)]

    def active(self) -> list[tuple[str, str]]:
        """The active filters, each with a URL that turns it off."""
        out: list[tuple[str, str]] = []
        if self.q:
            out.append((f'"{self.q}"', self.url(q="")))
        if self.show != "matched":
            out.append((dict(SHOW)[self.show], self.url(show="matched")))
        for value in self.source:
            out.append((value, self.toggle("source", value)))
        for value in self.company:
            out.append((value, self.toggle("company", value)))
        if self.loc:
            out.append((dict(LOC)[self.loc], self.url(loc="")))
        if self.days:
            out.append((dict(DAYS)[self.days], self.url(days="")))
        if self.band:
            out.append((dict(BAND)[self.band], self.url(band="")))
        if self.chance:
            out.append((dict(CHANCE)[self.chance], self.url(chance="")))
        if self.via != "direct":
            out.append((dict(VIA)[self.via], self.url(via="direct")))
        if self.found:
            out.append((dict(FOUND)[self.found], self.url(found="")))
        if self.raw:
            out.append(("could not be read", self.url(raw="")))
        return out
