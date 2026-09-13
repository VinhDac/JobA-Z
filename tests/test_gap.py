"""Khối HỤT — viết thêm câu về cái gì thì bao nhiêu TIN HẾT HỤT."""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else: fail += 1; print(f"  FAIL {name}")

from jobbot.scoring.gap import tin_tron, thang, NAMED_TOOL, _tin

print("[đơn vị là TIN HẾT HỤT, không phải lượt]")
# Một tin = danh sách dòng must. Hết hụt = MỌI dòng đều đáp được. Một dòng
# đáp được khi nó đòi ít nhất một thứ mình có — luật "hoặc": JD ghi
# "C++, Java hoặc Python" mà mình có Python thì dòng đó xong.
_t = [
    [({"python"}, False), ({"sql"}, False)],            # cần cả python lẫn sql
    [({"python", "java"}, False)],                      # python HOẶC java
    [({"cloud"}, True)],                                # chỉ cloud
]
check("có đủ mọi thứ -> tin hết hụt", tin_tron(_t, {"python", "sql", "cloud"}) == 3)
check("thiếu một dòng -> tin đó CHƯA hết hụt", tin_tron(_t, {"python"}) == 1)
check("luật HOẶC: có python là đủ cho dòng 'python hoặc java'",
      tin_tron(_t, {"python"}) >= 1)
check("không có gì -> 0 tin", tin_tron(_t, set()) == 0)
check("thêm kỹ năng không ai đòi -> không đổi gì",
      tin_tron(_t, {"python"}) == tin_tron(_t, {"python", "rust"}))

print("\n[VIẾT / HỌC: chia bằng luật, không bằng phán đoán]")
for _s in ("experience with AWS", "Docker and Kubernetes", "Power BI dashboards",
           "kdb+/q", "Tableau reporting", "Apache Spark"):
    check(f"gọi đích danh -> HỌC: {_s[:28]}", bool(NAMED_TOOL.search(_s)))
for _s in ("present findings to stakeholders", "build data pipelines",
           "strong analytical skills", "visualise results clearly"):
    check(f"nói chung chung -> VIẾT được: {_s[:28]}", not NAMED_TOOL.search(_s))

print("\n[thang cộng dồn: giá trị BIÊN, không phải cộng lại]")
import sqlite3, json
_db = sqlite3.connect(":memory:")
_db.row_factory = sqlite3.Row
_db.execute("CREATE TABLE posting (id INTEGER PRIMARY KEY, kept INT,"
            " realism TEXT, score_json TEXT)")
def _them(i, dong):
    _db.execute("INSERT INTO posting VALUES (?,1,'likely',?)",
                (i, json.dumps({"requirements":
                                [{"text": d, "must": True} for d in dong]})))
# Ba tin, cả ba cùng thiếu visualisation -> nó mở khoá cả ba MỘT LẦN.
for i in (1, 2, 3):
    _them(i, ["strong Python", "data visualisation skills"])
_them(4, ["strong Python", "experience with AWS"])
_db.commit()
_d = thang(_db, {"python"})
check("đếm đúng số tin có dòng must", _d["tin"] == 4)
check("nền = số tin đã hết hụt sẵn", _d["nen"] == 0)
_b = _d["buoc"]
check("bước đầu là thứ mở khoá NHIỀU TIN NHẤT", _b and _b[0]["ky_nang"] == "visualisation")
check("và nói đúng mở thêm mấy tin", _b and _b[0]["them"] == 3)
check("cộng dồn là TỔNG sau bước đó, không phải tổng cộng lại",
      _b and _b[0]["cong_don"] == 3)
# Bước hai chỉ còn 1 tin để mở — giá trị BIÊN, không phải giá trị riêng lẻ.
check("bước sau chỉ tính phần CÒN LẠI", len(_b) < 2 or _b[1]["them"] == 1)
check("cloud gọi đích danh AWS -> nhãn HỌC",
      all(x["viec"] == "hoc" for x in _b if x["ky_nang"] == "cloud"))

print("\n[hai đích: viết được tối nay vs phải đi học]")
check("có con số CHỈ VIẾT riêng", "chi_viet" in _d)
check("chỉ viết thì <= làm hết", _d["chi_viet"] <= (_b[-1]["cong_don"] if _b else 0))
check("và đếm đúng số câu phải viết",
      _d["so_viet"] == sum(1 for x in _b if x["viec"] == "viet"))
_db.close()

print("\n[kho RỖNG cũng không được làm sập]")
_e = sqlite3.connect(":memory:"); _e.row_factory = sqlite3.Row
_e.execute("CREATE TABLE posting (id INTEGER PRIMARY KEY, kept INT,"
           " realism TEXT, score_json TEXT)")
_r = thang(_e, {"python"})
check("kho rỗng -> trả về 0, không nổ", _r["tin"] == 0 and _r["buoc"] == [])
_e.close()

print("\n[viết một câu mới: máy dọn chỗ, NGƯỜI viết]")
from jobbot.scoring.gap import ho_hoi, nen_nhap, qua_giong, ta_viec
from jobbot.dashboard.views import cvsoan as _cs

_c2 = sqlite3.connect(":memory:"); _c2.row_factory = sqlite3.Row
_c2.execute("CREATE TABLE posting (id INTEGER PRIMARY KEY, kept INT,"
            " realism TEXT, score TEXT, company TEXT, title TEXT, score_json TEXT)")
def _t2(i, cty, dong):
    _c2.execute("INSERT INTO posting VALUES (?,1,'likely','90',?,'Analyst',?)",
                (i, cty, json.dumps({"requirements":
                                     [{"text": d, "must": True} for d in dong]})))
_t2(1, "Bonhill", ["Improve research frameworks, data pipelines and models"])
_t2(2, "Durlston", ["ETL across an Azure-hosted Data Lake"])
# Nhiều tin chép chung một câu mẫu — brief in lặp thì chỗ đọc được bị ăn mất.
_t2(3, "Nhai Lai", ["Improve research frameworks, data pipelines and models"])
_c2.commit()
_chung, _rieng = ho_hoi(_c2, "data pipeline")
check("tách dòng VIẾT ĐƯỢC khỏi dòng gọi đích danh tên sản phẩm",
      len(_chung) == 1 and len(_rieng) == 1)
check("dòng trùng chữ chỉ in MỘT lần, dù hai tin cùng đòi",
      [m["cong_ty"] for m in _chung] == ["Bonhill"])
check("dòng chung chung là dòng không nhắc tên sản phẩm",
      _chung and "Azure" not in _chung[0]["chu"])
check("in NGUYÊN VĂN, không tóm tắt",
      _chung and _chung[0]["chu"].startswith("Improve research frameworks"))
check("kèm tên công ty để biết đây là yêu cầu THẬT",
      _chung and _chung[0]["cong_ty"] == "Bonhill")
_nn = nen_nhap(_c2, "data pipeline")
_c2.close()

# NỀN BẢN NHÁP: chỉ dòng TẢ VIỆC mới đổi sang câu CV được.
#
# Nhãn VIẾT của thang hụt nói "dòng này không gọi đích danh tên sản phẩm, nên
# diễn đạt lại bằng chữ của mình được". Nói vậy rồi mà chỉ đưa ra ô trống thì
# cái nhãn là lời hứa suông — nên nhãn VIẾT phải đi kèm nền bản nháp.
check("dòng tả VIỆC dùng làm nền được",
      ta_viec("Build and maintain data pipelines, ensuring data quality"))
check("danh động từ mở đầu cũng là tả việc",
      ta_viec("Developing and maintaining data pipelines and live processes"))
# Đo trên kho thật: 12/22 dòng chung chung đòi `visualisation` là tả phẩm chất.
# "Interest in statistics" thì viết lại thành câu CV nào?
check("dòng tả PHẨM CHẤT thì KHÔNG",
      not ta_viec("Interest in statistics, data visualisation or modelling"))
check("kể cả khi có tính từ đứng trước",
      not ta_viec("Solid experience with SQL, Excel and at least one BI tool")
      and not ta_viec("Detailed understanding of data mining and warehousing"))
check("và danh từ ngành nghề đuôi -ing cũng không phải việc",
      not ta_viec("Engineering degree or equivalent industrial experience"))
check("nền lấy từ dòng yêu cầu THẬT, kèm tên công ty",
      len(_nn) == 1 and _nn[0]["cong_ty"] == "Bonhill")

# CHỐT CHẶN: nền là chữ NGUYÊN VĂN của nhà tuyển dụng. Lưu nguyên nó vào CV
# là hai cái hại — người sàng đọc ra chữ trong tin tuyển của chính mình, và
# người dùng phải đỡ một khẳng định họ chưa từng đưa ra.
_ne = "Build and maintain data pipelines, ensuring data quality and consistency"
check("chép nguyên -> bị bắt", qua_giong(_ne, _ne) == 1.0)
# Đổi mỗi THÌ của động từ vẫn là dòng của họ, không phải việc mình kể.
check("đổi mỗi thì -> vẫn bị bắt",
      qua_giong("Built and maintained data pipelines, ensuring data quality", _ne) >= 0.6)
check("câu nói ĐÚNG chủ đề đó nhưng là việc của mình -> qua",
      qua_giong("Rebuilt the research pipeline so a 40-minute reconciliation "
                "runs in 90 seconds over 17 feeds.", _ne) < 0.6)
check("câu thật của mình -> qua",
      qua_giong("Built a nightly pipeline in Python that validated 17 instrument "
                "feeds and cut reconciliation from 40 minutes to 90 seconds.",
                _ne) < 0.6)
check("viết dài thêm ra KHÔNG làm loãng phép đo",
      qua_giong(_ne + " across every desk and region we cover", _ne) == 1.0)

# VIẾT MỘT CÂU MỚI VÀ SỬA KHỐI LÀ MỘT VIỆC. Cả hai ghi vào cùng `cv_text`,
# nên chúng dùng chung một màn (/cv/soan) — không phải một tấm phủ riêng đọc
# yêu cầu ở chỗ này rồi gõ ở chỗ khác.
_c3 = sqlite3.connect(":memory:"); _c3.row_factory = sqlite3.Row
_c3.execute("CREATE TABLE posting (id INTEGER PRIMARY KEY, kept INT,"
            " realism TEXT, score TEXT, company TEXT, title TEXT, score_json TEXT)")
_c3.execute("INSERT INTO posting VALUES (1,1,'likely','90','Bonhill','Analyst',?)",
            (json.dumps({"requirements": [
                {"text": "Improve research frameworks and data pipelines",
                 "must": True}]}),))
_c3.commit()
_ch3, _ri3 = ho_hoi(_c3, "data pipeline")
_c3.close()
_kh3 = [{"title": "Khối A", "kind": "project", "lines": ["x"], "reach": 9}]
_d3 = {"ky": "data pipeline", "chung": _ch3, "rieng": _ri3,
       "nen": [m for m in _ch3 if ta_viec(m["chu"])]}
_bf = _cs._viet(_d3, "", "", "", _kh3)

check("brief in NGUYÊN VĂN dòng yêu cầu, ngay trên chỗ gõ",
      "Improve research frameworks" in _bf)
check("và kèm tên công ty — đây là yêu cầu THẬT của một tin thật",
      "Bonhill" in _bf)
# Dòng nền phải BẤM ĐƯỢC: bấm là nó rơi vào ô soạn, khỏi gõ lại.
check("bấm một dòng nền là nó rơi vào ô soạn",
      "&nen=Improve%20research%20frameworks" in _bf)
check("và giữ nguyên đích đang nhắm", "ky=data%20pipeline" in _bf)

# BA BƯỚC ĐÁNH SỐ. Phản hồi thật của người dùng trên bản phẳng trước đó:
# "tôi không biết phải bấm cái gì, viết như nào, confirm cái gì".
check("màn viết chia BA BƯỚC có đánh số", _bf.count("class=buocso") == 3)
check("bước 1 nói rõ phải bấm gì", "Dùng dòng này" in _bf)
check("bước 2 cho chọn khối ngay tại chỗ",
      "Viết vào khối nào" in _bf and "Khối A" in _bf)
check("bước 3 nói rõ confirm cái gì",
      "Viết lại thành việc BẠN đã làm" in _bf)
# Chưa chọn khối thì chưa có ô gõ — nói ra, đừng để một ô chết nằm đó.
check("chưa chọn khối -> bước 3 chỉ đường, không đưa ô chết",
      "Chọn khối ở bước 2" in _bf and "name=line" not in _bf)

# Chọn đủ thì bước 1-2 gập lại, bước 3 mở ra với ô và nút.
_bf2 = _cs._viet(_d3, "Khối A", "Improve research frameworks", "", _kh3)
check("chọn xong thì bước đã xong gập lại thành dòng đổi được",
      "class=dachon" in _bf2 and "Đổi dòng" in _bf2)
check("và ô gõ hiện ra, có sẵn nền", "name=line" in _bf2
      and "Improve research frameworks" in _bf2)
check("nút Lưu nói rõ câu này đi vào ĐÂU", "Thêm câu này vào" in _bf2)
check("và ghi rõ mấy câu đang có KHÔNG bị đụng",
      "giữ nguyên" in _bf2 and "name=them value=1" in _bf2)
check("nói thẳng vì sao máy không viết hộ",
      "không biết bạn đã làm gì" in _bf)
check("nhắc câu trên CV là câu phải ĐỠ ĐƯỢC lúc phỏng vấn",
      "phòng phỏng vấn" in _bf)
check("KHÔNG có nút nào 'máy viết hộ'",
      "tự viết" not in _bf.lower()
      and "máy viết" not in _bf.lower().replace("máy không viết", ""))

# Ô soạn phải TRỐNG. Gợi ý trong placeholder được phép — nó nói VIẾT VỀ CÁI
# GÌ; điều cấm là đưa sẵn một CÂU để người ta sửa vài chữ rồi nộp.
_fm = _cs._form(None, [], "data pipeline")
# Ô soạn CÓ NỀN: chữ rơi vào ô phải được gắn nhãn là của ai, ngay tại chỗ.
_d4 = {"ky": "data pipeline", "chung": [], "rieng": [], "nen": []}
_fn = _cs._viet(_d4, "Khối A", _ne, "", _kh3)
check("nền rơi đúng vào ô soạn", _ne in _fn)
check("và ghi rõ đây CHƯA phải câu của bạn",
      "chữ của nhà tuyển dụng" in _fn and "chưa phải câu của bạn" in _fn)
check("nền đi theo form để lượt Lưu so lại được",
      "name=nen value=" in _fn)
_fl = _cs._viet(_d4, "Khối A", _ne, "Câu này vẫn gần như nguyên văn", _kh3)
check("bị từ chối thì lời từ chối đứng NGAY TRÊN ô, chữ vừa gõ còn nguyên",
      "Câu này vẫn gần như nguyên văn" in _fl and _ne in _fl)
check("ô soạn để trống — không câu mẫu nào nằm sẵn trong ô",
      "<textarea class=cvdraft name=line rows=2 placeholder=" in _fm
      and "></textarea>" in _fm)
check("gợi ý chỉ nói viết VỀ CÁI GÌ, không phải một câu sẵn",
      "placeholder='viết một câu về data pipeline…'" in _fm)
# autofocus ĐÃ BỎ: nó cuộn thẳng xuống ô gõ, cuốn mất phần brief ngay trên —
# đúng thứ vừa đưa vào màn này để đọc TRƯỚC KHI viết.
check("ô trống đầu có NEO để nhảy tới", "id=viet" in _fm)
check("và KHÔNG tự cướp con trỏ, kẻo cuộn mất brief", "autofocus" not in _fm)
check("câu viết ra ghi thẳng vào CV gốc, không bảng riêng",
      "action='/cv/block'" in _fm)
check("và mang theo kỹ năng đang nhắm, để nhật ký ghi đúng việc",
      "name=ky value='data pipeline'" in _fm)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
