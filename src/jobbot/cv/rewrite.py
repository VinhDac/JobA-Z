"""Sửa câu CV — CHỈ BẰNG CHÍNH CHỮ CỦA VIN.

Luật gốc của cả tầng CV (xem build.py): *mọi câu trên CV đều là câu Vin đã
viết*. Module này không phá luật đó, nó làm rõ luật đó ra thành hai việc khác
hẳn nhau:

    BIẾN ĐỔI   cắt và xếp lại chữ đã có     -> máy tự làm, thêm 0 sự thật
    ĐIỂM YẾU   chỉ ra chỗ câu còn hổng      -> máy chỉ NÓI, Vin tự viết

Ranh giới nằm ở đúng một câu hỏi: *câu sau khi sửa có khẳng định thêm điều gì
Vin chưa từng viết không?* Bỏ chữ "I" ở đầu thì không. Thêm "resulting in a
30% improvement" thì có — và đó là câu Vin phải đỡ trước mặt người phỏng vấn
mà không phải Vin viết. Nên chỗ đó máy dừng lại.

VÌ SAO KHÔNG PHẪU THUẬT DẤU HAI CHẤM. Đo trên CV thật: 5/16 câu sống sót có
dấu hai chấm trong 60 ký tự đầu, và nhìn vào thì phần TRƯỚC dấu hai chấm mới
là ý chính ("The fix was not a better parameter but better normalisation: …").
Cắt tự động là giết nghĩa. Nên câu dài bị ĐÁNH DẤU, không bị cắt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import rules

# --- BIẾN ĐỔI -----------------------------------------------------------

# Quá khứ BẤT QUY TẮC hay gặp trong CV. Cần bảng này vì luật "đuôi -ed" không
# bắt được "built", "wrote", "chose". Đây là hình thái học, không phải bảng
# khớp theo CV của Vin — thêm câu mới vẫn đúng.
QUA_KHU = (
    "built", "rebuilt", "wrote", "rewrote", "chose", "ran", "led", "made",
    "took", "set", "kept", "found", "put", "sent", "sold", "won", "cut",
    "held", "grew", "drew", "spent", "taught", "brought", "began",
)

# "I <động từ quá khứ>" ở ĐẦU câu. Chỉ ở đầu câu: sửa giữa câu ("…, so I chose
# on average risk/return") là đổi cấu trúc câu, không còn là cắt chữ nữa.
#
# KHÔNG bắt trợ động từ. "I was optimising" -> "Was optimising" là sai ngữ
# pháp, mà luật -ed/bất-quy-tắc tự loại chúng: "was", "had", "could" không có
# đuôi -ed và không nằm trong bảng trên.
NGOI_MOT = re.compile(
    r"^\s*I\s+(?=(\w+ed|" + "|".join(QUA_KHU) + r")\b)", re.I)


@dataclass
class Sua:
    """Một phép biến đổi đã áp, đủ để Vin kiểm lại bằng mắt."""
    phep: str           # mã phép, để test và để nhóm
    truoc: str
    sau: str
    vi_sao: str         # nói cho NGƯỜI đọc, không phải cho máy


def _chu_ngu(text: str) -> tuple[str, str]:
    """Lược chủ ngữ ngôi thứ nhất — quy ước của CV.

    CV không viết "I built X", nó viết "Built X": người đọc đã biết cả tờ giấy
    nói về ai. Hai chữ đầu là chỗ đắt nhất của một dòng CV, và "I " không mang
    bằng chứng nào.
    """
    moi = NGOI_MOT.sub("", text)
    if moi == text:
        return text, ""
    moi = moi[0].upper() + moi[1:]
    return moi, ("CV lược chủ ngữ — cả tờ giấy đã nói về bạn rồi, nên hai chữ "
                 "đầu dành cho việc bạn làm, không dành cho đại từ")


def _hoa_dau(text: str) -> tuple[str, str]:
    """Hoa chữ đầu câu.

    Câu chữ thường ở đầu là mảnh vụn lúc bóc từ PDF, không phải chủ ý — đo
    được một câu như vậy trong hồ sơ thật ("the whole pipeline turned into…").
    Trên CV nó đọc như lỗi chính tả, và người đọc 200 CV một buổi chiều thì
    một lỗi chính tả là đủ.
    """
    if not text or not text[0].islower():
        return text, ""
    return text[0].upper() + text[1:], ("chữ đầu câu bị thường — mảnh vụn lúc "
                                        "bóc từ PDF, trên CV nó đọc như lỗi")


# Thứ tự CÓ Ý: lược chủ ngữ trước, hoa đầu sau — bỏ "I" xong thì chữ mới đứng
# đầu và có thể đang là chữ thường.
PHEP = (("chu_ngu", _chu_ngu), ("hoa_dau", _hoa_dau))


def sua(text: str, giong: str = "cv") -> tuple[str, list[Sua]]:
    """Câu sau khi sửa, kèm danh sách phép đã áp.

    Không phép nào áp được thì trả về đúng câu cũ và danh sách rỗng — người
    gọi phân biệt "đã sửa" với "không cần sửa" bằng chỗ đó.

    `giong` = "nguyen" thì KHÔNG lược chủ ngữ — Vin muốn giữ đúng giọng mình
    viết. Rác PDF và chữ đầu câu bị thường vẫn sửa: đó là lỗi bóc tệp, không
    phải giọng văn, và không ai chọn giữ một lỗi chính tả.
    """
    ra = rules.clean(text)          # rác PDF ở đầu/cuối — luật đã có sẵn
    da: list[Sua] = []
    if ra != text:
        da.append(Sua("rac_pdf", text, ra,
                      "chữ nút bấm dính vào câu lúc bóc từ PDF"))
    for ma, phep in PHEP:
        if ma == "chu_ngu" and giong == "nguyen":
            continue
        truoc = ra
        ra, vi_sao = phep(ra)
        if vi_sao:
            da.append(Sua(ma, truoc, ra, vi_sao))
    return ra, da


# --- ĐIỂM YẾU: máy CHỈ RA, Vin tự viết ----------------------------------

DAI_NHAT = 200          # quá ngần này thì mắt người đọc trượt qua cả dòng


@dataclass
class Yeu:
    ma: str
    noi: str            # điểm yếu là gì
    lam_gi: str         # sửa thế nào — phải là việc làm được, không phải lời khuyên


def diem_yeu(text: str, tags: list[str], wanted: set[str]) -> list[Yeu]:
    """Câu này còn hổng chỗ nào. KHÔNG sửa gì — chỉ nói.

    Đây là nửa mà máy không được làm thay. Một câu thiếu số đo thì thứ nó
    thiếu là MỘT CON SỐ THẬT, và con số đó chỉ Vin biết. Máy bịa vào là đẻ ra
    câu Vin không đỡ được lúc phỏng vấn — nên máy chỉ trỏ vào chỗ trống.
    """
    ra: list[Yeu] = []
    # MỘT CÂU CV LÀ MỘT TRONG HAI THỨ, và chúng đòi hai chuẩn khác nhau:
    #
    #   KHOE VIỆC  "Built two systems…"  -> phải kèm con số, không thì lời
    #              khoe không kiểm chứng được
    #   KIẾN THỨC  "A random train/test split leaks, because…"  -> không có
    #              số nào để mà thêm, và rules.py nói đây là thứ MẠNH NHẤT
    #
    # Đo trên hồ sơ thật: 12/16 câu là kiến thức. Đòi số đo ở cả 16 câu thì
    # 12 dấu là báo động giả — và một dấu mà dòng nào cũng có thì nó không
    # còn là dấu, nó là nền. Người dùng học được rằng đừng nhìn dấu nữa.
    khoe_viec = bool(rules.mo_bang_hanh_dong(text))
    if khoe_viec and not rules.HAS_NUMBER.search(text):
        ra.append(Yeu("khong_so",
                      "khoe việc nhưng không có số đo",
                      "thêm một con số thật: bao nhiêu, trên bao nhiêu dữ "
                      "liệu, đổi được mấy phần trăm"))
    # "không mở đầu bằng động từ" ĐÃ BỎ khỏi danh sách điểm yếu: câu kiến thức
    # vốn không mở đầu bằng động từ hành động, nên nó bắt đúng 12/16 câu mạnh
    # nhất của hồ sơ và gọi chúng là lỗi.
    if len(text) > DAI_NHAT:
        ra.append(Yeu("qua_dai",
                      f"dài {len(text)} ký tự",
                      "tách thành hai câu, hoặc cắt phần bối cảnh và giữ "
                      "phần bạn làm"))
    if tags and wanted and not (set(tags) & wanted):
        ra.append(Yeu("khong_tra_loi",
                      "không chạm yêu cầu nào của tin này",
                      "để dành cho tin khác — hoặc nối nó vào một kỹ năng "
                      "tin này có đòi"))
    return ra


# --- VẾT: CHỖ NÀO trong câu, không phải CÂU NÀO -------------------------
#
# Đây là khác biệt giữa "chấm bài" và "liệt kê lỗi". Gạch chân cả dòng thì
# người đọc vẫn phải tự dò xem chỗ nào hỏng; gạch đúng cụm chữ thì mắt tới
# thẳng chỗ phải sửa. Grammarly có giá trị chính ở chỗ đó.
#
# Không phải điểm yếu nào cũng có đoạn chữ. Thiếu số đo là một chỗ TRỐNG —
# không gạch được cái không có. Nhưng gạch được chỗ CON SỐ ĐÁNG RA PHẢI NẰM:
# cụm động từ khoe việc. "Built two systems" gạch chân, chú thích "bao nhiêu
# cái, trên bao nhiêu dữ liệu" — người đọc biết ngay phải chèn vào đâu.

# Cụm KHOE VIỆC: từ động từ hành động tới hết mệnh đề đầu. Đây là chỗ con số
# thuộc về.
_MENH_DE = re.compile(r"^(.{0,90}?)(?=[,:;]|\s+(?:then|and then|which)\b|$)",
                      re.I | re.S)


@dataclass
class Vet:
    """Một ĐOẠN CHỮ đáng đánh dấu: [dau, cuoi) trong câu."""
    dau: int
    cuoi: int
    loai: str           # 'thieu_so' | 'qua_dai' | 'lac_de' | 'da_sua'
    noi: str            # chỗ này sao
    lam_gi: str         # sửa thế nào


def vet(text: str, tags: list, wanted: set, da_sua=()) -> list:
    """Mọi đoạn chữ đáng đánh dấu trong MỘT câu.

    Trả về theo thứ tự xuất hiện. Đoạn chồng nhau là chuyện thường (một câu
    vừa dài vừa thiếu số), người vẽ tự gộp.
    """
    ra: list = []

    # 1. MÁY ĐÃ SỬA — đánh dấu chữ đầu, vì đó là chỗ chữ "I" vừa bị cắt.
    if da_sua:
        het = text.find(" ")
        ra.append(Vet(0, het if het > 0 else len(text), "da_sua",
                      "máy đã sửa chữ ở đây",
                      " · ".join(x.vi_sao for x in da_sua)))

    # 2. KHOE VIỆC MÀ THIẾU SỐ — gạch đúng cụm động từ, chỗ con số thuộc về.
    if rules.mo_bang_hanh_dong(text) and not rules.HAS_NUMBER.search(text):
        m = _MENH_DE.match(text)
        if m and m.end() > 3:
            ra.append(Vet(0, m.end(), "thieu_so",
                          "khoe việc mà không có số đo",
                          "chèn một con số thật vào đúng đây: bao nhiêu cái, "
                          "trên bao nhiêu dữ liệu, đổi được mấy phần trăm"))

    # 3. QUÁ DÀI — gạch ĐÚNG PHẦN THỪA, từ chỗ mắt người đọc bắt đầu trượt.
    if len(text) > DAI_NHAT:
        ra.append(Vet(DAI_NHAT, len(text), "qua_dai",
                      f"từ đây là phần thứ {len(text) - DAI_NHAT} ký tự vượt trần",
                      "cắt phần bối cảnh, giữ phần bạn LÀM — hoặc tách hai câu"))

    # 4. KHÔNG CHẠM TIN NÀY — cả câu, vì vấn đề là của cả câu.
    if tags and wanted and not (set(tags) & set(wanted)):
        ra.append(Vet(0, len(text), "lac_de",
                      "không chạm yêu cầu nào của tin này",
                      "để dành cho tin khác, hoặc đổi sang câu có trúng"))
    return sorted(ra, key=lambda v: (v.dau, -v.cuoi))

