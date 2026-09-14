"""Test tầng Chrome — WebSocket, CDP, và luật an toàn.  python3 tests/test_browser.py

Phần cần Chrome thật sẽ tự bỏ qua nếu Chrome chưa chạy.
"""

import re, struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.browser import chrome, ws
from jobbot.ingest.web import base as webbase

ok = fail = skip = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}{' — ' + extra if extra else ''}")

print("\n[khung WebSocket]")
class FakeSock:
    def __init__(self): self.sent = b""
    def sendall(self, b): self.sent += b
    def settimeout(self, t): pass
    def close(self): pass

conn = ws.WebSocket.__new__(ws.WebSocket)
conn.sock, conn._buf = FakeSock(), b""
conn.send("hi")
frame = conn.sock.sent
check("bit FIN + opcode text", frame[0] == 0x81)
check("client BẮT BUỘC mask", frame[1] & 0x80 == 0x80)
check("độ dài đúng", (frame[1] & 0x7F) == 2)
mask, body = frame[2:6], frame[6:]
check("giải mask ra đúng chữ",
      bytes(b ^ mask[i % 4] for i, b in enumerate(body)) == b"hi")

print("\n[bắt tay: khung về CHUNG gói với 101 không được rơi]")
# Mọi bài test ở trên đều đi vòng qua __init__ (dùng __new__), nên không cái
# nào thấy được rằng __init__ gán self._buf = b"" NGAY SAU _handshake — tức là
# ném đi đúng những byte khung mà _handshake vừa giữ lại. Chrome gửi 101 và
# sự kiện đầu tiên chung một gói TCP là mất frame.
class HandshakeSock:
    """Trả 101 và một khung 'hello' trong CÙNG một lần đọc."""
    RESPONSE = (b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\nConnection: Upgrade\r\n\r\n"
                + bytes([0x81, 5]) + b"hello")

    def __init__(self): self.sent, self.given = b"", False
    def sendall(self, b): self.sent += b
    def settimeout(self, t): pass
    def close(self): pass
    def recv(self, n):
        if self.given:
            return b""
        self.given = True
        return self.RESPONSE

made = HandshakeSock()
real_create = ws.socket.create_connection
ws.socket.create_connection = lambda *a, **k: made
try:
    live = ws.WebSocket("ws://127.0.0.1:9222/devtools/browser/abc")
    check("bắt tay xong vẫn giữ được khung đi kèm", live.recv() == "hello")
finally:
    ws.socket.create_connection = real_create

conn2 = ws.WebSocket.__new__(ws.WebSocket)
conn2.sock, conn2._buf = FakeSock(), bytes([0x81, 5]) + b"hello"
check("đọc được frame server (không mask)", conn2.recv() == "hello")

conn3 = ws.WebSocket.__new__(ws.WebSocket)
conn3.sock = FakeSock()
conn3._buf = bytes([0x01, 3]) + b"abc" + bytes([0x80, 3]) + b"def"
check("nối lại frame bị chia mảnh", conn3.recv() == "abcdef")

conn4 = ws.WebSocket.__new__(ws.WebSocket)
conn4.sock, conn4._buf = FakeSock(), bytes([0x81, 126]) + struct.pack(">H", 300) + b"x" * 300
check("đọc được payload dài (16-bit)", len(conn4.recv()) == 300)

print("\n[an toàn — cookie]")
js = webbase.REJECT_JS.lower()
check("KHÔNG có 'accept' trong danh sách nút bấm", "accept all" not in js)
check("có 'reject'", "reject" in js)
check("có 'only necessary'", "only necessary" in js)
for word in ("agree", "allow all", "consent to", "i accept"):
    check(f"không bao giờ bấm '{word}'", word not in js)

print("\n[an toàn — không cãi tường chặn]")
for text in ("Just a moment...", "Attention Required! | Cloudflare",
             "Access Denied", "Verify you are human", "403 Forbidden"):
    check(f"nhận ra chặn: {text[:28]}", bool(webbase.BLOCKED.search(text)))
check("trang bình thường KHÔNG bị nhận nhầm",
      not webbase.BLOCKED.search("Quantitative Analyst jobs in London | LinkedIn"))

print("\n[vòng đọc kỹ KHÔNG được đọc lại thứ đã đọc]")
# GỐC RỄ của cả chuỗi lỗi bước 1. Trên máy thật 194/196 tin LinkedIn đã có mô
# tả, mà vòng đọc kỹ vẫn mở lại tất cả — 97% công là làm lại. Chính chỗ thừa
# đó đẻ ra: 17 phút mỗi vòng -> ~5.000 lượt gọi/ngày -> bị bóp 40-82% -> phải
# nghỉ lâu hơn -> phải cắt 12 chức danh còn 5. Sửa một chỗ, cả chuỗi tan.
from jobbot.ingest.web import linkedin as li
import jobbot.scan_runner as _sr_doc

class FakeTab:
    """Trả danh sách 3 tin, và đếm xem vòng đọc kỹ mở bao nhiêu trang chi tiết."""
    def __init__(self): self.detail_opens = []
    def eval(self, js, timeout=None):
        if "show-more-less-html__markup" in js:      # DETAIL_JS
            return '[{"description":"' + "x" * 400 + '","criteria":""}]'
        return ('[{"title":"Quant Analyst","company":"A","location":"London",'
                '"url":"https://x/jobs/view/a-1000001","posted":""},'
                '{"title":"Data Scientist","company":"B","location":"London",'
                '"url":"https://x/jobs/view/b-1000002","posted":""},'
                '{"title":"Risk Analyst","company":"C","location":"London",'
                '"url":"https://x/jobs/view/c-1000003","posted":""}]')

real_open, real_pause = li.open_page, li._pause
opened = []
li.open_page = lambda tab, url, timeout=30: opened.append(url)
li._pause = lambda *a: None
try:
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True)
    all_read = sum(1 for u in opened if "jobPosting" in u)
    check("chưa biết gì -> đọc kỹ cả 3 tin", all_read == 3, f"đọc {all_read}")

    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True,
             skip=frozenset({"1000001", "1000002"}))
    again = sum(1 for u in opened if "jobPosting" in u)
    check("đã đọc 2 tin -> chỉ đọc kỹ 1 tin còn lại", again == 1, f"đọc {again}")

    opened.clear()
    out = li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True,
                   skip=frozenset({"1000001", "1000002", "1000003"}))
    check("đã đọc hết -> KHÔNG mở trang chi tiết nào",
          sum(1 for u in opened if "jobPosting" in u) == 0)
    check("nhưng vẫn TRẢ VỀ đủ tin tìm được", len(out[0]) == 3)
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[cập nhật thì chỉ hỏi TIN MỚI — không quét lại từ đầu]")
# ĐÃ THỬ THẬT trên cổng guest ngày 12/09:
#   f_TPR=r86400  CHẠY  — 10/10 tin trả về đều từ 24 giờ qua
#   sortBy=DD     bị phớt lờ — kết quả y hệt không truyền gì
#   f_WT=2        bị phớt lờ — (đo hôm trước, cùng kiểu)
# Phải thử từng cái: hai tham số trông hợp lý kia không làm gì cả, mà cổng
# vẫn trả 200 nên nhìn như đang chạy.
li.open_page = lambda tab, url, timeout=30: opened.append(url)
li._pause = lambda *a: None
try:
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False)
    check("quét đầy thì KHÔNG kèm cửa sổ thời gian",
          not any("f_TPR" in u for u in opened))
    # CỬA SỔ CHỈ ÁP CHO CẶP ĐÃ PHỦ. Cặp chưa hỏi bao giờ mà cũng chỉ hỏi 24
    # giờ thì tin cũ khớp nó không bao giờ được tìm thấy.
    _phu = frozenset({"Quant Analyst|United Kingdom"})
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False,
             recent=li.NGAY, covered=_phu)
    check("cặp ĐÃ phủ -> chỉ hỏi 24 giờ qua",
          all("f_TPR=r86400" in u for u in opened), str(opened[:1]))
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False,
             recent=li.TUAN, covered=_phu)
    check("nghỉ mấy hôm thì nới ra 7 ngày",
          all("f_TPR=r604800" in u for u in opened), str(opened[:1]))
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False, recent=li.NGAY)
    check("cặp CHƯA phủ -> hỏi đầy, bất kể cửa sổ",
          not any("f_TPR" in u for u in opened), str(opened[:1]))

    # HAI KIỂU TRONG CÙNG MỘT LƯỢT — đây là cả điểm của việc nhớ theo cặp.
    opened.clear()
    _xong = set()
    li.fetch(FakeTab(), ["Quant Analyst", "Data Scientist"], pages=1, deep=False,
             recent=li.NGAY, covered=_phu, done_out=_xong)
    _day = [u for u in opened if "f_TPR" not in u]
    _hep = [u for u in opened if "f_TPR" in u]
    check("cặp cũ hỏi cửa sổ, cặp mới hỏi đầy — trong cùng một lượt",
          len(_day) == 1 and len(_hep) == 1, f"{len(_day)} đầy / {len(_hep)} hẹp")
    check("và chỉ cặp vừa hỏi ĐẦY mới được ghi là đã phủ",
          _xong == {"Data Scientist|United Kingdom"}, str(_xong))
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[TIẾP TỤC = đọc nốt chỗ dở, KHÔNG tìm lại]")
# "Tiếp tục" mà vẫn chạy vòng tìm thì nó chỉ là chữ khác của "quét lại từ
# đầu": tìm lại 2.296 tin y hệt mất 30 phút, để rồi đọc nốt 11 tin.
from jobbot.ingest.base import Posting as _P
li.open_page = lambda tab, url, timeout=30: opened.append(url)
li._pause = lambda *a: None
try:
    opened.clear()
    do_dang = [_P(source_id="1000001", title="Quant Analyst", company="A",
                  location="London", url="https://x/jobs/view/a-1000001")]
    suc = li.read_deep(FakeTab(), do_dang)
    check("read_deep chạy được MỘT MÌNH, không cần vòng tìm", suc.attempted == 1)
    check("và KHÔNG gọi một trang tìm kiếm nào",
          not any("seeMoreJobPostings" in u for u in opened), str(opened[:2]))
    check("chỉ mở đúng trang chi tiết của tin dở",
          sum(1 for u in opened if "jobPosting" in u) == 1)
    check("mô tả được vá thẳng vào tin đó", len(do_dang[0].description) > 200)
    # TÊN NGUỒN TRONG NHẬT KÝ PHẢI ĐÚNG NGUỒN. Trang thì vẫn là trang
    # LinkedIn, nhưng tin tới từ đâu là chuyện khác: đọc 106 tin thư báo mà
    # nhật ký ghi "linkedin: 106 tin" thì người dùng tưởng vòng quét LinkedIn
    # đang chạy trong khi họ vừa tắt nó đi.
    from jobbot.core import journal as _jn
    _dong = []
    _that_emit = _jn.log.emit
    _jn.log.emit = lambda stream, text, **k: _dong.append(text)
    try:
        li.read_deep(FakeTab(), [_P(source_id="1000002", title="Q", company="A",
                                    location="London", url="https://x/b-1000002")],
                     ten="alert")
    finally:
        _jn.log.emit = _that_emit
    check("đọc tin thư báo -> nhật ký ghi 'alert', KHÔNG ghi 'linkedin'",
          any(d.startswith("alert:") for d in _dong)
          and not any(d.startswith("linkedin:") for d in _dong), str(_dong[:3]))
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[công tắc nguồn: TẮT thì phải thật sự không chạy]")
# Một nguồn tắt mà vòng quét vẫn chạy nó thì công tắc chỉ là cái nút trang
# trí. Kiểm bằng cách đếm số nguồn API thật sự được gọi.
import tempfile as _tf, os as _os
from pathlib import Path as _P
with _tf.TemporaryDirectory() as _tmp:
    _cu_dir = _os.environ.get("JOBBOT_DATA_DIR")
    _cu_root_b = _os.environ.get("JOBBOT_ROOT")
    _os.environ["JOBBOT_DATA_DIR"] = _tmp
    # JOBBOT_ROOT: không thì bài test đọc config.toml THẬT, thấy hộp thư của
    # Vin đã nối, và bật luôn nguồn thư báo. Test phải chạy trên thế giới của
    # chính nó, không phụ thuộc máy ai đang nối cái gì.
    (_P(_tmp) / "config").mkdir(exist_ok=True)
    _os.environ["JOBBOT_ROOT"] = _tmp
    try:
        from jobbot.core import db as _db, prefs as _pf
        from jobbot.core.paths import db_path as _dbp
        from jobbot.profile import store as _ps
        import jobbot.scan_runner as _sr
        # CHỐT: test KHÔNG được chạm DB thật. Đã xảy ra một lần.
        assert str(_dbp()).startswith(_tmp), f"test đang trỏ vào DB THẬT: {_dbp()}"
        _c = _db.connect()
        _ps.save(_c, {"job_titles": "Data Scientist", "markets": ["uk_onsite"],
                      "work_auth": "citizen", "location": "London"}, "t")
        _goi = []
        _that_run = _sr._run_source
        _that_chrome = _sr._chrome_pass
        _sr._run_source = lambda conn, name, fn, *a, log=None: (_goi.append(name), (0, 0))[1]
        _sr._chrome_pass = lambda *a, **k: (_goi.append("CHROME"), (0, 0))[1]
        try:
            _pf.set_flag(_c, _pf.SRC_BOARD, True)
            _pf.set_flag(_c, _pf.SRC_LINKEDIN, True)
            _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            check("bật cả hai -> chạy cả board lẫn Chrome",
                  len(_goi) > 1 and "CHROME" in _goi, str(_goi[-3:]))

            _c = _db.connect(); _pf.set_flag(_c, _pf.SRC_BOARD, False); _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            # Thư báo có công tắc RIÊNG, không nằm dưới công tắc board — nên
            # tắt board không được kéo theo nó.
            check("tắt board -> KHÔNG gọi board nào",
                  not [g for g in _goi if ":" in g], str(_goi[:4]))

            # TỪNG ATS một. Công tắc to và công tắc nhỏ là hai tầng; tắt tầng
            # nào cũng phải dừng đúng nhóm đó, không nhiều không ít.
            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_BOARD, True)
            _pf.set_flag(_c, _pf.SRC_ATS["greenhouse"], False)
            _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            check("tắt greenhouse -> không gọi board greenhouse nào",
                  not [g for g in _goi if g.startswith("greenhouse")],
                  str([g for g in _goi if g.startswith("greenhouse")][:3]))
            check("nhưng lever/ashby vẫn chạy",
                  any(g.startswith(("lever", "ashby")) for g in _goi),
                  str(_goi[:4]))
            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_ATS["greenhouse"], True)
            _c.close()

            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_BOARD, True)
            _pf.set_flag(_c, _pf.SRC_LINKEDIN, False)
            _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            # TẮT LINKEDIN KHÔNG PHẢI TẮT CHROME. Chrome còn là đường lấy mô
            # tả cho tin của nguồn KHÁC (thư báo), và thư báo có công tắc
            # riêng. Gộp lại thì tắt một nguồn làm chết một nguồn khác — đã
            # xảy ra thật, 107 tin thư báo nằm im không ai chấm.
            check("tắt LinkedIn -> vòng Chrome VẪN chạy (còn đọc tin nguồn khác)",
                  "CHROME" in _goi, str(_goi[:4]))
            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_ALERT, False)
            _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            # Nhưng tắt HẾT nguồn cần trang web thì đừng mở cửa sổ nào. Ở đây
            # _chrome_pass bị thay bằng hàm giả nên vẫn được gọi; phần "không
            # có việc thì không mở Chrome" do test TIEP ở dưới chứng minh.
            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_ALERT, True)
            _pf.set_flag(_c, _pf.SRC_LINKEDIN, True)
            _c.close()
        finally:
            _sr._run_source, _sr._chrome_pass = _that_run, _that_chrome
    finally:
        for _k, _v in (("JOBBOT_DATA_DIR", _cu_dir), ("JOBBOT_ROOT", _cu_root_b)):
            if _v is None:
                _os.environ.pop(_k, None)
            else:
                _os.environ[_k] = _v

print("\n[nhớ theo CẶP: không chạy đi chạy lại một thứ]")
# Đơn vị quét là CẶP (chức danh × nơi), không phải cả lưới. Vân tay cho cả
# lưới thì thô quá: bỏ bớt một chức danh cũng bắt quét lại từ đầu, trong khi
# bỏ bớt thì làm gì có gì mới để tìm.
_src = (Path(__file__).resolve().parent.parent
        / "src/jobbot/scan_runner.py").read_text(encoding="utf-8")
_than = _src.split("def _chrome_pass")[1]
_truoc = _than.split("prefs.put(conn, prefs.LI_DONE")[0].split("\n")[-8:]
_truoc = "\n".join(_truoc)
check("chỉ ghi nhớ khi lượt chạy LÀNH", "health.ok" in _truoc, _truoc[-70:])
check("cộng DỒN chứ không ghi đè", "cu_phu | vua_phu" in _than)

print("\n[nhịp gọi: núm hiệu năng THẬT, và nó là núm đánh đổi]")
# Vì sao không làm "chạy N tab song song": N tab với nhịp P giống hệt 1 tab
# với nhịp P/N — cùng số lượt gọi mỗi giây, cùng rủi ro bị bóp. Song song chỉ
# là cách viết phức tạp hơn của một con số nhỏ hơn, cộng thêm N cửa sổ Chrome
# ăn RAM và N chỗ có thể chết nửa chừng.
check("ba nhịp, không hơn", set(li.NHIP) == {"nhe", "thuong", "nhanh"})
check("mặc định là nhịp cũ, không đổi hành vi sẵn có",
      li.NHIP["thuong"] == li.PAUSE)
check("nhanh thì gọi dày hơn, nhẹ thì thưa hơn",
      li.NHIP["nhanh"][1] < li.NHIP["thuong"][1] < li.NHIP["nhe"][1])
# Nhịp lạ (gõ bừa vào URL) KHÔNG được thành nhịp 0 giây.
_do = []
_that = li.time.sleep
li.time.sleep = lambda s: _do.append(s)
li.open_page = lambda tab, url, timeout=30: None
try:
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False, pace="bịa")
    check("nhịp lạ -> rơi về mặc định, không phải 0 giây",
          _do and min(_do) >= li.PAUSE[0], str(_do[:3]))
    _do.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False, pace="nhanh")
    check("chọn 'nhanh' thì nhịp thật sự ngắn lại",
          _do and max(_do) <= li.NHIP["nhanh"][1], str(_do[:3]))
finally:
    li.time.sleep = _that
    li.open_page = real_open

print("\n[thư báo phải đi HẾT dây chuyền, không dừng ở bước lấy về]")
# Thư báo và vòng quét Chrome trỏ tới đúng MỘT trang /jobs/view/<id>, chỉ
# khác đường mang id về. Vòng đọc kỹ chỉ nhìn source='linkedin' thì tin thư
# báo đi được nửa dây chuyền: đo 12/09 là 195 tin về, LỌC chạy đúng (110 giữ
# / 85 bỏ), nhưng 0 tin có mô tả và 0 tin được chấm — mà 181/195 là việc vòng
# quét Chrome KHÔNG tìm ra.
import tempfile as _tf2, os as _os2
from pathlib import Path as _P2
check("hai nguồn cùng một vòng đọc kỹ",
      set(_sr_doc.DOC_KY) == {"linkedin", "alert"})
with _tf2.TemporaryDirectory() as _t2:
    _cu2 = _os2.environ.get("JOBBOT_DATA_DIR")
    _os2.environ["JOBBOT_DATA_DIR"] = _t2
    try:
        from jobbot.core import db as _db2, postings as _po2
        from jobbot.ingest.base import Posting as _P3
        _c2 = _db2.connect()
        assert str(_db2.paths.db_path()).startswith(_t2) if hasattr(_db2, "paths") else True
        for _ng in ("linkedin", "alert"):
            _po2.save_batch(_c2, _ng, [_P3(source_id="777", title="Quant",
                                           company="X", location="London",
                                           url="https://x/777", description="")])
        _c2.execute("UPDATE posting SET kept = 1")
        _c2.commit()
        _do = _sr_doc._tin_do_dang(_c2)
        check("tin thư báo NẰM TRONG hàng đợi đọc kỹ", "alert" in _do, str(list(_do)))
        check("và tách theo NGUỒN, không trộn một rổ",
              set(_do) == {"linkedin", "alert"}, str(list(_do)))
        # save_batch ghi theo cặp (nguồn, id): gộp lại rồi lưu dưới một tên là
        # đẻ ra dòng mới thay vì vá mô tả vào đúng dòng cũ.
        check("mỗi nguồn đúng một tin", all(len(v) == 1 for v in _do.values()))
        # Đọc xong ở nguồn này thì nguồn kia khỏi mở lại — cùng một trang.
        _c2.execute("UPDATE posting SET description = ? WHERE raw_id IN"
                    " (SELECT id FROM raw_posting WHERE source='alert')",
                    ("x" * 300,))
        _c2.commit()
        check("đọc ở thư báo rồi thì LinkedIn khỏi mở lại",
              "777" in _po2.already_read(_c2, _sr_doc.DOC_KY))
        _c2.close()
    finally:
        if _cu2 is None:
            _os2.environ.pop("JOBBOT_DATA_DIR", None)
        else:
            _os2.environ["JOBBOT_DATA_DIR"] = _cu2

print("\n[hai nguồn, hai công tắc: tắt LinkedIn thì thư báo vẫn chạy trọn]")
# "mặc dù allert cũng lấy từ linkdln nhưng 2 cách khác nhau phải làm 2 nguồn
# khác nhau, đừng gộp chung, khi tôi tắt linkdn thì nó tự search từ nguồn
# allert email thôi"
#
# Trước đây cả vùng Chrome nằm sau công tắc linkedin, mà vòng ĐỌC KỸ nằm
# trong vùng đó — nên tắt linkedin là 107 tin thư báo đứng im: có chức danh,
# có công ty, không có mô tả, không có điểm. Test này chạy THẬT _chrome_pass
# với linkedin TẮT và kiểm mô tả có vào đúng dòng thư báo hay không.
import tempfile as _tf4, os as _os4
with _tf4.TemporaryDirectory() as _t4:
    _cu4 = _os4.environ.get("JOBBOT_DATA_DIR")
    _cu4r = _os4.environ.get("JOBBOT_ROOT")
    _os4.environ["JOBBOT_DATA_DIR"] = _t4
    _os4.environ["JOBBOT_ROOT"] = _t4
    try:
        from jobbot.core import db as _db4, prefs as _pf4, postings as _po4
        from jobbot.ingest.base import Posting as _P4
        from jobbot.profile import store as _ps4
        from jobbot.browser import chrome as _ch4, cdp as _cdp4
        from jobbot.core.paths import db_path as _dbp4
        # CHỐT: test KHÔNG được chạm DB thật. Đã xảy ra một lần.
        assert str(_dbp4()).startswith(_t4), f"test đang trỏ vào DB THẬT: {_dbp4()}"

        _c4 = _db4.connect()
        _ps4.save(_c4, {"job_titles": "Quant Analyst", "markets": ["uk_onsite"],
                        "work_auth": "citizen", "location": "London"}, "t")
        # Một tin của THƯ BÁO, chưa có mô tả — đúng thứ thư báo mang về.
        _po4.save_batch(_c4, "alert", [_P4(
            source_id="1000001", title="Quant Analyst", company="A",
            location="London", url="https://x/jobs/view/a-1000001")])
        _c4.execute("UPDATE posting SET kept = 1")
        _c4.commit()
        _pf4.set_flag(_c4, _pf4.SRC_LINKEDIN, False)     # <- TẮT LinkedIn
        _pf4.set_flag(_c4, _pf4.SRC_ALERT, True)
        _c4.commit()

        _kieu = _sr_doc.scan_mode(_c4)
        check("LinkedIn tắt mà còn tin dở -> nút vẫn mời Tiếp tục",
              _kieu["mode"] == _sr_doc.TIEP, f"{_kieu['mode']} · {_kieu['note']}")
        check("và KHÔNG còn đòi bật LinkedIn",
              "bật LinkedIn" not in _kieu["note"], _kieu["note"])
        check("thư báo là nguồn cần đọc kỹ, độc lập với linkedin",
              _sr_doc.nguon_doc(_c4) == ("alert",), str(_sr_doc.nguon_doc(_c4)))

        _mo4, _dong4 = [], []
        _th_l, _th_s, _th_t = _ch4.launch, _ch4.shutdown, _cdp4.open_tab
        _th_w = _sr_doc.__dict__.get("in_human_window")
        class _Tab4(FakeTab):
            def close(self): _dong4.append(1)
        _ch4.launch = lambda **k: _mo4.append("launch")
        _ch4.shutdown = lambda: True
        _cdp4.open_tab = lambda *a, **k: _Tab4()
        li.open_page = lambda tab, url, timeout=30: opened.append(url)
        li._pause = lambda *a: None
        try:
            opened.clear()
            _s4, _n4 = _sr_doc._chrome_pass(_c4, _ps4.load(_c4),
                                            lambda _m: None, True, manual=True)
            check("TẮT LinkedIn -> vòng đọc kỹ VẪN chạy", _mo4 == ["launch"], str(_mo4))
            check("và KHÔNG gõ một lượt tìm từ khoá nào",
                  not any("seeMoreJobPostings" in u for u in opened),
                  str([u for u in opened if "seeMore" in u][:2]))
            check("mở đúng trang chi tiết của tin thư báo",
                  sum(1 for u in opened if "jobPosting" in u) == 1, str(opened))
            _mo_ta = _c4.execute(
                "SELECT length(COALESCE(p.description,'')) FROM posting p"
                " JOIN raw_posting r ON p.raw_id = r.id"
                " WHERE r.source = 'alert'").fetchone()[0]
            check("mô tả vào ĐÚNG dòng thư báo, không đẻ dòng linkedin mới",
                  _mo_ta > 200, f"dài {_mo_ta}")
            check("không đẻ dòng nguồn linkedin nào",
                  _c4.execute("SELECT COUNT(*) FROM raw_posting WHERE source"
                              " = 'linkedin'").fetchone()[0] == 0)
            # vua_phu: lỗi này nằm im vì `except Exception` nuốt NameError, rồi
            # ghi lượt quét là HỎNG trong khi mô tả đã lưu xong.
            _hong = _c4.execute("SELECT ok, error FROM source_run WHERE source"
                                " = 'alert' ORDER BY id DESC LIMIT 1").fetchone()
            check("và lượt chạy được ghi là LÀNH, không NameError",
                  _hong and _hong[0] == 1, str(tuple(_hong) if _hong else None))
            check("tab được đóng lại", _dong4 == [1], str(_dong4))

            # Tắt CẢ HAI -> không có việc nào cần trang web -> đừng mở Chrome.
            _c4.execute("UPDATE posting SET description = ''")
            _c4.commit()
            _pf4.set_flag(_c4, _pf4.SRC_ALERT, False)
            _c4.commit()
            _mo4.clear(); opened.clear()
            _sr_doc._chrome_pass(_c4, _ps4.load(_c4), lambda _m: None, True,
                                 manual=True)
            check("tắt hết nguồn -> KHÔNG mở cửa sổ Chrome nào", _mo4 == [],
                  str(_mo4))
        finally:
            _ch4.launch, _ch4.shutdown, _cdp4.open_tab = _th_l, _th_s, _th_t
            li.open_page, li._pause = real_open, real_pause
        _c4.close()
    finally:
        for _k4, _v4 in (("JOBBOT_DATA_DIR", _cu4), ("JOBBOT_ROOT", _cu4r)):
            if _v4 is None:
                _os4.environ.pop(_k4, None)
            else:
                _os4.environ[_k4] = _v4


print("\n[đọc kỹ là chỗ TỐN NHẤT — chỉ đọc tin sẽ được giữ]")
# Đo trên kho thật: 2.389 tin LinkedIn, chỉ 257 tin lọt lưới sàng. 89% số tin
# được mở trang, chờ 2,5-5 giây, rồi bị loại ngay sau đó — hơn hai tiếng mỗi
# lượt quét đổ đi.
#
# Lọc trước được vì judge() chỉ đụng tiêu đề/công ty/địa điểm, ba thứ trang
# danh sách đã đưa sẵn; mô tả mới là thứ phải mở trang mới có.
li.open_page = lambda tab, url, timeout=30: opened.append(url)
li._pause = lambda *a: None
try:
    opened.clear()
    tin, _ = li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True,
                      worth=lambda i: i.title == "Data Scientist")
    doc = [u for u in opened if "jobPosting" in u]
    check("chỉ đọc kỹ tin lọt lưới", len(doc) == 1, f"đọc {len(doc)}/3")
    check("nhưng VẪN trả về đủ tin để lưu — chồng 'Đã loại' còn nguyên",
          len(tin) == 3, f"{len(tin)} tin")

    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True,
             worth=lambda i: False)
    check("lưới loại hết -> không mở trang chi tiết nào",
          not [u for u in opened if "jobPosting" in u])

    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True)
    check("không truyền lưới -> đọc kỹ tất, y như cũ",
          len([u for u in opened if "jobPosting" in u]) == 3)
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[đứt giữa chừng: GIỮ LẠI thứ đã tìm được]")
# Xảy ra thật lúc 17:18 ngày 11/09: 48/76 lượt tìm đã xong, một
# ConnectionResetError ở vòng tìm bay thẳng ra ngoài fetch() — `items` không
# bao giờ trả về, save_batch() không bao giờ chạy, source_run ghi fetched=0.
# Cả kho tin đổ đi sạch.
#
# Máy ngủ dậy là ĐÚNG cái lỗi này (socket CDP chết), mà app chạy 24/7 nên đó
# là chuyện thường ngày chứ không phải tai nạn hiếm.
_dem = {"n": 0}
def _dut_o_lan_3(tab, url, timeout=30):
    _dem["n"] += 1
    if _dem["n"] >= 3:
        raise ConnectionResetError(54, "Connection reset by peer")
li.open_page = _dut_o_lan_3
li._pause = lambda *a: None
try:
    _tin, _suc = li.fetch(FakeTab(), ["Quant Analyst", "Data Scientist"],
                          location=["United Kingdom", ""], pages=1, deep=True)
    check("đứt rồi vẫn TRẢ VỀ tin đã tìm được", len(_tin) == 3, f"{len(_tin)} tin")
    check("và đánh dấu lần quét này KHÔNG lành", _suc.ok is False)
    check("nói rõ là ĐỨT, không phải BỊ CHẶN",
          "CUT OFF" in _suc.summary and "BLOCKED" not in _suc.summary, _suc.summary)
    check("ghi cả tên lỗi để lần sau còn dò",
          "ConnectionResetError" in _suc.summary, _suc.summary)
    check("đứt thì KHÔNG đọc kỹ tiếp — mở tiếp chỉ nhận thêm lỗi",
          _dem["n"] <= 4, f"gọi open_page {_dem['n']} lần")
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[vòng quét phải NÓI nó đang làm gì]")
# Đo trên lượt quét 19:22 ngày 11/09: vòng TÌM chạy 31 phút để lại đúng một
# dòng, vòng ĐỌC KỸ chạy 27 phút để lại đúng một dòng. Thanh tiến độ nhích mà
# nhật ký trống thì người dùng không biết máy đang gõ chức danh nào, mở tin
# nào, hay đã treo từ lâu.
from jobbot.core.journal import SEARCH as _S, log as _jl
_nhip_that = li.NHIP_BAO
li.open_page = lambda tab, url, timeout=30: None
li._pause = lambda *a: None
li.NHIP_BAO = 2                      # 3 tin thử là đủ chạm nhịp báo
try:
    _truoc = len(_jl.tail(_S, 999))
    li.fetch(FakeTab(), ["Quant Analyst", "Data Scientist"],
             location=["United Kingdom", ""], pages=1, deep=True)
    _moi = [e.text for e in _jl.tail(_S, 999)[:len(_jl.tail(_S, 999)) - _truoc]]

    _tim = [t for t in _moi if t.startswith("search · ")]
    check("mỗi lượt tìm để lại một dòng (2 chức danh × 2 nơi)",
          len(_tim) == 4, f"{len(_tim)} dòng: {_tim[:2]}")
    check("dòng nói rõ đang gõ chức danh nào",
          any("Quant Analyst" in t for t in _tim))
    check("và đang tìm ở đâu", any("United Kingdom" in t for t in _tim))
    check("nơi để trống thì gọi tên là 'toàn cầu', không bỏ lửng dấu chấm",
          any("worldwide" in t for t in _tim) and not any(t.endswith(" · ") for t in _tim))
    _doc = [t for t in _moi if t.startswith("deep-read ")]
    check("vòng đọc kỹ có nhịp báo giữa chừng", _doc, f"{_moi[:3]}")
    check("nhịp báo nói rõ đang đọc tin nào",
          any("reading:" in t for t in _doc), f"{_doc[:2]}")
finally:
    li.NHIP_BAO = _nhip_that
    li.open_page, li._pause = real_open, real_pause

print("\n[địa điểm đọc từ hồ sơ, không phải chuỗi cứng]")
check("uk_onsite + uk_remote -> United Kingdom (rộng hơn London)",
      li.places_for(["uk_onsite", "uk_remote"]) == ["United Kingdom"])
check("bỏ trùng", len(li.places_for(["uk_onsite", "uk_remote", "uk_onsite"])) == 1)
check("global_remote -> để trống, LinkedIn tìm toàn cầu",
      li.places_for(["global_remote"]) == [""])
check("nhiều thị trường -> nhiều nơi",
      li.places_for(["uk_onsite", "us_remote"]) == ["United Kingdom", "United States"])
check("hồ sơ chưa chọn gì -> vẫn có mặc định", li.places_for([]) == ["United Kingdom"])
check("KHÔNG còn 'London' cứng trong chữ ký hàm",
      'location: str = "London"' not in Path("src/jobbot/ingest/web/linkedin.py").read_text())

print("\n[trần chức danh: có, nhưng phải NÓI RA]")
runner = Path("src/jobbot/scan_runner.py").read_text()
# Bỏ dòng chú thích trước khi soi — nếu không thì chính lời giải thích về
# cái lỗi vừa sửa lại làm bài test đỏ.
code_only = "\n".join(l for l in runner.split("\n")
                       if not l.strip().startswith("#"))
check("bỏ hẳn titles[:5] khỏi CODE", "titles[:5]" not in code_only)
check("nhưng giữ lời giải thích vì sao bỏ", "titles[:5]" in runner)
li_src = Path("src/jobbot/ingest/web/linkedin.py").read_text()
check("trần đặt tên rõ ràng", "MAX_QUERIES" in li_src)
check("và chạm trần thì ghi nhật ký, không cắt lặng lẽ",
      "searching only" in li_src and "jlog.warn" in li_src)

print("\n[tắt Chrome: phải THẬT SỰ tắt, và chỉ tắt bản của app]")
# LỖI THẬT: bản cũ gọi GET /json/close — endpoint đó cần kèm target id nên
# trả 404, lỗi bị nuốt trong except, hàm trả None và Chrome vẫn nguyên đó.
# Hàm "tắt" mà không tắt gì, chạy êm ru suốt.
from jobbot.browser import chrome as ch
src_ch = Path("src/jobbot/browser/chrome.py").read_text()

def code_of(name, text=src_ch):
    """Thân hàm, BỎ chú thích và docstring — để không kiểm nhầm vào lời giải
    thích về chính cái lỗi đã sửa."""
    body = text.split(f"def {name}")[1]
    body = body.split("\ndef ")[0]
    body = re.sub(r'"""[\s\S]*?"""', "", body)
    return "\n".join(l for l in body.split("\n") if not l.strip().startswith("#"))

shut = code_of("shutdown")
check("KHÔNG gọi endpoint /json/close (cần target id, trả 404)",
      "/json/close" not in shut)
check("dùng lệnh CDP Browser.close", "Browser.close" in shut)
check("đi qua websocket của TRÌNH DUYỆT", "webSocketDebuggerUrl" in shut)
check("shutdown trả về bool để người gọi biết có tắt được không",
      "-> bool" in src_ch.split("def shutdown")[1].split("\n")[0])
check("và có chờ, không trả lời ngay khi chưa tắt xong", "alive(port)" in shut)
# Chrome cá nhân cũng là tiến trình "Google Chrome" — giết theo TÊN là quét
# luôn cả nó, mất việc người dùng đang làm dở. Giết tiến trình do CHÍNH MÌNH
# sinh ra (process.terminate() trong launch) thì không sao.
check("KHÔNG giết tiến trình theo tên",
      not any(w in src_ch for w in ("pkill", "killall", "pgrep")))
check("cổng debug riêng, không phải 9222 mặc định", ch.PORT != 9222)
check("profile riêng, không dùng profile người dùng",
      "chrome-profile" in str(ch.profile_dir()))
check("Chrome chưa chạy -> coi như đã tắt, không báo hỏng",
      ch.shutdown(port=1) is True or not ch.alive(1))

# Hàm tắt đúng vẫn vô dụng nếu KHÔNG AI GỌI. Trước đây không một chỗ nào gọi
# shutdown(), nên Chrome mở ra rồi nằm trên màn hình tới lần quét sau — một
# tiếng sau.
runner_src = Path("src/jobbot/scan_runner.py").read_text()
app_src = Path("src/jobbot/app.py").read_text()
check("quét xong thì đóng Chrome", "chrome.shutdown()" in runner_src)
check("và báo ra nếu đóng không được", "could not close Chrome" in runner_src)
# ĐÓNG PHẢI NẰM TRONG `finally`. Trước đây lệnh đóng nằm ở cuối hàm, ngoài mọi
# try: chỉ cần một lỗi ở giữa — DB khoá lúc đọc already_read, máy ngủ dậy
# socket chết — là cửa sổ Chrome nằm lại tới khi tắt app. App chạy 24/7 nên
# "tới khi tắt app" nghĩa là mãi mãi. Kiểm bằng cây cú pháp chứ không bằng
# tìm chuỗi: chữ "finally" ở đâu đó trong file không chứng minh được gì.
import ast as _ast
def _trong_finally(nguon: str, ham: str, goi: str) -> bool:
    for node in _ast.walk(_ast.parse(nguon)):
        if isinstance(node, _ast.FunctionDef) and node.name == ham:
            for con in _ast.walk(node):
                if isinstance(con, _ast.Try):
                    if goi in _ast.unparse(_ast.Module(body=con.finalbody, type_ignores=[])):
                        return True
    return False
check("lệnh đóng Chrome nằm trong finally — hỏng giữa chừng vẫn đóng",
      _trong_finally(runner_src, "_chrome_pass", "chrome.shutdown"))
# MỌI cổng, không riêng cổng quét. Cửa sổ NỘP (9335) cố ý được để mở trong
# lúc chạy để Vin bấm cú cuối, nên chỗ thoát app là chỗ DUY NHẤT đóng nó; chỉ
# gọi shutdown() thì nó nằm lại giữ khoá profile, và lần mở app sau Chrome
# không mở lại được profile đó.
check("thoát app đóng MỌI cửa sổ Chrome của app", "chrome.shutdown_all()" in app_src)
from jobbot.browser import chrome as _ch2
check("shutdown_all quét đủ ba cổng (quét · in PDF · nộp)",
      set(_ch2.PROFILE) == {_ch2.PORT, _ch2.PDF_PORT, _ch2.APPLY_PORT})
# Gọi shutdown_all() thật ở đây là ĐÓNG Chrome thật của máy đang chạy test —
# bài test không được có tác dụng phụ ra ngoài. Bịt alive() lại rồi mới gọi.
_alive_that = _ch2.alive
_ch2.alive = lambda port=_ch2.PORT: False
try:
    check("không cổng nào chạy thì trả 0, không báo hỏng", _ch2.shutdown_all() == 0)
finally:
    _ch2.alive = _alive_that

print("\n[LinkedIn — ranh giới an toàn]")
from jobbot.ingest.web import linkedin as li
src = Path("src/jobbot/ingest/web/linkedin.py").read_text()
# RANH GIỚI TỪ, không phải chuỗi con: "assigning" có chứa "signin", nên một
# docstring tiếng Anh bình thường cũng đủ làm bài canh này đỏ. Cổng kêu oan thì
# người sửa chỉ học được đúng một điều — tắt nó đi.
_dang_nhap = re.compile(
    r"(?<!\w)(password|signin|sign_in|credential)(?!\w)|login\s*\(", re.I)
_thay = _dang_nhap.search(src)
check("KHÔNG có mã đăng nhập", not _thay, _thay.group(0) if _thay else "")
check("KHÔNG đụng hồ sơ cá nhân", not any(
    w in src for w in ("linkedin.com/in/", "/voyager/", "profileView",
                       "invitation", "messaging")))
check("chỉ dùng endpoint dành cho khách", "jobs-guest" in src)
check("nhịp chậm hơn nguồn khác", li.PAUSE[0] >= 2.0)
check("bị chặn thì dừng, không thử lại",
      "except Blocked" in src and "break" in src)

rows = [{"title": "Quant Analyst", "company": "Citi", "location": "London",
         "url": "/jobs/view/quant-analyst-at-citi-4443885925", "posted": "2026-09-05"}]
p1 = li._from_row(rows[0])
check("tách được id tin", p1.source_id == "4443885925")
check("dựng URL đầy đủ", p1.url.startswith("https://www.linkedin.com/jobs/view/"))
check("bỏ dòng không có id", li._from_row({"title": "x", "url": "/jobs/view/no-id"}) is None)
check("bỏ dòng không có tiêu đề",
      li._from_row({"title": "", "url": "/jobs/view/a-1234567"}) is None)
check("cấp bậc -> mã kinh nghiệm LinkedIn", li.EXPERIENCE["grad"] == "2")

print("\n[Chrome]")
check("tìm được Chrome trên máy", Path(chrome.binary()).exists())
check("profile RIÊNG, không phải profile người dùng",
      "chrome-profile" in str(chrome.profile_dir())
      and "Application Support" not in str(chrome.profile_dir()))
check("cổng riêng, không phải 9222 mặc định", chrome.PORT != 9222)


print("\n[nguồn hỏng phải TRÔNG khác nguồn tốt]")
import tempfile
from jobbot.core import db as _db, postings as _po
from jobbot.ingest.web.base import Health

h = Health(attempted=10, failed=6)
h.note("TimeoutError"); h.note("mô tả rỗng")
check("Health đếm được hỏng", h.failed == 6)
check("Health tóm tắt được lý do", "6/10 failed" in h.summary and "TimeoutError" in h.summary)
check("không hỏng -> không báo gì", Health(10, 0).summary == "")
check("chạy trọn vẹn thì lành", Health(10, 0).ok)

# LỖI THẬT: linkedin.fetch gặp Blocked giữa vòng đọc kỹ thì chỉ note() rồi
# break — failed vẫn 0, record_run thấy 0/193 hỏng nên ghi ok=1, và màn hình
# Settings hiện huy hiệu XANH cho một lần quét bị cắt từ tin thứ ba.
blocked = Health(attempted=193, failed=0)
check("chưa chặn thì lành", blocked.ok)
blocked.block("bị chặn ở tin 3/193", unread=191)
check("bị chặn -> KHÔNG còn lành", not blocked.ok)
check("và số tin chưa đọc được tính là hỏng", blocked.failed == 191)
check("và nói thẳng ra là bị chặn", "BLOCKED" in blocked.summary)
early = Health(attempted=5)
early.block("chặn ngay từ tin đầu", unread=5)
check("bị chặn ngay tin đầu vẫn không lành", not early.ok)

with tempfile.TemporaryDirectory() as tmp:
    conn = _db.connect(Path(tmp) / "h.db")
    _po.record_run(conn, "s1", ok=True, fetched=4, attempted=10, failed=6)
    row = conn.execute("SELECT ok, error FROM source_run WHERE source='s1'").fetchone()
    check("hỏng 60% -> đánh dấu nguồn HỎNG dù vẫn lấy được tin", row["ok"] == 0)
    check("và nói rõ tỉ lệ", "6/10" in row["error"])

    _po.record_run(conn, "s2", ok=True, fetched=10, attempted=10, failed=1)
    check("hỏng 10% -> vẫn coi là chạy tốt",
          conn.execute("SELECT ok FROM source_run WHERE source='s2'").fetchone()["ok"] == 1)

    _po.record_run(conn, "s3", ok=True, fetched=10)
    check("không đo được thì không phán bừa",
          conn.execute("SELECT ok FROM source_run WHERE source='s3'").fetchone()["ok"] == 1)
    conn.close()

print("\n[Posting và bảng DB không được lệch nhau]")
from dataclasses import fields as _fields
from jobbot.core.postings import FIELD_MAP, NOT_COLUMNS
from jobbot.ingest.base import Posting as _P
_attrs = {f.name for f in _fields(_P)}
check("mọi trường Posting đều được khai", not (_attrs - set(FIELD_MAP) - set(NOT_COLUMNS)))
check("không khai thừa trường không tồn tại",
      not ((set(FIELD_MAP) | set(NOT_COLUMNS)) - _attrs))
with tempfile.TemporaryDirectory() as tmp:
    conn = _db.connect(Path(tmp) / "c.db")
    cols = {x[1] for x in conn.execute("PRAGMA table_info(posting)")}
    check("mọi cột khai trong FIELD_MAP đều có thật trong bảng",
          set(FIELD_MAP.values()) <= cols)
    conn.close()

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
