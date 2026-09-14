"""Render the tailored CV as HTML — the part that looks like a real SHEET.

The sheet ONLY. The explanation — what was dropped, why, which sentence was
reworded — lives in `cv/report.py`: that talks to a person, while this builds
the thing that gets sent. `audit()` used to sit in here and could only say
half of it (what was dropped), with no before/after.
"""

from __future__ import annotations

from html import escape as esc

from .build import TailoredCV, dang_ke, skills_in

LABEL = {"experience": "Experience", "project": "Selected projects",
         "education": "Education", "cert": "Certifications", "skill": "Technical skills"}


def paper(cv: TailoredCV, cham: bool = False,
          du_bi=None, job: str = "") -> str:
    """The CV sheet. `cham=True` MARKS IT UP in place, like marking work.

    ONE sheet, not two. The previous version drew the CV above and then
    listed every sentence below — the same sentence twice, leaving the reader
    to match "sentence 3 below" with one above. When you mark work, the red
    pen goes ON the work.

    The marking is pure CSS (a left border + a hover background), so the
    printed version is still a clean sheet: @media print removes every mark.
    The "before" text sits in the DOM already so the Before/After button can
    toggle it without another server call.
    """
    head = "".join(f"<div class=cvline>{esc(h)}</div>" for h in cv.header if h)
    out = [f"<div class=cvhead>{head}</div>"]
    if cv.summary:
        out.append(f"<p class=cvsum>{esc(cv.summary)}</p>")

    last = ""
    for section in cv.sections:
        if section.kind != last:
            out.append(f"<h4 class=cvsec>{esc(LABEL.get(section.kind, section.kind))}</h4>")
            last = section.kind

        if section.kind in ("experience", "project", "education"):
            meta = f"<span class=cvmeta>{esc(section.meta)}</span>" if section.meta else ""
            if section.title:
                out.append(f"<div class=cvrole><b>{esc(section.title)}</b>{meta}</div>")
            items = "".join(
                # HIGHLIGHT from the WIDE set (`wanted`, the whole posting),
                # not the narrow one (`asked`, the requirement lines only).
                # Two different jobs:
                #   asked  -> the DENOMINATOR of the fraction. Being wide
                #             here would be a lie.
                #   wanted -> what the EYE sees. Being narrow here highlights
                #             exactly 1 word on the whole sheet, and
                #             "highlight the keywords" becomes meaningless.
                # A wrongly highlighted word costs one green streak; nobody
                # is misled.
                _muc(l, cham, set(cv.wanted),
                     # THIS BLOCK'S OWN BENCH. Swapping an experience
                     # sentence for a project sentence swaps the wrong
                     # thing — each block has its own line budget.
                     [b for b in (du_bi or []) if b["khoi"] == section.title],
                     job)
                for l in section.lines)
            out.append(f"<ul class=cvlist>{items}</ul>")
        else:
            body = " ".join(l.text for l in section.lines)
            label = f"<b>{esc(section.title)}</b> — " if section.title else ""
            out.append(f"<div class=cvskill>{label}{esc(body)}</div>")
    lop = "cvpaper cham" if cham else "cvpaper"
    return f"<div class='{lop}'>{''.join(out)}</div>"


# The sentence number, counted across the whole sheet — so "sentence 3" in
# the detail is sentence 3 on the paper. A module variable rather than
# threading it through four layers of function.
_DEM = [0]


def _muc(line, cham: bool, doi=(), du_bi=(), job: str = "") -> str:
    """One line of the CV — MARKED IN PLACE, Grammarly-style.

    Four things, all on that line itself and not in an appendix:

        highlight  the keywords this posting ASKS FOR, wrapped in <mark> —
                   one glance says whether the sheet states what they asked
        click      opens a card directly under the line, no navigation
        how to fix what is still missing, and the specific thing to do
        re-pick    OTHER sentences Vin has written, ordered by how well they
                   hit this posting — click to swap

    NO JAVASCRIPT: the card opens with <details>, the swap is a real <form>.
    A feature with no listener has nothing to break, and it behaves
    identically on paper (printing closes the cards).
    """
    if not cham:
        return (f"<li{' class=review' if line.review else ''}>{esc(line.text)}"
                + (f"<span class=rv>{esc(line.review)}</span>"
                   if line.review else "") + "</li>")

    _DEM[0] += 1
    n = _DEM[0]
    doi = set(doi)
    lop = []
    if line.sua:
        lop.append("dsua")
    if line.yeu:
        lop.append("dhong")
    if line.review:
        lop.append("dxem")

    # --- the marking card ---
    trung = sorted(set(line.hits) | (skills_in(line.text) & doi))
    kho = ("".join(f"<span class='badge ok'>{esc(h)}</span>" for h in trung)
           if trung else
           "<span class=muted>hits nothing this posting asks for — this "
           "line is here because it carries scale or judgement</span>")

    # ONE SPOT AT A TIME, quoting the underlined text VERBATIM — so the eye
    # can connect the card to the streak on the sentence without hunting.
    vt = list(getattr(line, "vet", ()) or ())
    yeu = "".join(
        f"<div class='cspot v{esc(v.loai)}'>"
        f"<span class=cquote>{esc(line.text[v.dau:v.cuoi][:60])}</span>"
        f"<b>{esc(v.noi)}</b> — {esc(v.lam_gi)}</div>" for v in vt)
    sua = ""

    goc = line.goc or line.text
    doi_cau = ""
    if du_bi:
        nut = "".join(
            f"<form class=calt method=post action='/api/cv/pick'>"
            f"<input type=hidden name=job value='{esc(job)}'>"
            f"<input type=hidden name=out value='{esc(goc)}'>"
            f"<input type=hidden name=text value='{esc(b['text'])}'>"
            f"<button class='mbtn tiny'>swap in</button>"
            f"<span class=calttext>{to_khoa(b['text'], doi)}</span>"
            + ("".join(f"<span class='badge ok'>{esc(t)}</span>"
                       for t in b["trung"]) if b["trung"] else
               "<span class=muted>hits nothing extra</span>")
            + "</form>" for b in du_bi[:4])
        doi_cau = (f"<div class=cswap><b>swap in another sentence you wrote</b>"
                   f"{nut}</div>")

    the = (f"<div class=ccard><div class=ckw>this posting asks for: {kho}</div>"
           f"{sua}{yeu}{doi_cau}</div>")

    truoc = (f"<span class=ctruoc>{esc(goc)}</span>"
             if goc != line.text else "")
    return (f"<li class='{' '.join(lop)}' id='cau{n}'>"
            f"<details class=cdet><summary>"
            f"<span class=csau>{to_khoa(line.text, doi, getattr(line, 'vet', ()))}</span>{truoc}"
            f"<span class=cno>{n}</span></summary>{the}</details></li>")


def dem_lai() -> None:
    """Reset the sentence counter. Call BEFORE building each sheet."""
    _DEM[0] = 0

# --- TÔ TỪ KHOÁ ---------------------------------------------------------

def _vet(text: str, doi: set) -> list:
    """The spans in `text` that are keywords this posting ASKS FOR.
    [(start, end), …]

    `alias_hits` only returns the CANONICAL NAME ("machine learning"); it
    does not say where in the sentence it sits. Highlighting needs the
    position, so the alias patterns are re-run here — the same matching rule,
    not a second one.
    """
    from ..scoring.vocab import _ALIAS_RE
    thap = text.lower()
    ra = []
    for pattern, canonical in _ALIAS_RE.values():
        if canonical not in doi:
            continue
        for m in pattern.finditer(thap):
            ra.append((m.start(), m.end()))
    if not ra:
        return []
    # Merge overlapping spans: "machine learning" and "learning" overlap,
    # and highlighting both produces nested tags and broken HTML.
    ra.sort()
    gop = [ra[0]]
    for a, b in ra[1:]:
        if a <= gop[-1][1]:
            gop[-1] = (gop[-1][0], max(gop[-1][1], b))
        else:
            gop.append((a, b))
    return gop


def to_khoa(text: str, doi: set, vet=()) -> str:
    """The sentence, escaped, with KEYWORDS highlighted and PROBLEM SPOTS
    underlined.

    Built CHARACTER BY CHARACTER and then grouped into runs, rather than
    wrapping each streak in turn. The reason: overlapping streaks are normal
    — one phrase can be a requested keyword, inside a "no measurement" span,
    and inside a "too long" span at once. Wrapping in sequence produces tags
    that cross and broken HTML; grouping per character produces exactly one
    flat layer of tags for every combination.
    """
    n = len(text)
    if not n:
        return ""
    la_khoa = [False] * n
    for a, b in _vet(text, doi):
        for i in range(a, min(b, n)):
            la_khoa[i] = True
    loai = [set() for _ in range(n)]
    for v in vet or ():
        for i in range(max(0, v.dau), min(v.cuoi, n)):
            loai[i].add(v.loai)

    ra, i = [], 0
    while i < n:
        khoa = tuple(sorted(loai[i])), la_khoa[i]
        j = i
        while j < n and (tuple(sorted(loai[j])), la_khoa[j]) == khoa:
            j += 1
        chu = esc(text[i:j])
        lop = (["kw"] if khoa[1] else []) + [f"v{k}" for k in khoa[0]]
        ra.append(f"<span class='{' '.join(lop)}'>{chu}</span>" if lop else chu)
        i = j
    return "".join(ra)
