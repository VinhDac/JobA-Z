"""BẢN CHẤM ĐIỂM — trước/sau, và vì sao từng câu được chọn hay bị bỏ.

Đây là thứ duy nhất trong tầng CV nói chuyện với NGƯỜI. Mọi module khác quyết
định; module này giải trình.

VÌ SAO CẦN. Máy đã quyết đủ thứ ở mỗi lần dựng — câu nào lên, xếp trước sau
thế nào, câu nào bị cấm, câu nào sửa chữ — và trước đây không chỗ nào cho Vin
xem. Một cái máy quyết mà không giải trình thì người dùng chỉ có hai lựa chọn:
tin mù, hoặc bỏ không dùng. Cả hai đều tệ hơn là đọc được lý do rồi tự sửa.

Và nó bắt được lỗi. Luật `rules.sentence_ok` cấm câu kể thất bại lên CV từ đầu,
nhưng bộ dựng chưa bao giờ tra luật đó — 3 câu bị cấm đi ra ngoài trên MỌI bản,
trong đó có "drawdown ran roughly 30% deeper than the model predicted". Không
ai thấy vì không có bản giải trình nào để mà đọc.

BỐ CỤC, theo thứ tự người đọc cần:

    tóm       trả lời được mấy phần yêu cầu · mấy câu vào · mấy câu sửa
    từng câu  SAU (in ra) · TRƯỚC (Vin viết) · trả lời gì · còn hổng gì
    bỏ        chia HAI nhóm, vì hai nhóm cần hai hành động khác nhau
    câm       tin đòi mà hồ sơ không nói được gì -> đây là việc phải làm
"""

from __future__ import annotations

from html import escape as esc

from .build import TailoredCV, dang_ke

# Lý do bỏ nào là LUẬT CẤM. Phân biệt này quyết định người dùng phải làm gì:
# câu bị cấm thì sửa chữ cũng vô ích (nó không thuộc CV), còn câu yếu hơn thì
# không phải sửa gì cả — tin khác sẽ dùng nó.
CAM = ("outcome failure", "opinion", "invites the reader", "too short")

VIET = {
    "outcome failure — belongs on the project page, not the CV":
        "kể thất bại — thuộc trang project, không thuộc CV",
    "opinion, not evidence of capability":
        "ý kiến, không phải bằng chứng năng lực",
    "too short to carry evidence":
        "quá ngắn để mang bằng chứng",
    "invites the reader to doubt you":
        "mời người đọc nghi ngờ bạn",
    "has hard evidence but wording may read badly — your call":
        "có bằng chứng cứng nhưng chữ dễ đọc xấu — bạn tự quyết",
    "weaker than what this posting asks for":
        "yếu hơn thứ tin này hỏi — tin khác sẽ dùng tới",
}


def _vi(why: str) -> str:
    return VIET.get(why, why)


def _la_cam(why: str) -> bool:
    return any(k in why for k in CAM)


def _chi_tiet(index: int, line) -> str:
    """Khối chi tiết cho MỘT câu — chỗ nút bấm trên tờ CV nhảy xuống.

    KHÔNG chép lại toàn văn câu. Câu đã nằm ngay trên tờ giấy rồi; chép lại là
    bắt người đọc đọc hai lần cùng một thứ và tự ghép hai bản với nhau. Ở đây
    chỉ có thứ tờ giấy KHÔNG nói được: tin đòi gì, vì sao sửa, còn hổng gì.
    """
    doi = ("".join(f"<span class='badge ok'>{esc(h)}</span>" for h in line.hits)
           if line.hits else
           "<span class=muted>tin này không gọi tên kỹ năng nào mà câu này "
           "trúng — nó lên CV vì mang quy mô hoặc phán đoán</span>")

    # CHỈ LÝ DO, không chép lại câu. Nút Trước/Sau ở trên đã cho xem tận mắt
    # chữ gốc rồi — chép nguyên câu thêm hai lần ở đây là bắt người đọc đọc
    # cùng một thứ bốn lượt.
    sua = ""
    if line.sua:
        buoc = "".join(f"<li>{esc(x.vi_sao)}</li>" for x in line.sua)
        sua = f"<div class=gsua><b>Máy đã sửa</b><ul>{buoc}</ul></div>"

    yeu = ""
    if line.yeu:
        muc = "".join(f"<li><b>{esc(y.noi)}</b> — {esc(y.lam_gi)}</li>"
                      for y in line.yeu)
        yeu = f"<div class=gyeu><b>Bạn cần viết thêm</b><ul>{muc}</ul></div>"

    xem = (f"<div class=gnote>⚠ {esc(_vi(line.review))}</div>"
           if line.review else "")

    return (f"<div class='gcau{' review' if line.review else ''}' id='ct{index}'>"
            f"<a class=gnum href='#cau{index}' title='về câu {index} trên CV'>"
            f"{index}</a>"
            f"<div class=gbody>"
            f"<div class=gdoi><span class=glab>Tin này đòi</span>{doi}</div>"
            f"{xem}{sua}{yeu}</div></div>")


def _bo(cv: TailoredCV) -> str:
    """Câu bị bỏ, CHIA HAI NHÓM — vì hai nhóm cần hai hành động khác nhau."""
    cam = [(t, w) for t, w in cv.dropped if _la_cam(w)]
    yeu = [(t, w) for t, w in cv.dropped if not _la_cam(w)]

    def _khoi(rows, tieu_de, dan) -> str:
        if not rows:
            return ""
        muc = "".join(
            f"<li><span class=dtext>{esc(t)}</span>"
            f"<span class=dwhy>{esc(_vi(w))}</span></li>" for t, w in rows)
        return (f"<h4 class=cvsec>{esc(tieu_de)} ({len(rows)})</h4>"
                f"<ul class=droplist>{muc}</ul><div class=note>{dan}</div>")

    return (
        _khoi(cam, "Luật không cho lên CV",
              "Sửa chữ cũng không cứu được — mấy câu này không thuộc CV. "
              "Chúng KHÔNG bị xoá khỏi hồ sơ: chỗ của chúng là buổi phỏng vấn, "
              "nơi người đọc có kinh nghiệm coi sự trung thực là điểm mạnh. "
              "Trước mặt người sàng 200 CV một buổi chiều thì không.")
        + _khoi(yeu, "Để dành cho tin khác",
                "Mấy câu này hợp lệ — chỉ là tin NÀY hỏi thứ khác. Không phải "
                "sửa gì cả; bản CV cho tin khác sẽ dùng tới chúng."))


def diem(cv: TailoredCV) -> dict:
    """Mấy con số của bản này. Tính ở một chỗ để chữ và số không lệch nhau."""
    lines = [l for s in cv.sections for l in s.lines
             if s.kind in ("experience", "project")]
    return {
        "vao": len(lines),
        "sua": sum(1 for l in lines if l.sua),
        "hong": sum(1 for l in lines if l.yeu),
        "xem": sum(1 for l in lines if l.review),
        "bo_cam": sum(1 for _, w in cv.dropped if _la_cam(w)),
        "bo_yeu": sum(1 for _, w in cv.dropped if not _la_cam(w)),
        "doi": len(cv.wanted),
        "tra_loi": len(cv.covered),
        "cam": len(cv.missing),
    }


def head(cv: TailoredCV) -> str:
    """ĐIỂM + THỐNG KÊ + NÚT TRƯỚC/SAU. Đứng trên cùng, trước cả tờ CV.

    Nút Trước/Sau là một `<input type=checkbox>` ẩn, không phải JavaScript:
    đổi qua đổi lại một cái nhãn thì không đáng gọi thêm một trình nghe, và
    không JS thì nó không bao giờ hỏng.
    """
    d = diem(cv)
    ty = f"{d['tra_loi']}/{d['doi']}" if d["doi"] else "—"
    o = (("<div class=gsum>"
          f"<span class=gstat><b>{ty}</b>yêu cầu của tin được trả lời</span>"
          f"<span class=gstat><b>{d['vao']}</b>câu lên bản này</span>"
          f"<span class=gstat><b>{d['sua']}</b>câu máy sửa chữ</span>"
          f"<span class=gstat><b>{d['hong']}</b>câu còn hổng</span>"
          f"<span class=gstat><b>{d['bo_cam'] + d['bo_yeu']}</b>câu bị bỏ</span>"
          "</div>"))
    # CHECKBOX ĐỨNG NGOÀI `.gtoggle`, cùng cấp với tờ CV. Luật CSS dùng bộ
    # chọn anh-em `~` để bật/tắt chữ trước-sau; nhét checkbox vào trong một
    # <div> thì nó là cháu chứ không phải anh em, và cái nút bấm không làm gì
    # cả — im lặng, không lỗi. Đã xảy ra thật ở bản đầu.
    # <label for=...> thì vẫn với tới được qua id dù nằm khác cha.
    nut = ("<input type=checkbox id=cvtruoc class=gswitch hidden>"
           "<div class=gtoggle>"
           "<label for=cvtruoc><span class=gt1>Sau khi sửa</span>"
           "<span class=gt2>Trước khi sửa</span></label>"
           "<span class=muted>bấm để xem chữ gốc bạn viết</span></div>")
    chu = ("<div class=note><b class=ksua>Xanh</b> = máy đã sửa chữ, kiểm lại "
           "xem có đúng ý bạn không. <b class=khong>Cam</b> = còn việc cho "
           "bạn. Rê chuột xem nhanh, bấm vào nhảy xuống lý do. Máy chỉ "
           "<b>cắt và xếp lại</b> chữ của bạn — mọi từ trên bản in ra đều có "
           "trong câu bạn đã viết.</div>")
    # BỌC .cvaudit — cổng kiểm lúc in bắt được: `<h4 class=cvsec>Chấm điểm
    # bản này</h4>` đứng trần nên nó IN RA GIẤY, và đẩy tờ CV sang 2 trang.
    # Nút Trước/Sau phải đứng NGOÀI bọc: luật CSS dùng bộ chọn anh-em để với
    # tới tờ CV, nhét vào trong một <div> là nó hết với tới.
    return (f"{nut}<div class=cvaudit>"
            f"<h4 class=cvsec>Chấm điểm bản này</h4>{o}{chu}</div>")


def chi_tiet(cv: TailoredCV) -> str:
    """Phần dưới tờ CV: vì sao từng câu như thế, và những câu KHÔNG lên bài."""
    thu = 0
    khoi = []
    for section in cv.sections:
        if section.kind not in ("experience", "project"):
            continue
        for line in section.lines:
            thu += 1
            # Câu không sửa, không hổng, không cần xem lại thì KHÔNG có gì để
            # nói — đừng đẻ ra một khối rỗng chỉ để cho đủ bộ.
            if dang_ke(line):
                khoi.append(_chi_tiet(thu, line))

    cam = ""
    if cv.missing:
        cam = ("<h4 class=cvsec>Tin đòi mà hồ sơ câm</h4>"
               "<div class=chiprow>"
               + "".join(f"<span class='badge warn'>{esc(m)}</span>"
                         for m in cv.missing)
               + "</div><div class=note>Hoặc bạn thật sự chưa có, hoặc có mà "
                 "chưa viết ra. Cái thứ hai sửa được ngay: thêm một câu vào "
                 "khối ở tab CV.</div>")

    tieu = ("<h4 class=cvsec>Vì sao từng câu như thế</h4>" if khoi else "")
    # BỌC TRONG .cvaudit — luật @media print đã ẩn lớp này sẵn. Bản chấm điểm
    # là chuyện giữa app và Vin; tờ giấy gửi đi chỉ có tờ CV.
    return ("<div class=cvaudit>" + tieu + "".join(khoi)
            + _bo(cv) + cam + "</div>")
