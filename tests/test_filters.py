"""Test bộ lọc do người dùng điều khiển.  python3 tests/test_filters.py"""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db, postings
from jobbot.dashboard import live
from jobbot.dashboard.filters import BAND, PER_PAGE, JobFilter
from jobbot.dedup import group
from jobbot.ingest.base import Posting, to_ts

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

Q = lambda **kw: JobFilter.from_query({k: [str(v)] for k, v in kw.items()})

print("\n[lọc môi giới]")
check("mặc định chỉ hiện chủ việc trực tiếp", "via_agency = 0" in Q().where()[0])
check("'all' thì không lọc", "via_agency" not in Q(via="all").where()[0])
check("'agency' thì chỉ hiện môi giới", "via_agency = 1" in Q(via="agency").where()[0])
check("giá trị lạ -> về mặc định direct", Q(via="hack").via == "direct")

print("\n[đọc URL]")
check("mặc định là 'matched'", Q().show == "matched")
check("giá trị lạ bị vứt", Q(show="'; DROP TABLE--").show == "matched")
check("loc lạ bị vứt", Q(loc="mars").loc == "")
check("sort lạ về mặc định", Q(sort="hack").sort == "score")
check("page âm -> 1", Q(page="-5").page == 1)
check("page không phải số -> 1", Q(page="abc").page == 1)
check("q bị cắt độ dài", len(Q(q="x" * 500).q) == 120)

print("\n[dựng SQL — luôn dùng tham số ràng buộc]")
where, args = Q(q="quant'; DROP TABLE posting;--").where()
check("chuỗi độc đi vào ARGS, không vào SQL", "DROP" not in where and any("drop" in str(a).lower() for a in args))
check("kept=1 khi show=matched", "kept = 1" in Q().where()[0])
check("kept=0 khi show=dropped", "kept = 0" in Q(show="dropped").where()[0])
check("show=all không lọc kept", "kept" not in Q(show="all").where()[0])
check("days sinh mốc thời gian", Q(days="7").where()[1][-1] > 0)

print("\n[dựng URL]")
f = Q(q="quant", loc="london", page="3")
check("giữ bộ lọc khi đổi trang", "q=quant" in f.url(page=4) and "page=4" in f.url(page=4))
check("đổi bộ lọc thì về trang 1", "page" not in f.url(loc="uk"))
# Danh sách việc chuyển vào tab Search — tab Jobs đã bỏ.
check("bỏ giá trị mặc định khỏi URL", f.url(q="", loc="", page=1) == "/search")
check("chip tắt được từng cái", any(u == "/search?loc=london&page=3" or "q=" not in u
                                    for _, u in f.active()))

print("\n[lọc trên dữ liệu thật]")
with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "t.db")
    # Hồ sơ phải khai NƠI Ở, vì bộ lọc nơi chốn nay tính theo nó chứ không
    # còn đóng cứng "london" trong mã nguồn.
    from jobbot.profile import store as _st
    _st.save(conn, {"job_titles": "Data Scientist", "markets": ["uk_onsite"],
                    "work_auth": "citizen", "location": "London"}, "t")
    items = []
    for i, (title, comp, loc, when) in enumerate([
        ("Quantitative Analyst", "Man Group", "London", "2026-09-01T00:00:00+00:00"),
        ("Data Scientist", "Monzo", "London", "2026-01-01T00:00:00+00:00"),
        ("Product Manager", "Acme", "New York", "2026-09-01T00:00:00+00:00"),
    ]):
        p = Posting(source_id=f"s{i}", title=title, company=comp, location=loc, posted_at=when)
        items.append(p)
    postings.save_batch(conn, "greenhouse:test", items)
    conn.execute("UPDATE posting SET kept = 1, drop_reason = ''")
    conn.execute("UPDATE posting SET kept=0, drop_reason='title does not match'"
                 " WHERE title='Product Manager'")
    conn.commit()
    group.regroup(conn)

    check("mặc định chỉ hiện tin giữ", len(live.jobs(conn, Q())) == 2)
    check("show=dropped hiện tin bị bỏ", len(live.jobs(conn, Q(show="dropped"))) == 1)
    check("show=all hiện hết", len(live.jobs(conn, Q(show="all"))) == 3)
    check("tin bị bỏ mang theo lý do",
          live.jobs(conn, Q(show="dropped"))[0]["drop_reason"] == "title does not match")
    check("tìm theo chữ", len(live.jobs(conn, Q(q="quantitative"))) == 1)
    check("tìm cả tên công ty", len(live.jobs(conn, Q(q="monzo"))) == 1)
    check("lọc theo công ty", len(live.jobs(conn, Q(company="Man Group"))) == 1)
    # NƠI CHỐN TÍNH THEO HỒ SƠ, không đóng cứng tên thành phố. Id là QUAN HỆ
    # — gần tôi / cả nước / nơi khác — còn "gần" là ở đâu thì ô "Where you're
    # based" nói. Trước đây "london" nằm thẳng trong mã nguồn, tức là bộ lọc
    # chỉ đúng với đúng một người dùng.
    check("cả nước (UK) -> 2 việc London", len(live.jobs(conn, Q(show="all", loc="home"))) == 2)
    check("nơi khác -> 1 việc New York", len(live.jobs(conn, Q(show="all", loc="other"))) == 1)
    # PROFILE khai location="London", nên "gần tôi" = London.
    check("gần tôi -> đúng việc ở London",
          len(live.jobs(conn, Q(show="all", loc="near"))) == 2)

    # "Gần tôi" mà hồ sơ chưa khai nơi ở thì KHÔNG lọc gì cả — lọc theo một
    # chỗ bịa ra còn tệ hơn không lọc.
    _w, _ = Q(loc="near").where("uk", "")
    check("chưa khai nơi ở -> 'gần tôi' không thêm điều kiện nào",
          "LOWER(location)" not in _w)
    _w2, _a2 = Q(loc="near").where("uk", "London")
    check("khai rồi thì lọc đúng chỗ đó", _a2 == ["%london%"])
    # Đổi nơi ở là đổi luôn nghĩa của "cả nước" — không còn UK đóng cứng.
    _w3, _a3 = Q(loc="home").where("us", "")
    check("ở Mỹ thì 'cả nước' nghĩa là nước Mỹ", "%united states%" in _a3)
    check("và không còn dính chữ UK nào", "%united kingdom%" not in _a3)
    check("lọc theo ngày", len(live.jobs(conn, Q(days="30"))) == 1)
    check("sắp theo công ty", live.jobs(conn, Q(sort="company"))[0]["company"] == "Man Group")
    check("mặc định sắp theo điểm", Q().sort == "score")
    check("lọc theo ngưỡng điểm sinh SQL đúng", "score >= ?" in Q(band="75").where()[0])
    # "Not scorable" ĐÃ BỎ khỏi hàng điểm. Nó và "Can't tell" bên hàng cơ hội
    # là CÙNG một chồng tin — đo trên kho thật: 185 tin thiếu cả hai, 0 tin
    # chỉ thiếu một. Hai nút ở hai hàng cho cùng một thứ là hai lần hỏi.
    check("hàng điểm không còn 'not scorable'",
          "none" not in {v for v, _ in BAND})
    check("gộp thành MỘT nút: raw=1 tìm tin máy chưa đọc được",
          "score IS NULL" in Q(raw="1").where()[0]
          and "unknown" in Q(raw="1").where()[0])

    # THANG = SÀN, không phải bằng-đúng. Chọn "Có thể" mà giấu mất "Đáng nộp"
    # là giấu đúng những tin tốt nhất — không ai muốn thế.
    _sql = Q(chance="possible").where()[0]
    check("thang cơ hội sinh SQL kiểu >= , không phải =",
          ">= ?" in _sql and "realism = ?" not in _sql)
    check("sàn 'có thể' là hạng 2", Q(chance="possible").where()[1] == [2])
    check("sàn 'đáng nộp' là hạng 3", Q(chance="likely").where()[1] == [3])
    check("Tất cả thì không thêm điều kiện cơ hội nào",
          "realism" not in Q(chance="").where()[0])

    # TAG NGUỒN — lọc theo CÁCH TÌM.
    check("linkedin = chỉ LinkedIn", "source = 'linkedin'" in Q(found="linkedin").where()[0])
    check("board = mọi thứ trừ LinkedIn", "source <> 'linkedin'" in Q(found="board").where()[0])
    check("mọi nguồn thì không lọc gì", "source" not in Q(found="").where()[0])
    check("nguồn lạ bị vứt", Q(found="bịa").found == "")

    counts = live.job_counts(conn, Q())
    check("đếm đúng cho từng tab", (counts["matched"], counts["dropped"], counts["all"]) == (2, 1, 3))
    check("facets lấy nguồn thật", live.facets(conn)["sources"] == ["greenhouse"])
    check("trang 2 rỗng khi chỉ có 2 tin", len(live.jobs(conn, Q(page="2"))) == 0)
    conn.close()


print("\n[bộ lọc chọn HIỆN TIN NÀO, không đổi TIN TRÔNG RA SAO]")
# LỖI THẬT: badge nguồn, "+N nơi" và điểm được tính trên phần ĐÃ LỌC. Nên bấm
# bấm tag nguồn LinkedIn một cái là tin Man Group rụng badge board, mất "+1 nơi", và mất
# luôn điểm 100 — vì dòng LinkedIn của nó chưa đọc kỹ nên chưa có điểm. Cùng
# một việc, hai bộ lọc, hai bộ mặt.
with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "m.db")
    JD = ("Requirements:\n· Python and pandas\n· SQL\n" + "detail " * 80)
    # Cùng MỘT việc, hai nơi đăng: board có mô tả (chấm được), LinkedIn thì
    # chưa đọc kỹ nên rỗng — đúng hình dạng trên máy thật.
    postings.save_batch(conn, "greenhouse:mangroup", [
        Posting(source_id="g1", title="Quant Researcher", company="Man Group",
                location="London", url="https://g/1", description=JD)])
    postings.save_batch(conn, "linkedin", [
        Posting(source_id="l1", title="Quant Researcher", company="Man Group",
                location="London", url="https://l/1", description="")])
    conn.execute("UPDATE posting SET kept = 1")
    conn.execute("UPDATE posting SET score = 100 WHERE source LIKE 'greenhouse%'")
    conn.commit()
    group.regroup(conn)

    het = live.jobs(conn, Q())[0]
    chr_ = live.jobs(conn, Q(found="linkedin"))[0]
    api = live.jobs(conn, Q(found="board"))[0]
    check("không lọc: thấy cả hai nguồn", het["found_by"] == ["board", "linkedin"])
    check("lọc linkedin: VẪN thấy cả hai nguồn", chr_["found_by"] == ["board", "linkedin"])
    check("lọc board: VẪN thấy cả hai nguồn", api["found_by"] == ["board", "linkedin"])
    check("số '+N nơi' không đổi theo bộ lọc",
          het["merged"] == chr_["merged"] == api["merged"] == 2)
    check("điểm không đổi theo bộ lọc",
          het["score"] == chr_["score"] == api["score"] == 100)
    check("nhưng bộ lọc VẪN chọn đúng tin",
          len(live.jobs(conn, Q(found="linkedin"))) == 1)
    conn.close()

print("\n[phân trang phải LỢP KÍN số đếm — không thiếu, không lặp]")
# LỖI THẬT: jobs() cắt trang theo DÒNG rồi mới gộp trùng bằng Python, còn
# job_counts() đếm theo NHÓM. Trên máy thật đầu trang ghi 139 việc, đi hết
# các trang đếm được 144 thẻ: 5 nhóm bị cắt đôi qua ranh giới trang.
with tempfile.TemporaryDirectory() as tmp:
    import jobbot.dashboard.filters as filters_mod
    from jobbot.core.derive import derive
    from jobbot.profile import store

    conn = db.connect(Path(tmp) / "p.db")
    store.save(conn, {"job_titles": "Data Scientist", "seniority": ["grad", "junior"],
                      "markets": ["uk_onsite"], "work_auth": "citizen"}, "t")
    JD = ("Requirements:\n· Python and pandas\n· SQL\n" + "detail " * 80)
    items = []
    for n in range(11):
        # cứ hai tin lại có một tin TRÙNG (cùng công ty + chức danh) -> một nhóm
        # hai dòng, đúng chỗ phân trang hay cắt đôi.
        items.append(Posting(source_id=f"a{n}", title="Data Scientist",
                             company=f"Co{n}", location="London",
                             url=f"https://x/a{n}", description=JD))
        if n % 2 == 0:
            items.append(Posting(source_id=f"b{n}", title="Data Scientist",
                                 company=f"Co{n}", location="London",
                                 url=f"https://y/b{n}", description=JD))
    postings.save_batch(conn, "greenhouse:t", items)
    derive(conn)

    real_per = filters_mod.PER_PAGE
    filters_mod.PER_PAGE = 3                    # trang nhỏ -> nhiều ranh giới
    try:
        total = live.job_counts(conn, Q())["matched"]
        seen, sizes = [], []
        for page in range(1, 40):
            got = live.jobs(conn, Q(page=page))
            if not got:
                break
            sizes.append(len(got))
            seen += [j["id"] for j in got]
        check("đi hết các trang ra ĐÚNG số đếm trên đầu trang", len(seen) == total)
        check("không thẻ nào hiện hai lần", len(seen) == len(set(seen)))
        check("mọi trang đều đầy, trừ trang cuối",
              all(n == 3 for n in sizes[:-1]) and 0 < sizes[-1] <= 3)
        check("tin trùng được gộp, không đếm hai lần", total < len(items))
        merged = [j for j in live.jobs(conn, Q()) if j["merged"] > 1]
        check("nhóm gộp vẫn giữ số dòng của nó", bool(merged))
    finally:
        filters_mod.PER_PAGE = real_per
    conn.close()

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
