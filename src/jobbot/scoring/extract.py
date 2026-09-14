"""Extract the requirements out of a JD.

The approach, following the structure observed across 24 real JDs:
    1. Split the JD by section heading
    2. Drop the sections that are NOT requirements (benefits, company blurb)
    3. Take the bullets from the requirements and nice-to-have sections
    4. No headings at all -> take every bullet and treat it as required

Every requirement keeps its verbatim text so it can be shown to the reader to
check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .vocab import (DO_HEADS, MUST_WORDS, NICE_HEADS, NICE_WORDS,
                    REQ_HEADS, STOP_HEADS)

BULLET = re.compile(r"^\s*(?:[·•\-–*]|\d+[.)])\s+(.{6,400})$")

# The fallback for JDs written in prose (GSA, Zopa...): take any sentence
# that SOUNDS like a requirement. Nothing is invented — it is still the
# verbatim sentence from the JD.
PROSE_HINT = re.compile(
    r"\b(you (?:will )?(?:have|need|bring|possess)|if you have|we(?:'re| are) looking for|"
    r"experience (?:in|of|with)|knowledge of|degree in|background in|familiar(?:ity)? with|"
    r"proficien|strong (?:understanding|grasp|skills)|ability to|comfortable with|"
    r"academic credentials|track record)\b", re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+")

# Benefits sentences often slip into the fallback ("you'll have 25 days
# holiday"). Scoring a candidate on a company's benefits is meaningless.
BENEFIT_WORDS = re.compile(
    r"\b(holiday|annual leave|days off|pension|insurance|healthcare|wellbeing|"
    r"gym|parental leave|maternity|paternity|salary|bonus scheme|share options|"
    r"equity package|working from abroad|flexible working|hybrid working|"
    r"office|snacks|socials?|perks?|discount)\b", re.I)
MAX_REQS = 18            # a rambling JD gets cut — 18 lines is enough to judge


@dataclass
class Requirement:
    text: str
    must: bool           # required, or only a nice-to-have
    source: str = "bullet"   # bullet = trustworthy | prose = inferred


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not (3 < len(stripped) < 80):
        return False
    if BULLET.match(line):
        return False
    # headings are usually short and do not end in a full stop
    return bool(REQ_HEADS.match(stripped) or NICE_HEADS.match(stripped)
                or STOP_HEADS.match(stripped) or DO_HEADS.match(stripped))


def sections(text: str) -> list[tuple[str, list[str]]]:
    """Split into (section kind, lines). Kinds: req | nice | do | stop | body.

    `do` is the RESPONSIBILITIES section. It must NOT be mixed into `req`:
    requirements say "what you must have", responsibilities say "what you
    will do". Mixing them scores a candidate on the job description.
    """
    out: list[tuple[str, list[str]]] = []
    kind, buffer = "body", []
    for line in (text or "").splitlines():
        if _is_heading(line):
            if buffer:
                out.append((kind, buffer))
            stripped = line.strip()
            kind = ("nice" if NICE_HEADS.match(stripped)
                    else "stop" if STOP_HEADS.match(stripped)
                    else "do" if DO_HEADS.match(stripped)
                    else "req")
            buffer = []
        else:
            buffer.append(line)
    if buffer:
        out.append((kind, buffer))
    return out


def _bullets(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        found = BULLET.match(line)
        if found:
            item = re.sub(r"\s+", " ", found.group(1)).strip(" .;")
            if len(item) > 6:
                out.append(item)
    return out


MIN_RUN = 3              # fewer than 3 consecutive lines is not a list


def _runs(lines: list[str]) -> list[str]:
    """A list with NO bullet characters — recognised by the line breaks.

    Why it is needed: LinkedIn returns the JD as pre-rendered text, and every
    <li> loses its '·'. Forty-six kept postings had a perfectly readable
    requirements list while the extractor returned nothing, over one missing
    character.

    The distinguishing signal: when HTML is stripped to text, '</p>' becomes
    two blank lines while '<li>' becomes only one — so a prose paragraph
    stands ALONE between blank lines, while list items come in a RUN. Take
    the runs, drop the lone paragraphs.
    """
    out: list[str] = []
    run: list[str] = []

    def flush():
        if len(run) >= MIN_RUN:
            out.extend(run)
        run.clear()

    for line in lines:
        item = re.sub(r"\s+", " ", line).strip(" .;")
        if 20 < len(item) < 400 and not BULLET.match(line):
            run.append(item)
        else:
            flush()
    flush()
    return out


def requirements(text: str) -> list[Requirement]:
    parts = sections(text)
    out: list[Requirement] = []

    for kind, lines in parts:
        if kind == "stop":
            continue                       # benefits, blurb — not a requirement
        if kind == "body":
            continue                       # the opening prose, left to the fallback
        if kind == "do":
            continue                       # responsibilities — see duties()
        for item in _bullets(lines):
            must = kind == "req"
            if NICE_WORDS.search(item):
                must = False
            elif MUST_WORDS.search(item):
                must = True
            out.append(Requirement(item, must))

    if not out:                            # no sections -> take every bullet
        for kind, lines in parts:
            if kind == "stop":
                continue
            for item in _bullets(lines):
                out.append(Requirement(item, not NICE_WORDS.search(item)))

    if not out:                            # no bullets at all -> look for a list
        for kind, lines in parts:          #    recognised by line breaks (LinkedIn)
            if kind == "stop":
                continue
            for item in _runs(lines):
                # A benefits list is also a list. Scoring on "competitive
                # salary" produces a meaningless number.
                if BENEFIT_WORDS.search(item):
                    continue
                must = kind != "nice" and not NICE_WORDS.search(item)
                out.append(Requirement(item, must, "list"))

    if not out:                            # still nothing -> the JD is prose
        out = _from_prose(parts)

    # deduplicate, keeping order
    seen, unique = set(), []
    for req in out:
        key = req.text.lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(req)
    return unique[:MAX_REQS]


def _from_prose(parts: list[tuple[str, list[str]]]) -> list[Requirement]:
    """A JD with no bullets: pick sentences that sound like requirements.
    Still the real sentences."""
    out: list[Requirement] = []
    for kind, lines in parts:
        if kind == "stop":
            continue
        blob = re.sub(r"\s+", " ", " ".join(lines))
        for sentence in SENTENCE.split(blob):
            sentence = sentence.strip(" .;")
            if not (25 < len(sentence) < 320):
                continue
            if not PROSE_HINT.search(sentence) or BENEFIT_WORDS.search(sentence):
                continue
            out.append(Requirement(sentence, not NICE_WORDS.search(sentence), "prose"))
    return out


# A real RESPONSIBILITY sentence opens with a VERB. A sentence like "You will
# be part of one of our flagship teams" is a blurb, not a responsibility.
DUTY_VERB = re.compile(
    r"^\s*(?:you(?:'ll| will)?\s+(?:be\s+)?)?"
    r"(build|develop|design|research|conduct|create|analys|analyz|model|"
    r"implement|maintain|monitor|improve|optimis|optimiz|automat|test|"
    r"validat|backtest|investigat|explore|identif|measur|forecast|predict|"
    r"deploy|support|manage|own|deliver|produce|write|generat|evaluat|"
    r"collaborat|work with|partner with|contribute)", re.I)

MAX_DUTIES = 12


def duties(text: str) -> list[str]:
    """What this posting says you will DO — the half of the JD that used to
    be thrown away.

    Different from requirements() because it asks a different question:
    requirements are "what you must have", responsibilities are "what you
    will do". It is the second half that describes a project.

    Filtered by the OPENING VERB: many postings start their "The Role"
    section with a team advert ("you will be part of one of our flagship
    teams"), and taking the whole section collects the advert instead of the
    work.
    """
    out: list[str] = []
    for kind, lines in sections(text):
        if kind != "do":
            continue
        items = _bullets(lines) or _runs(lines)
        for item in items:
            if BENEFIT_WORDS.search(item) or not DUTY_VERB.match(item):
                continue
            out.append(item.strip())

    seen, unique = set(), []
    for item in out:
        key = item.lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:MAX_DUTIES]


def confidence(reqs: list[Requirement]) -> str:
    """How much to trust what was just extracted.

    When the requirements cannot be read it SAYS SO rather than scoring — an
    invented score is worse than no score.
    """
    if not reqs:
        return "none"
    if any(r.source == "prose" for r in reqs):
        return "low"
    if any(r.source == "list" for r in reqs):
        # A whole list was read, but its boundaries were inferred from line
        # breaks rather than stated by bullets — trust it moderately, not as
        # much as bullets.
        return "medium"
    return "high" if len(reqs) >= 4 else "medium"
