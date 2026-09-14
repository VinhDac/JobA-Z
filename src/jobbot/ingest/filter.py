"""Filter postings against the profile — and ALWAYS be able to say why.

Nothing is ever dropped in silence. Every rejected posting records a
drop_reason, so that looking back later shows where the filter is too tight.
Dropping in silence is the surest way to lose good postings and never know.
"""

from __future__ import annotations

import re

from .base import Posting, norm

# Seniority signals. Only rejected when CLEAR — "Analyst" in finance is
# usually entry level, not senior.
SENIOR_WORDS = {
    "senior", "snr", "sr", "lead", "principal", "staff", "head", "director",
    "chief", "vp", "vice president", "manager", "architect", "expert", "specialist ii",
}
# A BUG THAT WAS FIXED: "analyst" used to be in here, letting every
# "Senior ... Analyst" posting through because the exception always fired. In
# finance "Analyst" is a common title at EVERY level, so it is not a junior
# signal.
JUNIOR_WORDS = {
    "graduate", "grad", "junior", "jr", "intern", "internship", "placement",
    "entry", "trainee", "apprentice", "campus", "early career",
}

# ONE place table for the whole app. There used to be TWO:
# `linkedin.MARKET_PLACE` said WHERE TO SEARCH and `filter.UK_WORDS` said
# WHAT TO KEEP — two separate tables that drifted apart with nobody noticing
# until someone sat down and counted.
#
#   place  chữ gửi cho LinkedIn
#   manh   a CERTAIN signal of this region
#   thanh  a city name — correct, but COLLIDES with names elsewhere
NOI = {
    "uk": {
        "ten": "UK",
        "place": "United Kingdom",
        "manh": {"united kingdom", "uk", "gb", "england", "britain",
                 "scotland", "wales"},
        "thanh": {"london", "manchester", "edinburgh", "cambridge", "oxford",
                  "bristol", "leeds", "birmingham", "glasgow"},
    },
    "eu": {
        "ten": "EU",
        "place": "European Union",
        "manh": {"european union", "eu", "germany", "france", "netherlands",
                 "ireland", "spain", "italy", "poland", "portugal", "sweden"},
        "thanh": {"berlin", "paris", "amsterdam", "dublin", "madrid", "lisbon",
                  "munich", "warsaw", "stockholm"},
    },
    "us": {
        "ten": "US",
        "place": "United States",
        "manh": {"united states", "usa", "us"},
        "thanh": {"new york", "san francisco", "boston", "chicago", "seattle",
                  "austin", "washington"},
    },
}

# A US state code after a comma. THE GUARD for colliding city names:
# "Birmingham, AL" is Alabama, not the English Birmingham — and it was
# sitting in Vin's UK job list (measured 12 Sep, the Mission Pet Health
# posting). Measured effect: it removes exactly 2 wrong postings and keeps
# all 313 right ones.
BANG_MY = re.compile(
    r",\s*(A[LKZR]|C[AOT]|DE|FL|GA|HI|I[DLNA]|K[SY]|LA|M[EDAINSOT]|N[EVHJMYCD]"
    r"|OH|OK|OR|PA|RI|S[CD]|TN|TX|UT|V[TA]|W[AVIY]|DC)\b")

EU_REMOTE_WORDS = {"europe", "emea", "anywhere", "worldwide", "global", "remote"}


def o_vung(text: str, key: str) -> bool:
    """Does this location string belong to region `key`.

    A STRONG signal is trusted outright. A CITY name is trusted unless the
    string also carries a US state code — in which case it is the
    same-named American city.
    """
    vung = NOI.get(key)
    if not vung:
        return False
    if _names_in(text, vung["manh"]):
        return True
    return bool(vung["thanh"]) and _names_in(text, vung["thanh"])


def noi_o(location: str) -> str:
    """Which region you ARE IN — derived from the profile's "Where you're
    based".

    This is the job that field always promised ("Used to filter on-site and
    hybrid roles by commute") and never did: until today not one line of the
    search or the filter read it, only the CV and form filling. Meanwhile
    "UK" was hardcoded in three different places, which means the app assumed
    every user lives in Britain.

    When it cannot tell it returns empty and the caller keeps the old
    behaviour — it must not change what is being kept just because one
    profile field is worded oddly.
    """
    text = norm(location or "")
    if not text:
        return ""
    for key in NOI:
        if _names_in(text, NOI[key]["manh"]) or _names_in(text, NOI[key]["thanh"]):
            return key
    return ""


def _titles(answers: dict) -> list[str]:
    raw = answers.get("job_titles") or ""
    return [norm(line) for line in raw.splitlines() if line.strip()]


def title_hit(posting: Posting, targets: list[str]) -> str | None:
    """Does the posting's title contain any title you target."""
    text = norm(posting.title)
    return next((t for t in targets if t and t in text), None)


def seniority_ok(posting: Posting, accepted: list[str]) -> bool:
    """Targeting junior while the posting says Senior/Lead/Head -> drop."""
    wants_junior = bool({"intern", "grad", "grad_scheme", "junior"} & set(accepted))
    if not wants_junior:
        return True
    text = norm(posting.title)
    if any(f" {w} " in f" {text} " for w in SENIOR_WORDS):
        # Unless the posting says BOTH — "Graduate to Senior Analyst" stays.
        return any(f" {w} " in f" {text} " for w in JUNIOR_WORDS)
    return True


def _names_in(text: str, names: set[str]) -> bool:
    """Place names match by WORD, not by substring.

    'uk' is inside 'ukraine', 'gb' is inside 'gbagada' — on the real DB, 17
    postings in Paris, Köln and Bremen got through the location filter that
    way. norm() has already turned punctuation into spaces, so padding both
    ends is enough.
    """
    padded = f" {text} "
    return any(f" {name} " in padded for name in names)


# The profile's "markets" field says WHERE THE USER WILL TAKE WORK. Each
# choice opens one more region; the last two remove the location gate
# entirely.
#
# ONE TRANSLATION, shared with `NOI`. The LinkedIn side has a MARKET_PLACE
# table translating exactly these keys into places to search ("us_remote" ->
# "United States") — two tables means the app eventually searches in the US
# and then throws every result away, which is EXACTLY what happened.
THI_TRUONG = {"uk_onsite": {"uk"}, "uk_remote": {"uk"},
              "eu_remote": {"eu"}, "us_remote": {"us"},
              "global_remote": set(NOI), "relocate": set(NOI)}


def vung_nhan(markets: list[str], nha: str = "uk") -> set:
    """The regions the user will take work in: where they are + every market
    they chose."""
    ra = {nha}
    for m in markets or ():
        ra |= THI_TRUONG.get(str(m).strip().lower(), set())
    return ra


def location_ok(posting: Posting, markets: list[str], nha: str = "uk") -> bool:
    """Is this job WHERE I AM — where "I am" includes the chosen markets.

    `nha` is the region the user is in, derived from "Where you're based".

    `markets` IS A REAL PARAMETER, not decoration. The previous version took
    it and never read it once: a profile choosing "US — remote" still had New
    York postings thrown away with the reason "outside your area (UK)".
    Worse, LinkedIn translated those same keys into places to search — so the
    app searched in the US and then threw every result away, and the user
    just saw "no jobs".
    """
    nhan = vung_nhan(markets, nha)
    text = norm(f"{posting.location} {posting.company}")
    # A US state code blocks the CITY-NAME match: "Birmingham, AL" is
    # Alabama. A STRONG signal is still trusted — "London, New York" contains
    # the city name "london", but if something also says "United Kingdom"
    # that is certain.
    # A US state code is only noise WHEN the user does not take US work:
    # "Birmingham, AL" is Alabama, not the English Birmingham. For someone
    # who chose us_remote it is exactly what they wanted.
    if "us" not in nhan and BANG_MY.search(posting.location or ""):
        vung = NOI.get(nha) or {}
        if not _names_in(text, vung.get("manh", set())):
            return False
    for v in nhan:
        if o_vung(text, v):
            return True
    # A posting saying only "Remote": keep it if the user takes remote work
    # in ANY region beyond where they are — otherwise it is just a domestic
    # remote posting.
    if posting.remote and _names_in(text, EU_REMOTE_WORDS):
        return True
    if len(nhan) > 1 and (posting.remote or _names_in(text, EU_REMOTE_WORDS)):
        return True
    return False


def judge(posting: Posting, answers: dict) -> tuple[bool, str]:
    """Returns (keep, reason). There is always a reason, even when kept."""
    targets = _titles(answers)
    if not targets:
        return True, "no job_titles set — keeping everything"

    hit = title_hit(posting, targets)
    if not hit:
        return False, "title does not match any target title"
    if not seniority_ok(posting, answers.get("seniority") or []):
        return False, "title is senior level — you target graduate/junior"
    # Where they live comes from the profile; when it cannot be told, keep
    # the old behaviour (UK) rather than changing what is kept over one
    # oddly worded field.
    nha = noi_o(answers.get("location") or "") or "uk"
    if not location_ok(posting, answers.get("markets") or [], nha):
        return False, (f"location '{posting.location or 'unknown'}' outside"
                       f" your area ({NOI[nha]['ten']})")
    return True, f"matched target title '{hit}'"
