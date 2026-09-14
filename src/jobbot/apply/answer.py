"""The answer book — Vin's profile, rewritten as WHAT THE FORM ASKS.

ONE SOURCE. Every filled field takes its value from here; nowhere else
builds its own string. Missing is missing in the open — it returns empty and
that field becomes Vin's job. It INVENTS nothing and infers no "probably".

Why `aliases` exists: one fact, two kinds of field. A text field takes "MSc";
a select has a fixed list and has to hit the exact wording in it ("Master's
Degree"). The same fact, so the same entry — not two keys waiting to drift
apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Degrees: the abbreviation on the CV -> the bucket an ATS select uses.
DEGREE_LEVEL = {
    "phd": "doctor", "dphil": "doctor",
    "msc": "master", "ma": "master", "meng": "master", "mphil": "master",
    "mba": "mba", "mres": "master", "mfin": "master", "mst": "master",
    "bsc": "bachelor", "ba": "bachelor", "beng": "bachelor", "ba (hons)": "bachelor",
}
# Wordings commonly found in degree selects. Ordered MOST PRECISE FIRST,
# because that is also the order they are tried. Measured: with only the word
# "master", the machine selected "Master of Business Administration
# (M.B.A.)" — Vin has an MSc, so that is declaring the wrong degree.
LEVEL_WORDS = {
    "doctor": ("Doctorate", "Doctor of Philosophy (Ph.D.)", "PhD", "doctor"),
    "master": ("Master's Degree", "Masters Degree", "Master of Science", "master"),
    "mba": ("Master of Business Administration (M.B.A.)", "MBA"),
    "bachelor": ("Bachelor's Degree", "Bachelors Degree", "bachelor"),
}

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
MONTH_NAME = ["", "January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]

COUNTRY = {"uk": ("United Kingdom", "GB", "UK", "United Kingdom of Great Britain"),
           "gb": ("United Kingdom", "GB", "UK"),
           "england": ("United Kingdom", "GB", "UK"),
           "vietnam": ("Vietnam", "VN", "Viet Nam")}


@dataclass(frozen=True)
class Ans:
    """Một sự thật.

    `value`   what goes into a text field
    `aliases` other wordings, for finding it in a dropdown
    `prefer`  the REST of the profile, used to break ties when several
              options match

    Why `prefer` exists: typing "London" into Greenhouse's city field offers
    both "London, England, United Kingdom" and "London, Ontario, Canada". An
    answer missing that second half cannot break the tie itself — it has to
    use the rest of the profile (Vin is in the UK) to choose. Measured:
    without it, the machine declared Vin lives in Canada.
    """
    value: str
    aliases: tuple[str, ...] = ()
    prefer: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.value)

    def candidates(self) -> tuple[str, ...]:
        return (self.value,) + tuple(a for a in self.aliases if a)


@dataclass
class Education:
    degree: str = ""          # "MSc"
    level: str = ""           # "master"
    discipline: str = ""      # "Computational Finance"
    school: str = ""          # "Royal Holloway, University of London"
    start_month: int = 0
    start_year: int = 0
    end_month: int = 0
    end_year: int = 0
    note: str = ""            # the sub-line: module marks, classification
    missing: list[str] = field(default_factory=list)


_YEARS = re.compile(r"(?:(?P<m1>[A-Za-z]{3,9})\s+)?(?P<y1>(?:19|20)\d{2})"
                    r"\s*[–—-]\s*"
                    r"(?:(?P<m2>[A-Za-z]{3,9})\s+)?(?P<y2>(?:19|20)\d{2})")
_DEGREE_HEAD = re.compile(r"^\s*([A-Za-z.]+(?:\s*\(Hons\))?)\s+(.*)$")


def _month(word: str | None) -> int:
    return MONTHS.get((word or "")[:3].lower(), 0)


def educations(text: str) -> list[Education]:
    """EVERY degree in the Education field, not just the latest.

    ONE grammar for both reading and writing: the profile form builds its
    lines with `line()` just below, and this function reads them back. Let
    the two drift and the form writes something the machine cannot parse —
    and what it cannot parse here is the GRADUATION DATE, the question every
    single application asks.

    An indented line is a SUB-LINE (module marks, classification) — it
    belongs to the degree above it, not to a new degree.
    """
    out: list[Education] = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            if out:
                out[-1].note = (out[-1].note + " " + line.strip()).strip()
            continue
        sach = line.strip()
        # A line with NO degree name and NO year range is not a degree — it
        # is a sub-line written flush left. Real CVs often write module marks
        # that way ("Investment & Portfolio Management 86 · Data Analysis
        # 83"), and misreading it produces a degree called "Investment".
        if out and not _la_bang(sach):
            out[-1].note = (out[-1].note + " " + sach).strip()
            continue
        out.append(_one(sach))
    return out


def _la_bang(dong: str) -> bool:
    """Is this line a DEGREE — does it name one, or carry a year range."""
    dau = _DEGREE_HEAD.match(dong)
    if dau:
        key = dau.group(1).lower().replace(".", "").replace(" (hons)", "")
        if key in DEGREE_LEVEL:
            return True
    return bool(_YEARS.search(dong))


def line(degree: str, discipline: str, school: str,
         start: str, end: str, note: str = "") -> str:
    """The separate fields -> EXACTLY the line `educations()` can read back.

    Dạng: "MSc Computational Finance — Royal Holloway, Sep 2025 – Sep 2026"
    The note (module marks) goes on its own INDENTED line — that is how it
    says "this is a sub-line of the degree above", and it is also what keeps
    it from being misread as another
    bằng thứ hai.
    """
    trai = " ".join(x for x in (degree.strip(), discipline.strip()) if x)
    phai = school.strip()
    khi = " – ".join(x for x in (start.strip(), end.strip()) if x)
    if khi:
        phai = f"{phai}, {khi}" if phai else khi
    dong = " — ".join(x for x in (trai, phai) if x)
    if note.strip():
        dong += "\n  " + note.strip()
    return dong


def education(text: str) -> Education:
    """The LATEST degree — the first line. The fields an application asks for.

    The grammar it reads (exactly how Vin wrote it):

        MSc Computational Finance — Royal Holloway, University of London, 2025–2026
        BA (Hons) Advanced Finance — National Economics University, Vietnam

    If a month is there it takes it ("Sep 2025 – Sep 2026"). If not it does
    NOT guess — it records it in `missing` so Vin fixes the profile once
    instead of picking by hand 49 times.
    """
    hang = educations(text)
    if not hang:
        trong = Education()
        trong.missing = ["học vấn"]
        return trong
    return hang[0]


def _one(head: str) -> Education:
    out = Education()
    # Several separator styles. Accepting only "—" and " - " means that
    # "MSc X-Royal Holloway" or "MSc X | Royal Holloway" puts THE WHOLE LINE
    # into the field-of-study box and leaves the university box empty — and
    # the employer receives a meaningless string.
    left, right = head, ""
    for dash in ("—", "–", " - ", " | ", " · ", ", "):
        a, sep, b = head.partition(dash)
        if sep and b.strip():
            left, right = a, b
            break
    left, right = left.strip(), right.strip()

    match = _DEGREE_HEAD.match(left)
    if match:
        out.degree, out.discipline = match.group(1).strip(), match.group(2).strip()
        key = out.degree.lower().replace(".", "").replace(" (hons)", "")
        out.level = DEGREE_LEVEL.get(key, "")
    else:
        out.discipline = left

    span = _YEARS.search(right)
    if span:
        out.start_year, out.end_year = int(span.group("y1")), int(span.group("y2"))
        out.start_month, out.end_month = _month(span.group("m1")), _month(span.group("m2"))
        right = right[: span.start()].rstrip(" ,")
    out.school = right.rstrip(" ,")

    if not out.start_year:
        out.missing.append("the study years")
    elif not out.start_month:
        # Say how to fix it: this is missing data, not a missing rule.
        out.missing.append("the study months — write Education as "
                           "'Sep 2025 – Sep 2026'")
    return out


def _links(raw: str) -> dict[str, str]:
    """Split out the links. Only accepts what is genuinely a URL.

    The profile currently holds the bare words "LinkedIn"/"GitHub" — those
    are labels, not addresses. Putting the word "LinkedIn" into a LinkedIn
    URL field is rubbish. Drop it, and report it missing.
    """
    out = {"website": "", "linkedin": "", "github": ""}
    for piece in re.split(r"[\s,]+", raw or ""):
        low = piece.lower()
        if not low.startswith(("http://", "https://", "www.")):
            continue
        url = piece if piece.lower().startswith("http") else "https://" + piece
        if "linkedin." in low:
            out["linkedin"] = url
        elif "github.com" in low:
            out["github"] = url
        elif not out["website"]:
            out["website"] = url
    return out


def book(profile: dict[str, Any]) -> dict[str, Ans]:
    """Profile -> answer book. The key is THE QUESTION, not any ATS's field
    name."""
    get = lambda k: str(profile.get(k) or "").strip()      # noqa: E731

    # "Dac Vinh Nguyen" is written Western-style: the LAST WORD is the
    # surname and the rest is the given name. Splitting it the other way
    # (first = "Dac", last = "Vinh Nguyen") gets the surname wrong — and the
    # surname is what an employer writes in their email.
    full = get("full_name")
    parts = full.split()
    first = " ".join(parts[:-1]) if len(parts) > 1 else (parts[0] if parts else "")
    last = parts[-1] if len(parts) > 1 else ""

    place = get("location")                                # "London, UK"
    city, _, tail = place.partition(",")
    country_key = tail.strip().lower().rstrip(".")
    country = COUNTRY.get(country_key, (tail.strip(),) if tail.strip() else ())

    edu = education(get("education"))
    link = _links(get("links"))

    def month(n: int) -> Ans:
        return Ans(f"{n:02d}", (MONTH_NAME[n], MONTH_NAME[n][:3], str(n))) if n else Ans("")

    # The half used to break ties between identically named cities.
    where = tuple(x for x in (country[0] if country else "", "England",
                              *(country[1:] if country else ())) if x)

    return {
        "first_name": Ans(first),
        "last_name": Ans(last),
        "full_name": Ans(full),
        "email": Ans(get("email")),
        "phone": Ans(get("phone")),
        "location": Ans(place, (city.strip(),), where),
        "city": Ans(city.strip(), (place,), where),
        "country": Ans(country[0] if country else "", tuple(country[1:])),
        "website": Ans(link["website"]),
        "linkedin": Ans(link["linkedin"]),
        "github": Ans(link["github"]),
        "school": Ans(edu.school),
        "degree": Ans(edu.degree, tuple(LEVEL_WORDS.get(edu.level, ()))),
        "discipline": Ans(edu.discipline),
        "edu_start_year": Ans(str(edu.start_year) if edu.start_year else ""),
        "edu_end_year": Ans(str(edu.end_year) if edu.end_year else ""),
        "edu_start_month": month(edu.start_month),
        "edu_end_month": month(edu.end_month),
    }
