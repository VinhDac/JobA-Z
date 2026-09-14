"""Test bước 1 — lọc theo hồ sơ và gộp trùng.  python3 tests/test_ingest.py"""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db, postings
from jobbot.dedup import group
from jobbot.ingest import filter as jf
from jobbot.ingest.base import Posting, norm_company, norm_title, strip_html

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

def P(title, company="Acme", location="London", remote=False):
    return Posting(source_id="x", title=title, company=company,
                   location=location, remote=remote)

PROFILE = {"job_titles": "Quantitative Analyst\nData Scientist\nGraduate Analyst",
           "seniority": ["grad", "junior"], "markets": ["uk_onsite", "uk_remote"]}

print("\n[chuẩn hoá]")
check("bỏ đuôi công ty", norm_company("Monzo Bank Ltd") == norm_company("Monzo Bank"))
check("bỏ ngoặc trong chức danh", norm_title("Analyst (London)") == "analyst")
check("bỏ mã tin", norm_title("Analyst - REQ1042") == "analyst")
check("bỏ thẻ HTML", strip_html("<p>a<br>b</p>").replace("\n", " ").strip() == "a b")

print("\n[lọc]")
keep, why = jf.judge(P("Quantitative Analyst"), PROFILE)
check("khớp chức danh -> giữ", keep)
check("giải thích được vì sao giữ", "matched target title" in why)

keep, why = jf.judge(P("Product Manager"), PROFILE)
check("không khớp -> bỏ", not keep and "does not match" in why)

# LỖI ĐÃ TỪNG CÓ: 'analyst' nằm trong JUNIOR_WORDS làm mọi tin Senior lọt qua
for t in ["Senior Data Scientist", "Senior Quantitative Analyst", "Head of Data Scientist"]:
    keep, why = jf.judge(P(t), PROFILE)
    check(f"bỏ cấp cao: {t}", not keep and "senior level" in why)

keep, _ = jf.judge(P("Graduate Analyst to Senior Analyst"), PROFILE)
check("tin ghi cả grad lẫn senior -> vẫn giữ", keep)

keep, why = jf.judge(P("Data Scientist", location="New York"), PROFILE)
check("ngoài khu vực -> bỏ", not keep and "outside your area" in why)
# Lý do phải NÓI RÕ khu vực nào, vì khu vực đó nay suy từ ô "Where you're
# based" chứ không còn đóng cứng UK. Không ghi ra thì đọc nhật ký không biết
# máy đang lấy đâu làm nhà.
check("và nói rõ lấy đâu làm nhà", "(UK)" in why, )

# Ô "Where you're based" GIỜ CÓ TÁC DỤNG THẬT. Trước đây không một dòng nào
# trong tìm/lọc đọc nó — trong khi chính câu `why` của nó hứa
# "Used to filter on-site and hybrid roles by commute".
# Ở Mỹ, và KHÔNG chọn thị trường UK -> việc London là ngoài khu vực.
o_my = dict(PROFILE, location="New York, NY", markets=["us_remote"])
keep, _ = jf.judge(P("Data Scientist", location="New York"), o_my)
check("ở Mỹ thì việc New York được giữ", keep)
keep, why = jf.judge(P("Data Scientist", location="London"), o_my)
check("và việc London thành ngoài khu vực", not keep and "(US)" in why)

# Ô "thị trường" LÀ MỘT LỜI KHAI, không phải trang trí. Ở Mỹ mà tick
# "UK — onsite" nghĩa là sẵn sàng nhận việc ở UK, nên London phải được GIỮ.
#
# Bản trước location_ok nhận `markets` rồi không đọc một lần nào: hồ sơ chọn
# "US — remote" mà tin New York vẫn bị vứt vì "outside your area (UK)". Tệ
# hơn, LinkedIn dịch đúng mấy khoá đó thành nơi ĐI TÌM — app đi tìm ở Mỹ rồi
# tự ném sạch kết quả về.
o_my_uk = dict(PROFILE, location="New York, NY",
               markets=["uk_onsite", "uk_remote"])
keep, _ = jf.judge(P("Data Scientist", location="London"), o_my_uk)
check("ở Mỹ nhưng chọn thị trường UK -> việc London được giữ", keep)
o_uk_us = dict(PROFILE, location="London, UK", markets=["us_remote"])
keep, _ = jf.judge(P("Data Scientist", location="New York, NY"), o_uk_us)
check("ở UK nhưng chọn US remote -> việc New York được giữ", keep)
keep, _ = jf.judge(P("Data Scientist", location="Berlin, Germany"), o_uk_us)
check("nhưng Berlin thì không — không chọn EU", not keep)
o_all = dict(PROFILE, location="London, UK", markets=["global_remote"])
keep, _ = jf.judge(P("Data Scientist", location="Berlin, Germany"), o_all)
check("chọn global remote -> bỏ hẳn chốt địa điểm", keep)
# Ô để trống thì giữ NẾP CŨ, không tự ý đổi thứ đang giữ.
keep, _ = jf.judge(P("Data Scientist", location="London"),
                   dict(PROFILE, location=""))
check("hồ sơ chưa khai nơi ở -> vẫn xử như UK", keep)

# CHỐT CHẶN tên thành phố đụng nhau. "Birmingham, AL" là Alabama — mà nó
# đang nằm trong danh sách việc UK của Vin (đo 12/09, Mission Pet Health).
keep, _ = jf.judge(P("Data Scientist", location="Birmingham, AL"), PROFILE)
check("Birmingham, AL (Alabama) KHÔNG phải việc UK", not keep)
keep, _ = jf.judge(P("Data Scientist", location="Birmingham, England"), PROFILE)
check("nhưng Birmingham, England thì vẫn là UK", keep)
# Dấu hiệu MẠNH thắng chốt chặn: có "United Kingdom" thì mã bang không cứu
# nổi — tin đăng nhiều nơi là chuyện thường.
keep, _ = jf.judge(P("Data Scientist",
                     location="New York, NY; London, United Kingdom"), PROFILE)
check("tin đăng cả hai nơi, có UK rõ ràng -> vẫn giữ", keep)

keep, _ = jf.judge(P("Data Scientist", location="London, United Kingdom"), PROFILE)
check("nhiều địa điểm có London -> giữ", keep)

keep, _ = jf.judge(P("Data Scientist", location="Remote - Europe", remote=True), PROFILE)
check("remote châu Âu -> giữ", keep)

keep, why = jf.judge(P("Anything At All"), {})
check("chưa có job_titles -> giữ hết", keep and "no job_titles" in why)

print("\n[cache + gộp trùng]")
with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "t.db")
    batch = [P("Quantitative Analyst", "Monzo Bank Ltd"),
             P("Quantitative Analyst", "Monzo Bank"),      # cùng việc, tên khác
             P("Data Scientist", "Wise")]
    for i, item in enumerate(batch):
        item.source_id = f"s{i}"
    seen, new = postings.save_batch(conn, "test", batch)
    check("ghi lần đầu", (seen, new) == (3, 3))

    seen, new = postings.save_batch(conn, "test", batch)
    check("chạy lại KHÔNG ghi trùng (đây là cache)", (seen, new) == (3, 0))
    check("số tin không đổi", postings.count(conn) == 3)

    # LỖI ĐÃ SỬA: cache chặn cả việc bổ sung. Vòng quét nhanh ghi tin không mô tả,
    # vòng đọc kỹ lấy được mô tả nhưng không ghi vào đâu được.
    deep = P("Quantitative Analyst", "Monzo Bank Ltd")
    deep.source_id, deep.description = "s0", "x" * 900
    seen, new = postings.save_batch(conn, "test", [deep])
    check("bổ sung KHÔNG tạo dòng mới", (seen, new) == (1, 0))
    got = conn.execute("SELECT p.description FROM posting p"
                       " JOIN raw_posting r ON p.raw_id = r.id"
                       " WHERE r.source_id = 's0'").fetchone()[0]
    check("mô tả được ghi vào tin đã có", len(got) == 900)

    deep2 = P("Quantitative Analyst", "Monzo Bank Ltd")
    deep2.source_id, deep2.description = "s0", "ngắn hơn nhiều"
    postings.save_batch(conn, "test", [deep2])
    kept_long = conn.execute("SELECT p.description FROM posting p"
                             " JOIN raw_posting r ON p.raw_id = r.id"
                             " WHERE r.source_id = 's0'").fetchone()[0]
    check("KHÔNG đè mô tả dài bằng mô tả ngắn", len(kept_long) == 900)

    # kept mặc định 0 (chưa phán) — vòng lọc thật mới bật lên
    conn.execute("UPDATE posting SET kept = 1, drop_reason = ''")
    conn.commit()
    n_rows, n_groups = group.regroup(conn)
    check("gộp Monzo Bank Ltd + Monzo Bank", (n_rows, n_groups) == (3, 2))

    groups = group.groups(conn)
    merged = next(g for g in groups if g["count"] == 2)
    check("nhóm gộp giải thích được nguồn", merged["sources"] == ["test"])

    postings.log(conn, "test_event", "chi tiết")
    check("nhật ký ghi được", len(postings.recent_audit(conn)) == 1)
    conn.close()

print("\n[địa điểm khớp theo TỪ, không theo chuỗi con]")
from jobbot.ingest.filter import location_ok as _loc
_P = lambda loc, co="", rm=False: Posting(source_id="x", title="t", company=co,
                                          location=loc, remote=rm)
for _loc_text, _co in [("London", ""), ("Manchester, UK", ""),
                       ("United Kingdom", ""), ("Edinburgh", "")]:
    check(f"giữ {_loc_text!r}", _loc(_P(_loc_text, _co), []))
# 17 tin thật lọt qua vì 'uk' nằm trong 'ukraine', 'gb' nằm trong 'gbagada'
for _loc_text, _co in [("Kyiv, Ukraine", ""), ("Köln", "teamZUKUNFT gGmbH"),
                       ("Paris", "Bigblue"), ("Bremen", "GBC Group"),
                       ("Gbagada, Lagos", "")]:
    check(f"loại {_loc_text!r} {_co}", not _loc(_P(_loc_text, _co), []))
check("remote toàn cầu vẫn giữ", _loc(_P("Anywhere", "", True), []))

print("\n[danh sách board: người chọn + máy học, KHÔNG bỏ bên nào]")
# LỖI THẬT: boards.toml chỉ là DỰ PHÒNG khi bảng công ty rỗng. Bảng có 53 dòng
# nên file không bao giờ được đọc — aqr, cohere, palantir, ramp, synthesia gõ
# tay vào đó mà chưa từng được quét lần nào, và không có gì báo.
import os as _os, tempfile as _tf
from pathlib import Path as _P
with _tf.TemporaryDirectory() as _tmp:
    _os.environ["JOBBOT_DATA_DIR"] = _tmp
    from jobbot.core import db as _db
    from jobbot.scan_runner import load_boards, seed_boards

    _conn = _db.connect(_P(_tmp) / "b.db")
    seed = seed_boards()
    seed_slugs = {s for v in seed.values() for s in v}
    check("boards.toml đọc được", bool(seed_slugs))

    # bảng công ty RỖNG -> vẫn phải ra danh sách gõ tay
    got = {s for v in load_boards(_conn).values() for s in v}
    check("bảng rỗng -> dùng danh sách gõ tay", seed_slugs <= got)

    # bảng công ty CÓ dữ liệu -> danh sách gõ tay KHÔNG được biến mất
    _conn.execute(
        "INSERT INTO company (name, key, ats, ats_slug, is_agency, checked_at,"
        " roles_found, note) VALUES (?,?,?,?,0,?,?,?)",
        ("Máy Nhặt Được", "may nhat duoc", "greenhouse", "maynhat",
         "2026-01-01", 5, "seen in a posting"))
    _conn.commit()
    got = {s for v in load_boards(_conn).values() for s in v}
    check("bảng có dữ liệu -> vẫn giữ danh sách gõ tay", seed_slugs <= got)
    check("và gộp thêm cái máy học được", "maynhat" in got)

    every = [s for v in load_boards(_conn).values() for s in v]
    check("không lặp slug", len(every) == len(set(every)))
    _conn.close()
    _os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[thư báo việc — nguồn thứ ba, và là nguồn sạch nhất]")
# LinkedIn TỰ GỬI thư này vào hộp thư của Vin. Đọc hộp thư của chính mình thì
# không đụng gì tới Điều khoản của ai — khác hẳn vòng quét Chrome, vốn nằm
# ngoài mục 8.2 và app phải ghi rõ điều đó.
from jobbot.ingest import alerts as _al

_THU = """
<a href="https://www.linkedin.com/comm/jobs/view/4464889773/?trk=x"><img></a>
<a href="https://www.linkedin.com/comm/jobs/view/4464889773/?trk=y">
  <span>Data Analyst, Business Intelligence &mdash; Entry Level</span>
  <span>Jobright.ai &middot; United Kingdom (Remote)</span>
  <span>Fast growing</span>
</a>
<a href="https://www.linkedin.com/comm/jobs/view/4466042742/?trk=z">
  <span>Junior Data Analysis - 12 months FTC</span>
  <span>Slater and Gordon Lawyers (UK) &middot; London</span>
</a>
"""
_tin = _al.parse(_THU)
check("bóc được đủ số việc", len(_tin) == 2)
_m = {t.source_id: t for t in _tin}
check("tách đúng chức danh",
      _m["4464889773"].title == "Data Analyst, Business Intelligence — Entry Level")
# Chức danh và tên công ty nằm ở hai phần tử CẠNH NHAU, không có dấu gì ngăn.
# Nối bằng khoảng trắng thì ra "…Entry Level Jobright.ai" và không tách lại
# được — nên phải thay THẺ bằng XUỐNG DÒNG.
check("tách đúng công ty", _m["4464889773"].company == "Jobright.ai")
check("tách đúng địa điểm", _m["4464889773"].location == "United Kingdom (Remote)")
check("bỏ nhãn quảng cáo", "Fast growing" not in _m["4464889773"].title)
# URL trong thư là đường theo dõi dài loằng ngoằng; dựng lại URL sạch từ id.
check("dựng lại URL sạch, bỏ tham số theo dõi",
      _m["4464889773"].url == "https://www.linkedin.com/jobs/view/4464889773/")
check("cùng một việc xuất hiện 3 lần -> chỉ lấy một", len(set(_m)) == 2)
check("thư rỗng thì trả rỗng, không nổ", _al.parse("") == [])
check("thư không có việc nào cũng không nổ", _al.parse("<p>hello</p>") == [])
# Khối logo/nút không mang chữ -> phải bỏ, không được đẻ ra tin rỗng.
check("khối không có 'công ty · nơi' thì bỏ",
      not _al.parse('<a href="/jobs/view/9999999/"><img></a>'))

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
