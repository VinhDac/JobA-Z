"""Quyết định BÁO GÌ, và trả lời lệnh từ xa.

Chia đôi với core/tele.py cho rõ: tele lo ĐƯỜNG ĐI (gọi API, chốt chat_id,
đọc lệnh), file này lo NỘI DUNG (có đáng báo không, câu chữ thế nào, lệnh
này trả về gì). Trộn hai thứ thì không kiểm được cái nào: muốn thử câu chữ
lại phải có token thật.

LUẬT GỐC: BÁO ÍT THÔI. Bốn loại, mỗi loại mặc định phải trả lời được "biết
cái này thì tôi làm gì khác đi". Loại nào không trả lời được thì nó là tiếng
ồn, và tiếng ồn làm người dùng tắt cả thông báo — kể cả cái đáng giá.

KHÔNG NÉM LỖI RA NGOÀI. Chạy trong luồng nền của scheduler.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .core import prefs, tele
from .core.journal import SYSTEM, log as jlog


def _hom_nay() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def bat(conn: sqlite3.Connection, khoa: str) -> bool:
    """Loại báo này có bật không — VÀ bot đã nối chưa.

    Gộp hai câu hỏi vào một chỗ là cố ý: quên kiểm "đã nối chưa" thì mỗi lần
    quét lại gọi API với token rỗng, hỏng lặng lẽ, và nhật ký đầy rác.
    """
    return tele.da_noi() and prefs.flag(conn, khoa)


# --- BỐN LOẠI BÁO --------------------------------------------------------

def _thu_moi(conn: sqlite3.Connection) -> list:
    """Thư ĐI TIẾP chưa từng báo. Mốc lưu trong pref, không đếm lại từ đầu.

    Không có mốc thì mỗi lượt quét lại nhắn đúng lá cũ, và người dùng tắt
    thông báo sau đúng hai ngày.
    """
    try:
        moc = int(prefs.get(conn, prefs.BAO_MOC) or 0)
    except (TypeError, ValueError):
        moc = 0
    cho = ",".join(f"'{k}'" for k in ("interview", "offer"))
    return [dict(r) for r in conn.execute(
        f"SELECT m.id, m.subject, m.kind, m.received_at,"
        f" COALESCE(a.company, m.company_guess, '') AS cong_ty,"
        f" COALESCE(a.role, '') AS vai_tro"
        f" FROM message m LEFT JOIN application a ON a.id = m.application_id"
        f" WHERE m.kind IN ({cho}) AND m.id > ? ORDER BY m.id", (moc,))]


def di_tiep(conn: sqlite3.Connection) -> int:
    """Báo mấy lá thư mời mới. Trả về số lá đã báo."""
    if not bat(conn, prefs.BAO_TIEP):
        return 0
    moi = _thu_moi(conn)
    if not moi:
        return 0
    dong = []
    for m in moi:
        ai = tele.thoat(m["cong_ty"] or "không rõ công ty")
        vt = f" · {tele.thoat(m['vai_tro'])}" if m["vai_tro"] else ""
        loai = "MỜI PHỎNG VẤN" if m["kind"] == "interview" else "NHẬN VIỆC"
        dong.append(f"<b>{loai}</b>\n{ai}{vt}\n"
                    f"<i>{tele.thoat(m['subject'][:110])}</i>")
    if tele.gui("🔔 " + "\n\n".join(dong)):
        prefs.put(conn, prefs.BAO_MOC, str(max(m["id"] for m in moi)))
        jlog.ok(SYSTEM, f"đã nhắn Telegram: {len(moi)} thư đi tiếp")
        return len(moi)
    return 0


def phien_hong(conn: sqlite3.Connection, hong: list) -> bool:
    """Báo khúc nào của phiên vừa hỏng.

    HỎNG CÂM là kiểu hỏng tệ nhất: máy đứng im mấy ngày mà bảng vẫn xanh, và
    người dùng chỉ phát hiện khi thấy lâu quá không có tin mới.
    """
    if not hong or not bat(conn, prefs.BAO_HONG):
        return False
    ten = {khuc: nhan for _k, (khuc, nhan, _y) in prefs.PHIEN.items()}
    ds = ", ".join(ten.get(k, k) for k in hong)
    return tele.gui(f"⚠️ <b>Phiên hỏng</b>\nKhúc không chạy được: {tele.thoat(ds)}"
                    f"\nMở app xem nhật ký để biết vì sao.")


def hang_cho(conn: sqlite3.Connection) -> bool:
    """Báo khi hàng chờ dồn quá ngưỡng người dùng đặt."""
    if not bat(conn, prefs.BAO_CHO):
        return False
    from .track import scan as tscan
    n = len(tscan.proposals(conn)) + len(tscan.kho_hieu(conn))
    nguong = prefs.num(conn, prefs.BAO_NGUONG, 1, 999)
    if n < nguong:
        return False
    return tele.gui(f"📥 <b>{n} việc đang đợi bạn quyết</b>\n"
                    f"Thư máy không tự chốt được. Mở tab Quản lí → Queue.")


def ban_tin_ngay(conn: sqlite3.Connection, ep: bool = False) -> bool:
    """Bản tin cuối ngày — bốn số của hôm nay, gửi ĐÚNG MỘT LẦN.

    Nhớ đã gửi cho ngày nào (`BAO_NGAY_CUOI`): vòng nền chạy mỗi 30 giây, và
    không có cái mốc này thì qua giờ hẹn nó nhắn liên tục tới nửa đêm.
    """
    if not bat(conn, prefs.BAO_NGAY):
        return False
    hom_nay = _hom_nay()
    if not ep:
        if prefs.get(conn, prefs.BAO_NGAY_CUOI) == hom_nay:
            return False
        if datetime.now().hour < prefs.num(conn, prefs.BAO_GIO, 0, 23):
            return False
    from .dashboard import tongquan
    hn = tongquan.hom_nay(conn)
    ok = tele.gui(
        f"📊 <b>Hôm nay</b> · {hn['ngay']}\n"
        f"tin tìm được: <b>{hn['tim']}</b>\n"
        f"đơn đã nộp: <b>{hn['nop']}</b>\n"
        f"được gọi tiếp: <b>{hn['tiep']}</b>\n"
        f"báo trượt: <b>{hn['truot']}</b>")
    if ok and not ep:
        prefs.put(conn, prefs.BAO_NGAY_CUOI, hom_nay)
    return ok


def sau_phien(conn: sqlite3.Connection, ket_qua: dict) -> None:
    """MỘT chỗ gọi hết mọi loại báo, chạy sau mỗi vòng phiên.

    Rải lời gọi ở bốn chỗ khác nhau thì thêm một loại báo là phải nhớ sửa
    bốn chỗ, và sẽ có chỗ quên.
    """
    try:
        phien_hong(conn, (ket_qua or {}).get("hong") or [])
        di_tiep(conn)
        hang_cho(conn)
        ban_tin_ngay(conn)
    except Exception as exc:                # noqa: BLE001
        jlog.error(SYSTEM, f"nhắn Telegram hỏng — {type(exc).__name__}: {exc}")


# --- TRẢ LỜI LỆNH TỪ XA ---------------------------------------------------

GIUP = ("<b>jobbot</b>\n"
        "/trangthai — bốn số hôm nay + hàng chờ\n"
        "/batphien — bật trạm trực 24/7\n"
        "/tatphien — tắt trạm trực\n"
        "/thu — mấy thư đang đợi bạn quyết\n"
        "/nhan &lt;số&gt; — nhận đề xuất của thư đó\n"
        "/boqua &lt;số&gt; — bỏ qua thư đó\n\n"
        "<i>Không có lệnh nộp đơn, ở bất kỳ mức nào: cú bấm Gửi là của bạn, "
        "trước mặt cái form.</i>")


def _trang_thai(conn: sqlite3.Connection) -> str:
    from .core import scheduler
    from .dashboard import tongquan
    from .track import scan as tscan
    hn = tongquan.hom_nay(conn)
    k = tongquan.ket_qua(conn)
    cho = len(tscan.proposals(conn)) + len(tscan.kho_hieu(conn))
    sch = scheduler.current()
    truc = ("ĐANG CHẠY" if sch.running
            else "TẮT" if sch.paused else f"đang trực · vòng sau {sch.next_in() // 60}p")
    return (f"📊 <b>Hôm nay</b> · {hn['ngay']}\n"
            f"tìm được <b>{hn['tim']}</b> · nộp <b>{hn['nop']}</b> · "
            f"gọi tiếp <b>{hn['tiep']}</b> · trượt <b>{hn['truot']}</b>\n\n"
            f"tổng đã nộp <b>{k['tong']}</b> · đi tiếp <b>{k['di_tiep']}</b>"
            + (f" ({k['pc_di']:g}%)" if k["pc_di"] is not None else "") + "\n"
            f"hàng chờ <b>{cho}</b> việc\n"
            f"trạm trực: <b>{truc}</b>")


def _thu_cho(conn: sqlite3.Connection) -> str:
    from .track import scan as tscan
    ds = tscan.proposals(conn)[:8]
    if not ds:
        return "Không có thư nào đang đợi bạn quyết."
    o = []
    for p in ds:
        ai = tele.thoat(p.get("company") or p.get("company_guess") or "?")
        o.append(f"<b>{p['id']}</b> · {ai} → {tele.thoat(p['kind'])}\n"
                 f"   <i>{tele.thoat((p.get('subject') or '')[:70])}</i>")
    return ("📥 <b>Thư đợi bạn quyết</b>\n" + "\n".join(o)
            + "\n\n/nhan &lt;số&gt; hoặc /boqua &lt;số&gt;")


def tra_loi(conn: sqlite3.Connection, lenh: str, tham: str) -> str:
    """Chạy một lệnh ĐÃ QUA CHỐT QUYỀN và trả về câu đáp.

    Hàm này KHÔNG tự kiểm chat_id — việc đó là của tele.duoc_phep, gọi ở
    vòng ngoài. Tách ra để kiểm được câu chữ mà không cần dựng cả một update
    Telegram giả.
    """
    from .core import scheduler
    if lenh in ("giupdo", "start"):
        return GIUP
    if lenh == "trangthai":
        return _trang_thai(conn)
    if lenh == "batphien":
        sch = scheduler.current()
        sch.resume()
        return "▶️ Trạm trực ĐÃ BẬT. Vòng sau chạy theo lịch."
    if lenh == "tatphien":
        scheduler.current().pause()
        return "⏸ Trạm trực ĐÃ TẮT. Không tự chạy vòng nào nữa."
    if lenh == "thu":
        return _thu_cho(conn)
    if lenh in ("nhan", "boqua"):
        if not tham.strip().isdigit():
            return "Thiếu số hiệu thư. Ví dụ: /nhan 42 — xem /thu để lấy số."
        from .track import scan as tscan
        mid = int(tham)
        co = conn.execute("SELECT 1 FROM message WHERE id = ? AND needs_you = 1",
                          (mid,)).fetchone()
        if not co:
            return "Không thấy thư đó trong hàng chờ — có thể đã xử lý rồi."
        # `settle` KHÔNG trả về gì; nó cũng tự chặn thư CŨ đè trạng thái MỚI
        # (xem track/scan.py). Ở đây chỉ hỏi lại bảng xem đã đổi thật chưa.
        tscan.settle(conn, mid, lenh == "nhan")
        return ("✅ Đã nhận — bảng đã đổi theo thư đó."
                if lenh == "nhan" else "🗑 Đã bỏ qua thư đó.")
    return "Không hiểu lệnh. Gõ /giupdo để xem danh sách."


# --- NÚT TEST -------------------------------------------------------------

def tin_thu(conn: sqlite3.Connection) -> str:
    """Nội dung tin THỬ — và nó chính là bản hướng dẫn.

    Một tin thử chỉ nói "ok" thì nó mới chứng minh được ĐƯỜNG ĐI thông, chưa
    chứng minh CẤU HÌNH đúng. Người dùng vẫn phải quay về màn Cài đặt để xem
    mình đang ở mức nào, bật loại báo nào — mà lúc đó họ đang cầm điện thoại.

    Nên tin này nói đủ ba thứ, ngay trên điện thoại: đang ở CHẾ ĐỘ nào, dùng
    được LỆNH nào, và sẽ NHẮN KHI NÀO.
    """
    muc = prefs.get(conn, prefs.BAO_MUC) or tele.TAT
    ten_muc = tele.MUC_DIEU_KHIEN.get(muc, ("?", ""))[0]

    if muc == tele.TAT:
        lenh = ("<i>Đang ở chế độ chỉ báo một chiều — bot không nhận lệnh "
                "nào. Đổi ở Cài đặt · Thông báo trên máy.</i>")
    else:
        co = [l for l in tele.LENH_XEM if l not in ("giupdo", "start")]
        if muc == tele.DAY_DU:
            co += list(tele.LENH_GHI)
        lenh = "Lệnh dùng được: " + " ".join(f"/{l}" for l in co)

    bat_ds = [prefs.BAO[k][0] for k in prefs.BAO if prefs.flag(conn, k)]
    tat_ds = [prefs.BAO[k][0] for k in prefs.BAO if not prefs.flag(conn, k)]
    khi = ("Sẽ nhắn khi:\n" + "\n".join(f"• {tele.thoat(x)}" for x in bat_ds)
           if bat_ds else
           "<b>Chưa bật loại báo nào</b> — sẽ không có tin nào tự gửi về.")
    if tat_ds:
        khi += f"\n<i>(đang tắt: {tele.thoat(' · '.join(tat_ds))})</i>"

    gio = prefs.num(conn, prefs.BAO_GIO, 0, 23)
    them = (f"\nBản tin cuối ngày gửi lúc <b>{gio}:00</b>."
            if prefs.flag(conn, prefs.BAO_NGAY) else "")

    return (f"✅ <b>jobbot đã nối</b>\n"
            f"Tin này tới được nghĩa là token và số chat đều đúng.\n\n"
            f"<b>Chế độ:</b> {tele.thoat(ten_muc)}\n{lenh}\n\n"
            f"{khi}{them}\n\n"
            f"<i>Bấm Test ở Cài đặt · Thông báo để gửi lại tin này.</i>")


def thu(conn: sqlite3.Connection) -> tuple:
    """Bấm Test -> (được không, câu hiện lên màn Cài đặt).

    Gửi THẬT một tin, không giả lập: cả chuỗi token → số chat → mạng →
    Telegram chỉ chứng minh được bằng cách đi hết một vòng. Kiểm từng khúc
    rồi kết luận "chắc là chạy" là đúng kiểu tự lừa mà app này tránh.
    """
    ok, loi = tele.gui_chi_tiet(tin_thu(conn))
    if ok:
        jlog.ok(SYSTEM, "Telegram: tin thử đã gửi")
        return True, ("Đã gửi. Mở Telegram xem — tin đó nói luôn bạn đang ở "
                      "chế độ nào và dùng được lệnh gì.")
    jlog.warn(SYSTEM, f"Telegram: tin thử KHÔNG gửi được — {loi}")
    return False, f"Không gửi được: {loi}"


# --- LUỒNG NGHE LỆNH -----------------------------------------------------

def _mot_luot(conn: sqlite3.Connection, tin: dict, chat_id: str, muc: str) -> None:
    """Xử lý MỘT tin đến. Tách ra để kiểm được mà không cần mạng."""
    # CHỐT QUYỀN TRƯỚC MỌI THỨ KHÁC — kể cả trước khi đọc nội dung. Bot
    # Telegram ai cũng nhắn được; đây là hàng rào duy nhất.
    if not tele.duoc_phep(tin, chat_id):
        ai = ((tin.get("message") or {}).get("chat") or {}).get("id")
        jlog.warn(SYSTEM, f"bỏ tin Telegram từ chat lạ ({ai}) — không phải "
                          f"chat đã ghim")
        return
    lenh, tham = tele.doc_lenh(tin)
    if not lenh:
        return
    if not tele.cho_phep_lenh(lenh, muc):
        tele.gui("Mức điều khiển hiện tại không cho lệnh này. "
                 "Đổi ở Cài đặt · Thông báo trên máy.")
        return
    tele.gui(tra_loi(conn, lenh, tham))
    jlog.ok(SYSTEM, f"lệnh Telegram: /{lenh}")


def nghe(dung) -> None:
    """Vòng nghe lệnh — long polling, chỉ gọi RA ngoài.

    `dung` là threading.Event: đặt thì thoát. Chạy trong luồng nền riêng,
    KHÔNG dùng chung luồng với scheduler: long-poll ngủ 25 giây mỗi lượt, mà
    vòng quét thì không được ngủ theo.

    Đọc lại mức điều khiển MỖI LƯỢT, không đọc một lần lúc khởi động: đổi từ
    "chỉ báo" sang "điều khiển" ở Cài đặt phải ăn ngay, không phải mở lại app.
    """
    from .core import db
    offset = 0
    while not dung.is_set():
        try:
            c = cau_hinh_nghe()
            if not c:
                dung.wait(20)               # chưa nối, hoặc đang TẮT
                continue
            ds, offset = tele.nhan(offset)
            if not ds:
                continue
            conn = db.connect()
            try:
                for tin in ds:
                    _mot_luot(conn, tin, c["chat_id"], c["muc"])
            finally:
                conn.close()
        except Exception as exc:            # noqa: BLE001
            # Không bao giờ để luồng này chết: nó là đường điều khiển từ xa
            # duy nhất, và chết câm thì người dùng nhắn mãi không ai trả lời.
            jlog.error(SYSTEM, f"vòng nghe Telegram hỏng — "
                               f"{type(exc).__name__}: {str(exc)[:60]}")
            dung.wait(30)


def cau_hinh_nghe() -> dict | None:
    """{chat_id, muc} nếu đang thật sự nghe; None nếu chưa nối hoặc mức TẮT."""
    from .core import db
    if not tele.da_noi():
        return None
    conn = db.connect()
    try:
        muc = prefs.get(conn, prefs.BAO_MUC) or tele.TAT
    finally:
        conn.close()
    if muc == tele.TAT:
        return None
    return {"chat_id": str(tele.cau_hinh().get("chat_id", "")).strip(),
            "muc": muc}
