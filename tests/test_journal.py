"""Test nhật ký chạy — thứ app 24/7 sống chết bằng nó.

    python3 tests/test_journal.py
"""

import os, sys, tempfile, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}{' — ' + extra if extra else ''}")


with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    from jobbot.core import db
    from jobbot.core.journal import (ERROR, SEARCH, SCORE, SYSTEM,
                                     Journal, RING)

    db.connect().close()                      # dựng bảng audit

    print("[sự kiện: ghi thêm, không sửa]")
    j = Journal()
    j.emit(SEARCH, "bắt đầu quét")
    j.warn(SEARCH, "linkedin bị chặn")
    j.ok(SCORE, "chấm 208 tin")
    check("giữ lại đủ số dòng", len(j.tail(limit=99)) == 3)
    check("mới nhất lên đầu", j.tail(limit=99)[0].text == "chấm 208 tin")
    check("mức được ghi đúng",
          [e.level for e in j.tail(SEARCH, 9)] == ["warn", "info"])

    print("\n[luồng: mỗi tab chỉ thấy việc của mình]")
    check("lọc theo luồng search", len(j.tail(SEARCH, 99)) == 2)
    check("lọc theo luồng score", len(j.tail(SCORE, 99)) == 1)
    check("luồng chưa dùng thì rỗng", j.tail(SYSTEM, 99) == [])
    check("không lọc thì thấy tất cả", len(j.tail(None, 99)) == 3)

    print("\n[tiến độ: ghi đè, KHÔNG ghi đĩa]")
    j.progress(SEARCH, "đọc kỹ LinkedIn", 47, 192)
    j.progress(SEARCH, "đọc kỹ LinkedIn", 48, 192)
    check("chỉ giữ giá trị mới nhất", j.running()[SEARCH]["done"] == 48)
    check("tính được phần trăm", j.running()[SEARCH]["percent"] == 25)
    check("tiến độ KHÔNG lẫn vào nhật ký sự kiện", len(j.tail(limit=99)) == 3)
    check("đang chạy thì busy", j.busy())
    j.done(SEARCH)
    check("xong thì xoá thanh tiến độ", SEARCH not in j.running())
    check("và hết busy", not j.busy())
    j.progress(SCORE, "chấm điểm", 5, 0)
    check("không biết tổng thì phần trăm là 0", j.running()[SCORE]["percent"] == 0)
    j.done(SCORE)

    print("\n[đẩy cho giao diện]")
    chan = j.subscribe()
    j.emit(SEARCH, "tin mới")
    j.progress(SEARCH, "đang chạy", 1, 10)
    got = [chan.get_nowait(), chan.get_nowait()]
    check("sự kiện được đẩy đi", got[0]["type"] == "event" and got[0]["text"] == "tin mới")
    check("tiến độ cũng được đẩy đi", got[1]["type"] == "progress")
    check("có kèm luồng để giao diện lọc", got[1]["stream"] == SEARCH)
    j.unsubscribe(chan)
    j.emit(SEARCH, "sau khi rời")
    check("rời rồi thì không nhận nữa", chan.empty())

    print("\n[người xem chậm KHÔNG được làm nghẽn việc đang chạy]")
    # Vòng quét đứng lại vì chờ một cái hàng đợi đầy là hỏng thật; giao diện
    # mất vài dòng là chuyện nhỏ.
    slow = j.subscribe()
    for n in range(400):                       # nhiều hơn maxsize=200
        j.progress(SEARCH, "đổ tràn", n, 400)
    check("hàng đợi đầy thì bỏ tin, không treo", slow.qsize() <= 200)
    check("và việc vẫn chạy tới cuối", j.running()[SEARCH]["done"] == 399)
    j.unsubscribe(slow)
    j.done(SEARCH)

    print("\n[bộ nhớ có trần — chạy 24/7 không được phình]")
    k = Journal()
    for n in range(RING + 250):
        k.emit(SYSTEM, f"dòng {n}", persist=False)
    check(f"giữ tối đa {RING} dòng", len(k.tail(limit=99999)) == RING)
    check("giữ dòng MỚI, bỏ dòng cũ",
          k.tail(limit=1)[0].text == f"dòng {RING + 249}")

    print("\n[còn lại sau khi tắt app]")
    m = Journal()
    m.open()                                # gắn vào DB tạm
    m.emit(SCORE, "trước khi tắt")
    m.error(SCORE, "một lỗi cần nhớ")
    after = Journal()                          # "mở app lại"
    after.open()
    texts = [e.text for e in after.tail(SCORE, 99)]
    check("sự kiện được nạp lại từ đĩa", "trước khi tắt" in texts)
    check("và giữ đúng mức", after.tail(SCORE, 1)[0].level == ERROR)
    check("gắn lần hai không nhân đôi", after.open() == 0)

    # Dòng đời trước ghi bằng postings.log() chỉ có `kind`, detail rỗng —
    # nạp thẳng thì nhật ký đầy dòng trống trơn chỉ có mỗi giờ.
    conn = db.connect()
    conn.execute("INSERT INTO audit (at, kind, detail) VALUES (?,?,?)",
                 ("2026-01-01T00:00:00+00:00", "scan_started", ""))
    conn.commit(); conn.close()
    legacy = Journal(); legacy.open()
    old_line = [e for e in legacy.tail(limit=999) if e.at.startswith("2026-01-01")]
    check("dòng cũ không có detail thì lấy kind", bool(old_line))
    check("và đọc ra được chữ", old_line and old_line[0].text == "scan started")

    print("\n[chưa gắn vào DB thì KHÔNG được đụng đĩa]")
    # Đây là lý do 24 dòng của bài test lọt vào nhật ký thật: nhật ký mặc
    # định ghi thẳng db_path(), bất kể bài test đang dùng DB tạm nào.
    quiet = Journal()
    quiet.emit(SEARCH, "chỉ trong bộ nhớ")
    check("chưa open() thì không mở kết nối nào", quiet._db() is None)
    check("nhưng vẫn ghi được vào bộ nhớ", len(quiet.tail(SEARCH, 9)) == 1)

    print("\n[còn bao lâu nữa xong]")
    from jobbot.core.journal import remain_text
    check("dưới 90 giây thì nói giây", remain_text(45) == "~45 giây")
    check("trên 90 giây thì đổi sang phút", remain_text(600) == "~10 phút")
    check("trên một giờ thì nói giờ + phút", remain_text(11520) == "~3 giờ 12 phút")
    check("tròn giờ thì không viết '0 phút'", remain_text(7200) == "~2 giờ")
    check("không biết thì im, không đoán bừa", remain_text(0) == "")

    eta = Journal()
    eta.progress(SEARCH, "đọc kỹ · tin A", 1, 100)
    check("một nhịp thì CHƯA dám đoán", eta.running()[SEARCH]["eta"] == 0)
    eta.progress(SEARCH, "đọc kỹ · tin B", 2, 100)
    check("hai nhịp vẫn chưa", eta.running()[SEARCH]["eta"] == 0)
    time.sleep(0.05)
    eta.progress(SEARCH, "đọc kỹ · tin C", 3, 100)
    check("đủ ba nhịp mới nói", eta.running()[SEARCH]["eta"] > 0)
    check("và nói thành chữ luôn", eta.running()[SEARCH]["eta_text"] != "")
    check("cùng một con số với thanh tiến độ",
          eta.remaining(SEARCH) == eta.running()[SEARCH]["eta_text"])

    # Đây là cái bẫy thật: vòng tìm LinkedIn viết tên chức danh đang tìm vào
    # `what`, nên MỖI NHỊP LÀ MỘT CHỮ KHÁC. Nếu mốc thời gian đặt lại theo
    # chữ thì đồng hồ reset liên tục và không bao giờ đoán ra được gì.
    moc = eta.running()[SEARCH]["started"]
    eta.progress(SEARCH, "đọc kỹ · tin D — chữ hoàn toàn khác", 4, 100)
    check("đổi CHỮ thì đồng hồ vẫn chạy tiếp",
          eta.running()[SEARCH]["started"] == moc)
    eta.progress(SEARCH, "sang việc khác", 1, 7)
    check("đổi VIỆC (tổng khác) thì đồng hồ đặt lại",
          eta.running()[SEARCH]["started"] != moc)
    check("và lại im cho tới khi đủ nhịp", eta.running()[SEARCH]["eta"] == 0)

    print("\n[nhật ký phải CHẠY THEO tin mới nhất]")
    # Hợp đồng hai đầu: máy chủ gửi CŨ TRƯỚC, trình duyệt chèn từng dòng vào
    # ĐỈNH — nên nạp xong thì tin mới nhất nằm trên cùng, cùng chiều với dòng
    # về sau. Đảo một trong hai đầu là danh sách lộn tùng phèo mà không ai
    # nhận ra ngay, vì lúc mới mở app nhật ký nào cũng trông hợp lý.
    xep = Journal()
    for n in range(4):
        xep.emit(SEARCH, f"dòng {n}")
    trong_bo_nho = [e.text for e in xep.tail(SEARCH, 10)]
    check("tail() trả MỚI NHẤT trước", trong_bo_nho[0] == "dòng 3", str(trong_bo_nho))
    gui_di = trong_bo_nho[::-1]            # đúng phép server.py dùng cho 'hello'
    check("gói gửi cho trình duyệt thì CŨ trước", gui_di[0] == "dòng 0")
    tren_man = []
    for e in gui_di:                       # live.js: chèn từng dòng vào đỉnh
        tren_man.insert(0, e)
    check("chèn vào đỉnh xong thì mới nhất lên trên cùng",
          tren_man[0] == "dòng 3", str(tren_man))

    # LỖI THẬT: chèn ở TRÊN chỗ đang nhìn thì trình duyệt giữ nguyên scrollTop,
    # nên mỗi dòng mới đẩy khung nhìn xuống thêm một nấc — càng chạy càng trôi
    # xa tin mới nhất. Đo trên máy thật: nhật ký cao 877px trong khung 60px,
    # vòng nộp đang chạy mà màn hình đứng ở mấy dòng cũ.
    js = (Path(__file__).resolve().parent.parent
          / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
    than = js.split("function addLine")[1].split("\n  const journal")[0]
    check("chèn dòng xong có xử lý cuộn", "scrollTop" in than, "")
    check("đang bám đỉnh -> kéo về tin mới nhất", "sc.scrollTop = 0" in than)
    check("đang đọc dòng cũ -> giữ nguyên chỗ, không giật",
          "sc.scrollTop += row.offsetHeight" in than)
    # Thanh cuộn KHÔNG nằm trên .journal mà trên .jfeed bọc ngoài. Đặt
    # scrollTop lên nhầm phần tử thì không có gì xảy ra và cũng không có lỗi.
    check("tìm đúng khung cuộn chứ không đoán", "function scroller" in js)

    print("\n[quét: MỌI nguồn phải để lại dấu vết]")
    # Lượt quét 19:22 chạy 21 board và để lại đúng 3 dòng nhật ký, vì luật cũ
    # là "chỉ ghi khi có tin mới". Người dùng không có cách nào biết 18 board
    # kia đã chạy xong hay đã chết. Im lặng không phải là gọn — im lặng là mù.
    from jobbot.core.journal import log as chung
    from jobbot import scan_runner as _sr
    _c = db.connect()
    _truoc = len(chung.tail(SEARCH, 999))
    _sr._run_source(_c, "greenhouse:rong", lambda: [], log=lambda _m: None)
    _sau = chung.tail(SEARCH, 999)
    check("nguồn KHÔNG có tin mới vẫn ghi một dòng", len(_sau) == _truoc + 1)
    check("và dòng đó nói rõ là 0 mới", "0 mới" in _sau[0].text, _sau[0].text)
    check("mức 'info' chứ không phải 'ok' — không có gì để mừng",
          _sau[0].level == "info")
    _c.close()

    print("\n[nhật ký hỏng KHÔNG được giết việc đang chạy]")
    broken = Journal()
    broken.open()
    broken._conn = "không phải kết nối"        # ép mọi thao tác đĩa nổ
    try:
        broken.emit(SEARCH, "vẫn phải chạy")
        check("ghi đĩa hỏng vẫn emit được", True)
    except Exception as exc:                   # noqa: BLE001
        check("ghi đĩa hỏng vẫn emit được", False, f"{type(exc).__name__}: {exc}")
    check("và dòng đó vẫn có trong bộ nhớ", len(broken.tail(SEARCH, 9)) == 1)

    os.environ.pop("JOBBOT_DATA_DIR", None)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
