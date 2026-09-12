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

HOST = "imap.gmail.com"
PORT = 993
SINCE_DAYS = 30
MAX_MESSAGES = 400          # trần cứng, để một hộp thư to không treo vòng quét
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
    if not APP_PASSWORD.fullmatch(password.replace(" ", "")):
        return ("đây không phải app password. App password là 16 chữ cái "
                "thường, không số, không ký tự đặc biệt. Lấy ở "
                "myaccount.google.com/apppasswords sau khi bật xác minh 2 bước.")
    try:
        box = imaplib.IMAP4_SSL(HOST, PORT)
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
            return ("Gmail từ chối. Nhớ là app password 16 ký tự, KHÔNG phải "
                    "mật khẩu tài khoản — Gmail đã ngắt IMAP bằng mật khẩu "
                    "tài khoản từ 2022.")
        return why[:160]
    except OSError as exc:
        return f"không nối được tới {HOST}: {_hide(str(exc), password)[:100]}"
    return ""


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
        return re.sub(r"\s+", " ", text).strip()[:SNIPPET]
    return ""


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

    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
    box = imaplib.IMAP4_SSL(HOST, PORT)
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
        ids = (data[0] or b"").split()[-limit:]

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
                "received_at": when.isoformat(timespec="seconds") if when else "",
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
