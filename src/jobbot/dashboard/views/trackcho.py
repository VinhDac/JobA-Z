"""Hàng chờ — mọi thứ MÁY KHÔNG TỰ CHỐT ĐƯỢC, gom về một chỗ.

Màn con của Quản lí. Tách ra là có lý do, không phải để cho đẹp:

    /track        BẢNG. Việc đã xong, máy đã chốt, chỉ đọc.
    /track/queue  HÀNG CHỜ. Việc máy bí, cần người quyết.

Trộn hai thứ vào một trang thì cái sạch bị cái chưa rõ đè xuống — 16 thẻ thư
đẩy ô tìm của bảng xuống dưới hơn một màn hình, và người vào xem bảng phải
cuộn qua một đống việc chưa làm mới tới thứ họ định xem.

Và chúng khác nhau ở NHỊP: bảng là thứ liếc mỗi ngày, hàng chờ là thứ ngồi
dọn một lần rồi trống. Một chỗ trống được mới là chỗ làm việc; bảng thì
không bao giờ trống.

MÁY KHÔNG TỰ ĐỔI GÌ Ở ĐÂY. Nó đề xuất, người bấm. Đây là chỗ ranh giới đó
hiện ra thành hình — xem apply/run.py cho ranh giới cùng loại ở tầng nộp.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc

from ...track.board import STAGE_LABEL
from . import runtime


def _ask(items: list[dict], rows: list[dict] | None = None) -> str:
    """Dải CẦN VIN: thư về đề xuất đổi trạng thái.

    `rows` = cả bảng, để lá thư KHÔNG khớp dòng nào vẫn gán tay được. Trước
    đây lá như thế chỉ có đúng một nút — Bỏ qua. Máy đọc được kết cục mà
    không đoán ra công ty, rồi bắt người dùng vứt lá thư đi: thấy mà không
    làm gì được thì cũng là mất, chỉ là mất ồn ào hơn. Đo trên hộp thư thật
    có 3 lá như vậy.
    """
    if not items:
        return ""
    chon = "".join(
        f"<option value='{r['id']}'>{esc(r['company'][:34])}"
        + (f" · {esc(r['role'][:26])}" if r.get("role") else "") + "</option>"
        for r in sorted(rows or [], key=lambda x: x["company"].lower()))
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
               if p["app_id"] else
               (f"<form class=ganform method=post data-post='/api/track/mail/gan'>"
                f"<select name=app data-ganfor='{p['id']}'>"
                f"<option value=''>máy không biết thư này của ai — chọn…</option>"
                f"{chon}</select></form>" if chon else
                "<span class=muted>chưa khớp dòng nào</span>"))
            + f"<button class='mbtn tiny' data-post='/api/track/mail'"
              f" data-arg='{p['id']}:no'>Bỏ qua</button></div></div>")
    return (f"<div class=asklist><div class=askhead>{len(items)} thư đang đợi "
            f"bạn quyết — máy đề xuất, không tự đổi</div>{rows}</div>")


# Bốn kết cục người dùng có thể xếp cho một lá thư máy không đọc nổi.
XEP = (("applied", "xác nhận đã nộp"), ("interview", "mời phỏng vấn"),
       ("rejected", "từ chối"), ("offer", "nhận việc"))


def _mu(items: list[dict]) -> str:
    """THƯ MÁY KHÔNG HIỂU — và đây là lời hứa thật của tầng thư.

    Bảng mẫu cách diễn đạt không bao giờ đủ: đo trên hộp thư thật, thư từ
    chối của Maven ("Sorry, it's not quite a match") và thư xác nhận của
    Trading 212 ("Your application is in") đều rơi vào `other` và biến mất.
    Đua thêm từ khoá là trò không có điểm dừng.

    Nên máy KHÔNG hứa hiểu mọi lá thư. Nó hứa KHÔNG LÁ NÀO BIẾN MẤT: thư nào
    nó bó tay mà lại thuộc một lần nộp trên bảng thì hiện ra đây, người dùng
    xếp một cái là xong.
    """
    if not items:
        return ""
    rows = ""
    for m in items:
        nut = "".join(
            f"<button class='mbtn tiny' data-post='/api/track/mail/xep'"
            f" data-arg='{m['id']}:{ma}'>{esc(nhan)}</button>"
            for ma, nhan in XEP)
        rows += (
            f"<div class=askrow><div class=askmain>"
            f"<b>{esc(m['company'] or m['company_guess'] or '?')}</b>"
            f"<span class=askto>máy không đọc được — bạn xếp giúp</span>"
            f"<div class=asksub>{esc(' '.join((m['subject'] or '').split())[:96])}</div>"
            f"<div class=asksnip>{esc(' '.join((m['snippet'] or '').split())[:130])}</div>"
            f"</div><div class=askact>{nut}"
            f"<button class='mbtn tiny' data-post='/api/track/mail/ignore'"
            f" data-arg='{m['id']}'>bỏ qua</button></div></div>")
    return (f"<div class='askbox mu'><div class=askhead>"
            f"<b>{len(items)}</b> thư máy KHÔNG đọc được — nhưng chúng thuộc "
            f"về một lần nộp trên bảng, nên không lá nào bị bỏ rơi"
            f"</div>{rows}</div>")


# CHẶNG ĐI TIẾP ĐƯỢC từ mỗi chặng. Dọn từ bảng sang đây: đổi chặng là SỬA,
# và bảng không sửa gì cả.
NEXT = {"draft": [("applied", "đã gửi tay")],
        "applied": [("interview", "phỏng vấn"), ("rejected", "từ chối")],
        "interview": [("offer", "nhận"), ("rejected", "từ chối")],
        "rejected": [], "offer": []}


def _nhap(rows: list[dict]) -> str:
    """MÁY ĐIỀN XONG, CHỜ BẠN BẤM GỬI — việc dở dang thật sự của app.

    Máy mở form và điền phần nó chứng minh được rồi DỪNG: vài câu như
    sponsorship hay ngày tốt nghiệp chỉ bạn trả lời được, và cú bấm Gửi là
    của bạn. Ranh giới đó nằm trong apply/run.py, và đây là chỗ nó hiện ra
    thành việc phải làm.
    """
    nhap = [r for r in rows if r.get("stage") == "draft"]
    if not nhap:
        return ""
    o = ""
    for r in nhap:
        o += (f"<div class=askrow><div class=askmain>"
              f"<div class=askwho><b>{esc(r['company'][:34])}</b>"
              f"<i>{esc((r.get('role') or '')[:38])}</i></div>"
              f"<div class=asksub>máy đã điền xong phần nó chứng minh được — "
              f"còn lại là mấy câu chỉ bạn trả lời được</div></div>"
              f"<div class=askact>"
              f"<button class='mbtn tiny apply' data-post='/api/apply/send'"
              f" data-arg='{r['id']}'>Gửi đơn</button>"
              f"<button class='mbtn tiny' data-post='/api/track/drop'"
              f" data-arg='{r['id']}'>bỏ</button></div></div>")
    return (f"<div class=asklist><div class=askhead><b>{len(nhap)}</b> đơn máy "
            f"điền xong, chờ bạn bấm Gửi</div>{o}</div>")


def _tay(rows: list[dict]) -> str:
    """MÁY BÓ TAY — và nó đưa đủ đồ nghề chứ không chỉ báo một câu.

    Tin LinkedIn không lộ đường nộp (môi giới, hoặc buộc nộp trong LinkedIn).
    Hai thứ cần để tự làm là ĐƯỜNG NỘP và BẢN CV, app đang giữ cả hai. Làm
    xong bấm Quét thư: thư xác nhận về thì trạng thái tự đổi — không phải tự
    tay đánh dấu.
    """
    tay = [r for r in rows if (r.get("origin") or "") == "tay"]
    if not tay:
        return ""
    o = ""
    for r in tay:
        mo = (f"<a class='mbtn tiny apply' href='{esc(r['url'])}' target=_blank"
              f" rel=noopener>Mở trang nộp ↗</a>" if r.get("url") else "")
        tai = (f"<button class='mbtn tiny' data-post='/api/cv/pdf'"
               f" data-arg='{r['posting_id']}'>Tải bản CV</button>"
               if r.get("posting_id") else "")
        o += (f"<div class=askrow><div class=askmain>"
              f"<div class=askwho><b>{esc(r['company'][:34])}</b>"
              f"<i>{esc((r.get('role') or '')[:38])}</i></div>"
              f"<div class=asksub>máy không nộp hộ được — mở trang, tải bản "
              f"CV, nộp tay. Xong thì bấm <b>Quét thư</b>: thư xác nhận về là "
              f"dòng đó tự sang «đã nộp»</div></div>"
              f"<div class=askact>{mo}{tai}</div></div>")
    return (f"<div class='asklist mu'><div class=askhead><b>{len(tay)}</b> tin "
            f"máy không nộp hộ được — bạn tự nộp</div>{o}</div>")


def _doi(rows: list[dict], doi: str = "") -> str:
    """ĐỔI CHẶNG BẰNG TAY — cửa thoát hiểm, MỘT cái, không phải 74 cái nút.

    Vì sao phải có: thư là cảm biến duy nhất của bảng. Một cuộc gọi mời phỏng
    vấn không để lại lá thư nào, nên máy không bao giờ biết — và sau 20 ngày
    nó lặng lẽ xếp dòng đó vào "coi như trượt". Không có cửa này thì đó là
    mất trắng một cơ hội có thật.

    Vì sao KHÔNG để trên bảng: ở đó nó thành 74 cái nút nằm cạnh 37 dòng
    đang đọc, và một cú bấm nhầm đổi trạng thái thật. Ở đây nó là hai bước
    có chủ ý — chọn dòng, rồi chọn chặng.

    HAI BƯỚC ĐI QUA URL (`?doi=`), không qua JavaScript: mở thẳng địa chỉ
    hay bấm Back đều đúng, cùng lối với ô tìm bên Search.
    """
    that = [r for r in rows if r.get("stage") != "draft"]
    if not that:
        return ""
    chon = "".join(
        f"<option value='{r['id']}'{' selected' if str(r['id']) == doi else ''}>"
        + esc(r["company"][:34])
        + (f" · {esc(r['role'][:26])}" if r.get("role") else "")
        + f" — {esc(STAGE_LABEL.get(r['stage'], r['stage']))}</option>"
        for r in sorted(that, key=lambda x: x["company"].lower()))
    kia = next((r for r in that if str(r["id"]) == doi), None)
    nut = ""
    if kia:
        di = NEXT.get(kia["stage"], [])
        nut = ("".join(
            f"<button class='mbtn tiny{' apply' if to == 'applied' else ''}'"
            f" data-post='/api/track/state'"
            f" data-arg='{kia['id']}:{to}'>{esc(nhan)}</button>"
            for to, nhan in di)
            or "<span class=muted>chặng này đã là kết cục — không đi tiếp "
               "đâu được</span>")
        nut = (f"<div class=doinow><b>{esc(kia['company'][:40])}</b>"
               f"<span>đang ở «{esc(STAGE_LABEL.get(kia['stage'], ''))}»"
               f" — đổi sang:</span><div class=askact>{nut}</div></div>")
    return (f"<div class=asklist><div class=askhead>Đổi chặng bằng tay"
            f"<span>dùng khi kết quả đến ngoài hộp thư — một cuộc gọi, một "
            f"tin nhắn. Máy không thấy được những thứ đó.</span></div>"
            f"<form class=doiform method=get action='/track/queue'>"
            f"<select name=doi>{chon}</select>"
            f"<button class='mbtn tiny'>Chọn</button></form>{nut}</div>")


def _trong() -> str:
    """Hàng chờ rỗng — và nó RỖNG ĐƯỢC, đó là điểm của cả màn này."""
    return ("<div class=empty-box><b>Không còn gì đợi bạn quyết.</b><br>"
            "Thư nào máy đọc ra kết cục thì nó đã cập nhật thẳng vào bảng. "
            "Chỗ này chỉ sáng lên khi máy bí — bấm <b>Quét thư</b> để đọc "
            "hộp thư lần nữa.</div>")


def render(*, rows: list[dict], asks: list[dict], mu: list[dict] | None = None,
           stage: dict | None = None, doi: str = "") -> str:
    """Hai ô: THƯ (máy đọc được / máy bó tay) · VIỆC & SỬA.

    Bảng bên /track chỉ còn fact — không một nút nào đổi được dòng nào. Mọi
    thứ hỏi ý kiến hay sửa dồn hết về đây, chia theo AI ĐANG BÍ:

        máy đọc ra kết cục, xin gật đầu      -> một cú bấm
        máy không đọc nổi lá thư             -> bạn xếp giúp
        máy điền xong đơn, không được bấm Gửi -> bạn gửi
        máy không nộp hộ được                 -> bạn nộp tay
        máy không thấy gì cả (gọi điện, nhắn) -> bạn đổi chặng tay

    Ba cái đầu là thư, hai cái sau là việc — nên hai ô, không phải năm.
    """
    from ..layout import deck
    info = stage or {}
    de = asks or []
    bi = mu or []
    tay = _tay(rows)
    nhap = _nhap(rows)
    viec = nhap + tay + _doi(rows, doi)
    con = len(de) + len(bi) + sum(1 for r in rows if r.get("stage") == "draft") \
        + sum(1 for r in rows if (r.get("origin") or "") == "tay")
    return runtime.render(
        title="Hàng chờ", active="/track", stream="search", journal="bottom",
        cols=2,
        bar=deck("track", "Quản lí · hàng chờ",
                 (f"{con} việc đang đợi bạn" if con else "không còn gì đợi bạn"),
                 [(f"{len(de)}", "máy đề xuất", "act"),
                  (f"{len(bi)}", "máy không đọc nổi", "new"),
                  (f"{con - len(de) - len(bi)}", "đơn chờ bạn", "new"),
                  (f"{len(rows)}", "dòng trên bảng", "view")],
                 run="Quét thư", run_note="đọc hộp thư rồi cập nhật bảng",
                 sua=("/track", "← Bảng", "Quay lại bảng Đã nộp")),
        panels=[runtime.panel("Thư · máy hỏi bạn",
                              (_ask(de, rows) + _mu(bi)) or _trong(), rows=2),
                runtime.panel("Việc & sửa · bảng không làm được",
                              viec or "<div class=empty-box>không đơn nào dở "
                              "dang, và bảng đang đúng như thư kể.</div>",
                              rows=2)],
    )
