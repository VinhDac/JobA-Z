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

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
