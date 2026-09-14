"""Test M0 — hồ sơ người dùng. Chạy: python3 tests/test_profile.py"""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db
import os as _os
from jobbot.profile import store
from jobbot.profile.schema import INGEST_GATE, SECTIONS, all_questions, section_by_id
from jobbot.dashboard.server import _form_to_answers

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

print("\n[schema]")
qs = all_questions()
ids = [q.id for s in SECTIONS for q in s.questions]
check("không trùng id câu hỏi", len(ids) == len(set(ids)))
check("mọi câu chọn đều có option", all(
    q.options for q in qs.values() if q.kind in ("single", "multi")))
check("cổng ingest tồn tại trong schema", all(q in qs for q in INGEST_GATE))
check("job_titles là câu tự do, không phải danh sách cố định",
      qs["job_titles"].kind == "longtext" and not qs["job_titles"].options)
# Ba câu CHẾT của phần project cũ (proof_jds, existing_projects,
# project_numbers) đã bỏ — không chỗ nào trong app đọc chúng. Phần project
# quay lại với hình dạng khác: KHỐI, ghi thẳng vào cv_text, tức là thứ bộ chấm
# điểm và bộ dựng CV thật sự đọc.
check("ba câu chết đã bỏ",
      not any(q in all_questions() for q in
              ("proof_jds", "existing_projects", "project_numbers")))
check("kinh nghiệm & project là mục riêng của HỒ SƠ — đó là thông tin cá nhân",
      section_by_id("kinh_nghiem") is not None
      and section_by_id("project") is not None)
check("và lưu vào khối cv_text, không đẻ bản sao",
      all_questions()["experience_blocks"].block_kind == "experience"
      and all_questions()["project_blocks"].block_kind == "project")
# Máy nhập CV xong đã rút ra khối rồi thì phải TÍNH LÀ XONG. Chỉ nhìn bảng
# profile_answer thì Home báo "0/1 — chưa xong" trong khi dữ liệu đã nằm đó.
_cv_khoi = ("DAC VINH NGUYEN\n\nEXPERIENCE\n"
            "Quant Analyst — Schonfeld Jan 2025 – Sep 2025\n  did a thing\n")
check("có khối trong cv_text thì câu đó coi như đã trả lời",
      store.has_answer({"cv_text": _cv_khoi}, all_questions()["experience_blocks"]))
check("không có khối thì chưa",
      not store.has_answer({"cv_text": _cv_khoi}, all_questions()["project_blocks"]))
check("và mục kinh nghiệm được tính là XONG",
      store.is_section_done({"cv_text": _cv_khoi}, section_by_id("kinh_nghiem")))
check("work_auth nằm trong phần mục tiêu, không phải danh tính",
      any(q.id == "work_auth" for q in section_by_id("muc_tieu").questions))
check("không còn lựa chọn riêng của thị trường VN",
      not any(o.value.startswith("vn_") for q in all_questions().values() for o in q.options))
check("không câu bắt buộc nào nằm ngoài cổng ingest",
      {q.id for q in qs.values() if q.required} == set(INGEST_GATE))

print("\n[lưu trữ]")
with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "t.db")

    check("DB trống -> hồ sơ rỗng", store.load(conn) == {})
    check("DB trống -> chưa tìm được", not store.can_ingest({}))
    check("nêu đúng cái còn thiếu", store.missing_for_ingest({}) == list(INGEST_GATE))

    store.save(conn, {"job_titles": "Backend Engineer"}, "t")
    check("thiếu markets + work_auth -> vẫn chặn",
          store.missing_for_ingest(store.load(conn)) == ["markets", "work_auth"])

    store.save(conn, {"markets": ["uk_remote"], "work_auth": "citizen"}, "t")
    answers = store.load(conn)
    check("đủ 3 câu -> mở cổng", store.can_ingest(answers))
    check("câu cũ được mang sang", answers["job_titles"] == "Backend Engineer")
    check("lịch sử giữ 2 phiên bản", len(store.history(conn)) == 2)

    store.save(conn, {"khong_ton_tai": "x"}, "rác")
    check("bỏ qua câu ngoài schema", "khong_ton_tai" not in store.load(conn))

    check("phần kế tiếp đúng thứ tự", store.next_section("muc_tieu").id == "rang_buoc")
    check("phần cuối -> hết", store.next_section(SECTIONS[-1].id) is None)
    conn.close()

print("\n[đọc form]")
a = _form_to_answers({"markets": ["uk_remote", "HACK"],
                      "markets__other": ["Ireland, Netherlands"]}, "muc_tieu")
check("bỏ giá trị không có trong option", "HACK" not in a["markets"])
check("giữ giá trị hợp lệ", "uk_remote" in a["markets"])
check("ô tự do được gộp vào", a["markets"] == ["uk_remote", "Ireland", "Netherlands"])

b = _form_to_answers({"work_auth__other": ["Graduate visa, hết hạn 03/2027"]}, "muc_tieu")
check("câu chọn-một cũng nhận ô tự do", b["work_auth"] == "Graduate visa, hết hạn 03/2027")

c = _form_to_answers({"job_titles": ["  Backend Engineer\nSWE  "]}, "muc_tieu")
check("text được cắt khoảng trắng", c["job_titles"] == "Backend Engineer\nSWE")



print("\n[cổng chặn phải NÓI RA, không lặng lẽ bỏ cuộc]")
# Người dùng mới bấm Chạy khi hồ sơ trống: trước đây run_scan `return` lặng lẽ,
# API vẫn đáp "đang chạy…", nhật ký trống, không tin nào về — ngồi chờ vô tận.
import os as _os
_tmp = tempfile.mkdtemp()
# JOBBOT_DATA_DIR, KHÔNG phải JOBBOT_DB — không có biến nào tên vậy. Bản cũ
# gõ sai tên nên bài test chạy thẳng vào DB THẬT: lúc hồ sơ còn trống nó vẫn
# xanh (cổng đóng, quét bị từ chối), nhưng hồ sơ vừa đủ cổng là nó QUÉT THẬT
# — 2.226 tin ghi vào DB của người dùng chỉ vì chạy test.
_os.environ["JOBBOT_DATA_DIR"] = _tmp
try:
    # Và kiểm lại, đừng tin mỗi cái gán: bài test này gọi run_scan, tức là có
    # thể mở mạng và ghi hàng nghìn dòng. Sai chỗ một lần là hỏng dữ liệu thật.
    from jobbot.core.paths import db_path as _dbp
    assert str(_dbp()).startswith(_tmp), f"test đang trỏ vào DB THẬT: {_dbp()}"
    from jobbot.core import journal as _journal
    from jobbot import scan_runner as _sr
    _conn = db.connect()
    db.migrate(_conn)
    _journal.log.open()
    _noi = []
    _kq = _sr.run_scan(log=_noi.append, chrome_sources=False, deep=False)
    check("hồ sơ trống thì từ chối quét", _kq["ok"] is False)
    check("và NÓI RA lý do", bool(_noi) and "profile is incomplete" in _noi[0])
    check("lý do nêu đúng tên câu còn thiếu",
          bool(_noi) and all(all_questions()[q].text[:20] in _noi[0]
                             for q in _kq["missing"]))
    _dong = _conn.execute(
        "SELECT COUNT(*) FROM audit WHERE level='warn' AND detail LIKE '%cannot scan yet%'"
    ).fetchone()[0]
    check("và ghi vào nhật ký", _dong >= 1)
finally:
    _os.environ.pop("JOBBOT_DATA_DIR", None)


print("\n[nhập CV phải mở được CỔNG, không chỉ điền phần danh tính]")
# Trước đây import rút 9 ô nhưng KHÔNG ô nào thuộc cổng (job_titles, markets,
# work_auth) — nhập CV xong vẫn không chạy được gì, vẫn phải gõ tay.
from jobbot.profile.import_cv import propose as _propose
_cv = """DAC VINH NGUYEN
London, United Kingdom | vin@example.com | +44 7000 000000

EXPERIENCE
Quantitative Analyst Intern — Schonfeld
  Built an analyst dashboard for the risk team using Python and pandas.
Research Consultant — WorldQuant BRAIN

TECHNICAL SKILLS
Python, pandas, SQL, machine learning, backtesting

References available on request.
"""
_p = {x.field: x.value for x in _propose(_cv, {})}
check("đề xuất được chức danh", "job_titles" in _p)
# Hai luật dưới đây rút ra từ một CV THẬT đọc hụt: chức danh + công ty + ngày
# tháng nằm CÙNG MỘT DÒNG (81 ký tự), và có mục SELECTED PROJECTS trông y hệt.
_that = """DAC VINH NGUYEN
London, United Kingdom

EXPERIENCE
Founder / Quantitative Developer — Algorithmic Trading Startup Jan 2024 – Present
  Built the whole pipeline end to end.
Research Consultant — WorldQuant (BRAIN platform) Jan 2025 – Sep 2025

SELECTED PROJECTS
Quant Trading Studio — the whole pipeline turned into something a firm could run

TECHNICAL SKILLS
Python, pandas
"""
_pt = {x.field: x.value for x in _propose(_that, {})}
_tt = (_pt.get("job_titles") or "").splitlines()
check("dòng dài (chức danh + công ty + ngày) vẫn rút được",
      "Founder / Quantitative Developer" in _tt)
check("cắt được đuôi ngày tháng", "Research Consultant" in _tt)
check("KHÔNG lấy tên project ở mục SELECTED PROJECTS làm chức danh",
      not any("Quant Trading Studio" in t for t in _tt))
check("đọc đúng chức danh, bỏ tên công ty",
      _p.get("job_titles", "").splitlines()[:1] == ["Quantitative Analyst Intern"])
check("KHÔNG nhận câu mô tả làm chức danh",
      "Built an analyst dashboard" not in _p.get("job_titles", ""))
check("KHÔNG nhận 'References available on request'",
      "References" not in _p.get("job_titles", ""))
check("đề xuất được thị trường từ địa điểm",
      _p.get("markets") == ["uk_onsite", "uk_remote"])
check("đề xuất bậc từ chữ in trên CV", "intern" in (_p.get("seniority") or []))
# Đây là luật CỐ Ý, không phải thiếu sót: quyền làm việc là sự thật pháp lý
# về con người, CV không nói, đoán sai thì hỏng cả lá đơn.
check("KHÔNG BAO GIỜ đoán quyền làm việc", "work_auth" not in _p)
_con = [q for q in INGEST_GATE if q not in _p]
check("nhập CV xong chỉ còn đúng 1 câu phải tự trả lời", _con == ["work_auth"])
# Không đè lên thứ người dùng đã tự điền.
_p2 = {x.field for x in _propose(_cv, {"job_titles": "Quant Researcher"})}
check("ô đã có sẵn thì không đề xuất đè", "job_titles" not in _p2)
# MỘT ngoại lệ, cố ý: cv_text. "Nhập một CV mới" rõ ràng là muốn thay bản cũ,
# mà ô dán CV đã bỏ khỏi form — không cho thay ở đây thì CV đóng băng vĩnh
# viễn, không còn đường nào sửa.
_p3 = {x.field: x for x in _propose(_cv, {"cv_text": "CV CŨ", "full_name": "X"})}
check("nhập CV mới THAY được bản cũ", "cv_text" in _p3)
# LUẬT TỔNG QUÁT. store.save() lọc theo schema, nên MỌI ô mà máy nhập đề xuất
# đều phải có trong schema — thiếu một cái là nó lặng lẽ không bao giờ được
# lưu, mà màn hình duyệt vẫn tick xanh như thường.
_lac = [f for f in _p if f not in all_questions()]
check(f"mọi ô máy nhập đề xuất đều LƯU được {_lac or ''}", not _lac)
check("và nói rõ là sẽ thay", "THAY bản CV đang lưu" in _p3["cv_text"].note)
check("còn ô khác vẫn giữ luật không-đè", "full_name" not in _p3)
# cv_text KHÔNG vẽ ra form, nhưng PHẢI ở lại schema. store.save() lọc theo
# schema — gỡ khỏi đó là nó lặng lẽ không lưu được nữa. Đã mất nguyên toàn văn
# CV vì đúng chuyện này: nhập CV báo "13 fields" mà chỉ 12 câu vào DB.
check("cv_text vẫn ở trong schema để LƯU được", "cv_text" in all_questions())
check("nhưng không vẽ ra form", all_questions()["cv_text"].hidden)
_tmpdb = tempfile.mkdtemp()
_env_cu = _os.environ.get("JOBBOT_DATA_DIR")
_os.environ["JOBBOT_DATA_DIR"] = _tmpdb
try:
    import importlib as _il2
    from jobbot.core import paths as _p2
    _il2.reload(_p2)
    _c2 = db.connect(Path(_tmpdb) / "t.db")
    db.migrate(_c2)
    store.save(_c2, {"cv_text": "EXPERIENCE\nQuant Analyst — X Jan 2025 – Sep 2025\n"}, "t")
    check("lưu cv_text rồi đọc lại được",
          "Quant Analyst" in str(store.load(_c2).get("cv_text") or ""))
    _c2.close()
finally:
    if _env_cu is None:
        _os.environ.pop("JOBBOT_DATA_DIR", None)
    else:
        _os.environ["JOBBOT_DATA_DIR"] = _env_cu
    import importlib as _il3
    from jobbot.core import paths as _p3
    _il3.reload(_p3)

print("\n[học vấn & chứng chỉ — HÌNH DẠNG phải khớp ngữ pháp hệ thống đọc]")
# cv/build.py làm `certs.splitlines()[0]` để lấy chứng chỉ mạnh nhất, score.py
# cũng đọc theo dòng. CV thật viết "A · B · C" trên MỘT dòng — giữ nguyên thì
# máy đếm ra 1 chứng chỉ trong khi có 3, và CV nhét cả cụm làm một "fact".
_cv2 = """DAC VINH NGUYEN
London, UK

EDUCATION
MSc Computational Finance — Royal Holloway, University of London 2025 – 2026
Investment & Portfolio Management 86 · Data Analysis 83
BA (Hons) Advanced Finance — National Economics University, Vietnam
·
Certifications — CFA Level I, October 2024 · IBM Data Science · IBM Machine Learning
"""
_d2 = {x.field: x.value for x in _propose(_cv2, {})}
_ce = str(_d2.get("certifications", "")).splitlines()
check("mỗi chứng chỉ một dòng", len(_ce) == 3)
check("không nuốt mất cái nào", "IBM Machine Learning" in _ce)
_ed = str(_d2.get("education", "")).splitlines()
check("bỏ dòng rác chỉ có dấu chấm", "·" not in _ed)
check("nhưng giữ nguyên dòng điểm môn",
      any("Investment & Portfolio Management" in l for l in _ed))
# Và ô chứng chỉ phải là Ô THẺ, để sửa tay cũng không phá được hình dạng đó.
check("certifications là ô thẻ nối bằng xuống dòng",
      all_questions()["certifications"].tags == "\n")
# Ngữ pháp học vấn phải được NÓI RA ở chỗ người ta gõ — apply/answer cần đúng
# dạng đó mới điền hộ được ngày tốt nghiệp trên form xin việc.
check("ô học vấn nói rõ ngữ pháp hệ thống đọc",
      "MỘT BẰNG MỘT DÒNG" in all_questions()["education"].why)

print("\n[học vấn — MỘT ngữ pháp, ghi và đọc cùng dùng]")
# Đây là ô CÓ TẢI: apply/answer đọc nó ra ngày tốt nghiệp để điền form xin
# việc. Form ghi bằng line(), máy đọc bằng educations() — lệch nhau là form
# ghi ra thứ máy không hiểu, và mỗi lá đơn Vin phải tự chọn lại ngày.
from jobbot.apply.answer import educations as _eds, line as _eline, education as _ed1
from jobbot.profile.schema import ROWS as _ROWS
check("ô học vấn là kiểu HÀNG, không phải chữ thô",
      all_questions()["education"].kind == _ROWS)
_l = _eline("MSc", "Computational Finance", "Royal Holloway", "Sep 2025", "Sep 2026", "IPM 86")
_back = _eds(_l)[0]
check("ghi rồi đọc lại ra đúng bằng", _back.degree == "MSc")
check("đúng ngành", _back.discipline == "Computational Finance")
check("đúng trường", _back.school == "Royal Holloway")
check("GIỮ được tháng — thứ mà form xin việc hỏi",
      (_back.start_month, _back.start_year) == (9, 2025)
      and (_back.end_month, _back.end_year) == (9, 2026))
check("và không còn báo thiếu tháng", _ed1(_l).missing == [])
check("ghi chú thành dòng phụ, không thành bằng thứ hai",
      len(_eds(_l)) == 1 and "IPM 86" in _back.note)
# CV thật viết điểm môn SÁT LỀ, không thụt vào. Nhận nhầm thì nó hiện ra
# thành một cái bằng tên "Investment".
_ban = ("MSc Computational Finance — Royal Holloway, 2025 – 2026\n"
        "Investment & Portfolio Management 86 · Data Analysis 83\n"
        "BA (Hons) Advanced Finance — National Economics University")
_hai = _eds(_ban)
check("dòng điểm môn sát lề KHÔNG bị nhận thành bằng", len(_hai) == 2)
check("mà thành ghi chú của bằng ngay trên nó",
      "Investment & Portfolio Management 86" in _hai[0].note)


print("\n[kho chức danh rút từ TIN THẬT, không gõ tay]")
# Câu hỏi nói "viết ĐÚNG như trên tin", nên nguồn đúng duy nhất là chính tin.
# Danh sách gõ tay trong mã sai ngay từ ngày viết và mục dần từ đó.
from jobbot.profile.titles import extract as _extract
from jobbot.profile.schema import suggestions as _sug
check("schema KHÔNG còn danh sách chức danh gõ tay", _sug("titles") == [])
check("kho kỹ năng vẫn lấy từ vựng chấm điểm", len(_sug("skills")) > 20)
# Kho ngành cũng KHÔNG gõ tay: nó đúng bằng bộ ngành mà projects/inventory.py
# dùng để dán nhãn cho tin thật. Gõ danh sách riêng cho màn hình thì người
# dùng chọn được ngành mà máy không biết nhận ra.
from jobbot.scoring.vocab import INDUSTRY as _IND
check("kho ngành lấy từ bộ máy ĐANG dùng để nhận ngành trên tin",
      _sug("industries") == sorted(_IND))
check("ô ngành là ô thẻ", all_questions()["industries"].tags == ", ")
check("và nói rõ để trống = không kén ngành",
      "Để TRỐNG" in all_questions()["industries"].why)

# Tiêu đề thật trông như thế này — dùng nguyên thì vô dụng làm gợi ý.
_that = ["2027 Point72 Academy Investment Analyst Summer Internship - Japan (BCF)",
         "Investment Analyst", "Investment Analyst - London",
         "Quantitative Researcher", "Quantitative Researcher (Systematic)",
         "Quantitative Researcher — New York", "Software Engineer, Platform",
         "Software Engineer", "Software Engineer - Backend"]
_cum = dict(_extract(_that, least=2))
check("rút ra CỤM NGHỀ chứ không giữ nguyên tiêu đề",
      "Quantitative Researcher" in _cum)
check("bỏ được đuôi địa điểm", _cum.get("Quantitative Researcher") == 3)
check("bỏ được phần trong ngoặc", "Investment Analyst" in _cum)
check("KHÔNG giữ cụm dính năm", not any(c[0].isdigit() for c in _cum))
check("cụm phải KẾT THÚC bằng từ nghề",
      all(c.split()[-1].lower() in
          {"analyst","engineer","scientist","developer","researcher","manager",
           "trader","strategist","consultant","associate","specialist",
           "architect","lead","intern","quant","technologist","administrator"}
          for c in _cum))
# Sàn: cụm chỉ gặp một lần thường là tên chương trình riêng của một công ty.
check("có sàn số tin, không nhận cụm gặp một lần",
      all(v >= 2 for v in _cum.values()))

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
