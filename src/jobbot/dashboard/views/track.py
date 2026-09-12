"""Quản lí — bước 5 và 6. Một dòng cho một lần nộp.

    MÁY ĐIỀN -> sinh ra một dòng "đang điền"
    VIN GỬI  -> thư xác nhận về, dòng đó thành "đã nộp"
    THƯ VỀ   -> đề xuất đổi trạng thái tiếp
    BẢNG     -> mọi dòng, xem và sửa được

Thư là CẢM BIẾN, bảng là TRẠNG THÁI. Không phải hai tính năng, là một vòng.

Máy KHÔNG bấm Gửi. Nó điền phần chứng minh được rồi dừng; ba câu như
sponsorship hay ngày tốt nghiệp là việc của Vin, và cú bấm cuối cũng vậy.
Ranh giới đó nằm trong `apply/run.py` — ở đó không có lệnh bấm Gửi nào.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc

from ...track.board import OPEN, STAGE_LABEL
from . import runtime

NEXT = {"draft": [("applied", "đã gửi tay")],
        "applied": [("interview", "phỏng vấn"), ("rejected", "từ chối")],
        "interview": [("offer", "nhận"), ("rejected", "từ chối")],
        "rejected": [], "offer": []}


def _ask(items: list[dict]) -> str:
    """Dải CẦN VIN: thư về đề xuất đổi trạng thái."""
    if not items:
        return ""
    rows = ""
    for p in items:
        who = p["company"] or p["company_guess"] or "?"
        # Vin nộp ba vai trò ở Point72; thư từ chối đến, máy đề xuất hạ MỘT
        # dòng. Không hiện vai trò thì Vin bấm Nhận mà không biết vừa hạ cái
        # nào.
        job = f" · {p['role'][:38]}" if p.get("role") else ""
        now = STAGE_LABEL.get(p["stage"], "—") if p["stage"] else "chưa có dòng"
        to = STAGE_LABEL.get(p["kind"], p["kind"])
        rows += (
            f"<div class=askrow><div class=askmain>"
            f"<div class=askwho><b>{esc(who)}</b><i>{esc(job)}</i>"
            f"<span class=askmove>{esc(now)} → <b>{esc(to)}</b></span></div>"
            f"<div class=asksub>{esc(p['subject'][:88])}</div>"
            f"<div class=asksnip>{esc((p['snippet'] or '')[:130])}</div></div>"
            f"<div class=askact>"
            + (f"<button class='mbtn tiny apply' data-post='/api/track/mail'"
               f" data-arg='{p['id']}:yes'>Nhận</button>"
               if p["app_id"] else "<span class=muted>chưa khớp dòng nào</span>")
            + f"<button class='mbtn tiny' data-post='/api/track/mail'"
              f" data-arg='{p['id']}:no'>Bỏ qua</button></div></div>")
    return (f"<div class=asklist><div class=askhead>{len(items)} thư đang đợi "
            f"bạn quyết — máy đề xuất, không tự đổi</div>{rows}</div>")


def _table(rows: list[dict]) -> str:
    if not rows:
        return ("<div class=empty-box>chưa nộp chỗ nào. Sang tab Search, "
                "bấm <b>Nộp</b> trên một tin — máy mở trang nộp, điền phần "
                "chứng minh được, rồi để bạn bấm Gửi.</div>")
    body = ""
    for r in rows:
        stage = r["stage"]
        moves = "".join(
            f"<button class='mbtn tiny{' apply' if to == 'applied' else ''}'"
            f" data-post='/api/track/state'"
            f" data-arg='{r['id']}:{to}'>{esc(label)}</button>"
            for to, label in NEXT.get(stage, []))
        if stage == "draft":
            # Gửi: máy đọc lại form rồi mới bấm, còn ô bắt buộc trống thì từ
            # chối và nói ô nào. Đổi ý thì bỏ, đừng để bẩn bảng.
            moves = (f"<button class='mbtn tiny apply' data-post='/api/apply/send'"
                     f" data-arg='{r['id']}'>Gửi đơn</button>" + moves
                     + f"<button class='mbtn tiny' data-post='/api/track/drop'"
                       f" data-arg='{r['id']}'>bỏ</button>")
        when = f"{r['days']} ngày" if r["days"] is not None else "—"
        event = (f"{esc(r['last_event'][:52])}"
                 f"<i>{r['event_days']} ngày</i>" if r["last_event"] else
                 ('<span class=silent>im lặng</span>' if r["silent"] else "—"))
        cv = (f"<a class=plink href='/jobs/{r['posting_id']}/cv'>"
              f"{esc(r['cv_file'] or 'xem')}</a>" if r["posting_id"]
              else esc(r["cv_file"] or "—"))
        role = f"<i>{esc(r['role'][:44])}</i>" if r["role"] else ""
        body += (
            f"<tr class='{esc(stage)}{' quiet' if r['silent'] else ''}'>"
            f"<td class=tco><b>{esc(r['company'][:30])}</b>{role}</td>"
            f"<td class=twhen>{when}</td>"
            f"<td class=tcv>{cv}</td>"
            f"<td class=tstage><span class='pill {esc(stage)}'>"
            f"{esc(STAGE_LABEL.get(stage, stage))}</span></td>"
            f"<td class=tev>{event}</td>"
            f"<td class=tact>{moves}</td></tr>")
    return (
        "<table class=trackboard><thead><tr>"
        "<th>công ty · vị trí</th><th>nộp</th><th>bản CV</th>"
        "<th>trạng thái</th><th>thư gần nhất</th><th></th>"
        "</tr></thead><tbody>" + body + "</tbody></table>")


def _mailbox(ready: bool, address: str, days: int = 30) -> str:
    """Dòng hộp thư trên đầu bảng — CHỈ CÒN VIỆC, không còn cấu hình.

    Ô nhập địa chỉ + app password đã chuyển sang Cài đặt · Gmail. Nó là thứ
    nối một lần rồi thôi, mà trang này Vin mở hàng ngày; để một form cấu hình
    nằm trên đầu bảng việc là bắt mắt đọc lại nó mỗi ngày.

    Cái ở lại đây là VIỆC: bấm Quét thư. Chưa nối thì chỉ ra đúng chỗ nối.
    """
    if not ready:
        return ("<div class=boxrow><span class=muted>chưa nối hộp thư việc "
                "làm — thư trả lời sẽ không tự cập nhật bảng này</span>"
                "<button class='mbtn apply' data-appset='gmail'>"
                "Nối hộp thư…</button></div>")
    # "đã lưu", KHÔNG phải "đã nối": chỗ này chỉ biết config CÓ chuỗi, không
    # biết chuỗi đó còn đăng nhập được không. App password bị thu hồi bên
    # Google thì dòng này vẫn xanh, và Vin tin là hộp thư đang chạy.
    return (f"<div class=boxrow><span class=boxok>hộp thư "
            f"<b>{esc(address)}</b> đã lưu — bấm Quét để kiểm</span>"
            f"<button class='mbtn apply' data-post='/api/track/mail/scan'>"
            f"Quét thư {days} ngày</button></div>")


def render(*, rows: list[dict], asks: list[dict], counts: dict,
           mail_ready: bool = False, mail_address: str = "",
           mail_days: int = 30) -> str:
    open_now = sum(counts.get(s, 0) for s in OPEN)
    draft = counts.get("draft", 0)
    note = ((f"{draft} đang điền · " if draft else "")
            + f"{counts.get('total', 0)} lần nộp · {open_now} đang chờ · "
            f"{counts.get('silent', 0)} im lặng · "
            f"{counts.get('rejected', 0)} từ chối")
    scan = _mailbox(mail_ready, mail_address, mail_days)
    return runtime.render(
        title="Quản lí", active="/track", stream="search", journal="bottom",
        note=note, cols=1,
        panels=[runtime.panel(
            "Đã nộp",
            f"<div class=tracktop>{scan}</div>" + _ask(asks) + _table(rows),
            span=1)],
    )
