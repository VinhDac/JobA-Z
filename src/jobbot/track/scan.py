"""Quét hộp thư một lượt: đọc → xếp loại → khớp → ĐỀ XUẤT.

KHÔNG tự đổi trạng thái. Một thư mở đầu "unfortunately" có thể là từ chối, mà
cũng có thể là câu mở đầu của thư đổi lịch phỏng vấn. Đoán sai mà tự ghi thì
bảng thành sai, và Vin không có cách nào biết là nó đã sai.

Thư dựng lại được QUÁ KHỨ: MỌI thư có kết cục — xác nhận, mời phỏng vấn, từ
chối, nhận việc — đều là bằng chứng một lần đã nộp. Không khớp dòng nào thì đẻ
ra dòng mới ở đúng chặng đó. Đó là lần nộp có thật, chỉ là app chưa biết.

LỖI ĐÃ SỬA: trước đây chỉ thư XÁC NHẬN mới được dựng lại dòng. Một thư mời
phỏng vấn từ công ty app chưa có dòng thì hiện ra "chưa khớp dòng nào", Vin
bấm Nhận và KHÔNG có gì xảy ra — lời mời phỏng vấn biến mất. Mà thư mời còn là
bằng chứng mạnh hơn thư xác nhận. Một luật cho mọi kết cục, không ngoại lệ.
"""

from __future__ import annotations

import sqlite3

from ..core.journal import SEARCH, log as jlog
from . import board, mail, sort


# `needs_you` — ba mức, và mức thứ ba là cả ý tưởng của tầng này:
#     0  không cần bạn
#     1  máy HIỂU và đề xuất đổi trạng thái
#     2  máy KHÔNG HIỂU, mà thư này thuộc về một lần nộp trên bảng
#
# VÌ SAO CẦN MỨC 2. Bảng mẫu cách diễn đạt không bao giờ đủ — đo trên hộp thư
# thật: "Sorry, it's not quite a match" (Maven) và "Your application is in"
# (Trading 212) đều là thư thật, đều rơi vào `other`, và biến mất không dấu
# vết. Đua thêm từ khoá là trò không có điểm dừng.
#
# Nên đổi luật: KHÔNG hứa hiểu mọi lá thư, mà hứa KHÔNG LÁ NÀO BIẾN MẤT. Thư
# máy không hiểu mà khớp một lần nộp thì hiện ra để người dùng xếp — và cái
# họ xếp chính là thứ dạy lại bảng mẫu.
CAN_BAN = 1
KHONG_HIEU = 2


def store(conn: sqlite3.Connection, msg: dict, kind: str,
          company: str, app_id: int | None) -> bool:
    """Ghi một thư. Trả True nếu là thư MỚI."""
    found = conn.execute("SELECT id FROM message WHERE msg_id = ?",
                         (msg["msg_id"],)).fetchone()
    if found:
        return False
    conn.execute(
        "INSERT INTO message (msg_id, from_addr, from_name, subject,"
        " received_at, snippet, kind, company_guess, application_id, needs_you)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (msg["msg_id"], msg["from_addr"], msg["from_name"], msg["subject"],
         msg["received_at"], msg["snippet"], kind, company,
         app_id, _muc(kind, app_id)))
    conn.commit()
    return True


def _muc(kind: str, app_id: int | None) -> int:
    """Thư này cần người dùng tới mức nào — xem lời chú ở CAN_BAN."""
    if kind != "other":
        return CAN_BAN
    return KHONG_HIEU if app_id else 0


def _so_ngay(conn: sqlite3.Connection) -> int:
    """Đọc lại bao nhiêu ngày thư — người dùng chỉnh ở Cài đặt · Gmail."""
    from ..core import prefs
    return prefs.num(conn, prefs.MAIL_DAYS, 1, 365)


def run(conn: sqlite3.Connection, days: int | None = None) -> dict:
    """Một lượt quét. Trả về số đo, không trả về chữ."""
    address, password = mail.account()
    if not address or not password:
        jlog.warn(SEARCH, "chưa nối hộp thư — mở Cài đặt · Gmail để nối")
        return {"ok": False, "why": "chưa nối hộp thư"}

    # Số ngày do NGƯỜI DÙNG đặt, đọc lúc chạy chứ không đóng cứng vào chữ ký
    # hàm: đóng cứng thì đổi trong Cài đặt xong vẫn phải mở lại app mới ăn.
    if days is None:
        days = _so_ngay(conn)
    jlog.progress(SEARCH, f"đọc thư {days} ngày")
    try:
        messages = mail.fetch(address, password, since_days=days)
    except Exception as exc:                 # noqa: BLE001
        jlog.error(SEARCH, f"đọc thư hỏng — {type(exc).__name__}: {exc}")
        return {"ok": False, "why": str(exc)}
    finally:
        jlog.done(SEARCH)

    seen = fresh = made = 0
    for msg in messages:
        seen += 1
        kind = sort.kind(msg)
        company = sort.company_of(msg)
        app_id = sort.match(conn, msg)

        # Không khớp dòng nào mà thư có kết cục = lần nộp app chưa biết.
        # Dựng lại ở ĐÚNG chặng thư nói, đừng ép về "đã nộp": một thư từ chối
        # dựng thành dòng "đang chờ" là bảng sai ngay lúc sinh ra.
        # DỊCH VỤ CÔNG KHÔNG PHẢI VIỆC LÀM. "Your application for a National
        # Insurance number" khớp luật `applied` và đẻ ra một dòng trên bảng
        # theo dõi việc làm — đo trên hộp thư thật.
        if sort.KHONG_PHAI_VIEC.search(msg.get("from_addr") or ""):
            kind, company = "other", ""
        if app_id is None and company and kind in board.STAGES:
            # VỊ TRÍ và TIN GỐC đọc ngay lúc dựng dòng. Không nối thì bảng
            # Quản lí không chỉ ngược về được tin nào và bản CV nào — mà đó
            # chính là chỗ nó nối Search với CV.
            vai_tro = sort.role_of(msg)
            app_id = board.add(conn, company, vai_tro, origin="mail",
                               posting_id=sort.match_posting(conn, company, vai_tro),
                               applied_at=msg["received_at"], stage=kind)
            made += 1

        fresh += store(conn, msg, kind, company, app_id)

    jlog.ok(SEARCH, f"thư: đọc {seen} · mới {fresh} · dựng lại {made} lần nộp")
    return {"ok": True, "seen": seen, "fresh": fresh, "made": made}


def noi_lai(conn: sqlite3.Connection) -> dict:
    """Nối lại MỌI dòng đã có với tin trong kho và với vị trí đọc từ thư.

    Chạy lại được nhiều lần: chỉ điền chỗ còn trống, không đè thứ người dùng
    đã sửa. Cần có vì 37 dòng đầu tiên dựng ra khi máy chưa biết đọc vị trí.
    """
    noi = ten_vai = 0
    for a in conn.execute("SELECT id, company, role, posting_id FROM application"
                          ).fetchall():
        vai = a["role"] or ""
        if not vai:
            r = conn.execute(
                "SELECT subject, snippet FROM message WHERE application_id = ?"
                " ORDER BY received_at", (a["id"],)).fetchall()
            for m in r:
                vai = sort.role_of(dict(m))
                if vai:
                    conn.execute("UPDATE application SET role = ? WHERE id = ?",
                                 (vai, a["id"]))
                    ten_vai += 1
                    break
        if not a["posting_id"]:
            pid = sort.match_posting(conn, a["company"], vai)
            if pid:
                conn.execute("UPDATE application SET posting_id = ? WHERE id = ?",
                             (pid, a["id"]))
                noi += 1
    conn.commit()
    return {"noi_tin": noi, "them_vai_tro": ten_vai}


def kho_hieu(conn: sqlite3.Connection) -> list[dict]:
    """Thư máy KHÔNG xếp được, mà lại thuộc về một lần nộp trên bảng.

    Đây là chỗ chặn cuối: không hứa hiểu mọi cách viết, chỉ hứa không lá nào
    biến mất. Người dùng xếp một cái là trạng thái đổi ngay.
    """
    return [dict(r) for r in conn.execute(
        "SELECT m.id, m.subject, m.snippet, m.received_at, m.from_addr,"
        " m.company_guess, a.id AS app_id, a.company, a.role, a.stage"
        " FROM message m JOIN application a ON a.id = m.application_id"
        " WHERE m.needs_you = ? ORDER BY m.received_at DESC", (KHONG_HIEU,))]


def xep(conn: sqlite3.Connection, message_id: int, kind: str) -> bool:
    """Người dùng tự xếp loại một lá thư máy không hiểu.

    Ghi lại `kind` rồi đổi trạng thái luôn — người dùng đã đọc thư và đã
    quyết, hỏi lại lần nữa là bắt họ bấm hai lần cho một việc.
    """
    if kind not in board.STAGES:
        return False
    row = conn.execute("SELECT subject, application_id FROM message WHERE id = ?",
                       (message_id,)).fetchone()
    if row is None or not row["application_id"]:
        return False
    conn.execute("UPDATE message SET kind = ?, needs_you = 0 WHERE id = ?",
                 (kind, message_id))
    conn.commit()
    board.set_stage(conn, int(row["application_id"]), kind,
                    (row["subject"] or "")[:90])
    jlog.ok(SEARCH, f"bạn xếp một thư máy không hiểu -> {kind}")
    return True


def gan(conn: sqlite3.Connection, message_id: int, app_id: int) -> bool:
    """Người dùng chỉ tay: lá thư này thuộc lần nộp NÀO.

    NỬA CÒN THIẾU của lời hứa "không lá nào biến mất". Máy đọc được kết cục
    của lá thư nhưng không đoán ra công ty — đo trên hộp thư thật có 3 lá như
    thế, và trước đây chúng chỉ có đúng một nút: Bỏ qua. Thấy mà không làm gì
    được thì cũng là mất, chỉ là mất một cách ồn ào hơn.
    """
    m = conn.execute("SELECT kind, subject FROM message WHERE id = ?",
                     (message_id,)).fetchone()
    a = conn.execute("SELECT id FROM application WHERE id = ?", (app_id,)).fetchone()
    if m is None or a is None:
        return False
    conn.execute("UPDATE message SET application_id = ?, needs_you = ?"
                 " WHERE id = ?", (app_id, CAN_BAN, message_id))
    conn.commit()
    if m["kind"] in board.STAGES:
        board.set_stage(conn, app_id, m["kind"], (m["subject"] or "")[:90])
        conn.execute("UPDATE message SET needs_you = 0 WHERE id = ?", (message_id,))
        conn.commit()
    jlog.ok(SEARCH, f"gán một thư vào lần nộp #{app_id}")
    return True


def proposals(conn: sqlite3.Connection) -> list[dict]:
    """Thư đang ĐỀ XUẤT đổi trạng thái — Vin bấm mới đổi.

    Chỉ đề xuất khi trạng thái mới KHÁC trạng thái đang có; một thư xác nhận
    cho một dòng đã ở 'đã nộp' thì không có gì để hỏi.
    """
    out = []
    for r in conn.execute(
            "SELECT m.id, m.subject, m.snippet, m.kind, m.received_at,"
            " m.company_guess, a.id AS app_id, a.company, a.role, a.stage"
            " FROM message m LEFT JOIN application a ON a.id = m.application_id"
            " WHERE m.needs_you = ? ORDER BY m.received_at DESC", (CAN_BAN,)):
        row = dict(r)
        if row["app_id"] and row["kind"] == row["stage"]:
            continue                       # đã đúng trạng thái, không hỏi lại
        out.append(row)
    return out


def settle(conn: sqlite3.Connection, message_id: int, accept: bool) -> None:
    """Vin trả lời một đề xuất. Nhận thì đổi trạng thái, bỏ thì im luôn.

    Thư CŨ không được đè trạng thái MỚI. Man Group gửi "thank you for
    applying" ngày 1 rồi "unfortunately" ngày 20; Vin nhận thư từ chối trước,
    xong nhận nốt thư xác nhận cũ — và dòng quay ngược về "đang chờ". Bảng nói
    đơn còn sống trong khi nó đã chết, đúng thứ tệ nhất một bảng theo dõi có
    thể làm.
    """
    row = conn.execute(
        "SELECT m.kind, m.subject, m.received_at, m.application_id,"
        " a.last_event_at FROM message m"
        " LEFT JOIN application a ON a.id = m.application_id"
        " WHERE m.id = ?", (message_id,)).fetchone()
    if row is None:
        return
    stale = bool(row["received_at"] and row["last_event_at"]
                 and row["received_at"] < row["last_event_at"])
    if accept and row["application_id"] and row["kind"] in board.STAGES and not stale:
        board.set_stage(conn, row["application_id"], row["kind"],
                        row["subject"][:90])
    elif accept and stale:
        jlog.warn(SEARCH, f"bỏ qua thư cũ hơn trạng thái đang có — "
                          f"{(row['subject'] or '')[:50]}")
    conn.execute("UPDATE message SET needs_you = 0 WHERE id = ?", (message_id,))
    conn.commit()
