"""Rank every line of the CV — with no JD involved.

Answers the question the CV-against-a-JD page cannot: *which line on the CV
is taking up space without carrying information.*
"""

from __future__ import annotations

from html import escape as esc

from ...cv import rules
from ...cv.blocks import parse, sentences
from ...cv.build import skills_in
from ..layout import badge, card, empty, h1, page

GRADE = {
    "strong": ("strong", "ok", "action verb, numbers or concrete skills"),
    "thin": ("thin", "", "no number, no skill — takes space, says little"),
    "review": ("review", "warn", ""),
    "drop": ("cut", "warn", ""),
}


def _grade(text: str) -> tuple[str, str, float]:
    tags = sorted(skills_in(text))
    verdict, why = rules.sentence_ok(text, tags)
    if verdict == "drop":
        return "drop", why, 0.0
    if verdict == "review":
        return "review", why, 1.0
    weight = rules.sentence_weight(text, set(), tags)
    if weight >= 2.5:
        return "strong", ", ".join(tags[:4]) or "concrete", weight
    return "thin", "no number, no recognisable skill", weight


def render(cv_text: str) -> str:
    if not cv_text.strip():
        return page("CV health", h1("CV health")
                    + empty("No CV on your profile yet — import one first."),
                    active="/profile")

    blocks = parse(cv_text)
    counts = {"strong": 0, "thin": 0, "review": 0, "drop": 0}
    body = []

    for block in blocks:
        lines = sentences(block)
        if not lines or block.kind in ("header",):
            continue
        rows = []
        for text in lines:
            text = rules.clean(text)
            grade, why, weight = _grade(text)
            counts[grade] += 1
            label, kind, _ = GRADE[grade]
            rows.append(
                f"<li class='hl {grade}'>{badge(label, kind)}"
                f"<span class=ht>{esc(text)}</span>"
                f"<span class=hw>{esc(why)}</span></li>")
        title = block.title or block.kind
        body.append(card(f"<div class=hhead><b>{esc(title)}</b>"
                         f"<span class=muted>{esc(block.meta)}</span></div>"
                         f"<ul class=hlist>{''.join(rows)}</ul>", "health"))

    total = sum(counts.values()) or 1
    bar = "".join(
        f"<span class='seg {k}' style='width:{counts[k] / total * 100:.1f}%' "
        f"title='{k}'></span>" for k in ("strong", "thin", "review", "drop") if counts[k])
    summary = card(
        f"<div class=hbar>{bar}</div>"
        + "".join(f"<span class=hkey><i class='dot {k}'></i>{counts[k]} {GRADE[k][0]}</span>"
                  for k in ("strong", "thin", "review", "drop"))
        + "<div class=note>Judged without any job posting — this is about your CV on its "
          "own. \"Cut\" lines are not deleted: they move to the project write-up, where "
          "an experienced reader values them.</div>", "notice")

    return page("CV health",
                h1("CV health", "Every line in your CV, graded on its own merit.")
                + summary + "".join(body),
                active="/profile")
