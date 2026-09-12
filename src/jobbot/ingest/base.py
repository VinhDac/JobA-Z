"""Nền chung cho mọi nguồn: kiểu Posting, gọi HTTP, chuẩn hoá chuỗi.

Mỗi nguồn chỉ phải làm đúng một việc: fetch -> trả về list[Posting]. Hết.
Ghi DB, gộp trùng, chấm điểm đều là việc của chỗ khác.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from html import unescape
from dataclasses import dataclass, field
from typing import Any

UA = "jobbot/0.1 (personal job search; contact via local app)"
TIMEOUT = 25


# ---------------------------------------------------------------- HTTP

def get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# ------------------------------------------------------------ chuẩn hoá

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# GIỮ LẠI `+ # /` — chúng là MỘT PHẦN CỦA TÊN, không phải dấu câu.
#
# Bỏ chúng thì "C++" thành "c", và alias `c++` trong vocab không bao giờ khớp
# được nữa. Đo trên kho thật: 208 tin đòi C++, mà CV của Vin CÓ C++ — máy
# không bao giờ nhìn thấy. Cùng lỗi: ci/cd (19 tin), c# (9), kdb+ (3).
#
# Chỉ ba ký tự này, không mở rộng thêm: chúng là hậu tố tên công nghệ. Giữ cả
# dấu chấm thì "python." và "python" thành hai thứ khác nhau.
_PUNCT = re.compile(r"[^a-z0-9+#/ ]+")

# Đuôi công ty — bỏ đi để "Monzo Bank Ltd" và "Monzo Bank" gộp được vào nhau.
_SUFFIX = re.compile(
    r"\b(ltd|limited|llp|plc|inc|incorporated|llc|gmbh|bv|nv|sa|ag|corp|corporation|"
    r"co|company|group|holdings|international|uk|global)\b")


def strip_html(text: str) -> str:
    """Bóc HTML về chữ thuần, GIỮ cấu trúc xuống dòng và gạch đầu dòng.

    LỖI ĐÃ SỬA: trước đây bỏ thẻ TRƯỚC rồi mới giải mã &lt; &gt; — nên thẻ bị
    mã hoá (Greenhouse trả về kiểu này) biến thành thẻ thật sau khi đã bỏ xong,
    và nằm nguyên trong mô tả. Phải giải mã trước, và lặp cho tới khi sạch.
    """
    if not text:
        return ""
    for _ in range(3):                       # nội dung mã hoá lồng nhiều lớp
        before = text
        text = unescape(text)
        if text == before:
            break

    # giữ cấu trúc trước khi xoá thẻ — mất nó là mất luôn danh sách yêu cầu
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*/(p|div|h[1-6]|tr)\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "\n· ", text, flags=re.I)
    text = re.sub(r"<\s*/(ul|ol)\s*>", "\n", text, flags=re.I)
    text = _TAG.sub("", text)
    text = unescape(text)                    # thực thể còn sót trong nội dung

    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def norm(text: str) -> str:
    """Chuẩn hoá để so khớp: thường hoá, bỏ dấu câu, gộp khoảng trắng."""
    return _WS.sub(" ", _PUNCT.sub(" ", (text or "").lower())).strip()


# Đuôi dính liền vào tên, không tách bằng dấu cách: "ocadogroup", "manGroup"
_GLUED = re.compile(r"(group|holdings?|capital|partners?|global|international|"
                    r"technologies|solutions|labs?|ltd|inc|plc)$")


def norm_company(name: str) -> str:
    """Bỏ đuôi pháp lý và đuôi mô tả. 'Monzo Bank Ltd' -> 'monzo bank'.

    Cắt cả đuôi VIẾT LIỀN: Greenhouse trả slug "ocadogroup" còn tin thì ghi
    "Ocado Group" — không cắt thì hai bản của cùng một việc không gộp được.
    """
    out = _WS.sub(" ", _SUFFIX.sub(" ", norm(name))).strip()
    words = out.split()
    if len(words) == 1 and len(words[0]) >= 8:
        trimmed = _GLUED.sub("", words[0])
        if len(trimmed) >= 4:
            return trimmed
    return out


def norm_title(title: str) -> str:
    """Bỏ phần trong ngoặc và đuôi mã tin. 'Analyst (London) - REQ123' -> 'analyst'."""
    title = re.sub(r"\([^)]*\)", " ", title or "")
    title = re.sub(r"\b(req|job|id|ref)[-_ ]?\d+\b", " ", title, flags=re.I)
    return norm(title)


def to_ts(stamp: str) -> int:
    """Đổi mọi kiểu ngày về unix. Không đọc được thì 0.

    Greenhouse/Lever/Ashby trả ISO 8601; Arbeitnow trả unix dạng chuỗi.
    """
    if not stamp:
        return 0
    text = str(stamp).strip()
    if text.isdigit():
        value = int(text)
        return value // 1000 if value > 10_000_000_000 else value    # ms hay s
    try:
        from datetime import datetime, timezone
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except (ValueError, TypeError, OverflowError):
        return 0


# ---------------------------------------------------------------- Posting

@dataclass
class Posting:
    """Một tin, đã chuẩn hoá về cùng hình dạng dù đến từ nguồn nào."""
    source_id: str
    title: str
    company: str
    location: str = ""
    remote: bool = False
    salary: str = ""
    url: str = ""
    posted_at: str = ""
    description: str = ""
    raw_body: str = ""          # NGUYÊN VĂN trước khi bóc HTML — không bao giờ sửa
    payload: dict = field(default_factory=dict)

    def fingerprint(self) -> str:
        """Cùng công ty + cùng chức danh = nhiều khả năng cùng một việc."""
        return f"{norm_company(self.company)}|{norm_title(self.title)}"

    def text(self) -> str:
        """Toàn bộ chữ để tìm từ khoá."""
        return f"{self.title}\n{self.company}\n{self.location}\n{self.description}"
