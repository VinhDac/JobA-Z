"""Telegram — báo về điện thoại, và nhận lệnh từ xa.

Máy treo ở nhà 24/7. Thông báo của hệ điều hành (notify.py) hiện trên chính
cái máy đó, nên với trạm trực nó vô dụng: không ai đứng đấy mà nhìn.

VÌ SAO TELEGRAM, không phải thứ khác:

  · Bot API là HTTPS + JSON, nên `urllib.request` của thư viện chuẩn là đủ.
    Không cài gói nào — đúng luật không-phụ-thuộc của cả app.
  · `getUpdates` là LONG POLLING: máy ở nhà chỉ gọi RA ngoài. Không mở cổng
    router, không cần IP tĩnh, không ngrok. Mọi cách khác (webhook, dựng
    server công khai) đều đòi mở một đường ĐI VÀO nhà người dùng.

ĐÃ LOẠI, và lý do:
  · Gmail tự gửi cho mình — hộp thư đang bị khoá CHỈ ĐỌC bằng bốn ràng buộc
    trong code (track/mail.py). Gửi được thư là phá cái khoá đó. Đổi một
    tiện lợi nhỏ lấy ranh giới an toàn lớn nhất của app: không đáng.
  · Push APNs — phải có tài khoản Apple Developer trả phí.

BA CHỐT AN TOÀN, và cả ba đều là chốt CỨNG:

  1. BOT TELEGRAM AI CŨNG NHẮN ĐƯỢC. Biết tên bot là nhắn được. Nên mọi tin
     đến phải qua `duoc_phep()`: sai chat_id là bỏ và ghi nhật ký. Không có
     chốt này thì người lạ đọc được cả đường đi nước bước tìm việc, và bật
     tắt được máy ở nhà.
  2. TOKEN LÀ BÍ MẬT — nằm trong config/config.toml (chmod 600, đã
     gitignore). Không vào DB, không vào nhật ký, không vào HTML.
  3. RANH GIỚI "MÁY KHÔNG BẤM GỬI" GIỮ NGUYÊN QUA TELEGRAM. Không có lệnh
     nộp đơn từ xa, ở bất kỳ mức điều khiển nào. Cú bấm Gửi vẫn là của người
     dùng, trước mặt cái form.

KHÔNG BAO GIỜ NÉM LỖI RA NGOÀI. Hàm ở đây chạy trong luồng nền; một ngoại lệ
thoát ra là giết vòng chạy 24/7, và app im lặng thôi làm việc.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org"
MUC = "telegram"                 # tên mục trong config.toml

# Chờ tối đa mỗi lượt long-poll. 25 giây: đủ dài để không gọi dồn, đủ ngắn để
# dưới mọi thời hạn chờ của proxy trên đường (thường 30-60 giây).
CHO = 25
HET_GIO = CHO + 10


# --- CẤU HÌNH ------------------------------------------------------------

def cau_hinh() -> dict:
    """{token, chat_id} từ config.toml. Đọc hỏng thì rỗng, KHÔNG nổ."""
    try:
        from . import config
        return config.section(MUC) or {}
    except Exception:                       # noqa: BLE001
        return {}


def da_noi() -> bool:
    c = cau_hinh()
    return bool(str(c.get("token", "")).strip()
                and str(c.get("chat_id", "")).strip())


def che(token: str) -> str:
    """Token để in ra cho người xem — chỉ còn đuôi. Dùng ở màn Cài đặt.

    Không bao giờ in nguyên token: nó nằm trong HTML thì đọc được bằng View
    Source và bị trình duyệt lưu vào bộ nhớ đệm.
    """
    t = str(token or "").strip()
    return f"…{t[-4:]}" if len(t) > 4 else ("đã lưu" if t else "")


# --- GỬI ĐI ---------------------------------------------------------------

def goi(duong: str, tham: dict, giay: int = 12) -> tuple:
    """Một lượt gọi API -> (dữ liệu, LÝ DO HỎNG).

    Trả cả lý do chứ không chỉ None: nút Test tồn tại để nói HỎNG Ở ĐÂU, mà
    nuốt lý do thì nó chỉ nói được "không gửi được" — đúng cái câu người dùng
    đã tự biết rồi.

    Lý do dịch sang tiếng người ngay tại đây, vì chỉ chỗ này biết mã lỗi của
    Telegram nghĩa là gì: 401 là token sai, 400 + "chat not found" là số chat
    sai. Để người gọi tự đoán từ mã số là bắt họ học API.
    """
    c = cau_hinh()
    token = str(c.get("token", "")).strip()
    if not token:
        return None, "chưa dán token — lấy ở @BotFather trên Telegram"
    url = f"{API}/bot{token}/{duong}"
    data = urllib.parse.urlencode(
        {k: v for k, v in tham.items() if v is not None}).encode()
    try:
        req = urllib.request.Request(url, data=data,
                                     headers={"User-Agent": "jobbot"})
        with urllib.request.urlopen(req, timeout=giay) as r:
            return json.loads(r.read().decode("utf-8", "replace")), ""
    except urllib.error.HTTPError as e:
        than = ""
        try:
            than = json.loads(e.read().decode("utf-8", "replace")).get(
                "description", "")
        except Exception:                   # noqa: BLE001
            pass
        if e.code == 401:
            return None, "token sai hoặc đã bị thu hồi — tạo lại ở @BotFather"
        if e.code in (400, 403) and "chat" in than.lower():
            return None, ("số chat sai, hoặc bạn chưa nhắn câu nào cho bot. "
                          "Nhắn một câu rồi bấm Tìm chat.")
        return None, f"Telegram trả lỗi {e.code}" + (f" — {than[:70]}" if than else "")
    except urllib.error.URLError as e:
        return None, f"không ra được mạng — {str(getattr(e, 'reason', e))[:60]}"
    except Exception as e:                  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:60]}"


def _goi(duong: str, tham: dict, giay: int = 12) -> dict | None:
    """Bản nuốt lỗi, cho mấy chỗ chạy nền — ở đó không ai đọc lý do."""
    return goi(duong, tham, giay)[0]


def gui_chi_tiet(text: str) -> tuple:
    """Gửi và trả (được không, LÝ DO nếu không). Dùng cho nút Test."""
    c = cau_hinh()
    chat = str(c.get("chat_id", "")).strip()
    if not chat:
        return False, ("chưa có số chat — nhắn một câu cho bot rồi bấm "
                       "Tìm chat")
    ra, loi = goi("sendMessage", {"chat_id": chat, "text": str(text)[:4000],
                                  "parse_mode": "HTML",
                                  "disable_web_page_preview": "true"})
    if ra and ra.get("ok"):
        return True, ""
    return False, loi or str((ra or {}).get("description", ""))[:80] or "không rõ vì sao"


def gui(text: str) -> bool:
    """Gửi một tin cho đúng chat đã ghim. Trả False nếu chưa nối hoặc hỏng.

    HTML chứ không Markdown: tên công ty hay có dấu _ và * (ví dụ
    "Susquehanna_UK"), mà Markdown của Telegram thấy chúng là dấu định dạng
    và trả về lỗi 400 cho cả tin. HTML chỉ phải thoát ba ký tự.
    """
    c = cau_hinh()
    chat = str(c.get("chat_id", "")).strip()
    if not chat or not str(text or "").strip():
        return False
    ra = _goi("sendMessage", {"chat_id": chat, "text": text[:4000],
                              "parse_mode": "HTML",
                              "disable_web_page_preview": "true"})
    return bool(ra and ra.get("ok"))


def thoat(text) -> str:
    """Ba ký tự HTML phải thoát. Tên công ty thật có cả ba."""
    return (str(text or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


# --- NHẬN LỆNH ------------------------------------------------------------
#
# BA MỨC ĐIỀU KHIỂN. Người dùng chọn ở Cài đặt · Thông báo, và mỗi mức là một
# mặt tấn công khác nhau — nên mức phải là một con số kiểm được, không phải
# một câu hứa trong tài liệu.
TAT, XEM, DAY_DU = "tat", "xem", "day_du"

MUC_DIEU_KHIEN = {
    TAT: ("Chỉ báo, một chiều",
          "Bot chỉ gửi đi, không nhận lệnh nào. Không có mặt tấn công. Đổi "
          "lại: tối ở ngoài thấy phiên hỏng thì phải về nhà mới sửa được."),
    XEM: ("Xem và bật/tắt phiên",
          "Thêm ba lệnh vô hại: /trangthai, /batphien, /tatphien. Không lệnh "
          "nào đụng vào CV, hồ sơ, hay nộp đơn."),
    DAY_DU: ("Thêm duyệt thư từ xa",
             "Như trên, cộng /thu · /nhan <số> · /boqua <số> để duyệt mấy thư "
             "máy đề xuất đổi trạng thái. Lệnh từ xa bắt đầu GHI vào bảng."),
}

# Lệnh nào cho mức nào. KHÔNG có lệnh nộp đơn ở bất kỳ mức nào — xem chốt 3
# ở đầu file.
LENH_XEM = ("trangthai", "batphien", "tatphien", "giupdo", "start")
LENH_GHI = ("thu", "nhan", "boqua")


def duoc_phep(tin: dict, chat_id: str) -> bool:
    """CHỐT CỨNG: tin này có đúng từ chat đã ghim không.

    Đây là hàng rào duy nhất giữa cái máy ở nhà và bất kỳ ai biết tên bot.
    Nên nó là một hàm riêng, thuần, có bài test — không phải một câu `if`
    nằm lẫn trong vòng lặp.
    """
    if not chat_id:
        return False
    ai = ((tin or {}).get("message") or {}).get("chat") or {}
    return str(ai.get("id", "")) == str(chat_id).strip()


def doc_lenh(tin: dict) -> tuple:
    """(lệnh, tham số) từ một update. Không phải lệnh thì ('', '').

    Nhận cả "/trangthai@ten_bot" — Telegram tự thêm đuôi đó trong nhóm.
    """
    chu = str(((tin or {}).get("message") or {}).get("text", "")).strip()
    if not chu.startswith("/"):
        return "", ""
    dau, _, sau = chu[1:].partition(" ")
    return dau.split("@")[0].lower(), sau.strip()


def cho_phep_lenh(lenh: str, muc: str) -> bool:
    """Mức điều khiển có cho chạy lệnh này không."""
    if muc == TAT or not lenh:
        return False
    if lenh in LENH_XEM:
        return True
    return muc == DAY_DU and lenh in LENH_GHI


def nhan(offset: int) -> tuple:
    """Một lượt long-poll. Trả (danh sách update, offset kế tiếp).

    Hỏng mạng thì trả ([], offset cũ) — vòng ngoài ngủ rồi thử lại, không ai
    phải xử lý ngoại lệ.
    """
    ra = _goi("getUpdates",
              {"offset": offset, "timeout": CHO,
               "allowed_updates": json.dumps(["message"])}, giay=HET_GIO)
    if not ra or not ra.get("ok"):
        return [], offset
    ds = ra.get("result") or []
    if not ds:
        return [], offset
    return ds, max(int(u.get("update_id", 0)) for u in ds) + 1
