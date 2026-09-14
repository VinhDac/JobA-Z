"""Một PHIÊN — một vòng chạy hết cả dây chuyền.

Trước đây mỗi khúc một nút, và người dùng phải tự nhớ thứ tự: chạy Search
xong sang CV bấm Chạy, rồi sang Quản lí bấm Quét thư. Ba lần bấm cho một
việc, và quên một bước thì không có gì báo — chỉ là sáng ra ít bản CV hơn.

Phiên gom ba bước đó thành MỘT, và vòng chạy nền lặp lại nó 24/7.

    Search      tìm tin mới, lọc, chấm điểm
    Make CV     xếp lại chữ trên CV cho khớp từng tin trong kho
    Manage mail đọc hộp thư rồi cập nhật bảng

THỨ TỰ LÀ MỘT PHẦN CỦA ĐỊNH NGHĨA, không phải tình cờ. Dựng CV đọc kho tin,
nên nó phải chạy SAU lượt tìm; chạy trước thì nó xếp theo kho của vòng
trước, và mỗi vòng đều trễ đúng một nhịp. Đọc thư đứng cuối vì nó không phụ
thuộc hai khúc kia — nhưng để cuối thì bảng Quản lí luôn là thứ mới nhất
người dùng thấy khi mở app.

CHẠY TUẦN TỰ, KHÔNG SONG SONG. Ba khúc cùng ghi một file SQLite, và khúc
Search còn mở Chrome. Chạy chồng lên nhau thì được đúng một thứ: hai chỗ
cùng khoá một bảng, và không nhanh hơn chút nào vì nút cổ chai là mạng.

MỘT KHÚC HỎNG KHÔNG ĐƯỢC GIẾT CẢ PHIÊN. Hộp thư mất mạng thì lượt tìm việc
vẫn phải xong — nên mỗi khúc có hàng rào riêng, hỏng thì ghi nhật ký rồi đi
tiếp khúc sau.
"""

from __future__ import annotations

import sqlite3

from .core import prefs
from .core.journal import SYSTEM, log as jlog


def dang_bat(conn: sqlite3.Connection) -> list[str]:
    """Tên khúc của những khúc đang BẬT, theo đúng thứ tự chạy.

    Thứ tự lấy từ `prefs.PHIEN` chứ không gõ lại ở đây: gõ lại là hai nguồn
    cho một sự thật, và có ngày tấm Điều chỉnh xếp một đằng, phiên chạy một nẻo.
    """
    return [khuc for khoa, (khuc, _ten, _y) in prefs.PHIEN.items()
            if prefs.flag(conn, khoa)]


def _search(conn: sqlite3.Connection) -> str:
    from .scan_runner import run_scan
    return (run_scan() or {}).get("summary", "")


def _cv(conn: sqlite3.Connection) -> str:
    from .cv import batch
    ra = batch.run(conn) or {}
    return f"{len(ra.get('versions') or [])} bản CV"


def _mail(conn: sqlite3.Connection) -> str:
    from .track import scan as tscan
    tscan.run(conn)
    tscan.noi_lai(conn)
    return "đã đọc hộp thư"


CHAY = {"search": _search, "cv": _cv, "track": _mail}


def chay(conn: sqlite3.Connection | None = None) -> dict:
    """Chạy một vòng. Trả về khúc nào chạy, khúc nào hỏng, và vì sao.

    KHÔNG ném lỗi ra ngoài. Hàm này được gọi từ luồng nền của scheduler, và
    một ngoại lệ thoát ra khỏi đó là giết luôn vòng chạy 24/7 — app im lặng
    thôi làm việc, mà không có gì trên màn hình nói ra điều đó.
    """
    from .core import db, halt

    tu_mo = conn is None
    conn = conn or db.connect()
    xong, hong = [], []
    try:
        khuc = dang_bat(conn)
        if not khuc:
            # TẮT CẢ BA thì nói ra. Một phiên chạy mà không làm gì, im lặng,
            # là cách nhanh nhất để người dùng tin app hỏng.
            jlog.warn(SYSTEM, "phiên chạy nhưng cả ba khúc đang TẮT — "
                              "bật lại ở nút ⚟ trên thanh Tổng quan")
            return {"xong": [], "hong": [], "tat": True}
        ten = {khuc: nhan for _k, (khuc, nhan, _y) in prefs.PHIEN.items()}
        # GỠ CỜ DỪNG Ở ĐẦU MỖI PHIÊN.
        #
        # "Dừng" nghĩa là dừng VÒNG ĐANG CHẠY, không phải đầu độc mọi vòng
        # sau. Bản trước chỉ có /api/session/start gỡ cờ, nên bật lại bằng
        # vòng nền hay bằng /batphien trên Telegram thì cờ còn dính: mọi
        # phiên sau chạy 0/3 khúc rồi báo "xong" — đúng kiểu hỏng câm.
        #
        # Gỡ ở ĐÂY vì đây là chỗ DUY NHẤT một phiên bắt đầu, bất kể ai gọi.
        # Đặt ở từng lối vào thì thêm một lối là phải nhớ, và sẽ quên.
        for s in khuc:
            halt.clear(s)
        jlog.ok(SYSTEM, "phiên bắt đầu — " + " → ".join(ten[s] for s in khuc))
        for s in khuc:
            if halt.wanted(s):
                # Người dùng bấm Dừng giữa phiên: bỏ nốt mấy khúc còn lại,
                # không chạy tiếp rồi mới hỏi.
                jlog.warn(SYSTEM, f"phiên dừng giữa chừng — bỏ qua {ten[s]}")
                break
            try:
                ra = CHAY[s](conn)
                xong.append(s)
                jlog.ok(SYSTEM, f"phiên · {ten[s]} xong{' — ' + ra if ra else ''}")
            except Exception as exc:            # noqa: BLE001
                hong.append(s)
                jlog.error(SYSTEM, f"phiên · {ten[s]} hỏng — "
                                   f"{type(exc).__name__}: {str(exc)[:70]}")
        # NÓI ĐÚNG CHUYỆN GÌ XẢY RA. "xong — 0/3" đọc ra như một vòng bình
        # thường không tìm được gì; bị người dùng cắt ngang là chuyện khác hẳn.
        if not xong and not hong:
            jlog.warn(SYSTEM, "phiên KHÔNG chạy khúc nào — bị bấm Dừng")
        else:
            jlog.ok(SYSTEM, f"phiên xong — {len(xong)}/{len(khuc)} khúc chạy được")
        # BÁO VỀ ĐIỆN THOẠI — một chỗ gọi, ngay sau khi vòng xong. Rải lời
        # gọi vào từng khúc thì thêm một loại báo là phải nhớ sửa ba chỗ.
        from .bao import sau_phien
        sau_phien(conn, {"xong": xong, "hong": hong})
    finally:
        if tu_mo:
            conn.close()
    return {"xong": xong, "hong": hong, "tat": False}
