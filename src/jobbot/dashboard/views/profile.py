"""Profile — HTML generated from the schema. ONLY DRAWING, no business rules.

Adding a question means editing profile/schema.py; this file is not touched.
About to write `if question.id == "..."` here -> wrong place.
"""

from __future__ import annotations

from html import escape as esc
from typing import Any

from ...profile.schema import (
    BLOCKS, LONGTEXT, MULTI, ROWS, SINGLE, TEXT, SECTIONS, Question, Section,
    all_questions, suggestions,
)
from ..layout import page

Answers = dict[str, Any]
# How many suggestions to show before anything is typed. Showing all 60 at
# once overwhelms the eye; the rest are found by typing.
_TEN_KHO = {"titles": "job titles", "skills": "keywords",
            "industries": "industries"}
# Up to how many items a store still offers "select all". Above that,
# selecting everything disables the filter by hand — keeping every posting
# makes filtering pointless.
_CHON_HET = 12
OTHER_SUFFIX = "__other"


def _values(answers: Answers, qid: str) -> list[str]:
    value = answers.get(qid)
    if value is None or value == "":
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def _field(question: Question, answers: Answers,
           kho: dict[str, list[str]] | None = None) -> str:
    chosen = set(_values(answers, question.id))
    parts: list[str] = []

    if question.kind in (SINGLE, MULTI):
        input_type = "radio" if question.kind == SINGLE else "checkbox"
        parts.append("<div class=opts>")
        for option in question.options:
            checked = " checked" if option.value in chosen else ""
            note = f"<span class=note>{esc(option.note)}</span>" if option.note else ""
            parts.append(
                f"<label class=opt><input type={input_type} name={esc(question.id)} "
                f"value='{esc(option.value)}'{checked}>"
                f"<span><span class=lbl>{esc(option.label)}</span>{note}</span></label>"
            )
        parts.append("</div>")

        if question.allow_other:
            known = {o.value for o in question.options}
            extra = ", ".join(v for v in _values(answers, question.id) if v not in known)
            parts.append(
                f"<input class='txt other' type=text name='{esc(question.id)}{OTHER_SUFFIX}' "
                f"value='{esc(extra)}' placeholder='Add your own — separate with commas'>"
            )

    elif question.kind == BLOCKS:
        parts.append(_o_khoi(question, answers, kho))

    elif question.kind == ROWS:
        parts.append(_o_hoc_van(question, answers))

    elif question.tags:
        parts.append(_o_the(question, answers, kho))

    elif question.kind == TEXT:
        parts.append(
            f"<input class=txt type=text name={esc(question.id)} "
            f"value='{esc(str(answers.get(question.id, '')))}' "
            f"placeholder='{esc(question.placeholder)}'>"
        )

    elif question.kind == LONGTEXT:
        rows = 6 if question.placeholder.count("\n") < 3 else 8
        parts.append(
            f"<textarea class=txt rows={rows} name={esc(question.id)} "
            f"placeholder='{esc(question.placeholder)}'>"
            f"{esc(str(answers.get(question.id, '')))}</textarea>"
        )

    return "".join(parts)


def _question(question: Question, answers: Answers,
              kho: dict[str, list[str]] | None = None) -> str:
    tag = "<span class=req>required</span>" if question.required else ""
    why = f"<p class=why>{esc(question.why)}</p>" if question.why else ""
    return (
        f"<section class=q><h3>{esc(question.text)}{tag}</h3>"
        f"{why}{_field(question, answers, kho)}</section>"
    )


def _steps(current_id: str, done_ids: set[str]) -> str:
    items = "".join(
        f"<li class='{'done' if s.id in done_ids else ''}"
        f"{' now' if s.id == current_id else ''}'>"
        f"<a href='/profile/{esc(s.id)}'>{esc(s.title)}</a></li>"
        for s in SECTIONS
    )
    return f"<ol class=steps>{items}</ol>"


def render_section(section: Section, answers: Answers, done_ids: set[str],
                   next_label: str, gate_missing: list[str] | None = None,
                   kho: dict[str, list[str]] | None = None) -> str:
    optional = "<span class=opt-tag>optional</span>" if section.optional else ""
    # Hidden questions exist in the schema so they can be SAVED, but they
    # are not drawn on the form.
    questions = "".join(_question(q, answers, kho)
                        for q in section.questions if not q.hidden)

    # If a required question is still missing after saving, the user is sent
    # BACK here. Being returned without knowing why reads as a bug, not a
    # flow — so it has to say how many are left and where they are.
    nhac = ""
    if gate_missing:
        qs = all_questions()
        ten = " · ".join(esc(qs[q].text) for q in gate_missing if q in qs)
        nhac = (f"<div class='gate block'><b>{len(gate_missing)} more "
                f"question(s) and the app can run.</b> {ten}</div>")

    return page(
        section.title,
        _steps(section.id, done_ids)
        + f"<h1>{esc(section.title)}{optional}</h1>"
        + nhac
        + f"<p class=lead>{esc(section.why)}</p>"
        + f"<form method=post>{questions}"
        + f"<div class=actions><button class=primary type=submit>{esc(next_label)}</button>"
        + "<a class=skip href='/profile'>Review profile</a></div></form>",
        active="/profile",
    )


def _o_the(question: Question, answers: Answers,
           kho: dict[str, list[str]] | None = None) -> str:
    """A SEARCH box on top · suggestions in the middle · what is CHOSEN
    below. Three areas, three jobs.

    Merging the input into the tag box makes that box both where you type and
    where results appear: a few tags and there is no room left, and the
    suggestion row gets squeezed. And typing half a word then clicking away
    turns the fragment into a tag — "analys" and "Quant" got into the real
    profile exactly that way.
    """
    thoi = question.tags
    co = _tach(str(answers.get(question.id, "")), thoi)
    da = {v.lower() for v in co}

    chips = "".join(
        f"<span class=tag>{esc(t)}"
        f"<input type=hidden name={esc(question.id)} value='{esc(t)}'>"
        # type=button — without it, clicking × submits the whole form
        f"<button type=button class=untag data-untag title='remove'>×</button>"
        f"</span>" for t in co)
    chon = (f"<div class=chosenhead>chosen</div>"
            f"<div class=tagbox data-tags='{esc(question.id)}'>{chips}"
            f"<span class=tagempty{' hidden' if co else ''}>"
            f"search above and click to add</span></div>")

    nguon = (kho or {}).get(question.suggest) or suggestions(question.suggest)
    goi_y = [g for g in nguon if g.lower() not in da]
    if not goi_y:
        # No title store yet: do NOT show a hand-typed list for the sake of
        # it. Offer to take them from real postings — that is what actually
        # answers "write them as they appear on postings".
        moi = ("<button type=button class='mbtn tiny' "
               "data-post='/api/titles/refresh' data-arg='lay'>"
               "Build the title store from real postings (~15s)</button>"
               if question.suggest == "titles" else "")
        return f"<div class=tagfield data-tagfield>{moi}{chon}</div>"

    nut = "".join(
        f"<button type=button class=addtag data-addtag='{esc(g)}'>{esc(g)}</button>"
        for g in goi_y)
    ten = _TEN_KHO.get(question.suggest, "suggestions")
    # For a small store "select all" is one click instead of seven. A large
    # store (titles, skills) does NOT get this button: selecting all 60 titles
    # renders the filter meaningless and keeps every posting.
    tat_ca = ("<button type=button class='mbtn tiny' data-addall>"
              f"select all {len(goi_y)}</button>" if len(goi_y) <= _CHON_HET else "")
    return (
        f"<div class=tagfield data-tagfield>"
        f"<div class=findrow>"
        f"<input class='txt tagfind' type=text autocomplete=off"
        f" placeholder='type to search {len(goi_y)} {ten}…'>{tat_ca}</div>"
        f"<div class=sugdrop data-sugdrop>{nut}"
        f"<div class=sugnone hidden>not in the store — press Enter to add"
        f" it verbatim</div></div>{chon}</div>")


# The education field: ONE ROW PER DEGREE. Field names repeat across rows —
# the browser submits them as parallel arrays in row order, and the server
# zips them back together.
_COT = (("degree", "Degree", "MSc"),
        ("discipline", "Field of study", "Computational Finance"),
        ("school", "University", "Royal Holloway, University of London"),
        ("start", "From", "Sep 2025"),
        ("end", "To", "Sep 2026"),
        ("note", "Marks / class", "IPM 86 · Data Analysis 83"))


def _hang_hoc_van(e=None) -> str:
    v = {"degree": getattr(e, "degree", ""), "discipline": getattr(e, "discipline", ""),
         "school": getattr(e, "school", ""), "note": getattr(e, "note", "")}
    v["start"] = _khi(getattr(e, "start_month", 0), getattr(e, "start_year", 0))
    v["end"] = _khi(getattr(e, "end_month", 0), getattr(e, "end_year", 0))
    o = "".join(
        f"<label class='edufield {esc(key)}'><span>{esc(nhan)}</span>"
        f"<input class=txt type=text name='edu_{esc(key)}' value='{esc(v[key])}'"
        f" placeholder='{esc(vd)}' autocomplete=off></label>"
        for key, nhan, vd in _COT)
    return (f"<div class=edurow>{o}"
            f"<button type=button class=edudrop data-rowdrop title='remove this degree'>×</button>"
            f"</div>")


def _khi(thang: int, nam: int) -> str:
    if not nam:
        return ""
    return f"{_THANG[thang - 1]} {nam}" if thang else str(nam)


_THANG = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _o_hoc_van(question: Question, answers: Answers) -> str:
    """Degrees as ROWS of separate fields, not one raw text block.

    Why not raw text: this field's grammar is LOAD-BEARING — apply/answer
    reads the graduation date out of it to fill in application forms. Typed
    raw, one wrong dash loses the month, and Vin picks the date by hand on
    every single application.

    The form writes with `answer.line()` and reads with
    `answer.educations()` — one grammar, both directions, no second copy to
    drift.
    """
    from ...apply.answer import educations
    co = educations(str(answers.get(question.id, "")))
    hang = "".join(_hang_hoc_van(e) for e in co) or _hang_hoc_van()
    return (f"<div class=edurows data-rows>{hang}</div>"
            f"<button type=button class='mbtn tiny' data-rowadd>+ add a degree</button>")


def _o_khoi(question: Question, answers: Answers,
            kho: dict | None = None) -> str:
    """Experience / projects: one BLOCK each, one row per block.

    This is personal information, so the place to edit it is the profile. The
    place it is STORED is still a block inside cv_text — the scorer and the CV
    builder both read it there, so writing a second copy guarantees the two
    drift apart eventually.

    Each line in the description box is ONE SENTENCE that can go on the CV.
    The machine picks which sentence fits which posting — writing more
    sentences makes the CV hit harder, not picking more cleverly.
    """
    from ...cv.blocks import parse as parse_cv
    loai = question.block_kind
    co = [b for b in parse_cv(str(answers.get("cv_text") or "")) if b.kind == loai]
    hang = "".join(_hang_khoi(question, b) for b in co) or _hang_khoi(question)
    ten = "a job" if loai == "experience" else "a project"
    return (f"<div class=blockrows data-rows>{hang}</div>"
            f"<button type=button class='mbtn tiny' data-rowadd>+ add {ten}</button>")


def _hang_khoi(question: Question, b=None) -> str:
    key = question.id
    title = getattr(b, "title", "")
    meta = getattr(b, "meta", "")
    body = "\n".join(getattr(b, "lines", []) or [])
    nhan_meta = ("Where · when" if question.block_kind == "experience"
                 else "Note · when")
    return (
        "<div class=blockrow>"
        f"<label class='edufield btitle'><span>Name</span>"
        f"<input class=txt type=text name='{esc(key)}__title' value='{esc(title)}'"
        f" placeholder='Quantitative Analyst — Schonfeld' autocomplete=off></label>"
        f"<label class='edufield bmeta'><span>{esc(nhan_meta)}</span>"
        f"<input class=txt type=text name='{esc(key)}__meta' value='{esc(meta)}'"
        f" placeholder='Jan 2025 – Sep 2025' autocomplete=off></label>"
        f"<button type=button class=edudrop data-rowdrop title='remove this block'>×</button>"
        f"<label class='edufield bbody'><span>What you did — one sentence per line</span>"
        f"<textarea class=txt rows=4 name='{esc(key)}__body'"
        f" placeholder='{esc(question.placeholder)}'>{esc(body)}</textarea></label>"
        f"</div>")


def _tach(gia_tri: str, thoi: str) -> list[str]:
    """A stored string -> a list of tags. It can READ the older shape too.

    Old data was stored as "A · B · C" on one line (that is how the CV wrote
    it, and the importer copied it verbatim). Splitting only on the new
    separator turns the whole thing into ONE enormous tag, while cv/build.py
    reads line by line and therefore still believes there is one certificate.

    Read loosely, write strictly: it accepts both shapes but always saves in
    `thoi`. The first press of Save straightens old data into the right shape
    — no migration, and nothing for the user to do.
    """
    chinh = thoi.strip() or "\n"
    phan = [v for v in gia_tri.split(chinh)]
    if len(phan) <= 1:                       # nothing split -> try the old shape
        for cu in (" · ", " | ", "; "):
            if cu in gia_tri:
                phan = gia_tri.split(cu)
                break
    return [v.strip() for v in phan if v.strip()]


def _shown(question: Question, answers: Answers) -> str:
    values = _values(answers, question.id)
    if not values:
        return "<em class=empty>— not answered —</em>"
    if question.options:
        labels = {o.value: o.label for o in question.options}
        return " · ".join(esc(labels.get(v, v)) for v in values)
    text = values[0]
    return f"<span class=val>{esc(text if len(text) <= 300 else text[:300] + '…')}</span>"


def render_summary(answers: Answers, versions: int, missing_gate: list[str]) -> str:
    questions = all_questions()

    if missing_gate:
        names = " · ".join(esc(questions[q].text) for q in missing_gate)
        gate = (
            f"<div class='gate block'><b>Can't search yet.</b> Still missing: {names}. "
            "<a href='/profile/muc_tieu'>Fill these in</a></div>"
        )
    else:
        gate = "<div class='gate ok'><b>Ready to search.</b> The system may now pull postings (M2).</div>"

    blocks: list[str] = []
    for section in SECTIONS:
        filled = sum(1 for q in section.questions if _values(answers, q.id))
        optional = "<span class=opt-tag>optional</span>" if section.optional else ""
        rows = "".join(
            f"<tr><th>{esc(q.text)}</th><td>{_shown(q, answers)}</td></tr>"
            for q in section.questions
        )
        blocks.append(
            f"<h2>{esc(section.title)}{optional}"
            f"<span class=count>{filled}/{len(section.questions)}</span>"
            f"<a class=edit href='/profile/{esc(section.id)}'>edit</a></h2>"
            f"<table class=sum>{rows}</table>"
        )

    return page(
        "Profile",
        "<h1>Your profile</h1>"
        + "<div class=frow style='margin:0 0 14px'>"
          "<a class='chip on' href='/profile/import'>Import a CV</a>"
          "<a class=chip href='/profile/health'>CV health</a></div>"
        f"<p class=lead>{versions} version(s) saved. Every edit writes a new version rather than "
        "overwriting — this profile is living data, not a form you fill in once.</p>"
        f"{gate}{''.join(blocks)}",
        active="/profile",
    )
