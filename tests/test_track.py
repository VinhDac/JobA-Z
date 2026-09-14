"""Test bước 5-6: nộp và theo dõi.  python3 tests/test_track.py

Trọng tâm là RÀNG BUỘC, không phải tính năng: hộp thư là thứ Vin quan tâm
nhất, nên "chỉ đọc" phải là điều kiểm được, không phải lời hứa trong tài liệu.
"""

import inspect, os, re, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# KHÔNG GỌI MẠNG. Bài này kiểm mail.check(), mà check() mở socket IMAP thật —
# chạy lẻ bài test là nó vác địa chỉ thật ra Internet. run_all.py đã đặt cờ
# này; đặt lại ở đây để chạy lẻ cũng an toàn.
os.environ.setdefault("JOBBOT_OFFLINE", "1")

from jobbot.core import db
from jobbot.track import board, mail, scan, sort

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")


print("\n[hộp thư — CHỈ ĐỌC, và ràng buộc nằm trong code]")
src = inspect.getsource(mail)
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
# ĐẾM TỪNG CHỖ GỌI, KHÔNG DÒ MỘT CHUỖI.
#
# `"readonly=True" in code` xanh ngay cả khi chỉ MỘT trong hai chỗ mở hộp thư
# còn giữ nó. Đã chứng minh: bỏ readonly ở đúng vòng quét 24/7 (chỗ chạy
# nhiều nhất, chỗ đáng canh nhất) mà bài test vẫn báo ok — luật nền số 3 chỉ
# còn là một lời hứa trong tài liệu.
import ast as _astR
_mo = [n for n in _astR.walk(_astR.parse(src))
       if isinstance(n, _astR.Call) and isinstance(n.func, _astR.Attribute)
       and n.func.attr == "select"]
check(f"có {len(_mo)} chỗ mở hộp thư — phải canh HẾT", len(_mo) >= 2)
_thieu = [n.lineno for n in _mo
          if not any(k.arg == "readonly" and getattr(k.value, "value", None) is True
                     for k in n.keywords)]
check("MỌI chỗ mở hộp thư đều readonly=True"
      + (f" — thiếu ở dòng {_thieu}" if _thieu else ""), not _thieu)
check("lấy thư bằng BODY.PEEK — không đặt cờ đã đọc", "BODY.PEEK" in code)
# Kiểm CHÍNH XÁC: mọi lệnh gọi lên đối tượng IMAP (biến `box`), không phải
# tìm chuỗi ký tự — `out.append(...)` của list từng bị bắt nhầm là lệnh APPEND
# của IMAP.
import ast as _ast
calls = set()
for node in _ast.walk(_ast.parse(src)):
    if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Attribute)
            and isinstance(node.func.value, _ast.Name)
            and node.func.value.id == "box"):
        calls.add(node.func.attr)
check(f"chỉ gọi {sorted(calls)} lên hộp thư",
      calls <= {"login", "select", "search", "fetch", "logout", "close"})
for danger in ("store", "append", "copy", "expunge", "uid", "setacl",
               "create", "delete", "rename", "subscribe"):
    check(f"KHÔNG gọi box.{danger}()", danger not in calls)
check("KHÔNG import smtp", "smtplib" not in code)
check("giới hạn 30 ngày", mail.SINCE_DAYS == 30 and "since_days" in code)
check("có trần số thư, hộp to không treo vòng quét", mail.MAX_MESSAGES > 0)
check("chưa cấu hình thì báo lỗi rõ, không nổ vu vơ",
      "config.toml" in code)

print("\n[nộp lại nơi từng bị từ chối]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _id = board.add(conn, "Point72", "QR Intern")
    board.set_stage(conn, _id, board.REJECTED, "từ chối")
    # Công ty mở lại tin, Vin bấm Nộp. Giữ nguyên chặng "từ chối" thì bảng
    # không vẽ nút Gửi đơn, và lá đơn Vin vừa điền không bao giờ đi.
    board.add(conn, "Point72", "QR Intern", stage=board.DRAFT)
    _r = board.all(conn)[0]
    check("kéo về nháp để gửi được", _r["stage"] == board.DRAFT)
    check("nhưng NÓI RA kết cục cũ", "previously" in (_r["last_event"] or ""))
    check("vẫn một dòng, không đẻ thêm", len(board.all(conn)) == 1)
    # Dòng dựng từ thư không có số hiệu tin; không gắn vào thì nút Gửi đơn
    # trả "không có tin gốc".
    from jobbot.core import postings as _postings
    from jobbot.ingest.base import Posting as _P
    _postings.save_batch(conn, "greenhouse:test", [_P(
        source_id="mg-1", title="Quant", company="Man Group",
        location="London", url="http://x", description="d " * 60)])
    _pid = conn.execute("SELECT id FROM posting WHERE company = 'Man Group'"
                        ).fetchone()["id"]
    board.add(conn, "Man Group", "", origin="mail")
    board.add(conn, "Man Group", "", posting_id=_pid, stage=board.DRAFT)
    _m = [x for x in board.all(conn) if x["company"] == "Man Group"][0]
    check("gắn số hiệu tin vào dòng dựng từ thư", _m["posting_id"] == _pid)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[DB chứa CV và thư — chỉ chủ máy đọc được]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    conn.close()
    from pathlib import Path as _P2
    _dbf = _P2(tmp) / "jobbot.db"
    # Mặc định của sqlite là 0644: bất kỳ tài khoản nào trên máy cũng đọc được
    # toàn văn CV, hồ sơ, và tiêu đề + 400 ký tự đầu mọi thư tuyển dụng.
    check("DB không cho người khác đọc",
          _dbf.exists() and not (_dbf.stat().st_mode & 0o077))
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[giành quyền gửi — nguyên tử]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _ap = board.add(conn, "Prima", "Quant", stage=board.DRAFT)
    check("cú bấm đầu giành được", board.claim(conn, _ap) is True)
    check("cú bấm thứ hai KHÔNG giành được", board.claim(conn, _ap) is False)
    board.unclaim(conn, _ap)
    check("gửi hụt thì trả về nháp", board.all(conn)[0]["stage"] == board.DRAFT)
    check("và giành lại được", board.claim(conn, _ap) is True)
    board.set_stage(conn, _ap, board.SENT, "đã gửi")
    check("gửi xong thì sang đã nộp", board.all(conn)[0]["stage"] == board.SENT)
    check("đã nộp thì không giành được nữa", board.claim(conn, _ap) is False)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[thư CŨ không được đè trạng thái MỚI]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _app = board.add(conn, "Man Group", "Quant")

    def _mm(mid, sub, when):
        return {"msg_id": mid, "from_addr": "x@mangroup.com",
                "from_name": "Man Group", "subject": sub, "snippet": "",
                "received_at": when}

    from jobbot.track import scan as _scan
    _scan.store(conn, _mm("<1>", "Thank you for applying", "2026-09-01T09:00:00+00:00"),
                board.SENT, "Man Group", _app)
    _scan.store(conn, _mm("<2>", "Update", "2026-09-20T09:00:00+00:00"),
                board.REJECTED, "Man Group", _app)
    _ids = {r["kind"]: r["id"] for r in conn.execute("SELECT id, kind FROM message")}
    _scan.settle(conn, _ids["rejected"], True)
    check("thư mới đổi được trạng thái", board.all(conn)[0]["stage"] == board.REJECTED)
    # Man Group gửi "thank you" ngày 1 rồi "unfortunately" ngày 20. Nhận thư
    # từ chối trước rồi nhận nốt thư cũ -> bảng nói đơn còn sống, thực tế đã chết.
    _scan.settle(conn, _ids["applied"], True)
    check("thư CŨ không kéo ngược được", board.all(conn)[0]["stage"] == board.REJECTED)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[thư không có Message-ID]")
import email as _email
_e1 = _email.message_from_string("From: x@y.z\nSubject: Rejected\n"
                                 "Date: Mon, 1 Sep 2026 09:00:00 +0000\n\nhi")
_e2 = _email.message_from_string("From: q@y.z\nSubject: Interview\n"
                                 "Date: Mon, 2 Sep 2026 09:00:00 +0000\n\nhi")
# Số thứ tự trong hộp thư ĐỔI mỗi khi thêm/bớt thư, nên lần quét sau một lá
# KHÁC mang cùng "no-id-42" và bị coi là đã đọc — thư từ chối biến mất.
check("id thay thế ổn định theo lá thư", mail._made_id(_e1) == mail._made_id(_e1))
check("hai lá khác nhau ra id khác nhau", mail._made_id(_e1) != mail._made_id(_e2))
check("không dùng số thứ tự làm id",
      "no-id-{num" not in (Path(__file__).resolve().parent.parent
                           / "src/jobbot/track/mail.py").read_text(encoding="utf-8"))

print("\n[hai lỗi audit ở khúc thư]")
# (11) Một lá thư dị dạng KHÔNG được giết cả vòng quét 30 ngày.
_mailsrc = (Path(__file__).resolve().parent.parent
            / "src/jobbot/track/mail.py").read_text(encoding="utf-8")
check("mỗi lá thư có vòng bảo vệ riêng", "broken += 1" in _mailsrc)
check("và báo ra số thư bỏ qua", "thư đọc không nổi" in _mailsrc)
check("ngày sai định dạng không nổ", "except (TypeError, ValueError)" in _mailsrc)
# (12) Một công ty, nhiều lần nộp: đẩy bừa dòng đầu là chuyển trạng thái đơn
#      khác — thư từ chối vai trò A hạ luôn vai trò B đang chờ phỏng vấn.
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _a = board.add(conn, "Point72", "Quantitative Researcher")
    _b = board.add(conn, "Point72", "Data Engineer")

    def _msg(sub):
        return {"subject": sub, "snippet": "", "from_name": "Point72",
                "from_addr": "careers@point72.com"}

    check("thư nêu rõ vai trò -> đúng dòng đó",
          sort.match(conn, _msg("Update on your Data Engineer application")) == _b)
    check("thư không nêu vai trò -> KHÔNG đoán bừa",
          sort.match(conn, _msg("Update on your application")) is None)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[vòng quét phải là KHÁCH — máy tự canh, không bắt người nhớ]")
from jobbot.ingest.web import linkedin as _lk
from jobbot.ingest.web.base import Blocked as _Blocked


class _Cookies:
    """Tab giả trả về cookie LinkedIn."""

    def __init__(self, signed):
        self.signed = signed

    def call(self, method, params=None, timeout=30.0):
        if method == "Network.getCookies":
            return {"cookies": [{"name": "li_at", "value": "x"}] if self.signed else []}
        return {}


check("nhận ra profile ĐANG đăng nhập", _lk.signed_in(_Cookies(True)))
check("nhận ra profile khách", not _lk.signed_in(_Cookies(False)))
# Cửa sổ quét và cửa sổ nộp trông giống hệt nhau; đăng nhập nhầm là mỗi lần
# quét chạy dưới tài khoản thật — đúng thứ dễ mất tài khoản nhất.
_raised = ""
try:
    _lk.fetch(_Cookies(True), ["quant"])
except _Blocked as exc:
    _raised = str(exc)
except Exception as exc:                          # noqa: BLE001
    _raised = f"SAI LOẠI: {type(exc).__name__}"
check("quét khi đang đăng nhập -> Blocked", _raised.startswith("profile QUÉT"))
# Blocked phải được bắt RIÊNG cho từng nguồn: LinkedIn bị bỏ qua thì các nguồn
# khác vẫn chạy, chứ không giết cả vòng quét.
_runner = (Path(__file__).resolve().parent.parent
           / "src/jobbot/scan_runner.py").read_text(encoding="utf-8")
# So vị trí chuỗi trong file là sai: có `except Exception` khác nằm trước
# trong tệp mà không cùng một khối try. Hỏi AST thì mới đúng.
import ast as _ast
_tree = _ast.parse(_runner)
_ok = False
for _n in _ast.walk(_tree):
    if not isinstance(_n, _ast.Try):
        continue
    _names = [(_h.type.id if isinstance(_h.type, _ast.Name) else "") for _h in _n.handlers]
    if "Blocked" in _names:
        _ok = _names.index("Blocked") < (_names.index("Exception")
                                         if "Exception" in _names else 99)
        break
check("scan_runner bắt Blocked riêng, TRƯỚC Exception chung", _ok)

print("\n[nối hộp thư từ giao diện — mật khẩu không được rò ra]")
from jobbot.core import config as _cfg
from jobbot.dashboard.views import track as _tv

# CHẠY TRÊN REPO GIẢ. Bản cũ ghi thẳng vào config.toml THẬT rồi khôi phục ở
# finally — và khi tệp thật chưa tồn tại thì không có gì để khôi phục, nên nó
# để lại địa chỉ giả "a@b.c" với app password rỗng trong tệp của Vin. Chuyện
# đó xảy ra thật ngày 12/09.
import os as _osc, shutil as _shc, tempfile as _tfc
_ctmp = _tfc.mkdtemp()
_cu_root_c = _osc.environ.get("JOBBOT_ROOT")
_osc.environ["JOBBOT_ROOT"] = _ctmp
try:
    (Path(_ctmp) / "config").mkdir(parents=True, exist_ok=True)
    _shc.copy(Path(__file__).resolve().parent.parent
              / "config" / "config.example.toml",
              Path(_ctmp) / "config" / "config.example.toml")
    # CHỐT: không bao giờ ghi vào config THẬT. Cùng luật với chốt "test đang
    # trỏ vào DB THẬT" — và chốt này có vì đã mất một app password thật.
    assert str(_cfg.PATH).startswith(_ctmp), f"đang ghi vào config THẬT: {_cfg.PATH}"
    _cfg.write_value("mail", "address", "a@b.c")
    _cfg.write_value("mail", "password", 'p"w\\d')
    check("ghi rồi đọc lại ra đúng", _cfg.section("mail")["password"] == 'p"w\\d')
    check("không đụng khoá khác", _cfg.section("mail")["address"] == "a@b.c")
    # config.toml có phần chú thích dài giải thích vì sao dùng hộp thư riêng.
    # Dựng lại cả tệp là xoá mất phần đó.
    check("giữ nguyên chú thích", "app password" in _cfg.PATH.read_text())
    check("chỉ chủ máy đọc được", (_cfg.PATH.stat().st_mode & 0o777) == 0o600)
    _cfg.write_value("mail", "password", "")
    check("xoá được", _cfg.section("mail")["password"] == "")
finally:
    if _cu_root_c is None:
        _osc.environ.pop("JOBBOT_ROOT", None)
    else:
        _osc.environ["JOBBOT_ROOT"] = _cu_root_c
    _shc.rmtree(_ctmp, ignore_errors=True)

# Ô NHẬP HỘP THƯ ĐÃ CHUYỂN SANG CÀI ĐẶT · GMAIL. Nó là cấu hình — nối một
# lần rồi thôi — mà trang Quản lí thì Vin mở hàng ngày; để một form cấu hình
# trên đầu bảng việc là bắt mắt đọc lại nó mỗi ngày.
_html = _tv.render(rows=[], asks=[], counts={}, mail_ready=False,
                   mail_address="a@b.c")
check("Quản lí KHÔNG còn form nối hộp thư", "/api/mail/setup" not in _html)
check("nhưng chỉ ra đúng chỗ nối", "data-appset='gmail'" in _html)
_on = _tv.render(rows=[], asks=[], counts={}, mail_ready=True,
                 mail_address="a@b.c", mail_days=45)
# NÚT QUÉT ĐÃ LÊN THANH KHÚC, như Search và CV. Để cả hai chỗ là hai nút cùng
# làm một việc, và người dùng phải đoán chúng có khác nhau không.
check("nút quét nằm trên thanh khúc", "data-arg='track'" in _on)
check("trong ô chỉ còn TÌNH TRẠNG hộp thư, không nút thứ hai",
      "/api/track/mail/scan" not in _on)
check("và vẫn nói đúng số ngày đang đặt", "45 ngày" in _on)

# Form nối giờ nằm trong Cài đặt — mọi lời hứa về mật khẩu vẫn phải giữ.
from jobbot.dashboard.views import settings as _sv
_set = _sv.render(every=60, hours=(8, 22), status=[], mail_ready=False,
                  mail_address="a@b.c", mail_days=30)
check("Cài đặt có ô nhập hộp thư", "/api/mail/setup" in _set)
check("ô mật khẩu là type=password", "type=password" in _set)
check("KHÔNG vẽ giá trị mật khẩu ra HTML",
      not re.search(r"type=password[^>]*value=", _set))
check("địa chỉ thì vẽ ra được", "a@b.c" in _set)
_set_on = _sv.render(every=60, hours=(8, 22), status=[], mail_ready=True,
                     mail_address="a@b.c", mail_days=30, mail_profile="a@b.c")
# NỐI MỘT LẦN, và chỉ "Làm lại từ đầu" mới xoá. Hai đường phá hoại cho cùng
# một thứ là hai chỗ bấm nhầm — app password này đã mất ba lần trong một ngày.
check("KHÔNG còn nút xoá mật khẩu riêng", "/api/mail/forget" not in _set_on)
check("và nói rõ chỉ Làm lại từ đầu mới xoá", "Làm lại từ đầu" in _set_on)
check("nhưng vẫn đổi được bằng cách dán đè", "/api/mail/setup" in _set_on)
_srv3 = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("route xoá đã gỡ hẳn", '"/api/mail/forget"' not in _srv3)
# CHỐT: hộp thư quét phải ĐÚNG hộp thư khai trong hồ sơ. Nối nhầm thì app
# quét một nơi mà thư về một nơi — bảng Quản lí báo "đang chờ" mãi cho những
# đơn đã có hồi âm, và không có dấu hiệu nào cho thấy sai.
check("nối hộp thư có chốt khớp hồ sơ",
      'store.load(conn_ho_so).get("email")' in _srv3)
_set_khac = _sv.render(every=60, hours=(8, 22), status=[], mail_ready=False,
                       mail_address="", mail_days=30, mail_profile="vin@x.y")
check("nói TRƯỚC phải khớp địa chỉ nào", "vin@x.y" in _set_khac)
check("và điền sẵn để khỏi gõ sai", "value='vin@x.y'" in _set_khac)
check("hồ sơ chưa khai thì chỉ đường đi khai",
      "Hồ sơ chưa khai địa chỉ" in _sv.render(every=60, hours=(8, 22), status=[]))
check("và có ô đặt số ngày đọc lại thư", "name=mail_days" in _set)
_srv2 = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("route xoá đòi xác nhận", '!= "xoa"' in _srv2)

# Thông báo lỗi của imaplib là nguyên văn máy chủ trả lời, và nó đi thẳng vào
# nhật ký — một lần lọt là lọt vĩnh viễn.
check("mật khẩu bị bịt trong thông báo lỗi",
      mail._hide("login failed for hunter2", "hunter2") == "login failed for ***")
check("chưa điền thì nói ngay, không gọi mạng",
      mail.check("", "") == "chưa điền đủ địa chỉ và app password")
# Dán nhầm MẬT KHẨU TÀI KHOẢN là chuyện thường. Bắt bằng hình dạng, TRƯỚC khi
# gửi nó qua mạng — không thì mật khẩu thật đã bay đi rồi mới biết là vô ích.
check("mật khẩu tài khoản bị chặn tại chỗ",
      "không phải app password" in mail.check("a@gmail.com", "Work123@"))
check("và không hề gọi mạng",
      "Gmail từ chối" not in mail.check("a@gmail.com", "Work123@"))
# HÌNH DẠNG ĐÓ LÀ CỦA GOOGLE. Bản cũ áp nó cho MỌI địa chỉ, nên ai dùng
# Outlook / iCloud / hộp thư công ty bị chặn ngay cửa bằng một câu chẳng
# liên quan gì tới lý do thật — mà mật khẩu của họ có thể hoàn toàn đúng.
check("nhà cung cấp khác KHÔNG bị bộ lọc của Google chặn",
      "không phải app password" not in mail.check("a@outlook.com", "Work123@"))
check("app password đúng hình dạng thì cho qua vòng kiểm hình dạng",
      "không phải app password" not in mail.check.__doc__ or
      bool(mail.APP_PASSWORD.fullmatch("abcdefghijklmnop")))
check("Google hiện theo nhóm 4 — bỏ dấu cách vẫn nhận",
      bool(mail.APP_PASSWORD.fullmatch("abcd efgh ijkl mnop".replace(" ", ""))))
# Thứ đem đi KIỂM phải đúng bằng thứ đem đi ĐĂNG NHẬP. Route bỏ dấu cách ngay
# lúc lưu; nếu không, check() so chuỗi đã bỏ cách còn login() gửi chuỗi có cách.
_srv = (Path(__file__).resolve().parent.parent
        / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("lưu app password thì bỏ dấu cách", '.replace(" ", "")' in _srv)

print("\n[xếp loại thư]")
def m(subject, snippet="", name="", addr=""):
    return {"subject": subject, "snippet": snippet,
            "from_name": name, "from_addr": addr, "msg_id": subject}

check("thư xác nhận", sort.kind(m("Thank you for applying")) == board.SENT)
check("thư từ chối",
      sort.kind(m("Update", "we will not be moving forward")) == board.REJECTED)
check("thư mời phỏng vấn",
      sort.kind(m("Next steps", "we would like to invite you to a call")) == board.INTERVIEW)
check("bài kiểm tra online cũng tính là phỏng vấn",
      sort.kind(m("Assessment", "please complete the HackerRank test")) == board.INTERVIEW)
check("thư mời việc", sort.kind(m("Offer", "we are pleased to offer you")) == board.OFFER)
check("thư khác thì để yên", sort.kind(m("5 new jobs for you")) == "other")
# Thư mời phỏng vấn thường VẪN mở đầu bằng "thank you for applying". Xét từ
# kết cục mạnh nhất xuống, nếu không thì thư quan trọng nhất bị xếp thành xác nhận.
check("mời phỏng vấn thắng xác nhận khi cùng một thư",
      sort.kind(m("Your application",
                  "Thank you for applying. We would like to invite you to a call."))
      == board.INTERVIEW)

print("\n[đoán công ty]")
for want, msg in (("Point72", m("x", name="Careers at Point72")),
                  ("Jump Trading", m("x", name="Jump Trading Recruiting")),
                  ("Schonfeld", m("x", name="Schonfeld Talent Acquisition Team")),
                  ("Qube Research", m("Interview - Qube Research", addr="a@greenhouse.io")),
                  ("Jane Street", m("Your application to Jane Street", addr="a@lever.co"))):
    got = sort.company_of(msg)
    check(f"{want:<14} <- {got[:26]}", want.lower() in got.lower())

with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "t.db")

    print("\n[bảng]")
    a = board.add(conn, "Point72", "Quantitative Researcher", cv_file="p.pdf")
    b = board.add(conn, "Point72", "Quantitative Researcher")
    check("nộp lại cùng vai trò KHÔNG đẻ dòng mới", a == b)
    check("nộp khác vai trò thì là dòng khác",
          board.add(conn, "Point72", "Data Scientist") != a)
    board.set_stage(conn, a, board.REJECTED, "not moving forward")
    check("đổi được trạng thái",
          [r for r in board.all(conn) if r["id"] == a][0]["stage"] == board.REJECTED)
    board.set_stage(conn, a, "bịa")
    check("trạng thái bịa thì không nhận",
          [r for r in board.all(conn) if r["id"] == a][0]["stage"] == board.REJECTED)

    # `im lặng` là PHÉP TRỪ, không phải cột. Lưu thì phải cập nhật mỗi ngày,
    # và sẽ có ngày quên — cùng lý do `khoảng trống` ở lưới project không lưu.
    check("im lặng không phải cột trong bảng",
          "silent" not in [r[1] for r in conn.execute("PRAGMA table_info(application)")])
    old = board.add(conn, "Old Firm", "Analyst",
                    applied_at="2020-01-01T00:00:00+00:00")
    row = [r for r in board.all(conn) if r["id"] == old][0]
    check("nộp lâu, chưa thư nào -> im lặng", row["silent"])
    board.set_stage(conn, old, board.INTERVIEW, "mời phỏng vấn")
    row = [r for r in board.all(conn) if r["id"] == old][0]
    check("có thư rồi thì hết im lặng", not row["silent"])

    print("\n[thư khớp vào dòng nào]")
    conn.execute("DELETE FROM message"); conn.execute("DELETE FROM application")
    conn.commit()
    p72 = board.add(conn, "Point72", "Quantitative Researcher")
    board.add(conn, "Man Group", "Quant Developer")
    check("khớp theo tên người gửi",
          sort.match(conn, m("x", name="Careers at Point72")) == p72)
    check("tên miền không có dấu cách vẫn khớp (mangroup <-> man group)",
          sort.match(conn, m("Application update", addr="careers@mangroup.com")) is not None)
    check("không khớp được thì nói không khớp, không đoán bừa",
          sort.match(conn, m("Interview - Some Firm Nobody Applied To",
                             addr="a@greenhouse.io")) is None)

    print("\n[thư ĐỀ XUẤT, không tự đổi]")
    conn.execute("DELETE FROM message"); conn.execute("DELETE FROM application")
    conn.commit()
    app = board.add(conn, "Point72", "Quantitative Researcher")
    note = m("Next steps", "we would like to invite you to a call",
             name="Careers at Point72")
    scan.store(conn, {**note, "received_at": "2026-09-08T10:00:00",
                      "from_addr": "", "from_name": "Careers at Point72"},
               sort.kind(note), sort.company_of(note), app)
    stage_now = [r for r in board.all(conn) if r["id"] == app][0]["stage"]
    check("thư về mà trạng thái CHƯA đổi", stage_now == board.SENT)
    asks = scan.proposals(conn)
    check("nó nằm ở dải chờ Vin quyết", len(asks) == 1)
    check("và nói rõ đổi sang gì", asks[0]["kind"] == board.INTERVIEW)
    scan.settle(conn, asks[0]["id"], accept=True)
    check("Vin nhận thì mới đổi",
          [r for r in board.all(conn) if r["id"] == app][0]["stage"] == board.INTERVIEW)
    check("trả lời xong thì không hỏi lại", scan.proposals(conn) == [])

    print("\n[dựng lại quá khứ từ thư]")
    # Xoá THƯ trước rồi mới xoá dòng nộp: message.application_id là khoá
    # ngoại, và nó KHÔNG có ON DELETE CASCADE. Nghĩa là sau này muốn cho Vin
    # xoá một dòng khỏi bảng thì phải gỡ thư trỏ vào nó trước.
    conn.execute("DELETE FROM message"); conn.execute("DELETE FROM application")
    conn.commit()
    past = m("Thank you for applying", "We have received your application.",
             name="Jump Trading Recruiting")
    kind, who = sort.kind(past), sort.company_of(past)
    got = sort.match(conn, past)
    if got is None and kind == board.SENT and who:
        got = board.add(conn, who, "", origin="mail",
                        applied_at="2026-08-20T09:00:00+00:00")
    check("thư xác nhận không khớp ai -> dựng lại một lần nộp", got is not None)
    row = board.all(conn)[0]
    check("và ghi rõ nó đến từ thư", row["origin"] == "mail")
    check("giữ đúng ngày trong thư", row["applied_at"].startswith("2026-08-20"))
    conn.close()

print("\n[nộp lại nơi từng bị từ chối]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _id = board.add(conn, "Point72", "QR Intern")
    board.set_stage(conn, _id, board.REJECTED, "từ chối")
    # Công ty mở lại tin, Vin bấm Nộp. Giữ nguyên chặng "từ chối" thì bảng
    # không vẽ nút Gửi đơn, và lá đơn Vin vừa điền không bao giờ đi.
    board.add(conn, "Point72", "QR Intern", stage=board.DRAFT)
    _r = board.all(conn)[0]
    check("kéo về nháp để gửi được", _r["stage"] == board.DRAFT)
    check("nhưng NÓI RA kết cục cũ", "previously" in (_r["last_event"] or ""))
    check("vẫn một dòng, không đẻ thêm", len(board.all(conn)) == 1)
    # Dòng dựng từ thư không có số hiệu tin; không gắn vào thì nút Gửi đơn
    # trả "không có tin gốc".
    from jobbot.core import postings as _postings
    from jobbot.ingest.base import Posting as _P
    _postings.save_batch(conn, "greenhouse:test", [_P(
        source_id="mg-1", title="Quant", company="Man Group",
        location="London", url="http://x", description="d " * 60)])
    _pid = conn.execute("SELECT id FROM posting WHERE company = 'Man Group'"
                        ).fetchone()["id"]
    board.add(conn, "Man Group", "", origin="mail")
    board.add(conn, "Man Group", "", posting_id=_pid, stage=board.DRAFT)
    _m = [x for x in board.all(conn) if x["company"] == "Man Group"][0]
    check("gắn số hiệu tin vào dòng dựng từ thư", _m["posting_id"] == _pid)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[DB chứa CV và thư — chỉ chủ máy đọc được]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    conn.close()
    from pathlib import Path as _P2
    _dbf = _P2(tmp) / "jobbot.db"
    # Mặc định của sqlite là 0644: bất kỳ tài khoản nào trên máy cũng đọc được
    # toàn văn CV, hồ sơ, và tiêu đề + 400 ký tự đầu mọi thư tuyển dụng.
    check("DB không cho người khác đọc",
          _dbf.exists() and not (_dbf.stat().st_mode & 0o077))
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[giành quyền gửi — nguyên tử]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _ap = board.add(conn, "Prima", "Quant", stage=board.DRAFT)
    check("cú bấm đầu giành được", board.claim(conn, _ap) is True)
    check("cú bấm thứ hai KHÔNG giành được", board.claim(conn, _ap) is False)
    board.unclaim(conn, _ap)
    check("gửi hụt thì trả về nháp", board.all(conn)[0]["stage"] == board.DRAFT)
    check("và giành lại được", board.claim(conn, _ap) is True)
    board.set_stage(conn, _ap, board.SENT, "đã gửi")
    check("gửi xong thì sang đã nộp", board.all(conn)[0]["stage"] == board.SENT)
    check("đã nộp thì không giành được nữa", board.claim(conn, _ap) is False)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[thư CŨ không được đè trạng thái MỚI]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _app = board.add(conn, "Man Group", "Quant")

    def _mm(mid, sub, when):
        return {"msg_id": mid, "from_addr": "x@mangroup.com",
                "from_name": "Man Group", "subject": sub, "snippet": "",
                "received_at": when}

    from jobbot.track import scan as _scan
    _scan.store(conn, _mm("<1>", "Thank you for applying", "2026-09-01T09:00:00+00:00"),
                board.SENT, "Man Group", _app)
    _scan.store(conn, _mm("<2>", "Update", "2026-09-20T09:00:00+00:00"),
                board.REJECTED, "Man Group", _app)
    _ids = {r["kind"]: r["id"] for r in conn.execute("SELECT id, kind FROM message")}
    _scan.settle(conn, _ids["rejected"], True)
    check("thư mới đổi được trạng thái", board.all(conn)[0]["stage"] == board.REJECTED)
    # Man Group gửi "thank you" ngày 1 rồi "unfortunately" ngày 20. Nhận thư
    # từ chối trước rồi nhận nốt thư cũ -> bảng nói đơn còn sống, thực tế đã chết.
    _scan.settle(conn, _ids["applied"], True)
    check("thư CŨ không kéo ngược được", board.all(conn)[0]["stage"] == board.REJECTED)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[thư không có Message-ID]")
import email as _email
_e1 = _email.message_from_string("From: x@y.z\nSubject: Rejected\n"
                                 "Date: Mon, 1 Sep 2026 09:00:00 +0000\n\nhi")
_e2 = _email.message_from_string("From: q@y.z\nSubject: Interview\n"
                                 "Date: Mon, 2 Sep 2026 09:00:00 +0000\n\nhi")
# Số thứ tự trong hộp thư ĐỔI mỗi khi thêm/bớt thư, nên lần quét sau một lá
# KHÁC mang cùng "no-id-42" và bị coi là đã đọc — thư từ chối biến mất.
check("id thay thế ổn định theo lá thư", mail._made_id(_e1) == mail._made_id(_e1))
check("hai lá khác nhau ra id khác nhau", mail._made_id(_e1) != mail._made_id(_e2))
check("không dùng số thứ tự làm id",
      "no-id-{num" not in (Path(__file__).resolve().parent.parent
                           / "src/jobbot/track/mail.py").read_text(encoding="utf-8"))

print("\n[hai lỗi audit ở khúc thư]")
# (11) Một lá thư dị dạng KHÔNG được giết cả vòng quét 30 ngày.
_mailsrc = (Path(__file__).resolve().parent.parent
            / "src/jobbot/track/mail.py").read_text(encoding="utf-8")
check("mỗi lá thư có vòng bảo vệ riêng", "broken += 1" in _mailsrc)
check("và báo ra số thư bỏ qua", "thư đọc không nổi" in _mailsrc)
check("ngày sai định dạng không nổ", "except (TypeError, ValueError)" in _mailsrc)
# (12) Một công ty, nhiều lần nộp: đẩy bừa dòng đầu là chuyển trạng thái đơn
#      khác — thư từ chối vai trò A hạ luôn vai trò B đang chờ phỏng vấn.
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _a = board.add(conn, "Point72", "Quantitative Researcher")
    _b = board.add(conn, "Point72", "Data Engineer")

    def _msg(sub):
        return {"subject": sub, "snippet": "", "from_name": "Point72",
                "from_addr": "careers@point72.com"}

    check("thư nêu rõ vai trò -> đúng dòng đó",
          sort.match(conn, _msg("Update on your Data Engineer application")) == _b)
    check("thư không nêu vai trò -> KHÔNG đoán bừa",
          sort.match(conn, _msg("Update on your application")) is None)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[vòng quét phải là KHÁCH — máy tự canh, không bắt người nhớ]")
from jobbot.ingest.web import linkedin as _lk
from jobbot.ingest.web.base import Blocked as _Blocked


class _Cookies:
    """Tab giả trả về cookie LinkedIn."""

    def __init__(self, signed):
        self.signed = signed

    def call(self, method, params=None, timeout=30.0):
        if method == "Network.getCookies":
            return {"cookies": [{"name": "li_at", "value": "x"}] if self.signed else []}
        return {}


check("nhận ra profile ĐANG đăng nhập", _lk.signed_in(_Cookies(True)))
check("nhận ra profile khách", not _lk.signed_in(_Cookies(False)))
# Cửa sổ quét và cửa sổ nộp trông giống hệt nhau; đăng nhập nhầm là mỗi lần
# quét chạy dưới tài khoản thật — đúng thứ dễ mất tài khoản nhất.
_raised = ""
try:
    _lk.fetch(_Cookies(True), ["quant"])
except _Blocked as exc:
    _raised = str(exc)
except Exception as exc:                          # noqa: BLE001
    _raised = f"SAI LOẠI: {type(exc).__name__}"
check("quét khi đang đăng nhập -> Blocked", _raised.startswith("profile QUÉT"))
# Blocked phải được bắt RIÊNG cho từng nguồn: LinkedIn bị bỏ qua thì các nguồn
# khác vẫn chạy, chứ không giết cả vòng quét.
_runner = (Path(__file__).resolve().parent.parent
           / "src/jobbot/scan_runner.py").read_text(encoding="utf-8")
# So vị trí chuỗi trong file là sai: có `except Exception` khác nằm trước
# trong tệp mà không cùng một khối try. Hỏi AST thì mới đúng.
import ast as _ast
_tree = _ast.parse(_runner)
_ok = False
for _n in _ast.walk(_tree):
    if not isinstance(_n, _ast.Try):
        continue
    _names = [(_h.type.id if isinstance(_h.type, _ast.Name) else "") for _h in _n.handlers]
    if "Blocked" in _names:
        _ok = _names.index("Blocked") < (_names.index("Exception")
                                         if "Exception" in _names else 99)
        break
check("scan_runner bắt Blocked riêng, TRƯỚC Exception chung", _ok)

print("\n[nối hộp thư từ giao diện — mật khẩu không được rò ra]")
from jobbot.core import config as _cfg
from jobbot.dashboard.views import track as _tv

# CHẠY TRÊN REPO GIẢ. Bản cũ ghi thẳng vào config.toml THẬT rồi khôi phục ở
# finally — và khi tệp thật chưa tồn tại thì không có gì để khôi phục, nên nó
# để lại địa chỉ giả "a@b.c" với app password rỗng trong tệp của Vin. Chuyện
# đó xảy ra thật ngày 12/09.
import os as _osc, shutil as _shc, tempfile as _tfc
_ctmp = _tfc.mkdtemp()
_cu_root_c = _osc.environ.get("JOBBOT_ROOT")
_osc.environ["JOBBOT_ROOT"] = _ctmp
try:
    (Path(_ctmp) / "config").mkdir(parents=True, exist_ok=True)
    _shc.copy(Path(__file__).resolve().parent.parent
              / "config" / "config.example.toml",
              Path(_ctmp) / "config" / "config.example.toml")
    # CHỐT: không bao giờ ghi vào config THẬT. Cùng luật với chốt "test đang
    # trỏ vào DB THẬT" — và chốt này có vì đã mất một app password thật.
    assert str(_cfg.PATH).startswith(_ctmp), f"đang ghi vào config THẬT: {_cfg.PATH}"
    _cfg.write_value("mail", "address", "a@b.c")
    _cfg.write_value("mail", "password", 'p"w\\d')
    check("ghi rồi đọc lại ra đúng", _cfg.section("mail")["password"] == 'p"w\\d')
    check("không đụng khoá khác", _cfg.section("mail")["address"] == "a@b.c")
    # config.toml có phần chú thích dài giải thích vì sao dùng hộp thư riêng.
    # Dựng lại cả tệp là xoá mất phần đó.
    check("giữ nguyên chú thích", "app password" in _cfg.PATH.read_text())
    check("chỉ chủ máy đọc được", (_cfg.PATH.stat().st_mode & 0o777) == 0o600)
    _cfg.write_value("mail", "password", "")
    check("xoá được", _cfg.section("mail")["password"] == "")
finally:
    if _cu_root_c is None:
        _osc.environ.pop("JOBBOT_ROOT", None)
    else:
        _osc.environ["JOBBOT_ROOT"] = _cu_root_c
    _shc.rmtree(_ctmp, ignore_errors=True)

# Ô NHẬP HỘP THƯ ĐÃ CHUYỂN SANG CÀI ĐẶT · GMAIL. Nó là cấu hình — nối một
# lần rồi thôi — mà trang Quản lí thì Vin mở hàng ngày; để một form cấu hình
# trên đầu bảng việc là bắt mắt đọc lại nó mỗi ngày.
_html = _tv.render(rows=[], asks=[], counts={}, mail_ready=False,
                   mail_address="a@b.c")
check("Quản lí KHÔNG còn form nối hộp thư", "/api/mail/setup" not in _html)
check("nhưng chỉ ra đúng chỗ nối", "data-appset='gmail'" in _html)
_on = _tv.render(rows=[], asks=[], counts={}, mail_ready=True,
                 mail_address="a@b.c", mail_days=45)
# NÚT QUÉT ĐÃ LÊN THANH KHÚC, như Search và CV. Để cả hai chỗ là hai nút cùng
# làm một việc, và người dùng phải đoán chúng có khác nhau không.
check("nút quét nằm trên thanh khúc", "data-arg='track'" in _on)
check("trong ô chỉ còn TÌNH TRẠNG hộp thư, không nút thứ hai",
      "/api/track/mail/scan" not in _on)
check("và vẫn nói đúng số ngày đang đặt", "45 ngày" in _on)

# Form nối giờ nằm trong Cài đặt — mọi lời hứa về mật khẩu vẫn phải giữ.
from jobbot.dashboard.views import settings as _sv
_set = _sv.render(every=60, hours=(8, 22), status=[], mail_ready=False,
                  mail_address="a@b.c", mail_days=30)
check("Cài đặt có ô nhập hộp thư", "/api/mail/setup" in _set)
check("ô mật khẩu là type=password", "type=password" in _set)
check("KHÔNG vẽ giá trị mật khẩu ra HTML",
      not re.search(r"type=password[^>]*value=", _set))
check("địa chỉ thì vẽ ra được", "a@b.c" in _set)
_set_on = _sv.render(every=60, hours=(8, 22), status=[], mail_ready=True,
                     mail_address="a@b.c", mail_days=30, mail_profile="a@b.c")
# NỐI MỘT LẦN, và chỉ "Làm lại từ đầu" mới xoá. Hai đường phá hoại cho cùng
# một thứ là hai chỗ bấm nhầm — app password này đã mất ba lần trong một ngày.
check("KHÔNG còn nút xoá mật khẩu riêng", "/api/mail/forget" not in _set_on)
check("và nói rõ chỉ Làm lại từ đầu mới xoá", "Làm lại từ đầu" in _set_on)
check("nhưng vẫn đổi được bằng cách dán đè", "/api/mail/setup" in _set_on)
_srv3 = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("route xoá đã gỡ hẳn", '"/api/mail/forget"' not in _srv3)
# CHỐT: hộp thư quét phải ĐÚNG hộp thư khai trong hồ sơ. Nối nhầm thì app
# quét một nơi mà thư về một nơi — bảng Quản lí báo "đang chờ" mãi cho những
# đơn đã có hồi âm, và không có dấu hiệu nào cho thấy sai.
check("nối hộp thư có chốt khớp hồ sơ",
      'store.load(conn_ho_so).get("email")' in _srv3)
_set_khac = _sv.render(every=60, hours=(8, 22), status=[], mail_ready=False,
                       mail_address="", mail_days=30, mail_profile="vin@x.y")
check("nói TRƯỚC phải khớp địa chỉ nào", "vin@x.y" in _set_khac)
check("và điền sẵn để khỏi gõ sai", "value='vin@x.y'" in _set_khac)
check("hồ sơ chưa khai thì chỉ đường đi khai",
      "Hồ sơ chưa khai địa chỉ" in _sv.render(every=60, hours=(8, 22), status=[]))
check("và có ô đặt số ngày đọc lại thư", "name=mail_days" in _set)
_srv2 = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("route xoá đòi xác nhận", '!= "xoa"' in _srv2)

# Thông báo lỗi của imaplib là nguyên văn máy chủ trả lời, và nó đi thẳng vào
# nhật ký — một lần lọt là lọt vĩnh viễn.
check("mật khẩu bị bịt trong thông báo lỗi",
      mail._hide("login failed for hunter2", "hunter2") == "login failed for ***")
check("chưa điền thì nói ngay, không gọi mạng",
      mail.check("", "") == "chưa điền đủ địa chỉ và app password")
# Dán nhầm MẬT KHẨU TÀI KHOẢN là chuyện thường. Bắt bằng hình dạng, TRƯỚC khi
# gửi nó qua mạng — không thì mật khẩu thật đã bay đi rồi mới biết là vô ích.
check("mật khẩu tài khoản bị chặn tại chỗ",
      "không phải app password" in mail.check("a@gmail.com", "Work123@"))
check("và không hề gọi mạng",
      "Gmail từ chối" not in mail.check("a@gmail.com", "Work123@"))
# HÌNH DẠNG ĐÓ LÀ CỦA GOOGLE. Bản cũ áp nó cho MỌI địa chỉ, nên ai dùng
# Outlook / iCloud / hộp thư công ty bị chặn ngay cửa bằng một câu chẳng
# liên quan gì tới lý do thật — mà mật khẩu của họ có thể hoàn toàn đúng.
check("nhà cung cấp khác KHÔNG bị bộ lọc của Google chặn",
      "không phải app password" not in mail.check("a@outlook.com", "Work123@"))
check("app password đúng hình dạng thì cho qua vòng kiểm hình dạng",
      "không phải app password" not in mail.check.__doc__ or
      bool(mail.APP_PASSWORD.fullmatch("abcdefghijklmnop")))
check("Google hiện theo nhóm 4 — bỏ dấu cách vẫn nhận",
      bool(mail.APP_PASSWORD.fullmatch("abcd efgh ijkl mnop".replace(" ", ""))))
# Thứ đem đi KIỂM phải đúng bằng thứ đem đi ĐĂNG NHẬP. Route bỏ dấu cách ngay
# lúc lưu; nếu không, check() so chuỗi đã bỏ cách còn login() gửi chuỗi có cách.
_srv = (Path(__file__).resolve().parent.parent
        / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("lưu app password thì bỏ dấu cách", '.replace(" ", "")' in _srv)

print("\n[xếp loại thư — đo trên tiêu đề thư thật]")
# Bản cũ đạt 10/13. Ba ca hụt, và ca hụt nặng nhất là THƯ TỪ CHỐI rơi xuống
# "other": needs_you=0 nên thư không bao giờ hiện ra, bảng báo "đang chờ" mãi
# cho một lần nộp đã chết.
MAIL_CASES = [
    (board.SENT,      "Thank you for applying to Man Group",       "We have received your application."),
    (board.SENT,      "We've received your application",            "Your application is with our team."),
    (board.SENT,      "Application received — Quantitative Analyst", "Thanks for your interest."),
    (board.INTERVIEW, "Invitation to interview — Point72",          "Thank you for applying. We'd like to meet."),
    (board.INTERVIEW, "Interview invitation",                       "Thank you for applying to IMC."),
    (board.INTERVIEW, "We'd like to invite you for an interview",   "Thanks for applying."),
    (board.INTERVIEW, "Next steps: online assessment",              "Please complete the HackerRank test."),
    (board.INTERVIEW, "Let's schedule a call",                      "Are you free next week?"),
    (board.REJECTED,  "Your application to IMC",                    "Unfortunately we will not be progressing."),
    (board.REJECTED,  "Update on your application",                 "We have decided not to move forward at this time."),
    (board.REJECTED,  "Thank you for your interest in Jane Street", "We won't be taking your application further."),
    (board.REJECTED,  "Application update",                         "You have not been successful on this occasion."),
    (board.REJECTED,  "Re: Quantitative Analyst",                   "We are unable to offer you a position."),
    (board.OFFER,     "Offer of employment — Prima",                "We are delighted to offer you the role."),
    ("other",         "Your Amazon order has shipped",              "Track your parcel"),
    ("other",         "LinkedIn: 5 new jobs for you",               "Jobs matching your profile"),
    ("other",         "Your monthly statement is ready",            "Barclays"),
    ("other",         "Newsletter: quant careers this week",        "Top stories"),
]
for want, subject, snippet in MAIL_CASES:
    got = sort.kind({"subject": subject, "snippet": snippet,
                     "from_name": "", "from_addr": "x@y.z"})
    check(f"{want:<9} {subject[:40]}", got == want)
# Thư mời phỏng vấn gần như luôn mở đầu bằng "thank you for applying" — luật
# mời PHẢI xét trước luật xác nhận, không thì thư quan trọng nhất bị hạ cấp.
_names = [name for name, _ in sort.RULES]
check("xét kết cục mạnh trước", _names.index(board.INTERVIEW) < _names.index(board.SENT))
check("từ chối xét trước xác nhận", _names.index(board.REJECTED) < _names.index(board.SENT))

print("\n[thư dựng lại quá khứ — MỌI kết cục, không riêng thư xác nhận]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    from jobbot.track import mail as _mail, scan as _scan
    conn = db.connect()
    board.add(conn, "Prima", "Quantitative Analyst", stage=board.DRAFT)

    def _m(sub, snip, name, addr):
        return {"msg_id": f"<{abs(hash(sub))}@x>", "from_addr": addr,
                "from_name": name, "subject": sub, "snippet": snip,
                "received_at": "2026-09-09T10:00:00+00:00"}

    _mail.fetch = lambda *a, **k: [
        _m("Thank you for applying to Prima", "We have received your application.",
           "Prima", "no-reply@jobs.lever.co"),
        _m("Interview invitation — Jane Street", "Thank you for applying. Let's schedule a call.",
           "Jane Street", "recruiting@janestreet.com"),
        _m("Your Amazon order has shipped", "Track your parcel", "Amazon", "ship@amazon.co.uk"),
    ]
    _mail.account = lambda: ("x@y.z", "pw")
    got = _scan.run(conn)
    check("đọc hết thư", got["seen"] == 3)
    # LỖI ĐÃ SỬA: chỉ thư xác nhận mới dựng lại dòng, nên thư mời phỏng vấn từ
    # công ty chưa có dòng thì Vin bấm Nhận và KHÔNG có gì xảy ra.
    rows = {r["company"]: r for r in board.all(conn)}
    check("thư mời phỏng vấn dựng ra dòng mới", "Jane Street" in rows)
    check("và dựng ở ĐÚNG chặng, không ép về 'đã nộp'",
          rows.get("Jane Street", {}).get("stage") == board.INTERVIEW)
    check("thư mua hàng KHÔNG đẻ ra dòng nào", "Amazon" not in rows)
    # dòng nháp gặp thư xác nhận -> đề xuất chuyển sang đã nộp
    moves = {p["company"]: p["kind"] for p in _scan.proposals(conn)}
    check("nháp + thư xác nhận -> đề xuất 'đã nộp'", moves.get("Prima") == board.SENT)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[máy điền, Vin bấm Gửi]")
# Luật CŨ ở đây là "chỉ mở trang, không điền". Đã đổi có chủ ý: máy điền phần
# chứng minh được, còn cú bấm Gửi thì không tồn tại trong đường code nào —
# ranh giới nằm ở `apply/run.py`, và `tests/test_apply.py` canh nó.
server = (Path(__file__).resolve().parent.parent
          / "src/jobbot/dashboard/server.py").read_text()
apply_block = server[server.index('if path == "/api/apply"'):
                     server.index('if path == "/api/track/state"')]
check("nút Nộp chạy phần điền", "_start_apply" in apply_block)
check("và ghi một dòng vào bảng", "board.add" in apply_block)
check("dùng CHUNG một nguồn tên PDF", "cv_pdf_for" in apply_block)
check("không mở trình duyệt mặc định nữa", "webbrowser" not in apply_block)
for danger in ("Input.dispatchKeyEvent", "form.submit", "click()", "Page.navigate"):
    check(f"không có {danger}", danger not in apply_block)
check("và ghi một dòng vào bảng", "board.add" in apply_block)

print("\n[TÊN CÔNG TY: chữ trước, người gửi sau — đo trên hộp thư thật]")
# 56 thư có kết cục trong 60 ngày. Lỗi nặng nhất: thư MỜI PHỎNG VẤN — dòng
# quan trọng nhất cả bảng — mang tên "GoHire", một hãng phần mềm tuyển dụng.
from jobbot.track.sort import company_of as _co

def _t(sub, frm="", name="", snip=""):
    return _co({"subject": sub, "from_addr": frm, "from_name": name,
                "snippet": snip})

check("thư qua hãng phần mềm -> lấy tên trong TIÊU ĐỀ",
      _t("Kappa Lab Interview", "mail@gohire-messaging.com", "GoHire",
         "Thank you for applying to Kappa Lab.") == "Kappa Lab")
check("Workable không che mất công ty thật",
      _t("Thanks for applying to Flowdesk", "noreply@candidates.workablemail.com",
         "Workable") == "Flowdesk")
# Công ty nằm sau chữ `at` CUỐI CÙNG; phần trước là vai trò.
check("LinkedIn: lấy sau chữ `at`, không lấy chức danh",
      _t("Your application to Quantitative Researcher at Durlston Partners",
         "jobs-noreply@linkedin.com", "LinkedIn") == "Durlston Partners")
check("tiêu đề xuống dòng vẫn đọc được",
      _t("Your application to Junior Quant\n Researcher at Anson McCade",
         "jobs-noreply@linkedin.com", "LinkedIn") == "Anson McCade")
# Chức danh KHÔNG được thành tên công ty khi câu không có `at` tách đôi.
check("không có `at` mà bắt trúng chức danh -> KHÔNG đoán",
      _t("Great news, we've received your application for Quantitative "
         "Trading Analyst", "no-reply@mavensecurities.com") == "Maven"
      or _t("Great news, we've received your application for Quantitative "
            "Trading Analyst", "no-reply@mavensecurities.com") == "Mavensecurities")
# Tên người gửi vẫn được dùng khi chính nó là công ty — Ashby, SmartRecruiters
# gửi hộ nhưng đặt tên công ty vào ô From.
check("hãng gửi hộ mà ô From là công ty -> vẫn lấy",
      _t("Thank you|Consultant", "no-reply@smartrecruiters.com", "Ayming") == "Ayming")
check("bóc đuôi chức năng còn mỗi từ chung -> KHÔNG phải tên",
      _t("We have received your application", "no-reply@ashbyhq.com",
         "Talent Acquisition") == "")
# `st.griddynamics.net` -> "Griddynamics", KHÔNG phải "St". Lấy nhãn đầu là
# lấy tên máy chủ; đo trên hộp thư thật nó từng cho ra một công ty tên "GD".
_gd = _t("Your application for Python Quantitative Developer",
         "notification@st.griddynamics.net", "GD Notification")
check("tên miền lấy nhãn TRƯỚC TLD, không phải nhãn đầu",
      _gd == "Griddynamics")
check("và không phải mẩu còn lại của tên người gửi", _gd not in ("St", "GD"))
check("cả một CÂU thì không phải tên công ty",
      _t("Job Opportunity - from mcgregorboyall Thank you for your application",
         "noreply@broadbean.net") == "")
# Dịch vụ công không phải việc làm.
from jobbot.track.sort import KHONG_PHAI_VIEC as _kpv
check("thư dịch vụ công bị loại khỏi bảng việc làm",
      bool(_kpv.search("no-reply@notifications.service.gov.uk")))

print("\n[THƯ MÁY KHÔNG ĐỌC ĐƯỢC: không hứa hiểu hết, hứa KHÔNG MẤT lá nào]")
# Bảng mẫu cách diễn đạt không bao giờ đủ. Đo trên hộp thư thật: thư từ chối
# của Maven ("Sorry, it's not quite a match") và thư xác nhận của Trading 212
# ("Your application is in") đều rơi vào `other` và biến mất không dấu vết.
import sqlite3 as _sq3
from jobbot.core import db as _dbK
from jobbot.track import scan as _scK, board as _bdK
_ck = _dbK.connect(":memory:")
_app = _bdK.add(_ck, "Maven", "Quant Analyst", origin="mail")
_thu = {"msg_id": "m1", "from_addr": "no-reply@mavensecurities.com",
        "from_name": "", "subject": "Sorry, it's not quite a match",
        "received_at": "2026-09-09T00:00:00+00:00",
        "snippet": "we've decided not to progress"}
check("thư máy không xếp được vẫn là 'other'", _scK.sort.kind(_thu) == "other")
_scK.store(_ck, _thu, "other", "Maven", _app)
_mu = _scK.kho_hieu(_ck)
check("nhưng nó KHÔNG biến mất — hiện ra để người dùng xếp", len(_mu) == 1)
check("và chỉ rõ nó thuộc lần nộp nào", _mu[0]["company"] == "Maven")
# Thư 'other' KHÔNG thuộc lần nộp nào thì không quấy rầy.
_scK.store(_ck, {**_thu, "msg_id": "m2", "subject": "Sale 50%"},
           "other", "", None)
check("thư lạ không thuộc lần nộp nào -> không hỏi", len(_scK.kho_hieu(_ck)) == 1)
# Người dùng xếp một cái là trạng thái đổi ngay, không hỏi lại lần hai.
check("xếp xong -> đổi trạng thái", _scK.xep(_ck, _mu[0]["id"], "rejected"))
check("và dòng về đúng chặng",
      [r for r in _bdK.all(_ck) if r["id"] == _app][0]["stage"] == "rejected")
check("xếp rồi thì thôi hỏi", not _scK.kho_hieu(_ck))
check("loại lạ thì từ chối", not _scK.xep(_ck, _mu[0]["id"], "lung tung"))
_ck.close()

print("\n[bảng Quản lí: datasheet — ô tìm, tag lọc, bấm mở chi tiết]")
from jobbot.dashboard.views import track as _tkD

def _r(**kw):
    d = dict(id=1, stage="applied", company="Kappa Lab", role="Quant Dev",
             days=20, event_days=None, last_event="", silent=False, cv_file="",
             posting_id=None, url="", score=0, song="im", im_ngay=20,
             so_thu=1, ho_tra_loi=False, nguon="", ai_nop="tự nộp trước đây",
             origin="mail", co_cv=False)
    d.update(kw); return d

_h = _tkD.render(rows=[_r()], asks=[], counts={"total": 1}, mail_ready=False,
                 mail_address="", thu={1: []}, loc={})
check("có ô tìm như bên Search", "class=jfind" in _h)
for _ma in ("ng=", "ai=", "tt=", "cv="):
    check(f"có hàng lọc {_ma[:-1]}", f"/track?{_ma}" in _h or f"&{_ma}" in _h)
check("mỗi dòng bấm mở được, không cần JavaScript", "<details class='trow" in _h)

# LỌC PHẢI THẬT SỰ LỌC, không phải vẽ ra cho đẹp.
_hai = [_r(id=1, company="A", origin="mail", nguon="linkedin", song="im"),
        _r(id=2, company="B", origin="apply", nguon="board", song="nong")]
_loc = _tkD.render(rows=_hai, asks=[], counts={}, mail_ready=False,
                   mail_address="", thu={}, loc={"ng": "board"})
check("lọc theo nguồn -> chỉ còn dòng khớp",
      ">B<" in _loc and ">A<" not in _loc)
_loc2 = _tkD.render(rows=_hai, asks=[], counts={}, mail_ready=False,
                    mail_address="", thu={}, loc={"ai": "mail"})
check("lọc theo AI NỘP -> chỉ còn dòng khớp",
      ">A<" in _loc2 and ">B<" not in _loc2)
_loc3 = _tkD.render(rows=_hai, asks=[], counts={}, mail_ready=False,
                    mail_address="", thu={}, loc={"q": "zzz"})
check("tìm không ra thì NÓI RA, không trả bảng trống câm",
      "không dòng nào lọt lưới lọc" in _loc3)

# CHI TIẾT: thư, bản CV, tin gốc — và nói thẳng khi không có.
_ct = _tkD.render(rows=[_r(posting_id=9, nguon="linkedin", co_cv=True,
                           url="https://x/y")],
                  asks=[], counts={}, mail_ready=False, mail_address="",
                  thu={1: [dict(id=5, subject="Interview", snippet="hi",
                                kind="interview", received_at="2026-08-24",
                                from_addr="a@b.c")]}, loc={})
check("mở ra thấy thư đã nhận", "1 thư đã nhận" in _ct and "Interview" in _ct)
check("và đường tới bản CV", "/jobs/9/cv?tu=/track" in _ct)
check("và đường tới tin gốc", "/jobs/9?tu=/track" in _ct)
_trong = _tkD.render(rows=[_r()], asks=[], counts={}, mail_ready=False,
                     mail_address="", thu={1: []}, loc={})
check("nộp ngoài app thì NÓI THẲNG vì sao trống",
      "nộp ngoài app" in _trong and "chưa lá thư nào" in _trong)

print("\n[máy bó tay thì giao lại cho NGƯỜI, đừng để lần nộp đó rơi]")
# GIAO Ở QUEUE, không ở bảng: đây là VIỆC PHẢI LÀM, mà bảng chỉ chứa fact.
from jobbot.dashboard.views import trackcho as _qT
_hang = [_r(origin="tay", posting_id=9, url="https://li/job/1")]
_tay = _qT.render(rows=_hang, asks=[], mu=[])
check("có ô riêng cho tin máy không nộp được",
      "the machine cannot apply for you" in _tay)
check("đưa ĐƯỜNG NỘP để tự làm", "https://li/job/1" in _tay)
check("và đường TẢI BẢN CV", "/api/cv/pdf" in _tay)
check("nói rõ làm xong thì bấm gì", "Scan mail" in _tay)
_bang = _tkD.render(rows=_hang, asks=[], counts={}, mail_ready=False,
                    mail_address="", thu={1: []}, loc={})
check("và bảng KHÔNG ôm việc đó nữa", "máy không nộp hộ được" not in _bang)
# Cờ riêng, không dò chữ trong câu mô tả — câu chữ sửa một lần là nhãn chết.
from jobbot.apply.run import Report as _Rep
check("cờ 'phải tự làm' là TRƯỜNG riêng, không phải chuỗi trong note",
      "tu_lam" in _Rep.__dataclass_fields__)

print("\n[ba chỗ chắp vá đã vá lại]")
# 1. THANH MASTER: đủ số đo đã xin, và TRƯỢT tách khỏi IM LẶNG.
_bar = _tkD.render(rows=[_r()], asks=[], counts={}, mail_ready=False,
                   mail_address="", thu={}, loc={},
                   stage={"da_nop": 9, "di_tiep": 1, "truot": 2, "cho_ban": 3,
                          "hang_doi": 12, "state": "x"})
for _s in ("đã nộp", "đi tiếp", "trượt", "chờ bạn"):
    check(f"thanh có số «{_s}»", f">{_s}<" in _bar or _s in _bar)
# Trượt là họ ĐÃ NÓI, im lặng là họ CHƯA NÓI GÌ — gộp là mất phân biệt duy
# nhất giữa "đã chết" và "chưa biết".
check("TRƯỢT tách khỏi IM LẶNG", "trượt" in _bar)
check("có nút Nộp trên thanh", "/api/track/nop-tiep" in _bar)
check("và nút đó nói còn bao nhiêu tin đáng nộp", "12 tin đáng nộp" in _bar)

# 4. BẢNG KIỂU EXCEL: có hàng tiêu đề, mỗi cột một nhãn.
check("bảng có hàng tiêu đề cột", "class=thead" in _bar)
for _c in ("công ty", "vị trí", "nguồn", "ai nộp", "lần chạm cuối",
           "thư", "bản CV", "trạng thái"):
    check(f"có nhãn cột «{_c}»", f">{_c}<" in _bar)
check("công ty và vị trí là HAI cột, không dồn một ô",
      "class=c1" in _bar and "class=c2" in _bar)
# Hàng tiêu đề và từng dòng phải dùng CHUNG một lưới cột, nếu không chúng lệch.
_cssT = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
check("tiêu đề và dòng dùng chung một khai báo cột",
      "--cot:" in _cssT and _cssT.count("grid-template-columns:var(--cot)") == 2)

print("\n[việc CHƯA CHỐT ĐƯỢC ở màn riêng, không đè lên bảng đã sạch]")
from jobbot.dashboard.views import trackcho as _qD
_orphan = [dict(id=7, subject="Update on your application", snippet="…",
                kind="rejected", received_at="2026-09-01", company_guess="",
                app_id=None, company=None, role=None, stage=None)]
_mu1 = [dict(id=8, company="Maven", company_guess="", subject="Sorry",
             snippet="not quite a match")]
_q = _qD.render(rows=[_r(id=3, company="Kappa Lab")], asks=_orphan, mu=_mu1,
                stage={"cho_ban": 2})
_sach = _tkD.render(rows=[_r(id=3, company="Kappa Lab")], asks=_orphan, mu=_mu1,
                    counts={}, mail_ready=False, mail_address="", thu={},
                    loc={}, stage={"cho_ban": 2})
# HAI NHỊP KHÁC NHAU: bảng là thứ liếc mỗi ngày, hàng chờ là thứ ngồi dọn một
# lần rồi trống. Trộn lại thì 16 thẻ thư đẩy ô tìm xuống dưới một màn hình.
check("thẻ thư KHÔNG còn nằm trên tab Quản lí", "class=askrow" not in _sach)
check("mà nằm ở màn hàng chờ", _q.count("class=askrow") == 2)
check("có nút Queue dẫn sang đó", "href='/track/queue'" in _sach)
check("nút nói rõ còn mấy việc", ">Queue 2<" in _sach)
check("hết việc thì nút không bịa ra số",
      ">Queue<" in _tkD.render(rows=[_r()], asks=[], counts={}, thu={}, loc={},
                               mail_ready=False, mail_address="",
                               stage={"cho_ban": 0}))
check("màn hàng chờ có đường về bảng", "href='/track'" in _q)
# Rỗng ĐƯỢC, và đó là điểm của cả màn: bảng thì không bao giờ trống.
check("hàng chờ rỗng thì nói thẳng là xong",
      "Nothing is waiting on you" in _qD.render(rows=[], asks=[], mu=[]))
# Tên module KHÔNG được là `queue`: server.py đã `import queue` của thư viện
# chuẩn và luồng SSE bắt `queue.Empty`. Đè lên nhau = màn hình đứng im.
import queue as _stdq
check("không đè tên `queue` của thư viện chuẩn", hasattr(_stdq, "Empty"))

# 6. THƯ CÓ KẾT CỤC MÀ KHÔNG BIẾT CỦA AI: phải GÁN được, không chỉ Bỏ qua.
_ga = _q
check("thư không rõ của ai -> có ô CHỌN lần nộp", "data-ganfor='7'" in _ga)
check("và liệt kê đúng mấy dòng đang có", "Kappa Lab" in _ga)
check("không còn chỉ mỗi nút Bỏ qua", "chưa khớp dòng nào" not in _ga)
# Gán xong thì trạng thái đổi luôn, không hỏi lại lần hai.
_cg = _dbK.connect(":memory:")
_a2 = _bdK.add(_cg, "Kappa Lab", "Quant", origin="mail")
_scK.store(_cg, {"msg_id": "z1", "from_addr": "x@y.z", "from_name": "",
                 "subject": "Update", "received_at": "2026-09-01T00:00:00+00:00",
                 "snippet": ""}, "rejected", "", None)
_mid = _cg.execute("SELECT id FROM message WHERE msg_id='z1'").fetchone()[0]
check("gán được", _scK.gan(_cg, _mid, _a2))
check("và dòng về đúng chặng",
      [r for r in _bdK.all(_cg) if r["id"] == _a2][0]["stage"] == "rejected")
check("dòng lạ thì từ chối", not _scK.gan(_cg, _mid, 9999))
_cg.close()

print("\n[mốc IM LẶNG: quá N ngày thì coi như trượt, và N xoay được]")
from jobbot.core import prefs as _pf
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

def _truoc(n):
    return (_dt.now(_tz.utc) - _td(days=n)).isoformat()

_cn = _dbK.connect(":memory:")
check("mặc định 20 ngày, đúng con số bạn chọn", _pf.DEFAULTS[_pf.IM_QUA] == "20")
check("board đọc mốc từ tuỳ chọn", _bdK.nguong(_cn) == 20)

# Một dòng im 25 ngày và một dòng im 5 ngày. Mốc trượt qua giữa chúng.
_im = _bdK.add(_cn, "Im Lâu", "Quant", applied_at=_truoc(25))
_moi = _bdK.add(_cn, "Vừa Nộp", "Quant", applied_at=_truoc(5))

def _song(app_id):
    return [r for r in _bdK.all(_cn) if r["id"] == app_id][0]["song"]

check("mốc 20: im 25 ngày -> coi như trượt", _song(_im) == _bdK.SONG_IM)
check("mốc 20: im 5 ngày -> còn trong cửa sổ", _song(_moi) == _bdK.SONG_CHO)
_pf.put(_cn, _pf.IM_QUA, "30")
check("nới lên 30 -> dòng 25 ngày SỐNG LẠI", _song(_im) == _bdK.SONG_CHO)
_pf.put(_cn, _pf.IM_QUA, "10")
check("siết xuống 10 -> cả hai vẫn đúng phía",
      _song(_im) == _bdK.SONG_IM and _song(_moi) == _bdK.SONG_CHO)
# LỜI HỨA MẠNH NHẤT của cái núm này: nó là PHÉP SUY, không ghi xuống. Ghi
# xuống là đường một chiều, và thư về sau 31 ngày sẽ đâm vào một dòng đã đóng.
check("KHÔNG ghi vào bảng: chặng vẫn nguyên",
      _cn.execute("SELECT stage FROM application WHERE id=?",
                  (_im,)).fetchone()[0] == _bdK.SENT)
_pf.put(_cn, _pf.IM_QUA, "45")
check("nâng hẳn lên 45 -> về đúng chỗ cũ, không mất dòng nào",
      _song(_im) == _bdK.SONG_CHO and len(_bdK.all(_cn)) == 2)
# Giá trị rác không được làm chết bảng — mọi dòng phải vẫn vẽ ra được.
_pf.put(_cn, _pf.IM_QUA, "lung tung")
check("mốc hỏng thì về mặc định, không nổ", _bdK.nguong(_cn) == 20)
_pf.put(_cn, _pf.IM_QUA, "20")

# ĐANG PHỎNG VẤN THÌ KHÔNG BAO GIỜ "coi như trượt". Một lời mời 25 ngày trước
# chưa ai nhắc lại là chuyện ĐÁNG LO NHẤT bảng, không phải chuyện đã xong.
_pv = _bdK.add(_cn, "Kappa Lab", "Quant", applied_at=_truoc(25),
               stage=_bdK.INTERVIEW)
check("dòng đang phỏng vấn im lâu vẫn là 'đang nói chuyện'",
      _song(_pv) == _bdK.SONG_NONG)

print("\n[số đo cho cái núm: đặt mốc này thì ĐÓNG NHẦM mấy lá]")
# Câu hỏi thật của núm không phải "họ trả lời trong bao lâu" mà "mốc này đóng
# oan mấy dòng" — và nó có đáp án chính xác: mỗi quãng im ĐÃ BỊ PHÁ VỠ là một
# lần mốc-bằng-quãng-ấy đã sai.
_cp = _dbK.connect(":memory:")
_ap = _bdK.add(_cp, "Maven", "Quant", applied_at=_truoc(40))
_scK.store(_cp, {"msg_id": "p1", "from_addr": "a@maven.com", "from_name": "",
                 "subject": "Sorry", "received_at": _truoc(22), "snippet": ""},
           "rejected", "", _ap)
_do = _bdK.im_da_pha(_cp)
check(f"đo được quãng im rồi CÓ THƯ VỀ — ra {_do['lau']} ngày", _do["lau"] == 18)
check("và nói được đó là ai", _do["ai"] == "Maven")
# Đây chính là chỗ bản cũ đo nhầm: `im_ngay` là quãng im ĐANG KÉO DÀI (22
# ngày kể từ lá cuối), không phải quãng thư đã về sau đó (18).
check("KHÔNG lấy nhầm 'lần chạm cuối cách đây bao lâu'", _do["lau"] != 22)
check("mốc 20 không đóng oan lá nào",
      sum(1 for k in _do["khoang"] if k >= 20) == 0)
check("mốc 14 thì đóng oan đúng lá đó",
      sum(1 for k in _do["khoang"] if k >= 14) == 1)
_cp.close()

print("\n[núm hiện ra đúng: năm mức, tích cái đang dùng, khai giá từng mức]")
_adj = _tkD.adjust({}, 20, {"tra_loi": 9, "tong": 37, "lau": 18, "ai": "Maven",
                            "so": 58, "khoang": [3, 14, 18]})
for _m in ("10", "14", "20", "30", "45"):
    check(f"có mức {_m} ngày", f"im_qua:{_m}'" in _adj)
check("mức đang dùng có dấu tích", "✓ 20 ngày" in _adj)
check("mức khác thì không tích", "✓ 30 ngày" not in _adj)
check("khai thẳng cái giá: mốc 10 đóng oan 2 lá", "đóng oan 2" in _adj)
check("mốc 20 không đóng oan thì không bịa ra số", "đóng oan 0" not in _adj)
check("nói rõ số đo lấy từ đâu", "18</b> ngày (Maven)" in _adj)
check("và nói rõ nó KHÔNG ghi vào bảng", "PHÉP SUY, không ghi vào bảng" in _adj)
check("ba công tắc nguồn vẫn còn", _adj.count("data-post='/api/track/num'") == 8)
# Số đếm được PHẢI hiện trên mặt nút, không giấu trong tooltip: rê chuột từng
# nút mới biết mình đánh đổi gì thì coi như không có thông tin.
check("cái giá in ra mặt nút, không chỉ nằm trong tooltip",
      "class=nham" in _adj)
_cssN = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
check("và nó có CSS thật, không phải lớp chết", ".nham{" in _cssN)

print("\n[bảng và thanh nói CÙNG một con số]")
_r20 = _tkD.render(rows=[dict(id=1, stage=_bdK.SENT, company="Im Lâu", role="",
                             days=25, event_days=None, last_event="",
                             silent=True, cv_file="", posting_id=None, url="",
                             score=0, song="im", im_ngay=25, so_thu=1,
                             ho_tra_loi=False)],
                   asks=[], counts={}, mail_ready=False, mail_address="",
                   thu={}, loc={},
                   stage={"nguong": 20, "do": {"lau": 18}, "truot": 1,
                          "di_tiep": 0, "da_nop": 1, "cho_ban": 0})
check("nhóm gọi thẳng tên kết cục", "Coi như trượt" in _r20)
check("nhưng không nói dối: họ CHƯA nói gì", "họ CHƯA nói gì" in _r20)
check("bảng dùng đúng mốc đang đặt, không hằng số cũ", "quá 20 ngày" in _r20)
check("và đúng số đo thật", "từng có thư về là 18 ngày" in _r20)
# Thanh chỉ có chỗ cho một số "trượt". Gộp 2 lời từ chối thật với 32 phép suy
# mà không nói ra thì người đọc tưởng 34 công ty đã nói không.
from jobbot.dashboard import live as _lvK
_st = _lvK.track_stage(_cn)
check("dòng trạng thái tách 'họ từ chối' khỏi 'coi như trượt'",
      "họ từ chối" in _st.get("state", "") and "coi như trượt" in _st.get("state", ""))
check(f"thanh đếm cả hai vào TRƯỢT — ra {_st.get('truot')}", _st.get("truot") == 1)
check("mốc đang dùng đi kèm để bảng vẽ theo", _st.get("nguong") == 20)
_cn.close()

print("\n[BẢNG CHỈ CÓ FACT — không một nút nào sửa được gì]")
_rs = [_r(id=i, company=f"C{i}", stage=st, origin=og, posting_id=i, url="u")
       for i, (st, og) in enumerate(
           ((_bdK.DRAFT, "auto"), (_bdK.SENT, "mail"),
            (_bdK.INTERVIEW, "apply"), (_bdK.REJECTED, "tay"),
            (_bdK.OFFER, "manual")), start=1)]
_ban = _tkD.render(rows=_rs, asks=[], counts={}, mail_ready=True,
                   mail_address="a@b.c", thu={}, loc={},
                   stage={"nguong": 20, "do": {"lau": 18}})
# Đủ MỌI chặng và MỌI kiểu nộp trong một lượt vẽ: nút sót lại thường là nút
# của đúng một chặng hiếm, và vẽ mỗi chặng "đã nộp" thì bài test xanh oan.
_ruot = _ban[_ban.index("<div class=tboard>"):]
for _duong in ("/api/track/state", "/api/apply/send", "/api/track/drop",
               "/api/cv/pdf"):
    check(f"bảng không còn nút {_duong}", _duong not in _ruot)
check("bảng không còn nút POST nào", "data-post" not in _ruot)
check("cũng không còn ô nhập nào", "<input" not in _ruot and "<select" not in _ruot)
# Đường LINK thì được ở lại — xem không phải sửa.
check("nhưng vẫn mở được bản CV để XEM", "/jobs/" in _ruot)
# Và mấy nút đó phải CÒN SỐNG ở Queue, không phải bị vứt đi.
_hq2 = _qT.render(rows=_rs, asks=[], mu=[], doi="2")
for _duong in ("/api/apply/send", "/api/track/drop", "/api/track/state"):
    check(f"Queue nhận lại {_duong}", _duong in _hq2)
check("chọn dòng nào thì hiện chặng đi tiếp của DÒNG ĐÓ",
      "data-arg='2:interview'" in _hq2)
check("chưa chọn thì không bày nút đổi nào",
      "data-arg='2:interview'" not in _qT.render(rows=_rs, asks=[], mu=[]))
check("chặng đã là kết cục thì nói thẳng, không bày nút chết",
      "nowhere further to go" in _qT.render(rows=_rs, asks=[], mu=[], doi="5"))

print("\n[HUY HIỆU PHẢI NÓI CÙNG CÂU VỚI NHÓM]")
def _rim(im, stage=_bdK.SENT, song="im"):
    return _tkD.render(
        rows=[_r(id=1, company="Marlin Selection", stage=stage, song=song,
                 im_ngay=im, days=im, so_thu=1, ho_tra_loi=False)],
        asks=[], counts={}, mail_ready=False, mail_address="", thu={}, loc={},
        stage={"nguong": 20, "do": {"lau": 18}})
_q21 = _rim(21)
# Đây đúng là chỗ đã sai: dòng im 21 ngày nằm dưới tiêu đề "Coi như trượt"
# mà huy hiệu vẫn xanh "đã nộp". Hai câu trái nhau trên cùng một dòng.
# Bắt đúng cái huy hiệu, không dò chữ trong cả trang: "coi như trượt" còn
# nằm ở chip lọc, và dò cả trang là bài test xanh oan.
import re as _reP
def _huy(html):
    return _reP.findall(r"<span class='pill ([a-z]+)'[^>]*>([^<]*)", html)
check("dòng quá mốc: huy hiệu nói 'coi như trượt'",
      _huy(_q21) == [("suy", "coi như trượt")])
# Nhưng không được giả là họ từ chối — "từ chối" là họ ĐÃ NÓI.
check("không mượn lớp của huy hiệu thật", "pill rejected" not in _q21)
check("nói rõ đây là suy ra, và nới mốc thì mở lại",
      "họ chưa nói gì" in _q21 and "Nới mốc" in _q21)
check("nhắc đúng con số mốc đang đặt", "quá 20 ngày" in _q21)
_q5 = _rim(5, song="cho")
check("dòng còn trong cửa sổ vẫn là huy hiệu thật",
      _huy(_q5) == [("applied", "applied")])
_qtu = _rim(30, stage=_bdK.REJECTED, song="xong")
check("họ ĐÃ nói từ chối thì vẫn là huy hiệu thật",
      _huy(_qtu) == [("rejected", "từ chối")])
_cssP = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
check("và hai loại huy hiệu KHÁC MẶT thật, không chỉ khác chữ",
      ".pill.suy{" in _cssP and "dashed" in _cssP.split(".pill.suy{")[1][:90])

print("\n[hàng tiêu đề KHÔNG đóng băng]")
_hd = _cssP[_cssP.index(".thead{"):]
_hd = _hd[:_hd.index("}")]
check("không position:sticky", "sticky" not in _hd)
check("cũng không position:fixed", "fixed" not in _hd)

print("\n[CỘT KHÔNG THỂ LỆCH — không track nào co theo ruột ô]")
_css = (Path(__file__).resolve().parent.parent
        / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
_cot = _css[_css.index("--cot:"):]
_cot = _cot[:_cot.index("}")]
# ĐÂY LÀ LỖI ĐÃ XẢY RA THẬT, không phải lo xa: cột cuối khai `auto`, ô tiêu
# đề cuối rỗng nên rộng 0, ô dữ liệu cuối có hai nút nên rộng 110 — hai cột
# `fr` chia phần thừa lệch nhau đúng 110px và cả bảng trôi.
for _xau in ("auto", "min-content", "max-content", "fit-content"):
    check(f"lưới cột không dùng «{_xau}»", _xau not in _cot)
# Thiếu một track thì cột cuối rơi ra ngoài lưới và bảng lệch y như cũ — đếm
# cho chắc, đừng tin mắt.
_track = _cot.split(":", 1)[1].split()
check(f"số track ({len(_track)}) đúng bằng số nhãn cột ({len(_tkD.COT)})",
      len(_track) == len(_tkD.COT))
check("tiêu đề và dòng vẫn dùng chung một khai báo",
      _css.count("grid-template-columns:var(--cot)") == 2)
check("bảng không còn cột hành động", "\"\"" not in str(_tkD.COT))

print("\n[MỐC THỜI GIAN — chuẩn UTC lúc GHI, nên so chuỗi = so giờ]")
from datetime import datetime as _dtz, timezone as _tzz
# Ba chỗ trong app so mốc thời gian bằng SO CHUỖI: scan.settle (thư cũ có đè
# trạng thái mới không), board.all (max() tìm lần chạm cuối), ORDER BY. So
# chuỗi trên ISO KHÁC múi giờ là sai — và đo trên hộp thư thật, 200/1.046 lá
# mang múi giờ khác UTC. Sửa tại NGUỒN GHI thì cả ba chỗ đúng cùng lúc.
_thu_my = _dtz(2026, 9, 14, 1, 30, tzinfo=_tzz(__import__('datetime').timedelta(hours=-4)))
_utc = mail._utc(_thu_my)
check(f"ghi xong luôn ở UTC ({_utc})", _utc.endswith("+00:00"))
check("và đúng thời điểm", _dtz.fromisoformat(_utc) == _thu_my)
check("thư không ghi múi giờ thì coi là UTC",
      mail._utc(_dtz(2026, 9, 14, 2, 0)).endswith("+00:00"))
check("rỗng thì trả rỗng, không nổ", mail._utc(None) == "")
# Sau khi chuẩn hoá, SO CHUỖI mới cho cùng đáp án với SO GIỜ.
_bang = "2026-09-14T02:00:00+00:00"
check("thư mới hơn thì so chuỗi cũng ra mới hơn", _utc > _bang)
# Di trú phải vá được dòng CŨ, và không được đụng dòng đã đúng.
_cm = _dbK.connect(":memory:")
_cm.execute("INSERT INTO message (msg_id, from_addr, subject, received_at,"
            " snippet, kind) VALUES ('z','a@b.c','s','2026-09-14T01:30:00-04:00','','other')")
_cm.commit()
from jobbot.core import db as _dbm
for _sql in _dbm.MIGRATIONS[21:]:
    _cm.executescript(_sql)
_ra = _cm.execute("SELECT received_at FROM message").fetchone()[0]
check(f"di trú đổi dòng cũ sang UTC (ra {_ra})",
      _ra == "2026-09-14T05:30:00+00:00")
_cm.close()

print("\n[TUỲ CHỌN ĐÃ CHẾT — xoá khỏi DB, không để nằm đó nói dối]")
# Ba khoá của một bản dựng CV cũ. Mã đọc chúng bị xoá từ lâu mà HÀNG VẪN NẰM
# TRONG DB — đo thật trên máy đang chạy: cả ba còn đó. Mở bảng pref ra đọc
# thì chúng nói dối rằng có ba cái nút đâu đó đang điều khiển chúng.
_CHET = ("cv_bo_cuc", "cv_giong", "cv_giu_rui_ro")
_cp = _dbK.connect(":memory:")
for _k in _CHET + ("title_vocab", "autorun"):
    _cp.execute("INSERT OR REPLACE INTO pref (key, value) VALUES (?, 'x')", (_k,))
_cp.commit()
_cp.executescript(_dbm.MIGRATIONS[22])
_con = {r[0] for r in _cp.execute("SELECT key FROM pref")}
for _k in _CHET:
    check(f"di trú xoá «{_k}»", _k not in _con)
# XOÁ ĐÍCH DANH. Quét sạch "mọi khoá không có trong DEFAULTS" là xoá luôn
# title_vocab — 60 chức danh người dùng tự gõ.
check("và KHÔNG đụng title_vocab", "title_vocab" in _con)
check("cũng không đụng khoá thường", "autorun" in _con)
_cp.close()
# Không chỗ nào trong mã còn ghi ba khoá đó nữa — nếu còn, di trú chỉ dọn
# được một lần rồi chúng mọc lại.
# TRỪ core/db.py: chính di trú phải gọi tên ba khoá đó để xoá chúng.
_nguon = "\n".join(
    _p.read_text(encoding="utf-8")
    for _p in sorted((Path(__file__).resolve().parent.parent / "src").rglob("*.py"))
    if _p.name != "db.py")
for _k in _CHET:
    check(f"và mã nguồn không còn ghi «{_k}» ở đâu", _k not in _nguon)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
