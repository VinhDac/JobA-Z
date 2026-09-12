"""Thị trường đang ĐÒI kỹ năng nào, đếm trên chính kho tin đang giữ.

Một con số, một mục đích: tab CV hỏi "khối này của tôi chạm được bao nhiêu
tin". Khối 0 tin là khối chiếm chỗ — nó lên CV vì có ô trống, không vì nó
chứng minh được gì.

Trước ở `projects/inventory.py`. Nó chưa bao giờ thuộc về tính năng đó: chỗ
này không biết gì về project, nó chỉ cộng `posting.score_json` lại. Tính năng
personal project bị bỏ (xem docs/changes), phép đếm này ở lại — và ở đúng
tầng, cạnh bộ từ vựng mà nó dùng.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter

from ..ingest.base import norm
from .vocab import alias_hits


def demand(conn: sqlite3.Connection) -> Counter:
    """Kỹ năng nào bao nhiêu TIN đòi.

    Đếm theo TIN, không theo dòng yêu cầu — một tin nhắc 'python' năm lần vẫn
    chỉ là một tin.

    Đọc phần YÊU CẦU đã tách, không đọc toàn văn: toàn văn có cả đoạn giới
    thiệu công ty và đoạn phúc lợi, đọc vào là tin nào cũng đòi mọi thứ.
    """
    dem: Counter = Counter()
    for row in conn.execute(
            "SELECT score_json FROM posting"
            " WHERE kept = 1 AND score_json != ''"):
        try:
            reqs = json.loads(row["score_json"]).get("requirements", [])
        except (TypeError, ValueError):
            continue
        dem.update({h for r in reqs for h in alias_hits(norm(r.get("text", "")))})
    return dem
