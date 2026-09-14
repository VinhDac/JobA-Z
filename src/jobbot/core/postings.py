"""Lưu và đọc tin tuyển dụng. Bốn tầng tách bạch (design.md §4).

    raw_posting  nguyên văn đã fetch — không đụng vào, fetch lại được
    posting      đã chuẩn hoá — tính lại được từ raw
    source_run   mỗi lần chạy một nguồn: được bao nhiêu, hỏng chỗ nào
    audit        đã làm gì, lúc nào — nguồn của mọi thống kê sau này

Cache nằm ở UNIQUE(source, source_id): tin đã có thì không ghi lại,
nên chạy lại nguồn nhiều lần không sinh rác và không tốn công xử lý.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from ..ingest.base import Posting, to_ts


# MỘT nơi duy nhất nối kiểu Posting với cột trong bảng.
#
# Trước đây câu INSERT viết tay liệt kê tên cột và giá trị ở hai chỗ tách rời,
# nên thêm một trường vào Posting là phải sửa ba nơi, và không có gì báo nếu
# quên. Giờ chỉ sửa bảng này — và test sẽ gãy nếu Posting có trường chưa khai.
FIELD_MAP: dict[str, str] = {
    "title": "title", "company": "company", "location": "location",
    "salary": "salary", "url": "url", "posted_at": "posted_at",
    "description": "description",
}

# Trường của Posting KHÔNG đi thẳng vào bảng posting, kèm lý do
NOT_COLUMNS: dict[str, str] = {
    "source_id": "khoá ở raw_posting",
    "raw_body": "lưu ở raw_posting.body",
    "payload": "lưu ở raw_posting.payload",
    "remote": "phải ép về int, xử lý riêng",
}


def _row_values(source: str, raw_id: int, item: Posting) -> tuple[list[str], list]:
    """Dựng (cột, giá trị) từ FIELD_MAP thay vì viết tay câu INSERT."""
    columns = ["raw_id", "source", "remote", "fingerprint", "posted_ts"]
    values: list = [raw_id, source, int(item.remote), item.fingerprint(),
                    to_ts(item.posted_at)]
    for attr, column in FIELD_MAP.items():
        columns.append(column)
        values.append(getattr(item, attr))
    return columns, values


def xoa_kho(conn: sqlite3.Connection) -> dict:
    """Dọn sạch KHO TIN để quét lại từ đầu. Trả về những gì vừa bỏ đi.

    GIỮ LẠI TIN ĐÃ ĐỘNG TỚI. Tin có đơn (`application`) hay có câu ghim
    (`cv_pick`) là việc người dùng đã làm, không phải thứ máy cào về — xoá nó
    là xoá mất dấu vết một lần nộp, và không quét lại nào lấy lại được.

    KHÁC HẲN nút Xoá bản bên CV. Bản CV dựng lại mất 15 giây; kho tin dựng
    lại mất một lượt quét đầy đủ, có mở Chrome. Nên chốt ở đây phải nói rõ số
    tin sắp mất, chứ không chỉ hỏi "chắc chưa".

    KHÔNG đụng tới: hồ sơ, đơn đã nộp, thư, cài đặt, lưới lọc.
    """
    # LỌC NULL TRONG SUBQUERY. `NOT IN` gặp một NULL thì cả mệnh đề ra NULL
    # chứ không phải TRUE — SQL ba trạng thái, và đây là cái bẫy kinh điển
    # nhất của nó.
    #
    # Đo trên kho thật: 32/37 đơn có posting_id = NULL (mấy đơn dựng lại từ
    # thư, không có tin gốc). Vậy nên câu này xoá ĐÚNG 0 tin — trong khi
    # source_run (204 lượt quét) và cv_build vẫn bị xoá sạch ngay bên dưới.
    # Người dùng bấm "Dọn kho", thấy kho y nguyên, và mất lịch sử quét.
    giu = ("SELECT posting_id FROM application WHERE posting_id IS NOT NULL"
           " UNION SELECT posting_id FROM cv_pick WHERE posting_id IS NOT NULL")
    n = conn.execute(f"SELECT COUNT(*) FROM posting WHERE id NOT IN ({giu})"
                     ).fetchone()[0]
    # raw_posting xoá theo `raw_id` của chính mấy tin sắp bỏ — xoá sạch bảng
    # thì mất luôn nguyên văn của tin đang có đơn.
    conn.execute(
        f"DELETE FROM raw_posting WHERE id IN ("
        f"  SELECT raw_id FROM posting WHERE id NOT IN ({giu}) AND raw_id IS NOT NULL)")
    conn.execute(f"DELETE FROM posting WHERE id NOT IN ({giu})")
    lan = conn.execute("SELECT COUNT(*) FROM source_run").fetchone()[0]
    conn.execute("DELETE FROM source_run")
    # BẢN CV DỰNG TỪ KHO TIN NÀY. Giữ lại là giữ 157 bản nói về 5.000 tin vừa
    # biến mất — xem cv/batch.py.
    ban = conn.execute("SELECT COUNT(*) FROM cv_build").fetchone()[0]
    conn.execute("DELETE FROM cv_build")
    conn.commit()
    con = conn.execute("SELECT COUNT(*) FROM posting").fetchone()[0]
    return {"tin": n, "giu": con, "lan_quet": lan, "ban_cv": ban}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- nhật ký

def log(conn: sqlite3.Connection, kind: str, detail: str = "") -> None:
    conn.execute("INSERT INTO audit (at, kind, detail) VALUES (?,?,?)", (now(), kind, detail))
    conn.commit()


def recent_audit(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT at, kind, detail FROM audit ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


# ---------------------------------------------------------------- ghi tin

# Mô tả ngắn hơn ngần này thì coi như CHƯA đọc được — đọc lại lần sau.
# Cùng ngưỡng với chỗ save_batch quyết định có bổ sung mô tả hay không.
HAVE_DESC = 200


def already_read(conn: sqlite3.Connection, source) -> set[str]:
    """id bên nguồn của những tin ĐÃ có mô tả tử tế.

    Vòng đọc kỹ dùng cái này để BỎ QUA. Không có nó thì mỗi lần quét lại mở
    lại từng trang đã đọc: đo trên máy thật là 194/196 tin LinkedIn đã có mô
    tả, tức 97% công của vòng đọc kỹ là làm lại việc đã làm — và chính chỗ
    thừa đó kéo theo cả chuỗi: 8-16 phút mỗi giờ -> ~4.600 lượt gọi mỗi ngày
    -> bị bóp 40-82% -> phải nghỉ lâu hơn -> phải cắt bớt chức danh đi tìm.

    Tin đọc hỏng (mô tả rỗng) KHÔNG nằm trong đây — lần sau thử lại.
    """
    # Nhận MỘT tên hoặc NHIỀU tên. Thư báo và vòng quét Chrome trỏ tới cùng
    # một trang LinkedIn, chỉ khác đường mang id về — đọc xong ở nguồn này thì
    # nguồn kia không việc gì phải mở lại.
    ten = (source,) if isinstance(source, str) else tuple(source)
    return {r[0] for r in conn.execute(
        "SELECT r.source_id FROM raw_posting r JOIN posting p ON p.raw_id = r.id"
        f" WHERE r.source IN ({','.join('?' * len(ten))})"
        "   AND length(COALESCE(p.description,'')) >= ?",
        (*ten, HAVE_DESC))}


def save_batch(conn: sqlite3.Connection, source: str,
               items: Iterable[Posting]) -> tuple[int, int]:
    """Ghi một lô tin. Trả về (số thấy, số mới).

    Cache chặn tin TRÙNG, KHÔNG chặn việc BỔ SUNG.

    Lỗi đã sửa: trước đây tin đã có thì bỏ qua hoàn toàn — nên vòng quét nhanh
    ghi tin không mô tả, rồi vòng đọc kỹ lấy được mô tả cũng không ghi vào đâu
    được. Giờ: đã có mà đang thiếu mô tả, lần này có -> cập nhật.
    """
    seen = new = 0
    for item in items:
        seen += 1
        cur = conn.execute(
            "INSERT OR IGNORE INTO raw_posting"
            " (source, source_id, url, fetched_at, payload, body) VALUES (?,?,?,?,?,?)",
            (source, item.source_id, item.url, now(),
             json.dumps(item.payload, ensure_ascii=False),
             item.raw_body or item.description),      # nguyên văn, không đụng vào
        )
        if not cur.rowcount:            # đã có
            if item.raw_body:           # lần này có nguyên văn -> lưu nếu đang thiếu
                conn.execute(
                    "UPDATE raw_posting SET body = ? WHERE source = ? AND source_id = ?"
                    "  AND length(COALESCE(body,'')) < 200",
                    (item.raw_body, source, item.source_id))
            if item.description:        # và mô tả đã bóc, nếu đang thiếu
                # Mô tả về muộn thì phán quyết cũ được sinh ra từ CHỖ TRỐNG.
                # Xoá dấu phiên bản để derive() nhận ra tin này đã cũ và phán
                # lại — không xoá thì tin đứng nguyên score=NULL vĩnh viễn.
                conn.execute(
                    "UPDATE posting SET description = ?, salary = COALESCE(NULLIF(?,''), salary),"
                    " posted_at = COALESCE(NULLIF(?,''), posted_at),"
                    " posted_ts = CASE WHEN ? > 0 THEN ? ELSE posted_ts END,"
                    " judged_rules = '', scored_rules = ''"
                    " WHERE raw_id = (SELECT id FROM raw_posting WHERE source=? AND source_id=?)"
                    "   AND length(COALESCE(description,'')) < 200",
                    (item.description, item.salary, item.posted_at,
                     to_ts(item.posted_at), to_ts(item.posted_at),
                     source, item.source_id))
            continue
        raw_id = int(cur.lastrowid)
        columns, values = _row_values(source, raw_id, item)
        marks = ",".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO posting ({','.join(columns)}) VALUES ({marks})", values)
        new += 1
    conn.commit()
    return seen, new


# Hỏng quá tỉ lệ này thì coi như nguồn hỏng, dù có lấy về được vài tin.
FAIL_THRESHOLD = 0.3


def record_run(conn: sqlite3.Connection, source: str, ok: bool,
               fetched: int = 0, new_rows: int = 0, error: str = "",
               attempted: int = 0, failed: int = 0) -> None:
    """Ghi lại một lần chạy nguồn.

    Hỏng quá 30% số tin định đọc thì đánh dấu ok=0 KỂ CẢ khi vẫn lấy được ít
    tin — nguồn đổi giao diện thường hỏng gần hết chứ không hỏng hẳn, và nếu
    chỉ nhìn "có lấy được tin không" thì không bao giờ phát hiện ra.
    """
    if ok and attempted and failed / attempted > FAIL_THRESHOLD:
        ok = False
        error = error or (f"{failed}/{attempted} tin đọc hỏng "
                          f"({failed * 100 // attempted}%) — trang có thể đã đổi")
    conn.execute(
        "INSERT INTO source_run (source, started_at, ok, fetched, new_rows, error,"
        " attempted, failed) VALUES (?,?,?,?,?,?,?,?)",
        (source, now(), int(ok), fetched, new_rows, error, attempted, failed),
    )
    conn.commit()


# ---------------------------------------------------------------- đọc tin

def unjudged(conn: sqlite3.Connection) -> int:
    """Tin đã nạp nhưng vòng lọc chưa chạy qua. Nên luôn bằng 0 sau mỗi lần quét."""
    return int(conn.execute(
        "SELECT COUNT(*) FROM posting WHERE drop_reason = 'not judged yet'").fetchone()[0])


def count(conn: sqlite3.Connection, kept_only: bool = False) -> int:
    sql = "SELECT COUNT(*) FROM posting" + (" WHERE kept = 1" if kept_only else "")
    return int(conn.execute(sql).fetchone()[0])


def count_groups(conn: sqlite3.Connection) -> int:
    return int(conn.execute(
        "SELECT COUNT(DISTINCT COALESCE(group_id, CAST(id AS TEXT)))"
        " FROM posting WHERE kept = 1").fetchone()[0])


def all_postings(conn: sqlite3.Connection, kept_only: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM posting" + (" WHERE kept = 1" if kept_only else "") + " ORDER BY id"
    return conn.execute(sql).fetchall()


def source_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT source, COUNT(*) AS n, SUM(kept) AS kept FROM posting"
        " GROUP BY source ORDER BY n DESC").fetchall()


def last_runs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT source, MAX(started_at) AS at, ok, fetched, new_rows, error,"
        " attempted, failed FROM source_run GROUP BY source ORDER BY source").fetchall()
