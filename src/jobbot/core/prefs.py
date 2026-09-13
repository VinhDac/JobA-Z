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

# --- HAI NÚM CỦA TẦNG CV ------------------------------------------------
#
# HAI, không hơn. Mỗi núm phải trả lời được "xoay nó thì bản CV đổi thế nào"
# bằng một con số — núm nào không trả lời được thì nó là núm trang trí, và
# một núm trang trí làm người dùng mất tin vào cả bảng.
#
# BẢY NÚM ĐÃ BỎ, và đây là lý do từng cái:
#
#   độ dày từ khoá   xoay sang "dày" đổi ĐÚNG 0/60 bản. Nó cũng dựa trên một
#                    thứ không có thật: không nhà cung cấp ATS nào công bố
#                    công thức "keyword density".
#   giọng văn        6/26 câu có chủ ngữ để lược. Lược chủ ngữ là quy ước CV
#                    ai cũng theo — bày ra để chọn là bày một câu hỏi không
#                    ai muốn trả lời.
#   bố cục           đổi 19 -> 22 bản, nhưng "mấy dòng mỗi khối" là câu hỏi
#                    của người dàn trang, không phải của người tìm việc.
#   giữ câu kể thất bại · giữ câu ý kiến · giữ câu mời nghi ngờ ·
#   giữ mục kỹ năng mềm · giữ mọi khối kinh nghiệm
#                    năm công tắc lật lại năm LUẬT. Luật đúng trong đa số
#                    trường hợp và đã có số đo hậu thuẫn; bày ra để lật là
#                    bắt người dùng học năm luật trước khi dùng được app.
#                    Giờ chúng chạy cố định theo mặc định đã đo, và bản chấm
#                    điểm (report.py) vẫn nói rõ câu nào bị bỏ vì sao.
#
# Người dùng cần đúng hai thứ: bản CV riêng cho từng tin tới mức nào, và máy
# có tự lo phần nó lo được hay không.

CV_RIENG = "cv_rieng"
RIENG = {"chung": "một bản dùng chung cho nhiều tin",
         "vua": "xếp mục kỹ năng theo tin",
         "rieng": "xếp cả món trong từng mục"}

# TỰ LO — máy làm sẵn mọi phần nó làm được, không đợi bấm.
#
#   1  mọi chỗ hụt nhãn VIẾT đều có bản nháp dựng sẵn, chờ điền bằng chứng
#   2  chữ trên CV vừa đổi thì dựng lại toàn bộ bản CV ngay, chạy nền
#
# Phần DUY NHẤT máy không tự lo được là con số: bao nhiêu cái, trên bao nhiêu
# dữ liệu, đổi được mấy phần. Máy không biết người dùng đã làm gì, và câu
# trên CV là câu họ phải đỡ được trong phòng phỏng vấn.
#
# KHÔNG nằm trong `cv_nut` — xem `cv/batch.stamp`. Núm này không đổi bản dựng
# RA GÌ, nó chỉ đổi LÚC dựng; nhét vào dấu thì bật/tắt nó là mọi bản bỗng bị
# coi là cũ, mà chúng y hệt nhau.
CV_TU_LO = "cv_tu_lo"


DEFAULTS = {AUTORUN: "0", SCAN_EVERY: "60",
            HOURS_FROM: "8", HOURS_TO: "22", PACE: "thuong",
            SRC_BOARD: "1", SRC_LINKEDIN: "1", SRC_ALERT: "1", LI_DONE: "", LI_LEVELS: "", MAIL_DAYS: "30",
            CV_TU_LO: "0", CV_RIENG: "rieng",
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
