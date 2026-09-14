"""Go STRAIGHT to the company's careers page, skipping every middleman.

Why: 19 of 28 postings taken off boards belong to agencies. Going direct
means
    - the company name is unambiguous
    - the JD is the original, not rewritten
    - the right application form is already there (step 5)
    - postings that never reach a board become visible

How it probes, cheap before expensive:
    1. Guess the slug on the common ATSes — plain HTTP, no Chrome needed
    2. If that fails, open the homepage with Chrome and find the careers link
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from ..base import UA

ATS_PROBE = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever":      "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby":      "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}

# ATS fingerprints on a careers page, when Chrome has to be used
ATS_MARKS = [
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/([a-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([a-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-z0-9_-]+)", re.I)),
    ("workday", re.compile(r"([a-z0-9_-]+)\.wd\d+\.myworkdayjobs\.com", re.I)),
    ("smartrecruiters", re.compile(r"careers\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    ("teamtailor", re.compile(r"([a-z0-9-]+)\.teamtailor\.com", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([a-z0-9-]+)", re.I)),
]

CAREERS_PATHS = ["/careers", "/jobs", "/careers/", "/about/careers",
                 "/company/careers", "/join-us", "/work-with-us", "/en/careers"]


# Legal suffixes are dropped, but "Group"/"Capital"/"Partners" are KEPT —
# they are part of the real slug. `norm_company` also strips those (right for
# matching company names, wrong for guessing a slug): "Man Group" -> "man",
# losing "mangroup".
LEGAL_TAIL = re.compile(r"\b(ltd|limited|llp|llc|plc|inc|incorporated|"
                        r"gmbh|bv|nv|sa|ag|co)\b", re.I)


def slug_guesses(name: str) -> list[str]:
    """'Man Group Ltd' -> mangroup, man-group, man."""
    base = LEGAL_TAIL.sub(" ", name or "").lower()
    base = re.sub(r"[^a-z0-9 ]+", " ", base)
    words = base.split()
    if not words:
        return []
    out = ["".join(words), "-".join(words)]
    if len(words) > 1:
        out.append(words[0])                       # "Man Group" -> "man"
        out.append("".join(words[:-1]))            # bỏ từ cuối
        out.append("".join(w[0] for w in words))   # viết tắt
    return [s for s in dict.fromkeys(out) if 2 < len(s) < 40]


def _probe(url: str) -> tuple[int, str]:
    """(posting count, the name the board declares). (0, '') = not this board."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return 0, ""

    rows = data if isinstance(data, list) else next(
        (data[k] for k in ("jobs", "data", "results")
         if isinstance(data.get(k), list)), [])
    if not rows:
        return 0, ""
    first = rows[0] if isinstance(rows[0], dict) else {}
    return len(rows), str(first.get("company_name") or first.get("companyName") or "")


def _same_company(wanted: str, claimed: str) -> bool:
    """Is this board really the company being looked for.

    This step is needed because slug guessing hits the wrong target: "London
    Stock Exchange Group" guesses the slug `london`, which is the board of an
    entirely different company.
    """
    if not claimed:
        return True                      # the board declares no name -> trust it
    a, b = set(norm_key(wanted).split()), set(norm_key(claimed).split())
    return bool(a & b)


def norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).strip()


def resolve_ats(name: str) -> tuple[str, str, int]:
    """Guess the ATS + slug. Returns (ats, slug, count). ('','',0) if none."""
    for slug in slug_guesses(name):
        for ats, template in ATS_PROBE.items():
            count, claimed = _probe(template.format(slug=slug))
            if not count:                   # an empty board does not count
                continue
            if not _same_company(name, claimed):
                continue                    # the slug hit another company's board
            return ats, slug, count
    return "", "", 0


def sniff_page(html: str) -> tuple[str, str]:
    """Which ATS this careers page runs on."""
    for ats, pattern in ATS_MARKS:
        found = pattern.search(html or "")
        if found:
            return ats, found.group(1)
    return "", ""


def resolve_via_chrome(tab, domain: str) -> tuple[str, str, str]:
    """Open the homepage, follow the careers link, see which ATS it runs on.

    Trả về (ats, slug, careers_url).
    """
    from .base import Blocked, open_page

    for path in CAREERS_PATHS:
        url = f"https://{domain}{path}"
        try:
            open_page(tab, url, timeout=25)
        except Blocked:
            return "", "", ""
        except Exception:                    # noqa: BLE001
            continue
        html = tab.html()
        if len(html) < 2000:
            continue
        ats, slug = sniff_page(html)
        if ats:
            return ats, slug, url
        if re.search(r"\b(open roles?|current vacanc|job openings?|"
                     r"view (all )?jobs)\b", html, re.I):
            return "custom", "", url        # a careers page, but an unknown ATS
    return "", "", ""
