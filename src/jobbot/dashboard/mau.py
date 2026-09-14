"""Màu nhấn của cả app — MỘT chỗ khai, đổi được từ Cài đặt.

Trước đây màu xanh lá đóng cứng trong app.css. Đó không phải lựa chọn thiết
kế, chỉ là chưa ai cần đổi; mà màu nhấn là thứ người dùng nhìn cả ngày.

MỘT MÀU GỐC SINH RA CẢ BỘ SÁU. Năm giá trị kia đều là hàm của màu gốc, nên
gõ tay ba chục con số là mời lỗi: một bộ lệch tông thì cả app lệch theo mà
không ai chỉ ra được chỗ sai.

    --acc-rgb   ba thành phần RGB, cho mọi độ trong khác
    --acc       màu nhấn
    --acc-2     đậm hơn — dùng cho gradient và trạng thái bấm
    --acc-ink   chữ ĐẶT TRÊN nền nhấn
    --acc-bg    nền mờ (11%) — ô đang chọn
    --acc-bg-2  nền mờ đậm hơn (20%)

`--acc-rgb` LÀ CÁI QUAN TRỌNG NHẤT, và nó thêm vào sau. Không có nó thì mọi
chỗ cần màu nhấn ở một độ trong khác phải gõ cứng `rgba(85,201,141,.35)` —
đo thật, 12 chỗ viền và nền đã gõ như vậy, nên chọn Tím ra CHỮ TÍM VIỀN XANH.

XANH LÁ GIỮ NGUYÊN GIÁ TRỊ CŨ, không tính lại. Nó là mặc định, và một lần
"dọn dẹp" làm đổi tông xanh của cả app là đổi thứ không ai yêu cầu đổi.

MỌI MÀU PHẢI ĐẠT TƯƠNG PHẢN. Màu nhấn hay nằm trên chữ nhỏ (nhãn tab đang
mở, số trên thanh khúc), nên dưới 4.5:1 là không đọc được ở 10px — và một
màu đẹp mà không đọc được thì nó không phải lựa chọn, nó là cái bẫy. Có bài
test đo thật từng màu trên nền `--panel`.
"""

from __future__ import annotations

# Nền đậm nhất mà màu nhấn phải nằm lên. Cùng giá trị với `--panel` trong
# app.css — đây là chỗ khó đọc nhất, nên đo ở đây là đo trường hợp xấu nhất.
NEN_PANEL = "#212121"
TOI_THIEU = 4.5          # tỉ lệ tương phản WCAG cho chữ thường


def _rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def _nhan(h: str, k: float) -> str:
    return _hex(v * k for v in _rgb(h))


def _sang(h: str) -> float:
    """Độ sáng tương đối (WCAG). Không phải trung bình RGB — mắt người nhạy
    với xanh lá gấp bảy lần xanh dương, lấy trung bình là đo sai hẳn."""
    def kenh(v):
        v /= 255
        return v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
    r, g, b = (kenh(v) for v in _rgb(h))
    return .2126 * r + .7152 * g + .0722 * b


def tuong_phan(a: str, b: str) -> float:
    x, y = sorted((_sang(a), _sang(b)))
    return round((y + .05) / (x + .05), 2)


def _bo(goc: str) -> dict:
    """Màu gốc -> cả bộ năm. Hai hệ số lấy từ chính bộ xanh lá đang chạy:
    `--acc-2` là 0,89 lần màu gốc, `--acc-ink` là 0,19 lần."""
    r, g, b = _rgb(goc)
    return {"--acc-rgb": f"{r},{g},{b}",
            "--acc": goc,
            "--acc-2": _nhan(goc, .89),
            "--acc-ink": _nhan(goc, .19),
            "--acc-bg": f"rgba({r},{g},{b},.11)",
            "--acc-bg-2": f"rgba({r},{g},{b},.20)"}


# Sáu màu, mỗi màu một tính cách rõ ràng — không phải sáu sắc độ của cùng một
# thứ. Ai không muốn màu nào cả thì chọn Thép: nó vẫn là "màu nhấn", chỉ là
# nhấn bằng độ sáng thay vì bằng sắc.
BANG = {
    # XANH LÁ giữ NGUYÊN VĂN giá trị đang chạy trong app.css.
    "la": ("Xanh lá", {"--acc-rgb": "85,201,141",
                       "--acc": "#55C98D", "--acc-2": "#48B37C",
                       "--acc-ink": "#10261B",
                       "--acc-bg": "rgba(85,201,141,.11)",
                       "--acc-bg-2": "rgba(85,201,141,.20)"}),
    "lam": ("Xanh dương", _bo("#63B3F0")),
    "tim": ("Tím", _bo("#A78BFA")),
    "cam": ("Cam", _bo("#E8A15C")),
    "hong": ("Hồng", _bo("#F08BA8")),
    "thep": ("Thép", _bo("#AFB6BF")),
}

MAC_DINH = "la"


def css(ten: str) -> str:
    """Mảnh CSS đè lên :root. Màu mặc định -> RỖNG.

    Trả rỗng cho mặc định là cố ý: app.css vẫn là nguồn sự thật cho bộ xanh
    lá, nên chọn mặc định thì không có gì đè lên nó và không thể lệch tông.
    """
    if ten == MAC_DINH or ten not in BANG:
        return ""
    bo = BANG[ten][1]
    khai = "".join(f"{k}:{v};" for k, v in bo.items())
    return f"/* màu nhấn: {BANG[ten][0]} */\n:root{{{khai}}}\n"


def hop_le(ten: str) -> str:
    return ten if ten in BANG else MAC_DINH
