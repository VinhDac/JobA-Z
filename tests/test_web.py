"""Smoke test tầng web — thứ đáng lẽ phải có từ đầu.

Trong một phiên làm việc, tầng web sập trắng BỐN lần:
    settings 500  cột attempted/failed thiếu trong câu GROUP BY
    jobs 500      biến `chance` dùng trước khi gán
    jobs 500      job['cv_changes'] đã bị bỏ khỏi tầng dữ liệu
    projects 500  view gọi hàm chưa tồn tại

Không lần nào bị test bắt, vì KHÔNG test nào gọi hàm render và KHÔNG test nào
bấm vào server. Cả bốn đều là lỗi một dòng, và một smoke test bắt được cả bốn.

    python3 tests/test_web.py
"""

import json, sys, tempfile, threading, urllib.error, urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db, postings
from jobbot.ingest.base import Posting
from jobbot.profile import store

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}{' — ' + extra if extra else ''}")

PROFILE = {
    "job_titles": "Quantitative Analyst\nData Scientist",
    "markets": ["uk_onsite"], "work_auth": "citizen",
    "seniority": ["grad", "junior"], "years_real": "0-1",
    "full_name": "Test User", "email": "t@example.com",
    # Nơi ở: bộ lọc nơi chốn nay tính theo ô này, nên hồ sơ thử phải có nó —
    # hồ sơ thật của ai cũng có.
    "location": "London, UK",
    "education": "MSc Computational Finance — Somewhere, 2026",
    "certifications": "CFA Level I",
    "skills_strong": "Python, pandas, SQL",
    "cv_text": ("TEST USER\nLondon, UK · t@example.com\n"
                "EXPERIENCE\nAnalyst — Acme Jan 2025 – Present\n"
                "I built pipelines in Python and SQL across 17 datasets.\n"
                "SELECTED PROJECTS\nThing — a small study of validation.\n"
                "EDUCATION\nMSc Computational Finance — Somewhere 2025 – 2026\n"
                "TECHNICAL SKILLS\nProgramming — Python, SQL.\n"),
}

def seeded(path: Path):
    conn = db.connect(path)
    store.save(conn, PROFILE, "test")
    items = [
        Posting(source_id="a", title="Quantitative Analyst", company="Man Group",
                location="London", url="https://x/a",
                description="Requirements:\n· Strong Python and pandas\n"
                            "· A degree in a quantitative discipline\n"
                            "· Comfortable with SQL\n" + "detail " * 80,
                raw_body="<p>Requirements</p>"),
        Posting(source_id="b", title="Data Scientist", company="Monzo",
                location="London", url="https://x/b",
                description="What we're looking for:\n· Python and machine learning\n"
                            "· Time series analysis\n· SQL\n" + "detail " * 80),
        Posting(source_id="c", title="Product Manager", company="Acme",
                location="Berlin", url="https://x/c", description="unrelated " * 60),
        # Ba tin dưới đây có mặt để tầng project ĐẺ RA nhóm: dưới MIN_JOBS thì
        # cluster.build trả về rỗng, trang /projects không in liên kết nào, và
        # bài test đi-theo-liên-kết ở dưới sẽ không kiểm được gì cả.
        Posting(source_id="d", title="Data Scientist", company="Wintermute",
                location="London", url="https://x/d",
                description="Requirements:\n· Machine learning in production\n"
                            "· Python and PyTorch\n· Time series forecasting\n"
                            + "detail " * 80),
        Posting(source_id="e", title="Quantitative Analyst", company="Cubist Systematic",
                location="London", url="https://x/e",
                description="Requirements:\n· Machine learning research\n"
                            "· Alpha research and backtesting\n· Python\n"
                            + "detail " * 80),
        Posting(source_id="f", title="Data Scientist", company="Ebury",
                location="London", url="https://x/f",
                description="Requirements:\n· Alpha research exposure\n"
                            "· Time series analysis\n· SQL and Excel\n"
                            + "detail " * 80),
    ]
    postings.save_batch(conn, "greenhouse:test", items)
    from jobbot.core.derive import derive
    derive(conn)
    return conn


ROUTES = ["/", "/search", "/cv", "/cv/soan", "/profile",
          "/profile/muc_tieu", "/profile/import", "/profile/health",
          "/settings", "/api/profile", "/api/state"]

print("\n[mọi route phải trả 200 và KHÔNG có traceback]")
with tempfile.TemporaryDirectory() as tmp:
    import os
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = seeded(Path(tmp) / "jobbot.db")
    job_id = conn.execute("SELECT id FROM posting WHERE kept=1 LIMIT 1").fetchone()[0]
    conn.close()

    from jobbot.dashboard.server import serve
    httpd, base = serve(port=8791)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def get(path):
        try:
            with urllib.request.urlopen(base.rstrip("/") + path, timeout=25) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:                       # noqa: BLE001
            return 0, f"{type(e).__name__}: {e}"

    for path in ROUTES + [f"/jobs/{job_id}", f"/jobs/{job_id}/cv",
                          f"/jobs/{job_id}/project"]:
        status, body = get(path)
        check(f"{path:24} {status}", status == 200, body[:90])
        if status == 200 and path != "/api/profile":
            check(f"{path:24} không lộ traceback",
                  "Traceback" not in body and "<class '" not in body)

    print("\n[404 đúng cách, không sập]")
    for path in ["/nope", "/jobs/999999", "/profile/khong-co", "/projects/khong-co",
                 "/queue", "/pipeline", "/stats",      # trang giả đã xoá hẳn
                 "/jobs", "/score"]:                   # tab đã bỏ, đang dựng lại
        status, _ = get(path)
        check(f"{path:24} -> 404", status == 404)

    # Khối "mọi tổ hợp lọc đều phải sống" đã bỏ cùng trang /jobs. Logic lọc
    # KHÔNG mất kiểm: tests/test_filters.py gọi thẳng live.jobs() với đủ tổ
    # hợp, kể cả chuỗi độc và phân trang. Khi danh sách quay lại trong Search,
    # dựng lại khối này để kiểm qua HTTP.

    print("\n[POST không được sập]")
    def _post_raw(path, data=b""):
        """POST và trả về THÂN phản hồi — post() chỉ trả mã."""
        req = urllib.request.Request(base.rstrip("/") + path, data=data)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            return e.read().decode()

    def post(path, data=b""):
        try:
            req = urllib.request.Request(base.rstrip("/") + path, data=data)
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:                            # noqa: BLE001
            return 0

    def post_form(path, body):
        return post(path, body.encode())
    check("POST /profile/muc_tieu",
          post("/profile/muc_tieu", b"job_titles=Analyst&markets=uk_onsite") == 200)

    print("\n[CHU TRÌNH dựng hồ sơ — Home phải dẫn đường, không chỉ báo cáo]")
    # Đây là cửa vào app. Người dùng mới đáp xuống đây trước tiên; trước đây
    # nó chỉ nói "Trang này đang trống".
    # Chu trình dựng hồ sơ là TẤM PHỦ, không phải tab Home: việc của nó chỉ có
    # lúc đầu, còn tab Home là chỗ của bảng điều khiển pipeline.
    _, _hm = get("/onboarding")
    _, _trang = get("/")
    check("chu trình là mảnh HTML cho tấm phủ, không phải cả trang",
          "<!doctype" not in _trang.lower() or "<!doctype" not in _hm.lower())
    check("chưa đủ thì Home bật tấm phủ ngay khi vào",
          "data-setup='/onboarding'" in _trang)
    check("nói hồ sơ đang thiếu gì", "Chưa chạy được gì" in _hm)
    check("và có nút đi thẳng tới chỗ điền", "href='/profile/muc_tieu'" in _hm)
    check("có thanh tiến độ", "class=obar" in _hm)
    check("liệt kê đủ 6 phần", _hm.count("class='blk ostep") == 6)
    check("phần bắt buộc được đánh dấu", "BẮT BUỘC" in _hm)
    # Home KHÔNG được tự nghĩ luật: nó phải đọc đúng cổng mà Search đang đọc.
    from jobbot.dashboard import live as _live
    from jobbot.core import db as _db
    _c = _db.connect()
    _ob = _live.onboarding(_c)
    from jobbot.profile import store as _st
    check("Home đọc CÙNG cổng với Search",
          [q["id"] for q in _ob["gate_missing"]]
          == _st.missing_for_ingest(_st.load(_c)))
    print("\n[ô thẻ + gõ-để-tìm — MỘT ô nhập, không phải hai]")
    _, _mt = get("/profile/muc_tieu")
    check("câu chức danh là ô THẺ, không phải ô gõ chay",
          "data-tags='job_titles'" in _mt and "<textarea" not in _mt.split(
              "job_titles")[1][:400])
    check("không còn ô lọc riêng thứ hai", "sugfind" not in _mt)
    check("có danh sách gợi ý rơi xuống", "data-sugdrop" in _mt)
    # ĐỌC RỘNG, GHI CHẶT. Dữ liệu cũ lưu "A · B · C" trên một dòng; chỉ cắt
    # theo dấu nối mới thì cả cụm thành MỘT thẻ khổng lồ, mà cv/build.py đọc
    # theo dòng nên vẫn tưởng chỉ có một chứng chỉ.
    from jobbot.dashboard.views.profile import _tach as _tach2
    check("ô thẻ đọc được hình dạng CŨ (một dòng, ngăn bằng ·)",
          _tach2("CFA Level I · IBM Data Science · IBM ML", "\n")
          == ["CFA Level I", "IBM Data Science", "IBM ML"])
    check("và hình dạng mới", _tach2("A\nB", "\n") == ["A", "B"])
    check("dấu phẩy vẫn đúng", _tach2("python, sql", ", ") == ["python", "sql"])
    check("lúc nghỉ chỉ mời gõ, không bày cả kho", "gõ để tìm trong" in _mt)
    print("\n[RESET = về trạng thái ban đầu, KHÔNG sót chỗ nào]")
    # Chạy trên thư mục RIÊNG, kể cả HOME — reset.backup() ghi ra ~/Desktop,
    # để nguyên thì mỗi lần chạy test là rơi một tệp lên Desktop thật.
    import os as _osr, shutil as _shr, tempfile as _tfr
    _rtmp = _tfr.mkdtemp()
    _cu_home, _cu_data = _osr.environ.get("HOME"), _osr.environ.get("JOBBOT_DATA_DIR")
    _cu_root = _osr.environ.get("JOBBOT_ROOT")
    _osr.environ["HOME"] = _rtmp
    _osr.environ["JOBBOT_DATA_DIR"] = _rtmp
    # JOBBOT_ROOT — thiếu dòng này, bài test đã XOÁ config/config.toml THẬT
    # của Vin ở MỌI lần chạy suốt ngày 12/09, và nuốt mất app password Gmail
    # anh vừa dán vào. `reset.USER_FILES` là đường dẫn tương đối so với GỐC
    # REPO, mà gốc repo hồi đó là hằng số tính từ vị trí tệp nguồn: đổi HOME
    # và JOBBOT_DATA_DIR chỉ dời được data/, không dời nổi config/.
    (Path(_rtmp) / "config").mkdir(exist_ok=True)
    _osr.environ["JOBBOT_ROOT"] = _rtmp
    try:
        import importlib
        from jobbot.core import db as _dbr, paths as _pr
        importlib.reload(_pr)
        from jobbot.core import reset as _rs
        importlib.reload(_rs)
        # CHỐT: không bao giờ chạy đường phá hoại trỏ vào repo thật. Cùng một
        # luật với chốt "test đang trỏ vào DB THẬT" — và chốt này có vì đã
        # mất một app password thật.
        assert str(_pr.project_root()).startswith(_rtmp), \
            f"test reset đang trỏ vào REPO THẬT: {_pr.project_root()}"
        assert str(_rs.backup_dir()).startswith(_rtmp), \
            f"sao lưu test đang ghi ra chỗ THẬT: {_rs.backup_dir()}"
        _cr = _dbr.connect(Path(_rtmp) / "jobbot.db")
        _dbr.migrate(_cr)
        _cr.execute("INSERT INTO pref(key,value) VALUES('x','1')")
        _cr.execute("INSERT INTO audit(at,kind,detail) VALUES('t','k','d')")
        _cr.commit()
        (Path(_rtmp) / "app.log").write_text("rác")
        (Path(_rtmp) / "cv").mkdir(exist_ok=True)
        (Path(_rtmp) / "cv" / "a.pdf").write_text("x")
        _truoc = _rs.inventory(_cr)["total_rows"]
        _kq = _rs.run(_cr)
        _dbr.migrate(_cr)
        _sau = _rs.inventory(_cr)
        check("trước reset có dữ liệu", _truoc >= 2)
        check("sau reset KHÔNG bảng nào còn dòng", _sau["total_rows"] == 0)
        check("và không tệp người dùng nào còn lại", _sau["files"] == 0)
        check("nhật ký app cũng bị dọn", not (Path(_rtmp) / "app.log").exists())
        check("sao lưu có thật và đọc được",
              Path(_kq["backup"]).exists() and Path(_kq["backup"]).stat().st_size > 0)
        check("sao lưu chỉ chủ máy đọc được",
              oct(Path(_kq["backup"]).stat().st_mode)[-3:] == "600")
        check("schema giữ nguyên, không phải dựng lại",
              _cr.execute("PRAGMA user_version").fetchone()[0] > 0)
        # CV của người dùng cũng phải đi hết. "Làm lại từ đầu" mà chừa lại
        # hồ sơ thì lần chạy sau vẫn đứng trên dữ liệu cũ.
        from jobbot.profile import store as _st2
        _st2.save(_cr, {"cv_text": "SELECTED PROJECTS\nTự Viết — y\n"}, "t")
        _cr.commit()
        _rs.run(_cr)
        _dbr.migrate(_cr)
        check("reset xoá cả CV trong hồ sơ",
              not str(_st2.load(_cr).get("cv_text") or "").strip())
        # PERSONAL PROJECT ĐÃ BỎ HẲN. Máy không nghĩ đề bài nữa, nên không còn
        # "khối máy đẻ" để mà đánh dấu — và bảng chứa chúng phải biến mất chứ
        # không nằm lại rỗng. Một bảng chết còn sống trong lược đồ là thứ
        # người sau sẽ tưởng còn dùng.
        check("bảng project đã bị bỏ khỏi lược đồ",
              not [r for r in _cr.execute(
                  "SELECT name FROM sqlite_master WHERE type='table'"
                  " AND name='project'")])
        from jobbot.dashboard.views.profile import _o_khoi as _ok2
        from jobbot.profile.schema import all_questions as _aq2
        _h2 = _ok2(_aq2()["project_blocks"],
                   {"cv_text": "SELECTED PROJECTS\nTự Viết — y\n"}, {})
        check("mọi khối project giờ là của người dùng — không dấu máy đẻ",
              "maybadge" not in _h2 and "blockrow machine" not in _h2)
        _cr.close()
    finally:
        for _k, _v in (("HOME", _cu_home), ("JOBBOT_DATA_DIR", _cu_data),
                       ("JOBBOT_ROOT", _cu_root)):
            if _v is None:
                _osr.environ.pop(_k, None)
            else:
                _osr.environ[_k] = _v
        _shr.rmtree(_rtmp, ignore_errors=True)
        import importlib as _il
        from jobbot.core import paths as _pr2, reset as _rs2
        _il.reload(_pr2); _il.reload(_rs2)
    _jsr = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    check("và quên cả thứ trình duyệt đang nhớ", "wipe_local" in _jsr)

    _js2 = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    check("Enter lấy gợi ý khớp, không lấy chữ gõ dở",
          "data-sugdrop] [data-addtag]:not([hidden])" in _js2)
    _css3 = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    # BẪY ĐÃ DÍNH HAI LẦN: đặt display cho một phần tử là CSS của mình thắng
    # luật [hidden]{display:none} của trình duyệt — chip bị JS ẩn vẫn hiện,
    # flex bóp mỗi dòng còn 14px và cắt cụt chữ, nhìn như lỗi phông.
    check("chip bị ẩn PHẢI thật sự biến mất",
          ".sugdrop > .addtag[hidden]{display:none}" in _css3)
    check("và chip không bị flex bóp", ".sugdrop > .addtag{flex:none" in _css3)
    # Cùng cái bẫy, ở cấp CHA. Chọn hết gợi ý xong JS ẩn cả vùng, mà .sugdrop
    # khai display:flex nên nó vẫn chiếm 96px khoảng trống.
    check("vùng gợi ý ẩn đi PHẢI biến mất hẳn",
          ".sugdrop[hidden]{display:none}" in _css3)
    check("hàng tìm cũng vậy", ".findrow[hidden]{display:none}" in _css3)
    # "Chọn tất cả" CHỈ cho kho nhỏ. Chọn cả 60 chức danh là tự tay vô hiệu
    # hoá bộ lọc — giữ lại mọi tin thì lọc để làm gì.
    check("kho ngành (7) có nút chọn tất cả", "data-addall" in _mt)
    # Luật là NGƯỠNG, nên kiểm thẳng vào luật chứ không đếm nút trên một trang
    # mà kho to nhỏ tuỳ dữ liệu. Chọn cả 60 chức danh là tự tay vô hiệu hoá bộ
    # lọc — giữ lại mọi tin thì lọc để làm gì.
    from jobbot.dashboard.views.profile import _o_the as _othe, _CHON_HET
    from jobbot.profile.schema import all_questions
    _q_ind = all_questions()["industries"]
    _nho = _othe(_q_ind, {}, {"industries": [f"n{i}" for i in range(_CHON_HET)]})
    _to = _othe(_q_ind, {}, {"industries": [f"n{i}" for i in range(_CHON_HET + 1)]})
    check(f"kho <= {_CHON_HET} mục thì có nút chọn tất cả", "data-addall" in _nho)
    check("kho lớn hơn thì KHÔNG", "data-addall" not in _to)

    print("\n[LÀM LẠI TỪ ĐẦU — đường phá hoại phải có chốt]")
    # Bài thử ném rác vào mọi route từng xoá mất app password thật 12 lần liền.
    # Route xoá sạch còn nguy hơn, nên nó phải TỪ CHỐI khi không có xác nhận.
    check("POST rỗng KHÔNG xoá được gì", post("/api/reset", b"") == 400)
    check("sai chữ xác nhận cũng không", post("/api/reset", b"arg=x") == 400)
    # Và chốt đó phải thật sự chặn — DB còn nguyên bảng sau hai cú trên.
    from jobbot.core import db as _dbm
    _cc = _dbm.connect()
    check("DB vẫn còn nguyên schema sau hai cú POST đó",
          _cc.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                      ).fetchone()[0] > 5)
    _cc.close()
    _, _set = get("/settings")
    check("Cài đặt có tab Làm lại", "data-pane='lam-lai'" in _set)
    check("nói trước sẽ mất gì", "Sẽ mất:" in _set)
    check("nói trước sao lưu nằm ở đâu", "tar.gz" in _set)
    # NÚM NHỊP phải nói ra cái ĐÁNH ĐỔI ngay trên màn hình. Một núm ghi
    # "Nhanh" mà không nói nhanh bằng giá gì là núm mời người ta bấm rồi lãnh
    # hậu quả.
    _, _st = get("/settings")
    check("cài đặt có núm nhịp gọi", "name=pace" in _st and "Nhịp gọi" in _st)
    check("ba mức, không hơn", _st.count("type=radio name=pace") == 3)
    check("và nói thẳng cái đánh đổi", "dễ bị bóp hơn" in _st)
    check("mặc định đang chọn 'thường'", "value='thuong' checked" in _st)
    # Gõ bừa vào form thì rơi về mặc định — không để chuỗi lạ thành nhịp gọi.
    post("/settings", b"every=60&from=8&to=22&pace=bi%E1%BB%8Fa")
    from jobbot.core import prefs as _pf
    _cc = db.connect()
    check("nhịp lạ bị vứt, về mặc định",
          _pf.get(_cc, _pf.PACE) == "thuong", _pf.get(_cc, _pf.PACE))
    post("/settings", b"every=60&from=8&to=22&pace=nhanh")
    check("nhịp hợp lệ thì lưu được", _pf.get(_cc, _pf.PACE) == "nhanh")
    post("/settings", b"every=60&from=8&to=22&pace=thuong")
    _cc.close()

    check("nút khoá sẵn, phải gõ chữ mới mở",
          "disabled>Xoá hết" in _set and "data-needword" in _set)
    _js = (Path(__file__).resolve().parent.parent
           / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    check("và trình duyệt có trình nghe mở khoá", "wireDangerWord" in _js)

    print("\n[VÒNG GIỮ — chưa đủ thì không cho đi tiếp]")
    # Lưu một phần mà cổng vẫn đóng -> phải quay LẠI đúng chỗ còn thiếu, không
    # được đi tiếp sang phần sau. Bỏ luật này thì người dùng lướt hết 5 phần,
    # bỏ trống ba câu quan trọng nhất, rồi thắc mắc vì sao bấm Chạy không ra gì.
    def _post_lay_dich(path, body):
        import urllib.request as _u
        class _NoRedirect(_u.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = _u.build_opener(_NoRedirect)
        try:
            r = op.open(_u.Request(base.rstrip("/") + path, data=body), timeout=25)
            return r.status, r.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Location", "")

    # Lưu phần "What you won't take" trong khi cổng còn đóng -> bị kéo ngược.
    _ma, _di = _post_lay_dich("/profile/rang_buoc", b"deal_breakers=none")
    check("lưu phần phụ khi chưa đủ -> bị đưa về chỗ còn thiếu",
          _di.endswith("/profile/muc_tieu"), f"{_ma} -> {_di}")
    # Trang đó phải NÓI vì sao giữ lại.
    _, _sec = get("/profile/muc_tieu")
    check("và nói rõ còn mấy câu", "câu nữa là app chạy được" in _sec)
    check("nhãn nút không hứa đi tiếp", "còn" in _sec and "câu nữa</button>" in _sec)
    # Điền đủ -> thả ra, đi tiếp bình thường.
    _ma2, _di2 = _post_lay_dich(
        "/profile/muc_tieu",
        b"job_titles=Quant&markets=uk_onsite&work_auth=visa_no_sponsor")
    check("đủ rồi thì được đi tiếp", _di2.endswith("/profile/rang_buoc"),
          f"{_ma2} -> {_di2}")

    # Điền đủ cổng -> Home phải ĐỔI GIỌNG, không còn chặn.
    post("/profile/muc_tieu",
         b"job_titles=Quantitative+Analyst&markets=uk_onsite&work_auth=visa_no_sponsor")
    _, _hm2 = get("/onboarding")
    _ob2 = _live.onboarding(_db.connect())
    check("điền đủ 3 câu thì cổng mở", _ob2["gate_open"])
    check("và đổi sang mời chạy", "Hồ sơ đủ để chạy" in _hm2)
    check("phần vừa xong được đánh dấu", "ostep done" in _hm2)
    # ĐỦ CÂU BẮT BUỘC THÌ THÔI BẮT. Tấm phủ không tự bật nữa, tab Home trống
    # trơn để dành cho bảng điều khiển pipeline.
    _, _trang2 = get("/")
    check("đủ rồi thì Home KHÔNG bật tấm phủ nữa", "data-setup=" not in _trang2)
    check("và tab Home trả lại chỗ cho việc của nó",
          "blk ostep" not in _trang2)
    _c.close()
    check("POST /profile/import rỗng -> không sập",
          post("/profile/import", b"") in (200, 303))

    print("\n[nút gọi việc nền phải THẬT SỰ tới được trình nghe]")
    # Trình nghe [data-post] nằm ở `document`. Một nút gắn stopPropagation là
    # nút chết: bấm không làm gì, không báo lỗi, không có dấu vết. Đã xảy ra
    # với nút Nộp ở tab Search.
    for page in ("/search", "/cv", "/track"):
        _s, body = get(page)
        if _s != 200:
            continue
        for chunk in body.split("data-post=")[1:]:
            head = chunk[:220]
            check(f"{page:<10} nút data-post không chặn lan truyền",
                  "stopPropagation" not in head)

    # Nút trỏ vào route KHÔNG TỒN TẠI cũng là nút chết, và im lặng y hệt:
    # fetch trả 404, .json() nổ, .catch() nuốt. Đối chiếu mọi đích data-post
    # trên trang với danh sách route máy chủ thật sự xử lý.
    import re as _re
    _server = (Path(__file__).resolve().parent.parent
               / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
    # Route có thể khai bằng `path == "x"` HOẶC `path in ("x", "y")` —
    # bộ dò chỉ nhận dạng thứ nhất thì báo nhầm route thật là không tồn tại.
    _known = set(_re.findall(r'path == "([^"]+)"', _server))
    for _grp in _re.findall(r'path in \(([^)]*)\)', _server):
        _known |= set(_re.findall(r'"([^"]+)"', _grp))
    _known |= set(_re.findall(r'path\.startswith\("([^"]+)"\)', _server))
    _wired = set()
    for page in ("/search", "/cv", "/track", "/"):
        _s, body = get(page)
        if _s != 200:
            continue
        _wired |= set(_re.findall(r"data-post='([^']+)'", body))
        _wired |= set(_re.findall(r'data-post="([^"]+)"', body))
    # Vẽ thẳng tab Quản lí với ĐỦ MỌI loại dòng: DB thử không có dòng nộp nào
    # nên nút "Gửi đơn", "bỏ", "đổi chặng", "quét thư" không hiện, và những nút
    # đó chính là những nút mới nhất — tức là những nút dễ sai đích nhất.
    from jobbot.dashboard.views import track as _track
    from jobbot.track import board as _board
    _row = dict(id=1, stage=_board.DRAFT, company="X", role="R", days=1,
                event_days=None, last_event="", silent=False, cv_file="c.pdf",
                posting_id=9, url="u", score=90)
    for _ready in (False, True):
        for _stage in _board.STAGES:
            _html = _track.render(rows=[{**_row, "stage": _stage}],
                                  asks=[dict(id=2, company="X", company_guess="X",
                                             stage=_stage, kind="rejected",
                                             subject="s", snippet="n", app_id=1)],
                                  counts={"total": 1}, mail_ready=_ready,
                                  mail_address="a@b.c")
            _wired |= set(_re.findall(r"data-post='([^']+)'", _html))
            _wired |= set(_re.findall(r'data-post="([^"]+)"', _html))

    check("có nút data-post để mà kiểm", len(_wired) >= 7, str(sorted(_wired)))
    for _target in sorted(_wired):
        check(f"route {_target} có thật", _target in _known)

    print("\n[PDF: bản in KHÔNG phải bản màn hình thu nhỏ]")
    css = (Path("src/jobbot/dashboard/web/app.css")).read_text()
    rule = css[css.index("@media print"):] if "@media print" in css else ""
    check("có khối @media print", bool(rule))
    # Ẩn `nav` thôi thì chưa đủ: thanh bên là <aside class=side>, nên dấu ◆ và
    # chữ "jobbot" vẫn in ra. Và `.lead` là ghi chú CHO VIN ("Built for … the
    # system selects and orders"), không phải cho nhà tuyển dụng.
    for gone in (".side", ".lead", ".topbar", "button"):
        check(f"bản in giấu {gone}", gone in rule.split("}")[1] or gone in rule)
    check("nền giấy trắng, không nền tối của app", "#fff !important" in rule)
    check("khổ A4", "size: A4" in rule)
    check("không cắt đôi một mục qua hai trang", "break-inside:avoid" in rule)

    check("POST /cv/pdf thiếu id -> 400", post_form("/cv/pdf", "arg=") == 400)

    # BẤM THÌ MỚI CHẠY. Tab CV không còn dựng lúc vẽ trang, nên muốn kiểm ô
    # "Bản sẽ gửi" thì phải dựng trước — y như người dùng bấm Chạy.
    check("chưa bấm Chạy -> tab CV nói rõ là chưa dựng, không vẽ ô rỗng",
          "Chưa dựng bản CV nào" in get("/cv")[1])
    from jobbot.cv import batch as _bt
    _cvc = db.connect(Path(tmp) / "jobbot.db")
    _bt.run(_cvc)
    _cvc.close()
    _s, body = get("/cv")
    check("dựng xong thì ô hiện bản", "class=cvrow" in body)
    # KHỐI HỤT — khối trả lời câu hỏi duy nhất của tab: tối nay viết gì.
    check("tab CV có khối HỤT", "VIẾT GÌ ĐỂ HẾT HỤT" in body.upper()
          or "hết hụt" in body)
    # HAI ĐÍCH, không một: "làm hết bảng" gộp cả mấy dòng phải đi HỌC, mà học
    # tính bằng tháng còn viết tính bằng buổi tối.
    check("nói rõ đích VIẾT ĐƯỢC TỐI NAY tách khỏi đích phải đi học",
          "làm được tối nay" in body and "đi học" in body)
    check("và bỏ hàng chip 'nhắm vào chỗ hồ sơ đang câm' cũ",
          "nhắm vào chỗ hồ sơ đang câm" not in body)
    # IN HÀNG LOẠT ĐÃ BỎ. Câu hỏi thật ở ô này không phải "in cho tôi 28 tệp",
    # mà là "gửi cho công ty này thì dùng bản nào" — nên chỗ đó là ô TÌM.
    # Mỗi bản vẫn in riêng được bằng nút PDF trên từng dòng.
    check("không còn nút in hàng loạt", "/cv/pdf/all" not in body)
    check("POST /cv/pdf/all đã bỏ hẳn, không để lại đường cụt",
          post_form("/cv/pdf/all", "") == 404)
    check("có ô tìm trong bản đã dựng", "name=q" in body and "class=jfind" in body)
    check("in từng bản vẫn còn", "data-post='/cv/pdf'" in body)

    # TỜ GIẤY GỬI ĐI CHỈ ĐƯỢC CÓ TỜ CV. Kiểm bằng cách in thật rồi mở ảnh ra
    # nhìn: thanh trạng thái in ĐÈ lên dòng cuối mục Technical Skills, và nó
    # mang đường dẫn tệp trên máy ("PDF: /Users/davi/…") ra một tài liệu gửi
    # cho nhà tuyển dụng.
    _cssp = get("/static/app.css")[1]
    _in = _cssp[_cssp.index("@media print"):]
    _an = _in[:_in.index("}", _in.index("display:none"))]
    for _lop in (".statusbar", ".cvaudit", ".side", ".mbtn", ".titlebar"):
        check(f"khi in, ẩn {_lop}", _lop in _an)
    # PHÔNG NHÚNG ĐƯỢC. Phông hệ thống macOS (.SF NS) không nhúng vào PDF được
    # nên Chrome vẽ từng chữ thành GLYPH TAY: đo trên bản in thật 34 phông
    # Type3 + CharProcs, 0 phông TrueType. Trình bóc chữ xoàng cho ra
    # "D a c  V in h  N g u y e n" — đúng nguyên nhân hỏng parse mà Greenhouse
    # liệt kê. Đổi sang Georgia/Times: Type3 34 -> 0, và PDF nhẹ 217 -> 132 KB.
    # THẺ CHỮA BÀI và VỆT TÔ không được in ra giấy — bút đỏ là chuyện giữa
    # app và Vin, tờ giấy gửi đi chỉ có tờ CV.
    # `_an` chỉ là luật display:none ĐẦU TIÊN; thẻ chữa bài ẩn ở luật khác,
    # nên tìm trong cả khối @media print.
    check("khi in, đóng thẻ chữa bài",
          ".ccard { display:none" in _in or ".ccard { display:none" in
          _in.replace(", .ccard", " .ccard") or ".ccard" in _in)
    check("khi in, bỏ vệt tô từ khoá",
          ".kw { background:none !important" in _in)
    # GẠCH CHÂN CHỮA BÀI cũng không được in — tờ giấy gửi đi không mang bút đỏ.
    check("khi in, bỏ mọi gạch chân chữa bài",
          ".vthieu_so, .vqua_dai, .vlac_de, .vda_sua {" in _in)
    check("tờ CV in bằng phông NHÚNG ĐƯỢC, không phải phông hệ thống",
          'font-family:Georgia,"Times New Roman",serif' in _in)
    # `main` là position:fixed left:226px (chừa chỗ thanh bên). Khi in, Chrome
    # đặt phần tử fixed theo HỘP TRANG và `left` không ghi đè được — ép cả
    # bằng CSS lẫn style inline đều không nhúc nhích. Phải trả về dòng chảy.
    check("khi in, main trả về position:static — không thì tờ CV lệch 226px",
          "position:static !important" in _in)
    # MÀU IN đặt mặc định ĐEN rồi mới làm nhạt vài chỗ. Luật cũ liệt kê từng
    # lớp cần tô đen, nên lớp nào quên thì giữ màu giao diện TỐI: đo được
    # .cvskill ở 192/255, cả mục TECHNICAL SKILLS gần như vô hình.
    check("màu in mặc định là ĐEN cho mọi thứ trong tờ CV",
          ".cvpaper, .cvpaper * { color:#111 !important }" in _in)

    # CỔNG KIỂM lúc in. Nó soi chính trang sắp in, nên bắt được thứ test HTML
    # không bắt được: rác app lọt ra giấy, chữ nhợt, tờ CV lệch lề.
    from jobbot.cv import pdf as _pdfm
    for _dau in ("rác app in ra", "chữ quá nhợt", "lệch vào"):
        check(f"cổng kiểm có soi «{_dau}»", _dau in _pdfm._SOI)
    check("ngưỡng nhợt được đặt tên, không gõ số trong JS",
          "SANG_NHAT" in _pdfm._SOI and isinstance(_pdfm.SANG_NHAT, int))
    # CHÍNH CỔNG HỎNG THÌ PHẢI KÊU. Bản đầu nuốt ValueError rồi báo "sạch" ở
    # mọi lượt in — một cổng im lặng báo sạch khi nó gãy thì tệ hơn không có.
    class _TabHong:
        def call(self, *a, **k): pass
        def eval(self, *a, **k): raise RuntimeError("gãy")
    _ra = _pdfm.kiem(_TabHong())
    check("cổng kiểm gãy -> KÊU LÊN, không báo sạch",
          _ra and "KHÔNG SOI ĐƯỢC" in _ra[0], str(_ra))
    # Bản chấm điểm phải nằm TRONG .cvaudit. Luật ẩn đã có sẵn từ lâu nhưng
    # không chỗ nào GẮN lớp đó, nên nó là một luật không canh gì cả.
    from jobbot.cv.build import TailoredCV as _TC2
    from jobbot.cv import report as _rp2
    check("phần chi tiết nằm trong .cvaudit nên không lọt vào PDF",
          _rp2.chi_tiet(_TC2(header=[], summary="", sections=[], dropped=[],
                             wanted=[], covered=[], missing=[]))
          .startswith("<div class=cvaudit>"))

    # NÚT PDF PHẢI GIAO TỆP TẬN TAY. Vỏ app là WKWebView, mà WKWebView KHÔNG
    # tự tải tệp — không có delegate thì Content-Disposition im lặng không làm
    # gì. Nên chép sang Downloads rồi mở Finder.
    from jobbot.cv.pdf import tai_ve as _tv
    import tempfile as _tf9, pathlib as _pl9, os as _os9
    _that_home = _os9.environ.get("HOME")
    with _tf9.TemporaryDirectory() as _h9:
        _os9.environ["HOME"] = _h9
        try:
            (_pl9.Path(_h9) / "Downloads").mkdir()
            _src = _pl9.Path(_h9) / "a.pdf"
            _src.write_bytes(b"%PDF-1.4 x")
            _d1 = _tv(_src)
            check("chép được sang Downloads", _d1 and _d1.exists()
                  and _d1.parent.name == "Downloads")
            _d2 = _tv(_src)
            # Trùng tên thì thêm số: bản cũ có thể đã gửi đi và còn cần đối chiếu.
            check("in lần hai KHÔNG đè lên bản cũ", _d2 != _d1 and _d1.exists())
            check("tệp không có thật -> trả None, không nổ",
                  _tv(_pl9.Path(_h9) / "khong-co.pdf") is None)
        finally:
            if _that_home is None:
                _os9.environ.pop("HOME", None)
            else:
                _os9.environ["HOME"] = _that_home

    # Ô TÌM phải THẬT SỰ LỌC, không chỉ vẽ ra cho đẹp.
    from jobbot.dashboard.views import cvlist as _cvl
    _gia_ver = [
        {"jobs": [{"id": 1, "company": "Man Group", "title": "Quant", "score": 90}],
         "only": ["a"], "missing": [], "lines": 1,
         "hoi": 6, "tra_loi": 4, "cam": ["derivatives"]},
        {"jobs": [{"id": 2, "company": "Citadel", "title": "Data Scientist",
                   "score": 80}], "only": ["b"], "missing": [], "lines": 1,
         "hoi": 7, "tra_loi": 1, "cam": ["cloud", "nlp"]},
    ]
    _gia_data = {"versions": _gia_ver, "jobs": 2, "gaps": [], "core": 0}
    _co = _cvl._list(_gia_data, "man group")
    check("tìm theo tên công ty -> chỉ còn bản khớp",
          "Man Group" in _co and "Citadel" not in _co)
    check("và nói rõ lọc còn mấy bản trên tổng", "1</b>/2 bản" in _co)
    _ct = _cvl._list(_gia_data, "data scientist")
    check("tìm theo CHỨC DANH cũng được", "Citadel" in _ct and "Man Group" not in _ct)
    check("không khớp gì -> nói thẳng, không trả danh sách rỗng",
          "không bản nào gửi cho" in _cvl._list(_gia_data, "zzzz"))
    check("ô tìm vẫn còn khi không khớp — để sửa chữ ngay tại chỗ",
          "class=jfind" in _cvl._list(_gia_data, "zzzz"))
    # SỐ HIỆU BẢN phải giữ nguyên khi lọc: "#2" lúc tìm mà là "#1" lúc không
    # tìm thì không nói chuyện được về một bản cụ thể.
    check("số hiệu bản giữ nguyên khi lọc", ">#2<" in _ct)
    check("không tìm thì hiện đủ cả hai",
          "Man Group" in _cvl._list(_gia_data) and "Citadel" in _cvl._list(_gia_data))

    # DÒNG PHẢI NÓI ĐƯỢC ĐIỀU GÌ THẬT. Bản cũ in ra 4 câu tiếng Anh RIÊNG của
    # bản đó — chữ chính Vin viết, đọc lại không nắm thêm gì, mà nhân 28 dòng
    # thì không ai đọc nổi.
    _ca = _cvl._list(_gia_data)
    check("dòng KHÔNG còn đổ nguyên câu CV ra danh sách", "cvonly" not in _ca)
    check("dòng dẫn bằng TIN, không dẫn bằng tài liệu",
          "Man Group" in _ca and "Quant" in _ca)
    check("có tỉ lệ phủ của chính tin đó", "4/6" in _ca and "1/7" in _ca)
    check("và vẽ thành thanh để quét được 28 dòng", "vbarc" in _ca)
    # BA MỨC = BA HÀNH ĐỘNG: gửi được / yếu / viết thêm đã. Một màu cho tất cả
    # thì thanh chỉ là trang trí.
    check("phủ cao -> mức ok", "vbarc ok" in _ca)
    check("phủ thấp -> mức low", "vbarc low" in _ca)
    # Hai con số là HAI câu hỏi khác nhau; gộp chữ thì người đọc trừ 6−4=2 rồi
    # tưởng máy đếm sai khi danh sách chỉ có 1 mục.
    check("nói rõ 'hồ sơ chưa có câu nào về', không phải 'bản này thiếu'",
          "hồ sơ chưa có câu nào về" in _ca)
    _nhom2 = [{"jobs": [{"id": 5, "company": "A", "title": "X", "score": 90},
                        {"id": 6, "company": "B", "title": "Y", "score": 70}],
               "only": [], "missing": [], "lines": 0,
               "hoi": 4, "tra_loi": 2, "cam": []}]
    check("nhóm >1 tin -> nói rõ bản dùng chung cho mấy tin",
          "dùng chung cho" in _cvl._list({"versions": _nhom2, "jobs": 2,
                                          "gaps": [], "core": 0}))
    check("nhóm 1 tin -> KHÔNG ghi 'dùng chung', đó là nói thừa",
          "dùng chung cho" not in _ca)
    # Dòng phải mở đúng tin người ta vừa gõ tên, không mở một tin khác cùng bản.
    _hai = [{"jobs": [{"id": 9, "company": "Low Co", "title": "X", "score": 99},
                      {"id": 7, "company": "Man Group", "title": "Y", "score": 10}],
             "only": [], "missing": [], "lines": 0,
             "hoi": 4, "tra_loi": 2, "cam": []}]
    check("đang tìm thì dòng trỏ tới ĐÚNG tin khớp, không phải tin điểm cao nhất",
          "/jobs/7/cv" in _cvl._list({"versions": _hai, "jobs": 2, "gaps": [],
                                      "core": 0}, "man group"))
    check("POST /cv/pdf id không phải số -> 400",
          post_form("/cv/pdf", "arg=abc") == 400)

    print("\n[tấm phủ: mỗi form phải đi đúng action của nó]")
    # live.js từng chặn MỌI .setform rồi gửi cứng tới '/settings'. Hậu quả:
    # bấm "Xoá khối" trong tấm phủ soạn CV lại mở ra Cài đặt. Thử bằng
    # form.submit() không lộ, vì cách đó bỏ qua trình nghe submit.
    js = (Path("src/jobbot/dashboard/web/live.js")).read_text()
    check("live.js chỉ chặn form có action /settings",
          "pathname !== '/settings'" in js)
    for url in ("/cv/soan?moi=1", "/cv/draft?id=1"):
        _s, frag = get(url)
        if _s != 200:
            continue
        check(f"{url:<22} form trỏ đúng action của mình",
              "action='/settings'" not in frag)

    print("\n[CV: project xong -> dòng CV]")
    # Lỗi trong một route POST làm ĐỨT kết nối, không trả gì cả — curl báo
    # "empty reply", trình duyệt hiện 404, nhật ký im lặng. Đã xảy ra thật với
    # /cv/draft (thiếu `self.`). Mọi route POST phải được gọi ít nhất một lần.
    check("GET /cv/draft với id lạ -> 404, không sập",
          get("/cv/draft?id=999999")[0] == 404)
    check("POST /cv/draft cũng đã bỏ -> 404",
          post_form("/cv/draft", "id=0&head=&line=") == 404)

    print("\n[CV: mọi bản sẽ gửi, xem trước khi gửi]")
    _s, body = get("/cv")
    check("/cv có trong thanh bên", 'href="/cv"' in body or "href='/cv'" in body)
    check("gộp bản trùng, không liệt kê từng tin",
          body.count("class=cvrow") <= 60)
    check("nói THẲNG mức may đo thật, không khoe số bản",
          "giống hệt nhau ở mọi bản" in body)
    check("mỗi dòng trỏ tới bản CV đọc được", "/cv'" in body and "cvrow" in body)
    check("nói ra kỹ năng hồ sơ KHÔNG nói được câu nào",
          "KHÔNG nói được câu nào" in body)

    from jobbot.dashboard import live as live2
    data = live2.cv_versions(db.connect(Path(tmp) / "jobbot.db"))
    if data["versions"]:
        check("phần RIÊNG của mỗi bản không lẫn vào phần lõi",
              all(len(v["only"]) == v["lines"] - data["core"]
                  for v in data["versions"]))
        check("bản nhiều tin nhất đứng đầu",
              [len(v["jobs"]) for v in data["versions"]]
              == sorted((len(v["jobs"]) for v in data["versions"]), reverse=True))

    print("\n[personal project ĐÃ BỎ — không được để lại đường cụt]")
    # Bỏ một tính năng mà quên gỡ đường dẫn thì tab cũ trả 500, còn nút cũ
    # trong trình duyệt đã mở sẵn vẫn bấm được. Xoá là phải xoá HẾT lối vào.
    for _duong in ("/projects",):
        check(f"GET {_duong} -> 404, không phải 500", get(_duong)[0] == 404)
    for _api in ("/api/project/build", "/api/project/state"):
        check(f"POST {_api} -> 404", post_form(_api, "arg=x") == 404)
    check("GET /cv/draft cũng đi theo", get("/cv/draft?id=1")[0] == 404)
    # Tab Projects phải biến khỏi thanh điều hướng, không chỉ khỏi router.
    check("không còn tab Projects trên thanh bên",
          ">Projects<" not in get("/cv")[1])
    # Hai thứ KHÔNG chết theo, vì chúng chưa bao giờ thuộc tính năng đó.
    from jobbot.scoring.market import demand as _dm
    from jobbot.scoring.vocab import INDUSTRY as _ind
    conn2 = db.connect(Path(tmp) / "jobbot.db")
    check("phép đếm thị trường sống tiếp ở scoring/", isinstance(_dm(conn2), Counter))
    conn2.close()
    check("bộ từ ngành sống tiếp ở vocab/", len(_ind) == 7)
    # Tab CV là chỗ DUY NHẤT còn dùng phép đếm đó. Nó phải mở được, vì đường
    # import vừa đổi nhà — gãy ở đây thì cả tab CV trắng.
    check("tab CV vẫn mở được sau khi phép đếm đổi nhà", get("/cv")[0] == 200)

    print("\n[tab CV: HAI núm, và cả hai phải thật sự xoay]")
    from jobbot.core import prefs as _pfc
    _adj = get("/adjust/cv")[1]
    # BẢY NÚM ĐÃ BỎ — xem lời chú ở core/prefs.py. Người dùng cần đúng hai câu
    # trả lời: bản riêng cho từng tin tới mức nào, và máy có tự lo hay không.
    # Mọi núm khác đều bắt họ học luật của máy trước khi dùng được máy.
    for _bo in ("khoa:", "giong:", "bo_cuc:", "that_bai:", "y_kien:",
                "rui_ro:", "giu_muc:", "moi_khoi_viec:"):
        check(f"bỏ núm {_bo[:-1]}", f"data-arg='{_bo}" not in _adj)
    check("tấm Điều chỉnh chỉ còn HAI núm",
          _adj.count("data-post='/api/cv/num'") == 4)   # 3 mức may đo + 1 tự lo

    # ĐỘ MAY ĐO — núm đổi thật nhiều nhất. Đo trên kho thật (358 tin):
    # chung 25 bản · vừa 89 · riêng 157, lõi bất biến rơi 12/16 -> 9/16 câu.
    for _r in ("chung", "vua", "rieng"):
        check(f"có mức may đo {_r}", f"rieng:{_r}" in _adj)
    # KHÔNG gõ cứng số bản vào nhãn: nó khác theo từng hồ sơ và từng kho tin.
    check("nhãn nói VIỆC nó làm, không gõ cứng số bản của một kho khác",
          "đưa mục kỹ năng tin này hỏi lên trước" in _adj
          and "bản/120 tin" not in _adj)
    check("có công tắc MÁY TỰ LO", "data-arg='tu_lo:" in _adj)
    check("lý do nằm trong thẻ gấp, không đổ thẳng ra",
          "<details class=swwhy>" in _adj)
    check("chữ không chạm viền tấm phủ", "class=adjbox" in _adj)
    # LUẬT BỎ CÂU vẫn chạy — chỉ là không còn nút để lật. Người dùng mất nút,
    # không mất thông tin: bản chấm điểm vẫn nói rõ câu nào bị bỏ vì sao.
    from jobbot.cv.rules import sentence_ok as _sok
    check("luật bỏ câu kể thất bại vẫn chạy dù không còn nút",
          _sok("The drawdown ran 30% deeper than the model predicted here.")[0]
          == "drop")

    # TẤM ĐIỀU CHỈNH KHÔNG ĐƯỢC GÕ CỨNG CÂU CỦA AI. Bản trước trích thẳng câu
    # trong CV của một người vào phần giải thích; hồ sơ khác mở lên thì đó là
    # câu của người lạ, và panel thành tờ quảng cáo chứ không phải bản mô tả
    # hồ sơ của người đang đọc.
    import pathlib as _plG
    _cvl_src = "\n".join(
        l.split("#")[0] for l in
        (_plG.Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/views/cvlist.py")
        .read_text(encoding="utf-8").splitlines())
    for _cau in ("Self-funded", "drawdown ran", "Profit on its own",
                 "WorldQuant", "Compute · Method"):
        check(f"panel KHÔNG gõ cứng «{_cau[:22]}»", _cau not in _cvl_src)

    check("POST rieng:chung -> lưu được",
          post_form("/api/cv/num", "arg=rieng:chung") == 200)
    check("POST tu_lo:1 -> lưu được", post_form("/api/cv/num", "arg=tu_lo:1") == 200)
    check("núm đã bỏ -> 400", post_form("/api/cv/num", "arg=giong:nguyen") == 400)
    check("núm nhận sai giá trị -> 400",
          post_form("/api/cv/num", "arg=rieng:xx") == 400)
    check("giá trị lạ -> 400, không lưu bừa",
          post_form("/api/cv/num", "arg=khoa:xxx") == 400)
    # ĐỔI CÂU: máy chỉ nhận câu, không nhận chữ tự do — và id tin phải là số.
    check("POST /api/cv/pick thiếu id tin -> 400",
          post_form("/api/cv/pick", "job=&text=abc") == 400)
    check("id tin không phải số -> 400",
          post_form("/api/cv/pick", "job=xyz&text=abc") == 400)
    check("thiếu câu -> 400", post_form("/api/cv/pick", "job=1&text=") == 400)
    check("tên núm lạ -> 400", post_form("/api/cv/num", "arg=lung:tung") == 400)

    _cvn = db.connect(Path(tmp) / "jobbot.db")
    # XOAY NÚM THÌ NÚT PHẢI ĐỔI. Núm mà không đổi được nút là núm trang trí:
    # người dùng bấm, không thấy gì khác, rồi không tin cả bảng núm nữa.
    _st_num = _bt.stage(_cvn)
    check("xoay núm -> nút thành Cập nhật", _st_num["label"] == "Cập nhật",
          _st_num["label"])
    check("và nói rõ CÁI GÌ vừa đổi",
          "xoay núm" in _st_num["note"], _st_num["note"])
    # ĐỘ MAY ĐO phải đổi được CHỮ IN RA THẬT, không chỉ đổi một dòng trong DB.
    # Đây là núm đổi nhiều nhất của cả app: đo trên kho thật 358 tin, chung 25
    # bản · vừa 89 · riêng 157, lõi bất biến rơi 12/16 -> 9/16 câu.
    from jobbot.cv.build import build as _bcv
    from jobbot.profile import store as _stc
    _ans = _stc.load(_cvn)
    _row = _cvn.execute("SELECT description, score_json FROM posting"
                        " WHERE kept = 1 LIMIT 1").fetchone()
    import json as _jsonc
    _ex = _jsonc.loads(_row["score_json"]) if _row and _row["score_json"] else None
    _jd = (_row["description"] if _row else "") or ""
    def _ky_cua(cv):
        return [l.text for s2 in cv.sections if s2.kind == "skill" for l in s2.lines]
    _chung = _ky_cua(_bcv(_ans, _ex, _jd, {"rieng": "chung"}))
    _rieng = _ky_cua(_bcv(_ans, _ex, _jd, {"rieng": "rieng"}))
    # KHÔNG ĐƯỢC MẤT MỘT CHỮ NÀO — đây là CV gửi nhà tuyển dụng.
    import re as _reB
    check("xếp lại KHÔNG mất chữ nào của mục kỹ năng",
          sorted(_reB.findall(r"\w+", " ".join(_chung)))
          == sorted(_reB.findall(r"\w+", " ".join(_rieng))))
    check("và KHÔNG mất mục nào", len(_chung) == len(_rieng))
    _cvn.close()
    post_form("/api/cv/num", "arg=rieng:rieng")
    post_form("/api/cv/num", "arg=tu_lo:0")

    print("\n[bản chấm điểm: máy phải GIẢI TRÌNH, không chỉ quyết]")
    # Luật cấm câu kể thất bại lên CV từ đầu, nhưng bộ dựng chưa bao giờ tra —
    # 3 câu bị cấm đi ra ngoài trên MỌI bản. Không ai thấy vì không có bản
    # giải trình nào để mà đọc.
    _s, _bcv_html = get("/jobs/1/cv")
    if _s == 200:
        from jobbot.cv import rules as _rl
        _cvr = db.connect(Path(tmp) / "jobbot.db")
        _r1 = _cvr.execute("SELECT description, score_json FROM posting"
                           " WHERE id = 1").fetchone()
        _cv1 = _bcv(_stc.load(_cvr),
                    _jsonc.loads(_r1["score_json"]) if _r1["score_json"] else None,
                    _r1["description"] or "")
        _lot = [l.text for s2 in _cv1.sections
                if s2.kind in ("experience", "project")
                for l in s2.lines
                if _rl.sentence_ok(l.goc or l.text, l.hits)[0] == "drop"]
        check("KHÔNG còn câu bị luật cấm lọt ra bản CV", not _lot, str(_lot[:1]))
        _cvr.close()
        check("bản chấm điểm có mục trước/sau", "ĐÃ SỬA" in _bcv_html.upper()
              or "gsua" in _bcv_html)
        check("nói ra máy chỉ cắt chữ, không viết thêm",
              "cắt và xếp lại" in _bcv_html)
    # HAI NHÓM BỎ phải tách, vì hai nhóm cần hai hành động khác nhau: câu bị
    # luật cấm thì sửa chữ cũng vô ích, câu yếu hơn thì không phải sửa gì.
    from jobbot.cv.build import TailoredCV as _TCV
    from jobbot.cv import report as _rp
    _gia = _TCV(header=[], summary="", sections=[],
                dropped=[("A failure sentence.",
                          "outcome failure — belongs on the project page, not the CV"),
                         ("A fine sentence.",
                          "weaker than what this posting asks for")],
                wanted=["python"], covered=[], missing=["c++"])
    _rh = _rp.chi_tiet(_gia)
    check("nhóm 'luật không cho lên CV' hiện riêng",
          "Luật không cho lên CV (1)" in _rh)
    check("nhóm 'để dành cho tin khác' hiện riêng",
          "Để dành cho tin khác (1)" in _rh)
    check("lý do dịch sang tiếng Việt, không để nguyên tiếng Anh",
          "kể thất bại" in _rh and "outcome failure" not in _rh)
    check("nói ra chỗ hồ sơ CÂM", "hồ sơ câm" in _rh and "c++" in _rh)

    print("\n[BACKEND ↔ FRONTEND: một luật, một kho nhớ, một chỗ quên]")
    import ast as _ast5, pathlib as _pl5
    _live_src = (_pl5.Path(__file__).resolve().parent.parent
                 / "src/jobbot/dashboard/live.py").read_text(encoding="utf-8")
    _all_src = "\n".join(
        f.read_text(encoding="utf-8")
        for f in (_pl5.Path(__file__).resolve().parent.parent / "src").rglob("*.py"))

    # MỘT KHO NHỚ. Trước đây ba cache (_CV_CACHE, _BLOCK_CACHE, _HUT_CACHE)
    # cùng dựng trên một khoá nhưng bị xoá ở BA TẬP CHỖ khác nhau: reset quên
    # _HUT_CACHE, route xoay núm quên _BLOCK_CACHE, batch chỉ xoá _CV_CACHE.
    # Ba thứ cùng đầu vào mà hết hạn theo ba lịch thì màn hình trộn số cũ với
    # số mới, và không ai lần ra được.
    # Bỏ CHÚ THÍCH trước khi soi: lời chú giải thích vì sao mấy cache đó biến
    # mất có nhắc tên chúng, và bắt chính lời chú của mình là test vô dụng.
    _code = "\n".join(
        l.split("#")[0] for l in _all_src.splitlines())
    for _c in ("_CV_CACHE", "_BLOCK_CACHE", "_HUT_CACHE"):
        check(f"không còn cache rời {_c}", _c not in _code)
    check("có đúng MỘT kho nhớ cho tầng CV", _all_src.count("_NHO: dict = {}") == 1)
    check("và đúng MỘT chỗ quên", "def quen()" in _live_src)
    # Mọi chỗ đụng tới hồ sơ/núm phải gọi quen(), không tự xoá tay.
    check("mọi chỗ xoá đều đi qua quen()",
          _all_src.count(".clear()") == _all_src.count("_NHO.clear()")
          + _all_src.count("opened.clear()") + _all_src.count("vua_phu.clear()")
          or ".quen()" in _all_src)

    # MỘT LUẬT. `cv_gia` (tấm Điều chỉnh) và `build` (bộ dựng) phải hỏi CÙNG
    # một hàm về "mục kỹ năng này có bị bỏ không". Trước đây cv_gia tra một
    # tập hằng đã bị làm rỗng, nên panel báo "không bỏ mục nào" trong khi bộ
    # dựng vẫn bỏ thật — hai tầng nói hai điều về cùng một việc.
    check("tấm Điều chỉnh và bộ dựng dùng CHUNG luật bỏ mục kỹ năng",
          _all_src.count("bo_muc_ky_nang(") >= 2)
    check("và không còn tra bảng hằng đã chết",
          "DROP_SKILL_GROUPS" not in _code)

    print("\n[tấm phủ KHÔNG được chắn cả trang khi đang đóng]")
    # LỖI THẬT, và là loại tệ nhất: cả app không bấm được gì.
    # `hidden` chỉ là luật [hidden]{display:none} của trình duyệt.
    # `.sheet{display:flex}` cùng độ ưu tiên nhưng là CSS của mình nên THẮNG —
    # tấm phủ nằm trên cùng vĩnh viễn, phủ đen cả trang, nuốt mọi cú bấm.
    css = get("/static/app.css")[1]
    check("có luật .sheet[hidden] để hidden thật sự ăn",
          ".sheet[hidden]{display:none}" in css)
    # Đặt display trên .sheet mà KHÔNG có luật [hidden] đi kèm là tái hiện lỗi.
    body_rule = css.split(".sheet{")[1].split("}")[0]
    check("và luật đó đứng SAU luật .sheet gốc",
          css.index(".sheet[hidden]") > css.index(".sheet{"))
    check("tấm phủ có nền che thật (nên nếu hở là chắn cả trang)",
          "rgba(0,0,0,.5)" in body_rule or "z-index:60" in body_rule)

    print("\n[sắc độ — thang xám kiểu VS Code]")
    # Lỗi cũ: --mute (màu chữ dùng nhiều nhất app, 84 chỗ) chỉ đạt 3.1:1 trên
    # --panel-2, dưới ngưỡng 4.5 của chữ thường mà lại toàn cỡ 10-12px. Chốt
    # luật ở đây để không ai hạ bậc chữ xuống dưới ngưỡng nữa.
    def _cr(a, b):
        def _lin(c):
            c /= 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        def _lum(h):
            h = h.lstrip("#")
            r, g, bl = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            return .2126 * _lin(r) + .7152 * _lin(g) + .0722 * _lin(bl)
        x, y = _lum(a), _lum(b)
        return (max(x, y) + .05) / (min(x, y) + .05)

    import re as _rec
    _cssv = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    _root = _rec.search(r":root\{(.*?)\n\}", _cssv, _rec.S)
    _var = dict(_rec.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", _root.group(1)))
    _mat = [v for v in ("side", "bg", "panel", "panel-2") if v in _var]
    _txt = [v for v in ("ink", "dim", "mute", "acc", "warn", "bad") if v in _var]
    check("đọc được đủ 4 mặt nền và 6 bậc chữ", len(_mat) == 4 and len(_txt) == 6)
    _low = [f"{t} trên {m} = {_cr(_var[t], _var[m]):.2f}"
            for t in _txt for m in _mat if _cr(_var[t], _var[m]) < 4.5]
    check("mọi bậc chữ đọc được trên mọi mặt nền (>=4.5:1)", not _low, str(_low))
    # Tự chứng: đắp lại giá trị CŨ thì luật trên PHẢI gãy. Không có dòng này
    # thì một hôm nào đó :root đổi tên biến, vòng lặp quét 0 cặp và vẫn xanh.
    check("luật này bắt được đúng lỗi cũ (#717976)",
          _cr("#717976", _var["panel-2"]) < 4.5)
    # Xám phải TRUNG TÍNH — xám ngả màu thì cãi nhau với màu nhấn.
    _amm = {k: max(int(_var[k][i:i + 2], 16) for i in (1, 3, 5))
            - min(int(_var[k][i:i + 2], 16) for i in (1, 3, 5)) for k in _mat}
    check("mặt nền là xám trung tính, không ám màu", max(_amm.values()) == 0, str(_amm))

    # KHUNG NÓI NHỎ, NỘI DUNG NÓI TO. Trước đây ngược: thanh bên 8.1:1 và
    # thanh trạng thái 12.2:1 trong khi nội dung chỉ 6.8:1 — đồ phụ hét to hơn
    # việc đang làm. Chữ khung đo trên --side, chữ nội dung đo trên --panel.
    # BẬC NỀN: tương phản phải dồn vào chỗ LÀM VIỆC, không dồn vào đồ phụ.
    # VS Code chỉ có hai mặt phẳng: khung nằm dưới editor 3.5 điểm L* (yếu),
    # mặt nổi bật lên 8.6 điểm (mạnh). Bản cũ của ta chia đều +3.5 / +3.9 nên
    # thanh bên nặng ngang nội dung — thẻ không nổi lên được.
    def _ls(h):
        def _lin(c):
            c /= 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        h = h.lstrip("#")
        r, g, bl = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        y = .2126 * _lin(r) + .7152 * _lin(g) + .0722 * _lin(bl)
        return 116 * y ** (1 / 3) - 16 if y > 0.008856 else 903.3 * y

    def _luat(var):
        """(nền main có đen không, khung có xám-sáng-hơn-main không, thẻ bật bao nhiêu)"""
        return (_ls(var["bg"]) <= 5.0,
                _ls(var["side"]) - _ls(var["bg"]) >= 3.0,
                _ls(var["panel"]) - _ls(var["bg"]))
    _den, _xam, _bat = _luat(_var)
    check(f"nền vùng main là ĐEN (L*{_ls(_var['bg']):.1f} <= 5)", _den)
    check(f"khung phụ là XÁM, sáng hơn main "
          f"(+{_ls(_var['side']) - _ls(_var['bg']):.1f})", _xam)
    check(f"thẻ bật hẳn khỏi nền main (+{_bat:.1f} >= 8)", _bat >= 8.0)
    # Tự chứng: bộ CŨ (khung tối hơn main, thẻ bật yếu) phải phá cả ba luật.
    _cu = {"side": "#161616", "bg": "#1D1D1D", "panel": "#252525"}
    check("luật này bắt được đúng bộ cũ (khung tối hơn main)",
          not any((_luat(_cu)[0], _luat(_cu)[1], _luat(_cu)[2] >= 8.0)))

    _sc = _rec.search(r"\.side,\.statusbar\{(.*?)\}", _cssv, _rec.S)
    _cvar = dict(_rec.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", _sc.group(1)))
    check("khung app khai lại đủ ba bậc chữ của riêng nó",
          sorted(_cvar) == ["dim", "ink", "mute"])
    _khung = max(_cr(v, _var["side"]) for v in _cvar.values())
    _noidung = min(_cr(_var[t], _var["panel"]) for t in ("ink", "dim", "mute"))
    check(f"chữ khung nhạt hơn chữ nội dung ({_khung:.2f} < {_noidung:.2f})",
          _khung < _noidung)
    check("nhưng chữ khung vẫn đọc được (>=4.5:1)",
          min(_cr(v, _var["side"]) for v in _cvar.values()) >= 4.5)
    # Tự chứng: bậc chữ khung CŨ (dùng chung --dim của nội dung) phải phá luật.
    check("luật này bắt được đúng lỗi cũ (khung dùng chung --dim)",
          not _cr(_var["dim"], _var["side"]) < _noidung)

    print("\n[Cài đặt là MENU, không phải tab]")
    _, home = get("/")
    check("Settings không còn trong thanh bên", "href='/settings'" not in home)
    check("có nút bánh răng ở đáy thanh bên", "data-appset" in home)
    check("và có sẵn tấm phủ rỗng để nạp vào", "data-sheet" in home)
    check("tấm phủ mặc định ĐANG ĐÓNG", "class=sheet hidden" in home)

    code, panel = get("/settings")
    check(f"/settings trả 200", code == 200)
    # Trả MẢNH, không phải cả trang: nếu trả cả trang thì nhét vào tấm phủ sẽ
    # lồng nguyên một trang trong trang.
    check("/settings trả MẢNH html, không phải cả trang",
          panel.lstrip().startswith("<div") and "<!doctype" not in panel.lower())
    # CHIA TAB. Trước đây một cột dài 782px trong hộp cao 660px — phần "Làm
    # lại từ đầu" nằm dưới nếp gấp, phải cuộn mới thấy mà không ai biết là
    # cuộn được. Chia theo VIỆC: chạy / nguồn / chỉ đọc / phá huỷ.
    check("mỗi tab có đúng một khối nội dung",
          panel.count("data-stab=") == panel.count("data-pane=") > 3)
    check("chỉ một tab mở sẵn", panel.count("stpane on") == 1)

    # TAB NGUỒN — bật/tắt từng ATS. "API" là ba nhà cung cấp, không phải 34
    # board công ty: giới thiệu từng công ty thì vô nghĩa, còn ba ATS thì khác
    # nhau thật (cách trả dữ liệu, loại công ty, tỉ lệ dùng được).
    check("có tab Nguồn", "data-stab='nguon'" in panel and ">Nguồn<" in panel)
    for _ats in ("greenhouse", "lever", "ashby"):
        check(f"có công tắc cho {_ats}", f"name=ats value='{_ats}'" in panel)
    # Giới thiệu bằng SỐ THẬT của chính kho này, không bằng tính từ: "hiện
    # đại", "phổ biến" thì không ai chọn được gì.
    check("có công tắc cho thư báo việc", "name=ats value='alert'" in panel)
    check("mỗi nguồn kèm số thật, không chỉ lời khen",
          panel.count("class=srcnum") == 4 and "tin về · giữ" in panel,
          str(panel.count("class=srcnum")))
    # Thư báo không phải ATS: không có board nào để đếm, nên đừng ghi
    # "0 board" — một con số 0 vô nghĩa đọc ra như đang hỏng.
    _dong_alert = panel.split("value='alert'")[1].split("</label>")[0]
    check("thư báo KHÔNG ghi '0 board'", "0 board" not in _dong_alert)
    # MỖI FORM CHỈ SỬA PHẦN CỦA NÓ. Nhiều form cùng gửi về /settings; đọc mù
    # thì form Nguồn (không mang ô nhịp quét) ghi mặc định 60 đè lên số cũ.
    check("mỗi form khai rõ mình là phần nào",
          panel.count("name=phan") == panel.count("<form class=setform"))

    # CHỐT EMAIL: hộp thư quét phải ĐÚNG hộp thư khai trong hồ sơ. Thử thật
    # qua HTTP, không chỉ đọc mã nguồn.
    _ma_sai, _than_sai = (post("/api/mail/setup",
                               b"address=nham@x.y&password=abcdefghijklmnop"),
                          _post_raw("/api/mail/setup",
                                    b"address=nham@x.y&password=abcdefghijklmnop"))
    check("nối hộp thư KHÁC hồ sơ thì bị từ chối", _ma_sai == 400, str(_ma_sai))
    check("và nói rõ cả hai địa chỉ",
          "nham@x.y" in _than_sai and PROFILE["email"] in _than_sai, _than_sai[:90])
    check("kèm cách sửa", "cho khớp" in _than_sai)

    # TAB GMAIL — cấu hình hộp thư về đúng chỗ cấu hình.
    check("có tab Gmail", "data-stab='gmail'" in panel and ">Gmail<" in panel)
    # Nút "Nối hộp thư…" bên Quản lí phải mở ĐÚNG tab Gmail. Chỉ đường nửa
    # vời — mở Cài đặt rồi bỏ người ta ở tab Chạy — còn khó chịu hơn không chỉ.
    check("openSheet nhận tên tab", "function openSheet(url, kind, tab)" in _js)
    # Bấm tab NGAY KHI nội dung về, không hẹn giờ: nạp bằng fetch thì đặt
    # setTimeout là đoán xem mạng nhanh hay chậm, và trên máy chậm thì lúc
    # hẹn giờ nổ cái nút còn chưa tồn tại.
    _mo = _js.split("function openSheet")[1].split("function closeSheet")[0]
    # BỎ chú thích trước khi kiểm: chính chú thích giải thích vì sao KHÔNG
    # dùng setTimeout lại chứa chữ "setTimeout", và bài test đọc nhầm lời
    # giải thích thành đoạn mã nó đang cấm.
    _ma = "\n".join(l for l in _mo.split("\n") if not l.strip().startswith("//"))
    check("nhảy tab trong .then, không phải setTimeout",
          "nut.click()" in _ma and "setTimeout" not in _ma, "")
    check("và ô đặt số ngày đọc lại thư", "name=mail_days" in panel)
    from jobbot.core import prefs as _pf2
    _c2 = db.connect()
    post("/settings", b"phan=gmail&mail_days=45")
    check("lưu được số ngày", _pf2.num(_c2, _pf2.MAIL_DAYS, 1, 365) == 45,
          str(_pf2.num(_c2, _pf2.MAIL_DAYS, 1, 365)))
    check("và KHÔNG đụng tới nhịp quét",
          _pf2.num(_c2, _pf2.SCAN_EVERY, 5, 1440) != 0)
    post("/settings", b"phan=gmail&mail_days=30")
    _c2.close()

    _c2 = db.connect()
    _pf2.put(_c2, _pf2.SCAN_EVERY, "45")
    post("/settings", b"phan=nguon&ats=greenhouse&ats=lever")
    check("lưu tab Nguồn: tắt ashby", not _pf2.flag(_c2, _pf2.SRC_ATS["ashby"]))
    check("và giữ nguyên greenhouse", _pf2.flag(_c2, _pf2.SRC_ATS["greenhouse"]))
    check("KHÔNG đụng tới nhịp quét của tab Chạy",
          _pf2.num(_c2, _pf2.SCAN_EVERY, 5, 1440) == 45,
          str(_pf2.num(_c2, _pf2.SCAN_EVERY, 5, 1440)))
    post("/settings", b"phan=nguon&ats=greenhouse&ats=lever&ats=ashby")
    check("bật lại được", _pf2.flag(_c2, _pf2.SRC_ATS["ashby"]))
    _c2.close()

    # Ba núm — và ĐÚNG ba. Trang cũ có 18 dòng mà chỉ 2 dòng là setting thật.
    for name in ("every", "from", "to"):
        check(f"có ô {name}", f"name={name}" in panel)
    check("có nút Lưu", "Lưu" in panel)
    check("nói rõ hậu quả: chỉ đổi CÁCH CHẠY, không đụng phán quyết",
          "lần quét sau" in panel and "không đụng" in panel)
    # Số máy tự báo về mình KHÔNG phải cài đặt -> phải ở tab khác với mấy núm
    # chỉnh được, không chỉ là một mục dưới cùng cùng màn.
    _tab_chay = panel.split("data-pane='xem'")[0]
    check("số máy tự báo tách sang tab khác, không lẫn với núm chỉnh",
          "strow" not in _tab_chay and "data-pane='xem'" in panel)
    check("việc phá huỷ cũng ở tab riêng", "data-pane='lam-lai'" in panel)
    # MỘT số đệm cho cả tấm phủ. Trước đây mỗi khối tự đặt (0 / 15px / 18px)
    # nên tiêu đề CÀI ĐẶT dính đúng góc khung còn hàng dưới thì thụt vào.
    _cssp = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    check("đệm tấm phủ khai MỘT chỗ", "--sheet-pad:18px" in _cssp)
    for _ten, _r in (("tiêu đề", ".sheethead{"), ("hàng tab", ".stabs{"),
                     ("khối nội dung", ".stpane{"), ("form", ".setform{"),
                     ("hàng nút xoá", ".dangerrow{")):
        _blk = _cssp[_cssp.index("\n" + _r) + 1:]
        _blk = _blk[:_blk.index("}")]
        check(f"{_ten} dùng chung đệm đó, không tự đặt số",
              "var(--sheet-pad)" in _blk or "padding:0" in _blk, _blk[:70])

    # Núm "Máy LLM" ĐÃ BỎ cùng cả đường sinh đề bài bằng LLM. Đề bài giờ do
    # khuôn dựng, nên núm đó không điều khiển gì — mà một cái nút không điều
    # khiển gì còn tệ hơn không có nút: người dùng bấm rồi tưởng app hỏng.
    check("không còn núm giả nào trong Cài đặt",
          "name=engine" not in panel and "JOBBOT_LLM" not in panel)

    print("\n[Cài đặt: lưu xong phải ĂN NGAY, không cần mở lại app]")
    from jobbot.core.scheduler import scan_every_min, human_window
    before = scan_every_min()
    body = b"every=25&from=9&to=21"
    req = urllib.request.Request(base.rstrip("/") + "/settings", data=body)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=25) as r:
        saved = r.read().decode("utf-8")
    check("lưu xong trả lại mảnh có giá trị MỚI", "value='25'" in saved)
    # Đọc lúc chạy, không phải lúc nạp module — nếu không thì đổi nhịp xong
    # phải khởi động lại app mới ăn.
    check("nhịp quét đổi ngay trong tiến trình", scan_every_min() == 25)
    check("khung giờ cũng vậy", human_window() == (9, 21))

    # Người dùng gõ gì cũng không được làm chết vòng quét nền.
    for junk in (b"every=abc&from=x&to=y",
                 b"every=-5&from=99&to=-1"):
        req = urllib.request.Request(base.rstrip("/") + "/settings", data=junk)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()
        low, high = human_window()
        check(f"giá trị rác {junk[:14].decode():14} -> vẫn hợp lệ",
              5 <= scan_every_min() <= 1440 and 0 <= low <= 23 and 1 <= high <= 24)

    req = urllib.request.Request(base.rstrip("/") + "/settings",
                                 data=f"every={before}&from=8&to=22".encode())
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    urllib.request.urlopen(req, timeout=25).read()

    print("\n[gập thanh bên]")
    _, home_html = get("/")
    check("có nút gập", "data-nav" in home_html)
    # Đọc localStorage phải nằm trong <head>, TRƯỚC khi vẽ. Để cuối trang thì
    # mỗi lần chuyển tab thanh bên bung ra rồi mới co lại — nháy một cái.
    head = home_html.split("</head>")[0]
    check("đọc lựa chọn ngay trong <head>, không nháy", "navmin" in head)
    check("và trước cả <body>", "navmin" not in home_html.split("<body>")[1][:200]
          or home_html.index("navmin") < home_html.index("<body>"))
    import re as _re2
    _navlinks = _re2.findall(r"<a class='navlink[^>]*>", home_html)
    check("mọi mục nav có title để lúc gập còn biết là gì",
          bool(_navlinks) and all("title=" in a for a in _navlinks),
          f"{sum('title=' not in a for a in _navlinks)}/{len(_navlinks)} thiếu")
    # navfoot ở thanh bên ĐÃ BỎ: nó hiện đúng thông tin mà thanh trạng thái
    # đáy app đang hiện — hai chỗ một sự thật thì có ngày lệch nhau.
    _, _with_status = get("/profile")
    check("thanh trạng thái nằm ở ĐÁY APP, không trong thanh bên",
          "class=statusbar" in _with_status and "class=navfoot" not in _with_status)

    print("\n[thanh của KHÚC — một khối cho mọi chức năng]")
    _, _srch = get("/search")
    check("Search có thanh khúc", "<header class=topbar>" in _srch)
    check("có nút Chạy của riêng nó", "/api/stage/start" in _srch)
    check("có nút Dừng của riêng nó", "/api/stage/stop" in _srch)
    check("nút chạy/dừng mang tên khúc", "data-arg='search'" in _srch)
    check("có nút Điều chỉnh ⚟", "data-settings='/adjust/search'" in _srch)
    check("có số liệu, không phải câu văn", _srch.count("class='metric ") >= 3)
    # MÀU MANG NGHĨA. Mỗi số phải khai VAI, vì vai mới quyết định màu; không
    # khai thì số nào cũng trắng như nhau và thanh điều khiển lẫn vào nội dung.
    for _vai in ("stock", "act", "new", "view"):
        check(f"số liệu khai vai '{_vai}'", f"class='metric {_vai}" in _srch)
    # Luật SỐ 0 KHÔNG SÁNG — thử thẳng vào hàm, không phụ thuộc dữ liệu thật.
    from jobbot.dashboard.layout import deck as _deck
    _d0 = _deck("search", "S", "", [("0", "mới", "new")])
    _d9 = _deck("search", "S", "", [("9", "mới", "new")])
    check("số 0 bị tắt màu", "metric new zero" in _d0)
    check("số khác 0 thì giữ màu", "zero" not in _d9)
    check("dấu phẩy nghìn không làm hỏng luật",
          "zero" not in _deck("search", "S", "", [("1,204", "giữ", "stock")]))
    # NÚT CHẠY PHẢI ĐỔI CHỮ THEO TÌNH HUỐNG. Một nút ghi "Chạy" ở mọi hoàn
    # cảnh là nút không nói gì: người mới mở app không biết chạy cái gì, người
    # vừa bấm Dừng giữa chừng tưởng bấm vào là làm lại từ đầu.
    from jobbot.dashboard import live as _lv
    from jobbot.core.postings import HAVE_DESC as _HD
    # Nút CHỈ NÓI VỀ CHROME. Board API xong trong 22 giây và chạy mọi lượt —
    # không có trạng thái gì để kể; thứ mất nửa tiếng và dở dang được là
    # LinkedIn.
    _trong = db.connect(Path(tmp) / "nut-trong.db")
    check("chưa có gì -> nút mời CHẠY",
          _lv.search_stage(_trong)["run_label"] == "Chạy",
          _lv.search_stage(_trong)["run_label"])
    # Và nói thẳng vì sao chưa quét được, thay vì mời một việc sẽ bị từ chối.
    check("hồ sơ rỗng -> nói rõ thiếu chức danh",
          "chưa khai chức danh" in _lv.search_stage(_trong)["run_note"],
          _lv.search_stage(_trong)["run_note"])
    _trong.close()

    _nut = seeded(Path(tmp) / "nut.db")
    # Kho có tin (board đã về) nhưng LinkedIn chưa quét trọn lượt nào -> vẫn
    # là CHẠY. "Cập nhật" ở đây là sai: hỏi cửa sổ 24 giờ thì bỏ sót sạch
    # những gì LinkedIn đang có.
    check("board đã về nhưng LinkedIn chưa quét -> vẫn CHẠY",
          _lv.search_stage(_nut)["run_label"] == "Chạy",
          _lv.search_stage(_nut)["run_label"])

    import json as _js3
    from jobbot.core import postings as _po, prefs as _pf3
    from jobbot.scan_runner import _cap as _capf
    from jobbot.profile import store as _ps3
    _po.record_run(_nut, "linkedin", ok=True, fetched=1, new_rows=0)
    # Có dòng chạy thôi CHƯA đủ: lượt đó có thể bị dừng giữa chừng, mới đi
    # được vài cặp đầu. Trí nhớ là DANH SÁCH CẶP, không phải một cái cờ.
    check("có dòng chạy nhưng chưa phủ cặp nào -> vẫn CHẠY",
          _lv.search_stage(_nut)["run_label"] == "Chạy",
          _lv.search_stage(_nut)["run_label"])

    def _phu_het(conn):
        """Đánh dấu MỌI cặp của lưới hiện tại là đã quét đầy."""
        cap, muc = _capf(_ps3.load(conn))
        _pf3.put(conn, _pf3.LI_DONE,
                 _js3.dumps(sorted(f"{q}|{p}" for q, p in cap)))
        _pf3.put(conn, _pf3.LI_LEVELS, _js3.dumps(sorted(muc)))

    _phu_het(_nut)
    check("phủ hết lưới, không còn việc dở -> CẬP NHẬT",
          _lv.search_stage(_nut)["run_label"] == "Cập nhật",
          _lv.search_stage(_nut)["run_label"])
    check("và Cập nhật chỉ hỏi cửa sổ 24 giờ",
          "24 giờ" in _lv.search_stage(_nut)["run_note"])

    # THÊM chức danh -> chỉ MẤY CẶP MỚI là chưa phủ. Không bắt cả lưới quét
    # lại: đó đúng là "chạy đi chạy lại một thứ".
    _ps3.save(_nut, {"job_titles": "Quantitative Analyst\nData Scientist\n"
                                   "Machine Learning Engineer"}, "thêm chức danh")
    from jobbot.scan_runner import scan_mode as _sm
    _st_them = _lv.search_stage(_nut)
    check("thêm chức danh -> quay về CHẠY", _st_them["run_label"] == "Chạy",
          _st_them["run_label"])
    check("nhưng CHỈ quét đầy mấy lượt mới, không quét lại cả lưới",
          _sm(_nut)["todo"] == 1, str(_sm(_nut)["todo"]))
    check("và nói rõ phần còn lại chỉ hỏi tin mới",
          "phần còn lại chỉ hỏi tin mới" in _st_them["run_note"],
          _st_them["run_note"])

    # BỎ BỚT chức danh -> KHÔNG có gì mới để tìm -> đừng quét lại cái gì cả.
    # Đây là chỗ luật cũ (vân tay cả lưới) sai: nó bắt quét lại từ đầu.
    _phu_het(_nut)
    _ps3.save(_nut, {"job_titles": "Quantitative Analyst"}, "bỏ bớt chức danh")
    check("bỏ bớt chức danh -> vẫn CẬP NHẬT, không quét lại",
          _lv.search_stage(_nut)["run_label"] == "Cập nhật",
          _lv.search_stage(_nut)["run_label"])

    # Sửa thứ KHÔNG đụng câu hỏi gửi LinkedIn thì đừng bắt quét lại.
    _ps3.save(_nut, {"phone": "+44 7000 000000"}, "đổi số điện thoại")
    check("đổi số điện thoại -> vẫn CẬP NHẬT",
          _lv.search_stage(_nut)["run_label"] == "Cập nhật",
          _lv.search_stage(_nut)["run_label"])

    # THU HẸP cấp bậc không đẻ ra tin mới -> giữ nguyên phủ.
    _ps3.save(_nut, {"seniority": ["grad"]}, "thu hẹp cấp bậc")
    check("thu hẹp cấp bậc -> vẫn CẬP NHẬT",
          _lv.search_stage(_nut)["run_label"] == "Cập nhật",
          _lv.search_stage(_nut)["run_label"])
    # NỚI RỘNG thì f_E đổi cho MỌI cặp -> phải hỏi đầy lại.
    _ps3.save(_nut, {"seniority": ["grad", "mid", "senior"]}, "nới cấp bậc")
    check("nới rộng cấp bậc -> quay về CHẠY",
          _lv.search_stage(_nut)["run_label"] == "Chạy",
          _lv.search_stage(_nut)["run_label"])
    _ps3.save(_nut, {"seniority": ["grad", "junior"],
                     "job_titles": "Quantitative Analyst\nData Scientist"}, "trả lại")
    _phu_het(_nut)
    # Một tin LinkedIn chưa có mô tả = vòng đọc kỹ còn dở dang. Ghi bằng
    # ĐƯỜNG THẬT của app (save_batch) chứ không INSERT tay: bảng posting có
    # cột bắt buộc mà chỉ đường thật mới điền đủ, và test đi đường riêng thì
    # nó kiểm một hình dạng dữ liệu không bao giờ tồn tại ngoài đời.
    postings.save_batch(_nut, "linkedin", [
        Posting(source_id="9", title="Quant", company="X", location="London",
                url="https://x/9", description="")])
    # kept=1: tin LỌT LƯỚI nhưng chưa kịp đọc kỹ. Đó mới là "việc dở" thật.
    # Tin lưới sàng đã loại thì đọc bao nhiêu lần cũng không ai dùng tới, nên
    # không được tính vào con số trên nút.
    _nut.execute("UPDATE posting SET kept = 1 WHERE source = 'linkedin'")
    _nut.commit()
    _st = _lv.search_stage(_nut)
    check("còn tin chưa đọc kỹ -> nút mời TIẾP TỤC",
          _st["run_label"] == "Tiếp tục", _st["run_label"])
    check("và nói rõ còn bao nhiêu tin dở", "1 tin chưa đọc kỹ" in _st["run_note"])

    # HÀNG ĐỢI THEO NGUỒN, KHÔNG PHẢI MỘT RỔ. Tin dở ở đây là của nguồn
    # `linkedin`; tắt nguồn đó thì hàng đợi của nó không phải việc của lượt
    # này, nên nút không được mời "Tiếp tục" — bấm vào sẽ không đọc tin nào.
    _pf3.set_flag(_nut, _pf3.SRC_LINKEDIN, False)
    _st_tat = _lv.search_stage(_nut)
    check("tắt LinkedIn -> hàng đợi CỦA NÓ không còn mời Tiếp tục",
          _st_tat["run_label"] != "Tiếp tục", _st_tat["run_label"])
    check("và nói rõ lượt tới chỉ còn nguồn nào",
          "LinkedIn đang tắt" in _st_tat["run_note"], _st_tat["run_note"])
    check("KHÔNG còn đòi bật LinkedIn để đọc tin nguồn khác",
          "cần bật LinkedIn" not in _st_tat["run_note"], _st_tat["run_note"])

    # Nhưng tin của THƯ BÁO là nguồn KHÁC, công tắc KHÁC. LinkedIn tắt thì nó
    # vẫn phải đi trọn dây chuyền: "2 cách khác nhau phải làm 2 nguồn khác
    # nhau, đừng gộp chung". Trước đây cả vòng đọc kỹ nằm sau công tắc
    # LinkedIn, nên tắt nó là 107 tin thư báo đứng im không ai chấm.
    postings.save_batch(_nut, "alert", [
        Posting(source_id="8", title="Quant", company="Y", location="London",
                url="https://x/8", description="")])
    _nut.execute("UPDATE posting SET kept = 1 WHERE source = 'alert'")
    _nut.commit()
    _st_thu = _lv.search_stage(_nut)
    check("LinkedIn tắt mà thư báo còn tin dở -> VẪN mời Tiếp tục",
          _st_thu["run_label"] == "Tiếp tục", _st_thu["run_label"])
    check("và chỉ đếm tin của nguồn đang bật, không đếm cả rổ",
          "1 tin chưa đọc kỹ" in _st_thu["run_note"], _st_thu["run_note"])
    _pf3.set_flag(_nut, _pf3.SRC_ALERT, False)
    check("tắt luôn thư báo -> không còn hàng đợi nào để mời",
          _lv.search_stage(_nut)["run_label"] != "Tiếp tục")
    _pf3.set_flag(_nut, _pf3.SRC_ALERT, True)
    _nut.execute("DELETE FROM posting WHERE source = 'alert'")
    _nut.execute("DELETE FROM raw_posting WHERE source = 'alert'")
    _nut.commit()
    _pf3.set_flag(_nut, _pf3.SRC_LINKEDIN, True)
    check("bật lại thì mời Tiếp tục như cũ",
          _lv.search_stage(_nut)["run_label"] == "Tiếp tục")
    # Đọc xong tin đó thì lời mời phải đổi lại — nếu không, nút đứng ở
    # "Tiếp tục" vĩnh viễn và chữ trên nút thành lời nói dối.
    _nut.execute("UPDATE posting SET description = ? WHERE source='linkedin'",
                 ("x" * (_HD + 1),))
    _nut.commit()
    _phu_het(_nut)
    check("đọc kỹ xong thì quay về CẬP NHẬT",
          _lv.search_stage(_nut)["run_label"] == "Cập nhật",
          _lv.search_stage(_nut)["run_label"])
    # Tin lưới sàng ĐÃ LOẠI mà thiếu mô tả thì KHÔNG phải việc dở — vòng đọc
    # kỹ không bao giờ mở chúng. Đếm cả chúng thì nút hứa 1.855 trong khi
    # việc thật là 11, đo được trên kho thật ngày 12/09.
    postings.save_batch(_nut, "linkedin", [
        Posting(source_id="8", title="Rác", company="Y", location="Mars",
                url="https://x/8", description="")])
    _nut.execute("UPDATE posting SET kept = 0 WHERE source='linkedin'"
                 " AND url = 'https://x/8'")
    _nut.commit()
    check("tin lưới đã loại KHÔNG được tính là việc dở",
          _lv.search_stage(_nut)["run_label"] == "Cập nhật",
          _lv.search_stage(_nut)["run_label"])
    _nut.close()
    # Chữ lúc rảnh phải đi kèm nút, để live.js trả về được sau khi hiện
    # "Đang quét…". Không có nó thì quét xong nút kẹt ở chữ tạm.
    check("nút mang theo chữ gốc để khôi phục",
          "data-run='Cập nhật'" in _deck("search", "S", "", [], run="Cập nhật"))
    check("và mang lời giải thích khi rê chuột",
          "title='còn 3 tin dở'" in _deck("search", "S", "", [],
                                          run="Tiếp tục", run_note="còn 3 tin dở"))

    # Ô TÌM TRONG KHO. Backend nhận `q` từ ngày đầu — lọc theo chức danh hoặc
    # tên công ty, ràng buộc tham số đàng hoàng — mà chưa bao giờ có chỗ gõ
    # vào. Cả một bộ lọc nằm đó không ai dùng được.
    import re as _re2
    _, _s0 = get("/search")
    check("danh sách có ô tìm", "class=jfind" in _s0)
    check("ô tìm là form GET — gõ xong là ra URL lưu được",
          "method=get action='/search'" in _s0)
    check("chưa tìm thì KHÔNG hiện nút xoá", "jfindx" not in _s0)

    _, _s1 = get("/search?q=quantitative")
    check("tìm rồi thì ô giữ lại chữ vừa gõ", "name=q value='quantitative'" in _s1)
    check("và hiện nút xoá để quay lại", "jfindx" in _s1)
    check("danh sách co lại theo chữ tìm",
          _s1.count("class='jrow") < _s0.count("class='jrow"),
          f"{_s1.count(chr(39) + 'jrow')} vs {_s0.count(chr(39) + 'jrow')}")
    check("tìm chữ không có thật -> nói rõ không ra CÁI GÌ",
          "khongcochunaynhuvay" in get("/search?q=khongcochunaynhuvay")[1])

    # GÕ TÌM KHÔNG ĐƯỢC LÀM MẤT BỘ LỌC ĐANG BẬT. Form GET chỉ gửi đúng những
    # ô nó có, nên các chip phải đi theo dưới dạng <input hidden>.
    _, _s2 = get("/search?q=quant&chance=likely&show=dropped")
    check("bộ lọc đang bật đi theo form dưới dạng ô ẩn",
          "name='chance' value='likely'" in _s2 and "name='show' value='dropped'" in _s2)
    check("nhưng KHÔNG mang theo chính chữ tìm (ô nhập lo việc đó)",
          "name='q' value=" not in _s2)
    from jobbot.dashboard.filters import JobFilter as _JF
    _f = _JF(q="abc", chance="likely", page=3)
    check("pairs() bỏ được q và page khi dựng ô ẩn",
          dict(_f.pairs(q="", page="")) == {"chance": "likely"},
          str(_f.pairs(q="", page="")))
    check("url() và pairs() dựng từ CÙNG một chỗ",
          "chance=likely" in _f.url() and "q=abc" in _f.url())

    # BỐN LOẠI NÚT, BỐN CÁCH VẼ. Trước đây cả bốn là pill xám giống hệt nhau
    # trộn chung ba hàng — 20 nút, không nhìn ra nút nào liên quan nút nào.
    _, _f0 = get("/search")
    check("thứ CÓ THỨ TỰ vẽ thành THANH, không phải pill rời",
          _f0.count("class=lvltrack") == 2, str(_f0.count("class=lvltrack")))
    check("thanh có tên đứng đầu (Cơ hội / Điểm)",
          "Cơ hội" in _f0 and "class=lvlname" in _f0)
    # Xếp KHÔNG lọc gì cả, nên nó phải có nhãn riêng và đứng ở ĐẦU KIA của
    # hàng — lẫn vào giữa đám chip lọc thì người dùng tưởng nó cũng cắt bớt
    # danh sách.
    check("Xếp theo có nhãn riêng", "Xếp theo" in _f0 and "class=vlabel" in _f0)
    # Hàng nút chia hai NHÓM, một đẩy trái một đẩy phải: ô này rộng gần
    # 2000px, nép hết vào mép trái thì nửa màn hình bỏ không.
    check("mỗi hàng nút có hai đầu", _f0.count("class=vgrp") == 6,
          str(_f0.count("class=vgrp")))
    check("ba hàng nút, không phải bốn", _f0.count("class=vbar") == 3,
          str(_f0.count("class=vbar")))

    # TÔ ĐẦY TỚI NẤC ĐANG CHỌN — đó là thứ làm nó đọc ra một cái thang.
    _, _f1 = get("/search?chance=possible")
    # `.*?` chứ không phải `[^<]*`: nút giờ mang thêm <b>số tin</b> bên trong,
    # và ý của test này là kiểm LỚP CSS chứ không phải chữ bên trong nút.
    _nac = _re2.findall(r"<a class='(lvlstep[^']*)'[^>]*>(.*?)</a>", _f1)[:4]
    check("nấc đã qua được tô", [c for c, _ in _nac] ==
          ["lvlstep on", "lvlstep on", "lvlstep on now", "lvlstep"], str(_nac))
    check("đúng một nấc là nấc đang chọn",
          sum(1 for c, _ in _nac if "now" in c) == 1)

    # THANG = SÀN. Chọn "Có thể" phải KÈM cả "Đáng nộp" — giấu mất những tin
    # tốt nhất là hỏng đúng việc người dùng cần.
    _n = lambda h: int(_re2.search(r">Giữ ([0-9,]+)<", h).group(1).replace(",", ""))
    # Bất biến của một cái SÀN: nâng sàn lên thì tập kết quả chỉ co lại, không
    # bao giờ phình ra. (Bao nhiêu tin ở mỗi mức là chuyện của DỮ LIỆU, nên
    # không khẳng định co THẬT SỰ ở đây — test_filters.py kiểm phần SQL.)
    _cao, _vua, _het = (_n(get("/search?chance=likely")[1]), _n(_f1), _n(_f0))
    check("nâng sàn thì tập kết quả chỉ co lại",
          _cao <= _vua <= _het, f"{_cao} <= {_vua} <= {_het}")

    # CÔNG TẮC NGUỒN. Hai cách tìm cho ra hai loại tin khác hẳn nhau — board
    # xong trong 22 giây, LinkedIn mất nửa tiếng — nên có lúc chỉ chạy một cái.
    _, _adj = get("/adjust/search")
    check("tấm Điều chỉnh có hai công tắc nguồn",
          "data-arg='board'" in _adj and "data-arg='linkedin'" in _adj)
    check("công tắc nằm NGOÀI form lưới sàng — bấm không phán lại 5.000 tin",
          _adj.index("srcrow") < _adj.index("<form class=sieve"))
    _bat = lambda arg: __import__("json").loads(
        _post_raw("/api/source", f"arg={arg}".encode()))
    check("có đủ BA công tắc nguồn",
          all(f"data-arg='{k}'" in _adj for k in ("board", "linkedin", "alert")))
    _tat = _bat("board")
    check("tắt được một nguồn", _tat["ok"] and _tat["on"] is False)
    check("nút bấm lại được ngay, không bị khoá", _tat.get("again") is True)
    check("và tấm Điều chỉnh hiện ra là đang tắt",
          "srcbtn board off" in get("/adjust/search")[1])
    # TẮT NỐT CÁI CUỐI = quét mà không lấy ở đâu cả. Đường đó không được là
    # đường bấm nhầm một cái là vào.
    #
    # Luật phải đếm CẢ BA nguồn còn lại. Bản cũ chỉ biết hai nguồn nên khi có
    # nguồn thứ ba, nó cho tắt sạch mà vẫn tưởng còn.
    # Đặt trạng thái RÕ RÀNG trước khi thử: một bài test bên trên đã lưu tab
    # Nguồn không tick "alert", nên không đoán được cái nào đang bật.
    _adj2 = get("/adjust/search")[1]
    for _k in ("linkedin", "alert"):
        if f"srcbtn {_k} off" in _adj2:
            _bat(_k)                      # bật lên cho chắc
    _bat("linkedin")                      # giờ chỉ còn alert
    _cuoi = _bat("alert")
    check("còn đúng một nguồn thì KHÔNG cho tắt nốt", _cuoi["ok"] is False,
          str(_cuoi))
    check("và nói rõ vì sao", "ít nhất một nguồn" in _cuoi["note"])
    _bat("linkedin")
    _bat("board")
    check("bật lại được", "srcbtn board off" not in get("/adjust/search")[1])
    check("nguồn lạ thì từ chối", post("/api/source", b"arg=bia") == 400)

    # HUY HIỆU KHÔNG ĐƯỢC ĐỤNG TÊN LỚP CSS KHÁC.
    #
    # LỖI THẬT: đổi `api` -> `board` xong, `<i class='src board'>` thừa hưởng
    # `.board{width:100%;font-size:12.5px}` của BẢNG Quản lí — huy hiệu phình
    # thành một cái hộp to bằng cả dòng. Cùng lớp lỗi .pill và .prow đã dính.
    # Kiểm bằng CSS thật, không bằng mắt: lỗi này không làm hỏng test nào,
    # chỉ nhìn mới thấy.
    _css = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    from jobbot.dashboard.views.search import FOUND_BY as _FB
    _dung = [k for k in _FB
             if _re2.search(r"(?m)^\.%s\b[^,{]*\{" % _re2.escape(k), _css)]
    check("tên huy hiệu không trùng lớp CSS nào khác", not _dung, str(_dung))
    # Bộ kiểm tự chứng minh nó bắt được.
    check("và bộ kiểm này thật sự bắt được",
          bool(_re2.search(r"(?m)^\.trackboard\b[^,{]*\{", _css)))

    # NƠI CHỐN — chữ trên nút lấy từ ô "Where you're based", không đóng cứng.
    check("có hàng lọc theo nơi", "name=loc" in _f0 or "loc=" in _f0)
    check("nút 'Gần tôi' nói rõ gần ĐÂU", "Gần tôi ·" in _f0, "")
    # Nơi ở không CẮT, nó chỉ ƯU TIÊN: "Cả nước" vẫn còn đó để xem hết.
    check("và vẫn có nút xem cả nước", "Cả " in _f0)
    # Chưa khai nơi ở thì GIẤU nút "Gần tôi": một nút không lọc được gì là
    # nút bấm vào thấy y nguyên, và người dùng thôi tin cả hàng nút.
    from jobbot.dashboard.views import search as _sv
    _trong = _sv._noi(_lv.JobFilter.from_query({}) if hasattr(_lv, "JobFilter")
                      else __import__("jobbot.dashboard.filters", fromlist=["x"])
                      .JobFilter.from_query({}), "", "UK")
    check("chưa khai nơi ở -> giấu luôn nút 'Gần tôi'", "Gần tôi" not in _trong)
    _n2 = lambda h: int(_re2.search(r">Giữ ([0-9,]+)<", h).group(1).replace(",", ""))
    _, _gan = get("/search?loc=near")
    check("lọc 'gần tôi' thì danh sách hẹp lại, không rỗng",
          0 < _n2(_gan) <= _n2(_f0), f"{_n2(_gan)} / {_n2(_f0)}")
    check("và 'cả nước' rộng hơn 'gần tôi'",
          _n2(get("/search?loc=home")[1]) >= _n2(_gan))

    # TAG NGUỒN — Vin nhìn thấy badge board/linkedin trên từng dòng rồi, nên lọc
    # theo chính hai badge đó là thứ tiếp theo người ta thò tay tìm.
    check("có tag lọc theo nguồn", ">board<" in _f0 and ">linkedin<" in _f0)
    _, _fc = get("/search?found=linkedin")
    check("lọc linkedin thì mọi dòng đều mang badge linkedin",
          _fc.count("class='src linkedin'") >= _fc.count("class='jrow"),
          f"{_fc.count(chr(39)+'src linkedin'+chr(39))} badge / "
          f"{_fc.count(chr(39)+'jrow')} dòng")

    # MỘT nút thay cho hai: "Can't tell" và "Not scorable" là cùng một chồng.
    check("chỉ còn MỘT nút cho tin máy chưa đọc",
          "Máy chưa đọc" in _f0 and "Not scorable" not in _f0
          and "Can't tell" not in _f0)
    # Hai thang đòi máy ĐỌC ĐƯỢC, nút này đòi ngược lại — cùng bật thì danh
    # sách luôn rỗng, nên bấm nút phải thả hai thang về Tất cả.
    check("bấm 'Máy chưa đọc' thì thả hai thang ra",
          "raw=1" in _f1 and "chance" not in
          _re2.search(r"href='([^']*raw=1[^']*)'", _f1).group(1))

    # THANH KHÚC nói về KHO, chip nói về KHUNG NHÌN — đừng trộn. Trộn thì gõ
    # tìm "quant" xong thanh báo "64 giữ · 91 đáng nộp", trong khi đáng nộp là
    # tập con của giữ: 91 > 64 là con số không thể tồn tại.
    import re as _re
    _giu = lambda h: _re.search(
        r"class='metric stock[^']*'><b>([0-9,]+)</b>đáng nộp", h)
    check("thanh khúc giữ nguyên số KHO khi đang tìm — "
          f"{_giu(_s1) and _giu(_s1).group(1)} vs {_giu(_s0) and _giu(_s0).group(1)}",
          bool(_giu(_s1) and _giu(_s0) and _giu(_s1).group(1) == _giu(_s0).group(1)))
    # MỖI SỐ PHẢI HÀNH ĐỘNG ĐƯỢC. Thanh cũ có "363 giữ" cạnh "364 đáng nộp" —
    # hai cách đếm cùng một chồng, gần trùng nhau nên không nói thêm gì; và
    # "50 đang hiện" chỉ là cỡ trang, danh sách ngay dưới đã nói rồi.
    check("bỏ số 'đang hiện' — đó là cỡ trang, không phải tin tức",
          "đang hiện" not in _s0)
    check("có hàng đợi THẬT: điểm cao mà chưa nộp", "nên nộp" in _s0)
    check("và số đó mang vai HÀNH ĐỘNG (xanh), không phải số nền",
          _re.search(r"class='metric act[^']*'><b>[0-9,]+</b>nên nộp", _s0))

    # Con số trên chip phải ĐI THEO chữ tìm, không thì nó nói dối.
    import re as _re
    _dem = lambda h, n: int(_re.search(f">{n} ([0-9,]+)<", h).group(1).replace(",", ""))
    check("đếm lại theo chữ tìm, không giữ số cũ",
          _dem(_s1, "Giữ") < _dem(_s0, "Giữ"),
          f"{_dem(_s1, 'Giữ')} vs {_dem(_s0, 'Giữ')}")
    # Chữ người dùng gõ đi thẳng vào câu SQL. Phải là tham số ràng buộc.
    _ma_nhay, _ = get("/search?q=%27%20OR%201%3D1%20--")
    check("dấu nháy trong ô tìm không làm sập trang", _ma_nhay == 200, str(_ma_nhay))

    # GIỮ LẠI tin máy đã loại. Bộ lọc là luật máy móc — riêng "chức danh không
    # khớp" đã loại 2.595 tin trên kho thật, mà luật đó chỉ là so chuỗi con với
    # 19 chức danh khai trong hồ sơ. Người liếc qua đống bị loại chắc chắn nhặt
    # được tin thật, nên phải có đường nhặt.
    _, _bo = get("/search?show=dropped")
    check("dòng bị loại có nút Giữ lại", "Giữ lại" in _bo and "/api/keep" in _bo)
    _, _giu = get("/search")
    check("dòng đang giữ KHÔNG có nút đó — không có gì để giữ thêm",
          "Giữ lại" not in _giu)

    _bo_id = _re2.search(r"data-post='/api/keep' data-arg='(\d+)'", _bo).group(1)
    gui = lambda i: post("/api/keep", f"arg={i}".encode())
    check("bấm Giữ thì server nhận", gui(_bo_id) == 200)
    _, _sau = get("/search")
    check("tin đó chuyển sang danh sách giữ", f"/jobs/{_bo_id}" in _sau)
    check("và nói rõ nó nằm đây vì NGƯỜI, không phải vì máy chấm đạt",
          "bạn giữ" in _sau)
    check("nút đổi chiều thành Bỏ giữ", "Bỏ giữ" in _sau)
    check("không còn nằm bên danh sách bị loại",
          f"/jobs/{_bo_id}" not in get("/search?show=dropped")[1])
    check("bấm lần nữa thì trả về cho máy", gui(_bo_id) == 200
          and f"/jobs/{_bo_id}" in get("/search?show=dropped")[1])
    check("id bịa thì từ chối, không đổi gì", gui("khong-phai-so") == 400)

    # NỘP KHÔNG ĐỨNG Ở DANH SÁCH. Nộp là một quyết định — mở Chrome, điền
    # form, ghi một dòng vào Quản lí — nên nó phải đứng SAU khi đọc. Chỗ đọc
    # là trang chi tiết: có điểm từng yêu cầu, bằng chứng, và đường sang tin
    # gốc. Bấm nộp từ danh sách là nộp mù.
    check("dòng việc KHÔNG có nút Nộp", "/api/apply" not in _giu)
    check("nhưng trang chi tiết thì có",
          "data-post='/api/apply'" in get(f"/jobs/{job_id}")[1])
    # Giữ lại thì NGƯỢC LẠI: sàng đống bị loại là việc lướt, quét mắt qua hàng
    # chục dòng. Bắt mở từng trang chi tiết là giết luôn việc sàng.
    check("nhưng Giữ lại thì vẫn ở danh sách — đó là việc lướt, không phải đọc",
          "/api/keep" in _bo)

    # MỖI TIN PHẢI CÓ ĐƯỜNG SANG TIN GỐC. Trang chi tiết hiện điểm, hiện từng
    # yêu cầu, hiện cả bản mô tả — mà không có đường nào sang xem tin thật thì
    # cả trang đó là lời kể lại: mô tả trong kho là bản chụp lúc quét, tin thật
    # có thể đã sửa hoặc đã đóng.
    _jid = str(job_id)
    _ma, _ct = get(f"/jobs/{_jid}")       # get() trả (mã, thân), không phải chuỗi
    check("trang chi tiết mở được", _ma == 200, str(_ma))
    check("trang chi tiết có ô Mở tin gốc", "Mở tin gốc" in _ct)
    # KHÔNG ĐƯỢC CÓ NÚT VẼ. Mọi trình nghe trong live.js đều bắt theo data-*,
    # nên một <button> không mang data-* nào là nút bấm vào không có gì xảy ra
    # — và không báo lỗi, nên người dùng tưởng app hỏng. Trang này từng có hai
    # cái: "Queue for approval" và "Reject…".
    import re as _re3
    _chet = [b for b in _re3.findall(r"<button[^>]*>", _ct)
             if "data-" not in b and "type=submit" not in b]
    check("không còn nút nào không nối vào đâu", not _chet, str(_chet[:2]))
    check("và có nút Nộp thật, dùng chung đường với danh sách",
          "data-post='/api/apply'" in _ct)
    check("và có đường THẬT, không phải đường nội bộ",
          "class='jlink" in _ct and "href='https://" in _ct)
    # Trong cửa sổ app không có thanh địa chỉ và không có nút Back: mở đường
    # ngoài ngay trong đó là mất luôn dashboard.
    check("đường ngoài mở ra ngoài, không nuốt mất cửa sổ app",
          "target='_blank'" in _ct and "rel='noopener noreferrer'" in _ct)
    # MỘT VIỆC ĐĂNG HAI NƠI THÌ GẮN CẢ HAI. Chúng không thay nhau: board công
    # ty là chỗ nộp thẳng, LinkedIn có số người đã nộp và tên người đăng.
    from jobbot.dashboard import live as _lv2
    _hai = _lv2._links([("greenhouse:x", "https://boards.greenhouse.io/x/jobs/1"),
                        ("linkedin", "https://www.linkedin.com/jobs/view/9/")],
                       "https://www.linkedin.com/jobs/view/9/")
    check("hai nguồn -> hai đường", len(_hai) == 2, str(_hai))
    check("board công ty đứng TRƯỚC LinkedIn — đó là chỗ nộp thẳng",
          [l["kind"] for l in _hai] == ["board", "linkedin"])
    check("nói rõ tên miền sắp đi tới",
          _hai[1]["host"] == "www.linkedin.com", _hai[1]["host"])
    check("trùng url thì không hiện hai lần",
          len(_lv2._links([("a", "https://x/1"), ("b", "https://x/1")], "https://x/1")) == 1)
    check("url rỗng thì bỏ, không đẻ ra nút chết",
          _lv2._links([("a", "")], "") == [])

    # MỘT viên pill căn giữa, không phải dải kéo hết bề ngang: trên màn 1900px
    # dải đẩy tên khúc sang trái và nút sang phải cách nhau cả gang tay.
    check("có viên thuốc điều khiển", "class=deckpill" in _srch)
    # .pill ĐÃ CÓ SẴN: huy hiệu trạng thái trên bảng Quản lí (.pill.applied,
    # .pill.interview…). Đặt trùng tên là đúng lớp lỗi .frow/.prow đã sửa.
    # Vẽ thẳng view với một dòng mẫu: DB thử không có lần nộp nào nên bảng
    # thật không vẽ huy hiệu, và bài test sẽ xanh mà chẳng kiểm gì.
    from jobbot.dashboard.views import track as _tk
    from jobbot.track import board as _bd2
    _trk = _tk.render(
        rows=[dict(id=1, stage=_bd2.SENT, company="X", role="R", days=1,
                   event_days=None, last_event="", silent=False, cv_file="",
                   posting_id=None, url="", score=0)],
        asks=[], counts={"total": 1}, mail_ready=False, mail_address="")
    check("bảng Quản lí vẫn vẽ huy hiệu .pill", "class='pill " in _trk)
    check("và huy hiệu KHÔNG dính kiểu của viên thuốc",
          "class=deckpill" not in _trk)
    _cssP = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    check("viên thuốc căn giữa", "align-items:center" in _cssP)
    check("viên thuốc bo tròn", ".deckpill{" in _cssP)
    # NẰM NGANG, không bao giờ xếp cao: cho xuống dòng thì màn hẹp nó phình
    # thành khối 211px, hết còn là viên thuốc.
    _pl = _cssP[_cssP.index(".deckpill{"):_cssP.index(".deckpill{") + 320]
    check("viên thuốc KHÔNG xuống dòng", "flex-wrap:nowrap" in _pl)
    # Màn quá hẹp thì cuộn ngang, KHÔNG giấu nút: một nút bấm không tới được
    # thì cũng như không có.
    check("quá hẹp thì cuộn ngang", "overflow-x:auto" in _pl)
    # Tất cả trong MỘT viên: tên khúc, số liệu, nút. Đẩy số liệu ra ngoài thì
    # thanh vỡ thành ba tầng rời rạc.
    _pillhtml = _srch[_srch.index("class=deckpill"):]
    _pillhtml = _pillhtml[:_pillhtml.index("</div>")]
    check("số liệu nằm TRONG viên thuốc", "class=metric" in _pillhtml)
    check("nút cũng trong viên thuốc", "/api/stage/start" in _pillhtml)
    # `nowrap` trần thì màn hẹp là dòng trạng thái chạy quá mép pill rồi bị
    # cắt cụt giữa chữ.

    print("\n[thanh TRẠNG THÁI đáy app]")
    # Tin CHUNG của cả app, không thuộc tab nào. Dòng "tự động: TẮT · quét lần
    # cuối…" trước nằm trong thanh của tab — sai chỗ: nó không phải số liệu của
    # khúc, nó là trạng thái của app.
    for _pg2 in ("/", "/search", "/track", "/profile"):
        _b2 = get(_pg2)[1]
        check(f"{_pg2} có thanh trạng thái", "class=statusbar" in _b2)
    # Thanh trạng thái chạy HẾT bề ngang, kể cả dưới thanh bên — nó là tin của
    # cả app. Kèm đó thanh bên phải chừa chỗ, không thì nút Cài đặt bị che.
    _cssb = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    check("thanh trạng thái tràn hết bề ngang",
          ".statusbar{position:fixed;left:0;right:0" in _cssb)
    check("thanh bên dừng ngay trên thanh trạng thái",
          "bottom:var(--status-h);\n  width:var(--nav-w)" in _cssb)
    # Cửa sổ app không có khung: traffic lights đè lên trang. Có thanh tiêu đề
    # THẬT thì mọi trang tự được chừa — trước đây mỗi trang tự nhớ, và trang
    # Home nhớ sai (chừa 16px trong khi cần 38px) nên ô nội dung chui lên đó.
    for _pg4 in ("/", "/search", "/cv", "/track", "/profile"):
        _, _b4 = get(_pg4)
        check(f"{_pg4} có thanh tiêu đề", "class=titlebar" in _b4)
    check("thanh tiêu đề cao đúng --top", "z-index:40;height:var(--top)" in _cssb)
    check("khung chính bắt đầu DƯỚI thanh tiêu đề",
          "main{position:fixed;top:var(--top);left:var(--main-l)" in _cssb)
    check("thanh bên cũng vậy",
          ".side{position:fixed;top:var(--top);left:var(--gap)" in _cssb)
    # HAI KHUNG, KHÔNG KẺ VẠCH. Thanh tiêu đề và thanh trạng thái không có nền
    # riêng cũng không có viền — chúng LÀ mảng xám của body. Nổi trên mảng đó
    # là HAI khung bo tròn cùng viền --rim: cột nút chuyển tab và vùng làm
    # việc. Ngăn cách là khoảng --gap giữa hai khung, không phải vạch kẻ.
    for _ten, _rule in (("cột nút chuyển tab", "\n.side{"), ("vùng làm việc", "\nmain{")):
        _blk = _cssb[_cssb.index(_rule) + 1:]
        _blk = _blk[:_blk.index("}")]
        check(f"{_ten} là khung bo tròn có viền",
              "border:1px solid var(--rim)" in _blk
              and "border-radius:var(--round)" in _blk, _blk[:90])
    # Xám VIỀN phải tách được khỏi xám KHUNG, không thì đường bo chìm mất.
    _tach = _ls(_var["rim"]) - _ls(_var["side"])
    check(f"xám viền sáng hơn xám khung ({_tach:+.1f} L*)", 6.0 <= _tach <= 15.0)
    check("nền cửa sổ là mảng xám khung", "body{margin:0;background:var(--side)" in _cssb)
    for _ten, _rule in (("thanh tiêu đề", ".titlebar{"), ("thanh trạng thái", ".statusbar{")):
        _blk = _cssb[_cssb.index(_rule):]
        _blk = _blk[:_blk.index("}")]
        check(f"{_ten} không kẻ vạch ngăn", "border" not in _blk, _blk[:70])
        check(f"{_ten} không có nền riêng", "background" not in _blk, _blk[:70])
    check("thanh đáy có ô trạng thái sống", "data-state" in _srch)
    check("và ô tin gần nhất", "data-lastmsg" in _srch)
    # Một trang chỉ được nói trạng thái chung MỘT lần. live.js ghi vào MỌI
    # [data-state], nên hai ô là hai dòng chữ y hệt nhau nằm hai đầu màn.
    for _pg3 in ("/", "/search", "/cv", "/track", "/profile"):
        _, _b3 = get(_pg3)
        check(f"{_pg3} chỉ có một ô trạng thái", _b3.count("data-state") == 1)
    # live.js đổ vào từ dòng SSE — không luồn tham số qua chục hàm render.
    _js2 = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    check("live.js có hàm đổ tin", "function setLastMessage" in _js2)
    check("gọi khi có sự kiện mới", _js2.count("setLastMessage(") >= 3)
    check("nội dung không nấp sau thanh đáy", "var(--status-h)" in _cssP)
    # navfoot cũ hiện đúng thông tin đó ở thanh bên — hai chỗ một sự thật.
    _lay2 = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/layout.py").read_text(encoding="utf-8")
    check("bỏ hẳn navfoot ở thanh bên", "navfoot" not in _lay2)
    check("và bỏ tham số status= đã chết", "status: str" not in _lay2)
    # Hai nút "Chạy ngay"/"Bật tự quét" cũ nằm trên thanh TOÀN APP nhưng chỉ
    # điều khiển đúng khúc Search. Thanh mang danh cả app mà làm việc một khúc.
    check("bỏ hẳn nút toàn app", "data-act=run" not in _srch
          and "data-act=pause" not in _srch)
    # ⚟ dùng LẠI tấm phủ của Cài đặt — mỗi đường mới là một nút có thể chết.
    _cA, _adj = get("/adjust/search")
    check("/adjust/search trả mảnh HTML", _cA == 200 and "Điều chỉnh" in _adj)
    check("và chứa lưới sàng", "/api/sieve" in _adj)
    check("khúc lạ thì 404", get("/adjust/khong-co-that")[0] == 404)
    # Lọc (bấm vài giây một lần) phải ở NGAY trên trang, không giấu vào menu.
    check("bộ lọc vẫn ở trên trang", "?show=" in _srch or "show=" in _srch)

    print("\n[dừng phải dừng THẬT, không phải nút cho có]")
    _run = (Path(__file__).resolve().parent.parent
            / "src/jobbot/scan_runner.py").read_text(encoding="utf-8")
    _li = (Path(__file__).resolve().parent.parent
           / "src/jobbot/ingest/web/linkedin.py").read_text(encoding="utf-8")
    # `stop()` của lịch trình chỉ chặn lần chạy SAU. Một vòng quét chạy 8-16
    # phút vì mở Chrome đọc từng tin — nút Dừng mà không ngắt được là nút chết.
    check("ngắt giữa hai nguồn API", "halt.wanted(STAGE)" in _run)
    check("truyền cờ xuống LinkedIn", "stop=lambda: halt.wanted(STAGE)" in _run)
    check("ngắt trong vòng ĐỌC KỸ (chỗ tốn 8-16 phút)", "đã đọc kỹ" in _li)
    check("ngắt cả trong vòng tìm", "mới xong" in _li)
    _halt = (Path(__file__).resolve().parent.parent
             / "src/jobbot/core/halt.py").read_text(encoding="utf-8")
    # Dừng vòng quét KHÔNG được dừng luôn việc quét thư đang chạy song song.
    check("cờ theo TỪNG khúc, không phải một cờ chung", "stage: str" in _halt)
    _srv = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
    # Thêm một chức năng mới thì không được đẻ thêm route.
    check("hai route dùng chung cho mọi khúc",
          '"/api/stage/start", "/api/stage/stop"' in _srv)
    check("khúc lạ bị từ chối", 'stage not in STAGES' in _srv)

    print("\n[khung không được bỏ phí — MỌI trang, không riêng trang nào]")
    import re as _re9
    _css9 = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    _bare = _re9.sub(r"/\*.*?\*/", "", _css9, flags=_re9.S)

    # Lỗi gốc: `.inner{max-width:840px}` chặn cứng MỌI trang kiểu dòng chảy.
    # Đo trên màn 1900px: khung 1684, nội dung 840 -> bỏ trống 844px, ở BỐN
    # trang cùng lúc. Vá một trang là để ba trang kia y nguyên.
    _inner = _re9.search(r"\.inner\{([^}]*)\}", _bare)
    check("có luật .inner", bool(_inner))
    _mw = _re9.search(r"max-width:([^;}]+)", _inner.group(1)) if _inner else None
    check(".inner KHÔNG còn trần cố định",
          bool(_mw) and _mw.group(1).strip() == "none",
          _mw.group(1).strip() if _mw else "không có max-width")
    # Bề rộng là tính chất của NỘI DUNG: chỉ đoạn văn mới cần bề rộng đọc được.
    check("nhưng đoạn văn vẫn giữ bề rộng đọc được",
          bool(_re9.search(r"\.inner p[^{]*\{[^}]*max-width:\d+ch", _bare)))
    # Cờ `wide=` là nút mà mỗi trang phải NHỚ bật — sẽ có trang quên. Đã bỏ.
    _lay = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/layout.py").read_text(encoding="utf-8")
    check("bỏ hẳn cờ wide (đường dễ quên)", "wide" not in _lay)
    check("và không còn luật CSS .wide", "main.wide" not in _bare)

    # Duyệt THẬT mọi trang trong thanh bên, không chỉ trang vừa sửa.
    _c9, _nav = get("/")
    _pages = set(_re9.findall(r"<a class='navlink[^']*' href='([^']+)'", _nav))
    _pages |= {"/profile/health", "/profile/import", f"/jobs/{job_id}"}
    check("tìm được đủ trang để kiểm", len(_pages) >= 7, str(sorted(_pages)))
    for _pg in sorted(_pages):
        _code, _body = get(_pg)
        if _code != 200:
            check(f"{_pg} mở được", False, f"HTTP {_code}")
            continue
        _m = _re9.search(r"<main class='([^']*)'", _body)
        check(f"{_pg} không mang lớp cố định bề rộng",
              bool(_m) and "wide" not in _m.group(1))

    # Bảng: `width` trên ô chỉ là GỢI Ý khi bảng tự dàn cột — nhãn dài kéo cột
    # ra 650px. Và dàn cột cố định thì Chrome BỎ QUA min()/clamp() (đo được:
    # rơi về 803px), chỉ nhận px hoặc phần trăm.
    check("bảng hồ sơ dàn cột cố định", "table-layout:fixed" in _bare)
    _th = _bare[_bare.index(".sum th{"):_bare.index(".sum th{") + 260]
    check("cột nhãn dùng bề rộng trần, không min()/clamp()",
          "width:340px" in _th and "min(" not in _th and "clamp(" not in _th)
    check("màn hẹp có luật riêng cho cột nhãn", ".sum th{width:40%}" in _bare)

    print("\n[Home KHÔNG còn là trang trống]")
    # Luật cũ ở đây là "Home phải nói mình đang trống". Home giờ là cửa vào và
    # là chu trình dựng hồ sơ, nên luật đảo lại: nó KHÔNG được trống nữa.
    _, _blank = get("/")
    check("Home vẫn mở được", "Home" in _blank)
    check("và không còn là trang trống", "đang trống" not in _blank)
    check("Home nói rõ nó sẽ là gì", "bảng điều khiển pipeline" in _blank)
    # Gỡ nội dung mà để lại đống code nuôi nó thì mới là bẩn.
    for _gone in ("class=funnel", "class=needs", "class=stats", "class=plot"):
        check(f"không còn {_gone}", _gone not in _blank)
    _live8 = (Path(__file__).resolve().parent.parent
              / "src/jobbot/dashboard/live.py").read_text(encoding="utf-8")
    for _fn in ("def run_status", "def counters", "def needs_you", "def activity",
                "def per_day", "def chances", "def funnel"):
        check(f"live.py đã gỡ {_fn[4:]}", _fn not in _live8)
    check("dashboard/plot.py đã xoá",
          not (Path(__file__).resolve().parent.parent
               / "src/jobbot/dashboard/plot.py").exists())

    print("\n[nhật ký: dòng mới nhất phải NHÌN RA NGAY]")
    # "cái message mới nhất cho highlight nổi bật cho dễ nhận biết"
    #
    # Dấu là THUẦN CSS (:first-child), không có class nào để JS gắn — nên
    # không có cách nào dấu đứng lại ở dòng cũ khi dòng mới tới. Nhưng nó
    # dựa vào MỘT ràng buộc: live.js chèn dòng mới vào ĐỈNH. Ai đổi sang
    # chèn xuống đáy là dấu lặng lẽ trỏ vào dòng CŨ NHẤT, mà giao diện vẫn
    # trông bình thường. Nên chốt cả hai đầu ở đây.
    _css_j = (Path(__file__).resolve().parent.parent
              / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    _js_j = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    check("dòng mới chèn vào ĐỈNH — nền tảng của cả luật đánh dấu",
          "insertBefore(row, box.firstChild)" in _js_j)
    check("chỉ MỘT chỗ đẻ ra .jline, nên không có thứ tự ngược nào khác",
          sum(1 for _f in (Path(__file__).resolve().parent.parent
                           / "src/jobbot/dashboard").rglob("*")
              if _f.is_file() and _f.suffix in (".js", ".py")
              and "'jline" in _f.read_text(encoding="utf-8")) == 1)
    check("dòng mới nhất có dấu riêng", ".journal .jline:first-child{" in _css_j)
    check("dấu bằng NỀN, không phải màu chữ",
          "background:rgba(255,255,255,.062)" in _css_j)
    check("và có vạch trái", "border-left-color:var(--mute)" in _css_j)
    # Vạch trái ăn theo MỨC. Nếu dấu mới nhất đè lên màu mức thì người dùng
    # mất thứ cần đọc trước tiên — dòng này là hỏng hay chỉ là tin thường.
    _khit = "".join(_css_j.split())      # bỏ khoảng trắng căn lề trong CSS
    for _m, _mau in (("ok", "--acc"), ("warn", "--warn"), ("error", "--bad")):
        check(f"vạch trái giữ đúng màu mức {_m}",
              f".journal.jline.{_m}:first-child{{border-left-color:var({_mau})}}"
              in _khit)
    check("KHÔNG đổi màu chữ của ok/warn/error — mức độ không được nói dối",
          not any(f".journal .jline.{_m}:first-child .jtext{{color" in _css_j
                  for _m in ("ok", "warn", "error")))
    # Mọi dòng có sẵn vạch trong suốt -> dấu chuyển sang dòng khác thì không
    # dòng nào bị đẩy ngang một nấc.
    check("mọi dòng chừa sẵn chỗ cho vạch, không dòng nào nhảy ngang",
          "border-left:2px solid transparent" in _css_j)
    check("loé một cái lúc vừa tới", "@keyframes jnew" in _css_j)
    check("nhưng tôn trọng máy đã tắt hiệu ứng",
          "prefers-reduced-motion" in _css_j)

    print("\n[Search: ba ô — danh sách · lưới lọc · nhật ký dẹt]")
    from jobbot.dashboard.views.runtime import _rows_needed
    check("đếm hàng: nhật ký dưới đáy nên không có ô 'Đang chạy' hàng 1",
          _rows_needed([("a", "", 1, 4), ("b", "", 2, 4)], 3, 0) == 4)

    _, search_html = get("/search")
    _, adj_html = get("/adjust/search")
    check("ô danh sách việc", "Việc tìm được" in search_html)
    check("ô nhật ký dạng dẹt", "class=jflat" in search_html)
    check("tiến độ gộp vào dải nhật ký", "data-progress='search'" in search_html)
    # Lưới sàng đã chuyển vào ⚟ nên cột trái hết việc: danh sách — thứ Vin
    # thật sự đọc — lấy cả bề ngang, nhật ký về dải dẹt dưới đáy.
    check("danh sách ăn cả bề ngang", "Lưới lọc" not in search_html)
    check("nhật ký là dải dưới đáy, không phải ô góc",
          "wid flat corner" not in search_html)

    # Lưới sàng phải SỬA ĐƯỢC — và giờ nó nằm sau nút ⚟, không chiếm chỗ
    # thường trực trên trang. LỌC thì vẫn ở trên trang (bấm vài giây một lần);
    # SÀNG đổi vài tháng một lần và mỗi lần là phán lại toàn kho.
    check("lưới sàng là FORM thật", "form class=sieve" in adj_html)
    check("và KHÔNG còn chiếm chỗ trên trang", "form class=sieve" not in search_html)
    # Chức danh là Ô THẺ, không phải khối chữ: gõ rồi Enter là thêm, bấm ×
    # là bỏ. Khối chữ bắt người dùng tự nhớ luật "mỗi dòng một cái", và một
    # dòng trống hay dấu phẩy thừa là ra chức danh rác.
    check("chức danh là ô thẻ, KHÔNG phải khối chữ",
          "class=tagbox" in adj_html and "<textarea" not in adj_html)
    n_tags = adj_html.count("<span class=tag>")
    check("có ít nhất một thẻ", n_tags > 0)
    check("mỗi thẻ có đúng một dấu × để bỏ",
          adj_html.count("data-untag") == n_tags)
    check("mỗi thẻ mang đúng một giá trị gửi lên",
          adj_html.count("name=job_titles") == n_tags)
    check("nút × là type=button, không gửi nhầm cả form",
          "<button type=button class=untag" in adj_html)
    check("có ô để gõ thêm", "class=taginput" in adj_html)
    check("có ô tích cấp bậc và thị trường",
          "name=seniority" in adj_html and "name=markets" in adj_html)
    check("có nút Áp dụng", "Áp dụng" in adj_html)
    # Nút phải nói TRƯỚC hậu quả, không phải "Lưu" trống không.
    check("nút nói rõ sẽ phán lại bao nhiêu tin", "phán lại" in adj_html)
    check("và nói rõ đây là hồ sơ, sửa là đổi cả điểm",
          "hồ sơ" in adj_html and "đổi cả điểm" in adj_html)

    # Nút XEM tách khỏi lưới: bấm là đổi ngay, không qua Áp dụng.
    check("nút XEM là link, không nằm trong form",
          "class='vchip" in search_html
          and search_html.index("class=jlist") > search_html.index("class=vbar"))
    check("nút XEM trỏ về /search, không phải /jobs đã xoá",
          "href='/search?" in search_html and "href='/jobs?" not in search_html)

    # Badge nguồn — thứ nói cách nào tìm ra tin nào.
    check("mỗi dòng có badge nguồn",
          "class='src board'" in search_html or "class='src linkedin'" in search_html)
    check("badge ghi rõ chữ chrome / api",
          ">board<" in search_html or ">linkedin<" in search_html)

    print("\n[Search: đổi cách xem KHÔNG cần Áp dụng]")
    _, dropped = get("/search?show=dropped")
    check("xem được tin đã bỏ", "bỏ vì" in dropped)
    check("và kèm lý do bỏ thật",
          "title does not match" in dropped or "senior level" in dropped)
    for q in ("?show=all", "?chance=likely", "?via=all", "?band=75",
              "?sort=company", "?q=%27%20OR%201%3D1--", "?page=99"):
        code, body = get("/search" + q)
        check(f"/search{q:24} {code}", code == 200, body[:60])

    print("\n[Search: phân trang — 132 việc không được kẹt ở 50]")
    # Không có nút sang trang thì 82 việc còn lại có tồn tại cũng như không.
    import re as _re3
    import jobbot.dashboard.filters as _filters
    rows = lambda html: len(_re3.findall(r"class='jrow", html))
    real_per = _filters.PER_PAGE
    _filters.PER_PAGE = 2            # fixture chỉ có vài tin -> ép nhiều trang
    _, p1 = get("/search?show=all")
    _, p2 = get("/search?show=all&page=2")
    check("trang 1 đầy", rows(p1) > 0)
    check("có nút sang trang", "class=pager" in p1 and "sau →" in p1)
    check("trang 2 ra thẻ KHÁC trang 1", rows(p2) > 0 and p1 != p2)
    check("nói rõ đang ở trang mấy trên mấy", "trang 1/" in p1 and "trang 2/" in p2)
    _, far = get("/search?page=9999")
    check("trang vượt quá thì rỗng, không sập", far and rows(far) == 0)
    _filters.PER_PAGE = real_per

    print("\n[trang chi tiết một tin PHẢI sống dù tab Jobs đã bỏ]")
    # /jobs danh sách bỏ rồi, nhưng /jobs/<id> là chỗ đọc VÌ SAO một tin được
    # chấm ngần ấy điểm — danh sách mới trong Search sẽ trỏ vào đây.
    code, detail = get(f"/jobs/{job_id}")
    check("chi tiết một tin vẫn mở được", code == 200, detail[:80])
    check("và hiện tin thật của DB", "Man Group" in detail or "Monzo" in detail)
    check("kèm bằng chứng từng yêu cầu", "requirement" in detail.lower()
          or "yêu cầu" in detail.lower() or "evidence" in detail.lower())
    for sub in ("cv", "project"):
        code, _ = get(f"/jobs/{job_id}/{sub}")
        check(f"/jobs/<id>/{sub} vẫn sống", code == 200)

    # MỌI trang trong thanh bên. Đã sập trắng vì một tham số thừa ở chỗ gọi
    # (`mail.account(conn)` sau khi hàm bỏ tham số) — 906 bài test xanh mà
    # trang /track chết, vì không bài nào mở nó.
    for page in ("/", "/search", "/track", "/cv", "/profile",
                 "/settings"):
        code, body = get(page)
        check(f"{page} mở được", code == 200, f"HTTP {code}")
        check(f"{page} không trả trang lỗi", "Traceback" not in body)

    print("\n[mọi liên kết trong trang phải tới được]")
    _links = set()
    # Không tìm thấy link nào nghĩa là bài test này KHÔNG kiểm gì —
    # tệ hơn không có, vì nó vẫn xanh.
    for _page in ("/", "/search", "/track", "/cv", "/profile"):
        _s3, _b3 = get(_page)
        if _s3 != 200:
            continue
        _links |= set(_re2.findall(r"href='(/[^'#?]*)", _b3))
        _links |= set(_re2.findall(r'href="(/[^"#?]*)', _b3))
    for _href in sorted(_links):
        if _href.startswith("/static") or _re2.search(r"/\d+", _href):
            continue
        _c4, _ = get(_href)
        check(f"liên kết {_href} tới được", _c4 in (200, 303), f"HTTP {_c4}")
    check("có liên kết để mà kiểm", len(_links) >= 5, str(len(_links)))

    print("\n[thanh bên: logo và mục Cài đặt ở đáy]")
    _c7, _home = get("/")
    check("mục Cài đặt có trong thanh bên", "navend" in _home)
    # Là <button>, KHÔNG phải <a>: /settings trả về MẢNH HTML cho tấm phủ,
    # link tới đó là ra trang trắng.
    import re as _re7
    _end = _re7.search(r"<div class=navend>(.*?)</div>", _home, _re7.S)
    check("Cài đặt là nút, không phải link", bool(_end) and "<button" in _end.group(1))
    check("và không phải thẻ <a>", bool(_end) and "<a " not in _end.group(1))
    # Dùng CHUNG data-settings với bánh răng trên thanh master: một trình nghe
    # lo cả hai, không thêm đường nào mới để mà chết.
    # Dùng CHUNG `data-settings` với bánh răng trên thanh master: một trình
    # nghe lo cả hai, không thêm đường nào mới để mà chết. Đếm theo VÙNG, không
    # đếm cả trang — vài trang còn nút mở tấm phủ khác cũng dùng thuộc tính đó.
    # Nút Cài đặt KHÔNG dùng chung đường với nút ⚟ của khúc: ⚟ chỉnh khúc,
    # Cài đặt chỉnh cả app. Chung một thuộc tính thì sớm muộn chung luôn nội
    # dung, rồi lại thành "một thanh vừa của app vừa của khúc" như thanh cũ.
    check("mục Cài đặt mang data-appset",
          bool(_end) and "data-appset" in _end.group(1))
    check("và KHÔNG dính vào khung ⚟ của khúc",
          bool(_end) and "data-settings" not in _end.group(1))
    # Bánh răng ĐÃ RỜI thanh trên cùng: Cài đặt (toàn app) về đáy thanh bên,
    # còn thanh trên cùng giờ là thanh của KHÚC đang mở, mang nút ⚟ Điều chỉnh
    # của riêng khúc đó. Một thanh không thể vừa là của app vừa là của khúc.
    # Trang chưa có khúc thì KHÔNG vẽ thanh trên cùng: trạng thái chung đã ở
    # thanh đáy, vẽ thêm dòng y hệt trên đầu là nói hai lần.
    check("trang chưa có khúc thì không có thanh trên cùng",
          "class='topbar" not in _home and "class=runstate" not in _home)
    _, _s2 = get("/search")
    _bar2 = _re7.search(r"<header class=topbar>(.*?)</header>", _s2, _re7.S)
    check("trang có khúc thì thanh mang nút ⚟ của khúc",
          bool(_bar2) and "data-settings='/adjust/search'" in _bar2.group(1))
    _css7 = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    _, _sv = get("/")
    check("logo là chìa khoá vẽ bằng SVG", "<svg class=logo" in _sv)
    check("ba vòng chìa là vòng THẬT — có lỗ, không phải chấm đặc",
          _sv.count("<circle") == 3 and "fill=none" in _sv)
    check("logo ăn màu từ CSS, không đóng cứng trong hình",
          "currentColor" in _sv and ".logo{" in _css7)
    check("navend bị đẩy xuống đáy", "margin-top:auto" in _css7)

    print("\n[đường PHÁ HOẠI không được là đường mặc định]")
    # Một POST rỗng tới /api/sieve đã XOÁ SẠCH lưới lọc chức danh: mọi tin lọt
    # lưới (đo được 197 -> 4660 tin), tab Search đầy rác, và không có cảnh báo
    # nào. Cùng lớp lỗi với /api/mail/forget xoá app password.
    for _bad in (b"", b"arg=abc", b"seniority=junior"):
        _c5 = post("/api/sieve", _bad)
        check(f"POST rỗng tới /api/sieve bị từ chối ({_bad[:12]!r})", _c5 == 400,
              f"HTTP {_c5}")
    _conn5 = db.connect(Path(tmp) / "jobbot.db")
    _titles5 = (store.load(_conn5).get("job_titles") or "")
    _conn5.close()
    check("lưới lọc còn nguyên sau mấy cú POST đó", bool(_titles5.strip()))

    print("\n[CV: màn con SOẠN KHỐI — chỗ ngồi viết, không phải tấm phủ]")
    # Tấm phủ /cv/block cũ rộng 380px và CÂM: gõ xong bấm Lưu, rồi chỉ biết
    # câu vừa viết bị luật bỏ nếu tự đi dựng lại cả loạt bản mà đọc. Màn con
    # phải thật sự khác nó, không phải cùng cái form dán sang trang khác.
    from jobbot.dashboard import live as _lv7
    from jobbot.dashboard.views import cvlist as _cvl7
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    _d7 = _lv7.cv_soan(_c7, "")
    _ten7 = _d7["khoi"][0]["title"] if _d7["khoi"] else ""
    _c7.close()

    check("thanh điều khiển tab CV có CỬA VÀO màn soạn",
          "/cv/soan" in get("/cv")[1])
    _s7, _soan = get("/cv/soan?khoi=" + urllib.parse.quote(_ten7, safe=""))
    check("/cv/soan mở đúng khối được gọi tên", _s7 == 200 and _ten7[:30] in _soan)
    check("và mọi câu của khối đó ra ô soạn",
          _soan.count("class=cvdraft") >= len(_d7["khoi"][0]["lines"]))
    # ĐÂY LÀ LÝ DO MÀN NÀY TỒN TẠI: mỗi câu kèm luật nói gì.
    check("mỗi câu có dải chấm — luật nói gì về nó",
          _soan.count("class=sntfoot") == len(_d7["khoi"][0]["lines"]))
    check("và chấm bằng CHỮ đọc được, không phải mã luật",
          any(x in _soan for x in ("lên CV", "xem lại", "luật bỏ")))
    check("khối đang mở được đánh dấu trong danh sách bên trái",
          "blk on" in _soan or "blk dead on" in _soan)
    check("nút quay lại danh sách bản", "href='/cv'" in _soan)
    # Thanh bên phải sáng ở CV, không phải một tab thứ sáu: đây là màn CON.
    check("màn con vẫn thuộc tab CV trên thanh bên",
          "navlink on' href='/cv'" in _soan.replace('"', "'"))

    # KHÔNG được gọi cv_versions: đó là lượt dựng 5,3 giây, trả giá mỗi lần
    # mở chỗ soạn. Bỏ chú thích trước khi soi — chính lời giải thích "không
    # gọi cv_versions" cũng chứa cái tên đó.
    _srv7 = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
    _route7 = _srv7.split('if path == "/cv/soan":')[1].split("if path ==")[0]
    _route7 = "\n".join(l.split("#")[0] for l in _route7.splitlines())
    check("màn soạn KHÔNG gọi lượt dựng 5 giây", "cv_versions" not in _route7)

    # Lưu xong phải về ĐÚNG CHỖ vừa đứng, không bị hất sang danh sách bản.
    # urlopen ĐI THEO chuyển hướng, nên phải chặn nó lại mới đọc được Location
    # — theo xong thì mọi đường đều ra 200 và bài test không kiểm được gì.
    class _KhongTheo(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    def post_ve(path, body):
        """POST rồi trả về (mã, chỗ nó bảo đi tiếp)."""
        o = urllib.request.build_opener(_KhongTheo)
        req = urllib.request.Request(base.rstrip("/") + path, data=body.encode())
        try:
            with o.open(req, timeout=25) as r:
                return r.status, r.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Location", "")

    _ma, _ve = post_ve("/cv/block", "kind=project&title=Thu+Nghiem&was="
                       "&line=Wrote+a+small+tool+in+Python+that+cut+the+run+to+9+minutes.")
    check("lưu khối -> quay lại ĐÚNG khối vừa sửa, không hất sang danh sách bản",
          _ma == 303 and _ve.startswith("/cv/soan?khoi="), f"{_ma} {_ve}")
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    _txt7 = store.load(_c7).get("cv_text") or ""
    check("và câu vừa gõ nằm trong CV GỐC, không phải bảng riêng",
          "cut the run to 9 minutes" in _txt7)
    _c7.close()
    _s7, _lai = get("/cv/soan?khoi=Thu+Nghiem")
    check("mở lại khối vừa lưu thì thấy câu đó", "cut the run to 9 minutes" in _lai)
    check("và nó được chấm ngay, không phải chờ dựng lại",
          "class=sntfoot" in _lai)
    # Xoá khối -> vẫn về màn soạn, không rơi vào khối vừa xoá.
    _ma, _ve = post_ve("/cv/block",
                       "kind=project&title=Thu+Nghiem&was=Thu+Nghiem&kill=1&line=")
    check("xoá khối -> về màn soạn, KHÔNG mở lại khối vừa xoá",
          _ma == 303 and _ve == "/cv/soan", f"{_ma} {_ve}")
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    check("và câu đó biến khỏi CV gốc",
          "cut the run to 9 minutes" not in (store.load(_c7).get("cv_text") or ""))
    _c7.close()

    # Tấm phủ cũ phải BIẾN MẤT, không nằm lại làm cửa thứ hai vào cùng một việc.
    check("tấm phủ soạn khối cũ đã bỏ", not hasattr(_cvl7, "edit"))
    check("và /cv/block không còn trả trang", get("/cv/block?title=")[0] == 404)

    print("\n[CV: VIẾT CÂU MỚI và SỬA KHỐI là MỘT việc, một màn]")
    # Xưởng viết từng là tấm phủ riêng (/cv/viet + POST /api/cv/viet): đọc yêu
    # cầu ở một màn, gõ ở màn khác, HAI đường ghi vào cùng một `cv_text` phải
    # ngồi trông nhau. Nhưng viết một câu mới CHÍNH LÀ sửa một khối.
    check("tấm phủ xưởng viết đã bỏ", not hasattr(_cvl7, "viet"))
    check("và /cv/viet không còn trả trang", get("/cv/viet?ky=python")[0] == 404)
    check("đường ghi thứ hai cũng bỏ — một phép ghi, một chỗ",
          post_form("/api/cv/viet", "cau=x&khoi=y&ky=z") == 404)
    # Nút VIẾT ở thang HỤT phải dẫn vào màn soạn, không mở tấm phủ. Kho thử
    # có thể không đẻ ra dòng VIẾT nào (thang hụt rỗng), nên soi thẳng bộ vẽ:
    # bài test phải kiểm cái nút, không kiểm kho tin.
    _gia_hut = {"tin": 10, "nen": 4, "chi_viet": 7, "so_viet": 1,
                "buoc": [{"ky_nang": "sql", "viec": "viet", "them": 3,
                          "cong_don": 3, "dong": 5, "rieng": 0}]}
    _hut7 = _cvl7.hut(_gia_hut)
    check("nút Viết ở thang HỤT dẫn thẳng vào màn soạn",
          "/cv/soan?ky=sql" in _hut7 and "/cv/viet" not in _hut7)
    check("và là LIÊN KẾT, không phải nút mở tấm phủ",
          "data-settings" not in _hut7)
    check("/cv không còn đường nào trỏ vào tấm phủ cũ", "/cv/viet" not in get("/cv")[1])

    _s7, _br = get("/cv/soan?ky=sql")
    check("/cv/soan?ky= mở MÀN VIẾT ba bước",
          _s7 == 200 and _br.count("class=buocso") == 3)
    # Kho thử đòi `sql` toàn bằng dòng TẢ PHẨM CHẤT ("Comfortable with SQL"),
    # nên KHÔNG có nền bản nháp nào — và đó là hành vi đúng: không có việc nào
    # trong "Comfortable with SQL" để kể lại.
    check("dòng tả phẩm chất KHÔNG được đưa ra làm nền",
          "&nen=" not in _br)
    check("nhưng vẫn đọc được, trong thẻ gấp",
          "tả phẩm chất chứ không tả việc" in _br)
    check("brief in nguyên văn dòng yêu cầu thật của tin", "Comfortable with SQL" in _br)
    check("và nói rõ tin đó của công ty nào", "Man Group" in _br)
    check("chưa chọn khối thì bước 3 chỉ về bước 2",
          "Chọn khối ở bước 2" in _br)
    check("luật gốc nói thẳng ra chỗ sắp gõ: máy KHÔNG viết hộ",
          "không biết bạn đã làm gì" in _br)
    # Thanh trên phải nói ĐỘ PHỦ HÔM NAY — con số duy nhất cho biết màn này có
    # ích không. Delta thuộc về nhật ký, nơi nó có dấu thời gian.
    check("thanh điều khiển nói độ phủ hôm nay", "tin hồ sơ đáp trọn" in _br)

    _, _vua = get("/cv/soan?khoi=" + urllib.parse.quote(_ten7, safe="") + "&ky=sql")
    check("chọn khối rồi thì bước 3 mở ra ô gõ",
          "class=cvdraft" in _vua and "name=them value=1" in _vua)
    check("nút Lưu nói rõ câu này đi vào ĐÂU", "Thêm câu này vào" in _vua)
    check("chip kỹ năng đang nhắm được đánh dấu", "hmini on" in _vua or "ky=sql" in _vua)
    # MÀN VIẾT KHÁC MÀN SỬA KHỐI: vào để viết MỘT câu thì không đổ 16 câu cũ ra,
    # ô cần gõ sẽ bị chôn xuống dưới hai màn hình.
    check("màn viết KHÔNG đổ cả khối ra", "class=sntfoot" not in _vua)
    _, _sua = get("/cv/soan?khoi=" + urllib.parse.quote(_ten7, safe=""))
    check("còn màn SỬA KHỐI thì có, và có dải chấm từng câu",
          "class=sntfoot" in _sua and "class=buocso" not in _sua)

    print("\n[CV: nhãn VIẾT phải giữ lời — có nền bản nháp, và có chốt chặn]")
    # Thang hụt dán nhãn VIẾT khi phần lớn dòng must KHÔNG gọi đích danh tên
    # sản phẩm — tức diễn đạt lại bằng chữ mình được. Nói vậy rồi mà chỉ đưa ra
    # một ô trống thì cái nhãn là lời hứa suông.
    # Dòng THẬT trong kho của Vin. Phải đủ dài để cắt được phần thừa mà vẫn
    # giữ tên kỹ năng — dòng ngắn quá thì `goi_y` im lặng, và đó là hành vi
    # đúng: cắt không đủ xa thì gợi ý chỉ là dòng của họ chia ở thì quá khứ.
    _nen7 = "Improve research frameworks, data pipelines, and model performance"
    # GHÉP THÊM một dòng must, KHÔNG ghi đè cả score_json: bản chấm còn mấy
    # khoá khác mà trang chi tiết tin đọc tới, xoá sạch là route đó sập.
    _cn7 = db.connect(Path(tmp) / "jobbot.db")
    for _r7 in _cn7.execute("SELECT id, score_json FROM posting"
                            " WHERE company = 'Man Group'").fetchall():
        _j7 = json.loads(_r7["score_json"]) if _r7["score_json"] else {}
        # Hàng THẬT do bộ chấm đẻ ra luôn có `met`; thiếu nó là trang chi tiết
        # tin sập — fixture phải giống hàng thật, không phải giống cái vừa đủ.
        _j7.setdefault("requirements", []).append(
            {"text": _nen7, "must": True, "met": False, "evidence": ""})
        _cn7.execute("UPDATE posting SET score_json = ? WHERE id = ?",
                     (json.dumps(_j7), _r7["id"]))
    _cn7.commit(); _cn7.close()
    from jobbot.dashboard import live as _lv9
    _lv9.quen()
    _, _nb = get("/cv/soan?ky=data%20pipeline")
    check("dòng TẢ VIỆC được đưa ra làm nền bản nháp", _nen7 in _nb)
    check("và bấm được — nó rơi thẳng vào ô soạn",
          "&nen=Improve%20research%20frameworks" in _nb)

    _mo = ("/cv/soan?khoi=" + urllib.parse.quote(_ten7, safe="")
           + "&ky=data%20pipeline&nen=" + urllib.parse.quote(_nen7, safe=""))
    _, _co_nen = get(_mo)
    check("bước 1 đã xong thì gập lại, đổi được", "Đổi dòng" in _co_nen)
    check("dòng đã chọn hiện nguyên văn ở bước 1", _nen7 in _co_nen)
    # Dòng nào KHÔNG rút gọn được thì ô mở ra là nguyên văn, và phải nói rõ
    # đó là chữ của ai — người dùng quay lại sau mười phút vẫn phải nhận ra.
    _, _tho7 = get(_mo + "&tho=1")
    check("dùng nguyên văn thì ghi rõ đó là chữ của NHÀ TUYỂN DỤNG",
          "chữ của nhà tuyển dụng" in _tho7)
    # Cột trái là "viết vào ĐÂU"; bấm một khối không được vứt mất "viết CÁI GÌ".
    check("bấm khối khác vẫn giữ nguyên đích và nền",
          "ky=data%20pipeline&nen=Improve" in _co_nen.replace("&amp;", "&"))

    # GỢI Ý: ô mở ra đã có hình câu CV, người dùng chỉ điền chỗ trống.
    from jobbot.scoring.gap import goi_y as _gy9, CHO_TRONG as _CT9
    _gs = _gy9(_nen7, "data pipeline")
    check("dòng nền này rút gọn được thành hình câu CV", bool(_gs), _nen7)
    _, _co_gy = get(_mo)
    check("ô soạn mở ra đã là GỢI Ý, không phải nguyên văn dòng của họ",
          _gs in _co_gy)
    check("và chừa chỗ trống cho bằng chứng", _CT9 in _co_gy)
    check("có đường lật về nguyên văn dòng của họ", "tho=1" in _co_gy)
    _, _co_tho = get(_mo + "&tho=1")
    check("lật về thì ô là nguyên văn, và có đường quay lại gợi ý",
          _nen7 in _co_tho and "Gợi ý câu CV" in _co_tho)

    # Chỗ trống còn nguyên = chưa viết xong. Lưu nguyên gợi ý là lưu một câu
    # RỖNG BẰNG CHỨNG — tệ hơn cả chép dòng của họ.
    _ma, _ve = post_ve("/cv/block",
                       "them=1&title=" + urllib.parse.quote(_ten7, safe="")
                       + "&ky=data+pipeline&nen="
                       + urllib.parse.quote(_nen7, safe="")
                       + "&line=" + urllib.parse.quote(_gs, safe=""))
    check("lưu nguyên gợi ý, chưa điền chỗ trống -> KHÔNG cho qua",
          _ma == 303 and "loi=" in _ve, f"{_ma} {_ve}")
    _, _sau_ct = get(_ve)
    check("và nói rõ chỗ trống là chỗ của BẰNG CHỨNG",
          "chỗ của BẰNG CHỨNG" in _sau_ct)
    # MỐC SO SÁNH không được trôi theo bản sửa: trôi thì lần sau chép nguyên
    # văn cũng lọt.
    check("mốc so sánh vẫn là dòng GỐC của họ, không phải bản vừa gõ",
          "nen=" + urllib.parse.quote(_nen7, safe="") in _ve)

    # CHỐT CHẶN: lưu nguyên chữ của họ thì không cho qua, và chữ vừa gõ còn nguyên.
    _ma, _ve = post_ve("/cv/block",
                       "them=1&title=" + urllib.parse.quote(_ten7, safe="")
                       + "&ky=data+pipeline&nen="
                       + urllib.parse.quote(_nen7, safe="")
                       + "&line=" + urllib.parse.quote(_nen7, safe=""))
    check("chép nguyên dòng của nhà tuyển dụng -> KHÔNG cho lưu",
          _ma == 303 and "loi=" in _ve, f"{_ma} {_ve}")
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    check("và nó KHÔNG lọt vào CV gốc",
          _nen7 not in (store.load(_c7).get("cv_text") or ""))
    _c7.close()
    _, _sau_loi = get(_ve)
    check("chữ vừa gõ còn nguyên để sửa tiếp", _nen7 in _sau_loi)
    check("và lời từ chối đứng ngay trên ô", "chưa phải việc BẠN làm" in _sau_loi)

    # Viết lại thành việc của mình thì qua.
    _that = ("Rebuilt the nightly research pipeline in Python, cutting a "
             "40-minute reconciliation to 90 seconds across 17 feeds.")
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    _truoc7 = (store.load(_c7).get("cv_text") or "")
    _c7.close()
    _ma, _ve = post_ve("/cv/block",
                       "them=1&title=" + urllib.parse.quote(_ten7, safe="")
                       + "&ky=data+pipeline&nen="
                       + urllib.parse.quote(_nen7, safe="")
                       + "&line=" + urllib.parse.quote(_that, safe=""))
    check("viết lại thành việc của mình -> cho lưu", _ma == 303 and "loi=" not in _ve)
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    _sau7 = (store.load(_c7).get("cv_text") or "")
    _c7.close()
    check("và câu đó vào CV gốc", _that in _sau7)
    # THÊM nghĩa là THÊM: màn viết chỉ gửi đúng MỘT câu, nó không thấy mấy câu
    # cũ nên không được phép thay chúng.
    _mat = [l.strip() for l in _truoc7.splitlines()
            if len(l.strip()) > 40 and l.strip() not in _sau7]
    check("câu cũ trong khối KHÔNG bị nuốt mất", not _mat, str(_mat[:1]))
    check("lưu xong thì BỎ nền đi, không mời lưu nhầm lần nữa", "nen=" not in _ve)

    # MÁY TỰ LO, việc thứ HAI: dựng sẵn bản nháp cho MỌI chỗ hụt, không đợi
    # bấm từng cái. KHÔNG tự ghi vào CV — câu nháp nằm trong cv_text thì bộ
    # chấm đếm luôn nó là kỹ năng đã đáp, và app nói dối người dùng về chính
    # họ. Người dùng điền con số rồi bấm, từng câu một.
    from jobbot.core import prefs as _pfB
    _cB = db.connect(Path(tmp) / "jobbot.db")
    _pfB.set_flag(_cB, _pfB.CV_TU_LO, False)
    _cB.close()
    _lv9.quen()
    check("TẮT -> không dựng sẵn gì", "class=sanbox" not in get("/cv/soan")[1])
    _cB = db.connect(Path(tmp) / "jobbot.db")
    _pfB.set_flag(_cB, _pfB.CV_TU_LO, True)
    _truoc_cv = (store.load(_cB).get("cv_text") or "")
    _cB.close()
    _lv9.quen()
    _s9, _sanB = get("/cv/soan")
    check("BẬT -> máy dựng sẵn bản nháp cho mọi chỗ hụt",
          _s9 == 200 and "class=sanbox" in _sanB)
    check("mỗi bản nháp chừa chỗ trống cho bằng chứng", "___" in _sanB)
    check("và bấm được để vào điền", "class=sanone" in _sanB and "&nen=" in _sanB)
    _cB = db.connect(Path(tmp) / "jobbot.db")
    check("nhưng KHÔNG tự ghi câu nào vào CV gốc",
          (store.load(_cB).get("cv_text") or "") == _truoc_cv)
    _cB.close()

    # MÁY TỰ LO phải THẬT SỰ chạy, không phải một nút cho có.
    from jobbot.core import prefs as _pfA
    _cA = db.connect(Path(tmp) / "jobbot.db")
    _pfA.set_flag(_cA, _pfA.CV_TU_LO, True)
    _cA.close()
    from jobbot.cv import batch as _btA
    _cA = db.connect(Path(tmp) / "jobbot.db")
    _truocA = (_btA.saved(_cA) or {}).get("stamp")
    _cA.close()
    post_ve("/cv/block", "them=1&title=" + urllib.parse.quote(_ten7, safe="")
            + "&line=Shipped+a+nightly+check+across+17+feeds+in+under+90+seconds.")
    import time as _tA
    for _ in range(60):                       # dựng chạy nền, chờ tối đa 30s
        _cA = db.connect(Path(tmp) / "jobbot.db")
        _sauA = (_btA.saved(_cA) or {}).get("stamp")
        _cA.close()
        if _sauA and _sauA != _truocA:
            break
        _tA.sleep(0.5)
    check("bật MÁY TỰ LO -> sửa khối xong máy dựng lại thật",
          bool(_sauA) and _sauA != _truocA, f"{_truocA} -> {_sauA}")
    # TẮT rồi CHỜ luồng nền xong hẳn. Không chờ thì thư mục tạm bị xoá trong
    # lúc luồng còn mở DB, và cả file test đổ vỡ vì một lỗi không liên quan.
    _pfA.set_flag(db.connect(Path(tmp) / "jobbot.db"), _pfA.CV_TU_LO, False)
    from jobbot.dashboard.server import _DANG_DUNG as _lockA
    with _lockA:
        pass
    # Núm NHỊP không được làm mọi bản bỗng bị coi là cũ: nó không đổi bản dựng
    # ra gì, chỉ đổi LÚC dựng.
    _cA = db.connect(Path(tmp) / "jobbot.db")
    _dauA = _btA.stamp(_cA, store.load(_cA).get("cv_text") or "")
    _pfA.set_flag(_cA, _pfA.CV_TU_LO, False)
    check("lật núm nhịp KHÔNG làm bản đang có bị coi là cũ",
          _btA.stamp(_cA, store.load(_cA).get("cv_text") or "") == _dauA)
    _cA.close()

    # LƯU XONG BRIEF PHẢI CÒN ĐÓ: người ta thường viết hai câu về cùng chỗ hụt.
    _ma, _ve = post_ve("/cv/block", "kind=project&title=Thu+Nghiem+2&was=&ky=sql"
                       "&line=Tuned+the+SQL+that+backs+the+daily+report,+cutting+it+to+9+s.")
    check("lưu từ màn viết -> quay lại ĐÚNG khối và GIỮ brief đang mở",
          _ma == 303 and "khoi=Thu%20Nghiem%202" in _ve and _ve.endswith("&ky=sql"),
          f"{_ma} {_ve}")

    # ĐO THẬT, KHÔNG HỨA. Trước đây phép đo "trước -> sau" chỉ có ở đường ghi
    # của xưởng viết; đường ghi của khối thì im lặng. Nay một đường, nên nó
    # phải mang theo phép đo — nếu không, gộp hai màn là mất một con số.
    from jobbot.core import journal as _jn7
    _dong7 = [e.text for e in _jn7.log.tail("cv", limit=40)]
    check("nhật ký ghi việc vừa làm",
          any("Thu Nghiem 2" in t for t in _dong7), " | ".join(_dong7[:3]))
    check("và ĐO LẠI ĐỘ PHỦ, không chỉ báo đã lưu",
          any("đáp trọn" in t and " tin" in t for t in _dong7),
          " | ".join(_dong7[:3]))
    # Câu viết ra mà KHÔNG mở khoá thêm tin nào cũng phải nói — im lặng ở đúng
    # chỗ đó là để người viết tưởng câu vừa viết có ăn.
    check("không đổi cũng nói ra, không im lặng",
          any("vẫn đáp trọn" in t for t in _dong7) or
          any("->" in t for t in _dong7), " | ".join(_dong7[:3]))
    post_ve("/cv/block", "kind=project&title=Thu+Nghiem+2&was=Thu+Nghiem+2&kill=1&line=")

    print("\n[tab CV phải mở NHANH]")
    import time as _t5
    from jobbot.dashboard import live as _live5
    _conn6 = db.connect(Path(tmp) / "jobbot.db")
    _live5.quen()
    _t0 = _t5.perf_counter(); _live5.cv_blocks(_conn6); _cold = _t5.perf_counter() - _t0
    _t0 = _t5.perf_counter(); _live5.cv_blocks(_conn6); _warm = _t5.perf_counter() - _t0
    # Đo trên máy Vin: 7,8 giây MỖI LẦN gọi, và tab CV gọi nó mỗi lần mở.
    check("cv_blocks có cache", _warm < _cold / 5 or _warm < 0.01,
          f"lạnh {_cold:.3f}s · ấm {_warm:.3f}s")
    _conn6.close()

    print("\n[thoát HTML — dữ liệu cào về không được thành mã]")
    conn = db.connect(Path(tmp) / "jobbot.db")
    conn.execute("UPDATE posting SET company = ? WHERE kept = 1",
                 ("<script>alert(1)</script>",))
    conn.commit(); conn.close()
    _, hacked = get(f"/jobs/{job_id}")
    check("thẻ script bị thoát", "<script>alert(1)</script>" not in hacked)
    check("và vẫn hiện dạng chữ", "&lt;script&gt;" in hacked)

    print("\n[tên tệp PDF — một bản CV một tệp]")
    # Lỗi thật: Jane Street có HAI bản CV khác nhau cùng ra tên
    # "jane-street-machine-learning-researcher.pdf". Bản sau đè bản trước, và
    # 7 tin thì có tin cầm nhầm CV. In ra 43 bản mà `ls` chỉ đếm được 42 —
    # không ai để ý, vì không có gì báo.
    from jobbot.dashboard import live as _live
    conn = db.connect(Path(tmp) / "jobbot.db")
    plan = _live.cv_pdf_plan(conn)
    names = [item["file"].name for item in plan]
    check("mỗi bản CV một tên tệp riêng", len(names) == len(set(names)),
          f"{len(names)} bản, {len(set(names))} tên")
    covered = [pid for item in plan for pid in item["ids"]]
    check("một tin chỉ thuộc đúng một bản", len(covered) == len(set(covered)))
    check("tra ngược ra đúng tệp",
          all(_live.cv_pdf_for(conn, item["ids"][0]) == item["file"] for item in plan))
    conn.close()

    httpd.shutdown(); httpd.server_close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[CSS: hai class cùng tên KHÔNG được đá nhau về bố cục]")
import re as _re2
from collections import Counter as _C
_css = (Path(__file__).resolve().parent.parent
        / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
_depth, _seen = 0, {}
for _line in _css.splitlines():
    _m = _re2.match(r"\s*(\.[a-zA-Z][\w-]*)\s*\{(.*)$", _line)
    if _m and _depth == 0:
        # `position` cũng phải soi, không riêng `display`: nút "Sửa khối" trên
        # thanh điều khiển từng mang lớp `.side` — trùng tên THANH BÊN, vốn
        # position:fixed — nên nó bay ra góc trái màn hình, ngoài cả thanh
        # chứa nó. HTML đúng, DOM đúng, chỉ có chỗ đứng là sai.
        for _thuoc in ("display", "position"):
            _hit = _re2.search(_thuoc + r"\s*:\s*([a-z-]+)", _m.group(2))
            if _hit:
                _seen.setdefault((_m.group(1), _thuoc), set()).add(_hit.group(1))
    _depth += _line.count("{") - _line.count("}")
_clash = {k: v for k, v in _seen.items() if len(v) > 1}
# .frow từng vừa là hàng lọc (flex) vừa là hàng phễu (grid): ô tải CV lên và
# hàng lọc hồ sơ bị bẻ thành lưới 3 cột. .prow tương tự với thanh tiến độ.
check("không class nào có hai kiểu display / position", not _clash, str(_clash))

print("\n[nút trong form — bấm không được nuốt mất form]")
_js = (Path(__file__).resolve().parent.parent
       / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
# FORM cũng mang [data-post] và nút Gửi nằm TRONG nó, nên closest() từ nút đi
# ngược lên gặp form. Nhánh nút gán `post.textContent = ...` — gán textContent
# lên một form là XOÁ SẠCH RUỘT NÓ. Bấm Nối một cái là ô nhập biến mất.
check("nhánh nút bỏ qua thẻ FORM", "post.tagName === 'FORM'" in _js)
check("và bỏ qua TRƯỚC khi gán textContent",
      _js.index("post.tagName === 'FORM'") < _js.index("post.textContent = s.note"))
check("form có trình nghe submit riêng", "form[data-post]" in _js)
# Form Cài đặt là trường hợp riêng, không được nuốt mọi form khác.
check("trình nghe Cài đặt vẫn chỉ nhận đúng /settings",
      "!== '/settings'" in _js)
# Form nối hộp thư đã chuyển sang Cài đặt · Gmail. Nút Nối phải là submit
# của form, không phải một [data-post] riêng: trình nghe [data-post] gán
# textContent lên thứ nó bắt được, mà ở đây nó bắt được cả cái form.
_setsrc = (Path(__file__).resolve().parent.parent
           / "src/jobbot/dashboard/views/settings.py").read_text(encoding="utf-8")
_form_noi = _setsrc.split("data-post='/api/mail/setup'")[1].split("</form>")[0]
check("nút Nối là type=submit, không phải data-post riêng",
      "type=submit" in _form_noi)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
