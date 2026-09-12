"""Tuỳ chọn của APP — nhớ qua các lần mở lại.

Khác profile_answer: đó là hồ sơ NGƯỜI DÙNG (có phiên bản, có lịch sử). Đây
chỉ là mấy cái công tắc của chính cái app, không cần lịch sử gì.

Đọc hỏng thì trả về mặc định. Một cái công tắc đọc không được KHÔNG được phép
làm app không mở lên nổi.
"""

from __future__ import annotations

import sqlite3

# Tự quét ngay khi mở app. MẶC ĐỊNH TẮT, cố ý:
# mở app lên mà nó tự mở Chrome đi quét LinkedIn trong lúc người dùng còn chưa
# kịp vào Settings là sai. Người dùng bật khi nào họ thấy đã cấu hình xong.
AUTORUN = "autorun"

# Ba núm người dùng thật sự đổi. Mọi thứ khác giữ nguyên trong code — bày ra
# một cái núm mà không ai muốn vặn thì đó là rác, không phải lựa chọn.
SCAN_EVERY = "scan_every_min"    # quét lại mỗi bao nhiêu phút
HOURS_FROM = "hours_from"        # Chrome chỉ chạy trong khung giờ này
HOURS_TO = "hours_to"

# NHỊP gọi LinkedIn. Đây là núm hiệu năng THẬT của vòng quét, và nó là một
# núm ĐÁNH ĐỔI chứ không phải núm "nhanh hơn miễn phí": đi nhanh là gọi dày
# hơn, mà LinkedIn là bên duy nhất app đang ở nhờ.
#
# Vì sao không làm "chạy nhiều tab song song": N tab với nhịp P giống hệt 1
# tab với nhịp P/N — cùng số lượt gọi mỗi giây, cùng rủi ro bị bóp. Song song
# chỉ là cách viết phức tạp hơn của một con số nhỏ hơn, cộng thêm N cửa sổ
# Chrome ăn RAM và N chỗ có thể chết nửa chừng.
PACE = "linkedin_pace"

# BẬT/TẮT từng nguồn. Hai cách tìm cho ra hai loại tin khác hẳn nhau — board
# công ty có mô tả đầy đủ và miễn phí (22 giây), LinkedIn phải mở từng trang
# và tốn nửa tiếng — nên có lúc chỉ muốn chạy một cái.
#
# MẶC ĐỊNH BẬT CẢ HAI. Một nguồn tắt lặng lẽ là kiểu hỏng tệ nhất: quét xong
# ít tin hơn hẳn mà không ai hiểu vì sao.
SRC_BOARD = "src_board"
SRC_LINKEDIN = "src_linkedin"

# ... và từng ATS riêng. Ba nhà cung cấp này cho ra ba loại tin khác hẳn nhau
# (đo trên kho thật 12/09: greenhouse 1.520 tin giữ 82; lever 442 giữ 18;
# ashby 600 giữ 6 nhưng 523 tin có cờ remote thật). Ai thấy một nguồn toàn
# rác với mình thì tắt hẳn, không phải chịu đựng nó mỗi giờ.
SRC_ATS = {"greenhouse": "src_greenhouse", "lever": "src_lever",
           "ashby": "src_ashby"}

# Thư báo việc của LinkedIn gửi vào hộp thư. Nguồn thứ ba, và là nguồn duy
# nhất không đụng tới Điều khoản của ai — thư gửi cho mình thì đọc thôi.
SRC_ALERT = "src_alert"

# NHỮNG CẶP (chức danh × nơi) ĐÃ QUÉT ĐẦY ít nhất một lần, dạng JSON.
#
# Đơn vị quét là CẶP, không phải cả lưới. Một dấu vân tay cho cả lưới thì thô
# quá: bỏ bớt một chức danh cũng bắt quét lại từ đầu, trong khi bỏ bớt thì
# làm gì có gì mới để tìm. Nhớ theo cặp thì luật rút về đúng một câu —
#
#     cặp nào CHƯA quét bao giờ thì quét đầy, cặp nào rồi thì chỉ hỏi tin mới.
#
# Và hai việc đó chạy được trong CÙNG một lượt.
LI_DONE = "li_done"

# Cấp bậc (tham số f_E) của lần quét trước. Nó áp cho MỌI cặp nên không nhét
# vào khoá cặp được. NỚI RỘNG cấp bậc thì mọi cặp thành chưa phủ; THU HẸP thì
# không, vì thu hẹp không đẻ ra tin nào mới.
LI_LEVELS = "li_levels"

# Đọc lại bao nhiêu ngày thư khi quét hộp thư. Mặc định 30: đủ bắt thư trả
# lời cho đơn nộp tháng trước, mà không phải lôi cả hộp thư về.
MAIL_DAYS = "mail_days"

# --- BA NÚM CỦA TẦNG CV -------------------------------------------------
#
# Ba núm, không hơn. Mỗi núm phải trả lời được "xoay nó thì bản CV đổi thế
# nào" bằng một câu — núm nào không trả lời được thì nó là núm trang trí, và
# núm trang trí làm người dùng mất tin vào cả bảng.
#
# Cả ba đều xoay SỐ ĐÃ CÓ SẴN trong cv/rules.py, không đẻ khái niệm mới.

# GIỌNG VĂN. "cv" = lược chủ ngữ ngôi thứ nhất (quy ước CV); "nguyen" = giữ
# đúng chữ Vin viết. Mặc định "cv": đo trên hồ sơ thật, 6/26 câu mở đầu bằng
# "I/My/We", và hai chữ đầu là chỗ đắt nhất của một dòng CV.
CV_GIONG = "cv_giong"
GIONG = {"cv": "lược chủ ngữ — Built…, Designed…",
         "nguyen": "giữ nguyên chữ bạn viết — I built…, I designed…"}

# ĐỘ DÀY TỪ KHOÁ. Đây là trọng số cho "câu này trúng thứ tin đòi" trong
# rules.sentence_weight. Dày lên thì máy ưu tiên câu trúng từ khoá; nhẹ đi
# thì nó ưu tiên câu mạnh về nội dung dù không trúng từ nào.
#
# KHÔNG phải nút "nhồi từ khoá": máy không thêm từ nào vào CV. Nó chỉ đổi
# THỨ TỰ ƯU TIÊN giữa mấy câu Vin đã viết.
CV_KHOA = "cv_khoa"
KHOA = {"nhe": 1.5, "thuong": 3.0, "day": 5.0}

# BỐ CỤC — mấy dòng mỗi khối. Trần một mặt giấy: gọn thì đọc nhanh nhưng nói
# được ít, đầy thì ngược lại.
CV_BO_CUC = "cv_bo_cuc"
BO_CUC = {"gon": 2, "thuong": 3, "day": 4}


DEFAULTS = {AUTORUN: "0", SCAN_EVERY: "60",
            HOURS_FROM: "8", HOURS_TO: "22", PACE: "thuong",
            SRC_BOARD: "1", SRC_LINKEDIN: "1", SRC_ALERT: "1", LI_DONE: "", LI_LEVELS: "", MAIL_DAYS: "30",
            CV_GIONG: "cv", CV_KHOA: "thuong", CV_BO_CUC: "thuong",
            **{k: "1" for k in SRC_ATS.values()}}


def get(conn: sqlite3.Connection, key: str) -> str:
    try:
        row = conn.execute("SELECT value FROM pref WHERE key = ?", (key,)).fetchone()
    except Exception:                       # noqa: BLE001
        return DEFAULTS.get(key, "")
    return row[0] if row else DEFAULTS.get(key, "")


def flag(conn: sqlite3.Connection, key: str) -> bool:
    return get(conn, key) == "1"


def put(conn: sqlite3.Connection, key: str, value: str) -> None:
    try:
        conn.execute("INSERT INTO pref (key, value) VALUES (?,?)"
                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, str(value)))
        conn.commit()
    except Exception:                       # noqa: BLE001
        pass


def set_flag(conn: sqlite3.Connection, key: str, on: bool) -> None:
    put(conn, key, "1" if on else "0")


def num(conn: sqlite3.Connection, key: str, low: int, high: int) -> int:
    """Số nguyên trong khoảng. Giá trị hỏng -> về mặc định, không nổ.

    Người dùng gõ được gì vào ô cũng không được làm chết vòng quét nền.
    """
    try:
        value = int(get(conn, key))
    except (TypeError, ValueError):
        value = int(DEFAULTS.get(key, low))
    return max(low, min(high, value))
