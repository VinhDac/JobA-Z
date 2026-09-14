"""Thư này nói gì — và nó thuộc lần nộp nào.

Hộp thư RIÊNG cho việc làm nên bài toán nhẹ hẳn: gần như mọi thư đều là thư
tuyển dụng, nên đây là XẾP LOẠI, không phải LỌC. Hộp chính thì phải đoán giữa
hoá đơn, bạn bè, quảng cáo.

Thư ĐỀ XUẤT đổi trạng thái, KHÔNG tự đổi. Một thư "unfortunately" có thể là
từ chối, mà cũng có thể là câu mở đầu của một thư mời phỏng vấn đổi lịch.
Đoán sai mà tự ghi thì bảng thành sai, và Vin không có cách nào biết.
"""

from __future__ import annotations

import re

from ..ingest.base import norm
from .board import INTERVIEW, OFFER, REJECTED, SENT

# Thứ tự QUAN TRỌNG: xét từ kết cục mạnh nhất xuống. Một thư mời phỏng vấn
# thường vẫn mở đầu bằng "thank you for applying" — bắt "confirm" trước là
# xếp nhầm thư quan trọng nhất thành thư xác nhận.
RULES = [
    (OFFER, re.compile(
        r"\b(offer of employment|pleased to offer|we would like to offer|"
        r"offer letter|congratulations[^.]{0,40}offer)\b", re.I)),
    (INTERVIEW, re.compile(
        r"\b(invit\w* (?:you )?(?:to|for) (?:an? )?"
        r"(?:interview|call|chat|conversation)|"
        r"invitation to (?:an? )?interview|interview invitation|"
        r"would like to invite|would like to (?:meet|speak|chat|talk)|"
        r"schedule (?:a |an )?(?:call|interview|chat)|book a time|"
        r"next (?:round|stage)|first[- ]round|online assessment|"
        r"coding (?:test|challenge)|hackerrank|codility|karat)\b", re.I)),
    # Đo trên tiêu đề thư thật: bản cũ bắt hụt "decided not to move forward"
    # (chỉ có "moving") và "won't be taking your application further" (chỉ có
    # "take"). Hụt ở đây là hụt nặng nhất: thư từ chối rơi xuống "other" thì
    # `needs_you = 0`, thư không bao giờ hiện ra, và bảng báo "đang chờ" mãi
    # cho một lần nộp đã chết.
    (REJECTED, re.compile(
        r"\b(not (?:be )?(?:mov\w+|progress\w+|proceed\w+) forward|"
        r"will not be (?:progressing|proceeding|moving)|"
        r"decided not to (?:proceed|continue|mov\w+ forward)|"
        r"(?:not|won'?t)[^.]{0,24}your application (?:any )?further|"
        r"not (?:been )?successful|unsuccessful|"
        r"not (?:the )?right (?:fit|match)|"
        r"other candidates|unable to offer you|regret to inform)\b", re.I)),
    (SENT, re.compile(
        r"\b(thank you for (?:applying|your application)|"
        r"we(?:'ve| have) received your application|application received|"
        r"your application (?:to|for|has been received))\b", re.I)),
]

# NGƯỜI ĐƯA THƯ, KHÔNG PHẢI NGƯỜI TUYỂN. Ba nhóm, cùng một hệ quả: tên của
# họ KHÔNG BAO GIỜ là tên công ty, và tên công ty thật nằm trong chữ.
#
# Đo trên hộp thư thật, 60 ngày, 56 thư có kết cục: lỗi nặng nhất cả bảng là
# lá thư MỜI PHỎNG VẤN — dòng quan trọng nhất — bị ghi tên "GoHire", một hãng
# phần mềm tuyển dụng. Công ty thật là Kappa Lab, nằm ngay trong tiêu đề
# ("Kappa Lab Interview") lẫn thân thư ("Thank you for applying to Kappa Lab").
# Tương tự: Workable che mất Flowdesk, Longshot Systems, G-20 Group.
ATS_HOST = re.compile(
    r"(greenhouse|lever|ashbyhq|ashby|workday|myworkday|smartrecruiters|icims|"
    r"successfactors|teamtailor|pinpointhq|jobvite|bamboohr|ripplematch|"
    r"workable|gohire|broadbean|recruiterflow|recruitee|breezy|jazzhr|"
    r"applytojob|personio|taleo|brassring|avature|eightfold|phenom|"
    # bảng việc làm: người đưa thư, không phải người tuyển
    r"linkedin|indeed|glassdoor|ziprecruiter|totaljobs|reed\.co|cv-library|"
    r"efinancialcareers|otta|welcometothejungle|jobtoday)",
    re.I)

# KẾT CỤC MẠNH — ba loại này không thể khớp nhầm từ một lá thư hành chính.
# Không sở thuế nào viết "we would like to invite you to interview".
#
# `applied` thì YẾU: "Your application for a National Insurance number" khớp
# nó bằng đúng một chữ "application".
MANH = (INTERVIEW, OFFER, REJECTED)

# TÊN MIỀN HAY GỬI THƯ HÀNH CHÍNH. Danh sách RỘNG là cố ý, và nó chỉ an toàn
# nhờ luật MANH ở trên.
#
# Nó đè được lên bằng chứng YẾU — đo trên hộp thư thật, "Your application for
# a National Insurance number" từng đẻ ra một dòng việc làm tên "Apply for a
# National Insurance num".
#
# Nhưng nó KHÔNG đè được lên kết cục MẠNH. Ở UK, Civil Service và NHS là hai
# nhà tuyển dụng lớn nhất nước; bản trước ép thư mời phỏng vấn của họ về
# "other", needs_you = 0, và lá thư biến mất khỏi mọi màn hình.
#
# Đổi lại: thư "đã nhận đơn" từ Civil Service không tự đẻ dòng. Chấp nhận
# được — mất một dòng xác nhận nhẹ hơn nhiều so với mất một lời mời.
KHONG_PHAI_VIEC = re.compile(
    r"(service\.gov\.uk|gov\.uk|hmrc|dvla|nhs\.uk|\.edu$|companieshouse)", re.I)

# Tên công ty nằm trong CHỮ. Xếp từ chắc chắn nhất xuống — thư đầu tiên khớp
# thì dừng. Mẫu rút từ 56 thư thật, không phải đoán.
TRONG_CHU = (
    re.compile(r"thanks?(?: you)? for (?:applying|submitting your application)"
               r" (?:to|for) (.{2,160})", re.I),
    re.compile(r"thanks?(?: you)? for your (?:application|interest)"
               r" (?:to|in) (.{2,160})", re.I),
    re.compile(r"(?:we(?:'ve| have) )?received your application (?:to|for) (.{2,160})", re.I),
    re.compile(r"your application (?:to|for) (.{2,160})", re.I),
    re.compile(r"thanks?(?: you)? from (.{2,60})", re.I),
    re.compile(r"^(.{2,40}?) (?:interview|hiring team|careers team)\b", re.I),
)

# TÊN CÔNG TY NẰM SAU CHỮ `at` CUỐI CÙNG. Đây là luật cứu được nhiều dòng
# nhất, và nó rút thẳng từ hộp thư thật:
#     "Your application to Quantitative Researcher at Durlston Partners"
#     "interest in the Machine Learning Engineer position at IMC"
#     "interest in career opportunities at Schonfeld"
# Không có `at` thì phần bắt được chính là tên công ty.
_SAU_AT = re.compile(r"\bat\s+(.+)$", re.I | re.S)

# Đuôi thừa sau tên công ty: dấu câu, lời chào, động từ nối.
_DUOI_TEN = re.compile(
    r"\s*(?:[,|!.:;]|\band (?:for|your|taking)\b|\brole\b|\bposition\b|"
    r"\bis\b|\bhas\b|\bwas\b|\bwill\b|\bteam will\b).*$",
    re.I | re.S)

# CHỮ NÀY LÀ VAI TRÒ, KHÔNG PHẢI TÊN CÔNG TY. Chốt quan trọng nhất còn lại:
# "we've received your application for Quantitative Trading Analyst" — bắt
# được thì ra tên một chức danh, và bảng mọc thêm một "công ty" tên là
# "Quantitative Trading Analyst". Chỉ tin khi câu có chữ `at` tách đôi
# vai-trò / công-ty; không có thì thà không đoán.
LA_VAI_TRO = re.compile(
    r"\b(engineer|developer|analyst|researcher|scientist|trader|manager|"
    r"associate|consultant|intern(ship)?|specialist|architect|quant\w*|"
    r"programme|program|graduate|officer|lead|director|assistant|advisor|"
    r"strategist|technologist|administrator)\b", re.I)

# Mạo từ / rác HTML dính vào đầu đoạn bắt được.
_DAU_THUA = re.compile(r"^(?:the|a|an|our|your|from)\s+", re.I)
_RAC_HTML = re.compile(r"&[a-z]+;|&#\d+;|[\u200b\u200c\u00a0]")

# Chữ còn lại sau khi bóc đuôi/đầu mà rơi vào đây thì KHÔNG phải tên công ty.
# "Talent Acquisition" bóc "Talent" còn "Acquisition"; "GD Notification" còn
# "GD". Cả hai đã lên bảng như tên công ty.
KHONG_PHAI_TEN = re.compile(
    r"^(acquisition|notifications?|team|hiring|careers?|recruit\w*|talent|"
    r"people|hr|jobs?|apply|application|admin|info|support|mail|no ?reply|"
    r"do ?not ?reply|gd|ta|confirmation)$", re.I)

# Chữ thừa trong tiêu đề, bỏ đi thì còn lại tên công ty / vai trò.
NOISE = re.compile(
    r"\b(re|fwd|your application|application (?:for|to|update|status)|"
    r"thank you for applying|update on your application)\b[:\s-]*", re.I)


def kind(msg: dict) -> str:
    """-> 'offer' | 'interview' | 'rejected' | 'applied' | 'other'."""
    blob = f"{msg.get('subject', '')} {msg.get('snippet', '')}"
    for name, pattern in RULES:
        if pattern.search(blob):
            return name
    return "other"


# Đuôi thừa trong tên người gửi: "Jump Trading Recruiting" -> "Jump Trading".
ROLE_TAIL = re.compile(
    r"\s*\b(recruit(ing|ment)?|talent( acquisition)?|careers?|hr|people|"
    r"hiring|no[- ]?reply|team|notifications?)\b\s*$", re.I)

ROLE_HEAD = re.compile(
    r"^(careers?|recruit(ing|ment)?|talent|no[- ]?reply|hr|hiring|jobs?)"
    r"\s*(at|@|-|\|)?\s*", re.I)


def _clean_name(text: str) -> str:
    out = ROLE_HEAD.sub("", text or "").strip(" .,|-")
    for _ in range(3):                       # "X Talent Acquisition Team"
        cut = ROLE_TAIL.sub("", out).strip(" .,|-")
        if cut == out:
            break
        out = cut
    # BÓC XONG CÒN LẠI MỘT TỪ CHỨC NĂNG thì đó không phải tên công ty. Đo trên
    # hộp thư thật: "Talent Acquisition" ra "Acquisition", "GD Notification"
    # ra "GD" — cả hai đã lên bảng như tên hai công ty.
    return "" if KHONG_PHAI_TEN.match(out.strip()) else out


# Nhãn đứng trước tên miền thật: "st.griddynamics.net" -> "griddynamics",
# không phải "st". Lấy nhãn đầu là lấy tên máy chủ, không phải tên công ty.
_PHU = {"mail", "email", "mailer", "smtp", "no-reply", "noreply", "notify",
        "notification", "notifications", "st", "us", "eu", "uk", "hire",
        "candidates", "jobs", "careers", "apply", "info", "my", "www"}


def _ten_mien(host: str) -> str:
    phan = [x for x in (host or "").lower().split(".") if x]
    if len(phan) < 2:
        return phan[0] if phan else ""
    # Bỏ TLD (và TLD hai tầng kiểu .co.uk), rồi bỏ mấy nhãn phụ ở đầu.
    loi = phan[:-2] if phan[-2] in ("co", "com", "org", "net", "ac", "gov") \
        and len(phan) > 2 else phan[:-1]
    loi = [x for x in loi if x not in _PHU] or loi
    return loi[-1] if loi else ""


def _got(doan: str) -> str:
    """Từ một đoạn bắt được -> TÊN CÔNG TY, hoặc "" nếu không chắc.

    Ba phép, theo đúng thứ tự:
        1  lấy phần sau chữ `at` CUỐI CÙNG — phần trước là vai trò
        2  cắt đuôi thừa và mạo từ, dọn rác HTML
        3  còn dính chức danh mà KHÔNG có `at` tách đôi -> không đoán

    Phép 3 là chốt: "received your application for Quantitative Trading
    Analyst" bắt được thì ra tên một chức danh, và bảng mọc thêm một "công
    ty" mang tên đó. Thà rơi xuống tên miền — mavensecurities.com vẫn đúng.
    """
    doan = _RAC_HTML.sub(" ", doan or "")
    doan = " ".join(doan.split())             # tiêu đề thư có xuống dòng
    m = _SAU_AT.search(doan)
    co_at = bool(m)
    if m:
        doan = m.group(1)
    doan = _DUOI_TEN.sub("", doan)
    doan = _DAU_THUA.sub("", doan).strip(" -–—|:")
    # TÊN RIÊNG VIẾT HOA. Luật tổng quát, không phải bảng liệt kê: chữ sau
    # `at` trong "unable to give further feedback at this stage" là "this",
    # viết thường — và nó đã lên bảng như tên một công ty tên "this stage".
    # Mọi cụm kiểu "at the moment", "at least", "at scale" chết theo cùng một
    # luật, không cần thêm dòng nào.
    if doan and not (doan[0].isupper() or doan[0].isdigit()):
        return ""
    if not co_at and LA_VAI_TRO.search(doan):
        return ""
    # CẢ MỘT CÂU thì không phải tên. "from mcgregorboyall Thank you for your
    # application" từng lên bảng nguyên văn như tên một công ty.
    if len(doan.split()) > 8 or re.search(r"\bthank|\bapplication\b", doan, re.I):
        return ""
    return _clean_name(doan)


def _tu_chu(nguon: str) -> str:
    """Tên công ty trong MỘT đoạn chữ — tiêu đề, hoặc mấy dòng đầu thân thư."""
    nguon = " ".join((nguon or "").split())
    for mau in TRONG_CHU:
        m = mau.search(nguon)
        if not m:
            continue
        ten = _got(m.group(1))
        # Đừng nhận lại chính tên hãng phần mềm ("applying to Workable").
        if ten and len(ten) <= 46 and not ATS_HOST.search(ten):
            return ten[:60]
    return ""


def company_of(msg: dict) -> str:
    """Đoán công ty — CHỮ TRƯỚC, người gửi sau.

    THỨ TỰ NÀY LÀ CẢ VẤN ĐỀ. Bản cũ tin tên người gửi trước, mà thư tuyển
    dụng ngày nay phần lớn do hãng phần mềm gửi hộ: Greenhouse, Workable,
    Ashby, GoHire, Workday. Tên họ hiện ở ô "From", còn tên công ty thật nằm
    trong câu "Thank you for applying to …".

    Đo trên 56 thư có kết cục của hộp thư thật: tin người gửi trước thì thư
    MỜI PHỎNG VẤN mang tên "GoHire" thay vì Kappa Lab, và ba lần nộp qua
    Workable gộp thành một dòng "Workable".
    """
    host = (msg.get("from_addr") or "").split("@")[-1]
    la_trung_gian = bool(ATS_HOST.search(host))

    # 1. TIÊU ĐỀ — chữ chắc nhất, và là đường DUY NHẤT khi thư do bên thứ ba
    #    gửi hộ. Thư mời phỏng vấn của Kappa Lab do GoHire gửi: tên thật chỉ
    #    có ở đây.
    ten = _tu_chu(msg.get("subject") or "")
    if ten:
        return ten

    # 2. TÊN NGƯỜI GỬI — miễn là chính nó không phải tên bên đưa thư.
    #
    #    ĐỨNG TRƯỚC THÂN THƯ, không sau. Thân thư là chỗ nhiễu nhất: thư của
    #    Flowdesk mở đầu "We have received your application for the Technology
    #    | Quantitative Developer (Low Latency) | London", và bắt ở đó thì ra
    #    "Technology" trong khi ô From ghi sẵn "Flowdesk".
    #
    # KHÔNG chặn theo MÁY CHỦ ở đây. Ashby và SmartRecruiters gửi hộ nhưng vẫn
    # đặt tên CÔNG TY vào ô From ("Midnite Talent Team", "Ayming", "Monad
    # Foundation Hiring"); chặn cả nhà là vứt luôn mấy tên đúng đó. Chỉ chặn
    # khi chính CÁI TÊN là tên hãng phần mềm — GoHire, Workable, LinkedIn.
    name = _clean_name(msg.get("from_name") or "")
    if name and not ATS_HOST.search(name):
        return name[:60]

    # 3. THÂN THƯ — nhiễu hơn tiêu đề, nhưng cứu được thư mà tiêu đề chỉ ghi
    #    chức danh: "we've received your application for Quantitative Trading
    #    Analyst" / thân: "Thanks for applying to Maven."
    ten = _tu_chu(msg.get("snippet") or "")
    if ten:
        return ten

    # 4. TÊN MIỀN — nhãn trước TLD, không phải nhãn đầu.
    if host and not la_trung_gian:
        goc = _ten_mien(host)
        if goc:
            return goc.replace("-", " ").title()[:60]

    # 5. CUỐI CÙNG: đuôi tiêu đề sau dấu gạch — "… - Qube Research". Vẫn đi
    #    qua `_got`, không ghi thẳng: nhánh này từng cho nguyên câu "from
    #    mcgregorboyall Thank you for your application" lên bảng làm tên
    #    công ty, vì nó bỏ qua mọi chốt ở trên.
    head = NOISE.sub("", msg.get("subject") or "").strip(" -–—|:")
    if re.search(r"\s[-–—|]\s", head):
        return _got(re.split(r"\s[-–—|]\s", head)[-1])[:60]
    return "" if la_trung_gian else _got(head)[:60]


# VỊ TRÍ nằm TRƯỚC chữ `at`, công ty nằm sau. Cùng một câu, hai nửa:
#     "your application to Quantitative Researcher at Durlston Partners"
#     "interest in the Machine Learning Engineer position at IMC"
# Bỏ nửa trước đi là vứt mất cột `vị trí` của bảng, và vứt luôn thứ duy nhất
# tách được "Schonfeld · Quant Research Intern" khỏi 70 tin Schonfeld khác.
_TRUOC_AT = re.compile(r"^(.+?)\s+\bat\s+\S", re.I | re.S)

# Chữ bọc quanh chức danh, bỏ đi thì còn đúng cái tên.
_VO_VAI_TRO = re.compile(
    r"\b(the|a|an|our|your|for|to|position|role|opening|opportunity|vacancy|"
    r"job)\b", re.I)


def role_of(msg: dict) -> str:
    """Vị trí đã nộp, đọc từ chính lá thư. "" nếu thư không nói.

    Chỉ nhận khi câu có chữ `at` tách đôi — không có thì không biết đoạn bắt
    được là chức danh hay tên công ty, và đoán bừa thì cột `vị trí` thành chỗ
    chứa rác.
    """
    for nguon in (msg.get("subject") or "", msg.get("snippet") or ""):
        nguon = " ".join((nguon or "").split())
        for mau in TRONG_CHU:
            m = mau.search(nguon)
            if not m:
                continue
            truoc = _TRUOC_AT.match(_RAC_HTML.sub(" ", m.group(1)))
            if not truoc:
                continue
            ten = " ".join(_VO_VAI_TRO.sub(" ", truoc.group(1)).split())
            ten = ten.strip(" -–—|:,.")
            if ten and LA_VAI_TRO.search(ten) and len(ten) <= 70:
                return ten
    return ""


def match_posting(conn, company: str, role: str = "") -> int | None:
    """Tin nào trong kho ứng với lần nộp này. None nếu nộp ngoài app.

    KHỚP CÔNG TY TRƯỚC, RỒI MỚI VỊ TRÍ. Một công ty có thể có 70 tin trong
    kho (greenhouse:schonfeld), nên khớp mỗi tên công ty là chỉ đúng công ty
    chứ chưa đúng CHỖ đã nộp — và trang chi tiết sẽ mở ra một JD khác hẳn.

    Không tách được thì trả None. Bảng ghi "nộp ngoài app" là sự thật; chỉ
    đại một tin gần đúng là nói dối ở chỗ người dùng không kiểm được.
    """
    key = norm(company or "").replace(" ", "")
    if len(key) < 3:
        return None
    hang = conn.execute(
        "SELECT id, title, company FROM posting"
        " WHERE REPLACE(LOWER(REPLACE(company, ' ', '')), '.', '') LIKE ?"
        " ORDER BY kept DESC, score DESC", (f"%{key[:16]}%",)).fetchall()
    if not hang or not role:
        # KHÔNG BIẾT VỊ TRÍ THÌ KHÔNG NỐI. Công ty chỉ có một tin trong kho
        # cũng không đủ: Acadian có đúng một tin — "VP, Portfolio Manager" —
        # còn người dùng là sinh viên mới ra trường. Một tin cùng công ty
        # KHÔNG phải tin đã nộp.
        return None
    rn = norm(role)
    for r in hang:
        tn = norm(r["title"])
        if not tn:
            continue
        # Trùng khít, hoặc một bên chứa bên kia mà chỉ hơn vài chữ. "Quant
        # Researcher" và "Senior Quant Researcher" là HAI tin khác nhau;
        # "Quant Developer" và "Quant Developer (Systematic)" thì là một.
        if tn == rn or ((rn in tn or tn in rn)
                        and abs(len(tn) - len(rn)) <= 14):
            return int(r["id"])
    return None


def match(conn, msg: dict) -> int | None:
    """Lần nộp nào ứng với thư này. Khớp theo TÊN CÔNG TY đã chuẩn hoá.

    So CẢ bản bỏ khoảng trắng: tên miền không có dấu phân cách nên đoán ra
    "Mangroup" trong khi bảng ghi "Man Group". Đoán vốn có sai số; chỗ khớp
    phải chịu được, chứ không bắt chỗ đoán phải hoàn hảo.

    Không khớp được thì trả None, và thư nằm lại ở dải "cần Vin" — chỉ chỗ,
    không đoán bừa rồi ghi vào nhầm dòng.
    """
    guess = norm(company_of(msg))
    if not guess:
        return None
    tight = guess.replace(" ", "")
    hits = []
    for row in conn.execute("SELECT id, company_key, role FROM application"):
        key = (row["company_key"] or "").strip()
        if not key:
            continue
        flat = key.replace(" ", "")
        # Tên NGẮN nằm trong tên dài: "imc" nằm trong "imctradinggroup",
        # "man" nằm trong "freshman". Đòi tên ngắn phải đủ dài mới cho khớp
        # kiểu nằm-trong; ngắn hơn thì phải trùng khít.
        short = min(len(flat), len(tight))
        loose = short >= 5
        same = flat == tight
        inside = loose and (key in guess or guess in key
                            or flat in tight or tight in flat)
        if same or inside:
            hits.append(row)
    if not hits:
        return None
    if len(hits) == 1:
        return int(hits[0]["id"])

    # MỘT công ty, NHIỀU lần nộp. Đẩy bừa dòng đầu là chuyển trạng thái của
    # đơn khác: thư từ chối vai trò A hạ luôn vai trò B đang chờ phỏng vấn.
    # Xét thêm vai trò; không tách được thì trả None để Vin tự chỉ, vì "không
    # biết" thà hơn "biết sai".
    blob = norm(f"{msg.get('subject', '')} {msg.get('snippet', '')}")
    named = [r for r in hits if (r["role"] or "").strip()
             and norm(r["role"]) in blob]
    return int(named[0]["id"]) if len(named) == 1 else None
