"""The shared base for every source: the Posting type, HTTP, string
normalisation.

A source does exactly one job: fetch -> return list[Posting]. That is all.
Writing to the DB, grouping and scoring all belong elsewhere.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from html import unescape
from dataclasses import dataclass, field
from typing import Any

UA = "jobbot/0.1 (personal job search; contact via local app)"
TIMEOUT = 25


# ---------------------------------------------------------------- HTTP

def get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# --------------------------------------------------------- normalisation

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# KEEP `+ # /` — they are PART OF THE NAME, not punctuation.
#
# Strip them and "C++" becomes "c", and the `c++` alias in vocab can never
# match again. Measured on the real store: 208 postings asking for C++ while
# Vin's CV HAS C++ — the machine never saw it. Same bug: ci/cd (19 postings),
# c# (9), kdb+ (3).
#
# Only these three characters, no more: they are technology-name suffixes.
# Keep the full stop too and "python." and "python" become different things.
_PUNCT = re.compile(r"[^a-z0-9+#/ ]+")

# Company suffixes — stripped so "Monzo Bank Ltd" and "Monzo Bank" group.
_SUFFIX = re.compile(
    r"\b(ltd|limited|llp|plc|inc|incorporated|llc|gmbh|bv|nv|sa|ag|corp|corporation|"
    r"co|company|group|holdings|international|uk|global)\b")


def strip_html(text: str) -> str:
    """Strip HTML to plain text, KEEPING line breaks and bullet structure.

    A BUG THAT WAS FIXED: tags used to be removed BEFORE &lt; &gt; were
    decoded — so encoded tags (which is what Greenhouse returns) turned into
    real tags after the stripping was done, and sat in the description. The
    decode has to come first, and repeat until it is clean.
    """
    if not text:
        return ""
    for _ in range(3):                       # content encoded several layers deep
        before = text
        text = unescape(text)
        if text == before:
            break

    # keep the structure before dropping tags — losing it loses the
    # requirements list itself
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*/(p|div|h[1-6]|tr)\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "\n· ", text, flags=re.I)
    text = re.sub(r"<\s*/(ul|ol)\s*>", "\n", text, flags=re.I)
    text = _TAG.sub("", text)
    text = unescape(text)                    # entities left inside the content

    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def norm(text: str) -> str:
    """Normalise for matching: lowercase, drop punctuation, collapse space."""
    return _WS.sub(" ", _PUNCT.sub(" ", (text or "").lower())).strip()


# Suffixes glued to the name with no space: "ocadogroup", "manGroup"
_GLUED = re.compile(r"(group|holdings?|capital|partners?|global|international|"
                    r"technologies|solutions|labs?|ltd|inc|plc)$")


def norm_company(name: str) -> str:
    """Drop legal and descriptive suffixes. 'Monzo Bank Ltd' -> 'monzo bank'.

    Also cuts GLUED suffixes: Greenhouse returns the slug "ocadogroup" while
    the posting says "Ocado Group" — without the cut, two copies of the same
    job never group.
    """
    out = _WS.sub(" ", _SUFFIX.sub(" ", norm(name))).strip()
    words = out.split()
    if len(words) == 1 and len(words[0]) >= 8:
        trimmed = _GLUED.sub("", words[0])
        if len(trimmed) >= 4:
            return trimmed
    return out


def norm_title(title: str) -> str:
    """Drop parentheses and requisition codes. 'Analyst (London) - REQ123' ->
    'analyst'."""
    title = re.sub(r"\([^)]*\)", " ", title or "")
    title = re.sub(r"\b(req|job|id|ref)[-_ ]?\d+\b", " ", title, flags=re.I)
    return norm(title)


def to_ts(stamp: str) -> int:
    """Convert any date shape to unix. 0 when unreadable.

    Greenhouse/Lever/Ashby trả ISO 8601; Arbeitnow trả unix dạng chuỗi.
    """
    if not stamp:
        return 0
    text = str(stamp).strip()
    if text.isdigit():
        value = int(text)
        return value // 1000 if value > 10_000_000_000 else value    # ms hay s
    try:
        from datetime import datetime, timezone
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except (ValueError, TypeError, OverflowError):
        return 0


# ---------------------------------------------------------------- Posting

@dataclass
class Posting:
    """One posting, normalised to the same shape whatever source it came from."""
    source_id: str
    title: str
    company: str
    location: str = ""
    remote: bool = False
    salary: str = ""
    url: str = ""
    posted_at: str = ""
    description: str = ""
    raw_body: str = ""          # VERBATIM before HTML stripping — never edited
    payload: dict = field(default_factory=dict)

    def fingerprint(self) -> str:
        """Same company + same title = most likely the same job."""
        return f"{norm_company(self.company)}|{norm_title(self.title)}"

    def text(self) -> str:
        """All the text, for keyword searching."""
        return f"{self.title}\n{self.company}\n{self.location}\n{self.description}"
