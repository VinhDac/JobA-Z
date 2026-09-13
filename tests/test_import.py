"""Test nhập CV + xếp hạng dòng.  python3 tests/test_import.py"""

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

print("\n[đọc file]")
check("đọc TXT", read("cv.txt", CV.encode()).startswith("JANE SMITH"))

buf = BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("word/document.xml",
                "<w:document><w:p><w:t>Hello</w:t></w:p>"
                "<w:p><w:t>World</w:t></w:p></w:document>")
check("đọc DOCX", from_docx(buf.getvalue()).split() == ["Hello", "World"])
try:
    from_docx(b"not a zip"); check("DOCX hỏng -> báo lỗi rõ", False)
except ReadError:
    check("DOCX hỏng -> báo lỗi rõ", True)
try:
    read("x.bin", b"\x00\x01\x02binary"); check("file lạ -> báo lỗi rõ", False)
except ReadError:
    check("file lạ -> báo lỗi rõ", True)

print("\n[đề xuất — KHÔNG đè ô đã có]")
found = {p.field: p.value for p in propose(CV, {})}
check("lấy được tên", found.get("full_name") == "Jane Smith")
check("lấy được email", found.get("email") == "jane@example.com")
check("lấy được điện thoại", "7700 900123" in found.get("phone", ""))
check("lấy được địa điểm", found.get("location") == "Manchester")
check("lấy được link", "github.com/jane" in found.get("links", ""))
check("lấy được học vấn", "BSc Statistics" in found.get("education", ""))
check("lấy được chứng chỉ", "AWS" in found.get("certifications", ""))
check("nhận ra kỹ năng", {"python", "sql", "excel"} <=
      {x.strip() for x in found.get("skills_strong", "").split(",")})
check("giữ nguyên văn CV", found.get("cv_text", "").startswith("JANE SMITH"))

partial = {p.field for p in propose(CV, {"email": "old@x.com", "full_name": "Old Name"})}
check("ô đã điền tay thì KHÔNG đề xuất đè", not ({"email", "full_name"} & partial))
check("ô còn trống thì vẫn đề xuất", "education" in partial)

print("\n[nhận file tải lên]")
body = (b"--X\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cv.txt\"\r\n"
        b"Content-Type: text/plain\r\n\r\n" + CV.encode() + b"\r\n"
        b"--X\r\nContent-Disposition: form-data; name=\"pasted\"\r\n\r\n\r\n--X--\r\n")
fields = upload.parse('multipart/form-data; boundary=X', body)
check("tách được tên file", fields["file"][0] == "cv.txt")
check("tách được nội dung", fields["file"][1].startswith(b"JANE SMITH"))
check("tách được ô chữ", "pasted" in fields)
try:
    upload.parse("multipart/form-data; boundary=X", b"x" * (upload.MAX_BYTES + 1))
    check("file quá lớn -> chặn", False)
except upload.TooBig:
    check("file quá lớn -> chặn", True)

print("\n[xếp hạng từng dòng]")
cases = [
    ("Built dashboards in Python and SQL for 40 stores", "strong"),
    ("I designed and built two systems in Python: signals and risk", "strong"),
        # Ý KIẾN GIỜ LÀ "HỎI", KHÔNG PHẢI "XOÁ". Ý kiến và kiến thức cùng hình
    # dạng — hiện tại đơn, không số, không hành động — mà kiến thức là thứ
    # mạnh nhất của một CV kỹ thuật. Máy đoán sai một lần là xoá mất câu mạnh
    # nhất, nên nó đánh dấu để người viết tự quyết.
    ("Deciding which numbers deserve to be believed is the work I want to do", "review"),
    ("The mistake was mine: the regime split was a valid partition", "drop"),
    ("Self-funded, across 17 instruments and five years of data", "review"),
    ("I am a hard-working and motivated team player who enjoys challenges", "review"),
]
for text, want in cases:
    got = _grade(text)[0]
    check(f"{want:6} ← {text[:44]}…", got == want)

check("dòng mạnh có điểm cao hơn dòng rỗng",
      _grade("Built pipelines in Python processing 2M rows daily")[2]
      > _grade("A motivated individual seeking new opportunities")[2])

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
