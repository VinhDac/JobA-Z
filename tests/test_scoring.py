"""Test bước 2 — chấm điểm khớp.  python3 tests/test_scoring.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.scoring import extract
from jobbot.scoring.score import _degrees_needed, _years_needed, build_index, score_job

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

PROFILE = {
    "job_titles": "Quantitative Analyst\nData Scientist",
    "seniority": ["grad", "junior"],
    "years_real": "0-1",
    "education": "MSc Computational Finance — Royal Holloway, 2026\nBA Finance, GPA 3.59",
    "certifications": "CFA Level I — top 10% of global candidates",
    "skills_strong": "Python, pandas, SQL",
    "search_keywords": "machine learning, backtesting",
}

JD = """About the role
We do things.

Requirements:
· Strong knowledge of Python and pandas
· Degree in a quantitative discipline
· 5+ years of commercial experience
· Exceptional communication skills

Nice to have:
· Experience with kdb+

What we offer
· 25 days holiday
· Private healthcare
"""

print("\n[tách yêu cầu]")
reqs = extract.requirements(JD)
texts = [r.text for r in reqs]
check("lấy được gạch đầu dòng", len(reqs) == 5)
check("bỏ phần phúc lợi", not any("holiday" in t or "healthcare" in t for t in texts))
check("nhận ra điểm cộng", any(t.startswith("Experience with kdb") and not r.must
                               for t, r in zip(texts, reqs)))
check("còn lại là bắt buộc", sum(1 for r in reqs if r.must) == 4)
check("độ tin cậy cao khi có gạch đầu dòng", extract.confidence(reqs) == "high")
check("JD rỗng -> không chấm được", extract.confidence(extract.requirements("")) == "none")

prose = ("We are a research firm. If you have experience in time series analysis "
         "and knowledge of Python we would like to hear from you. "
         "You will have 25 days holiday and private healthcare.")
preqs = extract.requirements(prose)
check("văn xuôi vẫn nhặt được yêu cầu", len(preqs) >= 1)
check("văn xuôi -> độ tin cậy thấp", extract.confidence(preqs) == "low")
check("văn xuôi vẫn bỏ câu phúc lợi",
      not any("holiday" in r.text for r in preqs))

print("\n[bằng cấp — lỗi đã sửa]")
check("'MS or PhD' nhận CẢ HAI, không chỉ cái cao nhất",
      set(_degrees_needed("Undergraduate, MS, or PhD candidates")) >= {"phd", "masters"})
check("'PhD required' chỉ ra PhD", _degrees_needed("PhD required") == ["phd"])
check("'database' KHÔNG bị nhận là bằng BA", _degrees_needed("experience with databases") == [])
check("'systems' KHÔNG bị nhận là MS", "masters" not in _degrees_needed("distributed systems"))

print("\n[số năm]")
check("đọc được '5+ years'", _years_needed("5+ years of experience") == 5)
check("đọc được '3-5 years'", _years_needed("3-5 years required") == 3)
check("không có năm -> None", _years_needed("Strong Python") is None)

print("\n[bằng chứng mạnh / yếu]")
index = build_index(PROFILE)
labels = [e.where for e in index]
# Ô TÌM VIỆC KHÔNG PHẢI BẰNG CHỨNG. Nhãn của chính nó tự khai "(not proof)",
# nhưng nó vẫn nằm trong chỉ số nên một dòng yêu cầu tính là ĐẠT nhờ chữ Vin
# gõ vào ô TÌM VIỆC. Đo trên kho thật: 249 dòng ở 153/472 tin đạt kiểu đó.
# "Tôi muốn tìm việc có Kafka" không phải bằng chứng tôi biết Kafka.
check("ô TỪ KHOÁ TÌM VIỆC không được vào chỉ số bằng chứng",
      not any("keyword" in l for l in labels))
check("ô 'muốn chuyển sang' cũng không",
      not any("want to move into" in l for l in labels))
check("nhưng kỹ năng mạnh thì CÓ", "your strong skills" in labels)
# Kỹ năng ĐANG HỌC thì KHÁC ô từ khoá: nó là lời khai về chính mình, chỉ là
# lời khai yếu. Giữ lại, đánh dấu yếu — không vứt như ô tìm việc.
_hoc = build_index({**PROFILE, "skills_weak": "rust"})
check("kỹ năng đang học vẫn được giữ, ở mức YẾU",
      any("still learning" in e.where and not e.strong for e in _hoc))

print("\n[chấm điểm]")
result = score_job("Graduate Quantitative Analyst", JD, PROFILE)
by_text = {r["text"]: r for r in result["requirements"]}
check("Python có trong hồ sơ -> đạt",
      by_text["Strong knowledge of Python and pandas"]["met"] is True)
check("bằng cấp định lượng -> đạt",
      by_text["Degree in a quantitative discipline"]["met"] is True)
check("5+ năm mà mới 0-1 -> trượt",
      by_text["5+ years of commercial experience"]["met"] is False)
check("kỹ năng mềm -> KHÔNG phán (không tính vào mẫu số)",
      by_text["Exceptional communication skills"]["met"] is None)
check("bằng chứng trích từ hồ sơ thật",
      "Python" in by_text["Strong knowledge of Python and pandas"]["evidence"])
check("thiếu số năm -> chặn trần 55", result["score"] <= 55 and result["capped"])
check("có nêu dòng chặn", len(result["blockers"]) == 1)
check("điểm cộng cách biệt với bắt buộc", result["breakdown"]["nice"]["total"] == 1)

soft = score_job("Graduate Quantitative Analyst",
                 JD.replace("· 5+ years of commercial experience\n", ""), PROFILE)
check("bỏ yêu cầu số năm thì điểm vọt lên", soft["score"] > result["score"])
check("nhắm junior mà tin ghi Senior -> trừ nặng",
      score_job("Senior Quantitative Analyst", JD, PROFILE)["breakdown"]["level"]["points"] == 0)
check("tin ghi Graduate -> cộng đủ", soft["breakdown"]["level"]["points"] == 20)

blank = score_job("Analyst", "We are a great company. Join us.", PROFILE)
check("JD không có yêu cầu -> KHÔNG bịa điểm", blank["score"] is None)
check("và nói rõ vì sao", "Could not read" in blank["reason"])

print("\n[hồ sơ THIẾU ô cũng không được làm sập vòng chấm]")
# LỖI THẬT: "".splitlines() là [] chứ không phải [""], nên judge_one lấy [0]
# và ném IndexError. Nó nổ GIỮA giao dịch của derive(), cuộn lại cả lần quét —
# một hồ sơ chưa điền học vấn là cả đường ống chết câm.
_DEGREE_JD = ("Requirements:\n· A degree in a quantitative discipline\n"
              "· Strong Python\n· SQL\n")
for _missing in ["education", "skills_strong", "certifications", "years_real",
                 "seniority", "job_titles"]:
    _thin = {k: v for k, v in PROFILE.items() if k != _missing}
    try:
        _out = score_job("Data Scientist", _DEGREE_JD, _thin)
        check(f"thiếu {_missing!r} vẫn chấm được", _out["score"] is not None)
    except Exception as _exc:                        # noqa: BLE001
        check(f"thiếu {_missing!r} vẫn chấm được", False)
        print(f"       {type(_exc).__name__}: {_exc}")

check("hồ sơ RỖNG hoàn toàn cũng không sập",
      score_job("Data Scientist", _DEGREE_JD, {}) is not None)
_empty = score_job("Data Scientist", _DEGREE_JD, {"education": ""})
_edu = [r for r in _empty["requirements"] if "degree" in r["text"].lower()]
check("và nói thẳng là hồ sơ chưa có học vấn",
      bool(_edu) and "nothing on your profile" in _edu[0]["evidence"])

print("\n[khớp kỹ năng theo TỪ, không theo chuỗi con]")
# LỖI THẬT, ảnh hưởng lớn nhất trong cả đợt soát: 'excel' nằm trong
# 'excellent', nên 70/204 tin đang giữ được gắn kỹ năng Excel chỉ vì JD viết
# "excellent communication" — và nhóm project LỚN NHẤT trên /projects mọc lên
# từ cái bóng đó, tức là cả bước sinh project đang nhắm sai.
from jobbot.scoring.vocab import alias_hits
from jobbot.ingest.base import norm as _norm
_hits = lambda t: alias_hits(_norm(t))

for _text, _bad in [("Excellent communication skills", "excel"),
                    ("highly scalable systems", "scala"),
                    ("we build trust with clients", "rust"),
                    ("evaluation of trading models", "asset pricing"),
                    ("javascript front end", "java")]:
    check(f"{_text[:34]!r} KHÔNG ra {_bad!r}", _bad not in _hits(_text))

for _text, _want in [("Excel and VBA", "excel"),
                     ("Rust and C++", "rust"),
                     ("Scala on the JVM", "scala")]:
    check(f"{_text!r} vẫn ra {_want!r}", _want in _hits(_text))

# Cấm hẳn chuỗi con thì mất phần lớn cái ĐÚNG — tiếng Anh chia đuôi.
for _text, _want in [("backtesting engines", "backtesting"),
                     ("derivatives pricing", "derivatives"),
                     ("building data pipelines", "data pipeline"),
                     ("containerisation with docker", "docker"),
                     ("managing portfolios", "portfolio"),
                     ("running simulations", "backtesting")]:
    check(f"đuôi chia vẫn khớp: {_text!r}", _want in _hits(_text))

# Hai tầng phải hiểu chữ GIỐNG NHAU — trước đây mỗi bên giữ một bản sao luật.
from jobbot.cv.build import skills_in as _skills_in
_probe = "Excellent communication, Excel, backtesting and scalable pipelines"
check("cv.skills_in và scoring dùng chung một luật",
      _skills_in(_probe) == set(_hits(_probe)))

print("\n[tên có dấu: C++ · ci/cd · kdb+ — ĐÃ TỪNG mất hẳn]")
# HAI lỗi chồng nhau làm 208 tin đòi C++ không bao giờ khớp, dù CV CÓ C++:
#   norm() bỏ mọi ký tự không phải chữ-số  -> "C++" thành "c"
#   mẫu alias kết bằng \\b                  -> sau dấu '+' không bao giờ có
#                                             ranh giới từ, nên kể cả giữ được
#                                             dấu + thì vẫn không khớp
from jobbot.ingest.base import norm as _nm
from jobbot.scoring.vocab import alias_hits as _ah
check("norm giữ dấu + trong C++", "c++" in _nm("Strong C++ and Python"))
check("norm giữ dấu / trong CI/CD", "ci/cd" in _nm("CI/CD pipelines"))
check("khớp được C++", "c++" in _ah(_nm("Strong C++ and Python")))
check("khớp được ci/cd", "ci/cd" in _ah(_nm("CI/CD and Docker")))
check("C++ ở cuối câu cũng khớp", "c++" in _ah(_nm("experience with C++")))
# Nới ranh giới KHÔNG được đẻ ra khớp bừa — đây là lớp lỗi 'excel' trong
# 'excellent' đã cắn một lần rồi.
check("'abc' KHÔNG ra c++", "c++" not in _ah(_nm("abc company")))
check("'arc welding' KHÔNG ra r", "r" not in _ah(_nm("arc welding")))
check("'excellent' vẫn KHÔNG ra excel", "excel" not in _ah(_nm("excellent communication")))
check("'scalable' vẫn KHÔNG ra scala", "scala" not in _ah(_nm("highly scalable")))

print("\n[danh sách KHÔNG có dấu gạch đầu dòng — LinkedIn]")
# Lỗi thật: LinkedIn trả JD qua innerText, <li> mất sạch dấu '·'. Bộ tách nhận
# diện danh sách BẰNG dấu đó nên trả về rỗng, và 46/204 tin đang giữ — PIMCO,
# L&G, Smarkets — bị báo "không đọc được yêu cầu" dù có nguyên danh sách.
LINKEDIN = """Data Analyst

Nando's is on a journey to Create Lasting Happiness across the communities we work in.

What you'll bring

Writing complex SQL to query, transform and model data across our cloud platform
Building and maintaining data models in Dataform or a similar transformation tool
Building reports and dashboards in Looker or a similar BI tool for the business
Using Git as standard practice - branching, pull requests and code review
Applying relevant statistical methods to support analysis

Benefits

Competitive salary and non-contributory pension
25 days annual leave plus bank holidays
"""
reqs = extract.requirements(LINKEDIN)
check("đọc được danh sách dù không có dấu gạch", len(reqs) >= 4)
check("lấy đúng nguyên văn", any("Dataform" in r.text for r in reqs))
check("đánh dấu nguồn là 'list', không phải 'bullet'",
      all(r.source == "list" for r in reqs))
check("độ tin cậy vừa phải, không phải 'high'",
      extract.confidence(reqs) == "medium")
check("KHÔNG nuốt phúc lợi vào làm yêu cầu",
      not any("pension" in r.text.lower() or "annual leave" in r.text.lower()
              for r in reqs))
scored = score_job("Data Analyst", LINKEDIN, PROFILE)
check("và chấm ra điểm thật", scored["score"] is not None)

# Đoạn văn xuôi đứng lẻ giữa hai dòng trống KHÔNG được coi là mục danh sách
PROSE_ONLY = """About us

We are a great company with a long history of doing interesting things.

We believe in people and in building software that lasts a long time.
"""
check("đoạn văn lẻ không bị coi là danh sách",
      not [r for r in extract.requirements(PROSE_ONLY) if r.source == "list"])

print("\n[CẤP BẬC — phải chạy cho MỌI người, không chỉ cho một hồ sơ grad]")
from jobbot.scoring.score import _level_fit as _lf, _bac_tieu_de as _bt, BAC as _BAC

def _diem(title, muc):
    return _lf(title, {"seniority": muc})

# Đây là bài quan trọng nhất của khối: bản cũ CHỈ hỏi "có nhắm junior không",
# nên hồ sơ nhắm senior nhận 0.6 cho mọi tin — kể cả tin ghi "Graduate" to
# tướng ở đầu đề. Chạy đúng cho một người không phải là chạy đúng.
check("người nhắm SENIOR: tin senior được điểm cao",
      _diem("Senior Software Engineer", ["senior"])[0] == 1.0)
check("người nhắm SENIOR: tin graduate bị loại, không phải 0.6",
      _diem("Graduate Software Engineer", ["senior"])[0] == 0.0)
check("người nhắm SENIOR: tin lệch một bậc được nửa điểm",
      _diem("Staff Engineer", ["senior"])[0] == 0.5)
check("người nhắm MID: tin mid khớp", _diem("Mid-level Developer", ["mid"])[0] == 1.0)
check("người nhắm LEAD: tin thực tập lệch xa nhất",
      _diem("Summer Internship", ["lead"])[0] == 0.0)
check("người nhắm grad+junior: tin senior vẫn bị loại như cũ",
      _diem("Senior Software Engineer", ["grad", "junior"])[0] == 0.0)
check("người nhắm grad+junior: tin graduate vẫn 1.0 như cũ",
      _diem("Graduate Analyst", ["grad", "junior"])[0] == 1.0)

# Không biết thì phải NÓI không biết, và nói không biết CÁI GÌ.
check("đầu đề không nói cấp bậc -> 0.6 và nói đúng vậy",
      _diem("Software Engineer", ["senior"]) == (0.6, "level not stated in the title"))
_d, _vi = _diem("Senior Software Engineer", [])
check("hồ sơ bỏ trống cấp bậc -> vẫn 0.6 nhưng nói LÝ DO THẬT",
      _d == 0.6 and "haven't said" in _vi)
check("chữ tự do lạ trong hồ sơ không làm nó nói dối",
      "haven't said" in _diem("Senior Software Engineer", ["cap-bac-la"])[1])

# "Program Manager" KHÔNG phải tin sinh viên mới ra trường. Đo thật: 34 tin
# trong DB khớp "program|programme" mà không phải tin grad, và luật cũ cho
# chúng 1.0 "explicitly graduate/junior" — tin senior nhảy từ 0 lên 20 điểm.
check("«Program Manager» không bị coi là tin graduate",
      _bt("Technical Program Manager") is None)
check("«Senior Technical Program Manager» là SENIOR, không phải graduate",
      _diem("Senior Technical Program Manager", ["grad", "junior"])[0] == 0.0)
check("nhưng «Summer Analyst Programme» thì đúng là tin graduate",
      _bt("2027 MUFG UK Summer Analyst Programme") == 0)
check("«Graduate Programme» cũng vậy", _bt("Graduate Programme, Technology") == 0)

# Từ cấp cao mà bản cũ bỏ sót.
for _t in ("Portfolio Analytics Engineer - Vice President", "Chief of Staff",
           "Head of Engineering", "Director of Data"):
    check(f"«{_t[:34]}» nhận ra là cấp cao", _bt(_t) == 4)
check("«Early Careers» nhận ra là tin entry", _bt("Software Engineer, Early Careers") == 0)

# Đầu đề khớp cả hai đầu thang -> lấy bậc THẤP: mất tin tệ hơn thấy thừa.
check("đầu đề có cả graduate lẫn senior -> tính là graduate",
      _bt("Graduate Programme — Senior Analyst track") == 0)

# Thang phải phủ HẾT lựa chọn trong hồ sơ, không sót cái nào.
from jobbot.profile.schema import all_questions as _aq
_o = _aq()["seniority"].options
_thieu = [x.value for x in _o if x.value not in _BAC]
check(f"mọi lựa chọn cấp bậc trong hồ sơ đều có chỗ trên thang{' — thiếu: ' + str(_thieu) if _thieu else ''}",
      not _thieu)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
