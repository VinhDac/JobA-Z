"""Biểu đồ — SVG dựng sẵn ở máy chủ, KHÔNG thư viện, KHÔNG JavaScript.

Vì sao không nạp một thư viện vẽ: mấy màn này của app không có một dòng JS
nào ngoài live.js, và mỗi thư viện ngoài là một CDN phải với ra ngoài mạng —
app chạy được lúc mất mạng là một tính chất, không phải may mắn. Biểu đồ ở
đây toàn thanh và cột, mà thanh với cột thì `<rect>` là đủ.

BA LUẬT CHO MỌI HÌNH TRONG FILE NÀY:

  1. KHÔNG VẼ CÁI KHÔNG ĐO ĐƯỢC. Ngày app chưa chạy thì không có cột, không
     phải cột bằng 0 — "hôm đó làm được 0" và "hôm đó chưa có app" là hai sự
     thật khác nhau, vẽ giống nhau là nói dối bằng hình.
  2. LUÔN CÓ MẪU SỐ. Một cái thanh 3% mà không nói 3% của bao nhiêu thì người
     đọc tự điền con số trong đầu họ, và thường là điền sai.
  3. ĐỌC ĐƯỢC KHÔNG CẦN MÀU. Mọi hình đều kèm số bằng chữ; màu chỉ để xếp
     nhóm nhanh, không phải để mang thông tin.

CHỈ VẼ.
"""

from __future__ import annotations

from datetime import date
from html import escape as esc


def _so(n) -> str:
    """12345 -> 12.345. Số dài mà không chấm thì đọc phải đếm chữ số."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def cot_ngay(cot: list, dinh: int, cao: int = 34, mau: str = "",
             truoc: int = 0) -> str:
    """Cột theo ngày. MỘT cột một ngày, cao theo đỉnh của CHÍNH chuỗi này.

    Chuẩn hoá theo đỉnh riêng chứ không theo trục chung: một ngày quét ra
    4.651 tin trong khi nộp 4 đơn. Chung trục thì dải "nộp" phẳng lì thành
    một vạch, và cái dải đó chính là thứ người dùng cần nhìn nhất.

    Đổi lại, HAI DẢI KHÔNG SO ĐƯỢC VỚI NHAU BẰNG MẮT — nên mỗi dải phải in
    đỉnh của nó ra bằng chữ, và chỗ gọi có trách nhiệm làm việc đó.
    """
    if not cot:
        return ""
    # `truoc` = mấy ngày TRONG cửa sổ mà app CHƯA CHẠY. Chúng vẫn chiếm chỗ
    # trên dải, vẽ bằng một vạch mờ sát đáy — khác hẳn cột 0 (đậm hơn, đặc).
    #
    # Bỏ chúng đi thì hai ngày số liệu nở ra choán hết dải, đọc thành "lúc
    # nào cũng đều"; điền 0 cho chúng thì đọc thành "năng suất sụp đổ". Cả
    # hai đều sai, và cái sai thứ hai còn làm người dùng đi sửa nhầm chỗ.
    n = len(cot) + truoc
    w = round(100 / n, 4)
    o = []
    for i in range(truoc):
        o.append(f"<rect x='{round(i * w, 4)}%' y='99.4%'"
                 f" width='{round(w * .74, 4)}%' height='0.6%'"
                 f" class=ngoai><title>app chưa chạy</title></rect>")
    for j, (d, v) in enumerate(cot):
        i = j + truoc
        h = round(v * 100 / dinh, 2) if dinh else 0
        h = max(h, 1.6) if v else 0          # có số thì phải thấy được
        nhan = f"{esc(str(d))}: {_so(v)}"
        if h:
            o.append(f"<rect x='{round(i * w, 4)}%' y='{round(100 - h, 2)}%'"
                     f" width='{round(w * .74, 4)}%' height='{h}%' rx='0.6'>"
                     f"<title>{nhan}</title></rect>")
        else:
            # Ngày CÓ trong dải mà số bằng 0: vẽ một chấm đáy. Bỏ trống hẳn
            # thì nó lẫn với ngày nằm ngoài dải (app chưa chạy).
            o.append(f"<rect x='{round(i * w, 4)}%' y='99%'"
                     f" width='{round(w * .74, 4)}%' height='1%' rx='0.5'"
                     f" class=khong><title>{nhan}</title></rect>")
    lop = f" {mau}" if mau else ""
    # Chiều cao do CSS lo (.spark), không gắn style vào từng hình: mở to ô
    # thì dải phải cao lên theo, mà một con số nhúng trong HTML thì không.
    return (f"<svg class='spark{lop}' viewBox='0 0 100 100'"
            f" preserveAspectRatio=none aria-hidden=true>{''.join(o)}</svg>")


def dai_viec(v: dict) -> str:
    """Một việc = một dải: tên · tổng · trung bình · cột ngày · khoảng ngày."""
    cot = v.get("cot") or []
    if not cot:
        return (f"<div class=dai><div class=daitop><b>{esc(v['ten'])}</b>"
                f"<span class=muted>chưa có ngày nào</span></div></div>")
    truoc = v.get("truoc") or 0
    # Nhãn mốc trái phải là MÉP TRÁI CỦA DẢI, không phải ngày có số đầu tiên:
    # dải giờ vẽ cả đoạn app chưa chạy, nên lấy ngày có số làm mép là nói sai
    # cái người ta đang nhìn.
    dau = (v.get("mep_trai") or cot[0][0])[5:].replace("-", "/")
    cuoi = cot[-1][0][5:].replace("-", "/")
    # Nói THẲNG có bao nhiêu ngày app chưa chạy, đừng bắt người đọc suy ra từ
    # một khoảng trống — khoảng trống nào cũng đọc được thành "làm được 0".
    chan = (f"{v['ngay_co']} ngày có số" if not truoc else
            f"{truoc} ngày app chưa chạy · {v['ngay_co']} ngày có số")
    # VIỆC HIẾM THÌ "TB 0/ngày" LÀ MỘT CÂU VÔ NGHĨA. Được gọi phỏng vấn 1
    # lần trong 60 ngày là một sự thật rất đáng biết, mà in ra thành "TB
    # 0/ngày · đỉnh 1" thì nó đọc như dữ liệu hỏng. Với dải thưa, câu trả lời
    # đúng là LẦN CUỐI LÀ KHI NÀO.
    cuoi_co = next((d for d, x in reversed(cot) if x), "")
    if round(v["tb"]) < 1 and v["tong"]:
        phu = (f"lần cuối {esc(cuoi_co[5:].replace('-', '/'))}"
               if cuoi_co else f"đỉnh {_so(v['dinh'])}")
    else:
        phu = f"TB {_so(round(v['tb']))}/ngày · đỉnh {_so(v['dinh'])}"
    return (f"<div class=dai>"
            f"<div class=daitop><a href='{esc(v['di'])}'>{esc(v['ten'])}</a>"
            f"<span class=daiso><b>{_so(v['tong'])}</b><i>{phu}</i>"
            f"</span></div>"
            + cot_ngay(cot, v["dinh"], mau=v.get("mau", ""), truoc=truoc)
            + f"<div class=daichan><span>{esc(dau)}</span>"
            f"<span>{esc(chan)}</span>"
            f"<span>{esc(cuoi)}</span></div></div>")


def cot_thu(so: list, ten: list, mau: str = "") -> str:
    """Bảy cột, một cột một thứ. Dùng CHO CHUỖI ĐỦ DÀI thôi — chỗ gọi gác."""
    dinh = max(so) if so else 0
    o = ""
    for i, v in enumerate(so):
        h = round(v * 100 / dinh) if dinh else 0
        o += (f"<div class=tcot><span class=tbar style='height:{max(h, 2)}%'"
              f" title='{esc(ten[i])}: {_so(v)}'></span>"
              f"<b>{_so(v)}</b><i>{esc(ten[i])}</i></div>")
    return f"<div class='thubar {esc(mau)}'>{o}</div>"


def chua_du(co: int, can: int, don: str = "ngày") -> str:
    """Chưa đủ dữ liệu thì NÓI RA, không vẽ một cái lưới trống.

    Đây là hình quan trọng nhất file này: một biểu đồ trống trông y hệt một
    biểu đồ "năng suất bằng 0", và người dùng sẽ tin cái thứ hai.
    """
    return (f"<div class=chuadu><b>Chưa đủ để nói</b>"
            f"<span>mới có <b>{co}</b> {esc(don)} số liệu, cần <b>{can}</b> "
            f"{esc(don)} thì gộp lại mới có nghĩa. App chạy thêm là mục này "
            f"tự hiện.</span></div>")


# -------------------------------------------------------------------- PHỄU

def pheu(buoc: list, chu: str = "") -> str:
    """Rơi rụng qua từng khúc. Bề rộng theo bước ĐẦU, nên mắt thấy ngay độ hụt.

    Kèm % GIỮ LẠI của từng bước so với bước liền trước — đó mới là con số nói
    lên khúc nào đang cắt mạnh nhất; so với bước đầu thì bước nào cũng nhỏ.
    """
    if not buoc:
        return ""
    dau = buoc[0][1] or 1
    o = ""
    truoc = None
    for ten, so, di in buoc:
        r = max(round(so * 100 / dau, 2), 0.8) if dau else 0
        rot = ("" if truoc in (None, 0) else
               f"<i class=protr>giữ {round(so * 100 / truoc)}% bước trước</i>")
        o += (f"<a class=fbuoc href='{esc(di)}'>"
              f"<span class=pten>{esc(ten)}</span>"
              f"<span class=pbar><span style='width:{r}%'></span></span>"
              f"<span class=pso><b>{_so(so)}</b>{rot}</span></a>")
        truoc = so
    return f"<div class=pheu>{o}</div>" + (
        f"<div class=note>{chu}</div>" if chu else "")


def thanh_chia(phan: list, tong: int) -> str:
    """Một thanh chia khúc: [(nhãn, số, lớp)]. Mẫu số in ngay bên cạnh.

    Khúc nào 0 thì KHÔNG vẽ, không vẽ một vạch tóc rồi chú thích — chú thích
    cho một khúc không tồn tại làm người đọc đi tìm nó trên thanh.
    """
    if not tong:
        return "<div class=empty-box>chưa nộp chỗ nào</div>"
    o = "".join(
        f"<span class='segq {lop}' style='width:{round(so * 100 / tong, 2)}%'"
        f" title='{esc(ten)}: {_so(so)}/{_so(tong)}'></span>"
        for ten, so, lop in phan if so)
    chu = "".join(
        f"<span class=qkey><i class='qdot {lop}'></i>{esc(ten)}"
        f"<b>{_so(so)}</b></span>" for ten, so, lop in phan if so)
    return f"<div class=qbar>{o}</div><div class=qkeys>{chu}</div>"


def ti_le(pc, tren: str, ten: str, lop: str = "") -> str:
    """MỘT tỉ lệ + mẫu số của nó. Không bao giờ in % mà giấu mẫu số."""
    v = "—" if pc is None else f"{pc:g}%"
    return (f"<div class='tile {lop}'><b>{esc(v)}</b>"
            f"<span>{esc(ten)}</span><i>{esc(tren)}</i></div>")


def thang_gan(thang: dict, n: int = 6, mau: str = "") -> str:
    """Mấy tháng gần nhất. Tên tháng viết ra, không để 2026-08 trần."""
    if not thang:
        return ""
    muc = sorted(thang.items())[-n:]
    dinh = max(v for _, v in muc) or 1
    o = ""
    for t, v in muc:
        h = round(v * 100 / dinh)
        try:
            nhan = f"tháng {int(t[5:7])}"
        except (TypeError, ValueError):
            nhan = t
        o += (f"<div class=tcot><span class=tbar style='height:{max(h, 2)}%'"
              f" title='{esc(t)}: {_so(v)}'></span>"
              f"<b>{_so(v)}</b><i>{esc(nhan)}</i></div>")
    return f"<div class='thubar {esc(mau)}'>{o}</div>"


def hom_nay_la() -> str:
    t = date.today()
    return ("hai ba tư năm sáu bảy".split() + ["chủ nhật"])[t.weekday()]
