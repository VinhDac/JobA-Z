"""Vẽ CV đã tuỳ biến ra HTML — phần trông giống TỜ GIẤY thật.

CHỈ tờ giấy. Phần giải trình — bỏ gì, vì sao, câu nào đã sửa chữ — nằm ở
`cv/report.py`: nó nói chuyện với người, còn chỗ này dựng thứ đem đi gửi.
Trước đây `audit()` nằm lẫn ở đây và chỉ nói được một nửa (bỏ gì), bằng tiếng
Anh, không có trước/sau.
"""

from __future__ import annotations

from html import escape as esc

from .build import TailoredCV, dang_ke, skills_in

LABEL = {"experience": "Experience", "project": "Selected projects",
         "education": "Education", "cert": "Certifications", "skill": "Technical skills"}


def paper(cv: TailoredCV, cham: bool = False,
          du_bi=None, job: str = "") -> str:
    """Tờ CV. `cham=True` thì ĐÁNH DẤU ngay trên bài, như chữa bài.

    MỘT tờ giấy, không hai. Bản trước vẽ tờ CV ở trên rồi liệt kê lại từng
    câu ở dưới — cùng một câu hiện hai lần, và người đọc phải tự ghép "câu số
    3 ở dưới" với câu nào ở trên. Chữa bài thì bút đỏ nằm TRÊN bài.

    Đánh dấu là CSS thuần (viền trái + nền lúc rê chuột), nên bản in vẫn là
    tờ giấy sạch: @media print gỡ hết dấu. Chữ "trước" nằm sẵn trong DOM để
    nút Trước/Sau bật tắt mà không phải gọi lại máy chủ.
    """
    head = "".join(f"<div class=cvline>{esc(h)}</div>" for h in cv.header if h)
    out = [f"<div class=cvhead>{head}</div>"]
    if cv.summary:
        out.append(f"<p class=cvsum>{esc(cv.summary)}</p>")

    last = ""
    for section in cv.sections:
        if section.kind != last:
            out.append(f"<h4 class=cvsec>{esc(LABEL.get(section.kind, section.kind))}</h4>")
            last = section.kind

        if section.kind in ("experience", "project", "education"):
            meta = f"<span class=cvmeta>{esc(section.meta)}</span>" if section.meta else ""
            if section.title:
                out.append(f"<div class=cvrole><b>{esc(section.title)}</b>{meta}</div>")
            items = "".join(
                # TÔ bằng tập RỘNG (`wanted`, quét cả tin), không bằng tập
                # hẹp (`asked`, chỉ dòng yêu cầu). Hai việc khác nhau:
                #   asked  -> MẪU SỐ của phân số. Rộng ở đây là nói dối.
                #   wanted -> thứ MẮT nhìn. Hẹp ở đây thì tô được đúng 1 chữ
                #             trên cả tờ giấy, và "tô từ khoá" thành vô nghĩa.
                # Tô nhầm một chữ chỉ tốn một vệt xanh; không ai bị lừa.
                _muc(l, cham, set(cv.wanted),
                     # BĂNG GHẾ CỦA CHÍNH KHỐI NÀY. Đổi một câu kinh nghiệm
                     # sang một câu project là đổi sai chỗ — mỗi khối có
                     # ngân sách dòng riêng.
                     [b for b in (du_bi or []) if b["khoi"] == section.title],
                     job)
                for l in section.lines)
            out.append(f"<ul class=cvlist>{items}</ul>")
        else:
            body = " ".join(l.text for l in section.lines)
            label = f"<b>{esc(section.title)}</b> — " if section.title else ""
            out.append(f"<div class=cvskill>{label}{esc(body)}</div>")
    lop = "cvpaper cham" if cham else "cvpaper"
    return f"<div class='{lop}'>{''.join(out)}</div>"


# Số thứ tự câu, đếm xuyên suốt cả tờ — để "câu 3" ở phần chi tiết là đúng
# câu 3 trên giấy. Dùng biến module thay vì truyền qua bốn tầng hàm.
_DEM = [0]


def _muc(line, cham: bool, doi=(), du_bi=(), job: str = "") -> str:
    """Một dòng trên tờ CV — CHỮA BÀI NGAY TẠI CHỖ, kiểu Grammarly.

    Bốn thứ, và tất cả nằm trên chính dòng đó, không ở phụ lục:

        tô        từ khoá tin này ĐÒI được bọc <mark> — nhìn phát biết tờ
                  giấy có nói ra thứ họ hỏi không
        bấm       mở thẻ ngay dưới dòng, không nhảy đi đâu
        cách sửa  còn hổng gì, và việc cụ thể phải làm
        chọn lại  mấy câu KHÁC Vin đã viết, xếp theo mức trúng tin này —
                  bấm là đổi

    KHÔNG JAVASCRIPT: thẻ mở bằng <details>, đổi câu bằng <form> thật. Một
    tính năng không có trình nghe thì không có gì để hỏng, và nó chạy y hệt
    lúc in ra giấy (bản in tự đóng thẻ lại).
    """
    if not cham:
        return (f"<li{' class=review' if line.review else ''}>{esc(line.text)}"
                + (f"<span class=rv>{esc(line.review)}</span>"
                   if line.review else "") + "</li>")

    _DEM[0] += 1
    n = _DEM[0]
    doi = set(doi)
    lop = []
    if line.sua:
        lop.append("dsua")
    if line.yeu:
        lop.append("dhong")
    if line.review:
        lop.append("dxem")

    # --- thẻ chữa bài ---
    trung = sorted(set(line.hits) | (skills_in(line.text) & doi))
    kho = ("".join(f"<span class='badge ok'>{esc(h)}</span>" for h in trung)
           if trung else
           "<span class=muted>không trúng thứ tin này đòi — câu này lên vì "
           "nó mang quy mô hoặc phán đoán</span>")

    # TỪNG CHỖ MỘT, kèm NGUYÊN VĂN đoạn chữ bị gạch — để mắt nối được thẻ
    # với vệt trên câu mà không phải dò.
    vt = list(getattr(line, "vet", ()) or ())
    yeu = "".join(
        f"<div class='cspot v{esc(v.loai)}'>"
        f"<span class=cquote>{esc(line.text[v.dau:v.cuoi][:60])}</span>"
        f"<b>{esc(v.noi)}</b> — {esc(v.lam_gi)}</div>" for v in vt)
    sua = ""

    goc = line.goc or line.text
    doi_cau = ""
    if du_bi:
        nut = "".join(
            f"<form class=calt method=post action='/api/cv/pick'>"
            f"<input type=hidden name=job value='{esc(job)}'>"
            f"<input type=hidden name=out value='{esc(goc)}'>"
            f"<input type=hidden name=text value='{esc(b['text'])}'>"
            f"<button class='mbtn tiny'>đổi sang</button>"
            f"<span class=calttext>{to_khoa(b['text'], doi)}</span>"
            + ("".join(f"<span class='badge ok'>{esc(t)}</span>"
                       for t in b["trung"]) if b["trung"] else
               "<span class=muted>không trúng thêm gì</span>")
            + "</form>" for b in du_bi[:4])
        doi_cau = (f"<div class=cswap><b>đổi sang câu khác bạn đã viết</b>"
                   f"{nut}</div>")

    the = (f"<div class=ccard><div class=ckw>tin này đòi: {kho}</div>"
           f"{sua}{yeu}{doi_cau}</div>")

    truoc = (f"<span class=ctruoc>{esc(goc)}</span>"
             if goc != line.text else "")
    return (f"<li class='{' '.join(lop)}' id='cau{n}'>"
            f"<details class=cdet><summary>"
            f"<span class=csau>{to_khoa(line.text, doi, getattr(line, 'vet', ()))}</span>{truoc}"
            f"<span class=cno>{n}</span></summary>{the}</details></li>")


def dem_lai() -> None:
    """Đặt lại số đếm câu. Gọi TRƯỚC mỗi lần dựng một tờ."""
    _DEM[0] = 0

# --- TÔ TỪ KHOÁ ---------------------------------------------------------

def _vet(text: str, doi: set) -> list:
    """Các đoạn chữ trong `text` là từ khoá tin này ĐÒI. [(đầu, cuối), …]

    `alias_hits` chỉ trả về TÊN CHUẨN ("machine learning"), không nói chữ đó
    nằm ở đâu trong câu. Muốn tô thì phải biết vị trí, nên dò lại bằng chính
    mấy mẫu alias — cùng một luật khớp, không đẻ luật thứ hai.
    """
    from ..scoring.vocab import _ALIAS_RE
    thap = text.lower()
    ra = []
    for pattern, canonical in _ALIAS_RE.values():
        if canonical not in doi:
            continue
        for m in pattern.finditer(thap):
            ra.append((m.start(), m.end()))
    if not ra:
        return []
    # Gộp đoạn chồng nhau: "machine learning" và "learning" chồng lên nhau thì
    # tô hai lần là đẻ ra thẻ lồng nhau và HTML vỡ.
    ra.sort()
    gop = [ra[0]]
    for a, b in ra[1:]:
        if a <= gop[-1][1]:
            gop[-1] = (gop[-1][0], max(gop[-1][1], b))
        else:
            gop.append((a, b))
    return gop


def to_khoa(text: str, doi: set, vet=()) -> str:
    """Câu, đã escape, với TỪ KHOÁ tô xanh và VẾT VẤN ĐỀ gạch chân.

    Vẽ theo TỪNG KÝ TỰ rồi mới gom lại thành đoạn, chứ không bọc từng vệt một.
    Lý do: vệt chồng nhau là chuyện thường — một cụm vừa là từ khoá tin đòi,
    vừa nằm trong đoạn "thiếu số đo", vừa nằm trong đoạn "quá dài". Bọc lần
    lượt thì đẻ ra thẻ cắt chéo nhau và HTML vỡ; gom theo ký tự thì mọi tổ
    hợp đều ra đúng một lớp thẻ phẳng.
    """
    n = len(text)
    if not n:
        return ""
    la_khoa = [False] * n
    for a, b in _vet(text, doi):
        for i in range(a, min(b, n)):
            la_khoa[i] = True
    loai = [set() for _ in range(n)]
    for v in vet or ():
        for i in range(max(0, v.dau), min(v.cuoi, n)):
            loai[i].add(v.loai)

    ra, i = [], 0
    while i < n:
        khoa = tuple(sorted(loai[i])), la_khoa[i]
        j = i
        while j < n and (tuple(sorted(loai[j])), la_khoa[j]) == khoa:
            j += 1
        chu = esc(text[i:j])
        lop = (["kw"] if khoa[1] else []) + [f"v{k}" for k in khoa[0]]
        ra.append(f"<span class='{' '.join(lop)}'>{chu}</span>" if lop else chu)
        i = j
    return "".join(ra)
