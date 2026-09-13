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


def vi(why: str) -> str:
    """Lý do bỏ, sang tiếng Việt. Dùng chung với màn Soạn khối."""
    return VIET.get(why, why)


def _la_cam(why: str) -> bool:
    return any(k in why for k in CAM)


def _bo(cv: TailoredCV) -> str:
    """Câu bị bỏ, CHIA HAI NHÓM — vì hai nhóm cần hai hành động khác nhau."""
    cam = [(t, w) for t, w in cv.dropped if _la_cam(w)]
    yeu = [(t, w) for t, w in cv.dropped if not _la_cam(w)]

    def _khoi(rows, tieu_de, dan) -> str:
        if not rows:
            return ""
        muc = "".join(
            f"<li><span class=dtext>{esc(t)}</span>"
            f"<span class=dwhy>{esc(vi(w))}</span></li>" for t, w in rows)
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
        # Xem live.cv_versions: wanted/covered là cặp NÓI DỐI (mẫu số nhặt
        # cả đoạn giới thiệu công ty, tử số bỏ qua mục Technical skills).
        "doi": len(cv.asked),
        "tra_loi": len(cv.on_paper),
        "cam": len(cv.missing),
    }


def cho_xem(cv: TailoredCV) -> list:
    """Mọi CHỖ đáng xem trên tờ này, theo loại. [(loại, nhãn, số), …]

    Đếm theo CHỖ chứ không theo câu: một câu có thể vừa thiếu số vừa quá dài,
    và đó là hai việc phải làm, không phải một.
    """
    from collections import Counter
    dem: Counter = Counter()
    for sec in cv.sections:
        if sec.kind not in ("experience", "project"):
            continue
        for line in sec.lines:
            for v in getattr(line, "vet", ()) or ():
                dem[v.loai] += 1
    ten = {"thieu_so": "thiếu số đo", "qua_dai": "quá dài",
           "lac_de": "không chạm tin này", "da_sua": "máy đã sửa chữ"}
    thu_tu = ("thieu_so", "qua_dai", "lac_de", "da_sua")
    return [(k, ten[k], dem[k]) for k in thu_tu if dem[k]]


def head(cv: TailoredCV) -> str:
    """ĐIỂM + CHỖ CẦN XEM + nút Trước/Sau. Đứng trên cùng, trước cả tờ CV.

    Con số đầu tiên phải trả lời "tờ này còn việc gì" — mở ra là biết ngay có
    5 chỗ phải xem, không phải bấm từng dòng mới phát hiện ra.
    """
    d = diem(cv)
    ty = f"{d['tra_loi']}/{d['doi']}" if d["doi"] else "—"
    cho = cho_xem(cv)
    can = sum(n for k, _, n in cho if k != "da_sua")

    o = ("<div class=gsum>"
         f"<span class='gstat {'act' if can else ''}'><b>{can}</b>"
         f"chỗ cần bạn xem</span>"
         f"<span class=gstat><b>{ty}</b>thứ tin này đòi, CV nói được</span>"
         f"<span class=gstat><b>{d['vao']}</b>câu lên bản này</span>"
         f"<span class=gstat><b>{len(cv.missing)}</b>thứ hồ sơ câm</span>"
         "</div>")
    # CHÚ GIẢI vệt — không có nó thì mấy đường gạch chân là câu đố.
    chu_giai = ("<div class=glegend>"
                + "".join(f"<span class='gleg v{k}'>{esc(nhan)} <b>{n}</b></span>"
                          for k, nhan, n in cho)
                + "<span class='gleg kw'>từ khoá tin này đòi</span></div>"
                if cho else "")
    nut = ("<input type=checkbox id=cvtruoc class=gswitch hidden>"
           "<div class=gtoggle>"
           "<label for=cvtruoc><span class=gt1>Sau khi sửa</span>"
           "<span class=gt2>Trước khi sửa</span></label>"
           "<span class=muted>bấm để xem chữ gốc bạn viết</span></div>")
    chu = ("<div class=note>Gạch chân là chỗ máy có ý kiến — bấm vào chính "
           "đoạn đó để xem cách sửa và đổi sang câu khác bạn đã viết. Máy chỉ "
           "<b>cắt và xếp lại</b> chữ của bạn; mọi từ trên bản in ra đều có "
           "trong câu bạn đã viết.</div>")
    return (f"{nut}<div class=cvaudit>"
            f"<h4 class=cvsec>Chấm điểm bản này</h4>{o}{chu_giai}{chu}</div>")


def chi_tiet(cv: TailoredCV) -> str:
    """Phần dưới tờ CV — CHỈ thứ KHÔNG thuộc về một câu nào.

    Từng câu đã được chữa NGAY TRÊN BÀI (xem render._muc): bấm vào dòng là
    thẻ mở ra tại chỗ, nói tin này đòi gì, máy sửa gì, còn hổng gì, đổi sang
    câu nào. Nên ở đây KHÔNG lặp lại từng câu nữa — lặp là bắt người đọc đọc
    hai lần cùng một thứ rồi tự ghép "câu 3 ở dưới" với câu nào ở trên.

    Còn lại đúng hai thứ, và cả hai đều nói về TỜ GIẤY chứ không về một dòng:
        câu KHÔNG lên bài   — vì sao chúng vắng mặt
        tin đòi mà hồ sơ câm — việc phải làm, và không câu nào lấp được
    """
    cam = ""
    if cv.missing:
        cam = ("<h4 class=cvsec>Tin đòi mà hồ sơ câm</h4>"
               "<div class=chiprow>"
               + "".join(f"<span class='badge warn'>{esc(m)}</span>"
                         for m in cv.missing)
               + "</div><div class=note>Không câu nào trong hồ sơ lấp được "
                 "mấy chỗ này — máy chỉ chọn được chữ bạn đã viết. Hoặc bạn "
                 "thật sự chưa có, hoặc có làm mà chưa viết ra; cái thứ hai "
                 "sửa được tối nay bằng một câu.</div>")
    # BỌC .cvaudit — luật @media print đã ẩn lớp này sẵn.
    return "<div class=cvaudit>" + _bo(cv) + cam + "</div>"
