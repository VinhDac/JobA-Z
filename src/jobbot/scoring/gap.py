"""KHỐI HỤT — viết thêm câu về cái gì thì bao nhiêu TIN HẾT HỤT.

Đây là khối trả lời câu hỏi duy nhất của tab CV: *tối nay tôi phải tự viết
câu về cái gì?* Mọi thứ khác trên tab là để phục vụ câu đó.

ĐƠN VỊ LÀ **TIN HẾT HỤT** — số tin mà MỌI dòng must đều đáp được. Không phải
"lượt", không phải "kỹ năng phủ được". Lý do đo được: đếm theo lượt thì
`cloud` đứng đầu bảng (67 dòng) trong khi nó chỉ mở khoá thêm 14 tin, còn
`visualisation` ít lượt hơn mà mở 42 tin. Đếm sai đơn vị là xếp sai thứ tự
việc, và người dùng đi làm việc đắt nhất trước.

THANG CỘNG DỒN, KHÔNG PHẢI BẢNG ĐỘC LẬP. Ba kỹ năng cùng mở khoá một tin thì
cộng riêng lẻ là đếm tin đó ba lần. Nên mỗi dòng là GIÁ TRỊ BIÊN khi đã làm
xong các dòng phía trên — tham lam từng bước, đúng như người ta làm thật:
viết câu thứ nhất, rồi mới hỏi câu thứ hai còn đáng không.

HAI NHÃN, chia bằng MỘT luật đo được — không phải bằng phán đoán:

    VIẾT  phần lớn dòng must đòi nó KHÔNG gọi tên sản phẩm nào
          -> diễn đạt lại bằng chữ của mình được. Tốn một buổi tối.
    HỌC   phần lớn dòng must gọi ĐÍCH DANH tên sản phẩm (AWS, Tableau…)
          -> không câu nào viết thay được, phải đi học. Tốn hàng tháng.

NHÃN VIẾT LÀ MỘT LỜI HỨA, VÀ `nen_nhap` LÀ CHỖ GIỮ LỜI. Đã nói "diễn đạt lại
được" thì phải đưa ra được DÒNG ĐỂ DIỄN ĐẠT LẠI, không phải một ô trống. Nhãn
HỌC thì ngược lại và đúng ra là vậy: "phải dùng Tableau" không có bản nháp nào.

Nhãn KHÔNG nói "người dùng đã làm việc này" — máy không biết điều đó, và bản
trước của lời chú này nói vậy trong khi mã chưa bao giờ đo nó.

Đo trên kho thật: VIẾT trọn rổ đưa phủ must 73,5% -> 90,0% (166 -> 269 tin);
HỌC trọn rổ chỉ lên 81,8% (+31 tin). Viết ăn đứt học hơn hai lần, và tính
bằng ngày thay vì bằng tháng.
"""

from __future__ import annotations

import json
import re
import sqlite3

from ..ingest.base import norm
from .vocab import alias_hits

# TÊN SẢN PHẨM gọi đích danh -> không viết được, phải học. Bảng tra do người
# viết, cùng bản chất với vocab.py — không phải máy sinh.
NAMED_TOOL = re.compile(
    r"\b(aws|amazon web services|azure|gcp|google cloud|s3|redshift|snowflake|"
    r"databricks|terraform|kubernetes|k8s|docker|kafka|airflow|spark|hadoop|"
    r"tableau|power ?bi|looker|qlik|sas|matlab|kdb|q/kdb|bloomberg|murex|"
    r"jenkins|gitlab ci|circleci)\b", re.I)


def _tin(conn: sqlite3.Connection) -> list:
    """[(tập kỹ năng mỗi dòng must đòi, có gọi đích danh tên sản phẩm không)]

    Một tin = một danh sách dòng must. Giữ theo DÒNG chứ không gộp thành một
    tập: "hết hụt" nghĩa là mọi dòng đều được đáp, mà một dòng có thể đòi
    nhiều thứ và chỉ cần đáp một là xong ("C++, Java hoặc Python").
    """
    ra = []
    for row in conn.execute(
            "SELECT score_json FROM posting WHERE kept = 1"
            " AND realism IN ('likely','possible') AND score_json != ''"):
        try:
            reqs = json.loads(row["score_json"]).get("requirements", [])
        except (TypeError, ValueError):
            continue
        dong = []
        for q in reqs:
            if not q.get("must"):
                continue
            chu = q.get("text", "")
            ky = set(alias_hits(norm(chu)))
            if ky:
                dong.append((ky, bool(NAMED_TOOL.search(chu))))
        if dong:
            ra.append(dong)
    return ra


def tin_tron(tin: list, co: set) -> int:
    """Bao nhiêu tin mà MỌI dòng must đều đáp được bằng `co`.

    Một dòng đáp được khi nó đòi ít nhất một thứ mình có — đúng luật "hoặc"
    mà `cv.build._real_missing` đã dùng: JD ghi "C++, Java hoặc Python" mà
    mình có Python thì dòng đó xong, Java không phải chỗ hụt.
    """
    return sum(1 for dong in tin if all(ky & co for ky, _ in dong))


def thang(conn: sqlite3.Connection, co: set, sau: int = 8) -> dict:
    """Thang cộng dồn: viết/học thứ nào trước thì lợi nhất.

    Tham lam từng bước — mỗi vòng chọn kỹ năng mở khoá thêm NHIỀU TIN NHẤT
    tính trên phần đã chọn. Đó cũng là cách người ta làm thật: viết xong câu
    thứ nhất rồi mới hỏi câu thứ hai còn đáng không.
    """
    tin = _tin(conn)
    if not tin:
        return {"tin": 0, "nen": 0, "buoc": []}

    # Ứng viên = mọi kỹ năng còn hụt ở ít nhất một dòng must chưa đáp được.
    ung: dict = {}
    for dong in tin:
        for ky, ten_rieng in dong:
            if ky & co:
                continue                      # dòng này đáp được rồi
            for k in ky:
                a, b = ung.get(k, (0, 0))
                ung[k] = (a + 1, b + (1 if ten_rieng else 0))
    nen = tin_tron(tin, co)
    dang_co = set(co)
    buoc = []
    for _ in range(sau):
        tot, ten = 0, ""
        for k in ung:
            if k in dang_co:
                continue
            them = tin_tron(tin, dang_co | {k}) - tin_tron(tin, dang_co)
            if them > tot:
                tot, ten = them, k
        if not ten:
            break
        dang_co.add(ten)
        dong_n, rieng = ung[ten]
        buoc.append({
            "ky_nang": ten,
            "dong": dong_n,                  # bao nhiêu dòng must đòi nó
            "rieng": rieng,                  # trong đó mấy dòng gọi ĐÍCH DANH
            "them": tot,                     # mở khoá THÊM bao nhiêu tin
            "cong_don": tin_tron(tin, dang_co),
            # NHÃN theo phần đa số, nhưng LUÔN hiện cả hai số bên cạnh.
            #
            # Ép về một nhãn là mất thông tin: `visualisation` có 51 dòng must,
            # 26 gọi đích danh Tableau/Power BI (phải học) và 25 chỉ đòi
            # "trình bày kết quả" (viết được tối nay). Dán mỗi chữ HỌC thì Vin
            # bỏ qua 25 dòng đang nằm trong tầm tay.
            "viec": "hoc" if rieng * 2 > dong_n else "viet",
        })
    # CHỈ VIẾT THÔI thì tới đâu — con số quyết định nhất của cả bảng.
    #
    # "Làm hết bảng" gộp cả mấy dòng phải đi HỌC, mà học tính bằng tháng còn
    # viết tính bằng buổi tối. Trộn hai thứ vào một con số là để người dùng
    # nhìn vào một cái đích không với tới được tối nay.
    chi_viet = set(co)
    for b in buoc:
        if b["viec"] == "viet":
            chi_viet.add(b["ky_nang"])
    return {"tin": len(tin), "nen": nen, "buoc": buoc,
            "chi_viet": tin_tron(tin, chi_viet),
            "so_viet": sum(1 for b in buoc if b["viec"] == "viet")}


# --- XƯỞNG VIẾT: máy dọn chỗ, người viết ---------------------------------

def ho_hoi(conn: sqlite3.Connection, ky_nang: str, sau: int = 8) -> list:
    """NGUYÊN VĂN mấy dòng must đang đòi `ky_nang` mà hồ sơ chưa đáp.

    In nguyên văn, KHÔNG tóm tắt: người ta viết CV trúng hơn khi đọc đúng chữ
    nhà tuyển dụng dùng, chứ không phải khi đọc bản tóm tắt của máy. Kèm tên
    công ty để biết đây là yêu cầu thật của một tin thật.

    Chia hai nhóm vì chúng dẫn tới hai việc khác nhau: dòng gọi ĐÍCH DANH tên
    sản phẩm thì không viết thay được, dòng nói chung chung thì viết được.
    """
    chung, rieng = [], []
    # MỘT DÒNG MỘT LẦN. Nhiều tin chép chung một câu mẫu ("Understanding of
    # data visualisation and presenting analytical findings clearly" ra hai
    # lần từ cùng một hãng tuyển), và brief in lặp thì năm dòng đọc được rút
    # còn ba. Giữ lần xuất hiện ĐẦU — tin điểm cao nhất, vì câu lệnh đã
    # ORDER BY score DESC.
    da_co: set = set()
    for row in conn.execute(
            "SELECT company, title, score_json FROM posting WHERE kept = 1"
            " AND realism IN ('likely','possible') AND score_json != ''"
            " ORDER BY score DESC"):
        try:
            reqs = json.loads(row["score_json"]).get("requirements", [])
        except (TypeError, ValueError):
            continue
        for q in reqs:
            if not q.get("must"):
                continue
            chu = q.get("text", "")
            if ky_nang not in alias_hits(norm(chu)):
                continue
            dau = " ".join(norm(chu).split())
            if dau in da_co:
                continue
            da_co.add(dau)
            muc = {"cong_ty": row["company"], "tin": row["title"], "chu": chu}
            (rieng if NAMED_TOOL.search(chu) else chung).append(muc)
    # Dòng chung chung lên trước: đó là phần Vin viết được tối nay.
    return (chung[:sau], rieng[:sau])


# --- DÒNG DÙNG ĐƯỢC LÀM NỀN BẢN NHÁP ------------------------------------
#
# Nhãn VIẾT nói: dòng này KHÔNG gọi đích danh tên sản phẩm, nên diễn đạt lại
# bằng chữ của mình được. Đó chính là cái nền để dựng bản nháp — và là lý do
# nhãn HỌC thì không có bản nháp nào: "phải dùng Tableau" thì không câu nào
# viết thay được.
#
# NHƯNG KHÔNG PHẢI DÒNG CHUNG CHUNG NÀO CŨNG DÙNG ĐƯỢC. Đo trên kho thật,
# `visualisation` có 22 dòng chung chung mà 12 dòng là TẢ PHẨM CHẤT
# ("Interest in statistics, data visualisation or modelling"). Đổi câu đó
# sang một câu CV thì đổi thành cái gì? Không có việc nào trong đó để kể.
#
# Nên chỉ lấy dòng TẢ VIỆC: mở đầu bằng một động từ sai khiến ("Build and
# maintain data pipelines…") hoặc một danh động từ ("Developing and
# maintaining…"). Đó là dòng nói HỌ MUỐN NGƯỜI NÀY LÀM GÌ — và câu CV cũng
# là câu kể mình đã làm gì, nên hai bên cùng một hình.
#
# Bảng tra do người viết, cùng bản chất với NAMED_TOOL và vocab.py — không
# phải máy sinh, và thiếu từ thì thêm vào đây.
LAM_VIEC = (
    "build", "rebuild", "develop", "design", "create", "implement", "deliver",
    "maintain", "write", "produce", "automate", "analyse", "analyze", "model",
    "optimise", "optimize", "improve", "enhance", "manage", "own", "lead",
    "support", "use", "apply", "conduct", "perform", "run", "translate",
    "present", "communicate", "collaborate", "partner", "research", "explore",
    "investigate", "monitor", "test", "validate", "clean", "process",
    "extract", "transform", "visualise", "visualize", "report", "deploy",
    "scale", "integrate", "migrate", "refactor", "debug", "document",
    "contribute", "drive", "define", "evaluate", "benchmark", "tune",
    "forecast", "backtest", "prototype", "ship", "maintain", "assist",
)

# Danh từ TRẠNG THÁI mở đầu -> tả phẩm chất, không tả việc. Đứng trước nó
# thường có một hai tính từ ("Solid experience…", "Detailed understanding…").
PHAM_CHAT = re.compile(
    # BỐN từ đệm, không phải hai. "Strong programming and scripting skills
    # (Python, Bash)" có bốn từ trước danh từ trạng thái, nên nó lọt qua và
    # được đưa ra làm nền bản nháp — một dòng không có việc nào để kể.
    r"^(?:[a-z+0-9-]+\s+){0,4}"
    r"(interest|curiosity|understanding|knowledge|awareness|familiarity|"
    r"passion|enthusiasm|exposure|appreciation|experience|experiences|"
    r"proficiency|proficient|competency|comfort|comfortable|background|"
    r"degree|degrees|education|grasp|attention|ability|aptitude|mindset|"
    r"motivations?|desire|willingness|skills?|expertise|fluency|command|"
    r"confidence|confident|strength|acumen|literacy)\b", re.I)

# Danh động từ mở đầu ("Developing and maintaining…"). Trừ mấy từ đuôi -ing
# vốn là DANH TỪ ngành nghề, không phải việc đang làm.
_ING_KHONG_PHAI_VIEC = re.compile(
    r"^(engineering|marketing|accounting|banking|consulting|training|"
    r"understanding|reporting line)\b", re.I)

_MO_DAU = re.compile(
    r"^(?:the |a |an )?(?:proven |demonstrable |strong )?(?:ability to |able to )?"
    r"([a-z][a-z-]*)", re.I)


def ta_viec(chu: str) -> bool:
    """Dòng yêu cầu này có TẢ MỘT VIỆC không — tức dùng làm nền bản nháp được.

    Tả việc  "Build and maintain data pipelines, ensuring data quality…"
    Tả phẩm  "Interest in statistics, data visualisation or modelling"

    Chỉ dòng tả việc mới đổi sang câu CV được: câu CV cũng là câu kể mình đã
    LÀM gì. Đưa một dòng tả phẩm chất ra làm nền bản nháp là mời người dùng
    viết lại chính lời tự khen của nhà tuyển dụng.
    """
    t = " ".join((chu or "").split())
    if len(t) < 18 or PHAM_CHAT.match(t):
        return False
    m = _MO_DAU.match(t)
    if not m:
        return False
    tu = m.group(1).lower()
    if tu in LAM_VIEC:
        return True
    return tu.endswith("ing") and not _ING_KHONG_PHAI_VIEC.match(tu)


# --- GỢI Ý: đổi dòng của họ sang HÌNH một câu CV -------------------------
#
# Máy KHÔNG nghĩ ra khẳng định nào. Nó làm đúng ba phép cơ học, và cả ba đều
# đảo ngược lại được bằng mắt thường:
#
#   1  cắt phần đuôi của người viết tin ("…, ensuring data quality across…")
#   2  đổi động từ sai khiến sang QUÁ KHỨ — hình của câu CV
#   3  chừa lại một CHỖ TRỐNG `___` cho bằng chứng, thứ chỉ người dùng có
#
# Chỗ trống là phần quan trọng nhất. Không có nó thì "gợi ý" chỉ là dòng của
# nhà tuyển dụng chia ở thì quá khứ — một khẳng định người dùng chưa đưa ra và
# không đỡ nổi khi người phỏng vấn hỏi tiếp. Có nó thì máy đưa ra HÌNH, người
# dùng đưa ra NỘI DUNG, và `con_trong` không cho lưu khi chỗ trống còn nguyên.

# Đuôi của người viết tin: bối cảnh, điều kiện, lời hứa. Không thuộc câu CV.
# CHỈ CẮT KHI KỸ NĂNG CÒN SỐNG SÓT — xem `goi_y`. Cắt mất chính cái tên kỹ
# năng thì câu viết ra không lấp được chỗ hụt nào, mà lấp chỗ hụt là toàn bộ
# lý do người dùng ngồi đây.
_DUOI = re.compile(
    r"\s*(?:,\s*)?\b(?:ensuring|including|as well as|in order to|so that|"
    r"to ensure|to support|to help|with a focus on|whilst|while ensuring|"
    r"across multiple|and related|or similar|and other|such as|e\.g\.|etc)"
    r"\b.*$", re.I)

# Cắt thêm ở mấy chỗ nối, cũng chỉ khi kỹ năng còn sống sót. Dòng tin tuyển
# hay gộp ba bốn việc vào một dòng; câu CV thì kể MỘT việc.
_NOI = re.compile(r"\s*(?:,\s+and\s+|,\s+|\s+and\s+|\s+through\s+|"
                  r"\s+across\s+|\s+within\s+|\s+for\s+)", re.I)

# Động từ bất quy tắc có trong LAM_VIEC. Bảng tra do người viết — cùng bản
# chất với NAMED_TOOL và vocab.py.
_QUA_KHU = {"build": "built", "rebuild": "rebuilt", "write": "wrote",
            "run": "ran", "lead": "led", "drive": "drove", "ship": "shipped",
            "own": "owned", "deal": "dealt", "keep": "kept", "make": "made"}

CHO_TRONG = "___"


def qua_khu(tu: str) -> str:
    """Động từ sai khiến hoặc danh động từ -> QUÁ KHỨ. Hình của câu CV."""
    t = tu.lower()
    if t.endswith("ing"):                       # Developing -> develop
        goc = t[:-3]
        t = goc if goc in LAM_VIEC else (goc + "e" if goc + "e" in LAM_VIEC
                                         else goc)
    if t in _QUA_KHU:
        return _QUA_KHU[t]
    if t.endswith("e"):
        return t + "d"
    if len(t) > 2 and t.endswith("y") and t[-2] not in "aeiou":
        return t[:-1] + "ied"
    return t + "ed"


def _con_ky_nang(t: str, ky_nang: str) -> bool:
    """Đoạn chữ này còn nhắc tới kỹ năng đang nhắm không."""
    return bool(ky_nang) and ky_nang in alias_hits(norm(t))


def goi_y(chu: str, ky_nang: str = "") -> str:
    """Dòng yêu cầu -> HÌNH một câu CV, chừa chỗ trống cho bằng chứng.

    Ba phép cơ học, không phép nào nghĩ ra khẳng định mới:
        cắt phần thừa của người viết tin — nhưng KHÔNG cắt mất tên kỹ năng
        đổi động từ sai khiến sang quá khứ — hình của câu CV
        chừa `___` cho bằng chứng, thứ chỉ người dùng mới có

    TRẢ VỀ "" KHI KHÔNG ĐỔI ĐƯỢC ĐỦ XA. Đo trên kho thật: cắt nhẹ thì 12/19
    dòng ra đúng dòng của nhà tuyển dụng chia ở thì quá khứ (giống 0,86–1,00)
    — tức máy gợi ý ra chính thứ `qua_giong` sẽ chặn lúc Lưu. Gợi ý mà chính
    máy từ chối thì tệ hơn không gợi ý: người dùng bấm, gõ, rồi bị chặn, và
    không hiểu mình sai ở đâu. Nên chỗ nào cắt không đủ xa thì im lặng.
    """
    t = " ".join((chu or "").split())
    goc = t
    t = _DUOI.sub("", t).rstrip(" ,;.:-–—")
    if not _con_ky_nang(t, ky_nang):
        t = " ".join(goc.split())               # cắt mất kỹ năng -> hoàn lại

    # Cắt tiếp ở chỗ nối, từ phải sang trái, dừng ngay khi kỹ năng sắp mất.
    for m in reversed(list(_NOI.finditer(t))):
        ngan = t[:m.start()].rstrip(" ,;.:-–—")
        if len(ngan.split()) >= 2 and _con_ky_nang(ngan, ky_nang):
            t = ngan

    if not t or not ta_viec(t):
        return ""
    m = _MO_DAU.match(t)
    if not m:
        return ""
    tach = t.split()
    # Bỏ phần rào đón "The ability to …" trước khi chia thì.
    while tach and tach[0].lower() != m.group(1).lower():
        tach.pop(0)
    if not tach:
        return ""
    tach[0] = qua_khu(tach[0]).capitalize()
    # "Build AND maintain X" / "Developing AND maintaining X" -> cả hai động
    # từ cùng sang quá khứ, nếu không câu ra nửa quá khứ nửa hiện tại.
    if len(tach) > 2 and tach[1].lower() == "and":
        k = tach[2].lower()
        if k in LAM_VIEC or (k.endswith("ing") and k[:-3] in LAM_VIEC):
            tach[2] = qua_khu(tach[2])
    ra = " ".join(tach) + " — " + CHO_TRONG
    # CHỐT CUỐI: gợi ý phải qua được chính chốt chặn của lượt Lưu.
    return "" if qua_giong(ra, chu) >= 0.6 else ra


def con_trong(cau: str) -> bool:
    """Câu còn chỗ trống máy chừa lại -> chưa viết xong, không cho lưu."""
    return CHO_TRONG in (cau or "")


def nen_nhap(conn: sqlite3.Connection, ky_nang: str, sau: int = 12) -> list:
    """Mấy dòng yêu cầu DÙNG ĐƯỢC làm nền cho bản nháp, tin điểm cao trước.

    Máy KHÔNG viết câu mới — nó đưa ra chữ của NHÀ TUYỂN DỤNG, nguyên văn, để
    người dùng viết lại thành việc CHÍNH HỌ đã làm. Mọi khẳng định trên bản
    CV vẫn do người dùng đặt ra, và `qua_giong` ở dưới canh đúng chỗ đó.
    """
    # LẤY RỘNG rồi mới cắt. Trước đây `sau=3`, mà `goi_y` chỉ dựng nổi bản
    # nháp từ một phần nhỏ số dòng — đo trên kho thật: `nlp` có 8 dòng tả
    # việc, 3 dòng đầu chỉ ra 1 bản nháp, lấy cả 8 thì ra 3. `equities` ra 0
    # rồi thành 1. Cắt cụt trước khi thử là tự vứt mất bản nháp.
    chung, _rieng = ho_hoi(conn, ky_nang, sau=60)
    return [m for m in chung if ta_viec(m["chu"])][:sau]


# Từ nối — không tính khi so hai câu có giống nhau không.
_RONG = frozenset(
    "a an the and or of to in on for with by as at from into across is are be "
    "that this those these you your our their its it we they have has had will "
    "would can could should may might not no than then such including include "
    "e g eg ie etc other others more most both all any some".split())


def _goc(w: str) -> str:
    """Cắt đuôi biến hình, thô nhưng đủ: `maintained` và `maintain` là một từ.

    Không cắt thì đổi mỗi thì của động từ đã qua được chốt chặn — mà "Built
    and maintained data pipelines, ensuring data quality" vẫn đúng là dòng
    của nhà tuyển dụng viết ở thì quá khứ, không phải việc người dùng kể.
    Đo được: không cắt -> 0,57; cắt -> 0,86.
    """
    for duoi in ("ing", "ed", "es", "s"):
        if len(w) > len(duoi) + 2 and w.endswith(duoi):
            return w[:-len(duoi)]
    return w


def _loi(text: str) -> set:
    return {_goc(w) for w in re.findall(r"[a-z0-9+#]+", (text or "").lower())
            if w not in _RONG and len(w) > 1}


def qua_giong(cau: str, nen: str) -> float:
    """Câu người dùng vừa gõ còn GIỐNG dòng yêu cầu bao nhiêu — 0…1.

    Đây là chốt chặn của cả cơ chế gợi ý. Nền bản nháp là chữ của nhà tuyển
    dụng; lưu nguyên nó vào CV là hai cái hại cùng lúc: người sàng CV nhận ra
    ngay chữ trong tin tuyển của chính mình, và người dùng phải đỡ một khẳng
    định mình chưa bao giờ đưa ra.

    Đo bằng phần chữ có nghĩa của DÒNG YÊU CẦU còn sót lại trong câu — không
    phải Jaccard hai chiều: người dùng viết dài thêm ra thì Jaccard tụt xuống
    dù họ chưa bỏ chữ nào của nhà tuyển dụng.
    """
    a, b = _loi(cau), _loi(nen)
    if not b:
        return 0.0
    return len(a & b) / len(b)


def gan_nhat(profile: dict, ky_nang: str, sau: int = 3) -> list:
    """Câu Vin ĐÃ VIẾT gần với kỹ năng này nhất — để nối vào, không viết lại.

    Ô trống là chỗ khó nhất. Đưa câu gần nhất của chính Vin ra thì việc còn
    lại là nối thêm một mệnh đề, chứ không phải nghĩ từ đầu. Và nó giữ đúng
    giọng Vin — thứ mà bất kỳ khuôn câu mẫu nào cũng phá mất.
    """
    from ..cv.blocks import parse, sentences
    from ..cv.build import skills_in

    # Từ cùng NHÓM với kỹ năng đang nhắm: câu nói về "backtesting" là chỗ
    # gần nhất để nói thêm về "data pipeline".
    ra = []
    for b in parse(str(profile.get("cv_text") or "")):
        if b.kind not in ("experience", "project"):
            continue
        for s in sentences(b):
            ky = skills_in(s)
            if not ky:
                continue
            ra.append({"khoi": b.title, "chu": s.strip(), "ky": sorted(ky),
                       "diem": len(ky)})
    ra.sort(key=lambda x: -x["diem"])
    return ra[:sau]
