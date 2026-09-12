"""Vẽ CV đã tuỳ biến ra HTML — phần trông giống TỜ GIẤY thật.

CHỈ tờ giấy. Phần giải trình — bỏ gì, vì sao, câu nào đã sửa chữ — nằm ở
`cv/report.py`: nó nói chuyện với người, còn chỗ này dựng thứ đem đi gửi.
Trước đây `audit()` nằm lẫn ở đây và chỉ nói được một nửa (bỏ gì), bằng tiếng
Anh, không có trước/sau.
"""

from __future__ import annotations

from html import escape as esc

from .build import TailoredCV, dang_ke

LABEL = {"experience": "Experience", "project": "Selected projects",
         "education": "Education", "cert": "Certifications", "skill": "Technical skills"}


def paper(cv: TailoredCV, cham: bool = False) -> str:
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
            items = "".join(_muc(l, cham) for l in section.lines)
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


def _muc(line, cham: bool) -> str:
    """Một dòng trên tờ CV. Không chấm thì trả về đúng dòng chữ, không hơn."""
    if not cham:
        return (f"<li{' class=review' if line.review else ''}>{esc(line.text)}"
                + (f"<span class=rv>{esc(line.review)}</span>"
                   if line.review else "") + "</li>")

    _DEM[0] += 1
    n = _DEM[0]
    # DẤU nói lên VIỆC PHẢI LÀM, nên chỉ hai loại — thêm loại thứ ba là bắt
    # người đọc học một bảng chú giải trước khi đọc được CV của chính mình.
    lop = []
    if line.sua:
        lop.append("dsua")          # máy đã sửa chữ -> kiểm lại xem có đúng ý không
    if line.yeu:
        lop.append("dhong")         # còn hổng -> Vin phải viết thêm
    if line.review:
        lop.append("dxem")

    # Mách nước lúc rê chuột: một câu, đủ để quyết có cần bấm vào không.
    mach = []
    if line.hits:
        mach.append("trả lời: " + ", ".join(line.hits))
    if line.sua:
        mach.append("máy sửa chữ")
    if line.yeu:
        mach.append("còn hổng: " + ", ".join(y.noi for y in line.yeu))
    tip = (f"<span class=ctip>{esc(' · '.join(mach))}</span>" if mach else "")

    truoc = ""
    if line.goc and line.goc != line.text:
        truoc = f"<span class=ctruoc>{esc(line.goc)}</span>"
    # Có đích thì mới làm link. Link trỏ vào hư không là nút bấm không làm gì
    # — thứ người dùng bấm một lần rồi thôi tin cả trang.
    chu = f"<span class=csau>{esc(line.text)}</span>{truoc}"
    than = (f"<a class=cjump href='#ct{n}'>{chu}</a>" if dang_ke(line) else chu)
    return (f"<li class='{' '.join(lop)}' id='cau{n}'>{than}"
            f"<span class=cno>{n}</span>{tip}</li>")


def dem_lai() -> None:
    """Đặt lại số đếm câu. Gọi TRƯỚC mỗi lần dựng một tờ."""
    _DEM[0] = 0
