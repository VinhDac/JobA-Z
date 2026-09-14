"""Split a CV into separate BLOCKS so they can be picked and reordered per JD.

The rule running through this directory: **only PICK and ORDER facts that
already exist. Never add a word that is not in the profile.**

Why blocks are needed: without them there is one lump of text, and a lump is
all-or-nothing. Split, you can answer "which lines does this JD need".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..ingest.base import norm
from ..scoring.vocab import ALIASES

# CV SECTION HEADINGS — many spellings accepted, CASE-INSENSITIVE.
#
# The previous version matched only UPPERCASE and only the exact words the
# author happened to use. Measured on one CV, changing nothing but the
# heading line:
#     EXPERIENCE          -> experience blocks present, score 92
#     WORK EXPERIENCE     -> experience blocks GONE, score 22
#     Experience          -> GONE
#     EMPLOYMENT HISTORY  -> GONE
#     EXPERIENCE:         -> GONE
# With the experience blocks gone the evidence index is empty, every
# requirement line scores NOT MET — and nothing says a word. The app only
# worked for CVs written exactly as the author writes them; that is a special
# case, not a system.
SECTION = re.compile(
    r"^\s*("
    r"(?:work|professional|relevant|employment|career)?\s*"
    r"(?:experience|history)"
    r"|(?:selected|key|personal|side)?\s*projects?"
    r"|education(?:\s+and\s+training)?|academic(?:\s+background)?"
    r"|(?:technical|core|key)?\s*(?:skills?|competenc(?:y|ies))"
    r"|certifications?|licen[cs]es?|publications?|awards?|honou?rs?"
    r"|volunteering|languages?|interests?"
    r")\s*:?\s*$", re.I)

# Dates glued to the end of a title line by PDF extraction
DATE_TAIL = re.compile(
    r"\s+((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}"
    r"(?:\s*[–—-]\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*)?"
    r"(?:\d{4}|Present|present|Now))?"
    r"|\d{4}\s*[–—-]\s*(?:\d{4}|Present))\s*$")

CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.\w+|\+\d[\d ]{6,}|github\.io|linkedin|github", re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Block:
    kind: str                 # header|summary|experience|project|education|cert|skill
    title: str = ""
    meta: str = ""            # dates, organisation
    lines: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)   # skills recognised in the block

    def text(self) -> str:
        return " ".join([self.title, self.meta, *self.lines])


def _tags(text: str) -> list[str]:
    low = f" {norm(text)} "
    found = []
    for alias, canonical in ALIASES.items():
        needle = f" {alias.strip()} " if len(alias.strip()) <= 3 else alias.strip()
        if needle in low and canonical not in found:
            found.append(canonical)
    return found


def _label(line: str) -> tuple[str, str]:
    """'Label — content' -> ('Label', 'content'). No dash means an empty label."""
    for dash in (" — ", " – "):
        head, sep, rest = line.partition(dash)
        if sep and rest.strip():
            return head.strip(), rest.strip()
    return "", line.strip()


def _split_role(line: str) -> tuple[str, str]:
    """'Research Consultant — WorldQuant Jan 2025 – Sep 2025' -> (title, dates)."""
    found = DATE_TAIL.search(line)
    if found:
        return line[:found.start()].strip(), found.group(1).strip()
    return line.strip(), ""


def _looks_like_role(line: str) -> bool:
    """A title line, NOT a prose sentence containing a dash.

    A BUG THAT WAS FIXED: a " — " anywhere made it a title, so the sentence
    "...peak profit in the most recent window — which rewards luck" was cut
    became a new role and tore the experience block in two.
    """
    if DATE_TAIL.search(line):
        return True
    if len(line) > 90 or line.rstrip().endswith((".", ",", ";", ":")):
        return False
    if not (" — " in line or " – " in line):
        return False
    # a title line does not open with a lowercase word or a conjunction
    first = line.split()[0] if line.split() else ""
    return first[:1].isupper() and first.lower() not in {
        "the", "a", "an", "and", "but", "so", "then", "every", "one", "no", "it"}


def mo_khoi_project(line: str, truoc: str | None) -> bool:
    """Does this line open a NEW project block.

    ONE RULE, ONE PLACE — and this is where it nearly destroyed data.
    `parse` and `_bounds` used to guess separately: `parse` accepted a bare
    name on its own line, while `_bounds` only stopped at a line containing
    " — ". The consequence: saving one project deleted every project BELOW it
    in the same section, because `_bounds` saw no boundary and swallowed to
    the end of the file.

    A project name: SHORT, capitalised, NOT ending like a sentence. With a
    dash, the dash itself marks the boundary; without one it has to be
    stricter, because a heading and a content line look identical — it
    demands that the line does not end like a sentence, and that it comes
    after the previous sentence has ended.

    AND IT MUST NOT OPEN WITH AN ACTION VERB. "Improved research
    frameworks — cut runtime to 90 s." has every signal of a heading, and it
    is a SENTENCE. A project name does not begin with "Built", "Improved" or
    "Designed" — those are claims. This is the half that saves a line the
    user just wrote from being read as a block name.
    """
    from . import rules                       # late import: rules reads build back
    head = re.split(r"\s+[—–]\s+", line, maxsplit=1)[0]
    co_gach = head != line
    if not (len(head) <= 70 and head[:1].isupper()):
        return False
    if head.endswith((".", ",", ";", ":")):
        return False
    if rules.mo_bang_hanh_dong(head):
        return False
    if co_gach:
        return True
    sau_cau = truoc is None or truoc.endswith((".", "!", "?"))
    return not line.endswith((".", ",", ";", ":")) and sau_cau


def parse(cv_text: str) -> list[Block]:
    lines = [l.rstrip() for l in (cv_text or "").splitlines()]
    blocks: list[Block] = []
    section = "head"
    current: Block | None = None

    def flush():
        nonlocal current
        if current and (current.lines or current.title):
            current.tags = _tags(current.text())
            blocks.append(current)
        current = None

    truoc_do = None          # the line just above — see the project-open rule
    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        found = SECTION.match(line)
        if found:
            flush()
            # MATCH BY A WORD IN THE HEADING, not by the whole string.
            #
            # The previous version used `name == "experience"`, so widening
            # the heading table broke it immediately: "work experience" does
            # not equal "experience", so it fell to the last branch and
            # became "skill" — the experience section filed as a skills
            # section, worse than when it vanished.
            #
            # The ORDER MATTERS: specific before general. "technical skills"
            # has to be caught by the skill branch before anything else.
            name = " ".join(found.group(1).lower().split())
            section = ("project" if "project" in name
                       else "cert" if ("certification" in name
                                       or "licen" in name)
                       else "education" if ("education" in name
                                            or "academic" in name)
                       else "skill" if ("skill" in name
                                        or "competenc" in name
                                        or "language" in name)
                       else "experience" if ("experience" in name
                                             or "history" in name
                                             or "career" in name)
                       else "skill")
            continue

        # --- the header: name, contact, summary ---
        if section == "head":
            if not blocks and not current:
                blocks.append(Block("header", line))          # the name
                continue
            if CONTACT.search(line) or "visa" in line.lower():
                blocks.append(Block("header", "", "", [line]))
                continue
            if current is None:
                current = Block("summary")
            current.lines.append(line)
            continue

        _truoc = truoc_do
        truoc_do = line
        # --- experience / projects: a title line opens a new block ---
        if section in ("experience", "project"):
            if section == "project":
                starts_new = mo_khoi_project(line, _truoc)
            else:
                starts_new = _looks_like_role(line) and (
                    current is None or len(current.lines) > 0)
            if starts_new:
                flush()
                title, meta = _split_role(line)
                # 'Project name — description': the description is content, not a title
                if section == "project" and " — " in title:
                    name, rest = title.split(" — ", 1)
                    current = Block("project", name.strip(), meta, [rest.strip()])
                else:
                    current = Block(section, title, meta)
                continue
            if current is None:
                current = Block(section)
            current.lines.append(line)
            continue

        # --- education / certificates / skills: one block per line ---
        if line.lower().startswith("certification"):
            flush()
            # 'Certifications — CFA Level I, …'
            #
            # The word "Certifications" IS the section name: render.py sets
            # the heading from the kind ("cert" -> "Certifications"). Leave it
            # in the body and the printed sheet shows two stacked lines:
            #     Certifications
            #     Certifications — CFA Level I, October 2024, …
            # The label becomes the block's title, exactly as the skills
            # blocks do with 'Programming — Python…'. The title is also what
            # write_block needs to write it back in the original shape.
            label, rest = _label(line)
            blocks.append(Block("cert", label, "", [rest]))
            continue
        # skills: each group ('Programming — ...') is its own block
        if section == "skill":
            label = re.match(r"^([A-Z][A-Za-z /]{2,28})\s+[—–-]\s+(.+)$", line)
            if label:
                flush()
                current = Block("skill", label.group(1).strip(), "", [label.group(2).strip()])
            else:
                if current is None:
                    current = Block("skill")
                current.lines.append(line)
            continue

        if section in ("education", "cert"):
            if section == "education" and _looks_like_role(line):
                flush()
                title, meta = _split_role(line)
                current = Block("education", title, meta)
            else:
                if current is None:
                    current = Block(section)
                current.lines.append(line)
            continue

    flush()
    for block in blocks:
        if not block.tags:
            block.tags = _tags(block.text())
    _keu_neu_khong_hieu(cv_text, blocks)
    return blocks


# How many characters count as "a real CV" rather than a few test lines.
DU_DAI = 500


def khong_hieu(cv_text: str, blocks: list) -> bool:
    """A CV with text from which the machine built no experience or project
    block at all.

    THIS is the systemic guard, not the heading table above. The heading
    table only knows the spellings SOMEONE THOUGHT OF; tomorrow someone
    writes "BERUFSERFAHRUNG" or "工作经历" and it goes quiet again. This guard
    does not need to know what the heading is — it asks one question that
    cannot be wrong: a CV this long producing no blocks means something is
    definitely wrong.
    """
    if len((cv_text or "").strip()) < DU_DAI:
        return False
    return not any(b.kind in ("experience", "project") for b in blocks)


def _keu_neu_khong_hieu(cv_text: str, blocks: list) -> None:
    """Not understanding means SHOUTING. A silent failure is the worst kind:
    the score falls from 92 to 22 while the screen stays green, and the user
    goes off fixing the wrong thing."""
    if not khong_hieu(cv_text, blocks):
        return
    try:
        from ..core.journal import CV, log as jlog
        jlog.warn(CV, "NO section recognised in the CV — the headings should be "
                      "EXPERIENCE / PROJECTS / EDUCATION… Every posting will "
                      "score as lacking evidence until this is fixed.")
    except Exception:                       # noqa: BLE001
        pass


def sentences(block: Block) -> list[str]:
    """Break a block's prose into sentences — the smallest unit to pick from.

    It rewrites nothing. Every sentence on the CV is one Vin wrote.
    """
    # PDFs break lines mid-sentence ("...institutions combine\nthousands of
    # simple alphas"), so everything is rejoined before splitting on
    # punctuation.
    joined = re.sub(r"\s+", " ", " ".join(block.lines)).strip()
    return [part.strip() for part in SENTENCE.split(joined) if len(part.strip()) > 25]


# --------------------------------------------------------- writing it back

SECTION_FOR = {"experience": "EXPERIENCE", "project": "SELECTED PROJECTS"}


def _bounds(lines: list[str], title: str) -> tuple[int, int] | None:
    """Which lines the block with this title spans.

    Located by ITS TITLE LINE rather than rebuilding the whole file from
    blocks: parse() drops blank lines and trims trailing whitespace, so
    rebuilding loses the formatting of blocks that were never touched.
    """
    # Matched by PREFIX. Not equality: an experience block carries a date
    # tail ('… Startup Jan 2026 – Present') that the title has already cut,
    # and a project block carries a description after ' — '. Failing to match
    # sends write_block down the add-new branch and produces a duplicate
    # block with the same name.
    head = title.strip()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith(head)), None)
    if start is None:
        return None
    stop = len(lines)
    truoc = lines[start].strip()
    for i in range(start + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        if SECTION.match(line):                       # a different section
            stop = i
            break
        # The next block's boundary — SHARES the rule with parse(). Guessing
        # separately here is what swallowed every project below.
        if mo_khoi_project(line, truoc) or _looks_like_role(line):
            stop = i
            break
        truoc = line
    return start, stop


# SENTENCE-ending punctuation. A body line without it cannot be told apart
# from a project TITLE by `parse` — see `_cau_tron`.
_KET = (".", "!", "?", ":", ";")


def _cau_tron(chu: str) -> str:
    """A body line must END LIKE A SENTENCE, or it gets read back as a NAME.

    A REAL BUG, with data loss. The user saved "Improved research frameworks,
    data pipelines" into the `Quant Trading Studio` block. Reading it back,
    `parse` saw a short line, capitalised, NOT ending like a sentence, after
    the previous sentence had ended — exactly the shape of a project title.
    The result: the block was cut in two, an empty project named after that
    very sentence appeared, and the sentence NEVER printed again. The writer
    lost a sentence with nothing to warn them.

    Two identical-looking lines cannot be told apart by any reading rule. So
    it is fixed at the WRITING end: a body line missing one gets a full stop.
    Punctuation is not a word — the machine still adds none of the user's
    words.

    A very short line is left alone: it is not a sentence, and a full stop
    would mean nothing.
    """
    t = " ".join((chu or "").split())
    if len(t) < 12 or t.endswith(_KET):
        return t
    return t + "."


def write_block(cv_text: str, kind: str, title: str, meta: str,
                body: list[str]) -> str:
    """Replace the `title` block, or add it if absent. Returns the new cv_text.

    It touches only that block. Nothing is rebuilt, so no block has its
    formatting changed unintentionally.
    """
    lines = (cv_text or "").splitlines()
    body = [_cau_tron(b) for b in body if b.strip()]

    # An empty body = DELETE the block. Keeping a block that fits no posting
    # only dirties the original CV; measured: `Compress EA` fitted 0 of 117
    # postings and was still sitting there.
    if not body:
        found = _bounds(lines, title)
        if not found:
            return cv_text
        start, stop = found
        return "\n".join(lines[:start] + lines[stop:]).rstrip() + "\n"

    # Each block kind has its own SHAPE, and parse() recognises a new block
    # by that shape. Write the wrong shape and the block just written is
    # swallowed by the one before it and disappears — which happened twice: a
    # project block written as a bare "Compress EA" (missing " — "), and an
    # experience block written without its date tail.
    if kind == "experience":
        # 'Job title — Organisation  Jan 2025 – Sep 2025'
        # Do NOT add "· ": parse() does not strip it, so it sticks to the
        # sentence and goes straight onto the CV.
        head = f"{title.strip()} {meta.strip()}".strip()
        chunk = [head] + body
    elif meta.strip():
        chunk = [f"{title.strip()} — {meta.strip()}"] + body
    else:
        # A PROJECT NAME GOES ON ITS OWN LINE.
        #
        # The old version wrote 'Name — first sentence' because parse() back
        # then ONLY recognised a project title on a line containing " — ".
        # That rule is gone (it broke on 4 of 5 common writing styles), and
        # keeping this way of writing breaks the round trip: write 'Name —
        # First sentence.' and read it back, and the line ends in a full stop
        # so it is no longer a title, and the block loses its name.
        #
        # A name on its own line is also how real CVs write a project section.
        chunk = [title.strip()] + body

    found = _bounds(lines, title)
    if found:
        start, stop = found
        return "\n".join(lines[:start] + chunk + lines[stop:]).rstrip() + "\n"

    name = SECTION_FOR.get(kind, "SELECTED PROJECTS")
    at = next((i for i, l in enumerate(lines) if l.strip().upper() == name), None)
    if at is None:                                    # no section yet -> open one
        return "\n".join(lines + ["", name] + chunk).rstrip() + "\n"
    return "\n".join(lines[:at + 1] + chunk + lines[at + 1:]).rstrip() + "\n"
