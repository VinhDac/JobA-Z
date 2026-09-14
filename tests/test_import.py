"""Test the CV import + line ranking.  python3 tests/test_import.py"""

import sys, zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.dashboard import upload
from jobbot.dashboard.views.cvhealth import _grade
from jobbot.profile.import_cv import ReadError, from_docx, propose, read

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

CV = """JANE SMITH
Manchester, UK · +44 7700 900123 · jane@example.com · github.com/jane
EXPERIENCE
Data Analyst — Acme Ltd Jan 2024 – Present
Built dashboards in Python and SQL for 40 stores.
EDUCATION
BSc Statistics — University of Leeds 2020 – 2023
Certifications — AWS Certified Data Analytics
TECHNICAL SKILLS
Programming — Python, SQL, Excel.
"""

print("\n[reading a file]")
check("reads TXT", read("cv.txt", CV.encode()).startswith("JANE SMITH"))

buf = BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("word/document.xml",
                "<w:document><w:p><w:t>Hello</w:t></w:p>"
                "<w:p><w:t>World</w:t></w:p></w:document>")
check("reads DOCX", from_docx(buf.getvalue()).split() == ["Hello", "World"])
try:
    from_docx(b"not a zip"); check("a broken DOCX -> a clear error", False)
except ReadError:
    check("a broken DOCX -> a clear error", True)
try:
    read("x.bin", b"\x00\x01\x02binary"); check("an unknown file -> a clear error", False)
except ReadError:
    check("an unknown file -> a clear error", True)

print("\n[proposals — they NEVER overwrite a filled field]")
found = {p.field: p.value for p in propose(CV, {})}
check("picks up the name", found.get("full_name") == "Jane Smith")
check("picks up the email", found.get("email") == "jane@example.com")
check("picks up the phone", "7700 900123" in found.get("phone", ""))
check("picks up the location", found.get("location") == "Manchester")
check("picks up the links", "github.com/jane" in found.get("links", ""))
check("picks up the education", "BSc Statistics" in found.get("education", ""))
check("picks up the certifications", "AWS" in found.get("certifications", ""))
check("recognises the skills", {"python", "sql", "excel"} <=
      {x.strip() for x in found.get("skills_strong", "").split(",")})
check("keeps the CV verbatim", found.get("cv_text", "").startswith("JANE SMITH"))

partial = {p.field for p in propose(CV, {"email": "old@x.com", "full_name": "Old Name"})}
check("a hand-filled field is NOT proposed over", not ({"email", "full_name"} & partial))
check("an empty field is still proposed", "education" in partial)

print("\n[accepting an upload]")
body = (b"--X\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cv.txt\"\r\n"
        b"Content-Type: text/plain\r\n\r\n" + CV.encode() + b"\r\n"
        b"--X\r\nContent-Disposition: form-data; name=\"pasted\"\r\n\r\n\r\n--X--\r\n")
fields = upload.parse('multipart/form-data; boundary=X', body)
check("parses the filename", fields["file"][0] == "cv.txt")
check("parses the content", fields["file"][1].startswith(b"JANE SMITH"))
check("parses the text field", "pasted" in fields)
try:
    upload.parse("multipart/form-data; boundary=X", b"x" * (upload.MAX_BYTES + 1))
    check("a file that is too big -> blocked", False)
except upload.TooBig:
    check("a file that is too big -> blocked", True)

print("\n[ranking each line]")
cases = [
    ("Built dashboards in Python and SQL for 40 stores", "strong"),
    ("I designed and built two systems in Python: signals and risk", "strong"),
        # AN OPINION IS NOW "ASK", NOT "DROP". Opinion and knowledge have the
    # same shape — present simple, no number, no action — while knowledge is
    # the strongest thing on a technical CV. One wrong guess by the machine
    # deletes the strongest sentence, so it marks it and lets the writer
    # decide.
    ("Deciding which numbers deserve to be believed is the work I want to do", "review"),
    ("The mistake was mine: the regime split was a valid partition", "drop"),
    ("Self-funded, across 17 instruments and five years of data", "review"),
    ("I am a hard-working and motivated team player who enjoys challenges", "review"),
]
for text, want in cases:
    got = _grade(text)[0]
    check(f"{want:6} ← {text[:44]}…", got == want)

check("a strong line scores higher than an empty one",
      _grade("Built pipelines in Python processing 2M rows daily")[2]
      > _grade("A motivated individual seeking new opportunities")[2])

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
