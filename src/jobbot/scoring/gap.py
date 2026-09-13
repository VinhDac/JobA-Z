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

BA NHÃN, chia bằng luật chứ không bằng phán đoán:

    VIẾT  dòng must nói chung chung, mà hồ sơ đã có câu chạm tới khái niệm
          -> Vin CÓ LÀM, chỉ chưa viết ra. Tốn một buổi tối.
    HỌC   dòng must gọi ĐÍCH DANH tên sản phẩm (AWS, Docker, Tableau…)
          -> không viết được, phải đi học. Tốn hàng tháng.
    HỎI   chung chung mà hồ sơ im hẳn -> máy không biết Vin có làm không,
          nên hỏi một câu thay vì đoán.

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
