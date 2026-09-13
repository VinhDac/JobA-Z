"""Số liệu cho tab Home — MỘT chỗ tính, không tính rải trong lúc vẽ.

Home không có việc của riêng nó. Nó đọc lại việc của bốn tab kia và trả lời
đúng bốn câu mà đứng trong một tab lẻ không trả lời được:

    PHỄU      rơi rụng ở khúc nào — tìm được bao nhiêu, giữ bao nhiêu, nộp
              bao nhiêu, ai trả lời
    KẾT QUẢ   bao nhiêu phần trăm đi tiếp, bao nhiêu phần trăm trượt
    NĂNG SUẤT mỗi ngày làm được bao nhiêu, có đều không
    CHẨN ĐOÁN chỗ nào đang hỏng, và có chắc không

LUẬT LỚN NHẤT CỦA FILE NÀY: KHÔNG BỊA CHUỖI SỐ LIỆU.

App mới chạy được vài ngày. Vẽ biểu đồ 30 ngày mà 28 cột bằng 0 thì nó không
phải "dữ liệu trung thực" — nó ĐỌC RA thành "năng suất sụp đổ", trong khi sự
thật là app chưa tồn tại vào mấy ngày đó. Nên mọi chuỗi ở đây đều kèm SỐ NGÀY
CÓ THẬT, và chỗ nào chưa đủ để kết luận thì nói thẳng là chưa đủ, không vẽ
một cái lưới trống rồi để người đọc tự hiểu sai.

CHỈ ĐỌC. Không ghi gì, không quyết gì.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

# Bao nhiêu ngày thì đủ để nói "đều hay không đều".
#
# THEO THỨ cần ít nhất ba tuần: hai tuần thì mỗi thứ chỉ có hai điểm, mà hai
# điểm thì cái nào cũng thành "xu hướng". THEO THÁNG cần hai tháng, vì một
# tháng không so được với cái gì.
DU_NGAY = 21
DU_THANG = 2

# Điểm từ đây trở lên thì máy coi là ĐÁNG nộp. Cùng ngưỡng với nút Nộp bên
# Quản lí (live.track_stage) — hai chỗ hai ngưỡng là có ngày Home bảo còn 130
# tin đáng nộp mà bấm Nộp thì nó nói hết.
DIEM_DANG_NOP = 80

# Hai loại thư mang KẾT CỤC. Khai một chỗ, dùng cho cả thanh «hôm nay» lẫn
# dải theo ngày — hai chỗ định nghĩa "đi tiếp" là có ngày hai con số lệch.
TIEP = ("interview", "offer")
FAIL = ("rejected",)


def _ngay(x) -> str:
    return str(x or "")[:10]


def _hom_nay() -> date:
    return datetime.now(timezone.utc).date()


def _chuoi(conn: sqlite3.Connection, bang: str, cot: str, ngay: int,
           loc: str = "") -> dict:
    """{ngày: số} cho `ngay` ngày gần nhất. Ngày không có gì thì KHÔNG có khoá.

    Trả về thưa (chỉ ngày có số) chứ không điền 0 cho đủ: chỗ vẽ mới biết đâu
    là "hôm đó làm được 0" và đâu là "hôm đó app chưa chạy" — hai thứ khác
    hẳn nhau, và trộn lại là nguồn gốc của cái biểu đồ nói dối.
    """
    tu = (_hom_nay() - timedelta(days=ngay - 1)).isoformat()
    them = f" AND {loc}" if loc else ""
    return {_ngay(r[0]): r[1] for r in conn.execute(
        f"SELECT substr({cot},1,10) d, COUNT(*) FROM {bang}"
        f" WHERE {cot} IS NOT NULL AND substr({cot},1,10) >= ?{them}"
        f" GROUP BY d", (tu,))}


def _khoang(conn: sqlite3.Connection, bang: str, cot: str,
            loc: str = "") -> tuple:
    """(ngày đầu, ngày cuối, số ngày KHÁC NHAU có số) của cả bảng."""
    them = f" AND {loc}" if loc else ""
    r = conn.execute(
        f"SELECT MIN(substr({cot},1,10)), MAX(substr({cot},1,10)),"
        f" COUNT(DISTINCT substr({cot},1,10)) FROM {bang}"
        f" WHERE {cot} IS NOT NULL AND {cot} <> ''{them}").fetchone()
    return (r[0] or "", r[1] or "", r[2] or 0)


# --------------------------------------------------------------- HÔM NAY

# Bốn số của RIÊNG hôm nay. Thanh trên Home là BẢN TIN CỦA HÔM NAY, không
# phải bảng tổng kết — tổng kết đã nằm ở bốn ô bên dưới, và một con số như
# "37 đã nộp" thì hôm nào nhìn cũng thế, nên nó không nói được app có đang
# làm việc hay không.
#
# Hai số cuối lấy từ THƯ, không lấy từ cột `stage`: "hôm nay nhận được tin
# gì" là câu hỏi về thư đến trong ngày. Cột stage đổi lúc người dùng bấm
# Nhận, có thể là ba hôm sau, và lúc đó nó nhảy vào ngày hôm ấy.
def hom_nay(conn: sqlite3.Connection) -> dict:
    t = _hom_nay().isoformat()

    def m(sql, *a) -> int:
        try:
            return conn.execute(sql, a).fetchone()[0] or 0
        except Exception:                   # noqa: BLE001
            return 0

    def thu(loai) -> int:
        cho = ",".join("?" * len(loai))
        return m(f"SELECT COUNT(*) FROM message WHERE kind IN ({cho})"
                 f" AND substr(received_at,1,10) = ?", *loai, t)

    return {"ngay": t,
            "tim": m("SELECT COUNT(*) FROM raw_posting"
                     " WHERE substr(fetched_at,1,10) = ?", t),
            "nop": m("SELECT COUNT(*) FROM application"
                     " WHERE substr(applied_at,1,10) = ?", t),
            "tiep": thu(TIEP), "truot": thu(FAIL)}


# ------------------------------------------------------------------ PHỄU

def pheu(conn: sqlite3.Connection) -> dict:
    """Rơi rụng qua từng khúc. HAI đoạn, và chỗ nối phải nói thật.

    Đoạn TÌM đi từ tin lấy về tới tin đáng nộp — đó là việc của Search.
    Đoạn NỘP đi từ lần nộp tới lần được gọi — đó là việc của Quản lí.

    Chúng KHÔNG phải một phễu liền. Phần lớn lần nộp của người dùng có trước
    khi app tồn tại (dựng lại từ thư), nên không có tin gốc để nối. Vẽ liền
    một mạch thì con số "nộp" trông như là kết quả của con số "đáng nộp", mà
    thật ra hai cái gần như rời nhau. Chỗ nối trả về riêng ở `noi`.
    """
    def m(sql, *a) -> int:
        return conn.execute(sql, a).fetchone()[0] or 0

    ve = m("SELECT COUNT(*) FROM raw_posting")
    giu = m("SELECT COUNT(*) FROM posting WHERE kept = 1")
    that = m("SELECT COUNT(*) FROM posting WHERE kept = 1"
             " AND realism IN ('likely','possible')")
    dang = m("SELECT COUNT(*) FROM posting WHERE kept = 1"
             " AND realism IN ('likely','possible') AND score >= ?",
             DIEM_DANG_NOP)
    da_nop_kho = m(
        "SELECT COUNT(*) FROM posting p WHERE p.kept = 1"
        " AND p.realism IN ('likely','possible') AND p.score >= ?"
        " AND p.id IN (SELECT posting_id FROM application"
        "              WHERE posting_id IS NOT NULL)", DIEM_DANG_NOP)
    return {
        "tim": [("tin lấy về", ve, "/search"),
                ("giữ lại sau lọc", giu, "/search"),
                ("nộp được thật", that, "/search"),
                (f"đáng nộp (điểm ≥{DIEM_DANG_NOP})", dang, "/search")],
        "dang": dang,
        "cho_nop": dang - da_nop_kho,
        "noi": da_nop_kho,
    }


# --------------------------------------------------------------- KẾT QUẢ

def ket_qua(conn: sqlite3.Connection) -> dict:
    """% đi tiếp · % trượt · % có hồi âm, kèm MẪU SỐ và CỠ MẪU.

    Một tỉ lệ không có mẫu số là một câu nói suông: "2,7%" trên 37 lần nộp và
    "2,7%" trên 3.700 lần nộp là hai sự thật khác hẳn nhau, mà chỉ nhìn con số
    phần trăm thì không phân biệt được.

    HAI mẫu số, vì chúng trả lời hai câu khác nhau:
        trên TỔNG        nộp 37 chỗ thì mấy chỗ gọi — con số của cả quá trình
        trên ĐÃ NGÃ NGŨ  bỏ mấy chỗ còn đang chờ ra — con số của cái đã xong
    """
    from ..track import board
    rows = [r for r in board.all(conn) if r["stage"] != board.DRAFT]
    tong = len(rows)
    di = sum(1 for r in rows if r["stage"] in (board.INTERVIEW, board.OFFER))
    ho_noi = sum(1 for r in rows if r["stage"] == board.REJECTED)
    suy = sum(1 for r in rows if r.get("song") == board.SONG_IM)
    truot = ho_noi + suy
    hoi = sum(1 for r in rows if r.get("ho_tra_loi"))

    def pc(a, b):
        return round(a * 100 / b, 1) if b else None

    xong = di + truot
    return {"tong": tong, "di_tiep": di, "truot": truot, "ho_noi": ho_noi,
            "suy": suy, "cho": tong - xong, "hoi_am": hoi, "xong": xong,
            "pc_di": pc(di, tong), "pc_di_xong": pc(di, xong),
            "pc_truot": pc(truot, tong), "pc_hoi": pc(hoi, tong),
            "nguong_im": board.nguong(conn)}


# -------------------------------------------------------------- NĂNG SUẤT

# BỐN VIỆC — ĐÚNG BỐN SỐ CỦA THANH MASTER, chỉ khác là theo ngày thay vì
# riêng hôm nay. Thanh trên nói "hôm nay được bao nhiêu", dải dưới nói "mấy
# hôm trước thì sao" — cùng một câu hỏi, hai độ dài.
#
# "THƯ VỀ" ĐÃ BỎ. Đo trên hộp thư thật: 1.046 lá thì 991 lá rơi vào `other` —
# quảng cáo, thư báo việc, xác nhận đăng ký. Một dải 687 lá mà 95% là nhiễu
# thì nó không nói lên năng suất của bất cứ ai; nó chỉ nói hộp thư đông.
# Thay bằng hai số KẾT CỤC, và đó mới là thứ đáng nhìn theo ngày.
#
# CHÚNG KHÔNG CÙNG THANG: một ngày quét ra 4.651 tin mà nộp 4 đơn, và nhận 0
# lời mời. Vẽ chung một trục thì ba dải dưới phẳng thành ba cái vạch. Nên mỗi
# dải tự chuẩn hoá theo đỉnh CỦA CHÍNH NÓ, và in đỉnh đó ra bằng chữ.


def _la(loai) -> str:
    """Điều kiện SQL lọc theo loại thư. `loai` là hằng số trong code, không
    phải chữ người dùng gõ — nên nối thẳng được, không cần tham số."""
    return "kind IN (" + ",".join(f"'{x}'" for x in loai) + ")"


VIEC = (
    {"ma": "tim", "ten": "tin tìm được", "bang": "raw_posting",
     "cot": "fetched_at", "loc": "", "di": "/search", "mau": "kho"},
    {"ma": "nop", "ten": "đơn đã nộp", "bang": "application",
     "cot": "applied_at", "loc": "", "di": "/track", "mau": "lam"},
    # `goc` = CÁI GÌ ĐỊNH NGHĨA "app đã chạy từ bao giờ" cho dải này.
    #
    # Không có nó thì dải "được gọi tiếp" lấy ngày có LỜI MỜI ĐẦU TIÊN làm mốc
    # bắt đầu, và mọi ngày trước đó bị ghi là "app chưa chạy" — sai hẳn: hộp
    # thư chạy suốt 61 ngày, chỉ là không có lời mời nào. Một ngày KHÔNG AI
    # GỌI là một số 0 có thật, và nó là số 0 đáng nhìn nhất trên trang này.
    {"ma": "tiep", "ten": "được gọi tiếp", "bang": "message",
     "cot": "received_at", "loc": _la(TIEP), "di": "/track", "mau": "tot",
     "goc": ("message", "received_at")},
    # ĐỎ, không xanh. Một cột cao của thư từ chối mà tô xanh thì đọc thành
    # "hôm nay được việc" — màu ở đây mang nghĩa, không phải trang trí.
    {"ma": "truot", "ten": "báo trượt", "bang": "message",
     "cot": "received_at", "loc": _la(FAIL), "di": "/track", "mau": "xau",
     "goc": ("message", "received_at")},
)

THU = ("hai", "ba", "tư", "năm", "sáu", "bảy", "chủ nhật")


def nang_suat(conn: sqlite3.Connection, ngay: int = 30) -> dict:
    """Mỗi việc một dải ngày, kèm số ngày CÓ THẬT và có đủ để kết luận chưa.

    `du_thu` / `du_thang` là chỗ file này từ chối kết luận. Gộp theo thứ trên
    hai ngày dữ liệu sẽ ra "thứ sáu năng suất gấp 9 lần thứ bảy" — đúng phép
    tính, sai hoàn toàn về nghĩa, và người đọc không có cách nào biết.
    """
    het = _hom_nay()
    lich = [(het - timedelta(days=i)).isoformat() for i in range(ngay - 1, -1, -1)]
    ra = {}
    for v in VIEC:
        ma, bang, cot, loc = v["ma"], v["bang"], v["cot"], v["loc"]
        chuoi = _chuoi(conn, bang, cot, ngay, loc)
        _d, _c, so_ngay = _khoang(conn, bang, cot, loc)
        # MỐC BẮT ĐẦU lấy từ `goc` (nguồn), không từ chính dải đã lọc — xem
        # lời chú ở VIEC. Dải nào không khai goc thì chính nó là nguồn.
        g_bang, g_cot = v.get("goc") or (bang, cot)
        dau, cuoi, _n = _khoang(conn, g_bang, g_cot)
        # CHỈ TÍNH TỪ NGÀY CÓ DỮ LIỆU ĐẦU TIÊN. Trước đó app chưa chạy, và
        # đếm mấy ngày đó thành 0 là tự dìm con số trung bình của chính mình.
        song = [d for d in lich if dau and d >= dau]
        ra[ma] = {
            "ten": v["ten"], "di": v["di"], "mau": v["mau"],
            "cot": [(d, chuoi.get(d, 0)) for d in song],
            # Mấy ngày TRONG cửa sổ mà NẰM TRƯỚC ngày có dữ liệu đầu tiên.
            # Chỗ vẽ cần con số này để giữ nguyên bề rộng khung: hai ngày số
            # liệu mà vẽ thành hai cột choán hết dải thì trông như "lúc nào
            # cũng có số", trong khi sự thật là app mới chạy hai ngày.
            "truoc": len(lich) - len(song),
            "mep_trai": lich[0] if lich else "",
            "dinh": max(chuoi.values()) if chuoi else 0,
            "tong": sum(chuoi.get(d, 0) for d in song),
            "ngay_song": len(song),
            "ngay_co": so_ngay, "tu": dau, "den": cuoi,
            "tb": round(sum(chuoi.get(d, 0) for d in song) / len(song), 1)
            if song else 0,
        }

    # THEO THỨ và THEO THÁNG gộp trên TOÀN BỘ lịch sử, không riêng cửa sổ 30
    # ngày: cả hai là câu hỏi về thói quen, mà thói quen cần dài hơn một tháng.
    thu, thang = {}, {}
    for v in VIEC:
        ma, bang, cot = v["ma"], v["bang"], v["cot"]
        them = f" AND {v['loc']}" if v["loc"] else ""
        d_thu = [0] * 7
        for r in conn.execute(f"SELECT substr({cot},1,10) d, COUNT(*) FROM {bang}"
                              f" WHERE {cot} IS NOT NULL AND {cot} <> ''{them}"
                              f" GROUP BY d"):
            try:
                d_thu[date.fromisoformat(r[0]).weekday()] += r[1]
            except (TypeError, ValueError):
                continue
        thu[ma] = d_thu
        thang[ma] = {r[0]: r[1] for r in conn.execute(
            f"SELECT substr({cot},1,7) t, COUNT(*) FROM {bang}"
            f" WHERE {cot} IS NOT NULL AND {cot} <> ''{them}"
            f" GROUP BY t ORDER BY t")}

    # MỖI CHUỖI TỰ GÁC LẤY MÌNH, không dùng một con số chung.
    #
    # Đo trên kho thật: chuỗi thư có 61 ngày, chuỗi tin tìm được có 3. Lấy
    # số lớn nhất làm cổng chung thì biểu đồ "tin tìm được theo thứ" được vẽ
    # trên 3 ngày — và nó sẽ nói "thứ sáu gấp 9 lần thứ bảy". Đúng phép tính,
    # sai hoàn toàn về nghĩa, mà người đọc không có cách nào biết.
    for ma in ra:
        ra[ma]["du_thu"] = ra[ma]["ngay_co"] >= DU_NGAY
        ra[ma]["du_thang"] = len(thang[ma]) >= DU_THANG
        ra[ma]["thang_co"] = len(thang[ma])
    return {"viec": ra, "lich": lich, "thu": thu, "thang": thang,
            "ten_thu": THU, "can_thu": DU_NGAY, "can_thang": DU_THANG,
            # Số chung CHỈ để nói "app đã chạy được bao lâu", không dùng làm
            # cổng cho chuỗi nào cả.
            "ngay_co": max((ra[v["ma"]]["ngay_co"] for v in VIEC), default=0)}


# ------------------------------------------------------------ TÌM CÓ ĐỀU

def nhip_quet(conn: sqlite3.Connection) -> dict:
    """Vòng quét có chạy đều không, và nguồn nào đang câm.

    NGUỒN CÂM là thứ không tab nào khác nhìn thấy: Search chỉ khoe tin nó tìm
    được, nên một nguồn hỏng lặng lẽ chỉ làm kết quả ít đi chứ không báo gì.
    Ở đây nó hiện thành tên.
    """
    r = conn.execute("SELECT COUNT(*), SUM(ok), SUM(failed), SUM(new_rows),"
                     " COUNT(DISTINCT substr(started_at,1,10))"
                     " FROM source_run").fetchone()
    luot, ok, hong, moi, ngay = (r[0] or 0, r[1] or 0, r[2] or 0,
                                 r[3] or 0, r[4] or 0)
    cam = [x[0] for x in conn.execute(
        "SELECT source FROM source_run GROUP BY source"
        " HAVING SUM(new_rows) = 0 OR SUM(ok) = 0 ORDER BY source")]
    loi = [dict(nguon=x[0], khi=_ngay(x[1]), vi_sao=(x[2] or "")[:90])
           for x in conn.execute(
               "SELECT source, started_at, error FROM source_run"
               " WHERE ok = 0 ORDER BY started_at DESC LIMIT 4")]
    return {"luot": luot, "ok": ok, "hong_luot": luot - ok, "hong_tin": hong,
            "moi": moi, "ngay": ngay, "cam": cam, "loi": loi,
            "luot_moi_ngay": round(luot / ngay, 1) if ngay else 0,
            "pc_ok": round(ok * 100 / luot) if luot else None}


# ------------------------------------------------------------- CHẨN ĐOÁN

# Mức CHẮC CHẮN của một dấu hiệu. Bày dấu hiệu mà không nói mình chắc tới đâu
# là cách nhanh nhất để người dùng sửa nhầm chỗ: một con số đếm trực tiếp
# (130 tin chưa nộp) và một suy đoán trên 5 mẫu KHÔNG được trông giống nhau.
CHAC, VUA, YEU = "chac", "vua", "yeu"
MUC_HET = (CHAC, VUA, YEU)


def chan_doan(conn: sqlite3.Connection) -> list[dict]:
    """Dấu hiệu đang hỏng, XẾP THEO ĐỘ CHẮC chứ không theo độ giật gân.

    Mỗi dấu hiệu phải nói được: đo trên bao nhiêu mẫu, nghĩa là gì, bấm đi
    đâu để sửa. Thiếu một trong ba thì nó là câu than, không phải chẩn đoán.
    """
    from ..cv import batch
    ra = []
    p, k = pheu(conn), ket_qua(conn)

    # 1. ĐẾM TRỰC TIẾP — không suy gì cả, nên chắc nhất.
    if p["cho_nop"] > 0:
        ra.append(dict(
            muc=CHAC, ma="cho_nop", so=f"{p['cho_nop']}",
            ten=f"{p['cho_nop']} tin đáng nộp chưa nộp",
            y=f"Máy chấm ≥{DIEM_DANG_NOP} điểm và xếp là nộp được thật. "
              f"Đây là việc lớn nhất đang nằm chờ.",
            tren=f"đếm trực tiếp trên {p['dang']} tin đáng nộp",
            di="/search", nut="Xem kho"))

    # 2. NỘP CÓ ĐÚNG CHỖ KHÔNG — chỉ chấm được mấy đơn nối được tin gốc.
    diem = [r[0] for r in conn.execute(
        "SELECT p.score FROM application a JOIN posting p ON p.id = a.posting_id"
        " WHERE p.score IS NOT NULL")]
    ngoai = k["tong"] - len(diem)
    if diem:
        thap = [d for d in diem if d < DIEM_DANG_NOP]
        if thap:
            ra.append(dict(
                muc=VUA if len(diem) >= 5 else YEU, ma="nop_thap",
                so=f"{len(thap)}/{len(diem)}",
                ten=f"{len(thap)}/{len(diem)} đơn máy chấm được đều dưới "
                    f"{DIEM_DANG_NOP} điểm",
                y=f"Thấp nhất {min(thap)} điểm. Nộp vào chỗ máy đánh giá thấp "
                  f"trong khi {p['cho_nop']} tin điểm cao đang nằm không.",
                tren=f"{len(diem)} đơn nối được tin gốc — {ngoai} đơn còn lại "
                     f"nộp ngoài app nên không chấm được",
                di="/track", nut="Xem bảng"))

    # 3. RƠI Ở ĐÂU — họ có đọc không, hay đọc rồi mới loại.
    if k["tong"] >= 10 and k["pc_hoi"] is not None:
        doc = k["pc_hoi"] >= 20
        ra.append(dict(
            muc=VUA, ma="roi",
            so=f"{k['pc_hoi']:g}%",
            ten=("Người có đọc, nhưng không gọi" if doc
                 else "Phần lớn không ai trả lời"),
            y=(f"{k['hoi_am']}/{k['tong']} lần nộp có người hồi âm, mà chỉ "
               f"{k['di_tiep']} lần đi tiếp. Chỗ rơi nằm ở bước họ quyết, "
               f"không phải ở vòng máy lọc." if doc else
               f"Chỉ {k['hoi_am']}/{k['tong']} lần nộp từng có một chữ hồi "
               f"đáp. Im từ đầu thường là bị loại ở vòng máy đọc CV."),
            tren=f"{k['tong']} lần nộp",
            di="/cv", nut="Xem CV"))

    # 4. CV ĐÁP ĐƯỢC BAO NHIÊU PHẦN CỦA KHO — số của chính tầng CV.
    luu = batch.saved(conn) or {}
    hut = luu.get("hut") or {}
    if hut.get("tin"):
        nen, tin = hut.get("nen") or 0, hut["tin"]
        pc = round(nen * 100 / tin) if tin else 0
        if pc < 70:
            ra.append(dict(
                muc=CHAC, ma="phu", so=f"{pc}%",
                ten=f"CV đáp trọn {nen}/{tin} tin",
                y=f"{tin - nen} tin đang đòi thứ chưa có câu nào trên CV nói "
                  f"tới. Mỗi câu viết thêm đúng chỗ kéo con số này lên.",
                tren=f"{tin} tin trong kho",
                di="/cv/soan", nut="Soạn khối"))
    return ra


def tat_ca(conn: sqlite3.Connection, ngay: int = 30) -> dict:
    """Cả trang Home trong MỘT lượt đọc."""
    return {"hom_nay": hom_nay(conn), "pheu": pheu(conn), "ket_qua": ket_qua(conn),
            "nang_suat": nang_suat(conn, ngay), "nhip": nhip_quet(conn),
            "chan_doan": chan_doan(conn)}
