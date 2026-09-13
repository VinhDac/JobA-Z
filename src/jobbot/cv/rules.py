"""Luật viết CV — rút ra từ việc soi CV thật đang bị từ chối.

Đây là luật ÁP CHO MỌI JD, không phải bản sửa tay một lần.

Nguyên tắc chia tầng:
    CV            -> bằng chứng khớp, quét được   -> qua vòng lọc
    Trang project -> chiều sâu, cả chỗ làm sai    -> được gọi phỏng vấn
    Phỏng vấn     -> triết lý

Nên câu tự phê bình KHÔNG bị xoá — nó chuyển sang trang project ở bước 4.
"""

from __future__ import annotations

import re

# --- câu không thuộc CV (nhưng thuộc trang project) ---------------------

# Tự phê bình / kể thất bại. Trung thực rất giá trị — ở vòng phỏng vấn.
# Người đọc 200 CV một buổi chiều chỉ nhớ đúng câu tệ nhất.
# CHỈ bắt THẤT BẠI VỀ KẾT QUẢ của bản thân — không bắt kiến thức kỹ thuật.
#
# Phân biệt này quan trọng:
#   "A random train/test split leaks"        -> KIẾN THỨC, giữ. Đây là thứ mạnh nhất.
#   "Live drawdown ran 30% deeper"           -> KẾT QUẢ HỎNG, chuyển sang trang project
#
# Bản đầu tôi bắt cả chữ "leaks" nên bỏ mất phần chuyên môn giá trị nhất.
# KẾT CỤC XẤU CỦA CHÍNH MÌNH — luật CẤU TRÚC, không phải bảng tra.
#
# Bản cũ là một danh sách câu CHÉP TỪ HỒ SƠ CỦA MỘT NGƯỜI: "i was optimising
# for peak", "made money while my first choice did not", "nobody has
# exploited". Đo trên hai hồ sơ khác: bắt 0/5 câu, dù cả hai đều có câu kể
# thất bại rõ ràng ("I honestly struggled with the first rebuild and it
# shipped two weeks late"). Một bảng tra đội lốt một cái luật.
#
# Luật thật chỉ có hai vế: một TỪ CHỈ KẾT CỤC XẤU, và nó KHÔNG nằm trong câu
# kể chuyện mình xử lý chuyện xấu đó. "Prevented data leakage" là khoe việc,
# "my design leaked memory" là kể thất bại — cùng chữ `leak`, khác vế thứ hai.
# CHỈ NHẬN DẠNG QUÁ KHỨ. Đây là vế thứ ba, và thiếu nó thì luật bắt nhầm
# đúng câu mạnh nhất:
#
#     "My first design leaked memory"          -> chuyện ĐÃ XẢY RA với mình
#     "A random train/test split leaks"        -> SỰ THẬT CHUNG về cách nó chạy
#
# Cùng gốc `leak`, khác thì. Tác giả luật gốc đã ghi lại đúng cái bẫy này —
# "bản đầu tôi bắt cả chữ leaks nên bỏ mất phần chuyên môn giá trị nhất" — và
# bản cấu trúc đầu tiên của tôi giẫm lại y nguyên. Nên bảng dưới KHÔNG có
# dạng hiện tại: không `fails`, không `leaks`, không `breaks`.
KET_XAU = re.compile(
    r"\b(failed|failures?|struggled|mistakes?|fault|"
    r"broke|broken|leaked|lost|missed|went wrong|"
    r"gave up|abandoned|could ?n[o']t|did ?n[o']t|was ?n[o']t|"
    r"ran out|rolled back|deeper than|fell short|got lucky|"
    r"shipped .{0,12}late|too late|over budget)\b", re.I)

# Động từ XỬ LÝ: có chúng thì từ kết cục xấu đang mô tả thứ mình NGĂN được,
# không phải thứ mình gây ra. "Detected and fixed a memory leak" là khoe việc.
XU_LY = re.compile(
    r"\b(prevent\w*|avoid\w*|handl\w*|reduc\w*|fix(?:ed|es|ing)?|"
    r"catch\w*|caught|detect\w*|mitigat\w*|eliminat\w*|guard\w*|"
    r"protect\w*|recover\w*|debug\w*|diagnos\w*|resolv\w*)\b", re.I)


def ke_that_bai(text: str) -> bool:
    """Câu này có đang kể một kết cục XẤU của chính mình không."""
    return bool(KET_XAU.search(text)) and not XU_LY.search(text)


# Chữ nút bấm dính vào câu khi trích từ PDF ("Demo MetaTrader's backtester...")
LINK_NOISE = re.compile(r"^\s*(demo|live|code|live walkthrough|link)\s+", re.I)

# Ý KIẾN — và đây là chỗ luật cũ sai NẶNG NHẤT, nên bản mới không đoán nữa.
#
# Bản cũ: một danh sách chín cụm chép từ hồ sơ một người ("means nothing",
# "nobody has exploited", "rather than betting"). Hồ sơ khác thì bắt 0 câu,
# dù có câu ý kiến rành rành ("Good code is code other people can delete").
#
# Nhưng ý kiến KHÔNG phân biệt được với KIẾN THỨC bằng luật rẻ tiền, mà
# rules.py nói rõ kiến thức là thứ MẠNH NHẤT của một CV kỹ thuật:
#
#     "A random train/test split leaks, because adjacent dates are correlated"
#         -> KIẾN THỨC. Giữ. Đây là thứ phân biệt người làm thật.
#     "Good code is code other people can delete"
#         -> Ý KIẾN. Không chứng minh gì.
#
# Hai câu cùng hình dạng: hiện tại đơn, không số, không hành động. Máy đoán là
# máy đoán sai một trong hai, mà đoán sai nghĩa là XOÁ một câu mạnh nhất.
#
# Nên máy KHÔNG xoá nữa, nó HỎI. Ba dấu hiệu, thiếu cả ba thì đánh dấu "xem
# lại" để người dùng tự quyết — người viết biết câu đó là kiến thức hay là
# lời hay ý đẹp, còn máy thì không.


def khong_ke_viec(text: str, tags: list[str] | None = None) -> bool:
    """Câu này KHÔNG kể việc bạn làm, KHÔNG có số, KHÔNG nhắc kỹ năng nào.

    Thiếu cả ba thì nó có thể là kiến thức đáng giá, cũng có thể là lời hay ý
    đẹp. Máy không phân biệt được — nên nó đánh dấu, không xoá.
    """
    return not (mo_bang_hanh_dong(text)
                or HAS_NUMBER.search(text)
                or (tags or []))


# Câu mời người đọc nghi ngờ chính mình
RISKY = re.compile(
    r"\b(claude code|copilot|codex|chatgpt|prompt|ai (?:tool|assistant)|"
    r"self-funded|own capital|demo account)\b", re.I)

# MỤC KỸ NĂNG NÊN BỎ — nhận bằng NỘI DUNG, không bằng tên mục.
#
# Bản cũ: `{"compute", "method"}` — đúng hai tên mục trong CV của một người.
# Hồ sơ khác thì nó bỏ sót đúng mục đáng bỏ nhất: "Soft — communication,
# teamwork" trên CV của một data analyst, hay "Interests — chess, running".
#
# Luật thật: một mục kỹ năng đáng in ra khi nó kể được KỸ NĂNG máy nhận ra.
# Mục mà cả dòng không có lấy một cái tên công nghệ nào thì nó đang chiếm chỗ
# bằng tính từ.
def bo_muc_ky_nang(title: str, body: str) -> bool:
    """Mục kỹ năng này có đáng in ra không — xét NỘI DUNG."""
    from .build import skills_in
    if skills_in(body):
        return False
    # Không nhận ra kỹ năng nào: có thể là mục mềm ("teamwork"), có thể là
    # công nghệ máy chưa biết tên. Chỉ bỏ khi tên mục cũng báo là mục mềm —
    # bỏ nhầm một mục công nghệ lạ thì mất thật.
    return bool(MUC_MEM.search(title or ""))


# Tên mục báo hiệu "không phải kỹ năng kỹ thuật".
MUC_MEM = re.compile(
    r"\b(soft|interests?|hobbies|personal|languages? spoken|activities|"
    r"volunteering|references?|about|profile|strengths?)\b", re.I)

# --- dấu hiệu câu TỐT cho CV --------------------------------------------

# Cho phép "I "/"We " đứng trước — CV thật rất hay viết "I built…", và neo cứng
# ở đầu câu làm hụt mất phần lớn dòng có động từ hành động.
# ĐỘNG TỪ HÀNH ĐỘNG mở đầu câu — nhận dạng bằng HÌNH THÁI, không bằng danh
# sách gõ tay.
#
# Danh sách cũ có 21 từ, chọn theo một hồ sơ quant: nó không có `detected`,
# `fixed`, `migrated`, `owned`, `shipped`, `launched`, `scaled`, `refactored`,
# `mentored`… Hồ sơ của một kỹ sư backend hay một người marketing thì phần
# lớn câu khoe việc rơi ra ngoài, và máy tưởng họ không kể việc mình làm.
#
# Luật thật: câu CV viết theo lối lược chủ ngữ thì mở đầu bằng một động từ
# QUÁ KHỨ. Nhận quá khứ bằng hai dấu hiệu, đủ cho tiếng Anh: đuôi `-ed`, hoặc
# nằm trong bảng bất quy tắc. Bảng đó đã có sẵn ở cv/rewrite.py — dùng lại,
# không chép ra bản thứ hai để rồi hai bản trôi khỏi nhau.
_BAT_QUY_TAC = (
    "built", "rebuilt", "wrote", "rewrote", "chose", "ran", "led", "made",
    "took", "set", "kept", "found", "put", "sent", "sold", "won", "cut",
    "held", "grew", "drew", "spent", "taught", "brought", "began", "drove",
    "shipped", "ran", "oversaw", "rebuilt", "sped",
)
ACTION_VERB = re.compile(
    r"^(?:i|we)?\s*(?:\w+ed|" + "|".join(_BAT_QUY_TAC) + r")\b", re.I)

# Vài từ đuôi -ed KHÔNG phải động từ mở đầu — chúng là tính từ, và câu bắt
# đầu bằng chúng là câu tả chứ không phải câu khoe việc.
KHONG_PHAI_DONG_TU = re.compile(
    r"^(?:advanced|detailed|dedicated|experienced|skilled|motivated|"
    r"focused|based|related|mixed|limited|combined|applied statistics)\b", re.I)


def mo_bang_hanh_dong(text: str) -> bool:
    """Câu này có mở đầu bằng một động từ hành động không."""
    t = text.strip()
    return bool(ACTION_VERB.match(t)) and not KHONG_PHAI_DONG_TU.match(t)


HAS_NUMBER = re.compile(r"\b\d[\d,.]*\s*(%|years?|instruments?|models?|strategies|x)?\b")

# Ngân sách một trang giấy
BUDGET = {"experience": 2, "exp_bullets": 3, "project": 3, "skill": 4}


def clean(text: str) -> str:
    """Bỏ chữ nút bấm dính vào đầu câu khi trích từ PDF."""
    out = LINK_NOISE.sub("", text).strip()
    return re.sub(r"\s*·?\s*(Demo|Live|code|Live walkthrough)\s*$", "", out).strip()


def sentence_ok(text: str, tags: list[str] | None = None,
                giu: set | None = None) -> tuple[str, str]:
    """Câu này lên CV được không: keep | review | drop, kèm lý do.

    `review` = giữ lại nhưng đánh dấu để Vin tự quyết. Dùng khi câu vừa có
    bằng chứng cứng (số liệu, kỹ năng) vừa có chữ dễ gây hiểu lầm — vứt cả câu
    thì mất luôn con số, mà im lặng giữ thì giấu rủi ro.
    """
    # `giu` = mấy luật NGƯỜI DÙNG ĐÃ TẮT. Luật vẫn đúng trong đa số trường
    # hợp, nhưng nó không biết hoàn cảnh — nên người dùng phải lật được.
    # TỰ TÍNH `tags` NẾU KHÔNG ĐƯỢC TRUYỀN. Trước đây thiếu tham số nghĩa là
    # "câu này không có kỹ năng nào", nên CÙNG MỘT CÂU ra hai phán quyết tuỳ
    # người gọi có nhớ truyền hay không: "A random train/test split leaks…"
    # ra `keep` khi có tags và `review` khi không. Một cái luật mà kết quả
    # phụ thuộc chữ ký lời gọi thì không phải luật.
    if tags is None:
        from .build import skills_in
        tags = sorted(skills_in(text))
    giu = giu or set()
    if ke_that_bai(text) and "that_bai" not in giu:
        return "drop", "outcome failure — belongs on the project page, not the CV"
    if len(text) < 30:
        return "drop", "too short to carry evidence"
    # KHÔNG XOÁ, HỎI. Xem lời chú ở `khong_ke_viec`: ý kiến và kiến thức cùng
    # hình dạng, mà kiến thức là thứ mạnh nhất của một CV kỹ thuật.
    if khong_ke_viec(text, tags) and "y_kien" not in giu:
        return "review", ("không kể việc bạn LÀM, không có số đo, không nhắc "
                          "kỹ năng nào — đây là kiến thức đáng giá hay chỉ là "
                          "một câu hay? bạn quyết")
    if RISKY.search(text) and "rui_ro" not in giu:
        strong = bool(HAS_NUMBER.search(text)) or len(tags or []) >= 2
        if strong:
            return "review", "has hard evidence but wording may read badly — your call"
        return "drop", "invites the reader to doubt you"
    return "keep", ""


def sentence_weight(text: str, wanted: set[str], tags: list[str],
                    khoa: float = 3.0) -> float:
    """Câu này đáng lên CV đến mức nào, cho JD đang xét.

    `khoa` là trọng số của "trúng thứ tin đòi" — núm "độ dày từ khoá" ở tấm
    Điều chỉnh xoay đúng số này. Dày lên thì máy ưu tiên câu trúng từ khoá;
    nhẹ đi thì ưu tiên câu mạnh về nội dung dù không trúng từ nào.

    Nó KHÔNG nhồi từ khoá vào CV: máy không thêm từ nào. Nó chỉ đổi THỨ TỰ
    ƯU TIÊN giữa mấy câu Vin đã viết.
    """
    score = 0.0
    score += khoa * len(wanted & set(tags))       # trúng thứ JD đòi
    score += 1.0 * len(tags)                      # có nội dung kỹ thuật
    if mo_bang_hanh_dong(text):
        score += 1.5                              # mở đầu bằng động từ hành động
    if HAS_NUMBER.search(text):
        score += 1.0                              # có số
    if len(text) > 220:
        score -= 1.0                              # dài quá thì không quét được
    return score
