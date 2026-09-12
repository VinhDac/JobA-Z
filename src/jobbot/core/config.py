"""Đọc config/config.toml — MỘT chỗ.

Trước đây mỗi module tự mở tệp bằng tomllib. Hai bộ đọc là hai cách hiểu về
cùng một tệp, và chúng trôi xa nhau mà không ai biết — đúng bệnh vừa chữa ở
tầng chấm điểm và tầng dựng CV.

Không có tệp thì trả {} chứ không nổ: app phải chạy được khi Vin chưa cấu
hình gì, chỉ là mấy tính năng cần cấu hình thì tự tắt.
"""

from __future__ import annotations

import re
import tomllib

from pathlib import Path

from .paths import project_root


def _tep(ten: str) -> Path:
    """Đường tới một tệp cấu hình, tính LÚC CHẠY.

    Hằng số ở mức module thì bài test không chuyển hướng được, và nó đã ghi
    thẳng vào config.toml THẬT — để lại địa chỉ giả "a@b.c" và app password
    rỗng trong tệp của Vin ngày 12/09.
    """
    return project_root() / "config" / ten


class _Duong:
    """Cho `config.PATH` vẫn dùng được như một Path, nhưng tính lúc gọi."""

    def __init__(self, ten: str) -> None:
        self._ten = ten

    def __fspath__(self) -> str:
        return str(_tep(self._ten))

    def __getattr__(self, ten: str):
        return getattr(_tep(self._ten), ten)

    def __truediv__(self, khac):
        return _tep(self._ten) / khac

    def __str__(self) -> str:
        return str(_tep(self._ten))


PATH = _Duong("config.toml")


def load() -> dict:
    if not PATH.exists():
        return {}
    try:
        return tomllib.loads(PATH.read_text())
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def section(name: str) -> dict:
    got = load().get(name)
    return got if isinstance(got, dict) else {}


EXAMPLE = _Duong("config.example.toml")
SECRET = 0o600          # chỉ chủ máy đọc được — trong này có app password


def _quote(value: str) -> str:
    """Chuỗi TOML kiểu cơ bản. Escape dấu \\ và " — app password của Google
    không có hai ký tự đó, nhưng luật này không được phụ thuộc vào may mắn."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_value(name: str, key: str, value: str) -> None:
    """Đặt một giá trị trong config.toml, CHỈ đụng đúng dòng đó.

    Không dựng lại cả tệp: config.toml có phần chú thích dài giải thích vì sao
    dùng hộp thư riêng, vì sao app password là chìa khoá toàn quyền. Ghi đè cả
    tệp là xoá mất phần giải thích đó, và người đọc sau sẽ không biết.

    Không dùng thư viện ghi TOML vì stdlib chỉ có bộ ĐỌC (tomllib). Sửa theo
    dòng là đủ cho một tệp cấu hình phẳng, và giữ nguyên mọi thứ khác.
    """
    if not PATH.exists():
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(EXAMPLE.read_text() if EXAMPLE.exists()
                        else f"[{name}]\n")
    lines = PATH.read_text().splitlines()
    head = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    line = re.compile(rf"^\s*{re.escape(key)}\s*=")

    here, target, last = "", -1, -1
    for i, text in enumerate(lines):
        found = head.match(text)
        if found:
            here = found.group(1).strip()
            continue
        if here == name:
            last = i
            if line.match(text):
                target = i
                break

    new = f"{key} = {_quote(value)}"
    if target >= 0:
        lines[target] = new
    elif last >= 0:
        lines.insert(last + 1, new)                  # cuối phần đó
    else:
        lines += ["", f"[{name}]", new]

    PATH.write_text("\n".join(lines).rstrip() + "\n")
    try:
        PATH.chmod(SECRET)
    except OSError:
        pass
