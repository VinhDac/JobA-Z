"""Dựng CẢ LOẠT bản CV — và LƯU lại, vì nó tốn 5 giây.

VÌ SAO PHẢI LƯU. Đo trên kho thật: dựng bản CV cho 364 tin đáng nộp mất 5,3
giây. Trước đây tab CV gọi nó ngay lúc vẽ trang, nên mở tab là ngồi chờ 5 giây
— và chờ để xem một thứ mình chưa yêu cầu làm. Người vừa search xong chưa tới
bước làm CV; đập vào mặt họ 28 bản tiếng Anh là sai nhịp.

Nên giống Search: BẤM THÌ MỚI CHẠY. Chạy xong thì cất, mở tab là thấy ngay.

DẤU CŨ-MỚI phải ỔN ĐỊNH QUA CÁC LẦN CHẠY APP. `live._cv_key` dùng `hash(str)`
— Python muối lại hàm đó mỗi tiến trình, nên nó đúng cho cache trong bộ nhớ mà
sai hoàn toàn cho dấu ghi xuống đĩa: khởi động lại app là dấu đổi, và bản vừa
dựng xong bỗng bị coi là cũ. Ở đây dùng sha1.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict

from ..core import versions
from ..core.journal import CV, log as jlog


def stamp(conn: sqlite3.Connection, cv_text: str) -> str:
    """Dấu của MỌI thứ bản dựng phụ thuộc vào.

    Năm thành phần, và thiếu cái nào cũng để lại một đường sai:
        chữ CV      sửa khối xong mà bản cũ nằm lại thì nút không đổi
        luật viết   đổi rules.py mà không dựng lại thì bản cũ sai luật
        luật chấm   đổi điểm thì "họ hỏi gì" đổi, nên bản phải đổi
        tập tin     quét về tin mới thì có bản mới phải dựng
        ba núm      xoay núm mà nút vẫn ghi "Dựng lại" thì núm là đồ trang trí
    """
    from ..dashboard.live import cv_nut
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM posting"
        " WHERE kept = 1 AND realism IN ('likely','possible')").fetchone()
    num = cv_nut(conn)["ten"]
    thanh_phan = (hashlib.sha1(cv_text.encode("utf-8")).hexdigest()[:16],
                  versions.CV_RULES, versions.SCORE_RULES,
                  str(row[0]), str(row[1]),
                  ",".join(f"{k}={v}" for k, v in sorted(num.items())))
    return "|".join(thanh_phan)


def _phang(o):
    """dataclass -> dict. Line/Section/Sua/Yeu đều là dataclass lồng nhau."""
    try:
        return asdict(o)
    except TypeError:
        return str(o)


def save(conn: sqlite3.Connection, payload: dict, dau: str) -> None:
    """Cất bản dựng. ĐÚNG MỘT DÒNG — bảng có CHECK(id = 1).

    Không giữ lịch sử: "trước" trong bản so sánh là CV GỐC của Vin, không phải
    lần dựng trước. Giữ lịch sử ở đây là giữ thứ không ai đọc.
    """
    from ..core.postings import now
    conn.execute(
        "INSERT INTO cv_build (id, made_at, stamp, payload) VALUES (1, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET made_at = excluded.made_at,"
        " stamp = excluded.stamp, payload = excluded.payload",
        (now(), dau, json.dumps(payload, default=_phang)))
    conn.commit()


def saved(conn: sqlite3.Connection) -> dict | None:
    """Bản đã cất, hoặc None nếu chưa dựng lần nào."""
    row = conn.execute(
        "SELECT made_at, stamp, payload FROM cv_build WHERE id = 1").fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row["payload"])
    except (TypeError, ValueError):
        return None                   # dòng hỏng thì coi như chưa dựng
    data["made_at"] = row["made_at"]
    data["stamp"] = row["stamp"]
    return data


def xoa(conn: sqlite3.Connection) -> int:
    """Vứt bản đã dựng. Trả về số bản vừa bỏ đi.

    CHỈ ĐỤNG THỨ MÁY DỰNG RA. `cv_text` — chữ người dùng viết — không hề bị
    động tới, nên xoá nhầm chỉ tốn một lần bấm Chạy. Đó cũng là lý do chốt ở
    đây nhẹ hơn chốt của /api/reset: cái kia xoá thứ không dựng lại được.
    """
    cu = len((saved(conn) or {}).get("versions") or [])
    conn.execute("DELETE FROM cv_build")
    conn.commit()
    return cu


def stage(conn: sqlite3.Connection) -> dict:
    """Lượt dựng TỚI sẽ làm gì. MỘT chỗ quyết, nút Chạy chỉ đọc lại để đặt tên.

        Chạy      chưa dựng lần nào
        Cập nhật  đã dựng, nhưng chữ CV / luật / tập tin đã đổi
        Dựng lại  đang khớp — bấm cũng được, chỉ là không có gì mới

    Nút đoán một kiểu còn máy làm một kiểu thì chữ trên nút là lời nói dối.
    """
    from ..profile import store as pstore
    answers = pstore.load(conn)
    cv_text = answers.get("cv_text") or ""
    co_cv = bool(cv_text.strip())
    dang = conn.execute(
        "SELECT COUNT(*) FROM posting WHERE kept = 1"
        " AND realism IN ('likely','possible')").fetchone()[0]

    cu = saved(conn)
    ban = len((cu or {}).get("versions") or [])
    chung = {"kept": ban, "worth": dang, "state": "chưa dựng bản nào"}

    if not co_cv:
        # Không có CV thì không dựng được gì. Nói ra, đừng để nút mời một việc
        # bấm vào không xảy ra chuyện gì.
        return {**chung, "mode": "chua_cv", "label": "Chạy", "todo": 0,
                "note": "hồ sơ chưa có CV — nhập CV ở tab Profile trước"}
    if not dang:
        return {**chung, "mode": "chua_tin", "label": "Chạy", "todo": 0,
                "note": "chưa có tin nào đáng nộp — chạy Search trước"}
    if cu is None:
        return {**chung, "mode": "dau", "label": "Chạy", "todo": dang,
                "note": f"chưa dựng lần nào — dựng bản cho {dang:,} tin đáng nộp"}

    moi = stamp(conn, cv_text)
    xong = f"{ban} bản · dựng lúc {str(cu.get('made_at') or '')[11:16]}"
    if cu.get("stamp") != moi:
        vi_sao = _vi_sao_cu(cu.get("stamp") or "", moi)
        return {**chung, "mode": "moi", "label": "Cập nhật", "todo": dang,
                "state": xong, "note": f"bản đang có đã cũ — {vi_sao}"}
    return {**chung, "mode": "khop", "label": "Dựng lại", "todo": 0,
            "state": xong, "note": "bản đang có vẫn khớp — dựng lại cũng ra y hệt"}


def _vi_sao_cu(cu: str, moi: str) -> str:
    """Cũ vì CÁI GÌ. "Đã cũ" trơ trọi thì người dùng không biết mình vừa đổi gì."""
    a, b = cu.split("|"), moi.split("|")
    if len(a) != len(b):
        return "luật dựng đã đổi"
    ten = ("chữ trên CV đã sửa", "luật viết CV đã đổi", "luật chấm điểm đã đổi",
           "số tin đáng nộp đã đổi", "có tin mới về",
           "bạn vừa xoay núm ở tấm Điều chỉnh")
    doi = [ten[i] for i in range(len(b)) if a[i] != b[i]]
    return " · ".join(doi) or "đầu vào đã đổi"


def run(conn: sqlite3.Connection, log=None) -> dict:
    """Dựng mọi bản rồi cất. Đây là việc nút Chạy gọi, ở NỀN.

    Trả về chính bản vừa cất, để người gọi khỏi đọc lại từ đĩa.
    """
    say = log or (lambda _m: None)
    from ..profile import store as pstore
    answers = pstore.load(conn)
    cv_text = answers.get("cv_text") or ""
    if not cv_text.strip():
        jlog.warn(CV, "chưa có CV trong hồ sơ — không dựng được bản nào")
        return {}

    jlog.emit(CV, "bắt đầu dựng bản CV — đọc từng tin, hỏi hồ sơ trả lời được gì")
    from ..dashboard import live
    live.quen()            # buộc dựng thật, không lấy bản trong bộ nhớ
    data = live.cv_versions(conn)
    dau = stamp(conn, cv_text)
    save(conn, data, dau)

    n_ban = len(data.get("versions") or [])
    n_tin = sum(len(v.get("jobs") or []) for v in data.get("versions") or [])
    tom = f"{n_ban} bản cho {n_tin:,} tin"
    jlog.ok(CV, f"dựng xong — {tom}")
    jlog.done(CV)
    say(f"  CV: {tom}")
    return data
