"""Địa chỉ của lượt chạy đang sống — ghi ra tệp để NGOÀI đọc được.

Vì sao cần: server không còn chạy cố định ở 8765. `serve()` để hệ điều hành
cấp cổng trống, nên cổng đổi theo từng lượt chạy. Mà `start.command` (bấm đúp
để mở) thì đang hỏi đúng 8765 — đo thật: app đang chạy ở 8766 thì bấm đúp
KHÔNG mở nó, mà khởi động một lượt thứ hai đè lên cùng một tệp SQLite.

Tệp phẳng, hai dòng, cố ý:

    http://127.0.0.1:8766/
    54321

Dòng 1 địa chỉ, dòng 2 PID. Shell đọc bằng `head -1` — không cần Python, và
người sửa `start.command` sau này không phải học một định dạng nào.

TỆP CŨ KHÔNG ĐÁNG TIN, và đó là thiết kế chứ không phải thiếu sót. App bị
kill -9 hay mất điện thì không ai kịp xoá tệp. Nên người ĐỌC phải tự kiểm
chứng: hỏi `/api/alive` xem có đúng jobbot đang trả lời không. Chỉ xoá tệp
lúc thoát êm là bẫy — nó làm người đọc tưởng "có tệp nghĩa là đang chạy".
"""

from __future__ import annotations

import os

from .paths import data_dir

TEN = "dang-chay.txt"


def tep():
    return data_dir() / TEN


def ghi(url: str) -> None:
    """Ghi địa chỉ + PID. Hỏng thì im — không đáng làm chết lượt khởi động."""
    try:
        tep().write_text(f"{url}\n{os.getpid()}\n", encoding="utf-8")
    except OSError:
        pass


def doc() -> tuple[str, int] | None:
    """(url, pid) nếu đọc được. KHÔNG hứa là nó còn sống — xem docstring."""
    try:
        dong = tep().read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not dong or not dong[0].startswith("http://127.0.0.1:"):
        return None
    try:
        pid = int(dong[1]) if len(dong) > 1 else 0
    except ValueError:
        pid = 0
    return dong[0].strip(), pid


def xoa() -> None:
    try:
        tep().unlink()
    except OSError:
        pass
