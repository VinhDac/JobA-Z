"""Đọc hộp thư việc làm qua IMAP — CHỈ ĐỌC, và ràng buộc nằm trong code.

Vì sao hộp thư RIÊNG chứ không phải hộp chính: app password của Google là chìa
khoá TOÀN QUYỀN — đọc, gửi, xoá, cả hộp thư, vĩnh viễn tới khi thu hồi. Google
không cho tạo loại chỉ-đọc, cũng không giới hạn được theo ngày. Chìa đó nằm
dạng chữ trong config.toml. Đặt nó lên hộp thư chính là đặt sai chỗ; đặt lên
một hộp chỉ chứa thư từ chối việc làm thì mất cũng chẳng sao.

BỐN RÀNG BUỘC, viết thành code chứ không thành lời hứa:

    1. chỉ SELECT chế độ readonly=True — thư không bị đánh dấu đã đọc
    2. KHÔNG có hàm nào gửi, xoá, hay đổi cờ. Không tồn tại thì không gọi nhầm.
    3. chỉ lấy thư trong SINCE_DAYS ngày gần nhất
    4. chỉ lấy TIÊU ĐỀ và mấy dòng đầu — không tải toàn văn, không tải đính kèm

Xem tests/test_track.py: mỗi ràng buộc một bài test.
"""

from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header

# --------------------------------------------------------------- máy chủ thư
#
# GMAIL LÀ MẶC ĐỊNH, KHÔNG PHẢI LÀ LUẬT. Bản cũ đóng cứng `HOST =
# "imap.gmail.com"`, và kèm theo đó là một bộ lọc chỉ nhận app password của
# Google (16 chữ cái thường). Ai dùng Outlook, iCloud, Fastmail hay hộp thư
# công ty thì KHÔNG dùng được khúc quản lí thư — mà lời từ chối họ nhận được
# là "đây không phải app password", một câu chẳng liên quan gì tới lý do thật.
#
# Ba tầng, theo đúng thứ tự đó:
#   1. `host` trong [mail] của config.toml — người dùng nói gì thì nghe nấy
#   2. tên miền của địa chỉ, tra bảng dưới đây
#   3. `imap.<tên miền>` — quy ước phổ biến, và hỏng thì câu lỗi chỉ đúng
#      chỗ phải sửa
MAC_DINH_HOST = "imap.gmail.com"
PORT = 993

NHA_CUNG_CAP = {
    "gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com", "hotmail.com": "outlook.office365.com",
    "hotmail.co.uk": "outlook.office365.com", "live.com": "outlook.office365.com",
    "live.co.uk": "outlook.office365.com", "msn.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com", "yahoo.co.uk": "imap.mail.yahoo.com",
    "ymail.com": "imap.mail.yahoo.com",
    "icloud.com": "imap.mail.me.com", "me.com": "imap.mail.me.com",
    "mac.com": "imap.mail.me.com",
    "fastmail.com": "imap.fastmail.com", "fastmail.fm": "imap.fastmail.com",
    "zoho.com": "imap.zoho.com", "zohomail.com": "imap.zoho.com",
    "aol.com": "imap.aol.com",
    "gmx.com": "imap.gmx.com", "gmx.net": "imap.gmx.net", "gmx.de": "imap.gmx.net",
    "yandex.com": "imap.yandex.com", "yandex.ru": "imap.yandex.ru",
    "mail.com": "imap.mail.com", "hey.com": "imap.hey.com",
}

# Proton KHÔNG nói IMAP ra ngoài Internet — phải qua Proton Mail Bridge chạy
# trên chính máy này, cổng 1143, và cổng đó KHÔNG phải SSL. Đoán bừa một máy
# chủ cho họ là để họ ngồi chờ một lỗi mạng vô nghĩa; nói thẳng thì họ biết
# phải làm gì.
CAN_CAU = {"proton.me", "protonmail.com", "protonmail.ch", "pm.me"}


def ten_mien(address: str) -> str:
    return address.strip().rpartition("@")[2].lower()


def may_chu(address: str = "") -> str:
    """Máy chủ IMAP cho địa chỉ này. Rỗng = phải hỏi người dùng (xem CAN_CAU)."""
    from ..core.config import section
    cfg = section("mail")
    khai = str(cfg.get("host") or "").strip()
    if khai:
        return khai
    mien = ten_mien(address or str(cfg.get("address") or ""))
    if not mien:
        return MAC_DINH_HOST
    if mien in CAN_CAU:
        return ""
    return NHA_CUNG_CAP.get(mien) or f"imap.{mien}"


def cong() -> int:
    """Cổng IMAP. Đổi được để còn nối vào Bridge hay máy chủ công ty."""
    from ..core.config import section
    try:
        return int(str(section("mail").get("port") or PORT))
    except (TypeError, ValueError):
        return PORT


def _chi_cach(mien: str) -> str:
    """Câu chỉ đường khi không đoán được máy chủ — phải NÓI RA phải sửa ở đâu."""
    return (f"không biết máy chủ thư của «{mien}». Mở "
            "config/config.toml, mục [mail], thêm dòng:\n"
            '  host = "imap.ten-nha-cung-cap.com"')

# THỜI HẠN CHỜ CHO MỌI CÚ GỌI IMAP.
#
# Không đặt thì socket chờ VÔ HẠN. Hậu quả không phải "chậm": khúc đọc thư
# chạy trong vòng nền và đang GIỮ KHOÁ của scheduler (`_gate`), nên một lần
# treo là trạm trực đứng im vĩnh viễn — màn hình vẫn báo "đang chạy", không
# vòng nào sau đó chạy được, và không có gì nói ra điều đó. Đúng kiểu hỏng
# câm tệ nhất.
#
# 30 giây: Gmail trả lời trong một hai giây khi mạng bình thường; quá 30 là
# đã hỏng chứ không phải chậm. Mạng chập chờn thì vòng sau chạy lại.
HET_GIO = 30
SINCE_DAYS = 30
# TRẦN CỨNG, để một hộp thư to không treo vòng quét. 400 là quá thấp và nó
# CẮT ÂM THẦM: hộp thư thật có 1.041 thư trong 60 ngày, lấy 400 thư mới nhất
# là chỉ đọc 19 ngày — 41 ngày còn lại không bao giờ tới, và thư mời phỏng
# vấn nằm trong đó. Người dùng bấm "quét 60 ngày" và nhận về 19.
#
# Đắt nhất là lượt fetch, không phải con số này: 0,27 giây mỗi thư.
MAX_MESSAGES = 3000
SNIPPET = 400               # ký tự lấy từ thân thư

# App password của Google: đúng 16 chữ cái thường. Google hiện nó theo nhóm 4
# có dấu cách cho dễ chép, nên bỏ dấu cách trước khi so.
APP_PASSWORD = re.compile(r"[a-z]{16}")


class MailError(RuntimeError):
    pass


def account() -> tuple[str, str]:
    """(địa chỉ, app password) từ config.toml. Chưa điền thì trả rỗng."""
    from ..core.config import section
    cfg = section("mail")          # KHÔNG đặt tên `box` — `box` là hộp thư IMAP
    return (str(cfg.get("address") or "").strip(),
            str(cfg.get("password") or "").strip())


def check(address: str, password: str) -> str:
    """Thử đăng nhập một cái rồi thoát. Rỗng = được, khác rỗng = lý do hỏng.

    Có mặt hàm này vì nếu không, Vin dán mật khẩu xong không biết nó đúng hay
    sai cho tới lần quét đầu tiên — và lúc đó thì lỗi nằm lẫn trong nhật ký.

    KHÔNG bao giờ để mật khẩu lọt vào chuỗi trả về: thông báo lỗi của imaplib
    là nguyên văn máy chủ trả lời, và chuỗi đó đi thẳng vào nhật ký.
    """
    if not address or not password:
        return "chưa điền đủ địa chỉ và app password"
    # Nhận ra mật khẩu TÀI KHOẢN trước khi gửi nó đi đâu cả. App password của
    # Google luôn là 16 chữ cái thường, không số, không ký tự đặc biệt. Dán
    # nhầm mật khẩu tài khoản là chuyện thường, và nếu cứ thử đăng nhập thì
    # mật khẩu thật đã bay qua mạng rồi mới biết là vô ích.
    host = may_chu(address)
    mien = ten_mien(address)
    if not host:
        return (f"{mien} chỉ cho IMAP qua Proton Mail Bridge chạy trên chính "
                "máy này. Cài Bridge, rồi điền host/port của nó vào [mail] "
                "trong config/config.toml.")
    # BỘ LỌC NÀY LÀ CỦA GOOGLE, chỉ áp cho Google. Áp cho mọi người là chặn
    # cửa ngay từ đầu với một câu chẳng liên quan gì tới lý do thật.
    if _la_google(host) and not APP_PASSWORD.fullmatch(password.replace(" ", "")):
        return ("đây không phải app password. App password là 16 chữ cái "
                "thường, không số, không ký tự đặc biệt. Lấy ở "
                "myaccount.google.com/apppasswords sau khi bật xác minh 2 bước.")
    # KHOÁ MẠNG lúc chạy thử — CÙNG một cái công tắc với Telegram. Đặt ở
    # ĐÂY, sau mọi lần kiểm tại chỗ: kiểm hình dạng không tốn gói tin nào,
    # và bài test vẫn phải kiểm được chúng.
    #
    # Không có chốt này thì một bài test gọi check() là mở socket thật ra
    # Internet, mang theo địa chỉ thật. Đúng lớp lỗi đã xảy ra một lần với
    # Telegram: bộ test nhắn tin thật về điện thoại mỗi lần chạy.
    from ..core.tele import khoa_mang
    if khoa_mang():
        return "JOBBOT_OFFLINE — không gọi mạng lúc chạy thử"
    try:
        box = imaplib.IMAP4_SSL(host, cong(), timeout=HET_GIO)
        try:
            box.login(address, password)
            box.select("INBOX", readonly=True)
        finally:
            try:
                box.logout()
            except Exception:            # noqa: BLE001
                pass
    except imaplib.IMAP4.error as exc:
        why = _hide(str(exc), password)
        if "AUTHENTICATIONFAILED" in why or "Invalid credentials" in why:
            if _la_google(host):
                return ("Gmail từ chối. Nhớ là app password 16 ký tự, KHÔNG "
                        "phải mật khẩu tài khoản — Gmail đã ngắt IMAP bằng "
                        "mật khẩu tài khoản từ 2022.")
            return (f"{host} từ chối. Phần lớn nhà cung cấp bắt dùng mật khẩu "
                    "riêng cho ứng dụng, không phải mật khẩu tài khoản — và "
                    "phải bật IMAP trong phần cài đặt hộp thư.")
        return why[:160]
    except OSError as exc:
        doan = not str(_section_host()).strip()
        them = ("\n" + _chi_cach(mien)) if doan and mien not in NHA_CUNG_CAP else ""
        return (f"không nối được tới {host}: "
                f"{_hide(str(exc), password)[:100]}{them}")
    return ""


def _la_google(host: str) -> bool:
    return host.endswith("gmail.com") or host.endswith("googlemail.com")


def _section_host() -> str:
    from ..core.config import section
    return str(section("mail").get("host") or "")


def _hide(text: str, secret: str) -> str:
    """Bịt mật khẩu nếu nó lọt vào thông báo lỗi. Rẻ, và một lần lọt là lọt
    vĩnh viễn vào nhật ký."""
    return text.replace(secret, "***") if secret else text


def _made_id(msg) -> str:
    """Id thay thế cho thư không có Message-ID — băm từ người gửi, tiêu đề,
    ngày. Cùng một lá thư thì cùng một id, dù nó nằm ở vị trí nào."""
    import hashlib

    seed = "|".join(str(msg.get(h) or "") for h in ("From", "Subject", "Date"))
    return "no-id-" + hashlib.sha1(seed.encode("utf-8", "replace")).hexdigest()[:20]


def _utc(when) -> str:
    """Mốc thời gian dạng chuỗi ISO, LUÔN ở UTC. Nhờ vậy so chuỗi = so giờ."""
    if not when:
        return ""
    from datetime import timezone
    if when.tzinfo is None:                 # thư không ghi múi giờ -> coi là UTC
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).isoformat(timespec="seconds")


def _text(raw) -> str:
    out = []
    for part, enc in decode_header(raw or ""):
        out.append(part.decode(enc or "utf-8", "replace")
                   if isinstance(part, bytes) else part)
    return " ".join(out).strip()


def _body(msg) -> str:
    """Mấy dòng đầu của phần chữ. KHÔNG đụng đính kèm."""
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() != "text/plain":
            continue
        if part.get_filename():          # là đính kèm, bỏ qua
            continue
        try:
            body = part.get_payload(decode=True) or b""
        except Exception:                # noqa: BLE001
            continue
        text = body.decode(part.get_content_charset() or "utf-8", "replace")
        got = re.sub(r"\s+", " ", text).strip()
        if got:
            return got[:SNIPPET]
    # KHÔNG CÓ CHỮ TRƠN THÌ BÓC TỪ HTML.
    #
    # Rất nhiều hệ ATS chỉ gửi thân HTML. Đo trên hộp thư thật: 307/1047 lá
    # (29%) có snippet RỖNG, và 296 trong số đó bị xếp là "other" — nghĩa là
    # `sort.kind()` chỉ nhìn được TIÊU ĐỀ. Một thư từ chối có tiêu đề trung
    # tính ("Update on your application") mà thân ghi "unfortunately" thì
    # không có cách nào đọc ra, và lần nộp đó nằm mãi ở "đang chờ".
    return _tu_html(msg)


def _tu_html(msg) -> str:
    """Chữ bóc ra từ thân HTML. Rỗng nếu thư không có phần HTML nào."""
    tho = _html_body(msg)
    if not tho:
        return ""
    from ..ingest.base import strip_html
    return re.sub(r"\s+", " ", strip_html(tho)).strip()[:SNIPPET]


def _html_body(msg) -> str:
    """Thân HTML nguyên văn. Rỗng nếu thư chỉ có chữ trơn."""
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() != "text/html" or part.get_filename():
            continue
        try:
            body = part.get_payload(decode=True) or b""
        except Exception:                    # noqa: BLE001
            continue
        return body.decode(part.get_content_charset() or "utf-8", "replace")
    return ""


def fetch(address: str, password: str, since_days: int = SINCE_DAYS,
          limit: int = MAX_MESSAGES, sender: str = "",
          want_html: bool = False) -> list[dict]:
    """Thư trong `since_days` ngày gần nhất. Không đổi gì trên máy chủ.

    `sender` lọc thẳng trên máy chủ IMAP — rẻ hơn hẳn kéo cả hộp thư về rồi
    lọc bằng Python, và là thứ làm cho nguồn "thư báo việc" khả thi: hộp thư
    của Vin có 381 thư báo lẫn trong 5.513 thư.

    `want_html` chỉ bật khi người gọi THẬT SỰ cần: thân HTML của một thư báo
    là 86 KB, mà vòng quét đơn chỉ cần 400 ký tự chữ trơn.
    """
    if not address or not password:
        raise MailError("chưa điền [mail] address/password trong config.toml")

    from ..core.tele import khoa_mang
    if khoa_mang():
        raise MailError("JOBBOT_OFFLINE — không mở hộp thư lúc chạy thử")

    host = may_chu(address)
    if not host:
        raise MailError(f"{ten_mien(address)} cần Proton Mail Bridge — "
                        "điền host/port của Bridge vào [mail] trong config.toml")

    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
    box = imaplib.IMAP4_SSL(host, cong(), timeout=HET_GIO)
    try:
        box.login(address, password)
        # readonly=True: máy chủ KHÔNG đánh dấu thư đã đọc.
        box.select("INBOX", readonly=True)
        loc = f'(SINCE "{since}"'
        if sender:
            # Escape dấu nháy: chuỗi lọt vào câu lệnh IMAP, không phải SQL,
            # nhưng cùng một luật — chữ người dùng đưa vào thì không được ghép
            # thẳng vào câu lệnh.
            loc += f' FROM "{sender.replace(chr(34), "")}"'
        ok, data = box.search(None, loc + ")")
        if ok != "OK":
            raise MailError(f"tìm thư hỏng: {ok}")
        tat_ca = (data[0] or b"").split()
        ids = tat_ca[-limit:]
        # CẮT THÌ PHẢI NÓI. Lấy `limit` thư MỚI NHẤT nghĩa là bỏ phần cũ hơn,
        # tức bỏ luôn mấy ngày đầu của khoảng người dùng vừa xin. Im lặng ở
        # đây là báo "đã quét 60 ngày" trong khi mới đọc 19.
        if len(tat_ca) > len(ids):
            from ..core.journal import SEARCH, log as jlog
            jlog.warn(SEARCH,
                      f"hộp thư có {len(tat_ca):,} thư trong {since_days} ngày, "
                      f"trần đang là {limit:,} — chỉ đọc {len(ids):,} thư MỚI "
                      f"NHẤT, phần cũ hơn chưa đọc")

        out, broken = [], 0
        for num in ids:
            # MỘT lá thư dị dạng KHÔNG được giết cả vòng quét. Ngày sai định
            # dạng, mã hoá lạ, MIME hỏng — parsedate_to_datetime và
            # decode_header đều ném lỗi được, và một lá như thế làm mất luôn
            # 29 lá còn lại. Thư quảng cáo hỏng thì bỏ; thư từ chối thì không
            # được bỏ vì lá bên cạnh hỏng.
            try:
                # BODY.PEEK: lấy mà KHÔNG đặt cờ \Seen. BODY[] thường thì có.
                ok, chunk = box.fetch(num, "(BODY.PEEK[])")
                if ok != "OK" or not chunk or not isinstance(chunk[0], tuple):
                    continue
                msg = email.message_from_bytes(chunk[0][1])
                addr = email.utils.parseaddr(msg.get("From", ""))
                try:
                    when = email.utils.parsedate_to_datetime(msg.get("Date", "")) \
                        if msg.get("Date") else None
                except (TypeError, ValueError):
                    when = None
            except Exception:                    # noqa: BLE001
                broken += 1
                continue
            out.append({
                # KHÔNG dùng số thứ tự làm id thay thế: số đó đổi mỗi khi hộp
                # thư thêm/bớt thư, nên lần quét sau một lá KHÁC mang cùng
                # "no-id-42" và bị coi là đã đọc rồi — thư từ chối biến mất.
                # Băm từ chính nội dung thì id ổn định theo lá thư.
                "msg_id": msg.get("Message-ID") or _made_id(msg),
                "from_addr": addr[1], "from_name": _text(addr[0]),
                "subject": _text(msg.get("Subject")),
                # CHUẨN HOÁ VỀ UTC NGAY LÚC GHI, không để nguyên múi giờ
                # người gửi.
                #
                # Ba chỗ khác so mốc thời gian bằng SO CHUỖI: scan.settle
                # (thư cũ có đè trạng thái mới không), board.all (max() tìm
                # lần chạm cuối), và ORDER BY received_at. So chuỗi trên ISO
                # khác múi giờ là sai: '...01:30-04:00' (05:30 UTC) đứng
                # TRƯỚC '...02:00+00:00' theo bảng chữ cái, nên một lá mới
                # hơn 3,5 tiếng bị coi là cũ rồi bị bỏ.
                #
                # Đo trên hộp thư thật: 200/1.046 lá mang múi giờ khác UTC.
                # Sửa ở ĐÂY thì cả ba chỗ kia đúng cùng lúc — vá từng chỗ so
                # là phải nhớ mãi, và sẽ có chỗ quên.
                "received_at": _utc(when),
                "snippet": _body(msg),
                **({"html": _html_body(msg)} if want_html else {}),
            })
        if broken:
            from ..core.journal import SEARCH, log as jlog
            jlog.warn(SEARCH, f"bỏ qua {broken} thư đọc không nổi (định dạng lạ)")
        return out
    finally:
        # logout() ném lỗi khi kết nối đã gãy, và imaplib KHÔNG tự đóng socket
        # bên dưới. Quét mỗi giờ, mạng chập chờn, là rò dần file descriptor.
        try:
            box.logout()
        except Exception:                # noqa: BLE001
            pass
        try:
            sock = getattr(box, "sock", None)
            if sock is not None:
                sock.close()
        except Exception:                # noqa: BLE001
            pass
