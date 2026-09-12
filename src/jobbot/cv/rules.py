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
SELF_CRITIQUE = re.compile(
    r"(the mistake was mine|my (?:own )?(?:mistake|fault)|"
    r"(?:the )?capital ran out|ran out before|"
    r"i (?:never|failed to|could ?n[o']t)\b|"
    r"broke my own|did ?n[o']t work|got lucky|"
    r"\bdeeper than (?:the |my )?(?:model|expected|predicted)|"
    r"i was optimising for peak|i was optimizing for peak|"
    r"made money while my first choice did not)", re.I)

# Chữ nút bấm dính vào câu khi trích từ PDF ("Demo MetaTrader's backtester...")
LINK_NOISE = re.compile(r"^\s*(demo|live|code|live walkthrough|link)\s+", re.I)

# Ý kiến / triết lý, không phải bằng chứng năng lực
OPINION = re.compile(
    r"\b(means nothing|teaches you|i want to do|i worked the rest out|"
    r"is already a lot|nobody has exploited|the work i want|"
    r"rather than betting|matters more than)\b", re.I)

# Câu mời người đọc nghi ngờ chính mình
RISKY = re.compile(
    r"\b(claude code|copilot|codex|chatgpt|prompt|ai (?:tool|assistant)|"
    r"self-funded|own capital|demo account)\b", re.I)

# Khối kỹ năng nên bỏ hẳn: dạy người đọc kiến thức cơ bản = tín hiệu non tay
DROP_SKILL_GROUPS = {"compute", "method"}

# --- dấu hiệu câu TỐT cho CV --------------------------------------------

# Cho phép "I "/"We " đứng trước — CV thật rất hay viết "I built…", và neo cứng
# ở đầu câu làm hụt mất phần lớn dòng có động từ hành động.
ACTION_VERB = re.compile(
    r"^(?:i|we)?\s*(built|designed|implemented|generated|developed|created|wrote|applied|"
    r"validated|tested|analysed|analyzed|modelled|modeled|automated|delivered|"
    r"reduced|improved|led|ran|deployed|classified|normalised|normalized)\b", re.I)
HAS_NUMBER = re.compile(r"\b\d[\d,.]*\s*(%|years?|instruments?|models?|strategies|x)?\b")

# Ngân sách một trang giấy
BUDGET = {"experience": 2, "exp_bullets": 3, "project": 3, "skill": 4}


def clean(text: str) -> str:
    """Bỏ chữ nút bấm dính vào đầu câu khi trích từ PDF."""
    out = LINK_NOISE.sub("", text).strip()
    return re.sub(r"\s*·?\s*(Demo|Live|code|Live walkthrough)\s*$", "", out).strip()


def sentence_ok(text: str, tags: list[str] | None = None) -> tuple[str, str]:
    """Câu này lên CV được không: keep | review | drop, kèm lý do.

    `review` = giữ lại nhưng đánh dấu để Vin tự quyết. Dùng khi câu vừa có
    bằng chứng cứng (số liệu, kỹ năng) vừa có chữ dễ gây hiểu lầm — vứt cả câu
    thì mất luôn con số, mà im lặng giữ thì giấu rủi ro.
    """
    if SELF_CRITIQUE.search(text):
        return "drop", "outcome failure — belongs on the project page, not the CV"
    if OPINION.search(text):
        return "drop", "opinion, not evidence of capability"
    if len(text) < 30:
        return "drop", "too short to carry evidence"
    if RISKY.search(text):
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
    if ACTION_VERB.match(text.strip()):
        score += 1.5                              # mở đầu bằng động từ hành động
    if HAS_NUMBER.search(text):
        score += 1.0                              # có số
    if len(text) > 220:
        score -= 1.0                              # dài quá thì không quét được
    return score
