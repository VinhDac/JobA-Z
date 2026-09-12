"""Test bước 5-6: nộp và theo dõi.  python3 tests/test_track.py

Trọng tâm là RÀNG BUỘC, không phải tính năng: hộp thư là thứ Vin quan tâm
nhất, nên "chỉ đọc" phải là điều kiểm được, không phải lời hứa trong tài liệu.
"""

import inspect, os, re, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

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
check("mở hộp thư ở chế độ readonly", "readonly=True" in code)
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
    check("nhưng NÓI RA kết cục cũ", "lần trước" in (_r["last_event"] or ""))
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
check("nối rồi thì hiện nút quét", "/api/track/mail/scan" in _on)
check("nút quét nói đúng số ngày đang đặt", "Quét thư 45 ngày" in _on)

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
      "không phải app password" in mail.check("a@b.c", "Work123@"))
check("và không hề gọi mạng", "Gmail từ chối" not in mail.check("a@b.c", "Work123@"))
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
    check("nhưng NÓI RA kết cục cũ", "lần trước" in (_r["last_event"] or ""))
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
check("nối rồi thì hiện nút quét", "/api/track/mail/scan" in _on)
check("nút quét nói đúng số ngày đang đặt", "Quét thư 45 ngày" in _on)

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
      "không phải app password" in mail.check("a@b.c", "Work123@"))
check("và không hề gọi mạng", "Gmail từ chối" not in mail.check("a@b.c", "Work123@"))
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

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
