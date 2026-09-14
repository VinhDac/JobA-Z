"""Read a CV from a file — PDF, DOCX, TXT — and PROPOSE profile answers.

Nothing to install:
    PDF   macOS PDFKit through PyObjC (already there)
    DOCX  zipfile + xml from the standard library
    TXT   read directly

The rule: **propose, never write.** The user approves item by item.
Writing automatically is the fastest way to erase what they typed by hand.
"""

from __future__ import annotations

import re
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO

from ..ingest.base import norm
from ..scoring.vocab import ALIASES

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?){2,4}\d{2,4}")
URL = re.compile(r"(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:/[\w./%-]*)?", re.I)
CITY = re.compile(r"\b(London|Manchester|Edinburgh|Birmingham|Leeds|Bristol|Glasgow|"
                  r"Cambridge|Oxford|Hanoi|Ho Chi Minh|New York|Singapore|Dublin)\b", re.I)


# Keywords that recognise a line AS a job title. Deliberately narrow: better
# to miss a few lines than to propose "References available on request" as a
# job title.
ROLE_WORD = re.compile(
    r"\b(Analyst|Engineer|Scientist|Developer|Researcher|Manager|Consultant|"
    r"Trader|Strategist|Quant|Associate|Specialist|Architect|Administrator)\b", re.I)
# A line containing these is NOT a title — it is prose or a company name.
NOT_ROLE = re.compile(r"[.;•·]|\b(and|with|using|for|the|a|an|of|to)\b\s", re.I)
UK = re.compile(r"\b(London|Manchester|Edinburgh|Birmingham|Leeds|Bristol|Glasgow|"
                r"Cambridge|Oxford|United Kingdom|UK|England|Scotland|Wales)\b")
# Seniority: the word on the CV -> the schema option. Not inferred from years
# of experience — counting years is guessing, while the word "Intern" printed
# on the CV is evidence.
LEVEL_WORD = [("intern", re.compile(r"\b(intern|internship|placement)\b", re.I)),
              ("grad", re.compile(r"\b(graduate|MSc|MEng|BSc|BEng|MA|BA)\b")),
              ("junior", re.compile(r"\bjunior\b", re.I))]


class ReadError(RuntimeError):
    pass


# ------------------------------------------------------------ reading files

def from_pdf(data: bytes) -> str:
    """Đọc chữ trong PDF.

    macOS has PDFKit — it handles embedded fonts and custom encodings, so it
    goes first. Elsewhere the standard library does it: inflate the content
    streams and pick the text out of the Tj/TJ operators.

    The hand-written extractor CANNOT read a PDF using an embedded font with
    a custom encoding (LaTeX, Canva and InDesign often produce these) — it
    returns garbage characters. So it CHECKS ITSELF and says so, rather than
    pushing a pile of junk into the profile. The user has another route:
    paste the text into the box beside it.
    """
    if sys.platform == "darwin":
        try:
            return _pdf_macos(data)
        except ReadError:
            raise
        except Exception:                       # noqa: BLE001
            pass                                # no PyObjC -> extract by hand
    text = _pdf_plain(data)
    if not _looks_like_text(text):
        raise ReadError(
            "This PDF uses an embedded font, so the extracted text is "
            "garbage. Open the PDF, select all, copy, and PASTE it into the "
            "box beside this one.")
    return text


def _pdf_macos(data: bytes) -> str:
    import objc
    from Foundation import NSData
    objc.loadBundle("PDFKit", globals(),
                    bundle_path="/System/Library/Frameworks/Quartz.framework"
                                "/Frameworks/PDFKit.framework")
    doc = PDFDocument.alloc().initWithData_(              # noqa: F821
        NSData.dataWithBytes_length_(data, len(data)))
    if doc is None:
        raise ReadError("Could not open the PDF — corrupt, or password protected.")
    return str(doc.string() or "")


# (text) Tj   |   [(a) -3 (b)] TJ   — the two ways a PDF puts text on a page
_PDF_STR = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)
_PDF_SHOW = re.compile(rb"(?:Tj|TJ|'|\")")


def _pdf_plain(data: bytes) -> str:
    """Extract with the standard library. Only works on normally encoded PDFs."""
    import zlib

    chunks: list[str] = []
    for raw in re.findall(rb"stream\r?\n(.*?)endstream", data, re.S):
        body = raw
        try:
            body = zlib.decompress(raw)
        except zlib.error:
            try:
                body = zlib.decompressobj().decompress(raw)   # a truncated stream
            except zlib.error:
                continue                                       # not Flate
        chunks.append(_pdf_text_ops(body))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(c for c in chunks if c.strip())).strip()


def _pdf_text_ops(body: bytes) -> str:
    out: list[str] = []
    for line in body.split(b"\n"):
        if not _PDF_SHOW.search(line):
            continue
        parts = [_pdf_unescape(m[1:-1]) for m in _PDF_STR.findall(line)]
        if parts:
            out.append("".join(parts))
    return "\n".join(out)


_ESCAPES = {b"n": "\n", b"r": "", b"t": "\t", b"b": "", b"f": "",
            b"(": "(", b")": ")", b"\\": "\\"}


def _pdf_unescape(raw: bytes) -> str:
    out, i = [], 0
    while i < len(raw):
        ch = raw[i:i + 1]
        if ch == b"\\" and i + 1 < len(raw):
            nxt = raw[i + 1:i + 2]
            if nxt.isdigit():                     # \ddd = an octal code
                digits = raw[i + 1:i + 4]
                out.append(chr(int(digits, 8))); i += 1 + len(digits); continue
            out.append(_ESCAPES.get(nxt, nxt.decode("latin-1"))); i += 2; continue
        out.append(ch.decode("latin-1")); i += 1
    return "".join(out)


def _looks_like_text(text: str) -> bool:
    """Is this readable text, or garbage from an embedded font.

    The signal: in a real CV most characters are letters, spaces and
    punctuation. An embedded font with a custom encoding produces a sea of
    strange characters.
    """
    body = text.strip()
    if len(body) < 200:                           # too short -> not a CV
        return False
    good = sum(c.isalnum() or c.isspace() or c in ".,;:/@()&+%-–—·" for c in body)
    return good / len(body) > 0.85


def from_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", "replace")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ReadError("Could not read the .docx — corrupt file?") from exc
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", " ", xml)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"<[^>]+>", "", xml)).strip()


def read(filename: str, data: bytes) -> str:
    low = (filename or "").lower()
    if low.endswith(".pdf") or data[:5] == b"%PDF-":
        return from_pdf(data)
    if low.endswith(".docx") or data[:2] == b"PK":
        return from_docx(data)
    text = data.decode("utf-8", "replace")
    if "\x00" in text:
        raise ReadError("Unreadable format. Use PDF, DOCX or TXT.")
    return text


# ------------------------------------------------------------- proposals

@dataclass
class Proposal:
    field: str
    label: str
    value: str | list[str]        # a list for multi-select questions
    note: str = ""


def _section(text: str, name: str) -> str:
    found = re.search(rf"^{name}\s*$(.*?)(?=^[A-Z][A-Z &]{{3,}}\s*$|\Z)",
                      text, re.M | re.S)
    return found.group(1).strip() if found else ""


def propose(text: str, existing: dict) -> list[Proposal]:
    """Extract information from a CV. It only proposes for fields that are
    EMPTY — it never overwrites what the user typed themselves."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out: list[Proposal] = []

    def add(field, label, value, note="", thay=False):
        """A multi-select question takes a LIST of option codes, a free-text
        question takes a string — the store keeps whatever type it is given.
        This function used to know only strings, so passing a list broke
        immediately at .strip().

        `thay=True` lets a proposal OVERWRITE a field that already has a
        value. Only used for cv_text: "import a new CV" clearly means
        replacing the old one. Every other field keeps the never-overwrite
        rule — that is what protects the sentences the user typed.
        """
        cu = existing.get(field)
        if isinstance(cu, (list, tuple)):
            da_co = bool(cu)
        else:
            da_co = bool((cu or "").strip())
        if not value or (da_co and not thay):
            return
        out.append(Proposal(field, label,
                            value if isinstance(value, list) else value.strip(),
                            note))

    cu_cv = str(existing.get("cv_text") or "")
    add("cv_text", "Full CV text", text,
        (f"{len(text)} characters — REPLACES the stored CV "
         f"({len(cu_cv)} characters). Untick to take only the fields below."
         if cu_cv.strip() else f"{len(text)} characters"),
        thay=True)

    if lines:
        head = lines[0]
        if len(head) < 60 and head.replace(" ", "").isalpha():
            add("full_name", "Name", head.title() if head.isupper() else head)

    blob = "\n".join(lines[:6])
    email = EMAIL.search(blob)
    if email:
        add("email", "Email", email.group())
    phone = PHONE.search(blob.replace(email.group(), "") if email else blob)
    if phone and len(re.sub(r"\D", "", phone.group())) >= 9:
        add("phone", "Phone", phone.group().strip())
    city = CITY.search(blob)
    if city:
        add("location", "Location", city.group())

    links = [u for u in URL.findall(blob)
             if any(k in u.lower() for k in ("github", "linkedin", ".io", "gitlab", "portfolio"))]
    if links:
        add("links", "Profile links", "\n".join(dict.fromkeys(links)))

    edu = _section(text, "EDUCATION")
    if edu:
        # Drop lines carrying NO information: a PDF often produces a lone
        # "·" between two degrees. Left in, it becomes an empty education
        # line, and both score.py and cv/build.py read LINE BY LINE.
        sach = [l for l in edu.split("Certification")[0].strip().splitlines()
                if l.strip(" ·—–-\t")]
        add("education", "Education", "\n".join(sach))
    cert = re.search(r"^Certifications?\s*[—–-]\s*(.+)$", text, re.M)
    if cert:
        # ONE CERTIFICATE PER LINE. The CV writes "A · B · C" on one line,
        # but cv/build.py does `certs.splitlines()[0]` to take the strongest
        # one — leave it as one line and it puts the whole 90-character run
        # into the CV as a single "fact", and the machine counts 1
        # certificate where there are really 3.
        tung = [c.strip() for c in re.split(r"\s·\s|\s\|\s", cert.group(1))
                if c.strip()]
        add("certifications", "Certifications", "\n".join(tung),
            f"{len(tung)} certificates — one per line; the system reads by line"
            if len(tung) > 1 else "")

    skills = _section(text, "TECHNICAL SKILLS") or _section(text, "SKILLS")
    found = sorted({c for a, c in ALIASES.items()
                    if (f" {a.strip()} " if len(a.strip()) <= 3 else a.strip())
                    in f" {norm(skills or text)} "})
    if found:
        add("skills_strong", "Skills recognised in your CV", ", ".join(found),
            f"{len(found)} terms — edit before saving, the system cannot tell "
            f"strong from merely mentioned")
        # The same batch of skills doubles as the search keywords. Not
        # re-extracted under a different rule — two rules for one thing drift
        # apart sooner or later.
        add("search_keywords", "Keywords to look for in postings",
            ", ".join(found[:12]),
            "taken from the skills above — trim to the few that really matter")

    # --- the GOALS section: this is what opens the gate for the app --------
    titles = _job_titles(text)
    if titles:
        add("job_titles", "Job titles to search for", "\n".join(titles),
            f"{len(titles)} titles read off your CV — these are jobs you HAVE "
            f"done. Edit them into the jobs you WANT; the search sends this "
            f"string to the boards as-is")

    levels = [key for key, rx in LEVEL_WORD if rx.search(text)]
    if levels:
        add("seniority", "Levels you'd accept", levels,
            "inferred from words printed on your CV (" + ", ".join(levels) + ")")

    if UK.search(blob) or UK.search(text[:600]):
        add("markets", "Which markets?", ["uk_onsite", "uk_remote"],
            "inferred from the location on your CV — change it if you are "
            "looking elsewhere")

    # work_auth IS DELIBERATELY NOT PROPOSED. It is a legal fact about a
    # person, the CV does not state it, and guessing wrong ruins the whole
    # application — employers filter on that question before reading anything
    # else. The person answers it themselves.
    return out


def _job_titles(text: str) -> list[str]:
    """The job titles readable in a CV, in the order they appear.

    Two rules, both drawn from a REAL CV that was read badly:

    1. CUT FIRST, MEASURE SECOND. A real CV writes a whole line as "Founder /
       Quantitative
       Developer — Algorithmic Trading Startup Jan 2024 – …" (81 ký tự). Đo
       the length before cutting the company half and every line is too long
       and all of them are rejected — exactly the bug that left Vin's profile
       with no extracted titles at all.

    2. ONLY READ THE EXPERIENCE SECTION when the CV has one. Scanning the
       whole file lets "Quant Trading Studio" from SELECTED PROJECTS through
       — that is a project name, not a job title, and it looks identical.
    """
    vung = (_section(text, "EXPERIENCE")
            or _section(text, "WORK EXPERIENCE")
            or _section(text, "PROFESSIONAL EXPERIENCE")
            or text)
    seen: list[str] = []
    for raw in vung.splitlines():
        line = raw.strip(" \t-–—•|")
        if not ROLE_WORD.search(line):
            continue
        # cut the company / date half FIRST, then measure
        line = re.split(r"\s[—–|]\s|\s{2,}|,\s", line)[0].strip()
        # drop a leftover date tail: "Research Consultant Jan 2025 – Sep 2025"
        line = re.sub(r"\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*"
                      r"\s+\d{4}.*$", "", line).strip()
        if not (4 <= len(line) <= 60) or NOT_ROLE.search(line):
            continue
        if line.lower() not in [t.lower() for t in seen]:
            seen.append(line)
    return seen[:8]
