"""Separate "MATCHES" from "STANDS A CHANCE".

The match score answers: does this profile have what the JD asks for.
It does NOT answer: is applying worth anything.

A Quantitative Researcher posting at Jane Street can match at 84 while
demanding a PhD, with 500 PhDs applying alongside. A Graduate Analyst posting
matching at 74 is a graduate intake taking 40 people.

Two different numbers, and using only one of them misreads the whole ranking.

No LLM. Every signal here is read straight out of the JD.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# Dấu hiệu tin TUYỂN NGƯỜI MỚI RA TRƯỜNG — cửa rộng nhất
OPEN_DOOR = re.compile(
    r"\b(graduate (?:programme|program|scheme|role|opportunit)|"
    r"campus (?:hire|recruit)|entry[- ]level|no (?:prior )?experience (?:is )?"
    r"(?:required|necessary)|intern(?:ship)? (?:programme|program)|"
    r"placement year|training (?:programme|program)|"
    r"final[- ]year (?:student|undergraduate)|recent graduate|"
    r"we welcome applications from students)\b", re.I)

# Dấu hiệu CỬA HẸP
PHD_HARD = re.compile(r"\b(phd (?:is )?(?:required|essential)|must have a phd|"
                      r"phd in|doctorate (?:required|in))\b", re.I)
PHD_SOFT = re.compile(r"\bph\.?d\b", re.I)
YEARS = re.compile(r"(\d+)\s*\+?\s*(?:or more\s*)?years?[^.]{0,40}"
                   r"(?:experience|exp\b)", re.I)
SENIOR_TITLE = re.compile(r"\b(senior|snr|lead|principal|staff|head of|vp|"
                          r"vice president|director|manager|architect)\b", re.I)

YEARS_HAVE = {"0-1": 0.5, "1-3": 2, "3-5": 4, "5-8": 6.5, "8+": 10}

# Hạn nộp viết trong JD
DEADLINE = re.compile(
    r"(?:deadline|closing date|applications? close|apply by|closes on|"
    r"last day to apply)\D{0,24}"
    r"(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})", re.I)

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def find_deadline(text: str) -> tuple[str, int]:
    """(the deadline text, unix). ('', 0) when there is none."""
    found = DEADLINE.search(text or "")
    if not found:
        return "", 0
    raw = found.group(1).strip()
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
                "%Y-%m-%d", "%d/%m/%Y"):
        try:
            when = datetime.strptime(raw.replace(",", ""), fmt).replace(tzinfo=timezone.utc)
            return raw, int(when.timestamp())
        except ValueError:
            continue
    return raw, 0


def assess(title: str, description: str, explain: dict | None,
           answers: dict) -> dict:
    """Judge 'is there a chance', with the reason. When it cannot tell, it
    says it cannot tell."""
    text = description or ""
    reasons: list[str] = []
    score = 0                       # negative = narrow, positive = open

    if OPEN_DOOR.search(text) or OPEN_DOOR.search(title):
        score += 2
        reasons.append("explicitly a graduate or entry-level opening")

    if SENIOR_TITLE.search(title):
        score -= 3
        reasons.append("the title itself is a senior role")

    if PHD_HARD.search(text):
        score -= 3
        reasons.append("a PhD is stated as required")
    elif PHD_SOFT.search(text):
        score -= 1
        reasons.append("a PhD is mentioned — you would be competing with PhDs")

    have = YEARS_HAVE.get(str(answers.get("years_real") or ""), 0)
    asked = [int(m.group(1)) for m in YEARS.finditer(text)]
    worst = max(asked) if asked else 0
    if worst >= 5 and have < worst:
        score -= 3
        reasons.append(f"asks for {worst}+ years; you have about {have:g}")
    elif worst >= 3 and have < worst:
        score -= 2
        reasons.append(f"asks for {worst}+ years; you have about {have:g}")
    elif worst and have >= worst:
        score += 1
        reasons.append(f"asks for {worst}+ years and you meet it")

    if explain and explain.get("capped"):
        score -= 1

    # MEETING WHAT THEY ASK FOR is evidence too, and it used to count for
    # nothing. This scale only knew how to SUBTRACT — a PhD, years, a senior
    # title — and there was exactly one way to add: the JD had to contain the
    # word "graduate". The measured cost on 10 Sep: 81 postings matching ≥80
    # with no blockers and no cap, of which 75 were still filed as "possible"
    # or "unlikely" — including one at 100 and one at 92 at Point72. The
    # "worth applying to" filter was hiding exactly the best matches.
    #
    # Uses the SHARE OF MUST-HAVES MET, not the total score: the total also
    # contains title fit and level fit, and both of those are already counted
    # separately above.
    must = ((explain or {}).get("breakdown") or {}).get("must") or {}
    total, met = must.get("total") or 0, must.get("met") or 0
    if total >= 3 and not (explain or {}).get("blockers"):
        share = met / total
        if share >= 0.8:
            score += 2
            reasons.append(f"you meet {met} of their {total} stated must-haves")
        elif share >= 0.6:
            score += 1
            reasons.append(f"you meet {met} of their {total} stated must-haves")

    if not description or len(description) < 300:
        return {"band": "unknown", "why": "no description to judge from",
                "score": 0}

    band = "likely" if score >= 2 else "unlikely" if score <= -2 else "possible"
    return {"band": band, "why": " · ".join(reasons[:3]) or "nothing decisive either way",
            "score": score}
