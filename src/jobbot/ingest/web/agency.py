"""Recognise postings put up by an AGENCY rather than the employer.

Why it matters: 17 of 28 postings fetched from eFinancialCareers came from a
recruiting middleman. They rewrite the JD, hide the real company name, and
applying through them puts one more filter between you and the employer.

Two signals, and BOTH are used because each alone misses things:
    the company name — a list of known agencies
    chữ trong JD — "our client", "on behalf of"

Wording alone misses: a posting naming "Invesco" still says "our client".
The name alone misses: a new agency is not on the list.
"""

from __future__ import annotations

import re

from ...ingest.base import norm

# London finance/tech recruiting agencies, seen in the real data
KNOWN = {
    "oxford knight", "eka finance", "anson mccade", "mccabe barton",
    "emagine consulting", "quanteam", "selby jennings", "harrington starr",
    "robert walters", "michael page", "hays", "robert half", "morgan mckinley",
    "goodman masson", "eames consulting", "gqr", "durlston partners",
    "arrows group", "lorien", "sthree", "huxley", "phaidon", "glocomms",
    "understanding recruitment", "salt", "la fosse", "trust in soda",
    "vertus partners", "paragon alpha", "alexander ash", "gerrard white",
}

# Words inside the company NAME
NAME_HINTS = re.compile(
    r"\b(recruit\w*|resourcing|staffing|talent|search|consultanc\w+|"
    r"partners?|associates|solutions group|manpower|headhunt\w*)\b", re.I)

# Phrases only an agency writes
TEXT_HINTS = re.compile(
    r"\b(our client|my client|our customer|on behalf of (?:our|a)|"
    r"we are (?:working with|partnered with|recruiting for)|"
    r"a (?:leading|top[- ]tier|prestigious|world[- ]class) (?:hedge fund|"
    r"investment bank|asset manager|firm|client)|"
    r"confidential client|client is seeking)\b", re.I)


def judge(company: str, description: str) -> tuple[bool, str]:
    """(is an agency, why). It can always give the reason."""
    key = norm(company).replace("ltd", "").replace("limited", "").strip()
    if key in KNOWN:
        return True, f"'{company}' is a known recruitment agency"

    text = description or ""
    phrase = TEXT_HINTS.search(text)
    if phrase:
        return True, f"description says \"{phrase.group().strip()}\""

    if NAME_HINTS.search(company or "") and "bank" not in key:
        return True, f"company name reads like an agency"
    return False, ""
