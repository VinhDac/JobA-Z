"""Lọc tin theo hồ sơ — và LUÔN nói được vì sao bỏ.

Không bao giờ bỏ im lặng. Mỗi tin bị loại đều ghi drop_reason, để sau này
nhìn lại biết bộ lọc quá chặt ở đâu. Bỏ im lặng là cách chắc chắn nhất để
mất tin tốt mà không bao giờ biết.
"""

from __future__ import annotations

import re

from .base import Posting, norm

# Dấu hiệu cấp cao. Chỉ loại khi thấy RÕ RÀNG — "Analyst" trong tài chính
# thường là entry level, không phải cấp cao.
SENIOR_WORDS = {
    "senior", "snr", "sr", "lead", "principal", "staff", "head", "director",
    "chief", "vp", "vice president", "manager", "architect", "expert", "specialist ii",
}
# LỖI ĐÃ SỬA: "analyst" từng nằm ở đây, làm mọi tin "Senior ... Analyst" lọt qua
# vì ngoại lệ luôn kích hoạt. Trong tài chính "Analyst" là chức danh phổ biến ở
# MỌI cấp, nên nó không phải dấu hiệu junior.
JUNIOR_WORDS = {
    "graduate", "grad", "junior", "jr", "intern", "internship", "placement",
    "entry", "trainee", "apprentice", "campus", "early career",
}

# MỘT bảng nơi chốn cho cả app. Trước đây có HAI: `linkedin.MARKET_PLACE`
# bảo TÌM ở đâu, `filter.UK_WORDS` bảo GIỮ cái gì — hai bảng rời nhau, và
# chúng lệch nhau mà không ai biết cho tới lúc ngồi đếm.
#
#   place  chữ gửi cho LinkedIn
#   manh   dấu hiệu CHẮC CHẮN thuộc vùng này
#   thanh  tên thành phố — đúng, nhưng ĐỤNG TÊN với nơi khác
NOI = {
    "uk": {
        "ten": "UK",
        "place": "United Kingdom",
        "manh": {"united kingdom", "uk", "gb", "england", "britain",
                 "scotland", "wales"},
        "thanh": {"london", "manchester", "edinburgh", "cambridge", "oxford",
                  "bristol", "leeds", "birmingham", "glasgow"},
    },
    "eu": {
        "ten": "EU",
        "place": "European Union",
        "manh": {"european union", "eu", "germany", "france", "netherlands",
                 "ireland", "spain", "italy", "poland", "portugal", "sweden"},
        "thanh": {"berlin", "paris", "amsterdam", "dublin", "madrid", "lisbon",
                  "munich", "warsaw", "stockholm"},
    },
    "us": {
        "ten": "US",
        "place": "United States",
        "manh": {"united states", "usa", "us"},
        "thanh": {"new york", "san francisco", "boston", "chicago", "seattle",
                  "austin", "washington"},
    },
}

# Mã bang Mỹ đứng sau dấu phẩy. CHỐT CHẶN cho tên thành phố đụng nhau:
# "Birmingham, AL" là Alabama, không phải Birmingham của Anh — mà nó đang nằm
# trong danh sách việc UK của Vin (đo ngày 12/09, tin Mission Pet Health).
# Đo tác dụng: loại đúng 2 tin sai, giữ nguyên 313 tin đúng.
BANG_MY = re.compile(
    r",\s*(A[LKZR]|C[AOT]|DE|FL|GA|HI|I[DLNA]|K[SY]|LA|M[EDAINSOT]|N[EVHJMYCD]"
    r"|OH|OK|OR|PA|RI|S[CD]|TN|TX|UT|V[TA]|W[AVIY]|DC)\b")

EU_REMOTE_WORDS = {"europe", "emea", "anywhere", "worldwide", "global", "remote"}


def o_vung(text: str, key: str) -> bool:
    """Chuỗi địa điểm này có thuộc vùng `key` không.

    Dấu hiệu MẠNH thì tin ngay. Tên THÀNH PHỐ thì tin, trừ khi trong chuỗi có
    mã bang Mỹ — lúc đó nó là thành phố trùng tên ở Mỹ.
    """
    vung = NOI.get(key)
    if not vung:
        return False
    if _names_in(text, vung["manh"]):
        return True
    return bool(vung["thanh"]) and _names_in(text, vung["thanh"])


def noi_o(location: str) -> str:
    """Bạn ĐANG Ở vùng nào — suy từ ô "Where you're based" trong hồ sơ.

    Đây là việc mà ô đó vẫn hứa ("Used to filter on-site and hybrid roles by
    commute") nhưng chưa bao giờ làm: cho tới hôm nay không một dòng nào trong
    tìm/lọc đọc nó, chỉ CV và điền form dùng. Còn "UK" thì bị đóng cứng ở ba
    chỗ khác nhau trong mã nguồn, tức là app mặc định ai dùng cũng ở Anh.

    Không đoán ra thì trả rỗng, và người gọi giữ nguyên nếp cũ — không được
    tự ý đổi thứ đang giữ chỉ vì một ô hồ sơ viết lạ.
    """
    text = norm(location or "")
    if not text:
        return ""
    for key in NOI:
        if _names_in(text, NOI[key]["manh"]) or _names_in(text, NOI[key]["thanh"]):
            return key
    return ""


def _titles(answers: dict) -> list[str]:
    raw = answers.get("job_titles") or ""
    return [norm(line) for line in raw.splitlines() if line.strip()]


def title_hit(posting: Posting, targets: list[str]) -> str | None:
    """Chức danh tin có chứa chức danh nào mình nhắm không."""
    text = norm(posting.title)
    return next((t for t in targets if t and t in text), None)


def seniority_ok(posting: Posting, accepted: list[str]) -> bool:
    """Nhắm junior mà tin ghi rõ Senior/Lead/Head thì bỏ."""
    wants_junior = bool({"intern", "grad", "grad_scheme", "junior"} & set(accepted))
    if not wants_junior:
        return True
    text = norm(posting.title)
    if any(f" {w} " in f" {text} " for w in SENIOR_WORDS):
        # Trừ khi tin ghi CẢ hai — "Graduate to Senior Analyst" thì vẫn nhận.
        return any(f" {w} " in f" {text} " for w in JUNIOR_WORDS)
    return True


def _names_in(text: str, names: set[str]) -> bool:
    """Tên địa danh khớp theo TỪ, không theo chuỗi con.

    'uk' nằm trong 'ukraine', 'gb' nằm trong 'gbagada' — trên DB thật có 17
    tin ở Paris, Köln, Bremen lọt qua bộ lọc địa điểm kiểu này. norm() đã đổi
    dấu câu thành khoảng trắng rồi, nên chỉ cần đệm hai đầu là đủ.
    """
    padded = f" {text} "
    return any(f" {name} " in padded for name in names)


# Ô "thị trường" trong hồ sơ nói NGƯỜI DÙNG NHẬN VIỆC Ở ĐÂU. Mỗi lựa chọn
# mở thêm một vùng; hai lựa chọn cuối bỏ hẳn chốt địa điểm.
#
# MỘT CHỖ DỊCH, dùng chung với `NOI`. Bên LinkedIn có bảng MARKET_PLACE dịch
# đúng mấy khoá này sang nơi để đi tìm ("us_remote" -> "United States") —
# hai bảng thì có ngày app đi tìm ở Mỹ rồi tự vứt sạch kết quả, mà đó CHÍNH
# LÀ chuyện đã xảy ra.
THI_TRUONG = {"uk_onsite": {"uk"}, "uk_remote": {"uk"},
              "eu_remote": {"eu"}, "us_remote": {"us"},
              "global_remote": set(NOI), "relocate": set(NOI)}


def vung_nhan(markets: list[str], nha: str = "uk") -> set:
    """Những vùng người dùng chịu nhận việc: chỗ đang ở + mọi thị trường đã chọn."""
    ra = {nha}
    for m in markets or ():
        ra |= THI_TRUONG.get(str(m).strip().lower(), set())
    return ra


def location_ok(posting: Posting, markets: list[str], nha: str = "uk") -> bool:
    """Việc này có ở CHỖ MÌNH KHÔNG — "chỗ mình" gồm cả thị trường đã chọn.

    `nha` là vùng người dùng đang ở, suy từ ô "Where you're based".

    `markets` LÀ THAM SỐ CÓ THẬT, không phải trang trí. Bản trước nhận nó rồi
    không đọc một lần nào: hồ sơ chọn "US — remote" mà tin New York vẫn bị
    vứt với lý do "outside your area (UK)". Tệ hơn, LinkedIn dịch đúng mấy
    khoá đó thành nơi đi tìm — nên app đi tìm ở Mỹ rồi tự ném sạch kết quả
    về, và người dùng chỉ thấy "không có việc nào".
    """
    nhan = vung_nhan(markets, nha)
    text = norm(f"{posting.location} {posting.company}")
    # Mã bang Mỹ thì chặn phần khớp theo TÊN THÀNH PHỐ: "Birmingham, AL" là
    # Alabama. Dấu hiệu MẠNH vẫn được tin — "London, New York" có chữ
    # "london" là tên thành phố, nhưng nếu đâu đó ghi "United Kingdom" thì
    # đó là chắc chắn.
    # Mã bang Mỹ chỉ là dấu hiệu nhiễu KHI người dùng không nhận việc ở Mỹ:
    # "Birmingham, AL" là Alabama, không phải Birmingham của Anh. Ai đã chọn
    # us_remote thì đó lại chính là thứ họ muốn.
    if "us" not in nhan and BANG_MY.search(posting.location or ""):
        vung = NOI.get(nha) or {}
        if not _names_in(text, vung.get("manh", set())):
            return False
    for v in nhan:
        if o_vung(text, v):
            return True
    # Tin ghi "Remote" trống trơn: giữ nếu người dùng có nhận việc từ xa ở
    # BẤT KỲ vùng nào ngoài chỗ đang ở — không thì nó chỉ là tin remote nội địa.
    if posting.remote and _names_in(text, EU_REMOTE_WORDS):
        return True
    if len(nhan) > 1 and (posting.remote or _names_in(text, EU_REMOTE_WORDS)):
        return True
    return False


def judge(posting: Posting, answers: dict) -> tuple[bool, str]:
    """Trả về (giữ, lý do). Lý do luôn có, kể cả khi giữ."""
    targets = _titles(answers)
    if not targets:
        return True, "no job_titles set — keeping everything"

    hit = title_hit(posting, targets)
    if not hit:
        return False, "title does not match any target title"
    if not seniority_ok(posting, answers.get("seniority") or []):
        return False, "title is senior level — you target graduate/junior"
    # Nơi ở suy từ hồ sơ; không đoán được thì giữ nếp cũ (UK) chứ không tự ý
    # đổi thứ đang giữ chỉ vì một ô viết lạ.
    nha = noi_o(answers.get("location") or "") or "uk"
    if not location_ok(posting, answers.get("markets") or [], nha):
        return False, (f"location '{posting.location or 'unknown'}' outside"
                       f" your area ({NOI[nha]['ten']})")
    return True, f"matched target title '{hit}'"
