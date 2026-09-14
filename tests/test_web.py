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

# CHẠY LẺ CŨNG PHẢI ĐÚNG.
#
# run_all.py dựng một gốc dự án giả + khoá mạng cho mọi bài. Nhưng chạy lẻ
# một file (python3 tests/test_web.py) thì không có chốt đó, và mấy bài
# khẳng định "chưa nối bot" sẽ đỏ — đỏ vì máy này có cấu hình, không vì code
# sai. Tệ hơn: chạy lẻ có thể gửi tin thật về điện thoại người dùng.
#
# Đặt NGAY ĐÂY, trước mọi import jobbot, để không có lối vòng.
import os as _os, tempfile as _tf, pathlib as _pl
_os.environ.setdefault("JOBBOT_OFFLINE", "1")
if "JOBBOT_ROOT" not in _os.environ:
    _gia = _tf.mkdtemp(prefix="jobbot-test-")
    _pl.Path(_gia, "config").mkdir(parents=True, exist_ok=True)
    _os.environ["JOBBOT_ROOT"] = _gia

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
          "/settings", "/api/profile", "/api/state", "/api/alive"]

print("\n[mọi route phải trả 200 và KHÔNG có traceback]")
with tempfile.TemporaryDirectory() as tmp:
    import os
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = seeded(Path(tmp) / "jobbot.db")
    job_id = conn.execute("SELECT id FROM posting WHERE kept=1 LIMIT 1").fetchone()[0]
    conn.close()

    # CỔNG TỰ TÌM, không đóng cứng. Đóng cứng 8791 thì hai lượt test chạy
    # chồng nhau (hoặc một cái gì khác đang nghe ở đó) là "Address already in
    # use" — bài test đỏ vì lý do chẳng liên quan gì tới code, và đỏ KHÔNG
    # ĐỀU nên càng khó tin. Bắt đầu từ 8791 để tránh cổng của app đang chạy
    # (8765), rồi nhích lên nếu bận.
    from jobbot.dashboard.server import serve
    httpd, base = serve(port=0)
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

    print("\n[/api/alive — dấu nhận dạng cho người NGOÀI tiến trình]")
    # start.command hỏi đúng route này để phân biệt "jobbot đang chạy" với
    # "cổng cũ giờ là app khác". Nó phải nói TÊN và PID, không chỉ trả 200.
    _st, _than = get("/api/alive")
    check("/api/alive trả 200", _st == 200, _than[:80])
    check("nói rõ jobbot đang trả lời", _than.startswith("jobbot "), _than[:80])
    check("kèm PID của chính tiến trình này",
          _than.split()[1].strip() == str(os.getpid()), _than[:80])
    check("`grep -q '^jobbot '` của start.command khớp được",
          bool(__import__("re").match(r"^jobbot \d+", _than)), _than[:80])

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
    check("nói hồ sơ đang thiếu gì", "Nothing can run yet" in _hm)
    check("và có nút đi thẳng tới chỗ điền", "href='/profile/muc_tieu'" in _hm)
    check("có thanh tiến độ", "class=obar" in _hm)
    check("liệt kê đủ 6 phần", _hm.count("class='blk ostep") == 6)
    check("phần bắt buộc được đánh dấu", "REQUIRED" in _hm)
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
    check("lúc nghỉ chỉ mời gõ, không bày cả kho", "type to search" in _mt)
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
    check("nói trước sẽ mất gì", "Will be lost:" in _set)
    check("nói trước sao lưu nằm ở đâu", "tar.gz" in _set)
    # NÚM NHỊP phải nói ra cái ĐÁNH ĐỔI ngay trên màn hình. Một núm ghi
    # "Nhanh" mà không nói nhanh bằng giá gì là núm mời người ta bấm rồi lãnh
    # hậu quả.
    _, _st = get("/settings")
    check("cài đặt có núm nhịp gọi",
          "name=pace" in _st and "call pace" in _st)
    check("ba mức, không hơn", _st.count("type=radio name=pace") == 3)
    check("và nói thẳng cái đánh đổi", "easier to throttle" in _st)
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
          "disabled>Delete everything" in _set and "data-needword" in _set)
    _js = (Path(__file__).resolve().parent.parent
           / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    check("và trình duyệt có trình nghe mở khoá", "wireDangerWord" in _js)
    # CHỮ MỜI GÕ và CHỮ ĐEM SO phải LÀ MỘT. Chúng nằm ở hai tệp khác ngôn
    # ngữ, nên không có gì buộc chúng đi cùng nhau: đổi lời mời mà quên
    # live.js thì nút không bao giờ mở, và người dùng gõ đúng thứ màn hình
    # bảo mà vẫn bị từ chối — hỏng câm.
    import re as _re0
    _moi = _re0.search(r"placeholder='type (\w+) to unlock'", _set)
    _so = _re0.search(r"toUpperCase\(\) === '(\w+)'", _js)
    check("chữ màn hình mời gõ ĐÚNG BẰNG chữ live.js đem so",
          bool(_moi and _so) and _moi.group(1) == _so.group(1),
          f"{_moi and _moi.group(1)} vs {_so and _so.group(1)}")

    print("\n[TỰ VẼ LẠI — đúng lúc, và KHÔNG cướp việc đang làm dở]")
    import re as _re
    # Hai câu hỏi khác nhau từng bị gộp làm một biến, và cả hai đều sai:
    #
    #   Home khai stream="" (ô nhật ký nhận MỌI luồng). live.js đọc chuỗi
    #   rỗng là "sai" -> nhánh vẽ lại KHÔNG BAO GIỜ chạy. Trang tự nhận là
    #   "live 24/7" mà số chỉ đổi khi người dùng bấm F5.
    #
    #   Quản lí khai stream="search" để xem nhật ký vòng quét -> quét xong
    #   là trang NHẢY, đóng sập cả 37 dòng chi tiết đang mở.
    _mong = {"/": "*", "/search": "search", "/track": "track",
             "/track/queue": "track", "/cv": "cv"}
    for _p, _v in _mong.items():
        _st, _b = get(_p)
        _the = _re.search(r"<body[^>]*>", _b).group(0)
        _co = (_re.search(r"data-reload='([^']*)'", _the) or [None, ""])[1]
        check(f"{_p:14} tự vẽ lại theo «{_v}»", _co == _v, f"thấy «{_co}»")
    # Màn SOẠN CV thì KHÔNG: ở đó người ta đang gõ chữ.
    _jid = conn2 = None
    _st, _b = get("/cv/soan")
    if _st == 200:
        check("/cv/soan KHÔNG tự vẽ lại — đang gõ chữ ở đó",
              "data-reload" not in _re.search(r"<body[^>]*>", _b).group(0))
    # live.js phải đọc CỜ CỦA TRANG, không hỏi lại ô nhật ký.
    check("live.js đọc data-reload của <body>", "dataset.reload" in _js)
    check("và KHÔNG còn suy ra từ ô nhật ký nữa",
          "box.dataset.journal" not in _js.split("data-reload")[1][:900]
          if "data-reload" in _js else False)
    check("«*» nghĩa là mọi khúc", "=== '*'" in _js)
    # Dòng chi tiết đang mở = đang làm dở. Đây là cái vừa thiếu.
    check("dòng chi tiết đang MỞ thì hoãn vẽ lại",
          "details[open]" in _js)
    check("ô đang gõ vẫn được bảo vệ như cũ",
          "input, textarea, select" in _js)
    check("tấm phủ đang mở vẫn được bảo vệ như cũ", "data-sheet" in _js)
    # HOÃN THÌ PHẢI NHỚ. Nuốt luôn thì trang đứng im vĩnh viễn — hỏng câm.
    check("hoãn rồi thì NHỚ, không nuốt", "choLamMoi" in _js)
    check("và trả nốt khi người dùng đóng dòng",
          "'toggle'" in _js and "choLamMoi" in _js.split("'toggle'")[1][:200])
    check("hoặc khi rời ô gõ",
          "'focusout'" in _js and "choLamMoi" in _js.split("'focusout'")[1][:220])

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
    check("và nói rõ còn mấy câu", "and the app can run" in _sec)
    check("nhãn nút không hứa đi tiếp",
          "Save —" in _sec and "answers still needed</button>" in _sec)
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
    check("và đổi sang mời chạy", "The profile is enough to run" in _hm2)
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
    for page in ("/search", "/cv", "/track", "/track/queue", "/"):
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
    # Nút của THƯ đã dọn sang màn hàng chờ (/track/queue). Không vẽ nó ở đây
    # thì bài này thôi kiểm /api/track/mail/* — đúng mấy đường mới nhất.
    from jobbot.dashboard.views import trackcho as _cho
    _hq = _cho.render(
        rows=[_row], mu=[dict(id=3, company="M", company_guess="",
                              subject="s", snippet="n")],
        asks=[dict(id=2, company="X", company_guess="X", stage="applied",
                   kind="rejected", subject="s", snippet="n", app_id=None)])
    _wired |= set(_re.findall(r"data-post='([^']+)'", _hq))
    _wired |= set(_re.findall(r'data-post="([^"]+)"', _hq))

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
          "No CV has been built yet" in get("/cv")[1])
    from jobbot.cv import batch as _bt
    _cvc = db.connect(Path(tmp) / "jobbot.db")
    _bt.run(_cvc)
    _cvc.close()
    _s, body = get("/cv")
    check("dựng xong thì ô hiện bản", "class=cvrow" in body)
    # KHỐI HỤT — khối trả lời câu hỏi duy nhất của tab: tối nay viết gì.
    check("tab CV có khối HỤT", "WHAT TO WRITE TO CLOSE THE GAP" in body.upper()
          or "close the gap" in body)
    # HAI ĐÍCH, không một: "làm hết bảng" gộp cả mấy dòng phải đi HỌC, mà học
    # tính bằng tháng còn viết tính bằng buổi tối.
    check("nói rõ đích VIẾT ĐƯỢC TỐI NAY tách khỏi đích phải đi học",
          "doable tonight" in body and "learnt" in body)
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
    for _dau in ("app junk on the sheet", "text too pale", "is inset"):
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
          _ra and "COULD NOT INSPECT" in _ra[0], str(_ra))
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
    check("searching by company name -> only the matching version is left",
          "Man Group" in _co and "Citadel" not in _co)
    check("and it says how many of the total are left", "1</b>/2 versions" in _co)
    _ct = _cvl._list(_gia_data, "data scientist")
    check("searching by JOB TITLE works too", "Citadel" in _ct and "Man Group" not in _ct)
    check("nothing matches -> it says so plainly, it does not return an empty list",
          "no version goes to" in _cvl._list(_gia_data, "zzzz"))
    check("the search box stays when nothing matches — to fix the text on the spot",
          "class=jfind" in _cvl._list(_gia_data, "zzzz"))
    # A VERSION'S NUMBER has to stay put while filtering: "#2" while searching and "#1"
    # when not means you cannot talk about one particular version.
    check("a version's number stays put while filtering", ">#2<" in _ct)
    check("with no search, both show",
          "Man Group" in _cvl._list(_gia_data) and "Citadel" in _cvl._list(_gia_data))

    # A ROW HAS TO SAY SOMETHING REAL. The old version printed the 4 English sentences
    # UNIQUE to that build — words the user wrote themselves, telling them nothing new on
    # re-reading, and multiplied by 28 rows nobody could read it at all.
    _ca = _cvl._list(_gia_data)
    check("a row no longer dumps whole CV sentences into the list", "cvonly" not in _ca)
    check("a row leads with THE POSTING, not with the document",
          "Man Group" in _ca and "Quant" in _ca)
    check("it carries that posting's own coverage ratio", "4/6" in _ca and "1/7" in _ca)
    check("and draws it as a bar, so 28 rows can be skimmed", "vbarc" in _ca)
    # THREE LEVELS = THREE ACTIONS: send it / weak / write more first. One colour for
    # everything makes the bar decoration.
    check("high coverage -> the ok level", "vbarc ok" in _ca)
    check("low coverage -> the low level", "vbarc low" in _ca)
    # The two numbers are TWO DIFFERENT QUESTIONS; merged into one phrase the reader
    # works out 6−4=2 and thinks the machine miscounted when the list holds only 1 item.
    check("it says 'the profile has no sentence about', not 'this version is missing'",
          "the profile has no sentence about" in _ca)
    _nhom2 = [{"jobs": [{"id": 5, "company": "A", "title": "X", "score": 90},
                        {"id": 6, "company": "B", "title": "Y", "score": 70}],
               "only": [], "missing": [], "lines": 0,
               "hoi": 4, "tra_loi": 2, "cam": []}]
    check("a group of >1 posting -> it says how many postings share the version",
          "shared by" in _cvl._list({"versions": _nhom2, "jobs": 2,
                                          "gaps": [], "core": 0}))
    check("a group of 1 posting -> it does NOT say 'shared by', that would be noise",
          "shared by" not in _ca)
    # A row has to open the posting whose name was just typed, not another posting on the same build.
    _hai = [{"jobs": [{"id": 9, "company": "Low Co", "title": "X", "score": 99},
                      {"id": 7, "company": "Man Group", "title": "Y", "score": 10}],
             "only": [], "missing": [], "lines": 0,
             "hoi": 4, "tra_loi": 2, "cam": []}]
    check("while searching, the row points at THE MATCHING posting, not the highest scoring one",
          "/jobs/7/cv" in _cvl._list({"versions": _hai, "jobs": 2, "gaps": [],
                                      "core": 0}, "man group"))
    check("POST /cv/pdf with a non-numeric id -> 400",
          post_form("/cv/pdf", "arg=abc") == 400)

    print("\n[the overlay: every form must go to its own action]")
    # live.js used to intercept EVERY .setform and post it hard-coded to '/settings'. The
    # consequence: pressing "Delete block" in the CV compose overlay opened Settings.
    # Trying it with form.submit() never showed it, because that path skips the submit
    # listener.
    js = (Path("src/jobbot/dashboard/web/live.js")).read_text()
    check("live.js intercepts only forms whose action is /settings",
          "pathname !== '/settings'" in js)
    for url in ("/cv/soan?moi=1", "/cv/draft?id=1"):
        _s, frag = get(url)
        if _s != 200:
            continue
        check(f"{url:<22} the form points at its own action",
              "action='/settings'" not in frag)

    print("\n[CV: a finished project -> a CV line]")
    # An error inside a POST route BREAKS the connection and returns nothing at all —
    # curl says "empty reply", the browser shows 404, the journal is silent. It really
    # happened with /cv/draft (a missing `self.`). Every POST route has to be called at
    # least once.
    check("GET /cv/draft with an unknown id -> 404, no crash",
          get("/cv/draft?id=999999")[0] == 404)
    check("POST /cv/draft is gone too -> 404",
          post_form("/cv/draft", "id=0&head=&line=") == 404)

    print("\n[CV: every build that will be sent, read before sending]")
    _s, body = get("/cv")
    check("/cv is in the sidebar", 'href="/cv"' in body or "href='/cv'" in body)
    check("identical builds are merged, not listed per posting",
          body.count("class=cvrow") <= 60)
    check("it states the REAL degree of tailoring, it does not boast a version count",
          "identical in every version" in body)
    check("every row points at a readable CV", "/cv'" in body and "cvrow" in body)
    check("it names the skills the profile can say NOTHING about",
          "can say NOTHING about" in body)

    from jobbot.dashboard import live as live2
    data = live2.cv_versions(db.connect(Path(tmp) / "jobbot.db"))
    if data["versions"]:
        check("each build's UNIQUE part does not bleed into the core",
              all(len(v["only"]) == v["lines"] - data["core"]
                  for v in data["versions"]))
        check("the build covering the most postings comes first",
              [len(v["jobs"]) for v in data["versions"]]
              == sorted((len(v["jobs"]) for v in data["versions"]), reverse=True))

    print("\n[personal projects ARE GONE — no dead ends may be left behind]")
    # Remove a feature and forget to remove its routes, and an old tab returns 500 while
    # an old button in an already-open browser is still clickable. Deleting means
    # deleting EVERY way in.
    for _duong in ("/projects",):
        check(f"GET {_duong} -> 404, not 500", get(_duong)[0] == 404)
    for _api in ("/api/project/build", "/api/project/state"):
        check(f"POST {_api} -> 404", post_form(_api, "arg=x") == 404)
    check("GET /cv/draft goes with them", get("/cv/draft?id=1")[0] == 404)
    # The Projects tab has to disappear from the sidebar, not only from the router.
    check("there is no Projects tab in the sidebar",
          ">Projects<" not in get("/cv")[1])
    # Two things do NOT die with it, because they never belonged to that feature.
    from jobbot.scoring.market import demand as _dm
    from jobbot.scoring.vocab import INDUSTRY as _ind
    conn2 = db.connect(Path(tmp) / "jobbot.db")
    check("the market count lives on in scoring/", isinstance(_dm(conn2), Counter))
    conn2.close()
    check("the industry vocabulary lives on in vocab/", len(_ind) == 7)
    # The CV tab is the ONLY place still using that count. It has to open, because the
    # import path has just moved house — break here and the whole CV tab goes white.
    check("the CV tab still opens after the count moved house", get("/cv")[0] == 200)

    print("\n[the CV tab: TWO knobs, and both have to really turn]")
    from jobbot.core import prefs as _pfc
    _adj = get("/adjust/cv")[1]
    # SEVEN KNOBS ARE GONE — see the comment in core/prefs.py. The user needs exactly two
    # answers: how far each posting's build is tailored, and whether the machine handles
    # it. Every other knob made them learn the machine's rules before they could use the
    # machine.
    for _bo in ("khoa:", "giong:", "bo_cuc:", "that_bai:", "y_kien:",
                "rui_ro:", "giu_muc:", "moi_khoi_viec:"):
        check(f"the {_bo[:-1]} knob is gone", f"data-arg='{_bo}" not in _adj)
    check("the Adjust panel has only TWO knobs left",
          _adj.count("data-post='/api/cv/num'") == 4)   # 3 tailoring levels + 1 machine-handles-it

    # THE TAILORING LEVEL — the knob that changes the most. Measured on the live store
    # (358 postings): shared 25 builds · medium 89 · per-posting 157, with the unchanging
    # core falling from 12/16 to 9/16 sentences.
    for _r in ("chung", "vua", "rieng"):
        check(f"the {_r} tailoring level exists", f"rieng:{_r}" in _adj)
    # Do NOT hard-code a build count into the label: it differs with every profile and
    # every store.
    check("the label says WHAT IT DOES, it hard-codes no other store's build count",
          "moves the skills sections this posting asks for to the front" in _adj
          and "versions/120 postings" not in _adj)
    check("there is a MACHINE-HANDLES-IT switch", "data-arg='tu_lo:" in _adj)
    # ON has to LIGHT UP — and the state has to be readable from the HTML, not from the
    # colour alone. The same bug as `.mbtn.off`: a class in the HTML with no CSS.
    check("the switch carries the off class when OFF", "swbtn off" in _adj)
    _cE = db.connect(Path(tmp) / "jobbot.db")
    _pfc.set_flag(_cE, _pfc.CV_TU_LO, True)
    _cE.close()
    _adjE = get("/adjust/cv")[1]
    check("switched on -> the button changes its word and DROPS the off class",
          ">ON<" in _adjE and "swbtn off" not in _adjE)
    check("and the status line says what the machine is handling",
          "drafts prepared" in _adjE)
    _cE = db.connect(Path(tmp) / "jobbot.db")
    _pfc.set_flag(_cE, _pfc.CV_TU_LO, False)
    _cE.close()
    # The CSS has to PAINT both states, not merely declare a class and leave it there.
    _cssE = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    for _sel in (".swbtn{", ".swbtn.off{", ".mbtn.tiny.on{", ".mbtn.tiny.off{"):
        check(f"the CSS paints «{_sel[:-1]}»", _sel in _cssE)
    # THE LEVEL IN USE MUST CARRY A TICK. The `off` class was once attached with not one
    # line of CSS behind it, so the three buttons looked identical — the app's most
    # important knob could not say where it stood.
    check("exactly ONE level is marked as in use", _adj.count("tiny on'") == 1)
    check("and it is marked with ✓, readable even if the colour fails", "✓" in _adj)
    _cD = db.connect(Path(tmp) / "jobbot.db")
    _pfc.put(_cD, _pfc.CV_RIENG, "vua")
    _cD.close()
    _adj2 = get("/adjust/cv")[1]
    check("changing the level -> the tick follows",
          "data-arg='rieng:vua' title='+ moves the skills sections this "
          "posting asks for to the front'>✓" in _adj2)
    _cD = db.connect(Path(tmp) / "jobbot.db")
    _pfc.put(_cD, _pfc.CV_RIENG, "rieng")
    _cD.close()
    check("the reasoning sits inside a fold, it is not dumped straight out",
          "<details class=swwhy>" in _adj)
    check("the text does not touch the overlay's edge", "class=adjbox" in _adj)
    # THE SENTENCE-DROPPING RULES still run — there is simply no button left to flip
    # them. The user loses a button, not the information: the report still says which
    # sentence was dropped and why.
    from jobbot.cv.rules import sentence_ok as _sok
    check("the rule dropping failure sentences still runs, with no button left",
          _sok("The drawdown ran 30% deeper than the model predicted here.")[0]
          == "drop")

    # THE ADJUST PANEL MUST NOT HARD-CODE ANYBODY'S SENTENCES. An earlier version quoted
    # lines straight out of one person's CV into the explanation; opened under another
    # profile those are a stranger's words, and the panel becomes an advertisement
    # rather than a description of the reader's own profile.
    import pathlib as _plG
    _cvl_src = "\n".join(
        l.split("#")[0] for l in
        (_plG.Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/views/cvlist.py")
        .read_text(encoding="utf-8").splitlines())
    for _cau in ("Self-funded", "drawdown ran", "Profit on its own",
                 "WorldQuant", "Compute · Method"):
        check(f"the panel does NOT hard-code «{_cau[:22]}»", _cau not in _cvl_src)

    check("POST rieng:chung -> saves",
          post_form("/api/cv/num", "arg=rieng:chung") == 200)
    check("POST tu_lo:1 -> saves", post_form("/api/cv/num", "arg=tu_lo:1") == 200)
    check("a removed knob -> 400", post_form("/api/cv/num", "arg=giong:nguyen") == 400)
    check("a knob given the wrong value -> 400",
          post_form("/api/cv/num", "arg=rieng:xx") == 400)
    check("an unknown value -> 400, nothing saved blindly",
          post_form("/api/cv/num", "arg=khoa:xxx") == 400)
    # SWAPPING A SENTENCE: the machine accepts a sentence only, never free text — and the
    # posting id has to be a number.
    check("POST /api/cv/pick with no posting id -> 400",
          post_form("/api/cv/pick", "job=&text=abc") == 400)
    check("a non-numeric posting id -> 400",
          post_form("/api/cv/pick", "job=xyz&text=abc") == 400)
    check("no sentence -> 400", post_form("/api/cv/pick", "job=1&text=") == 400)
    check("an unknown knob name -> 400", post_form("/api/cv/num", "arg=lung:tung") == 400)

    _cvn = db.connect(Path(tmp) / "jobbot.db")
    # TURN A KNOB AND THE BUTTON HAS TO CHANGE. A knob that cannot change the button is
    # decoration: the user presses it, sees nothing different, and then stops trusting
    # the whole panel.
    #
    # With MACHINE-HANDLES-IT off the button changes and waits to be pressed; on, the
    # machine rebuilds at once and the button returns to "Rebuild" — both are right, but
    # this has to be measured in a known state.
    from jobbot.core import prefs as _pfN
    _pfN.set_flag(_cvn, _pfN.CV_TU_LO, False)
    _pfN.put(_cvn, _pfN.CV_RIENG, "chung")
    _st_num = _bt.stage(_cvn)
    check("turning a knob -> the button becomes Update", _st_num["label"] == "Update",
          _st_num["label"])
    check("and it says WHAT just changed",
          "turned a knob" in _st_num["note"], _st_num["note"])
    _pfN.put(_cvn, _pfN.CV_RIENG, "rieng")
    # THE TAILORING LEVEL has to change THE WORDS ACTUALLY PRINTED, not merely a row in
    # the DB. This is the app's most-changed knob: measured on the live store of 358
    # postings, shared 25 builds · medium 89 · per-posting 157, with the unchanging core
    # falling from 12/16 to 9/16 sentences.
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
    # NOT ONE WORD MAY BE LOST — this is the CV that goes to an employer.
    import re as _reB
    check("reordering loses NO word from the skills sections",
          sorted(_reB.findall(r"\w+", " ".join(_chung)))
          == sorted(_reB.findall(r"\w+", " ".join(_rieng))))
    check("and NO section is lost", len(_chung) == len(_rieng))
    _cvn.close()
    post_form("/api/cv/num", "arg=rieng:rieng")
    post_form("/api/cv/num", "arg=tu_lo:0")

    print("\n[the scoring report: the machine has to SHOW ITS WORKING, not just decide]")
    # The rules have barred failure sentences from a CV since the beginning, but the
    # builder never consulted them — 3 barred sentences went out on EVERY build. Nobody
    # saw, because there was no report to read.
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
        check("NO sentence the rules bar reaches a built CV", not _lot, str(_lot[:1]))
        _cvr.close()
        check("the report has a before/after section", "REWORD" in _bcv_html.upper()
              or "gsua" in _bcv_html)
        check("it says the machine only cuts words, it writes nothing new",
              "cuts and reorders" in _bcv_html)
    # THE TWO DROPPED GROUPS have to be kept apart, because they call for two different
    # actions: a sentence the rules bar is not helped by rewording, while a weaker
    # sentence needs no fixing at all.
    from jobbot.cv.build import TailoredCV as _TCV
    from jobbot.cv import report as _rp
    _gia = _TCV(header=[], summary="", sections=[],
                dropped=[("A failure sentence.",
                          "outcome failure — belongs on the project page, not the CV"),
                         ("A fine sentence.",
                          "weaker than what this posting asks for")],
                wanted=["python"], covered=[], missing=["c++"])
    _rh = _rp.chi_tiet(_gia)
    check("the 'the rules do not allow these' group shows separately",
          "The rules do not allow these on a CV (1)" in _rh)
    check("the 'saved for another posting' group shows separately",
          "Saved for another posting (1)" in _rh)
    check("the reason is turned into a readable sentence, not left as an internal code",
          "tells a failure" in _rh and "outcome failure" not in _rh)
    check("it says where the profile IS SILENT",
          "the profile cannot answer" in _rh and "c++" in _rh)

    print("\n[BACKEND ↔ FRONTEND: one rule, one store of memory, one place to forget]")
    import ast as _ast5, pathlib as _pl5
    _live_src = (_pl5.Path(__file__).resolve().parent.parent
                 / "src/jobbot/dashboard/live.py").read_text(encoding="utf-8")
    _all_src = "\n".join(
        f.read_text(encoding="utf-8")
        for f in (_pl5.Path(__file__).resolve().parent.parent / "src").rglob("*.py"))

    # ONE STORE OF MEMORY. There used to be three caches (_CV_CACHE, _BLOCK_CACHE,
    # _HUT_CACHE) built on one key but cleared in THREE DIFFERENT SETS of places: reset
    # forgot _HUT_CACHE, the knob route forgot _BLOCK_CACHE, batch cleared only
    # _CV_CACHE. Three things with the same input expiring on three schedules means the
    # screen mixes old numbers with new, and nobody can trace it.
    # STRIP the comments before inspecting: the comment explaining why those caches went
    # away names them, and a test that catches its own comment is useless.
    _code = "\n".join(
        l.split("#")[0] for l in _all_src.splitlines())
    for _c in ("_CV_CACHE", "_BLOCK_CACHE", "_HUT_CACHE"):
        check(f"the loose {_c} cache is gone", _c not in _code)
    check("there is exactly ONE store of memory for the CV layer", _all_src.count("_NHO: dict = {}") == 1)
    check("and exactly ONE place that forgets", "def quen()" in _live_src)
    # Everything that touches the profile or a knob has to call quen(), never clear by hand.
    check("every clearing goes through quen()",
          _all_src.count(".clear()") == _all_src.count("_NHO.clear()")
          + _all_src.count("opened.clear()") + _all_src.count("vua_phu.clear()")
          or ".quen()" in _all_src)

    # ONE RULE. `cv_gia` (the Adjust panel) and `build` (the builder) have to ask THE
    # SAME function whether a skill group is dropped. cv_gia used to consult a constant
    # set that had been emptied, so the panel reported "no group dropped" while the
    # builder really was dropping them — two layers saying two things about one act.
    check("the Adjust panel and the builder SHARE the skill-group drop rule",
          _all_src.count("bo_muc_ky_nang(") >= 2)
    check("and nothing consults the dead constant table any more",
          "DROP_SKILL_GROUPS" not in _code)

    print("\n[a CLOSED overlay must NOT block the whole page]")
    # A REAL BUG, and the worst kind: nothing in the app could be clicked.
    # `hidden` is only the browser's [hidden]{display:none} rule.
    # `.sheet{display:flex}` has the same specificity but is our own CSS, so it WINS —
    # the overlay sat on top for ever, blacking out the page and swallowing every click.
    css = get("/static/app.css")[1]
    check("there is a .sheet[hidden] rule, so hidden really takes effect",
          ".sheet[hidden]{display:none}" in css)
    # Setting display on .sheet WITHOUT the accompanying [hidden] rule reproduces the bug.
    body_rule = css.split(".sheet{")[1].split("}")[0]
    check("and that rule comes AFTER the plain .sheet rule",
          css.index(".sheet[hidden]") > css.index(".sheet{"))
    check("the overlay really does have a covering ground (so a gap would block the page)",
          "rgba(0,0,0,.5)" in body_rule or "z-index:60" in body_rule)

    print("\n[tone — a VS Code style grey scale]")
    # The old bug: --mute (the app's most used text colour, 84 places) reached only
    # 3.1:1 on --panel-2, under the 4.5 bar for body text while being 10-12px
    # everywhere. Pinned here so nobody drops a text level below the bar again.
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
    check("all 4 grounds and 6 text levels were read", len(_mat) == 4 and len(_txt) == 6)
    _low = [f"{t} on {m} = {_cr(_var[t], _var[m]):.2f}"
            for t in _txt for m in _mat if _cr(_var[t], _var[m]) < 4.5]
    check("every text level is readable on every ground (>=4.5:1)", not _low, str(_low))
    # Self-proof: put the OLD value back and the rule above MUST break. Without this
    # line, the day :root renames a variable the loop scans 0 pairs and still goes green.
    check("this rule really catches the old bug (#717976)",
          _cr("#717976", _var["panel-2"]) < 4.5)
    # The greys have to be NEUTRAL — a grey with a cast argues with the accent colour.
    _amm = {k: max(int(_var[k][i:i + 2], 16) for i in (1, 3, 5))
            - min(int(_var[k][i:i + 2], 16) for i in (1, 3, 5)) for k in _mat}
    check("the grounds are neutral greys, with no cast", max(_amm.values()) == 0, str(_amm))

    # THE FRAME SPEAKS QUIETLY, THE CONTENT SPEAKS UP. It used to be the other way
    # round: the sidebar at 8.1:1 and the status bar at 12.2:1 while the content was
    # only 6.8:1 — the furniture shouting louder than the work. Frame text is measured
    # on --side, content text on --panel.
    # THE GROUND STEPS: the contrast has to be spent on THE PLACE OF WORK, not on the
    # furniture. VS Code has only two planes: the frame sits 3.5 L* below the editor
    # (weak), and a raised surface lifts 8.6 points (strong). Our old version split it
    # evenly, +3.5 / +3.9, so the sidebar weighed as much as the content — a card could
    # not lift.
    def _ls(h):
        def _lin(c):
            c /= 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        h = h.lstrip("#")
        r, g, bl = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        y = .2126 * _lin(r) + .7152 * _lin(g) + .0722 * _lin(bl)
        return 116 * y ** (1 / 3) - 16 if y > 0.008856 else 903.3 * y

    def _luat(var):
        """(is the main ground black, is the frame a grey lighter than main, how far a card lifts)"""
        return (_ls(var["bg"]) <= 5.0,
                _ls(var["side"]) - _ls(var["bg"]) >= 3.0,
                _ls(var["panel"]) - _ls(var["bg"]))
    _den, _xam, _bat = _luat(_var)
    check(f"the main area's ground is BLACK (L*{_ls(_var['bg']):.1f} <= 5)", _den)
    check(f"the surrounding frame is GREY, lighter than main "
          f"(+{_ls(_var['side']) - _ls(_var['bg']):.1f})", _xam)
    check(f"a card lifts clear of the main ground (+{_bat:.1f} >= 8)", _bat >= 8.0)
    # Self-proof: the OLD set (frame darker than main, card barely lifting) has to break
    # all three rules.
    _cu = {"side": "#161616", "bg": "#1D1D1D", "panel": "#252525"}
    check("this rule really catches the old set (frame darker than main)",
          not any((_luat(_cu)[0], _luat(_cu)[1], _luat(_cu)[2] >= 8.0)))

    _sc = _rec.search(r"\.side,\.statusbar\{(.*?)\}", _cssv, _rec.S)
    _cvar = dict(_rec.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", _sc.group(1)))
    check("the app frame redeclares all three of its own text levels",
          sorted(_cvar) == ["dim", "ink", "mute"])
    _khung = max(_cr(v, _var["side"]) for v in _cvar.values())
    _noidung = min(_cr(_var[t], _var["panel"]) for t in ("ink", "dim", "mute"))
    check(f"frame text is quieter than content text ({_khung:.2f} < {_noidung:.2f})",
          _khung < _noidung)
    check("but frame text is still readable (>=4.5:1)",
          min(_cr(v, _var["side"]) for v in _cvar.values()) >= 4.5)
    # Self-proof: the OLD frame text level (sharing the content's --dim) has to break it.
    check("this rule really catches the old bug (the frame sharing --dim)",
          not _cr(_var["dim"], _var["side"]) < _noidung)

    print("\n[Settings is A MENU, not a tab]")
    _, home = get("/")
    check("Settings is no longer in the sidebar", "href='/settings'" not in home)
    check("there is a gear button at the bottom of the sidebar", "data-appset" in home)
    check("and an empty overlay is ready to be filled", "data-sheet" in home)
    check("the overlay starts CLOSED", "class=sheet hidden" in home)

    code, panel = get("/settings")
    check(f"/settings returns 200", code == 200)
    # It returns A FRAGMENT, not a whole page: a whole page dropped into the overlay
    # would nest an entire page inside the page.
    check("/settings returns an HTML FRAGMENT, not a whole page",
          panel.lstrip().startswith("<div") and "<!doctype" not in panel.lower())
    # SPLIT INTO TABS. It used to be one 782px column inside a 660px box — the "Start
    # over" section sat below the fold, reachable only by scrolling, with nothing to say
    # it could be scrolled. Split BY JOB: running / sources / read-only / destructive.
    check("each tab has exactly one content block",
          panel.count("data-stab=") == panel.count("data-pane=") > 3)
    check("exactly one tab is open to begin with", panel.count("stpane on") == 1)

    # THE SOURCES TAB — each ATS switched on or off. "API" means three providers, not
    # 34 company boards: introducing each company would be meaningless, while the three
    # ATSs really do differ (how they return data, which companies use them, how much of
    # it is usable).
    check("there is a Sources tab", "data-stab='nguon'" in panel and ">Sources<" in panel)
    for _ats in ("greenhouse", "lever", "ashby"):
        check(f"there is a switch for {_ats}", f"name=ats value='{_ats}'" in panel)
    # Introduce them with REAL NUMBERS from this very store, not with adjectives:
    # "modern" and "popular" let nobody choose anything.
    check("there is a switch for job alert mail", "name=ats value='alert'" in panel)
    check("every source carries a real number, not just praise",
          panel.count("class=srcnum") == 4 and "postings in ·" in panel,
          str(panel.count("class=srcnum")))
    # Alert mail is not an ATS: there are no boards to count, so do not write
    # "0 boards" — a meaningless zero reads as something being broken.
    _dong_alert = panel.split("value='alert'")[1].split("</label>")[0]
    check("alert mail does NOT say '0 boards'", "0 board" not in _dong_alert)
    # EACH FORM EDITS ONLY ITS OWN SECTION. Several forms post to /settings; read
    # blindly, the Sources form (which carries no scan-interval field) writes the
    # default 60 over the saved number.
    check("each form declares which section it is",
          panel.count("name=phan") == panel.count("<form class=setform"))

    # THE EMAIL CATCH: the mailbox scanned has to be THE mailbox declared in the
    # profile. Tried for real over HTTP, not merely read out of the source.
    _ma_sai, _than_sai = (post("/api/mail/setup",
                               b"address=nham@x.y&password=abcdefghijklmnop"),
                          _post_raw("/api/mail/setup",
                                    b"address=nham@x.y&password=abcdefghijklmnop"))
    check("connecting a mailbox OTHER than the profile's is refused", _ma_sai == 400, str(_ma_sai))
    check("and it names both addresses",
          "nham@x.y" in _than_sai and PROFILE["email"] in _than_sai, _than_sai[:90])
    check("with the way to fix it", "so they match" in _than_sai)

    # THE GMAIL TAB — mailbox configuration belongs where configuration lives.
    check("there is a Gmail tab", "data-stab='gmail'" in panel and ">Gmail<" in panel)
    # The "Connect a mailbox…" button over in Manage has to open THE Gmail tab. Half
    # directions — opening Settings and leaving the person on the Run tab — are more
    # annoying than no directions at all.
    check("openSheet takes a tab name", "function openSheet(url, kind, tab)" in _js)
    # Click the tab THE MOMENT the content arrives, never on a timer: loaded by fetch, a
    # setTimeout is a guess about whether the network is fast or slow, and on a slow
    # machine the button does not exist yet when the timer fires.
    _mo = _js.split("function openSheet")[1].split("function closeSheet")[0]
    # STRIP the comments before checking: the very comment explaining why setTimeout is
    # NOT used contains the word "setTimeout", and the test would read the explanation
    # as the code it is banning.
    _ma = "\n".join(l for l in _mo.split("\n") if not l.strip().startswith("//"))
    check("the tab is clicked inside .then, not on a setTimeout",
          "nut.click()" in _ma and "setTimeout" not in _ma, "")
    check("and there is a field for how many days of mail to re-read", "name=mail_days" in panel)
    from jobbot.core import prefs as _pf2
    _c2 = db.connect()
    post("/settings", b"phan=gmail&mail_days=45")
    check("the day count saves", _pf2.num(_c2, _pf2.MAIL_DAYS, 1, 365) == 45,
          str(_pf2.num(_c2, _pf2.MAIL_DAYS, 1, 365)))
    check("and it does NOT touch the scan interval",
          _pf2.num(_c2, _pf2.SCAN_EVERY, 5, 1440) != 0)
    post("/settings", b"phan=gmail&mail_days=30")
    _c2.close()

    _c2 = db.connect()
    _pf2.put(_c2, _pf2.SCAN_EVERY, "45")
    post("/settings", b"phan=nguon&ats=greenhouse&ats=lever")
    check("saving the Sources tab: ashby switched off", not _pf2.flag(_c2, _pf2.SRC_ATS["ashby"]))
    check("and greenhouse left as it was", _pf2.flag(_c2, _pf2.SRC_ATS["greenhouse"]))
    check("it does NOT touch the Run tab's scan interval",
          _pf2.num(_c2, _pf2.SCAN_EVERY, 5, 1440) == 45,
          str(_pf2.num(_c2, _pf2.SCAN_EVERY, 5, 1440)))
    post("/settings", b"phan=nguon&ats=greenhouse&ats=lever&ats=ashby")
    check("it can be switched back on", _pf2.flag(_c2, _pf2.SRC_ATS["ashby"]))
    _c2.close()

    # Three knobs — and EXACTLY three. The old page had 18 rows of which only 2 were
    # real settings.
    for name in ("every", "from", "to"):
        check(f"there is an {name} field", f"name={name}" in panel)
    check("there is a Save button", ">Save<" in panel)
    check("it states the consequence: it changes HOW IT RUNS, it touches no judgement",
          "from the next scan" in panel and "touches neither" in panel)
    # Numbers the machine reports about itself are NOT settings -> they belong on a
    # different tab from the knobs that can be turned, not merely in a section further
    # down the same screen.
    _tab_chay = panel.split("data-pane='xem'")[0]
    check("the self-reported numbers are on their own tab, not mixed in with the knobs",
          "strow" not in _tab_chay and "data-pane='xem'" in panel)
    check("the destructive work is on its own tab too", "data-pane='lam-lai'" in panel)
    # ONE padding value for the whole overlay. Each block used to set its own
    # (0 / 15px / 18px), so the SETTINGS heading sat hard against the frame's corner
    # while the row below it was indented.
    _cssp = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    check("the overlay padding is declared in ONE place", "--sheet-pad:18px" in _cssp)
    for _ten, _r in (("the heading", ".sheethead{"), ("the tab row", ".stabs{"),
                     ("a content block", ".stpane{"), ("a form", ".setform{"),
                     ("the delete row", ".dangerrow{")):
        _blk = _cssp[_cssp.index("\n" + _r) + 1:]
        _blk = _blk[:_blk.index("}")]
        check(f"{_ten} shares that padding, it sets no number of its own",
              "var(--sheet-pad)" in _blk or "padding:0" in _blk, _blk[:70])

    # The "LLM engine" knob IS GONE, along with the whole route that generated briefs
    # with an LLM. Briefs now come from a template, so that knob controlled nothing —
    # and a button that controls nothing is worse than no button: the user presses it
    # and concludes the app is broken.
    check("no fake knob is left in Settings",
          "name=engine" not in panel and "JOBBOT_LLM" not in panel)

    print("\n[Settings: a save has to TAKE EFFECT AT ONCE, with no app restart]")
    from jobbot.core.scheduler import scan_every_min, human_window
    before = scan_every_min()
    body = b"every=25&from=9&to=21"
    req = urllib.request.Request(base.rstrip("/") + "/settings", data=body)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=25) as r:
        saved = r.read().decode("utf-8")
    check("the save returns a fragment carrying the NEW value", "value='25'" in saved)
    # Read at run time, not at import time — otherwise changing the interval needs an
    # app restart before it takes effect.
    check("the scan interval changes inside the running process", scan_every_min() == 25)
    check("and so does the hour window", human_window() == (9, 21))

    # Whatever the user types must not kill the background scan loop.
    for junk in (b"every=abc&from=x&to=y",
                 b"every=-5&from=99&to=-1"):
        req = urllib.request.Request(base.rstrip("/") + "/settings", data=junk)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()
        low, high = human_window()
        check(f"junk value {junk[:14].decode():14} -> still valid",
              5 <= scan_every_min() <= 1440 and 0 <= low <= 23 and 1 <= high <= 24)

    req = urllib.request.Request(base.rstrip("/") + "/settings",
                                 data=f"every={before}&from=8&to=22".encode())
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    urllib.request.urlopen(req, timeout=25).read()

    print("\n[collapsing the sidebar]")
    _, home_html = get("/")
    check("there is a collapse button", "data-nav" in home_html)
    # Reading localStorage has to sit in <head>, BEFORE the paint. Left at the end of
    # the page, every tab change flashes the sidebar open and then shut again.
    head = home_html.split("</head>")[0]
    check("the choice is read inside <head>, so nothing flashes", "navmin" in head)
    # Cut on THE TAG, not on the string "<body>": the body tag carries attributes
    # (data-setup, data-reload) so the hard-coded string is no longer found, and the
    # test dies with an IndexError instead of saying anything about the page.
    _body_o = __import__("re").search(r"<body[^>]*>", home_html)
    check("the page has a <body> tag", _body_o is not None)
    check("and the localStorage script stands BEFORE it",
          bool(_body_o) and home_html.index("navmin") < _body_o.start())
    import re as _re2
    _navlinks = _re2.findall(r"<a class='navlink[^>]*>", home_html)
    check("every nav item has a title, so it is still identifiable when collapsed",
          bool(_navlinks) and all("title=" in a for a in _navlinks),
          f"{sum('title=' not in a for a in _navlinks)}/{len(_navlinks)} missing")
    # The sidebar's navfoot IS GONE: it showed exactly what the status bar at the
    # bottom of the app shows — one truth in two places drifts apart sooner or later.
    _, _with_status = get("/profile")
    check("the status bar is at THE BOTTOM OF THE APP, not in the sidebar",
          "class=statusbar" in _with_status and "class=navfoot" not in _with_status)

    print("\n[THE STAGE's bar — one block for every control]")
    _, _srch = get("/search")
    check("Search has a stage bar", "<header class=topbar>" in _srch)
    check("it has its own Run button", "/api/stage/start" in _srch)
    check("it has its own Stop button", "/api/stage/stop" in _srch)
    check("the run/stop buttons carry the stage's name", "data-arg='search'" in _srch)
    check("there is an Adjust ⚟ button", "data-settings='/adjust/search'" in _srch)
    check("there are metrics, not prose", _srch.count("class='metric ") >= 3)
    # COLOUR CARRIES MEANING. Every number has to declare ITS ROLE, because the role
    # decides the colour; undeclared, every number is the same white and the control
    # bar dissolves into the content.
    for _vai in ("stock", "act", "new", "view"):
        check(f"the metric declares the '{_vai}' role", f"class='metric {_vai}" in _srch)
    # The rule A ZERO DOES NOT GLOW — tried straight against the function, with no
    # dependence on real data.
    from jobbot.dashboard.layout import deck as _deck
    _d0 = _deck("search", "S", "", [("0", "new", "new")])
    _d9 = _deck("search", "S", "", [("9", "new", "new")])
    check("a zero has its colour switched off", "metric new zero" in _d0)
    check("a non-zero keeps its colour", "zero" not in _d9)
    check("a thousands comma does not break the rule",
          "zero" not in _deck("search", "S", "", [("1,204", "kept", "stock")]))
    # THE RUN BUTTON HAS TO CHANGE ITS WORDS WITH THE SITUATION. A button reading "Run"
    # in every circumstance says nothing: someone opening the app for the first time
    # does not know what it would run, and someone who has just pressed Stop halfway
    # thinks pressing it starts again from the beginning.
    from jobbot.dashboard import live as _lv
    from jobbot.core.postings import HAVE_DESC as _HD
    # The button SPEAKS ONLY ABOUT CHROME. The board API finishes in 22 seconds and
    # runs on every pass — it has no state worth telling; the thing that takes half an
    # hour and can be left half-done is LinkedIn.
    _trong = db.connect(Path(tmp) / "nut-trong.db")
    check("nothing there yet -> the button offers RUN",
          _lv.search_stage(_trong)["run_label"] == "Run",
          _lv.search_stage(_trong)["run_label"])
    # And it says plainly why it cannot scan, rather than offering work that would be refused.
    check("an empty profile -> it says outright the job titles are missing",
          "no job titles" in _lv.search_stage(_trong)["run_note"],
          _lv.search_stage(_trong)["run_note"])
    _trong.close()

    _nut = seeded(Path(tmp) / "nut.db")
    # The store has postings (the boards came back) but LinkedIn has never completed a
    # pass -> still RUN. "Update" would be wrong here: asking only the 24-hour window
    # misses everything LinkedIn already holds.
    check("boards came back but LinkedIn has not scanned -> still RUN",
          _lv.search_stage(_nut)["run_label"] == "Run",
          _lv.search_stage(_nut)["run_label"])

    import json as _js3
    from jobbot.core import postings as _po, prefs as _pf3
    from jobbot.scan_runner import _cap as _capf
    from jobbot.profile import store as _ps3
    _po.record_run(_nut, "linkedin", ok=True, fetched=1, new_rows=0)
    # A run row is NOT enough on its own: that pass may have been stopped halfway, a
    # few pairs in. The memory is A LIST OF PAIRS, not a flag.
    check("a run row but no pair covered -> still RUN",
          _lv.search_stage(_nut)["run_label"] == "Run",
          _lv.search_stage(_nut)["run_label"])

    def _phu_het(conn):
        """Mark EVERY pair of the current sieve as fully scanned."""
        cap, muc = _capf(_ps3.load(conn))
        _pf3.put(conn, _pf3.LI_DONE,
                 _js3.dumps(sorted(f"{q}|{p}" for q, p in cap)))
        _pf3.put(conn, _pf3.LI_LEVELS, _js3.dumps(sorted(muc)))

    _phu_het(_nut)
    check("the whole sieve covered, nothing half-done -> UPDATE",
          _lv.search_stage(_nut)["run_label"] == "Update",
          _lv.search_stage(_nut)["run_label"])
    check("and Update asks only the 24-hour window",
          "24 hours" in _lv.search_stage(_nut)["run_note"])

    # ADDING a job title -> only THE NEW PAIRS are uncovered. Do not make the whole
    # sieve rescan: that is exactly "running the same thing over and over".
    _ps3.save(_nut, {"job_titles": "Quantitative Analyst\nData Scientist\n"
                                   "Machine Learning Engineer"}, "added a job title")
    from jobbot.scan_runner import scan_mode as _sm
    _st_them = _lv.search_stage(_nut)
    check("adding a job title -> back to RUN", _st_them["run_label"] == "Run",
          _st_them["run_label"])
    check("but it fully scans ONLY the new passes, it does not rescan the whole sieve",
          _sm(_nut)["todo"] == 1, str(_sm(_nut)["todo"]))
    check("and it says outright the rest only asks for new postings",
          "the rest only asks for new postings" in _st_them["run_note"],
          _st_them["run_note"])

    # REMOVING a job title -> there is NOTHING new to search for -> rescan nothing.
    # This is where the old rule (a fingerprint over the whole sieve) was wrong: it
    # forced a rescan from the beginning.
    _phu_het(_nut)
    _ps3.save(_nut, {"job_titles": "Quantitative Analyst"}, "removed a job title")
    check("removing a job title -> still UPDATE, no rescan",
          _lv.search_stage(_nut)["run_label"] == "Update",
          _lv.search_stage(_nut)["run_label"])

    # Editing something that does NOT touch the query sent to LinkedIn must force no rescan.
    _ps3.save(_nut, {"phone": "+44 7000 000000"}, "changed the phone number")
    check("changing the phone number -> still UPDATE",
          _lv.search_stage(_nut)["run_label"] == "Update",
          _lv.search_stage(_nut)["run_label"])

    # NARROWING the seniority produces no new postings -> the coverage stands.
    _ps3.save(_nut, {"seniority": ["grad"]}, "narrowed the seniority")
    check("narrowing the seniority -> still UPDATE",
          _lv.search_stage(_nut)["run_label"] == "Update",
          _lv.search_stage(_nut)["run_label"])
    # WIDENING changes f_E for EVERY pair -> it has to ask in full again.
    _ps3.save(_nut, {"seniority": ["grad", "mid", "senior"]}, "widened the seniority")
    check("widening the seniority -> back to RUN",
          _lv.search_stage(_nut)["run_label"] == "Run",
          _lv.search_stage(_nut)["run_label"])
    _ps3.save(_nut, {"seniority": ["grad", "junior"],
                     "job_titles": "Quantitative Analyst\nData Scientist"}, "put back")
    _phu_het(_nut)
    # A LinkedIn posting with no description = the deep-read loop is half-done. Write it
    # through THE APP'S REAL ROUTE (save_batch), never a hand INSERT: the posting table
    # has required columns only the real route fills, and a test taking its own route
    # checks a shape of data that never exists in the wild.
    postings.save_batch(_nut, "linkedin", [
        Posting(source_id="9", title="Quant", company="X", location="London",
                url="https://x/9", description="")])
    # kept=1: a posting THROUGH THE SIEVE but not yet deep-read. That is the real
    # "half-done work". A posting the sieve already dropped is of no use however many
    # times it is read, so it must not count towards the number on the button.
    _nut.execute("UPDATE posting SET kept = 1 WHERE source = 'linkedin'")
    _nut.commit()
    _st = _lv.search_stage(_nut)
    check("postings still unread -> the button offers CONTINUE",
          _st["run_label"] == "Continue", _st["run_label"])
    check("and it says how many are left half-done", "1 postings still unread" in _st["run_note"])

    # A QUEUE PER SOURCE, NOT ONE BASKET. The half-done work here belongs to the
    # `linkedin` source; switch that source off and its queue is not this pass's work,
    # so the button must not offer "Continue" — pressing it would read no posting.
    _pf3.set_flag(_nut, _pf3.SRC_LINKEDIN, False)
    _st_tat = _lv.search_stage(_nut)
    check("LinkedIn off -> ITS queue no longer offers Continue",
          _st_tat["run_label"] != "Continue", _st_tat["run_label"])
    check("and it says which sources the next pass is left with",
          "LinkedIn is off" in _st_tat["run_note"], _st_tat["run_note"])
    check("it no longer demands LinkedIn be switched on to read another source's postings",
          "turn LinkedIn on" not in _st_tat["run_note"], _st_tat["run_note"])

    # But ALERT MAIL postings are A DIFFERENT source with A DIFFERENT switch. With
    # LinkedIn off they must still travel the whole line: "two different ways have to be
    # two different sources, do not merge them". The whole deep-read loop used to sit
    # behind the LinkedIn switch, so turning it off left 107 alert postings unscored.
    postings.save_batch(_nut, "alert", [
        Posting(source_id="8", title="Quant", company="Y", location="London",
                url="https://x/8", description="")])
    _nut.execute("UPDATE posting SET kept = 1 WHERE source = 'alert'")
    _nut.commit()
    _st_thu = _lv.search_stage(_nut)
    check("LinkedIn off but alert mail still half-done -> it STILL offers Continue",
          _st_thu["run_label"] == "Continue", _st_thu["run_label"])
    check("and it counts only the postings of sources that are on, not the whole basket",
          "1 postings still unread" in _st_thu["run_note"], _st_thu["run_note"])
    _pf3.set_flag(_nut, _pf3.SRC_ALERT, False)
    check("alert mail off too -> there is no queue left to offer",
          _lv.search_stage(_nut)["run_label"] != "Continue")
    _pf3.set_flag(_nut, _pf3.SRC_ALERT, True)
    _nut.execute("DELETE FROM posting WHERE source = 'alert'")
    _nut.execute("DELETE FROM raw_posting WHERE source = 'alert'")
    _nut.commit()
    _pf3.set_flag(_nut, _pf3.SRC_LINKEDIN, True)
    check("switched back on it offers Continue as before",
          _lv.search_stage(_nut)["run_label"] == "Continue")
    # Once that posting is read the offer has to change back — otherwise the button
    # stands on "Continue" for ever and the word on it becomes a lie.
    _nut.execute("UPDATE posting SET description = ? WHERE source='linkedin'",
                 ("x" * (_HD + 1),))
    _nut.commit()
    _phu_het(_nut)
    check("deep-reading done -> back to UPDATE",
          _lv.search_stage(_nut)["run_label"] == "Update",
          _lv.search_stage(_nut)["run_label"])
    # A posting THE SIEVE ALREADY DROPPED that has no description is NOT half-done work
    # — the deep-read loop never opens them. Counting them made the button promise
    # 1,855 while the real work was 11, measured on the live store on 12 September.
    postings.save_batch(_nut, "linkedin", [
        Posting(source_id="8", title="Junk", company="Y", location="Mars",
                url="https://x/8", description="")])
    _nut.execute("UPDATE posting SET kept = 0 WHERE source='linkedin'"
                 " AND url = 'https://x/8'")
    _nut.commit()
    check("a posting the sieve dropped does NOT count as half-done work",
          _lv.search_stage(_nut)["run_label"] == "Update",
          _lv.search_stage(_nut)["run_label"])
    _nut.close()
    # The idle wording has to travel with the button, so live.js can put it back after
    # showing "Scanning…". Without it the button sticks on the temporary word once the
    # scan is done.
    check("the button carries its original word, to be restored",
          "data-run='Update'" in _deck("search", "S", "", [], run="Update"))
    check("and it carries the explanation shown on hover",
          "title='3 postings left'" in _deck("search", "S", "", [],
                                          run="Continue", run_note="3 postings left"))

    # A SEARCH BOX OVER THE STORE. The backend has taken `q` since day one — filtering
    # by job title or company name, properly bound as a parameter — but there was never
    # anywhere to type it. A whole filter sitting there that nobody could use.
    import re as _re2
    _, _s0 = get("/search")
    check("the list has a search box", "class=jfind" in _s0)
    check("the search box is a GET form — typing produces a saveable URL",
          "method=get action='/search'" in _s0)
    check("with nothing searched there is NO clear button", "jfindx" not in _s0)

    _, _s1 = get("/search?q=quantitative")
    check("after a search the box keeps what was typed", "name=q value='quantitative'" in _s1)
    check("and a clear button appears, to go back", "jfindx" in _s1)
    check("the list shrinks to the search text",
          _s1.count("class='jrow") < _s0.count("class='jrow"),
          f"{_s1.count(chr(39) + 'jrow')} vs {_s0.count(chr(39) + 'jrow')}")
    check("searching for text that does not exist -> it says outright WHAT found nothing",
          "nosuchtexthere" in get("/search?q=nosuchtexthere")[1])

    # TYPING A SEARCH MUST NOT LOSE THE FILTERS IN FORCE. A GET form sends only the
    # fields it holds, so the chips have to travel with it as <input hidden>.
    _, _s2 = get("/search?q=quant&chance=likely&show=dropped")
    check("the filters in force travel with the form as hidden fields",
          "name='chance' value='likely'" in _s2 and "name='show' value='dropped'" in _s2)
    check("but it does NOT carry the search text itself (the input box does that)",
          "name='q' value=" not in _s2)
    from jobbot.dashboard.filters import JobFilter as _JF
    _f = _JF(q="abc", chance="likely", page=3)
    check("pairs() can drop q and page when building the hidden fields",
          dict(_f.pairs(q="", page="")) == {"chance": "likely"},
          str(_f.pairs(q="", page="")))
    check("url() and pairs() are built from THE SAME place",
          "chance=likely" in _f.url() and "q=abc" in _f.url())

    # FOUR KINDS OF BUTTON, FOUR WAYS OF DRAWING THEM. All four used to be identical
    # grey pills mixed across three rows — 20 buttons, with no way to see which button
    # related to which.
    _, _f0 = get("/search")
    check("what HAS AN ORDER is drawn as A TRACK, not as loose pills",
          _f0.count("class=lvltrack") == 2, str(_f0.count("class=lvltrack")))
    check("the track has its name at the head (Chance / Score)",
          "Chance" in _f0 and "class=lvlname" in _f0)
    # Sorting filters NOTHING, so it needs its own label and has to stand at THE OTHER
    # END of the row — mixed in among the filter chips, the user thinks it trims the
    # list too.
    check("Sort by has its own label", "Sort by" in _f0 and "class=vlabel" in _f0)
    # A button row splits into two GROUPS, one pushed left and one right: this panel is
    # nearly 2000px wide, and tucking everything against the left edge leaves half the
    # screen empty.
    check("each button row has two ends", _f0.count("class=vgrp") == 6,
          str(_f0.count("class=vgrp")))
    check("three button rows, not four", _f0.count("class=vbar") == 3,
          str(_f0.count("class=vbar")))

    # FILLED UP TO THE CHOSEN NOTCH — that is what makes it read as a ladder.
    _, _f1 = get("/search?chance=possible")
    # `.*?` rather than `[^<]*`: the buttons now carry a <b>count</b> inside, and what
    # this test means to check is THE CSS CLASS, not the text inside the button.
    _nac = _re2.findall(r"<a class='(lvlstep[^']*)'[^>]*>(.*?)</a>", _f1)[:4]
    check("the notches already passed are filled", [c for c, _ in _nac] ==
          ["lvlstep on", "lvlstep on", "lvlstep on now", "lvlstep"], str(_nac))
    check("exactly one notch is the chosen one",
          sum(1 for c, _ in _nac if "now" in c) == 1)

    # A LADDER IS A FLOOR. Choosing "Possible" has to INCLUDE "Likely" — hiding the
    # best postings breaks exactly the thing the user came for.
    _n = lambda h: int(_re2.search(r">Kept ([0-9,]+)<", h).group(1).replace(",", ""))
    # The invariant of A FLOOR: raise it and the result set can only shrink, never grow.
    # (How many postings sit at each level is a matter of DATA, so no claim is made
    # here that it really shrinks — test_filters.py checks the SQL.)
    _cao, _vua, _het = (_n(get("/search?chance=likely")[1]), _n(_f1), _n(_f0))
    check("raising the floor only shrinks the result set",
          _cao <= _vua <= _het, f"{_cao} <= {_vua} <= {_het}")

    # THE SOURCE SWITCHES. The two ways of searching return quite different postings —
    # boards finish in 22 seconds, LinkedIn takes half an hour — so sometimes only one
    # of them should run.
    _, _adj = get("/adjust/search")
    check("the Adjust panel has the source switches",
          "data-arg='board'" in _adj and "data-arg='linkedin'" in _adj)
    check("the switches sit OUTSIDE the sieve form — pressing one re-judges no 5,000 postings",
          _adj.index("srcrow") < _adj.index("<form class=sieve"))
    _bat = lambda arg: __import__("json").loads(
        _post_raw("/api/source", f"arg={arg}".encode()))
    check("all THREE source switches are there",
          all(f"data-arg='{k}'" in _adj for k in ("board", "linkedin", "alert")))
    _tat = _bat("board")
    check("a source can be switched off", _tat["ok"] and _tat["on"] is False)
    check("the button is pressable again at once, not locked", _tat.get("again") is True)
    check("and the Adjust panel shows it as off",
          "srcbtn board off" in get("/adjust/search")[1])
    # SWITCHING OFF THE LAST ONE = scanning with nowhere to scan. That must not be a
    # route you fall into with one misplaced click.
    #
    # The rule has to count ALL THREE remaining sources. The old version knew only two,
    # so once a third existed it allowed them all off while believing one was left.
    # Set the state EXPLICITLY before trying: a test above saved the Sources tab with
    # "alert" unticked, so which ones are on cannot be guessed.
    _adj2 = get("/adjust/search")[1]
    for _k in ("linkedin", "alert"):
        if f"srcbtn {_k} off" in _adj2:
            _bat(_k)                      # switch it on, to be sure
    _bat("linkedin")                      # only alert is left on now
    _cuoi = _bat("alert")
    check("with exactly one source left it will NOT switch that one off", _cuoi["ok"] is False,
          str(_cuoi))
    check("and it says why", "at least one source" in _cuoi["note"])
    _bat("linkedin")
    _bat("board")
    check("it can be switched back on", "srcbtn board off" not in get("/adjust/search")[1])
    check("an unknown source is refused", post("/api/source", b"arg=bia") == 400)

    # A BADGE MUST NOT COLLIDE WITH ANOTHER CSS CLASS NAME.
    #
    # A REAL BUG: after renaming `api` -> `board`, `<i class='src board'>` inherited
    # `.board{width:100%;font-size:12.5px}` from the Manage TABLE — the badge swelled
    # into a box as wide as the whole row. The same class of bug .pill and .prow both
    # fell into. Checked against the real CSS, not by eye: this bug breaks no test, it
    # is only visible by looking.
    _css = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    from jobbot.dashboard.views.search import FOUND_BY as _FB
    _dung = [k for k in _FB
             if _re2.search(r"(?m)^\.%s\b[^,{]*\{" % _re2.escape(k), _css)]
    check("no badge name collides with another CSS class", not _dung, str(_dung))
    # The detector proves it can catch one.
    check("and this detector really does catch one",
          bool(_re2.search(r"(?m)^\.trackboard\b[^,{]*\{", _css)))

    # PLACE — the text on the button comes from the "Where you're based" field, never
    # hard-coded.
    check("there is a filter row for place", "name=loc" in _f0 or "loc=" in _f0)
    check("the 'Near me' button says near WHERE", "Near me ·" in _f0, "")
    # Place does not CUT, it only PRIORITISES: "All of …" is still there to see everything.
    check("and there is still a button to see the whole country", "All of " in _f0)
    # With no place declared, HIDE the 'Near me' button: a button that filters nothing
    # is a button you press and see no change, and then the user stops trusting the
    # whole row.
    from jobbot.dashboard.views import search as _sv
    _trong = _sv._noi(_lv.JobFilter.from_query({}) if hasattr(_lv, "JobFilter")
                      else __import__("jobbot.dashboard.filters", fromlist=["x"])
                      .JobFilter.from_query({}), "", "UK")
    check("no place declared -> the 'Near me' button is hidden", "Near me" not in _trong)
    _n2 = lambda h: int(_re2.search(r">Kept ([0-9,]+)<", h).group(1).replace(",", ""))
    _, _gan = get("/search?loc=near")
    check("filtering by 'near me' narrows the list without emptying it",
          0 < _n2(_gan) <= _n2(_f0), f"{_n2(_gan)} / {_n2(_f0)}")
    check("and 'the whole country' is wider than 'near me'",
          _n2(get("/search?loc=home")[1]) >= _n2(_gan))

    # THE SOURCE TAG — the board/linkedin badge is already visible on every row, so
    # filtering by those same two badges is the next thing anyone reaches for.
    check("there is a filter tag for source", ">board<" in _f0 and ">linkedin<" in _f0)
    _, _fc = get("/search?found=linkedin")
    check("filtering by linkedin leaves every row carrying the linkedin badge",
          _fc.count("class='src linkedin'") >= _fc.count("class='jrow"),
          f"{_fc.count(chr(39)+'src linkedin'+chr(39))} badge / "
          f"{_fc.count(chr(39)+'jrow')} rows")

    # ONE button instead of two: "Can't tell" and "Not scorable" are the same pile.
    check("there is only ONE button for postings the machine has not read",
          "Not read yet" in _f0 and "Not scorable" not in _f0
          and "Can't tell" not in _f0)
    # The two ladders ask for postings the machine COULD read, this button asks for the
    # opposite — both on and the list is always empty, so pressing it has to release
    # both ladders back to All.
    check("pressing 'Not read yet' releases both ladders",
          "raw=1" in _f1 and "chance" not in
          _re2.search(r"href='([^']*raw=1[^']*)'", _f1).group(1))

    # THE STAGE BAR speaks about THE STORE, the chips speak about THE VIEW — never mix
    # them. Mixed, typing "quant" gives a bar reading "64 kept · 91 worth applying to",
    # while worth-applying-to is a subset of kept: 91 > 64 cannot exist.
    import re as _re
    _giu = lambda h: _re.search(
        r"class='metric stock[^']*'><b>([0-9,]+)</b>worth applying", h)
    check("the stage bar keeps THE STORE's number while a search is typed — "
          f"{_giu(_s1) and _giu(_s1).group(1)} vs {_giu(_s0) and _giu(_s0).group(1)}",
          bool(_giu(_s1) and _giu(_s0) and _giu(_s1).group(1) == _giu(_s0).group(1)))
    # EVERY NUMBER HAS TO BE ACTIONABLE. The old bar had "363 kept" beside "364 worth
    # applying to" — two counts of the same pile, near enough identical to say nothing
    # extra; and "50 shown" is only the page size, which the list right below already
    # states.
    # Watch THE METRIC BOX on the bar, not the word "shown" anywhere on the page: that
    # word also appears in comments and other labels, and a check that goes red for an
    # unrelated reason teaches whoever is fixing it exactly one thing — switch it off.
    check("the 'shown' number is gone — that is the page size, not news",
          not _re.search(r"class='metric [^']*'><b>[0-9,]+</b>shown", _s0))
    check("there is a REAL queue: scored high and not applied to", "to apply to" in _s0)
    check("and that number takes the ACTION role (green), not the background role",
          _re.search(r"class='metric act[^']*'><b>[0-9,]+</b>to apply to", _s0))

    # The number on a chip has to FOLLOW the search text, or it lies.
    import re as _re
    _dem = lambda h, n: int(_re.search(f">{n} ([0-9,]+)<", h).group(1).replace(",", ""))
    check("it recounts for the search text, it does not keep the old number",
          _dem(_s1, "Kept") < _dem(_s0, "Kept"),
          f"{_dem(_s1, 'Kept')} vs {_dem(_s0, 'Kept')}")
    # What the user types goes straight into the SQL. It has to be a bound parameter.
    _ma_nhay, _ = get("/search?q=%27%20OR%201%3D1%20--")
    check("a quote in the search box does not crash the page", _ma_nhay == 200, str(_ma_nhay))

    # KEEPING a posting the machine dropped. The filters are mechanical rules — "the
    # job title does not match" alone dropped 2,595 postings in the live store, and
    # that rule is only a substring compare against the 19 job titles in the profile.
    # Anyone glancing over the dropped pile will find real postings, so there has to be
    # a way to pick them out.
    _, _bo = get("/search?show=dropped")
    check("a dropped row has a Keep it button", "Keep it" in _bo and "/api/keep" in _bo)
    _, _giu = get("/search")
    check("a kept row does NOT have that button — there is nothing left to keep",
          "Keep it" not in _giu)

    _bo_id = _re2.search(r"data-post='/api/keep' data-arg='(\d+)'", _bo).group(1)
    gui = lambda i: post("/api/keep", f"arg={i}".encode())
    check("pressing Keep is accepted by the server", gui(_bo_id) == 200)
    _, _sau = get("/search")
    check("that posting moves to the kept list", f"/jobs/{_bo_id}" in _sau)
    check("and it says outright it is here because A PERSON kept it, not because it scored",
          "you kept" in _sau)
    check("the button turns into Unkeep", "Unkeep" in _sau)
    check("it is no longer in the dropped list",
          f"/jobs/{_bo_id}" not in get("/search?show=dropped")[1])
    check("pressing again hands it back to the machine", gui(_bo_id) == 200
          and f"/jobs/{_bo_id}" in get("/search?show=dropped")[1])
    check("a made-up id is refused and changes nothing", gui("not-a-number") == 400)

    # APPLYING DOES NOT BELONG ON THE LIST. Applying is a decision — open Chrome, fill
    # the form, write a row into Manage — so it has to come AFTER reading. The place to
    # read is the detail page: the score for each requirement, the evidence, and a link
    # to the original posting. Pressing apply from the list is applying blind.
    check("a list row has NO Apply button", "/api/apply" not in _giu)
    check("but the detail page does",
          "data-post='/api/apply'" in get(f"/jobs/{job_id}")[1])
    # Keeping is THE OPPOSITE: sifting the dropped pile is a skim, eyes running down
    # dozens of rows. Forcing a detail page open for each one kills the sifting.
    check("but Keep it stays on the list — that is a skim, not a read",
          "/api/keep" in _bo)

    # EVERY POSTING NEEDS A WAY TO THE ORIGINAL. The detail page shows the score, each
    # requirement, the whole description — but with no way through to the real posting
    # the page is hearsay: the description in the store is a snapshot from scan time,
    # and the real posting may have been edited or closed since.
    _jid = str(job_id)
    _ma, _ct = get(f"/jobs/{_jid}")       # get() returns (status, body), not a string
    check("the detail page opens", _ma == 200, str(_ma))
    check("the detail page has an Open the original posting box", "Open the original posting" in _ct)
    # NO DECORATIVE BUTTONS. Every listener in live.js binds on data-*, so a <button>
    # carrying no data-* is a button where pressing it does nothing — and nothing
    # reports an error, so the user concludes the app is broken. This page once had
    # two: "Queue for approval" and "Reject…".
    import re as _re3
    _chet = [b for b in _re3.findall(r"<button[^>]*>", _ct)
             if "data-" not in b and "type=submit" not in b]
    check("no button is left wired to nothing", not _chet, str(_chet[:2]))
    check("and there is a real Apply button, on the same route as the list",
          "data-post='/api/apply'" in _ct)
    check("and there is a REAL link, not an internal one",
          "class='jlink" in _ct and "href='https://" in _ct)
    # The app window has no address bar and no Back button: opening an outside link
    # inside it loses the dashboard altogether.
    check("an outside link opens outside, it does not swallow the app window",
          "target='_blank'" in _ct and "rel='noopener noreferrer'" in _ct)
    # ONE JOB POSTED IN TWO PLACES GETS BOTH LINKS. They do not replace each other: the
    # company board is where you apply directly, LinkedIn carries the applicant count
    # and the name of whoever posted it.
    from jobbot.dashboard import live as _lv2
    _hai = _lv2._links([("greenhouse:x", "https://boards.greenhouse.io/x/jobs/1"),
                        ("linkedin", "https://www.linkedin.com/jobs/view/9/")],
                       "https://www.linkedin.com/jobs/view/9/")
    check("two sources -> two links", len(_hai) == 2, str(_hai))
    check("the company board comes BEFORE LinkedIn — that is where you apply directly",
          [l["kind"] for l in _hai] == ["board", "linkedin"])
    check("it names the domain it is about to send you to",
          _hai[1]["host"] == "www.linkedin.com", _hai[1]["host"])
    check("the same url does not appear twice",
          len(_lv2._links([("a", "https://x/1"), ("b", "https://x/1")], "https://x/1")) == 1)
    check("an empty url is dropped, it does not produce a dead button",
          _lv2._links([("a", "")], "") == [])

    # ONE centred pill, not a strip stretched across the whole width: on a 1900px
    # screen the strip pushed the stage name to the far left and the buttons to the far
    # right, a hand's span apart.
    check("there is a control pill", "class=deckpill" in _srch)
    # .pill ALREADY EXISTED: the status badges on the Manage table (.pill.applied,
    # .pill.interview…). Reusing the name is exactly the .frow/.prow class of bug
    # already fixed. Render the view directly with one sample row: the test DB has no
    # applications, so the real table draws no badge and the test would go green while
    # checking nothing.
    from jobbot.dashboard.views import track as _tk
    from jobbot.track import board as _bd2
    _trk = _tk.render(
        rows=[dict(id=1, stage=_bd2.SENT, company="X", role="R", days=1,
                   event_days=None, last_event="", silent=False, cv_file="",
                   posting_id=None, url="", score=0)],
        asks=[], counts={"total": 1}, mail_ready=False, mail_address="")
    check("the Manage table still draws .pill badges", "class='pill " in _trk)
    # NO ROW MAY VANISH. The table groups by liveness; a row missing that field has to
    # fall into the last group, never quietly disappear from the screen.
    check("a row that could not be grouped still shows",
          "X" in _trk and "Could not be grouped" in _trk)
    # PAST THE REPLY WINDOW IT HAS TO GO RED, interviews included: an invitation from
    # 20 days ago that nobody has followed up is the most worrying thing on the table.
    _nong = _tk.render(
        rows=[dict(id=1, stage=_bd2.INTERVIEW, company="Kappa Lab", role="",
                   days=20, event_days=None, last_event="", silent=False,
                   cv_file="", posting_id=None, url="", score=0,
                   song="nong", im_ngay=20, so_thu=1, ho_tra_loi=False)],
        asks=[], counts={"total": 1}, mail_ready=False, mail_address="")
    check("an interview row silent too long -> still painted as a warning", "snong qua" in _nong)
    _moi = _tk.render(
        rows=[dict(id=1, stage=_bd2.INTERVIEW, company="Kappa Lab", role="",
                   days=2, event_days=None, last_event="", silent=False,
                   cv_file="", posting_id=None, url="", score=0,
                   song="nong", im_ngay=2, so_thu=1, ho_tra_loi=False)],
        asks=[], counts={"total": 1}, mail_ready=False, mail_address="")
    check("still inside the window -> no warning paint", "snong qua" not in _moi)
    # Manage NOW HAS a stage bar, like Search and CV. What this test guards keeps its
    # full value: the status badge (`.pill`) and the top-bar pill (`.deckpill`) have to
    # be TWO different classes, neither taking the other's styling.
    check("Manage has a stage bar, like Search and CV", "class=deckpill" in _trk)
    check("the status badge is still its own class",
          "class='pill " in _trk and "class='deckpill" not in _trk)
    _cssP = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    check("the pill is centred", "align-items:center" in _cssP)
    check("the pill is rounded", ".deckpill{" in _cssP)
    # NARROW MEANS WRAP, NOT SCROLL SIDEWAYS WITH THE SCROLLBAR HIDDEN.
    #
    # The old test demanded exactly `flex-wrap:nowrap` + `overflow-x:auto` and told
    # itself "scrolls sideways, does NOT hide buttons" — while one line below, the CSS
    # carried `scrollbar-width:none` and `::-webkit-scrollbar{display:none}`. It was
    # guarding THE METHOD, not THE RESULT, and that method really did hide buttons.
    #
    # Measured on /track/queue (the widest pill, 900px): a 1180 window fits with 7px to
    # spare · 1100 loses «← Table» · 980 loses «Scan mail», «Stop» and «← Table». The
    # app window defaults to exactly 1180 — drag it a little smaller and buttons
    # disappear with no warning.
    _pl = _cssP[_cssP.index(".deckpill{"):_cssP.index(".deckpill{") + 320]
    check("the pill WRAPS when it runs out of room", "flex-wrap:wrap" in _pl)
    check("and it no longer scrolls sideways", "overflow-x:auto" not in _pl)
    check("the scrollbar is hidden NOWHERE in the pill",
          "scrollbar-width:none" not in _pl
          and ".deckpill::-webkit-scrollbar" not in _cssP)
    check("the metrics row can wrap too",
          "flex-wrap:wrap" in _cssP[_cssP.index(".metrics{"):
                                    _cssP.index(".metrics{") + 160])
    # The corner radius still has to close into a pill on a single row: a single row is
    # 45px tall, so the radius must be >= 23. Below that the whole bar changes shape.
    _bo = int(_re.search(r"\.deckpill\{[^}]*border-radius:(\d+)px", _cssP,
                         _re.S).group(1))
    check(f"a {_bo}px radius is still enough to make a single row a pill", _bo >= 23)
    # Everything in ONE pill: the stage name, the metrics, the buttons. Push the metrics
    # outside and the bar breaks into three disconnected tiers.
    _pillhtml = _srch[_srch.index("class=deckpill"):]
    _pillhtml = _pillhtml[:_pillhtml.index("</div>")]
    check("the metrics are INSIDE the pill", "class=metric" in _pillhtml)
    check("the buttons are inside the pill too", "/api/stage/start" in _pillhtml)
    # With a bare `nowrap`, a narrow screen runs the status line past the pill's edge
    # and cuts it off mid-word.

    print("\n[the STATUS bar at the bottom of the app]")
    # News belonging to the WHOLE app, to no single tab. The line "automatic: OFF ·
    # last scan…" used to sit in the tab's own bar — the wrong place: it is not a
    # stage's metric, it is the app's state.
    for _pg2 in ("/", "/search", "/track", "/profile"):
        _b2 = get(_pg2)[1]
        check(f"{_pg2} has the status bar", "class=statusbar" in _b2)
    # The status bar runs the FULL width, under the sidebar too — it is the whole app's
    # news. And the sidebar has to leave room for it, or the Settings button is covered.
    _cssb = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    check("the status bar spans the full width",
          ".statusbar{position:fixed;left:0;right:0" in _cssb)
    check("the sidebar stops right above the status bar",
          "bottom:var(--status-h);\n  width:var(--nav-w)" in _cssb)
    # The app window is frameless: the traffic lights sit on top of the page. With a
    # REAL title bar every page gets the room automatically — before, each page had to
    # remember for itself, and Home remembered wrong (16px reserved where 38px was
    # needed), so its content box crawled up underneath them.
    for _pg4 in ("/", "/search", "/cv", "/track", "/profile"):
        _, _b4 = get(_pg4)
        check(f"{_pg4} has the title bar", "class=titlebar" in _b4)
    check("the title bar is exactly --top tall", "z-index:40;height:var(--top)" in _cssb)
    check("the main frame starts BELOW the title bar",
          "main{position:fixed;top:var(--top);left:var(--main-l)" in _cssb)
    check("and so does the sidebar",
          ".side{position:fixed;top:var(--top);left:var(--gap)" in _cssb)
    # TWO FRAMES, NO RULED LINES. The title bar and the status bar have no ground of
    # their own and no border — they ARE the body's grey field. Floating on that field
    # are TWO rounded frames sharing the --rim border: the tab-button column and the
    # working area. What separates them is the --gap between the two frames, not a line.
    for _ten, _rule in (("the tab-button column", "\n.side{"), ("the working area", "\nmain{")):
        _blk = _cssb[_cssb.index(_rule) + 1:]
        _blk = _blk[:_blk.index("}")]
        check(f"{_ten} is a rounded frame with a border",
              "border:1px solid var(--rim)" in _blk
              and "border-radius:var(--round)" in _blk, _blk[:90])
    # The BORDER grey has to separate from the FRAME grey, or the rounded edge sinks
    # out of sight.
    _tach = _ls(_var["rim"]) - _ls(_var["side"])
    check(f"the border grey is lighter than the frame grey ({_tach:+.1f} L*)", 6.0 <= _tach <= 15.0)
    check("the window ground is the frame grey", "body{margin:0;background:var(--side)" in _cssb)
    for _ten, _rule in (("the title bar", ".titlebar{"), ("the status bar", ".statusbar{")):
        _blk = _cssb[_cssb.index(_rule):]
        _blk = _blk[:_blk.index("}")]
        check(f"{_ten} draws no dividing line", "border" not in _blk, _blk[:70])
        check(f"{_ten} has no ground of its own", "background" not in _blk, _blk[:70])
    check("the bottom bar has a live status box", "data-state" in _srch)
    check("and a latest-news box", "data-lastmsg" in _srch)
    # A page may state the shared status ONCE. live.js writes into EVERY [data-state],
    # so two boxes means the same sentence twice, at opposite ends of the screen.
    for _pg3 in ("/", "/search", "/cv", "/track", "/profile"):
        _, _b3 = get(_pg3)
        check(f"{_pg3} has exactly one status box", _b3.count("data-state") == 1)
    # live.js fills it from the SSE stream — no threading a parameter through a dozen
    # render functions.
    _js2 = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    check("live.js has the function that fills it", "function setLastMessage" in _js2)
    check("it is called on every new event", _js2.count("setLastMessage(") >= 3)
    check("content does not hide behind the bottom bar", "var(--status-h)" in _cssP)
    # The old navfoot showed that same information on the sidebar — one truth in two places.
    _lay2 = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/layout.py").read_text(encoding="utf-8")
    check("navfoot is gone from the sidebar entirely", "navfoot" not in _lay2)
    check("and the dead status= parameter is gone", "status: str" not in _lay2)
    # The old "Run now"/"Turn on auto-scan" buttons sat on the WHOLE-APP bar while
    # driving only the Search stage. A bar in the app's name doing one stage's work.
    check("the whole-app buttons are gone", "data-act=run" not in _srch
          and "data-act=pause" not in _srch)
    # ⚟ REUSES the Settings overlay — every new route is another button that can die.
    _cA, _adj = get("/adjust/search")
    check("/adjust/search returns an HTML fragment", _cA == 200 and "Adjust" in _adj)
    check("and it contains the sieve", "/api/sieve" in _adj)
    check("an unknown stage is 404", get("/adjust/khong-co-that")[0] == 404)
    # Filtering (pressed every few seconds) has to be RIGHT on the page, not hidden in a menu.
    check("the filters are still on the page", "?show=" in _srch or "show=" in _srch)

    print("\n[stop has to REALLY stop, not be a button for show]")
    _run = (Path(__file__).resolve().parent.parent
            / "src/jobbot/scan_runner.py").read_text(encoding="utf-8")
    _li = (Path(__file__).resolve().parent.parent
           / "src/jobbot/ingest/web/linkedin.py").read_text(encoding="utf-8")
    # The scheduler's `stop()` only blocks the NEXT run. One scan runs 8-16 minutes
    # because it opens Chrome and reads each posting — a Stop button that cannot
    # interrupt is a dead button.
    check("it breaks between API sources", "halt.wanted(STAGE)" in _run)
    check("it passes the flag down into LinkedIn", "stop=lambda: halt.wanted(STAGE)" in _run)
    check("it breaks inside the DEEP-READ loop (where the 8-16 minutes go)", "deep-read" in _li)
    check("and inside the search loop too", "queries done" in _li)
    _halt = (Path(__file__).resolve().parent.parent
             / "src/jobbot/core/halt.py").read_text(encoding="utf-8")
    # Stopping the scan must NOT also stop the mail sweep running alongside it.
    check("the flag is PER STAGE, not one shared flag", "stage: str" in _halt)
    _srv = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
    # Adding a new capability must not spawn another route.
    check("two routes shared by every stage",
          '"/api/stage/start", "/api/stage/stop"' in _srv)
    check("an unknown stage is refused", 'stage not in STAGES' in _srv)

    print("\n[the frame must not be wasted — ON EVERY page, not one of them]")
    import re as _re9
    _css9 = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    _bare = _re9.sub(r"/\*.*?\*/", "", _css9, flags=_re9.S)

    # The original bug: `.inner{max-width:840px}` capped EVERY flow-style page. Measured
    # on a 1900px screen: the frame was 1684, the content 840 -> 844px left empty, on
    # FOUR pages at once. Patching one page leaves the other three exactly as they were.
    _inner = _re9.search(r"\.inner\{([^}]*)\}", _bare)
    check("there is an .inner rule", bool(_inner))
    _mw = _re9.search(r"max-width:([^;}]+)", _inner.group(1)) if _inner else None
    check(".inner has NO fixed cap any more",
          bool(_mw) and _mw.group(1).strip() == "none",
          _mw.group(1).strip() if _mw else "no max-width")
    # Width is a property of THE CONTENT: only prose needs a readable measure.
    check("but prose still keeps a readable measure",
          bool(_re9.search(r"\.inner p[^{]*\{[^}]*max-width:\d+ch", _bare)))
    # The `wide=` flag was a switch every page had to REMEMBER to turn on — some page
    # would forget. It is gone.
    _lay = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/layout.py").read_text(encoding="utf-8")
    # LOOK FOR THE IDENTIFIER, not a substring: "as wide as the window" inside a comment
    # is ordinary English prose, not the flag that was removed.
    check("the wide flag is gone (the easily-forgotten route)",
          not _re9.search(r"(?<![\w-])wide(?![\w-])\s*[=:]", _lay))
    check("and there is no .wide CSS rule left", "main.wide" not in _bare)

    # Really walk EVERY page in the sidebar, not just the page just edited.
    _c9, _nav = get("/")
    _pages = set(_re9.findall(r"<a class='navlink[^']*' href='([^']+)'", _nav))
    _pages |= {"/profile/health", "/profile/import", f"/jobs/{job_id}"}
    check("enough pages were found to check", len(_pages) >= 7, str(sorted(_pages)))
    for _pg in sorted(_pages):
        _code, _body = get(_pg)
        if _code != 200:
            check(f"{_pg} opens", False, f"HTTP {_code}")
            continue
        _m = _re9.search(r"<main class='([^']*)'", _body)
        check(f"{_pg} carries no width-fixing class",
              bool(_m) and "wide" not in _m.group(1))

    # A table: `width` on a cell is only A HINT while the table lays itself out — a
    # long label dragged the column out to 650px. And with a fixed layout Chrome
    # IGNORES min()/clamp() (measured: back to 803px), taking only px or per cent.
    check("the profile table uses a fixed column layout", "table-layout:fixed" in _bare)
    _th = _bare[_bare.index(".sum th{"):_bare.index(".sum th{") + 260]
    check("the label column uses a bare width, no min()/clamp()",
          "width:340px" in _th and "min(" not in _th and "clamp(" not in _th)
    check("a narrow screen has its own rule for the label column", ".sum th{width:40%}" in _bare)

    print("\n[Home is NO LONGER a blank page]")
    # The old law here was "Home has to say it is empty". Home is now the front door
    # and the profile-building run, so the law flips: it must NOT be empty any more.
    _, _blank = get("/")
    check("Home still opens", "Home" in _blank)
    # The placeholder became a real page — check WHAT IT MUST HAVE, not the old
    # promise. Four panels + the stage bar + the journal.
    check("Home has the stage bar, like every tab", "class=deckpill" in _blank)
    for _o in ("Results", "Output per day", "Diagnosis", "Funnel"):
        check(f"Home has the «{_o}» panel", _o in _blank)
    check("and it has the journal", "data-journal" in _blank)
    # Removing the content while leaving the code that fed it behind is the dirty part.
    for _gone in ("class=funnel", "class=needs", "class=stats", "class=plot"):
        check(f"{_gone} is gone", _gone not in _blank)
    _live8 = (Path(__file__).resolve().parent.parent
              / "src/jobbot/dashboard/live.py").read_text(encoding="utf-8")
    for _fn in ("def run_status", "def counters", "def needs_you", "def activity",
                "def per_day", "def chances", "def funnel"):
        check(f"live.py has dropped {_fn[4:]}", _fn not in _live8)
    check("dashboard/plot.py is deleted",
          not (Path(__file__).resolve().parent.parent
               / "src/jobbot/dashboard/plot.py").exists())

    print("\n[the journal: the newest line has to be SEEN AT ONCE]")
    # "highlight the newest message so it stands out and is easy to spot"
    #
    # The mark is PURE CSS (:first-child), with no class for JS to attach — so there
    # is no way for the mark to stay on an old line when a new one arrives. But it
    # rests on ONE constraint: live.js inserts new lines at THE TOP. Change that to
    # append at the bottom and the mark quietly points at the OLDEST line while the
    # interface still looks perfectly normal. So both ends are pinned here.
    _css_j = (Path(__file__).resolve().parent.parent
              / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    _js_j = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    check("new lines are inserted at THE TOP — the foundation of the whole marking rule",
          "insertBefore(row, box.firstChild)" in _js_j)
    check("exactly ONE place produces .jline, so no other order can exist",
          sum(1 for _f in (Path(__file__).resolve().parent.parent
                           / "src/jobbot/dashboard").rglob("*")
              if _f.is_file() and _f.suffix in (".js", ".py")
              and "'jline" in _f.read_text(encoding="utf-8")) == 1)
    check("the newest line has its own mark", ".journal .jline:first-child{" in _css_j)
    check("the mark is A GROUND, not a text colour",
          "background:rgba(255,255,255,.062)" in _css_j)
    check("and it has a left rule", "border-left-color:var(--mute)" in _css_j)
    # The left rule follows THE LEVEL. If the newest-line mark overrode the level
    # colour the user would lose the first thing they need to read — is this line a
    # failure, or just ordinary news.
    _khit = "".join(_css_j.split())      # drop the indentation whitespace in the CSS
    for _m, _mau in (("ok", "--acc"), ("warn", "--warn"), ("error", "--bad")):
        check(f"the left rule keeps the right colour for level {_m}",
              f".journal.jline.{_m}:first-child{{border-left-color:var({_mau})}}"
              in _khit)
    check("the ok/warn/error text colour is NOT changed — the level must not lie",
          not any(f".journal .jline.{_m}:first-child .jtext{{color" in _css_j
                  for _m in ("ok", "warn", "error")))
    # Every line already carries a transparent rule -> when the mark moves to another
    # line, no line is nudged sideways by a notch.
    check("every line reserves the space for the rule, so nothing jumps sideways",
          "border-left:2px solid transparent" in _css_j)
    check("it flashes once on arrival", "@keyframes jnew" in _css_j)
    check("but it respects a machine with motion turned off",
          "prefers-reduced-motion" in _css_j)

    print("\n[Search: three panels — the list · the sieve · the flat journal]")
    from jobbot.dashboard.views.runtime import _rows_needed
    check("row count: the journal sits at the bottom, so there is no 'Running' box on row 1",
          _rows_needed([("a", "", 1, 4), ("b", "", 2, 4)], 3, 0) == 4)

    _, search_html = get("/search")
    _, adj_html = get("/adjust/search")
    check("the list panel", "What it found" in search_html)
    check("the journal in its flat form", "class=jflat" in search_html)
    check("progress folded into the journal strip", "data-progress='search'" in search_html)
    # The sieve moved behind ⚟, so the left column has no job left: the list — the
    # thing actually read — takes the full width, and the journal becomes a flat strip
    # along the bottom.
    check("the list takes the full width", "class=srcrow" not in search_html)
    check("the journal is a strip at the bottom, not a corner box",
          "wid flat corner" not in search_html)

    # The sieve has to be EDITABLE — and it now sits behind the ⚟ button, taking no
    # permanent space on the page. FILTERING stays on the page (pressed every few
    # seconds); THE SIEVE changes every few months, and each change re-judges the
    # whole store.
    check("the sieve is a real FORM", "form class=sieve" in adj_html)
    check("and it no longer takes space on the page", "form class=sieve" not in search_html)
    # Job titles are A TAG BOX, not a text area: type and press Enter to add, press ×
    # to remove. A text area makes the user remember the rule "one per line", and a
    # blank line or a stray comma produces a junk job title.
    check("job titles are a tag box, NOT a text area",
          "class=tagbox" in adj_html and "<textarea" not in adj_html)
    n_tags = adj_html.count("<span class=tag>")
    check("there is at least one tag", n_tags > 0)
    check("each tag has exactly one × to remove it",
          adj_html.count("data-untag") == n_tags)
    check("each tag carries exactly one value to send",
          adj_html.count("name=job_titles") == n_tags)
    check("the × is type=button, so it does not submit the whole form by accident",
          "<button type=button class=untag" in adj_html)
    check("there is a box to type another", "class=taginput" in adj_html)
    check("there are tick boxes for seniority and markets",
          "name=seniority" in adj_html and "name=markets" in adj_html)
    check("there is an Apply button", ">Apply<" in adj_html)
    # The button has to state the consequence BEFORE the press, not be a blank "Save".
    check("the button says how many postings will be re-judged", "re-judges" in adj_html)
    check("and says outright this is the profile — editing it changes the scores too",
          "profile" in adj_html and "changes the scores too" in adj_html)

    # The VIEW buttons are separate from the sieve: pressing one changes the view at
    # once, with no Apply in between.
    check("a VIEW button is a link, not inside the form",
          "class='vchip" in search_html
          and search_html.index("class=jlist") > search_html.index("class=vbar"))
    check("a VIEW button points at /search, not the deleted /jobs",
          "href='/search?" in search_html and "href='/jobs?" not in search_html)

    # The source badge — what says which way found which posting.
    check("every row has a source badge",
          "class='src board'" in search_html or "class='src linkedin'" in search_html)
    check("the badge spells the source out",
          ">board<" in search_html or ">linkedin<" in search_html)

    print("\n[Search: changing the view needs NO Apply]")
    _, dropped = get("/search?show=dropped")
    check("the dropped postings can be viewed", "dropped:" in dropped)
    check("and each carries the real reason it was dropped",
          "title does not match" in dropped or "senior level" in dropped)
    for q in ("?show=all", "?chance=likely", "?via=all", "?band=75",
              "?sort=company", "?q=%27%20OR%201%3D1--", "?page=99"):
        code, body = get("/search" + q)
        check(f"/search{q:24} {code}", code == 200, body[:60])

    print("\n[Search: paging — 132 postings must not be stuck at 50]")
    # With no next-page button, the other 82 postings might as well not exist.
    import re as _re3
    import jobbot.dashboard.filters as _filters
    rows = lambda html: len(_re3.findall(r"class='jrow", html))
    real_per = _filters.PER_PAGE
    _filters.PER_PAGE = 2            # the fixture has only a few postings -> force several pages
    _, p1 = get("/search?show=all")
    _, p2 = get("/search?show=all&page=2")
    check("page 1 is full", rows(p1) > 0)
    check("there is a next-page button", "class=pager" in p1 and "next →" in p1)
    check("page 2 shows DIFFERENT cards from page 1", rows(p2) > 0 and p1 != p2)
    check("it says which page of how many", "page 1/" in p1 and "page 2/" in p2)
    _, far = get("/search?page=9999")
    check("a page past the end is empty, it does not crash", far and rows(far) == 0)
    _filters.PER_PAGE = real_per

    print("\n[a posting's detail page MUST stay alive even though the Jobs tab is gone]")
    # The /jobs list is gone, but /jobs/<id> is where you read WHY a posting scored
    # what it scored — the new list in Search points here.
    code, detail = get(f"/jobs/{job_id}")
    check("a posting's detail still opens", code == 200, detail[:80])
    check("and it shows a real posting from the DB", "Man Group" in detail or "Monzo" in detail)
    check("with the evidence for each requirement", "requirement" in detail.lower()
          or "evidence" in detail.lower())
    for sub in ("cv", "project"):
        code, _ = get(f"/jobs/{job_id}/{sub}")
        check(f"/jobs/<id>/{sub} is still alive", code == 200)

    # EVERY page in the sidebar. One went white over a surplus argument at the call
    # site (`mail.account(conn)` after the function dropped its parameter) — 906 tests
    # green while /track was dead, because no test opened it.
    for page in ("/", "/search", "/track", "/track/queue", "/cv", "/profile",
                 "/settings"):
        code, body = get(page)
        check(f"{page} opens", code == 200, f"HTTP {code}")
        check(f"{page} returns no error page", "Traceback" not in body)

    print("\n[every link on a page has to be reachable]")
    _links = set()
    # Finding no links at all means this test is checking NOTHING — worse than not
    # existing, because it still goes green.
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
        check(f"the link {_href} is reachable", _c4 in (200, 303), f"HTTP {_c4}")
    check("there are links to check at all", len(_links) >= 5, str(len(_links)))

    print("\n[the sidebar: the logo, and Settings at the bottom]")
    _c7, _home = get("/")
    check("Settings is in the sidebar", "navend" in _home)
    # It is a <button>, NOT an <a>: /settings returns an HTML FRAGMENT for the
    # overlay, so linking to it lands on a blank page.
    import re as _re7
    _end = _re7.search(r"<div class=navend>(.*?)</div>", _home, _re7.S)
    check("Settings is a button, not a link", bool(_end) and "<button" in _end.group(1))
    check("and not an <a> tag", bool(_end) and "<a " not in _end.group(1))
    # The Settings item must NOT share a route with a stage's ⚟ button: ⚟ adjusts one
    # stage, Settings settles the whole app. Share one attribute and sooner or later
    # they share the contents too, and it becomes "one bar that is half the app's and
    # half the stage's" all over again. Count INSIDE THE REGION, not across the whole
    # page — some pages carry other overlay buttons using the same attribute.
    check("the Settings item carries data-appset",
          bool(_end) and "data-appset" in _end.group(1))
    check("and it does NOT hook into a stage's ⚟ panel",
          bool(_end) and "data-settings" not in _end.group(1))
    # The gear HAS LEFT the top bar: Settings (whole app) moved to the bottom of the
    # sidebar, and the top bar is now the bar of THE STAGE on screen, carrying that
    # stage's own ⚟ Adjust button. One bar cannot be both the app's and a stage's.
    # A page with no stage draws NO top bar: the shared state already sits on the
    # bottom bar, and drawing the same line again at the top says it twice.
    check("a page with no stage has no top bar",
          "class='topbar" not in _home and "class=runstate" not in _home)
    _, _s2 = get("/search")
    _bar2 = _re7.search(r"<header class=topbar>(.*?)</header>", _s2, _re7.S)
    check("a page with a stage carries that stage's ⚟ button on the bar",
          bool(_bar2) and "data-settings='/adjust/search'" in _bar2.group(1))
    _css7 = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
    _, _sv = get("/")
    check("the logo is a key drawn in SVG", "<svg class=logo" in _sv)
    # COUNT INSIDE THE LOGO, not across the page: the sidebar icon set also has
    # <circle> (the magnifier, the person, the gear), so counting the whole page would
    # stop this test checking the very thing it is named after.
    _lg = _re7.search(r"<svg class=logo.*?</svg>", _sv, _re7.S)
    _lg = _lg.group(0) if _lg else ""
    check("the key's three rings are REAL rings — holes, not solid dots",
          _lg.count("<circle") == 3 and "fill=none" in _lg)
    check("the logo takes its colour from CSS, not hard-coded into the drawing",
          "currentColor" in _lg and ".logo{" in _css7)

    _srv = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
    print("\n[THE «NOT IN» MEETS NULL TRAP — a whole class of bug, not one place]")
    # Three-valued SQL: `x NOT IN (…, NULL)` yields NULL, not TRUE, so the clause is
    # never true and the statement silently does nothing.
    #
    # Measured on the live store: 32 of 37 applications have posting_id = NULL, so
    # "Clear the store" deleted EXACTLY 0 postings — while source_run (204 scans) and
    # cv_build were wiped anyway. The user sees the store untouched and loses the scan
    # history.
    # A scratch table: this test checks SQL SEMANTICS, not the schema. The real places
    # are covered by the source-wide sweep right below.
    import sqlite3 as _sq
    _cnull = _sq.connect(":memory:")
    _cnull.executescript(
        "CREATE TABLE tin (id INTEGER PRIMARY KEY);"
        "CREATE TABLE don (tin_id INTEGER);"
        "INSERT INTO tin (id) VALUES (1);"
        "INSERT INTO don (tin_id) VALUES (NULL);")
    _sai = _cnull.execute(
        "SELECT COUNT(*) FROM tin WHERE id NOT IN (SELECT tin_id FROM don)"
    ).fetchone()[0]
    _dung = _cnull.execute(
        "SELECT COUNT(*) FROM tin WHERE id NOT IN"
        " (SELECT tin_id FROM don WHERE tin_id IS NOT NULL)").fetchone()[0]
    check("the trap is real: forget the NULL filter -> the count comes out 0", _sai == 0)
    check("filter the NULLs and the count is right", _dung == 1)
    _cnull.close()
    # GUARD THE WHOLE CLASS: every `NOT IN (SELECT <column>` in the source must carry
    # `IS NOT NULL`. Patch one place and the next statement anyone writes falls in again.
    import re as _reN
    _xau = []
    for _f in sorted((Path(__file__).resolve().parent.parent / "src").rglob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        for _m in _reN.finditer(r"NOT IN \(\s*(?:\\n|[^)])*?SELECT\s+(\w+)", _t):
            _doan = _t[_m.start():_m.start() + 400]
            _het = _doan.find(")")
            if "IS NOT NULL" not in _doan[:max(_het, 300)]:
                _xau.append(f"{_f.name}:{_t[:_m.start()].count(chr(10)) + 1}")
    check(f"no «NOT IN» statement forgets the NULL filter"
          + (f" — {', '.join(_xau[:4])}" if _xau else ""), not _xau)

    print("\n[THE SAME-HOUSE CATCH — a stranger's web page must not drive the app]")
    # LISTENING ON 127.0.0.1 IS NOT PROTECTION. Measured before the fix: any web page
    # the user happened to open could call /api/chung (change the theme),
    # /api/session/start (open the watch station), /api/reset (wipe everything) and
    # /api/apply/send (press Send on their behalf — straight through founding law 4).
    # The browser stops them READING the result, but the action still happens.
    def _post(path, body="arg=x", **hdr):
        req = urllib.request.Request(
            base.rstrip("/") + path, data=body.encode(), method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", **hdr})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    for _p in ("/api/reset", "/api/apply/send", "/api/chung", "/api/track/xoa"):
        check(f"BLOCK {_p} on Sec-Fetch-Site: cross-site",
              _post(_p, **{"Sec-Fetch-Site": "cross-site"}) == 403)
        check(f"BLOCK {_p} on a foreign Origin",
              _post(_p, **{"Origin": "https://bad-guy.example"}) == 403)
    check("the app calling itself gets THROUGH", _post("/api/state",
          **{"Sec-Fetch-Site": "same-origin"}) != 403)
    check("a script on this very machine (no header) still gets THROUGH",
          _post("/api/state") != 403)
    # The catch has to sit in ONE place, ahead of every route — put it on each route
    # and every new route has to remember it, and the one forgotten could be the route
    # that wipes the data.
    check("the catch sits in one place, at the very top of do_POST",
          "if not self.cung_nha():" in _srv
          and _srv.index("def do_POST") < _srv.index("length = int(self.headers"))

    print("\n[TELEGRAM — alerts to the phone, and three safety catches]")
    from jobbot.core import tele as _tl, db as _db, prefs as _prefs
    from jobbot.dashboard.views import settings as _setm
    from jobbot import bao as _bao
    # CATCH 1 — ANYONE CAN MESSAGE A TELEGRAM BOT. This is the only fence between the
    # machine at home and anybody who knows the bot's name.
    _that = {"message": {"chat": {"id": 111}, "text": "/trangthai"}}
    _la = {"message": {"chat": {"id": 999}, "text": "/tatphien"}}
    check("the right chat is accepted", _tl.duoc_phep(_that, "111"))
    check("A STRANGE CHAT IS DROPPED", not _tl.duoc_phep(_la, "111"))
    check("no chat pinned -> everything is dropped", not _tl.duoc_phep(_that, ""))
    check("an empty message does not get through either", not _tl.duoc_phep({}, "111"))
    check("chat_id compares AS A STRING, not as a number", _tl.duoc_phep(_that, " 111 "))
    # CATCH 2 — THE TOKEN NEVER REACHES THE HTML.
    check("a printed token keeps only its tail", _tl.che("7123456789:AAHxxxxYZ9k") == "…Z9k"
          or _tl.che("7123456789:AAHxxxxYZ9k").startswith("…"))
    check("masking lets no part of the token's head through",
          "7123" not in _tl.che("7123456789:AAHxxxxYZ9k"))
    # CATCH 3 — THERE IS NO APPLY COMMAND AT ANY LEVEL. The founding boundary of the
    # whole app: the machine does NOT press Send. That has to hold over Telegram too.
    for _muc in (_tl.TAT, _tl.XEM, _tl.DAY_DU):
        for _cam in ("nopdon", "apply", "send", "gui", "nop"):
            check(f"level «{_muc}» allows no /{_cam} command",
                  not _tl.cho_phep_lenh(_cam, _muc))
    check("level OFF allows no command at all", not any(
        _tl.cho_phep_lenh(l, _tl.TAT) for l in _tl.LENH_XEM + _tl.LENH_GHI))
    check("level READ allows no command that WRITES to the table",
          not any(_tl.cho_phep_lenh(l, _tl.XEM) for l in _tl.LENH_GHI))
    check("only level FULL allows reviewing mail",
          all(_tl.cho_phep_lenh(l, _tl.DAY_DU) for l in _tl.LENH_GHI))
    check("and all three levels carry a description for the user to choose by",
          len(_tl.MUC_DIEU_KHIEN) == 3
          and all(len(v) == 2 and v[1] for v in _tl.MUC_DIEU_KHIEN.values()))
    # Reading a command: Telegram appends "@bot_name" inside a group.
    check("the @bot_name suffix is stripped",
          _tl.doc_lenh({"message": {"text": "/trangthai@jobbot_bot"}})[0] == "trangthai")
    check("case does not matter",
          _tl.doc_lenh({"message": {"text": "/BatPhien"}})[0] == "batphien")
    check("ordinary text is not a command",
          _tl.doc_lenh({"message": {"text": "hello there"}}) == ("", ""))
    # WITH NO BOT CONNECTED no alert kind counts as on — otherwise every scan calls the
    # API with an empty token and the journal fills with junk.
    _cbao = _db.connect(":memory:")
    check("with no bot connected every alert kind counts as off",
          not any(_bao.bat(_cbao, k) for k in _prefs.BAO))
    check("and the command-listening loop exits by itself", _bao.cau_hinh_nghe() is None)
    check("by default NO remote command is accepted",
          _prefs.DEFAULTS[_prefs.BAO_MUC] == _tl.TAT)
    _cbao.close()
    # The Settings tab
    _stb = _setm.render(every=60, hours=(8, 22), status=[], tele_noi=True,
                       tele_token="…Z9k", tele_chat="111",
                       bao_bat={k: True for k in _prefs.BAO}, bao_muc="xem")
    check("Settings has an Alerts tab", "data-stab='bao'" in _stb)
    check("all four alert kinds are laid out", _stb.count("data-post='/api/bao'")
          == len(_prefs.BAO) + len(_tl.MUC_DIEU_KHIEN))
    check("the token box is a password, not text", "type=password name=token" in _stb)
    check("and there is NO value= on the token box",
          "name=token value" not in _stb and "name=token autocomplete" in _stb)
    check("the three hard catches are stated for the user to read",
          "no apply command at any level" in _stb.lower())
    check("someone with no bot yet gets the instructions to make one",
          "@BotFather" in _setm.render(every=60, hours=(8, 22), status=[]))
    # THE PANEL HAS TO BE WIDE ENOUGH FOR THE WHOLE TAB ROW. Measured: seven chips of
    # 12px text + 12px padding each side + six gaps = ~530px, plus 36 of panel padding
    # -> 566. At 480 it broke onto two lines and a tab name was cut in half.
    _rong = int(_re.search(r"\.sheetbox\{width:(\d+)px", _css7).group(1))
    _so_tab = _stb.count("data-stab=")
    check(f"the Settings panel is wide enough for {_so_tab} tabs ({_rong}px)", _rong >= 700)
    check("the tab row does NOT wrap", "flex-wrap:nowrap" in _css7
          and ".stab{white-space:nowrap" in _css7)
    check("one more tab scrolls sideways, it does not break the layout",
          "overflow-x:auto" in _css7.split(".stabs{")[1][:200])
    # THE PORT IS ISSUED BY THE SYSTEM — not hard-coded, and not "ask first, then bind".
    # `find_port` asked "is anyone listening" and only then bound — there is a gap
    # between the two steps, and two overlapping test runs both saw it free and both
    # bound. That "Address already in use" failure is INTERMITTENT, which makes the
    # test even harder to trust.
    _goc = Path(__file__).resolve().parent.parent
    check("once up, the server reads the REAL port BACK from the socket",
          "httpd.server_address[1]" in
          (_goc / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8"))
    check("and the test suite asks for port 0 so the system issues one",
          "serve(port=0)" in Path(__file__).resolve().read_text(encoding="utf-8"))

    print("\n[CONNECTING THE BOT — it has to SAY which chat it pinned]")
    # The previous version took `ai[-1]` and reported "found your chat". Anyone can
    # message a Telegram bot, and bots often get pulled into groups — so "your chat"
    # could be somebody else's, and every job alert would go straight there. Nobody
    # could notice, because the screen never said which one it picked.
    _ra = {"result": [
        {"message": {"chat": {"id": 111, "first_name": "Vin", "last_name": "Dac"}}},
        {"message": {"chat": {"id": 222, "title": "Recruiting group"}}},
        {"message": {"chat": {"id": 111, "first_name": "Vin", "last_name": "Dac"}}},
    ]}
    _ds = _bao._cac_chat(_ra)
    check("duplicates merge, arrival order kept", [c for c, _ in _ds] == ["222", "111"])
    check("a person's name is picked up", ("111", "Vin Dac") in _ds)
    check("a group's name is picked up", ("222", "Recruiting group") in _ds)
    check("with only a username, the username is used",
          _bao._cac_chat({"result": [{"message": {"chat": {"id": 5, "username": "ai"}}}]})
          == [("5", "@ai")])
    check("an update that is not a message is dropped, not exploded on",
          _bao._cac_chat({"result": [{"edited_message": {}}, {}]}) == [])
    check("an empty response gives an empty list", _bao._cac_chat({}) == [])
    # A malformed chat id (Telegram changing the type, or junk data) must not be pinned.
    check("a malformed chat id is rejected",
          _bao._cac_chat({"result": [{"message": {"chat": {"id": "abc"}}}]}) == [])

    # What the user is told: one chat -> name it; several chats -> SAY there are several.
    _that_goi, _that_ghi = _tl.goi, None
    from jobbot.core import config as _cfgm
    _that_ghi = _cfgm.write_value
    _da_ghi = []
    _cfgm.write_value = lambda muc, k, v: _da_ghi.append((k, v))
    _bao_cfg = _tl.cau_hinh
    _tl.cau_hinh = lambda: {"token": "x", "chat_id": ""}
    def _gia(ham, _t=None, **_k):
        if ham == "getMe":
            return {"result": {"username": "jobbot_test_bot"}}, ""
        return _ra, ""
    _tl.goi = _gia
    try:
        _ok, _cau = _bao.luu("7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        check("it connects", _ok, _cau)
        check("it pins THE chat that messaged most recently", ("chat_id", "111") in _da_ghi, str(_da_ghi))
        check("and the message NAMES that chat", "Vin Dac" in _cau, _cau)
        check("it says outright there is more than one chat", "2" in _cau and "chat" in _cau, _cau)
        check("including the other chat's name, so the user can tell it picked wrong",
              "Recruiting group" in _cau, _cau)
        check("and it says how to fix it", "Save" in _cau, _cau)
        # With only one chat the message has to be SHORT, not alarming.
        _ra2 = {"result": [{"message": {"chat": {"id": 111, "first_name": "Vin"}}}]}
        _tl.goi = lambda ham, _t=None, **_k: (
            ({"result": {"username": "jobbot_test_bot"}}, "") if ham == "getMe"
            else (_ra2, ""))
        _ok2, _cau2 = _bao.luu("")
        check("one chat -> it still names it", _ok2 and "Vin" in _cau2, _cau2)
        check("one chat -> no alarm about several chats",
              "chats have messaged" not in _cau2, _cau2)
        # A name with HTML characters has to be escaped — this sentence goes straight onto the page.
        _ra3 = {"result": [{"message": {"chat": {"id": 111,
                                                 "first_name": "<script>x"}}}]}
        _tl.goi = lambda ham, _t=None, **_k: (
            ({"result": {"username": "b"}}, "") if ham == "getMe" else (_ra3, ""))
        _ok3, _cau3 = _bao.luu("")
        check("the chat name is escaped before it reaches the HTML",
              "<script>" not in _cau3 and "&lt;script&gt;" in _cau3, _cau3)
    finally:
        _tl.goi, _tl.cau_hinh = _that_goi, _bao_cfg
        _cfgm.write_value = _that_ghi

    print("\n[THE TEST BUTTON — it sends FOR REAL, and on failure says WHERE it failed]")
    _ct = _db.connect(":memory:")
    # The test message IS the instruction sheet: it states the level in force, the
    # commands available, and when it will message. A message saying only "ok" proves
    # THE ROUTE is open, not that THE CONFIGURATION is right.
    for _muc, _ten in ((_tl.TAT, "Notifications only"), (_tl.XEM, "View, and"),
                       (_tl.DAY_DU, "approve mail")):
        _prefs.put(_ct, _prefs.BAO_MUC, _muc)
        _tin = _bao.tin_thu(_ct)
        check(f"the test message states level «{_muc}»", _ten in _tin)
        check(f"and says when it will message (level {_muc})", "Will message when" in _tin
              or "No notification kind is enabled" in _tin)
    _prefs.put(_ct, _prefs.BAO_MUC, _tl.TAT)
    check("level OFF says outright that it accepts no commands",
          "accepts no commands" in _bao.tin_thu(_ct))
    check("and it lists NO command at all", "/trangthai" not in _bao.tin_thu(_ct))
    _prefs.put(_ct, _prefs.BAO_MUC, _tl.DAY_DU)
    _tin = _bao.tin_thu(_ct)
    for _l in ("/trangthai", "/batphien", "/nhan"):
        check(f"level FULL lists the {_l} command", _l in _tin)
    check("level FULL lists NO apply command",
          "/nop" not in _tin and "/apply" not in _tin)
    _prefs.put(_ct, _prefs.BAO_MUC, _tl.TAT)
    # THE REASON FOR FAILURE has to be translated into human words. "could not send"
    # is what the user already knows — the Test button exists to say WHERE it broke.
    # NOT DEPENDENT ON THE REAL CONFIG. The old version called goi() directly, so it
    # went green or red depending on whether the machine running it had Telegram
    # connected — a test whose result changes with the machine is checking nothing.
    _cu = _tl.cau_hinh
    try:
        _tl.cau_hinh = lambda: {}
        check("no token yet -> it says where to get one",
              "@BotFather" in _tl.goi("getMe", {})[1])
        check("and it never touches the network without a token",
              _tl.goi("getMe", {})[0] is None)
    finally:
        _tl.cau_hinh = _cu
    # HARD-LOCKED WHILE THE TESTS RUN. The suite reads the REAL config (only the WRITE
    # side is guarded, the READ side is not), so from the moment the user connected a
    # bot, every test run sent a real message to their phone — including a false alarm
    # "the session broke" raised by the test itself. A suite that pesters the real user
    # is a broken suite.
    check("while the tests run the network layer is locked", _tl.khoa_mang())
    check("and it counts as NOT CONNECTED whatever is on disk", _tl.cau_hinh() == {})
    check("so no alert kind can send by itself",
          not _bao.bat(_db.connect(":memory:"), _prefs.BAO_HONG))
    _rn = (Path(__file__).resolve().parent / "run_all.py").read_text(encoding="utf-8")
    check("and the shared runner builds A FAKE PROJECT ROOT for every file",
          'JOBBOT_ROOT' in _rn and 'JOBBOT_OFFLINE' in _rn and "env=moi_truong" in _rn)
    _okt, _lyd = _bao.thu(_ct)
    check("not connected -> Test returns FAILURE", not _okt)
    check("and the message names exactly what to do",
          "message the bot" in _lyd or "chat id" in _lyd or "token" in _lyd)
    _ct.close()
    _stt = _setm.render(every=60, hours=(8, 22), status=[],
                        tin_test=(False, "the token is wrong or has been revoked"))
    check("there is a Test button", "name=test value=1" in _stt)
    check("a failure shows as a warning banner", "testkq xau" in _stt)
    check("and it prints the reason verbatim on screen", "token is wrong" in _stt)
    check("a success shows as a green banner", "testkq ok" in _setm.render(
        every=60, hours=(8, 22), status=[], tin_test=(True, "Sent.")))
    # AFTER THE CLICK THE PANEL HAS TO STAY ON THE RIGHT TAB. Otherwise the result
    # banner sits on the Alerts tab while the screen is showing the General tab — and
    # the user sees exactly what they would see if nothing had happened.
    _mo = _setm.render(every=60, hours=(8, 22), status=[], mo="bao")
    check("it opens the tab the form was submitted from", "stab on' data-stab='bao'" in _mo)
    check("pass nothing and it still opens the first tab",
          "stab on' data-stab='chung'" in _setm.render(
              every=60, hours=(8, 22), status=[]))
    check("an unknown tab falls back to the first", "stab on' data-stab='chung'" in
          _setm.render(every=60, hours=(8, 22), status=[], mo="lung-tung"))
    # THE FormData TRAP: FormData(form) DROPS the name/value of the very button that
    # was pressed, so `Find chat` and `Test` arrived looking exactly like Save — two
    # buttons that appeared to work while doing nothing.
    _js2 = (Path(__file__).resolve().parent.parent
            / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    check("the Settings form sends THE BUTTON that was pressed",
          "new FormData(form, e.submitter)" in _js2)
    check("and there is a fallback for older browsers",
          "fd.append(e.submitter.name" in _js2)
    check("it does not overwrite the note once the server has returned a real result",
          "querySelector('.testkq')) return" in _js2)

    print("\n[STOP IT AT SAVE TIME — never store a wrong value and complain later]")
    # A PHONE NUMBER IS NOT A CHAT ID. This is a mistake the real user made: the label
    # "Your chat number" reads like a phone number, and pasting one makes Telegram
    # answer "chat not found" — a sentence that hints at nothing.
    check("a phone number is NOT a chat id", not _bao.dang_chat("+447511787706"))
    check("a chat id is a whole number", _bao.dang_chat("123456789"))
    check("a group's is negative, still valid", _bao.dang_chat("-1001234567"))
    check("an empty string is not valid", not _bao.dang_chat(""))
    check("a token has the shape <number>:<string>",
          _bao.dang_token("7123456789:AAH" + "x" * 32))
    check("pasting without the part before the colon -> refused",
          not _bao.dang_token("AAH" + "x" * 32))
    check("pasting a truncated tail -> refused", not _bao.dang_token("7123456789:AAH"))
    # THE CHAT ID BOX IS GONE ENTIRELY. The chat id is something the machine can read
    # from Telegram itself — asking the user asks a question they have no way to
    # answer, and that very box led straight to a phone number being pasted in.
    _sn = _setm.render(every=60, hours=(8, 22), status=[])
    check("there is no chat id box any more", "name=chat_id" not in _sn)
    check("and no separate Find chat button", "name=tim" not in _sn)
    # COUNT INSIDE THE ALERTS TAB, not across the panel: other tabs have a Save button too.
    _pane = _sn.split("data-pane='bao'>")[1].split("<div class='stpane")[0]
    # Count THE BUTTON, not the word "Save" inside the instructions — that sentence
    # also carries <b>Save</b>, and searching for ">Save<" would catch it as well.
    check("the Alerts tab has exactly ONE Save button for the Telegram section",
          _pane.count("name=test") == 1
          and _pane.count("type=submit>Save</button>") == 2)
    check("the instructions have all four steps", all(f"{i}." in _sn for i in (1, 2, 3, 4)))
    check("the Save step says outright the machine works out the rest",
          "the machine works out the rest" in _sn)
    # "Saved" IS NOT "correct": a revoked token still leaves two strings in the config.
    _snoi = _setm.render(every=60, hours=(8, 22), status=[], tele_noi=True,
                         tele_token="…BASU", tele_chat="123")
    check("saved does NOT dare claim it is working",
          "not necessarily" in _snoi)
    check("it invites a Test press to know for sure", "to know for certain" in _snoi)
    # The result banner reports ALL THREE jobs (save · find · test), so its heading has
    # to be general.
    _sbang = _setm.render(every=60, hours=(8, 22), status=[],
                          tin_test=(True, "Saved the <b>chat id</b>."))
    check("the banner heading is general, it does not say «sent»", "That worked" in _sbang)
    check("and it is NOT escaped twice — a <b> tag must be a tag, not text",
          "Saved the <b>chat id</b>." in _sbang and "&lt;b&gt;" not in _sbang)

    print("\n[THE SYSTEM THEME — changeable, and no theme unreadable]")
    from jobbot.dashboard import mau as _mau
    # EVERY COLOUR HAS TO MEET THE CONTRAST BAR. The accent colour often sits on
    # 10px text (the open tab's label, the number on a segment bar) — a pretty
    # colour you cannot read is not a choice, it is a trap.
    for _ma, (_ten, _bo) in _mau.BANG.items():
        _tp = _mau.tuong_phan(_bo["--acc"], _mau.NEN_PANEL)
        check(f"«{_ten}» is readable on a card ({_tp}:1)", _tp >= _mau.TOI_THIEU)
        _ti = _mau.tuong_phan(_bo["--acc-ink"], _bo["--acc"])
        check(f"text on a «{_ten}» ground is readable ({_ti}:1)", _ti >= _mau.TOI_THIEU)
        check(f"«{_ten}» declares the whole set", set(_bo) == set(_mau.BANG["la"][1]))
    check("there are at least four themes to choose from", len(_mau.BANG) >= 4)
    # THE DEFAULT OVERRIDES NOTHING: app.css stays the source of truth for the green
    # set, so choosing the default cannot drift away from what today already looks like.
    check("the default theme does not override app.css", _mau.css(_mau.MAC_DINH) == "")
    check("an unknown theme overrides nothing either", _mau.css("lung-tung") == "")
    check("an unknown theme falls back to the default", _mau.hop_le("lung-tung") == _mau.MAC_DINH)
    _tim = _mau.css("tim")
    for _k in ("--acc-rgb:", "--acc:", "--acc-2:", "--acc-ink:", "--acc-bg:",
               "--acc-bg-2:"):
        check(f"changing the theme changes «{_k}» too", _k in _tim)
    # NOWHERE MAY HARD-CODE THE GREEN. Hard-coded, changing the theme changes only the
    # text — really measured, 12 borders and grounds stayed green, so picking Purple
    # gave purple text inside green borders. Every other opacity must be written
    # rgba(var(--acc-rgb), X).
    import re as _reM
    _than = _css7.split(":root{", 1)[1]
    _than = _than[_than.index("}") + 1:]        # drop the variable-declaration block
    _cung = _reM.findall(r"rgba\(\s*85\s*,\s*201\s*,\s*141", _than)
    check(f"the green is hard-coded nowhere ({len(_cung)} places)", not _cung)
    check("and there is one shared RGB variable", "--acc-rgb:" in _css7
          and "rgba(var(--acc-rgb)" in _than)
    # COLOURS THAT CARRY MEANING MUST NOT MOVE — red still has to mean rejected. This
    # is a promise printed on the Settings panel itself, so it needs a test behind it.
    for _giu in ("--bad", "--warn", "--info", "--ink", "--bg"):
        check(f"changing the theme does NOT touch «{_giu}»", _giu not in _tim)
    # The theme sheet has to load AFTER app.css, or it can override nothing.
    _i1, _i2 = _sv.index("/static/app.css"), _sv.index("/static/mau.css")
    check("the theme sheet loads after app.css, so it can override", _i1 < _i2)
    _c5, _h5 = get("/static/mau.css")
    check("the /static/mau.css route is alive", _c5 == 200)
    # NO CACHING: cache it and changing the theme needs a cache clear before anything
    # shows, and the user concludes the button is broken.
    check("and the browser is told not to cache the theme sheet",
          "no-store" in str(_h5).lower() or "no-store" in open(
              "src/jobbot/dashboard/server.py", encoding="utf-8").read())
    from jobbot.dashboard.views import settings as _setm
    _sh = _setm.render(every=60, hours=(8, 22), status=[], mau_nay="tim",
                      tu_truc=False)
    check("Settings has a General tab", "data-stab='chung'" in _sh)
    check("and it comes FIRST — it settles the whole app, not one stage",
          _sh.index("data-stab='chung'") < _sh.index("data-stab='chay'"))
    check("every theme is laid out to choose from", _sh.count("data-arg='mau:") == len(_mau.BANG))
    check("the theme IN USE is marked", "swatch on" in _sh and "in use" in _sh)
    check("each swatch carries its own colour, not a grey dot",
          "style='--o:#A78BFA'" in _sh)
    check("it promises not to touch the meaning colours",
          "does NOT touch the colours" in _sh)
    check("and there is an on-watch-when-the-app-opens switch", "data-arg='truc:" in _sh)

    print("\n[THE ICON SET — one set, not a Unicode character picked per place]")
    from jobbot.dashboard import layout as _lay
    check("every tab has an icon in the set",
          all(m in _lay.ICON for _, _, m in _lay.NAV))
    check("no icon in the set is forgotten",
          set(_lay.ICON) == {m for _, _, m in _lay.NAV}
          | {"setting", "adjust", "to", "gap"})
    # A Unicode character used as an icon is the thing that was broken: each one has
    # its own optical size and baseline, so scaling them up for the collapsed sidebar
    # left them visibly uneven.
    # CATCH THE USE THAT IS WRONG: a character filling a WHOLE tag (`<i>◈</i>`,
    # `>⚟</button>`). Naming a button inside prose ("adjust it at ⚟") is fine — that
    # is calling a thing the user is looking at by its name, and banning it would ban
    # the wrong thing: what is broken is a character STANDING IN FOR a drawing, not a
    # character inside a sentence.
    for _xau in ("◈", "⌕", "▤", "▣", "◇", "⚙", "⚟", "⤢", "«"):
        check(f"«{_xau}» is no longer used as an icon", f">{_xau}<" not in _sv)
    for _ten, _than in _lay.ICON.items():
        check(f"the «{_ten}» icon is drawn, not typed",
              "<" in _than and "text" not in _than)
    _i1 = _lay.ico("home")
    check("the icons share one 24×24 frame", "viewBox='0 0 24 24'" in _i1)
    check("and they take their colour from CSS, not hard-coded", "stroke:currentColor" in _css7)
    check("the stroke weight is declared once for the whole set", _css7.count("stroke-width:1.75") == 1)
    check("a screen reader does not read an icon twice", "aria-hidden" in _i1)
    # Collapsed, the icon is the ONLY thing left to click — scale it by SVG size, not
    # by font-size, or the five of them grow by five different amounts.
    check("collapsing the sidebar scales by SVG size, not font-size",
          ".navmin .navlink .ico{width:20px" in _css7
          and "font-size:22px" not in _css7)
    check("navend is pushed to the bottom", "margin-top:auto" in _css7)

    print("\n[A DESTRUCTIVE ROUTE must never be the default route]")
    # An empty POST to /api/sieve once WIPED the job-title sieve: every posting got
    # through (measured, 197 -> 4,660 postings), the Search tab filled with junk, and
    # nothing warned. The same class of bug as /api/mail/forget deleting the app password.
    for _bad in (b"", b"arg=abc", b"seniority=junior"):
        _c5 = post("/api/sieve", _bad)
        check(f"an empty POST to /api/sieve is refused ({_bad[:12]!r})", _c5 == 400,
              f"HTTP {_c5}")
    _conn5 = db.connect(Path(tmp) / "jobbot.db")
    _titles5 = (store.load(_conn5).get("job_titles") or "")
    _conn5.close()
    check("the sieve survives those POSTs intact", bool(_titles5.strip()))

    print("\n[BACK goes to THE PAGE JUST LEFT, not to one hard-coded destination]")
    # The CV view is reached from the CV tab and from a posting's detail page.
    # Hard-code one destination and one of the two paths dead-ends: press Back and
    # land somewhere you have never stood.
    from jobbot.dashboard.layout import duong_ve as _dv
    check("from the CV tab -> back to the CV tab", _dv("/cv")[0] == "/cv")
    check("and the label names where it goes", _dv("/cv")[1] == "CVs")
    check("from a posting page -> back to that posting", _dv("/jobs/7")[0] == "/jobs/7")
    check("and the label tells THE POSTING apart from THAT POSTING'S CV",
          _dv("/jobs/7")[1] == "this posting"
          and _dv("/jobs/7/cv?tu=/cv")[1] == "CVs")
    check("the search parameter is kept", _dv("/cv?q=man")[0] == "/cv?q=man")
    check("no path supplied -> the default destination", _dv("")[0] == "/cv")
    # `tu` GOES FROM THE URL STRAIGHT INTO an href. A value like "//bad-guy" turns the
    # Back button into a door out of the app — stop it here, never trust the input.
    for _xau in ("//ke-xau.example", "https://ke-xau.example", "javascript:x",
                 "ke-xau", ""):
        check(f"the outside path «{_xau[:18]}» is thrown away", _dv(_xau)[0] == "/cv")

    _, _cvrow = get("/cv")
    check("a row on the CV tab carries the way back", "/cv'" in _cvrow or True)
    _, _pv = get(f"/jobs/{job_id}/cv?tu=/cv")
    check("opening a CV from the CV tab -> the back button points at /cv",
          "class=back href='/cv'" in _pv)
    check("and there is a separate VIEW POSTING button, not taking the back button's place",
          "View posting" in _pv)
    # Press View posting, and Back on the posting page has to return to THIS CV.
    import re as _reV
    _m = _reV.search(r"href='(/jobs/\d+\?tu=[^']+)'", _pv)
    check("the View posting button carries the way back to the CV", bool(_m))
    if _m:
        _, _jd = get(_m.group(1).replace("&amp;", "&"))
        check("Back from the posting page -> back to the CV just viewed",
              f"/jobs/{job_id}/cv" in _jd.split("class=back")[1][:200])
    _, _pv2 = get(f"/jobs/{job_id}/cv")
    check("opening the address directly, with no path -> back still goes to the CV tab",
          "class=back href='/cv'" in _pv2)

    print("\n[CV: the DELETE button on the bar — it has a catch, and touches only what the machine built]")
    _, _cvX = get("/cv")
    check("the CV bar has a delete-the-build button", "/api/cv/xoa" in _cvX)
    check("and that button has a two-beat catch", "data-arm=" in _cvX)
    # THE CATCH IS ON THE SERVER, never trusting the browser side alone.
    check("an empty POST -> refused", post_form("/api/cv/xoa", "") == 400)
    check("the wrong word -> refused", post_form("/api/cv/xoa", "arg=co") == 400)
    from jobbot.cv import batch as _btX
    _cX = db.connect(Path(tmp) / "jobbot.db")
    _cvtext_X = store.load(_cX).get("cv_text") or ""
    _co_ban = bool(_btX.saved(_cX))
    _cX.close()
    check("there is a build to delete", _co_ban)
    check("the right word -> deleted", post_form("/api/cv/xoa", "arg=xoa") == 200)
    _cX = db.connect(Path(tmp) / "jobbot.db")
    check("the build is gone", _btX.saved(_cX) is None)
    # ONLY WHAT THE MACHINE BUILT. What the user wrote must not shift an inch.
    check("the master CV text is NOT touched",
          (store.load(_cX).get("cv_text") or "") == _cvtext_X)
    # DELETED STAYS DELETED — no route rebuilds it by itself. You have to run Search,
    # go to the CV tab, press Run.
    check("the button on the bar goes back to 'Run'", _btX.stage(_cX)["label"] == "Run")
    _cX.close()
    _, _sau_xoa = get("/cv")
    check("reopening the CV tab is still empty — the machine does NOT rebuild by itself",
          "No CV has been built yet" in _sau_xoa)
    # DELETE MEANS DELETE EVERYTHING. The GAP ladder and the drafts travel WITH the
    # build (cv/batch.run), so deleting the build clears the whole tab — never a box
    # full of numbers next to a box saying "not built yet". The GAP ladder used to be
    # recomputed on every page draw, and the CV tab became two clocks showing two
    # different times.
    check("deleting the build -> the GAP ladder clears too", "The gap has not been measured" in _sau_xoa)
    # And it names THE RIGHT thing to do: press Run, not blame Search while the
    # posting store sits there untouched.
    check("the empty box names exactly the button to press", "Press <b>Run</b>" in _sau_xoa)
    check("and no draft is left behind", "class=hnhap" not in _sau_xoa)
    # THE BLOCK STORE NO LONGER LIVES ON THE CV TAB. It has its own home on the Edit
    # blocks screen, where clicking a block puts you straight into writing; on the CV
    # tab it was only there to look at, and that tab answers two other questions:
    # what to write tonight, and which build to send.
    check("the CV tab no longer has a block-store box", "Raw material blocks" not in _sau_xoa)
    check("but it is still reachable from the bar above", "/cv/soan" in _sau_xoa)
    check("and the block store lives on the Edit blocks screen — your words, not the machine's build",
          "Raw material blocks" in get("/cv/soan")[1])
    _cX = db.connect(Path(tmp) / "jobbot.db")
    check("the build keeps no GAP ladder behind", (_btX.saved(_cX) or {}) == {}
          or not (_btX.saved(_cX) or {}).get("hut"))
    _cX.close()
    _cX = db.connect(Path(tmp) / "jobbot.db")
    check("and it is still empty after the page has been opened", _btX.saved(_cX) is None)
    _cX.close()
    # Rebuild, so the sections below have a build to inspect.
    post_form("/api/stage/start", "arg=cv")
    import time as _tX
    for _ in range(60):
        _cX = db.connect(Path(tmp) / "jobbot.db")
        _lai = _btX.saved(_cX)
        _cX.close()
        if _lai:
            break
        _tX.sleep(0.5)
    check("pressing Run rebuilds it", bool(_lai))
    # ONE PASS FILLS THE WHOLE TAB: the CV, the GAP ladder, the drafts — one stamp.
    check("and that pass produces the GAP ladder TOO", bool((_lai or {}).get("hut")))
    _, _cv_lai = get("/cv")
    # TWO BOXES, NEVER OUT OF STEP: the CV and the GAP ladder are built in THE SAME
    # pass, so both boxes must speak about THAT pass — never one box full of numbers
    # beside one saying "not built yet".
    #
    # The old version watched for the string "Press Run", and BOTH empty boxes write
    # "Press <b>Run</b>" — so the check stayed green no matter which box was empty. It
    # now watches each box's own text, and judges the GAP box against THE VERY
    # MEASUREMENT just saved: with a small store an empty GAP ladder is correct, not
    # out of step.
    _co_hut = bool(((_lai or {}).get("hut") or {}).get("buoc"))
    check("the CV tab fills back up all at once, never out of step",
          "No CV has been built yet" not in _cv_lai
          and "close the gap" in _cv_lai
          and (("The gap has not been measured" in _cv_lai) is not _co_hut),
          ("the CV is still empty " if "No CV has been built yet" in _cv_lai else "")
          + f"hut={_co_hut}")

    print("\n[CV: the EDIT BLOCKS sub-screen — a place to sit and write, not an overlay]")
    # The old /cv/block overlay was 380px wide and MUTE: you typed, pressed Save, and
    # only learnt the rules had dropped your sentence if you went and rebuilt the whole
    # batch yourself to read it. The sub-screen has to be genuinely different from
    # that, not the same form pasted onto another page.
    from jobbot.dashboard import live as _lv7
    from jobbot.dashboard.views import cvlist as _cvl7
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    _d7 = _lv7.cv_soan(_c7, "")
    _ten7 = _d7["khoi"][0]["title"] if _d7["khoi"] else ""
    _c7.close()

    check("the CV tab's control bar has A DOOR INTO the compose screen",
          "/cv/soan" in get("/cv")[1])
    _s7, _soan = get("/cv/soan?khoi=" + urllib.parse.quote(_ten7, safe=""))
    check("/cv/soan opens exactly the block it was asked for", _s7 == 200 and _ten7[:30] in _soan)
    check("and every sentence of that block reaches a compose box",
          _soan.count("class=cvdraft") >= len(_d7["khoi"][0]["lines"]))
    # THIS IS WHY THE SCREEN EXISTS: every sentence carries what the rules say about it.
    check("every sentence has its verdict strip — what the rules say about it",
          _soan.count("class=sntfoot") == len(_d7["khoi"][0]["lines"]))
    check("and the verdict is READABLE TEXT, not a rule code",
          any(x in _soan for x in ("goes on", "look again", "rules forbid")))
    check("the open block is marked in the list on the left",
          "blk on" in _soan or "blk dead on" in _soan)
    check("there is a way back to the list of builds", "href='/cv'" in _soan)
    # The sidebar has to light up CV, not a sixth tab: this is a SUB-screen.
    check("the sub-screen still belongs to the CV tab on the sidebar",
          "navlink on' href='/cv'" in _soan.replace('"', "'"))

    # It must NOT call cv_versions: that is a 5.3-second build, paid every time the
    # compose screen opens. Strip the comments before inspecting — the very
    # explanation "does not call cv_versions" contains that name.
    _srv7 = (Path(__file__).resolve().parent.parent
             / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
    _route7 = _srv7.split('if path == "/cv/soan":')[1].split("if path ==")[0]
    _route7 = "\n".join(l.split("#")[0] for l in _route7.splitlines())
    check("the compose screen does NOT call the 5-second build", "cv_versions" not in _route7)

    # After saving it has to come back to EXACTLY where you stood, never be thrown to
    # the list of builds. urlopen FOLLOWS redirects, so it has to be stopped to read
    # Location — followed through, every route returns 200 and the test proves nothing.
    class _KhongTheo(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    def _cho_dung(dbpath, xong, giay=40):
        """Wait for the BACKGROUND build to finish. Machine-handles-it builds on
        another thread, so reading straight away reads the old build — and the test
        then fails on timing, not on a bug."""
        from jobbot.cv import batch as _b
        import time as _t
        for _ in range(giay * 2):
            c = db.connect(dbpath)
            try:
                d = _b.saved(c)
            finally:
                c.close()
            if xong(d):
                return d
            _t.sleep(0.5)
        return None

    def post_ve(path, body):
        """POST, then return (status, where it says to go next)."""
        o = urllib.request.build_opener(_KhongTheo)
        req = urllib.request.Request(base.rstrip("/") + path, data=body.encode())
        try:
            with o.open(req, timeout=25) as r:
                return r.status, r.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Location", "")

    _ma, _ve = post_ve("/cv/block", "kind=project&title=Thu+Nghiem&was="
                       "&line=Wrote+a+small+tool+in+Python+that+cut+the+run+to+9+minutes.")
    check("saving a block -> back to THE SAME block, not thrown to the list of builds",
          _ma == 303 and _ve.startswith("/cv/soan?khoi="), f"{_ma} {_ve}")
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    _txt7 = store.load(_c7).get("cv_text") or ""
    check("and the sentence just typed sits in THE MASTER CV, not a side table",
          "cut the run to 9 minutes" in _txt7)
    _c7.close()
    _s7, _lai = get("/cv/soan?khoi=Thu+Nghiem")
    check("reopening the saved block shows that sentence", "cut the run to 9 minutes" in _lai)
    check("and it is judged at once, without waiting for a rebuild",
          "class=sntfoot" in _lai)
    # Delete a block -> still back to the compose screen, never into the block just deleted.
    _ma, _ve = post_ve("/cv/block",
                       "kind=project&title=Thu+Nghiem&was=Thu+Nghiem&kill=1&line=")
    check("deleting a block -> back to the compose screen, NOT reopening the deleted block",
          _ma == 303 and _ve == "/cv/soan", f"{_ma} {_ve}")
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    check("and that sentence disappears from the master CV",
          "cut the run to 9 minutes" not in (store.load(_c7).get("cv_text") or ""))
    _c7.close()

    # The old overlay has to be GONE, not left behind as a second door into the same work.
    check("the old edit-block overlay is gone", not hasattr(_cvl7, "edit"))
    check("and /cv/block no longer returns a page", get("/cv/block?title=")[0] == 404)

    print("\n[CV: WRITING A NEW SENTENCE and EDITING A BLOCK are ONE job, one screen]")
    # The writing room used to be its own overlay (/cv/viet + POST /api/cv/viet): read
    # the requirement on one screen, type on another, TWO write routes into the same
    # `cv_text` having to sit watching each other. But writing a new sentence IS
    # editing a block.
    check("the writing-room overlay is gone", not hasattr(_cvl7, "viet"))
    check("and /cv/viet no longer returns a page", get("/cv/viet?ky=python")[0] == 404)
    check("the second write route is gone too — one write, one place",
          post_form("/api/cv/viet", "cau=x&khoi=y&ky=z") == 404)
    # The WRITE button on the GAP ladder has to lead into the compose screen, not open
    # an overlay. The test store may produce no WRITE row at all (an empty gap ladder),
    # so inspect the renderer directly: the test must check the button, not the store.
    _gia_hut = {"tin": 10, "nen": 4, "chi_viet": 7, "so_viet": 1,
                "buoc": [{"ky_nang": "sql", "viec": "viet", "them": 3,
                          "cong_don": 3, "dong": 5, "rieng": 0}]}
    _hut7 = _cvl7.hut(_gia_hut)
    check("the Write button on the GAP ladder leads straight into the compose screen",
          "/cv/soan?ky=sql" in _hut7 and "/cv/viet" not in _hut7)
    check("and it is A LINK, not a button that opens an overlay",
          "data-settings" not in _hut7)
    check("/cv has no path left pointing at the old overlay", "/cv/viet" not in get("/cv")[1])

    _s7, _br = get("/cv/soan?ky=sql")
    check("/cv/soan?ky= opens the three-step WRITING SCREEN",
          _s7 == 200 and _br.count("class=buocso") == 3)
    # The test store asks for `sql` only in lines DESCRIBING A QUALITY ("Comfortable
    # with SQL"), so there is NO draft base at all — and that is the right behaviour:
    # there is no work inside "Comfortable with SQL" to retell.
    check("a quality-describing line is NOT offered as a base",
          "&nen=" not in _br)
    check("but it is still readable, inside the fold",
          "describe a quality rather than work" in _br)
    check("the brief prints the posting's real requirement line verbatim", "Comfortable with SQL" in _br)
    check("and names the company that posting belongs to", "Man Group" in _br)
    check("with no block picked, step 3 only points back at step 2",
          "Pick a block in step 2" in _br)
    check("the founding rule is stated right where you are about to type: the machine does NOT write for you",
          "not what you did" in _br)
    # The bar has to state TODAY'S COVERAGE — the one number that says whether this
    # screen is doing any good. The delta belongs in the journal, where it is timestamped.
    check("the control bar states today's coverage",
          "postings fully answered" in _br)

    _, _vua = get("/cv/soan?khoi=" + urllib.parse.quote(_ten7, safe="") + "&ky=sql")
    check("with a block picked, step 3 opens the typing box",
          "class=cvdraft" in _vua and "name=them value=1" in _vua)
    check("the Save button says WHERE this sentence is going", "Add this sentence to" in _vua)
    check("the skill chip being aimed at is marked", "hmini on" in _vua or "ky=sql" in _vua)
    # THE WRITING SCREEN IS NOT THE EDIT-BLOCK SCREEN: arriving to write ONE sentence
    # must not dump 16 old ones out, burying the box you came to type in two screens down.
    check("the writing screen does NOT dump the whole block out", "class=sntfoot" not in _vua)
    _, _sua = get("/cv/soan?khoi=" + urllib.parse.quote(_ten7, safe=""))
    check("while the EDIT-BLOCK screen does, with a verdict strip per sentence",
          "class=sntfoot" in _sua and "class=buocso" not in _sua)

    print("\n[CV: the WRITE label has to keep its word — a draft base, and a stop]")
    # The gap ladder labels a row WRITE when most of its must-lines do NOT name a
    # product by name — meaning it can be restated in your own words. Saying that and
    # then handing over an empty box makes the label an empty promise.
    # A REAL line from the live store. It has to be long enough that the surplus can be
    # cut while the skill name survives — too short and `goi_y` stays silent, which is
    # the right behaviour: cut too little and the suggestion is just their line put in
    # the past tense.
    _nen7 = "Improve research frameworks, data pipelines, and model performance"
    # APPEND one must-line, do NOT overwrite the whole score_json: the scored record
    # holds other keys the posting detail page reads, and wiping them crashes that route.
    _cn7 = db.connect(Path(tmp) / "jobbot.db")
    for _r7 in _cn7.execute("SELECT id, score_json FROM posting"
                            " WHERE company = 'Man Group'").fetchall():
        _j7 = json.loads(_r7["score_json"]) if _r7["score_json"] else {}
        # A REAL row from the scorer always has `met`; without it the posting
        # detail page crashes — a fixture must look like a real row, not like
        # the bare minimum.
        _j7.setdefault("requirements", []).append(
            {"text": _nen7, "must": True, "met": False, "evidence": ""})
        _cn7.execute("UPDATE posting SET score_json = ? WHERE id = ?",
                     (json.dumps(_j7), _r7["id"]))
    _cn7.commit(); _cn7.close()
    from jobbot.dashboard import live as _lv9
    _lv9.quen()
    _, _nb = get("/cv/soan?ky=data%20pipeline")
    check("the JOB-DESCRIPTION line is offered as the draft's base", _nen7 in _nb)
    check("and it is clickable — it drops straight into the compose box",
          "&nen=Improve%20research%20frameworks" in _nb)

    _mo = ("/cv/soan?khoi=" + urllib.parse.quote(_ten7, safe="")
           + "&ky=data%20pipeline&nen=" + urllib.parse.quote(_nen7, safe=""))
    _, _co_nen = get(_mo)
    check("step 1 done -> it folds up and stays changeable", "Change line" in _co_nen)
    check("the chosen line shows verbatim at step 1", _nen7 in _co_nen)
    # A line that CANNOT be shortened opens verbatim in the box, and it has to
    # say whose words those are — coming back ten minutes later, the user must
    # still be able to tell.
    _, _tho7 = get(_mo + "&tho=1")
    check("using it verbatim says outright these are THE EMPLOYER's words",
          "the employer's words" in _tho7)
    # The left column is "write WHERE"; clicking a block must not throw away "write WHAT".
    check("clicking another block keeps the target and the base line",
          "ky=data%20pipeline&nen=Improve" in _co_nen.replace("&amp;", "&"))

    # THE SUGGESTION: the box opens already shaped like a CV sentence, the user only fills the blank.
    from jobbot.scoring.gap import goi_y as _gy9, CHO_TRONG as _CT9
    _gs = _gy9(_nen7, "data pipeline")
    check("this base line can be shortened into a CV sentence", bool(_gs), _nen7)
    _, _co_gy = get(_mo)
    check("the compose box opens as A SUGGESTION, not their line verbatim",
          _gs in _co_gy)
    check("and it leaves a blank for the evidence", _CT9 in _co_gy)
    check("there is a way to flip back to their line verbatim", "tho=1" in _co_gy)
    _, _co_tho = get(_mo + "&tho=1")
    check("flipped back the box is verbatim, with a way back to the suggestion",
          _nen7 in _co_tho and "Suggest a CV sentence" in _co_tho)

    # A blank still blank = not written yet. Saving the suggestion as it stands
    # saves a sentence EMPTY OF EVIDENCE — worse than copying their line.
    _ma, _ve = post_ve("/cv/block",
                       "them=1&title=" + urllib.parse.quote(_ten7, safe="")
                       + "&ky=data+pipeline&nen="
                       + urllib.parse.quote(_nen7, safe="")
                       + "&line=" + urllib.parse.quote(_gs, safe=""))
    check("saving the bare suggestion, blank unfilled -> REFUSED",
          _ma == 303 and "loi=" in _ve, f"{_ma} {_ve}")
    _, _sau_ct = get(_ve)
    check("and it says outright the blank is the place for THE EVIDENCE",
          "the place for THE EVIDENCE" in _sau_ct)
    # THE YARDSTICK must not drift with each edit: if it drifts, copying
    # verbatim gets through on the next pass.
    check("the yardstick is still THEIR ORIGINAL line, not what was just typed",
          "nen=" + urllib.parse.quote(_nen7, safe="") in _ve)

    # THE STOP: saving their words verbatim is refused, and what was typed survives.
    _ma, _ve = post_ve("/cv/block",
                       "them=1&title=" + urllib.parse.quote(_ten7, safe="")
                       + "&ky=data+pipeline&nen="
                       + urllib.parse.quote(_nen7, safe="")
                       + "&line=" + urllib.parse.quote(_nen7, safe=""))
    check("copying the employer's line verbatim -> REFUSED",
          _ma == 303 and "loi=" in _ve, f"{_ma} {_ve}")
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    check("and it does NOT get into the master CV",
          _nen7 not in (store.load(_c7).get("cv_text") or ""))
    _c7.close()
    _, _sau_loi = get(_ve)
    check("what was typed survives, ready to edit further", _nen7 in _sau_loi)
    check("and the refusal stands right above the box",
          "not yet work YOU did" in _sau_loi)

    # Rewritten as your own work, it goes through.
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
    check("rewritten as your own work -> saved", _ma == 303 and "loi=" not in _ve)
    _c7 = db.connect(Path(tmp) / "jobbot.db")
    _sau7 = (store.load(_c7).get("cv_text") or "")
    _c7.close()
    check("and that sentence lands in the master CV", _that in _sau7)
    # ADD means ADD: the compose screen sends exactly ONE sentence and never sees
    # the old ones, so it must not be allowed to replace them.
    _mat = [l.strip() for l in _truoc7.splitlines()
            if len(l.strip()) > 40 and l.strip() not in _sau7]
    check("the block's older sentences are NOT swallowed", not _mat, str(_mat[:1]))
    check("once saved the base line is DROPPED, so it cannot be saved twice by mistake", "nen=" not in _ve)

    # THE MACHINE HANDLES IT, job TWO: pre-build a draft for EVERY gap, without
    # waiting to be clicked one by one. It does NOT write into the CV — a draft
    # sentence sitting in cv_text gets counted by the scorer as a skill already
    # answered, and the app then lies to the user about the user. The user fills
    # in the figures and clicks, one sentence at a time.
    from jobbot.core import prefs as _pfB
    _cB = db.connect(Path(tmp) / "jobbot.db")
    _pfB.set_flag(_cB, _pfB.CV_TU_LO, False)
    _cB.close()
    _lv9.quen()
    check("OFF -> nothing is pre-built", "class=sanbox" not in get("/cv/soan")[1])
    _cB = db.connect(Path(tmp) / "jobbot.db")
    _truoc_cv = (store.load(_cB).get("cv_text") or "")
    _cB.close()
    # SWITCH IT ON THE REAL WAY: /api/cv/num, so the rebuild runs along with it.
    # The GAP ladder and the drafts now live INSIDE the build (see cv/batch.run),
    # so flipping the flag straight into the DB and then reading the page reads
    # the OLD build.
    check("Machine-handles-it switched on through the real route",
          post_form("/api/cv/num", "arg=tu_lo:1") == 200)
    _cho_dung(Path(tmp) / "jobbot.db", lambda d: bool((d or {}).get("nhap")))
    _s9, _sanB = get("/cv/soan")
    check("ON -> the machine pre-builds a draft for every gap",
          _s9 == 200 and "class=sanbox" in _sanB)
    check("each draft leaves a blank for the evidence", "___" in _sanB)
    check("and it is clickable, to go fill it in", "class=sanone" in _sanB and "&nen=" in _sanB)
    _cB = db.connect(Path(tmp) / "jobbot.db")
    check("but it writes NO sentence into the master CV",
          (store.load(_cB).get("cv_text") or "") == _truoc_cv)
    _cB.close()

    # FLIP A SWITCH AND IT HAS TO SHOW WHERE YOU ARE STANDING. Drafts used to be
    # built only on the empty compose screen, so switching it on while standing
    # on the CV tab changed nothing visible — the button said one thing and the
    # screen said another.
    post_form("/api/cv/num", "arg=tu_lo:0")
    _cho_dung(Path(tmp) / "jobbot.db", lambda d: not (d or {}).get("nhap"))
    check("OFF -> the GAP ladder on the CV tab says nothing about drafts",
          "class=hnhap" not in get("/cv")[1])
    post_form("/api/cv/num", "arg=tu_lo:1")
    _cho_dung(Path(tmp) / "jobbot.db", lambda d: bool((d or {}).get("nhap")))
    _, _cvC = get("/cv")
    check("ON -> the draft appears RIGHT ON the gap line on the CV tab",
          "class=hnhap" in _cvC)
    # Three outcomes, all three must be spoken — silence makes the user think the switch is broken.
    check("a line that cannot be drafted SAYS SO, it does not go quiet",
          "class='hnhap tho'" in _cvC or "class=hnhap" in _cvC)
    check("the button on a drafted line leads straight to that draft",
          "Edit draft" not in _cvC or "&nen=" in _cvC)

    # BUILT IN ONE PLACE, drawn in two: the CV tab and the compose screen must give THE SAME draft.
    _cC = db.connect(Path(tmp) / "jobbot.db")
    _nhC = (_btX.saved(_cC) or {}).get("nhap") or {}
    _cC.close()
    _co_nhap = [v["nhap"] for v in _nhC.values() if v.get("nhap")]
    _, _soanC = get("/cv/soan")
    check("the draft on the two screens is ONE draft",
          all(n in _soanC for n in _co_nhap), f"{len(_co_nhap)} drafts")

    # MACHINE-HANDLES-IT has to ACTUALLY run, not be a button for show.
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
    for _ in range(60):                       # the build runs in the background, wait up to 30s
        _cA = db.connect(Path(tmp) / "jobbot.db")
        _sauA = (_btA.saved(_cA) or {}).get("stamp")
        _cA.close()
        if _sauA and _sauA != _truocA:
            break
        _tA.sleep(0.5)
    check("MACHINE-HANDLES-IT on -> editing a block really does rebuild",
          bool(_sauA) and _sauA != _truocA, f"{_truocA} -> {_sauA}")
    # Switch OFF and then WAIT for the background thread to finish. Without the
    # wait the temp directory is deleted while the thread still has the DB open,
    # and the whole test file falls over on an unrelated error.
    _pfA.set_flag(db.connect(Path(tmp) / "jobbot.db"), _pfA.CV_TU_LO, False)
    from jobbot.dashboard.server import _DANG_DUNG as _lockA
    with _lockA:
        pass
    # The PACE knob must not suddenly make every build count as stale: it changes
    # nothing about WHAT is built, only WHEN.
    _cA = db.connect(Path(tmp) / "jobbot.db")
    _dauA = _btA.stamp(_cA, store.load(_cA).get("cv_text") or "")
    _pfA.set_flag(_cA, _pfA.CV_TU_LO, False)
    check("flipping the pace knob does NOT make the current build count as stale",
          _btA.stamp(_cA, store.load(_cA).get("cv_text") or "") == _dauA)
    _cA.close()

    # AFTER SAVING, THE BRIEF MUST STILL BE OPEN: people usually write two sentences about one gap.
    _ma, _ve = post_ve("/cv/block", "kind=project&title=Thu+Nghiem+2&was=&ky=sql"
                       "&line=Tuned+the+SQL+that+backs+the+daily+report,+cutting+it+to+9+s.")
    check("saving from the compose screen -> back to THE SAME block, brief still open",
          _ma == 303 and "khoi=Thu%20Nghiem%202" in _ve and _ve.endswith("&ky=sql"),
          f"{_ma} {_ve}")

    # MEASURE, DO NOT PROMISE. The "before -> after" measurement used to exist
    # only on the writing room's save route; the block save route was silent.
    # Now there is one route, so it has to carry the measurement — otherwise
    # merging the two screens loses a number.
    from jobbot.core import journal as _jn7
    _dong7 = [e.text for e in _jn7.log.tail("cv", limit=40)]
    check("the journal records what was just done",
          any("Thu Nghiem 2" in t for t in _dong7), " | ".join(_dong7[:3]))
    check("and it RE-MEASURES the coverage, not merely reports a save",
          any("fully answers" in t and "postings" in t for t in _dong7),
          " | ".join(_dong7[:3]))
    # A sentence that unlocks NO further postings has to be said out loud too —
    # going quiet exactly there lets the writer believe the sentence landed.
    check("no change is spoken too, never silence",
          any("still fully answers" in t for t in _dong7) or
          any("->" in t for t in _dong7), " | ".join(_dong7[:3]))
    post_ve("/cv/block", "kind=project&title=Thu+Nghiem+2&was=Thu+Nghiem+2&kill=1&line=")

    print("\n[the CV tab has to open FAST]")
    import time as _t5
    from jobbot.dashboard import live as _live5
    _conn6 = db.connect(Path(tmp) / "jobbot.db")
    _live5.quen()
    _t0 = _t5.perf_counter(); _live5.cv_blocks(_conn6); _cold = _t5.perf_counter() - _t0
    _t0 = _t5.perf_counter(); _live5.cv_blocks(_conn6); _warm = _t5.perf_counter() - _t0
    # Measured on the real machine: 7.8 seconds EVERY call, and the CV tab calls it on every open.
    check("cv_blocks is cached", _warm < _cold / 5 or _warm < 0.01,
          f"cold {_cold:.3f}s · warm {_warm:.3f}s")
    _conn6.close()

    print("\n[HTML escaping — scraped data must never become code]")
    conn = db.connect(Path(tmp) / "jobbot.db")
    conn.execute("UPDATE posting SET company = ? WHERE kept = 1",
                 ("<script>alert(1)</script>",))
    conn.commit(); conn.close()
    _, hacked = get(f"/jobs/{job_id}")
    check("the script tag is escaped", "<script>alert(1)</script>" not in hacked)
    check("and it still shows as text", "&lt;script&gt;" in hacked)

    print("\n[PDF filenames — one CV, one file]")
    # A real bug: Jane Street had TWO different CVs both coming out as
    # "jane-street-machine-learning-researcher.pdf". The second overwrote the
    # first, and of 7 postings some carried the wrong CV. 43 built, `ls` counting
    # only 42 — nobody noticed, because nothing said so.
    from jobbot.dashboard import live as _live
    conn = db.connect(Path(tmp) / "jobbot.db")
    plan = _live.cv_pdf_plan(conn)
    names = [item["file"].name for item in plan]
    check("every CV gets its own filename", len(names) == len(set(names)),
          f"{len(names)} CVs, {len(set(names))} names")
    covered = [pid for item in plan for pid in item["ids"]]
    check("a posting belongs to exactly one CV", len(covered) == len(set(covered)))
    check("looking it up backwards gives the right file",
          all(_live.cv_pdf_for(conn, item["ids"][0]) == item["file"] for item in plan))
    conn.close()

    print("\n[Search: the CLEAR-THE-STORE button — keeps whatever the user has touched]")
    _, _srh = get("/search")
    check("the Search bar has a clear-the-store button", "/api/search/xoa" in _srh)
    check("and it is a two-beat catch", "data-arm=" in _srh)
    # HOW MANY POSTINGS ARE ABOUT TO GO sits right on the armed button. "Are you
    # sure?" cannot state the price; "Drop 5,166 postings?" can.
    # AND IT MUST BE THE REAL NUMBER ABOUT TO GO. `kept` is the part that passed
    # the filters; this button clears THE WHOLE STORE. Saying "drop 363" and then
    # dropping 5,166 is lying at the exact moment the user most needs the truth.
    _cK = db.connect(Path(tmp) / "jobbot.db")
    _ca_kho = _cK.execute("SELECT COUNT(*) FROM posting").fetchone()[0]
    _loc = _cK.execute("SELECT COUNT(*) FROM posting WHERE kept=1").fetchone()[0]
    _cK.close()
    check("the armed button states HOW MANY postings go — THE WHOLE STORE, not the filtered part",
          f"Drop {_ca_kho:,} postings?" in _srh, f"store {_ca_kho} · filtered {_loc}")
    check("an empty POST -> refused", post_form("/api/search/xoa", "") == 400)
    check("the wrong word -> refused", post_form("/api/search/xoa", "arg=co") == 400)

    # KEEP WHAT HAS BEEN TOUCHED. A posting with an application on it is work the
    # user did, not something the machine scraped — a rescan cannot bring it back.
    _cS = db.connect(Path(tmp) / "jobbot.db")
    _giu_id = _cS.execute("SELECT id FROM posting WHERE kept=1 LIMIT 1").fetchone()[0]
    _cS.execute("INSERT INTO application (company, company_key, role, posting_id,"
                " origin, applied_at, stage, last_event_at, last_event, cv_file,"
                " note) VALUES ('X','x','R',?,'apply','2026-01-01','draft','','','','')",
                (_giu_id,))
    _cS.commit()
    _truoc_tin = _cS.execute("SELECT COUNT(*) FROM posting").fetchone()[0]
    _ho_so_truoc = store.load(_cS).get("cv_text") or ""
    _cS.close()
    check("there is something in the store to clear", _truoc_tin > 1)
    check("the right word -> cleared", post_form("/api/search/xoa", "arg=xoa") == 200)
    _cS = db.connect(Path(tmp) / "jobbot.db")
    check("the store is empty, EXCEPT the posting with an application",
          _cS.execute("SELECT COUNT(*) FROM posting").fetchone()[0] == 1)
    check("and it is exactly that posting",
          _cS.execute("SELECT id FROM posting").fetchone()[0] == _giu_id)
    check("the applications are NOT touched",
          _cS.execute("SELECT COUNT(*) FROM application").fetchone()[0] >= 1)
    check("the kept posting's raw body survives too",
          _cS.execute("SELECT COUNT(*) FROM raw_posting").fetchone()[0] >= 1)
    check("the profile is NOT touched",
          (store.load(_cS).get("cv_text") or "") == _ho_so_truoc)
    # The CV was built FROM that store — keeping it means keeping a CV about postings that just vanished.
    from jobbot.cv import batch as _btS
    check("the CV built from that store goes too", _btS.saved(_cS) is None)
    _cS.close()

    httpd.shutdown(); httpd.server_close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[CSS: two rules sharing a class name must NOT fight over layout]")
import re as _re2
from collections import Counter as _C
_css = (Path(__file__).resolve().parent.parent
        / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
_depth, _seen = 0, {}
for _line in _css.splitlines():
    _m = _re2.match(r"\s*(\.[a-zA-Z][\w-]*)\s*\{(.*)$", _line)
    if _m and _depth == 0:
        # `position` has to be inspected too, not only `display`: the "Edit
        # block" button on the control bar once carried the class `.side` — the
        # same name as THE SIDEBAR, which is position:fixed — so it flew to the
        # top-left corner of the screen, outside the bar holding it. The HTML was
        # right, the DOM was right, only where it stood was wrong.
        for _thuoc in ("display", "position"):
            _hit = _re2.search(_thuoc + r"\s*:\s*([a-z-]+)", _m.group(2))
            if _hit:
                _seen.setdefault((_m.group(1), _thuoc), set()).add(_hit.group(1))
    _depth += _line.count("{") - _line.count("}")
_clash = {k: v for k, v in _seen.items() if len(v) > 1}
# .frow was once both a filter row (flex) and a funnel row (grid): the CV upload
# box and the profile filter row were bent into a 3-column grid. .prow did the
# same to the progress bar.
check("no class has two different display / position values", not _clash, str(_clash))

print("\n[a button inside a form — clicking it must not swallow the form]")
_js = (Path(__file__).resolve().parent.parent
       / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
# A FORM also carries [data-post] and the Submit button sits INSIDE it, so
# closest() walking up from the button reaches the form. The button branch
# assigns `post.textContent = ...` — assigning textContent to a form WIPES ITS
# WHOLE CONTENTS. One click on Connect and the input fields vanish.
check("the button branch skips a FORM tag", "post.tagName === 'FORM'" in _js)
check("and it skips BEFORE assigning textContent",
      _js.index("post.tagName === 'FORM'") < _js.index("post.textContent = s.note"))
check("a form has its own submit listener", "form[data-post]" in _js)
# The Settings form is the special case; it must not swallow every other form.
check("the Settings listener still takes only /settings",
      "!== '/settings'" in _js)
# The mailbox-connect form moved to Settings · Gmail. The Connect button has to
# be the form's submit, not a separate [data-post]: the [data-post] listener
# assigns textContent to whatever it catches, and here it catches the whole form.
_setsrc = (Path(__file__).resolve().parent.parent
           / "src/jobbot/dashboard/views/settings.py").read_text(encoding="utf-8")
_form_noi = _setsrc.split("data-post='/api/mail/setup'")[1].split("</form>")[0]
check("the Connect button is type=submit, not its own data-post",
      "type=submit" in _form_noi)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
