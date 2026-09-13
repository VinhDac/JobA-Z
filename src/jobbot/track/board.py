"""Bảng theo dõi — một dòng cho một lần nộp.

Một dòng sinh ra khi Vin nộp, và đổi trạng thái khi có thư về. Thư là CẢM
BIẾN, bảng là TRẠNG THÁI — không phải hai tính năng, là một vòng.

`im lặng` KHÔNG lưu thành cột. Nó là phép trừ, tính lúc đọc: đã nộp quá lâu
mà chưa thư nào. Lưu thì phải ngồi cập nhật mỗi ngày, và sẽ có ngày quên —
đúng cách `khoảng trống` ở lưới project.
"""

from __future__ import annotations

import sqlite3

from ..ingest.base import norm

# Năm chặng. Mỗi chặng ứng với một việc Vin làm khác nhau — chặng nào không
# ứng với việc nào thì không được tồn tại.
#
# `draft` sinh ra khi máy mở form và điền hộ. Nó KHÔNG phải "đã nộp": form còn
# vài câu chỉ Vin trả lời được, và cú bấm Gửi là của Vin. Ghi thẳng "đã nộp"
# lúc đó thì bảng nói dối ngay dòng đầu tiên — mà bảng này Vin đọc mỗi ngày.
# Thư xác nhận về sẽ tự đẩy nó sang "đã nộp"; đó đúng là vai trò cảm biến của
# thư, không phải một cơ chế mới.
DRAFT = "draft"
SENT, INTERVIEW, REJECTED, OFFER = "applied", "interview", "rejected", "offer"
STAGES = (DRAFT, SENT, INTERVIEW, REJECTED, OFFER)
STAGE_LABEL = {DRAFT: "đang điền", SENT: "đã nộp", INTERVIEW: "phỏng vấn",
               REJECTED: "từ chối", OFFER: "nhận"}
# Đang chờ KẾT CỤC. Bản nháp không chờ ai cả — nó chờ chính Vin, nên không
# tính vào đây và không bao giờ bị gọi là "im lặng".
OPEN = (SENT, INTERVIEW)

# MẶC ĐỊNH của "quá bao nhiêu ngày im thì coi như trượt". Người dùng xoay
# được (⚟ trên thanh Quản lí — xem core/prefs.IM_QUA); con số ở đây chỉ là
# chỗ dựa khi chưa ai xoay, và khi gọi `all()` mà không truyền gì.
#
# 20, không phải 14: 14 là mốc ĐO ĐƯỢC (lá hồi âm muộn nhất trong hộp thư
# thật về sau đúng 14 ngày), nhưng mốc đo được là mốc của quá khứ — lấy y
# nguyên nó làm hạn chót là không chừa chỗ cho lá thư thứ 38.
SILENT_AFTER = 20


def nguong(conn: sqlite3.Connection) -> int:
    """Số ngày im hiện đang dùng. MỘT chỗ đọc, để bảng và thanh đếm giống nhau.

    Hai chỗ tự đọc là có ngày thanh trên báo "32 trượt" còn bảng dưới xếp 34
    dòng vào nhóm đó, và không ai biết chỗ nào sai.
    """
    from ..core import prefs
    return prefs.num(conn, prefs.IM_QUA, 3, 365)


def _now() -> str:
    from ..core.postings import now
    return now()


def add(conn: sqlite3.Connection, company: str, role: str,
        posting_id: int | None = None, cv_file: str = "",
        origin: str = "manual", applied_at: str = "",
        stage: str = SENT) -> int:
    """Ghi một lần nộp. Nộp lại đúng vai trò đó ở đúng công ty đó thì KHÔNG
    đẻ dòng mới — đó là một lần nộp, không phải hai."""
    key = norm(company)
    found = conn.execute(
        "SELECT id, stage, posting_id FROM application"
        " WHERE company_key = ? AND role = ?", (key, role)).fetchone()
    if found:
        app_id = int(found["id"])
        if cv_file:
            conn.execute("UPDATE application SET cv_file = ? WHERE id = ?",
                         (cv_file, app_id))
        # Dòng dựng từ thư không có số hiệu tin. Không gắn vào thì nút Gửi đơn
        # đi tìm cửa sổ theo posting_id và trả "không có tin gốc".
        if posting_id and not found["posting_id"]:
            conn.execute("UPDATE application SET posting_id = ? WHERE id = ?",
                         (posting_id, app_id))
        # NỘP LẠI nơi từng bị từ chối (công ty mở lại tin) là một lần nộp MỚI.
        # Giữ nguyên chặng cũ thì bảng vẫn ghi "từ chối", nút Gửi đơn không
        # hiện, và đơn Vin vừa điền không bao giờ đi. Kéo về nháp, nhưng NÓI RA
        # kết cục cũ — mất lịch sử cũng là nói dối.
        if stage == DRAFT and found["stage"] in (REJECTED, OFFER):
            conn.execute(
                "UPDATE application SET stage = ?, last_event = ?,"
                " last_event_at = ? WHERE id = ?",
                (DRAFT, f"nộp lại — lần trước: {STAGE_LABEL[found['stage']]}",
                 _now(), app_id))
        conn.commit()
        return app_id
    cur = conn.execute(
        "INSERT INTO application (company, company_key, role, posting_id,"
        " origin, applied_at, stage, cv_file) VALUES (?,?,?,?,?,?,?,?)",
        (company, key, role, posting_id, origin, applied_at or _now(),
         stage if stage in STAGES else SENT, cv_file))
    conn.commit()
    return int(cur.lastrowid)


def set_stage(conn: sqlite3.Connection, app_id: int, stage: str,
              event: str = "") -> None:
    if stage not in STAGES:
        return
    conn.execute(
        "UPDATE application SET stage = ?, last_event_at = ?, last_event = ?"
        " WHERE id = ?",
        (stage, _now(), event or STAGE_LABEL[stage], app_id))
    conn.commit()


SENDING = "sending"          # đang bấm Gửi — chặng TẠM, không hiện thành nhãn


def claim(conn: sqlite3.Connection, app_id: int) -> bool:
    """Giành quyền gửi lá đơn này. Trả True nếu giành được.

    Một câu UPDATE ... WHERE stage = 'draft' là NGUYÊN TỬ: hai cú bấm cách
    nhau hai giây thì chỉ một câu đổi được dòng, câu kia đếm 0. Đọc-rồi-ghi ở
    tầng route thì cả hai cùng thấy 'draft' và cùng đi bấm Submit — hai lá đơn
    giống nhau tới cùng một nhà tuyển dụng.
    """
    cur = conn.execute(
        "UPDATE application SET stage = ? WHERE id = ? AND stage = ?",
        (SENDING, app_id, DRAFT))
    conn.commit()
    return cur.rowcount == 1


def unclaim(conn: sqlite3.Connection, app_id: int) -> None:
    """Trả lại về nháp khi gửi không thành."""
    conn.execute("UPDATE application SET stage = ? WHERE id = ? AND stage = ?",
                 (DRAFT, app_id, SENDING))
    conn.commit()


def drop(conn: sqlite3.Connection, app_id: int) -> bool:
    """Xoá một dòng — CHỈ khi nó còn là bản nháp.

    Mở form rồi đổi ý là chuyện thường, và một dòng nháp bỏ quên làm bẩn bảng.
    Nhưng lần nộp THẬT thì không xoá bằng một cú bấm: đó là lịch sử, và lịch
    sử mất đi thì 30 ngày nhìn lại chẳng còn gì để nhìn.

    Xoá thư trước rồi mới xoá dòng: `message.application_id` không có
    ON DELETE CASCADE nên làm ngược lại là vướng khoá ngoại.
    """
    row = conn.execute("SELECT stage FROM application WHERE id = ?",
                       (app_id,)).fetchone()
    if row is None or row["stage"] != DRAFT:
        return False
    conn.execute("DELETE FROM message WHERE application_id = ?", (app_id,))
    conn.execute("DELETE FROM application WHERE id = ?", (app_id,))
    conn.commit()
    return True


def note(conn: sqlite3.Connection, app_id: int, text: str) -> None:
    conn.execute("UPDATE application SET note = ? WHERE id = ?", (text, app_id))
    conn.commit()


def _days(stamp: str) -> int | None:
    from datetime import datetime, timezone
    if not stamp:
        return None
    try:
        then = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - then).total_seconds() // 86400)


# SỨC SỐNG của một lần nộp — thứ bảng phải trả lời mà `stage` một mình không
# trả lời nổi. "Đã nộp" 40 ngày trước, im lặng, khác hẳn "đã nộp" hôm qua.
SONG_NONG = "nong"        # họ đang nói chuyện với bạn — phỏng vấn, nhận việc
SONG_CHO = "cho"          # còn trong cửa sổ hồi âm
SONG_IM = "im"            # quá cửa sổ mà không một chữ
SONG_XONG = "xong"        # đã có kết cục

# AI NỘP — ba giá trị, và người dùng cần phân biệt rõ cả ba.
#     mail   bạn tự nộp TRƯỚC KHI dùng app; máy dựng lại từ thư
#     apply  bạn nộp qua app
#     tay    máy định nộp mà không nộp được (LinkedIn khoá) — bạn tự làm
AI_NOP = {"mail": "tự nộp trước đây", "apply": "nộp qua app",
          "auto": "máy nộp", "tay": "phải tự nộp tay",
          "manual": "thêm bằng tay"}


def nguon_cua(source: str) -> str:
    """`greenhouse:imc` -> board · `linkedin` -> linkedin · `alert` -> alert.

    MỘT chỗ dịch, dùng chung với tab Search (views/search.FOUND_BY). Dịch ở
    hai chỗ thì có ngày hai tab gọi cùng một tin bằng hai tên nguồn.
    """
    s = (source or "").strip().lower()
    if not s:
        return ""
    return s if s in ("linkedin", "alert") else "board"


def all(conn: sqlite3.Connection, im_qua: int | None = None) -> list[dict]:
    """Cả bảng, kèm SỐ ĐO về thời gian và thư.

    IM LẶNG ĐO TỪ LÁ THƯ CUỐI, KHÔNG TỪ `last_event_at`. `last_event_at` chỉ
    được ghi khi người dùng BẤM NHẬN một đề xuất; nên một công ty đã trả lời
    bốn lá thư mà người dùng chưa bấm thì vẫn bị đếm là "im lặng". Đo trên hộp
    thư thật: bảng báo 35 im lặng trong khi chỉ có 28 — 7 công ty đã trả lời
    bị ghi là im.
    """
    moc = nguong(conn) if im_qua is None else int(im_qua)
    thu = {}
    for r in conn.execute(
            "SELECT application_id, COUNT(*) n, MAX(received_at) cuoi,"
            " MIN(received_at) dau FROM message"
            " WHERE application_id IS NOT NULL GROUP BY application_id"):
        thu[r["application_id"]] = (r["n"], r["cuoi"], r["dau"])

    rows = []
    for r in conn.execute(
            "SELECT a.*, p.url AS url, p.score AS score, p.source AS source_tin,"
            " p.title AS tin_title FROM application a"
            " LEFT JOIN posting p ON p.id = a.posting_id ORDER BY a.id DESC"):
        row = dict(r)
        n, cuoi, dau = thu.get(row["id"], (0, "", ""))
        row["so_thu"] = n
        row["thu_cuoi"] = cuoi or ""
        row["days"] = _days(row["applied_at"])
        row["event_days"] = _days(row["last_event_at"])
        # LẦN CHẠM CUỐI CÙNG = mốc muộn nhất trong ba thứ: lá thư mới nhất,
        # mốc sự kiện người dùng đã xác nhận, và lúc nộp.
        #
        # Thiếu `last_event_at` là sai: người dùng bấm Nhận cho một thư mời
        # phỏng vấn thì ĐÓ LÀ một lần chạm, dù thư đó cũ. Bỏ nó ra thì một
        # dòng đang phỏng vấn vẫn bị đếm là "im lặng".
        row["im_ngay"] = _days(max(
            x for x in (cuoi, row["last_event_at"], row["applied_at"]) if x)
            if any((cuoi, row["last_event_at"], row["applied_at"])) else "")
        row["ho_tra_loi"] = n > 1 or bool(cuoi and dau and cuoi != dau)
        row["silent"] = (row["stage"] in OPEN
                         and (row["im_ngay"] or 0) >= moc)
        if row["stage"] in (INTERVIEW, OFFER):
            row["song"] = SONG_NONG
        elif row["stage"] not in OPEN:
            row["song"] = SONG_XONG
        else:
            row["song"] = SONG_IM if row["silent"] else SONG_CHO
        row["nguon"] = nguon_cua(row.get("source_tin") or "")
        row["ai_nop"] = AI_NOP.get(row.get("origin") or "", row.get("origin") or "")
        row["co_cv"] = bool(row.get("cv_file")) or bool(row.get("posting_id"))
        rows.append(row)
    # Nháp lên đầu: đó là việc đang dở, và việc đang dở phải đập vào mắt.
    rows.sort(key=lambda r: (r["stage"] != DRAFT, r["stage"] not in OPEN,
                             -(r["days"] or 0)))
    return rows


def im_da_pha(conn: sqlite3.Connection) -> dict:
    """Những khoảng IM LẶNG ĐÃ TỪNG BỊ PHÁ VỠ — số đo để chọn mốc cho đúng.

    Câu hỏi thật của cái núm "coi như trượt sau bao nhiêu ngày" không phải
    "họ thường trả lời trong bao lâu". Nó là: ĐẶT MỐC NÀY THÌ TÔI ĐÓNG NHẦM
    MẤY LÁ? Và câu đó có đáp án chính xác trong hộp thư đang có — mỗi lần
    một lá thư về sau một quãng im, quãng đó là một lần mốc-bằng-quãng-ấy
    đã sai.

    Nên hàm này trả về MỌI quãng im đã bị phá vỡ. Mốc M đóng nhầm đúng bằng
    số quãng >= M.

    KHÔNG PHẢI `max(im_ngay)` — đó là cái bảng đang đo nhầm trước đây.
    `im_ngay` là "lần chạm cuối cách đây bao lâu", tức là quãng im ĐANG KÉO
    DÀI và chưa ai phá vỡ; lấy nó làm "thư về muộn nhất" thì trên hộp thư
    thật nó ra 40 ngày trong khi số đúng là 18.
    """
    from datetime import datetime, timezone

    def _moc(x):
        try:
            t = datetime.fromisoformat((x or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t

    thu = {}
    for m in conn.execute("SELECT application_id, received_at FROM message"
                          " WHERE application_id IS NOT NULL"
                          " ORDER BY application_id, received_at"):
        thu.setdefault(m["application_id"], []).append(m["received_at"])

    khoang, ai, lau = [], "", 0
    for a in conn.execute("SELECT id, company, applied_at FROM application"):
        moc = [x for x in [_moc(a["applied_at"])]
               + [_moc(t) for t in thu.get(a["id"], [])] if x]
        for truoc, sau in zip(moc, moc[1:]):
            n = int((sau - truoc).total_seconds() // 86400)
            if n < 0:
                continue
            khoang.append(n)
            if n > lau:
                lau, ai = n, a["company"] or ""
    return {"lau": lau, "ai": ai, "so": len(khoang), "khoang": sorted(khoang)}


def thu_cua(conn: sqlite3.Connection, app_id: int) -> list[dict]:
    """Mọi lá thư của MỘT lần nộp, mới nhất trước. Ruột của thẻ chi tiết."""
    return [dict(r) for r in conn.execute(
        "SELECT id, subject, snippet, kind, received_at, from_addr"
        " FROM message WHERE application_id = ? ORDER BY received_at DESC",
        (app_id,))]


def counts(conn: sqlite3.Connection) -> dict:
    out = {s: 0 for s in STAGES}
    silent = 0
    for row in all(conn):
        out[row["stage"]] = out.get(row["stage"], 0) + 1
        silent += bool(row["silent"])
    out["silent"] = silent
    # "Tổng" là số lần NỘP THẬT. Bản nháp chưa gửi đi đâu cả, đếm vào là tự
    # khen mình.
    out["total"] = sum(out[s] for s in STAGES if s != DRAFT)
    return out
