"""Score the CV against a JD, and ALWAYS be able to explain the score.

The rule: a score that cannot be explained is not used to decide whether to
apply. So every function here returns EVIDENCE with it — wording taken
straight from the profile.

Out of 100:
    55  how much of the REQUIRED is met
    15  the NICE-TO-HAVE
    20  the right level (targeting graduate on a senior posting is a heavy
        deduction)
    10  the title matching

A requirement that cannot be judged (no keyword recognised) does NOT count
toward the denominator — counting it would invent a certainty we do not have.
It only lowers the confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..ingest.base import norm
from . import extract
from .vocab import (DEGREE_WORDS, QUANT_FIELD, SKILLS, YEARS,
                    alias_hits)

YEARS_BAND = {"0-1": 0.5, "1-3": 2, "3-5": 4, "5-8": 6.5, "8+": 10}
# ------------------------------------------------------------------ level
#
# ONE NUMBER LINE, not a "is this junior" flag.
#
# The old version knew exactly one question: does the user target junior. Vin
# targets grad+junior so it worked FOR VIN, and was plainly wrong for everyone
# else: choose "senior" and `junior` is False, and the function returned 0.6
# "level not stated in the title" for EVERY posting — including one shouting
# "Graduate Intern" in its title. Level is 20 of 100 points, so the whole
# ranking shifted with nothing to say so. That is the rut of "works for my own
# case", not a solution.
#
# The numbers are a DISTANCE, not a rank: grad and senior are 3 steps apart,
# so "does it fit" is measured by subtraction, and the same subtraction works
# for everyone — someone targeting senior meeting an internship is 3 steps
# off, exactly as in the other direction.
BAC = {"intern": 0, "grad": 0, "grad_scheme": 0, "junior": 1,
       "mid": 2, "senior": 3, "lead": 4}
TEN_BAC = {0: "entry/graduate", 1: "junior", 2: "mid", 3: "senior",
           4: "lead/principal"}

# Read the level FROM THE TITLE. Listed high to low: a title matching several
# levels keeps the LOWEST match (see `_bac_tieu_de`).
#
# BARE "programme" does NOT count as a graduate posting, and this is a
# measured bug: 34 postings in the DB match "program|programme" and are not
# graduate postings —
# "Senior Technical Program Manager", "GRC Program Manager", "Swag Program
# Manager". The old rule gave them 1.0 "explicitly graduate/junior" AND
# cancelled the seniority penalty, so a senior posting jumped from 0 to 20
# points. So the word only counts alongside something that makes it an
# early-careers programme: graduate, summer,
# analyst, internship, rotational, pathway, campus, early careers.
BAC_TIEU_DE = (
    (4, re.compile(r"\b(lead|principal|staff|head of|director|vp|chief|"
                   r"vice president)\b", re.I)),
    (3, re.compile(r"\b(senior|snr|sr)\b", re.I)),
    (2, re.compile(r"\b(mid[- ]?level|midweight|intermediate)\b", re.I)),
    (1, re.compile(r"\b(junior|jr)\b", re.I)),
    (0, re.compile(r"\b(graduate|grad|intern|internship|placement|entry|"
                   r"trainee|campus|academy|apprentice|scheme|rotational|"
                   r"early careers?)\b"
                   r"|\b(graduate|summer|analyst|internship|rotational|"
                   r"pathway|campus|early careers?)\s+programme?\b", re.I)),
)

# The old names are kept: realism.py and others still ask "is this senior".
SENIOR_TITLE = BAC_TIEU_DE[1][1]
JUNIOR_TITLE = BAC_TIEU_DE[4][1]
JUNIOR_LEVELS = {"intern", "grad", "grad_scheme", "junior"}


@dataclass
class Evidence:
    where: str
    text: str
    normal: str
    strong: bool
    kind: str = ""        # experience | project | "" (a profile field)
    meta: str = ""        # dates / organisation, for building the CV


@dataclass
class Judged:
    text: str
    must: bool
    met: bool | None          # None = cannot be judged
    evidence: str = ""
    signals: list[str] = field(default_factory=list)
    weak_only: bool = False   # rests on keywords/wishes, not on evidence


def build_index(answers: dict) -> list[Evidence]:
    """Turn the profile into searchable evidence — per SENTENCE, not per FIELD.

    `cv_text` used to be ONE chunk. On a match the evidence returned was the
    first 80 characters of the whole CV — the scoring layer *knew* the profile
    contained something, but not WHICH SENTENCE proved it. So the CV builder
    had to pick again from scratch with its own weights, and the two drifted:
    measured 10 Sep, a posting scoring 92 received a CV where 76% of the
    sentences touched nothing in it.

    Per sentence, one index serves all three jobs:

        scoring    how many of their questions can be answered
        CV build   those exact sentences, in the order they asked
        the grid   which questions NO sentence answers
    """
    from ..cv.blocks import parse as parse_cv, sentences as split_cv

    out: list[Evidence] = []

    # Each sentence of the CV, carrying the block it came from — so the CV
    # builder knows which heading to file it under.
    for block in parse_cv(str(answers.get("cv_text") or "")):
        if block.kind not in ("experience", "project"):
            continue
        for line in split_cv(block):
            text = line.strip()
            if len(text) < 25:            # a PDF-extraction fragment, not a sentence
                continue
            out.append(Evidence(block.title or block.kind, text, norm(text), True,
                                kind=block.kind, meta=block.meta))

    # The remaining fields stay per field: they are lists, not prose.
    fields = [
        ("your strong skills", "skills_strong", True),
        ("your education", "education", True),
        ("your certifications", "certifications", True),
        ("skills you're still learning", "skills_weak", False),
    ]
    # `search_keywords` AND `stack_want` ARE EXCLUDED FROM THE EVIDENCE.
    #
    # Their own labels declare "(not proof)" — and they were still loaded
    # into the evidence index, so a requirement line counted as MET off words
    # Vin typed into a JOB SEARCH box. Measured on the real store: 249
    # requirement lines across 153 of 472 postings passed that way.
    #
    # "I want a job with Kafka" is not evidence I know Kafka. Leave them in
    # the index and every coverage number inflates, and the "what the profile
    # still lacks" table — the thing telling Vin what to WRITE — points at
    # fake gaps.
    #
    # Scores will DROP after this fix. Those are the real scores.
    for label, key, strong in fields:
        value = answers.get(key)
        if not value:
            continue
        text = " ".join(value) if isinstance(value, list) else str(value)
        out.append(Evidence(label, text.strip(), norm(text), strong))
    return out


def _signals(text: str) -> list[str]:
    """The skills/concepts this requirement line is actually asking for.

    The matching rule lives in vocab.alias_hits — shared with
    cv.build.skills_in, so the scoring layer and the CV builder can never
    understand the same
    a single word.
    """
    return alias_hits(norm(text))


def _find(signal: str, index: list[Evidence]) -> tuple[bool, str, bool]:
    """Does the profile have evidence for this signal, where, and is it STRONG."""
    hit = _match(signal, index)
    if hit is None:
        return False, "", False
    return True, f"{hit.where} — {hit.text}", hit.strong


def _match(signal: str, index: list[Evidence]) -> Evidence | None:
    """The FIRST piece of evidence that answers this signal."""
    for ev in _matches(signal, index):
        return ev
    return None


def _matches(signal: str, index: list[Evidence]):
    """EVERY piece that answers this signal. The CV builder needs the list."""
    forms = SKILLS.get(signal, {signal}) | {signal}
    for ev in index:
        for form in forms:
            needle = f" {form.strip()} " if len(form.strip()) <= 3 else form.strip()
            if needle in f" {ev.normal} ":
                yield ev
                break


def _years_needed(text: str) -> int | None:
    found = YEARS.search(text)
    return int(found.group(1)) if found else None


# Remove a full stop sitting BETWEEN two letters, before norm(). norm()
# replaces full stops with spaces, so "B.S., M.S. or PhD" becomes
# "b s m s or phd" — bachelors and masters gone, only phd left. The
# consequence: a JD saying "B.S., M.S. OR PhD" was read as "PhD required",
# that posting became a blocker and was capped at 55 points, even though Vin
# has an MSc and more than qualifies. "B.Sc." was worse still: no degree
# recognised at all.
#
# Only stops WITH A LETTER ON BOTH SIDES are removed, so sentence-ending full
# stops are untouched:
#   B.S. -> BS.    M.Sc. -> MSc.    Ph.D. -> PhD.    "...field. The" unchanged
_DOTTED = re.compile(r"(?<=[A-Za-z])\.(?=[A-Za-z])")


def _undot(text: str) -> str:
    return _DOTTED.sub("", text or "")


def _degrees_needed(text: str) -> list[str]:
    """EVERY degree mentioned, not the highest one.

    A BUG THAT WAS FIXED (1): it used to take the highest degree and demand
    exactly that, so "Undergraduate, MS, or PhD candidates" failed despite an
    MSc — the JD wrote "or" and we read "must be a PhD".

    A BUG THAT WAS FIXED (2): abbreviations with full stops. See _undot.
    """
    low = f" {norm(_undot(text))} "
    return [level for level in ("phd", "masters", "bachelors")
            if any(f" {word.strip()} " in low for word in DEGREE_WORDS[level])]


def judge_one(req: extract.Requirement, index: list[Evidence], answers: dict) -> Judged:
    text = req.text

    # --- a years requirement ---
    needed = _years_needed(text)
    if needed is not None:
        have = YEARS_BAND.get(str(answers.get("years_real") or ""), 0)
        met = have >= needed
        return Judged(text, req.must, met,
                      f"you have about {have:g} years, they ask for {needed}+",
                      [f"{needed}+ years"])

    # --- a degree requirement ---
    levels = _degrees_needed(text)
    if levels:
        education = norm(str(answers.get("education") or ""))
        padded = f" {education} "
        has = {"phd": any(f" {w} " in padded for w in ("phd", "doctorate")),
               "masters": any(f" {w} " in padded for w in ("msc", "master", "masters", "mba")),
               "bachelors": any(f" {w} " in padded for w in
                                ("bsc", "ba", "bachelor", "bachelors", "msc", "master", "phd"))}
        quant = any(f in education for f in QUANT_FIELD)
        met = any(has[level] for level in levels)      # the JD wrote "or", so or
        note = "quantitative field" if quant else "field not obviously quantitative"
        # "".splitlines() is [] and not [""] — taking [0] is an IndexError,
        # and it fires inside derive()'s transaction so THE WHOLE scan rolls
        # back. The line just below already handled an empty field; it simply
        # never got there.
        lines = str(answers.get("education") or "").splitlines()
        raw = lines[0][:80] if lines else ""
        return Judged(text, req.must, met,
                      f"{raw} — {note}" if raw else "nothing on your profile about education",
                      levels)

    # --- a skill requirement ---
    signals = _signals(text)
    if not signals:
        return Judged(text, req.must, None, "no recognisable skill in this line", [])

    hits = [(s, *_find(s, index)) for s in signals]
    strong = [(s, e) for s, ok, e, is_strong in hits if ok and is_strong]
    weak = [(s, e) for s, ok, e, is_strong in hits if ok and not is_strong]
    if strong:
        return Judged(text, req.must, True, strong[0][1], signals)
    if weak:
        # Only weak evidence -> counts as MET BUT FLAGGED, because it rests
        # on what Vin said he wants rather than on what he can prove.
        return Judged(text, req.must, True, weak[0][1], signals, weak_only=True)
    return Judged(text, req.must, False,
                  f"nothing on your profile mentions: {', '.join(signals[:4])}", signals)


def _bac_tieu_de(title: str) -> int | None:
    """The level read from the title, or None if the title does not say.

    Several matches take the LOWEST. "Graduate Programme — Senior Analyst
    track" is a graduate posting, not a senior one; guessing wrong that way
    costs someone targeting entry level the posting they needed, while
    guessing wrong the other way only shows someone targeting senior one
    stray posting. Losing a posting is worse than seeing a spare one.
    """
    thay = [bac for bac, mau in BAC_TIEU_DE if mau.search(title or "")]
    return min(thay) if thay else None


def _level_fit(title: str, answers: dict) -> tuple[float, str]:
    """The level-fit score, 0..1 — and a TRUE sentence saying why.

    Three cases, none of them silent: the title does not state a level, the
    profile does not state a target, and both do (only then can we subtract).
    """
    muon = sorted({BAC[w] for w in (answers.get("seniority") or []) if w in BAC})
    tin = _bac_tieu_de(title)

    if tin is None:
        return 0.6, "level not stated in the title"
    if not muon:
        # The profile is empty, or holds only free text this scale does not
        # know. Say exactly that — 0.6 with "the title does not say" is a LIE.
        return 0.6, (f"posting is {TEN_BAC[tin]} level, but you haven't said "
                     "which levels you'd accept")

    lech = min(abs(tin - m) for m in muon)
    cua_ban = ", ".join(TEN_BAC[m] for m in muon)
    if lech == 0:
        return 1.0, f"posting is {TEN_BAC[tin]} level — matches your target"
    if lech == 1:
        return 0.5, (f"posting is {TEN_BAC[tin]} level, you target "
                     f"{cua_ban} — one step off")
    return 0.0, f"posting is {TEN_BAC[tin]} level, you target {cua_ban}"


def _title_fit(title: str, answers: dict) -> tuple[float, str]:
    targets = [norm(t) for t in str(answers.get("job_titles") or "").splitlines() if t.strip()]
    low = norm(title)
    hit = next((t for t in targets if t and t in low), None)
    if hit:
        return 1.0, f"title contains your target '{hit}'"
    words = set(low.split())
    best, name = 0.0, ""
    for t in targets:
        tw = set(t.split())
        if tw:
            overlap = len(words & tw) / len(tw)
            if overlap > best:
                best, name = overlap, t
    return best, (f"partly matches '{name}'" if best else "no overlap with your target titles")


def score_job(title: str, description: str, answers: dict) -> dict:
    reqs = extract.requirements(description)
    # The other half of the JD: what this posting says you WILL DO. Not used
    # for scoring — scoring a candidate on a job description is wrong. Kept
    # because it describes what a project looks like (see projects/frame.py).
    todo = extract.duties(description)
    confidence = extract.confidence(reqs)
    if confidence == "none":
        return {"score": None, "confidence": "none", "requirements": [],
                "duties": todo,
                "reason": "Could not read any requirements from this posting — read it yourself.",
                "breakdown": {}}

    index = build_index(answers)
    judged = [judge_one(r, index, answers) for r in reqs]

    must = [j for j in judged if j.must and j.met is not None]
    nice = [j for j in judged if not j.must and j.met is not None]
    unknown = [j for j in judged if j.met is None]

    must_ratio = (sum(1 for j in must if j.met) / len(must)) if must else 0.5
    nice_ratio = (sum(1 for j in nice if j.met) / len(nice)) if nice else 0.5
    level_ratio, level_why = _level_fit(title, answers)
    title_ratio, title_why = _title_fit(title, answers)

    points = (55 * must_ratio + 15 * nice_ratio + 20 * level_ratio + 10 * title_ratio)

    # cap only when a PhD is the ONLY degree accepted
    blockers = [j.text for j in must if j.met is False
                and (_years_needed(j.text) or _degrees_needed(j.text) == ["phd"])]
    capped = False
    if blockers:
        # Demanding a PhD, or years you do not have -> however well
        # everything else matches, the filter is hard to pass
        if points > 55:
            capped = True
        points = min(points, 55)

    return {
        "score": int(round(points)),
        "confidence": confidence,
        "requirements": [
            {"text": j.text, "met": j.met, "must": j.must, "evidence": j.evidence}
            for j in judged],
        "duties": todo,
        "blockers": blockers,
        "capped": capped,
        "weak_evidence": sum(1 for j in judged if j.weak_only),
        "unknown": len(unknown),
        "breakdown": {
            "must": {"met": sum(1 for j in must if j.met), "total": len(must),
                     "points": round(55 * must_ratio, 1)},
            "nice": {"met": sum(1 for j in nice if j.met), "total": len(nice),
                     "points": round(15 * nice_ratio, 1)},
            "level": {"points": round(20 * level_ratio, 1), "why": level_why},
            "title": {"points": round(10 * title_ratio, 1), "why": title_why},
        },
    }
