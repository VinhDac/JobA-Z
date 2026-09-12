"""Profile — sinh HTML từ schema. CHỈ VẼ, không có luật nghiệp vụ ở đây.

Thêm câu hỏi thì sửa profile/schema.py, file này không phải đụng tới.
Thấy mình sắp viết `if question.id == "..."` ở đây -> viết nhầm chỗ.
"""

from __future__ import annotations

from html import escape as esc
from typing import Any

from ...profile.schema import (
    BLOCKS, LONGTEXT, MULTI, ROWS, SINGLE, TEXT, SECTIONS, Question, Section,
    all_questions, suggestions,
)
from ..layout import page

Answers = dict[str, Any]
# Số gợi ý bày sẵn lúc chưa gõ. Bày hết 60 cái là dồn mắt người xem;
# phần còn lại tìm bằng cách gõ.
_TEN_KHO = {"titles": "chức danh", "skills": "từ khoá",
            "industries": "ngành"}
# Kho tới bao nhiêu mục thì còn cho "chọn tất cả". Trên ngưỡng này, chọn hết
# là tự tay vô hiệu hoá bộ lọc — giữ lại mọi tin thì lọc để làm gì.
_CHON_HET = 12
OTHER_SUFFIX = "__other"


def _values(answers: Answers, qid: str) -> list[str]:
    value = answers.get(qid)
    if value is None or value == "":
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def _field(question: Question, answers: Answers,
           kho: dict[str, list[str]] | None = None) -> str:
    chosen = set(_values(answers, question.id))
    parts: list[str] = []

    if question.kind in (SINGLE, MULTI):
        input_type = "radio" if question.kind == SINGLE else "checkbox"
        parts.append("<div class=opts>")
        for option in question.options:
            checked = " checked" if option.value in chosen else ""
            note = f"<span class=note>{esc(option.note)}</span>" if option.note else ""
            parts.append(
                f"<label class=opt><input type={input_type} name={esc(question.id)} "
                f"value='{esc(option.value)}'{checked}>"
                f"<span><span class=lbl>{esc(option.label)}</span>{note}</span></label>"
            )
        parts.append("</div>")

        if question.allow_other:
            known = {o.value for o in question.options}
            extra = ", ".join(v for v in _values(answers, question.id) if v not in known)
            parts.append(
                f"<input class='txt other' type=text name='{esc(question.id)}{OTHER_SUFFIX}' "
                f"value='{esc(extra)}' placeholder='Add your own — separate with commas'>"
            )

    elif question.kind == BLOCKS:
        parts.append(_o_khoi(question, answers, kho))

    elif question.kind == ROWS:
        parts.append(_o_hoc_van(question, answers))

    elif question.tags:
        parts.append(_o_the(question, answers, kho))

    elif question.kind == TEXT:
        parts.append(
            f"<input class=txt type=text name={esc(question.id)} "
            f"value='{esc(str(answers.get(question.id, '')))}' "
            f"placeholder='{esc(question.placeholder)}'>"
        )

    elif question.kind == LONGTEXT:
        rows = 6 if question.placeholder.count("\n") < 3 else 8
        parts.append(
            f"<textarea class=txt rows={rows} name={esc(question.id)} "
            f"placeholder='{esc(question.placeholder)}'>"
            f"{esc(str(answers.get(question.id, '')))}</textarea>"
        )

    return "".join(parts)


def _question(question: Question, answers: Answers,
              kho: dict[str, list[str]] | None = None) -> str:
    tag = "<span class=req>required</span>" if question.required else ""
    why = f"<p class=why>{esc(question.why)}</p>" if question.why else ""
    return (
        f"<section class=q><h3>{esc(question.text)}{tag}</h3>"
        f"{why}{_field(question, answers, kho)}</section>"
    )


def _steps(current_id: str, done_ids: set[str]) -> str:
    items = "".join(
        f"<li class='{'done' if s.id in done_ids else ''}"
        f"{' now' if s.id == current_id else ''}'>"
        f"<a href='/profile/{esc(s.id)}'>{esc(s.title)}</a></li>"
        for s in SECTIONS
    )
    return f"<ol class=steps>{items}</ol>"


def render_section(section: Section, answers: Answers, done_ids: set[str],
                   next_label: str, gate_missing: list[str] | None = None,
                   kho: dict[str, list[str]] | None = None) -> str:
    optional = "<span class=opt-tag>optional</span>" if section.optional else ""
    # Câu ẩn có trong schema để LƯU được, nhưng không vẽ ra form.
    questions = "".join(_question(q, answers, kho)
                        for q in section.questions if not q.hidden)

    # Lưu xong mà còn thiếu câu bắt buộc thì người dùng bị đưa NGƯỢC về đây.
    # Bị quay lại mà không biết vì sao là lỗi, không phải chu trình — nên phải
    # nói rõ còn mấy câu và chúng nằm ở đâu.
    nhac = ""
    if gate_missing:
        qs = all_questions()
        ten = " · ".join(esc(qs[q].text) for q in gate_missing if q in qs)
        nhac = (f"<div class='gate block'><b>Còn {len(gate_missing)} câu nữa "
                f"là app chạy được.</b> {ten}</div>")

    return page(
        section.title,
        _steps(section.id, done_ids)
        + f"<h1>{esc(section.title)}{optional}</h1>"
        + nhac
        + f"<p class=lead>{esc(section.why)}</p>"
        + f"<form method=post>{questions}"
        + f"<div class=actions><button class=primary type=submit>{esc(next_label)}</button>"
        + "<a class=skip href='/profile'>Review profile</a></div></form>",
        active="/profile",
    )


def _o_the(question: Question, answers: Answers,
           kho: dict[str, list[str]] | None = None) -> str:
    """Ô TÌM ở trên · gợi ý ở giữa · thứ ĐÃ CHỌN ở dưới. Ba vùng, ba việc.

    Gộp ô nhập vào chung khung thẻ thì khung vừa là chỗ gõ vừa là chỗ hiện
    kết quả: đầy vài thẻ là hết chỗ, hàng gợi ý bị ép cụt. Và gõ dở rồi bấm đi
    chỗ khác là chữ dở biến thành thẻ — "analys", "Quant" lọt vào hồ sơ thật
    đúng kiểu đó.
    """
    thoi = question.tags
    co = _tach(str(answers.get(question.id, "")), thoi)
    da = {v.lower() for v in co}

    chips = "".join(
        f"<span class=tag>{esc(t)}"
        f"<input type=hidden name={esc(question.id)} value='{esc(t)}'>"
        # type=button — thiếu nó thì bấm × là gửi luôn cả form
        f"<button type=button class=untag data-untag title='bỏ'>×</button>"
        f"</span>" for t in co)
    chon = (f"<div class=chosenhead>đã chọn</div>"
            f"<div class=tagbox data-tags='{esc(question.id)}'>{chips}"
            f"<span class=tagempty{' hidden' if co else ''}>"
            f"tìm ở ô trên rồi bấm để thêm</span></div>")

    nguon = (kho or {}).get(question.suggest) or suggestions(question.suggest)
    goi_y = [g for g in nguon if g.lower() not in da]
    if not goi_y:
        # Chưa có kho chức danh: KHÔNG bày danh sách gõ tay cho có. Mời lấy từ
        # tin thật — đó mới trả lời đúng câu "viết như trên tin".
        moi = ("<button type=button class='mbtn tiny' "
               "data-post='/api/titles/refresh' data-arg='lay'>"
               "Lấy kho chức danh từ tin thật (~15 giây)</button>"
               if question.suggest == "titles" else "")
        return f"<div class=tagfield data-tagfield>{moi}{chon}</div>"

    nut = "".join(
        f"<button type=button class=addtag data-addtag='{esc(g)}'>{esc(g)}</button>"
        for g in goi_y)
    ten = _TEN_KHO.get(question.suggest, "gợi ý")
    # Kho nhỏ thì "chọn hết" là một cú bấm thay cho bảy. Kho lớn (chức danh,
    # kỹ năng) KHÔNG có nút này: chọn cả 60 chức danh là tự tay làm lưới lọc
    # thành vô nghĩa, giữ lại mọi tin.
    tat_ca = ("<button type=button class='mbtn tiny' data-addall>"
              f"chọn tất cả {len(goi_y)}</button>" if len(goi_y) <= _CHON_HET else "")
    return (
        f"<div class=tagfield data-tagfield>"
        f"<div class=findrow>"
        f"<input class='txt tagfind' type=text autocomplete=off"
        f" placeholder='gõ để tìm trong {len(goi_y)} {ten}…'>{tat_ca}</div>"
        f"<div class=sugdrop data-sugdrop>{nut}"
        f"<div class=sugnone hidden>không có trong kho — Enter để thêm"
        f" nguyên văn</div></div>{chon}</div>")


# Ô học vấn: MỖI BẰNG MỘT HÀNG. Tên ô trùng nhau giữa các hàng — trình duyệt
# gửi lên thành mảng song song theo đúng thứ tự hàng, server zip lại.
_COT = (("degree", "Bằng", "MSc"),
        ("discipline", "Ngành", "Computational Finance"),
        ("school", "Trường", "Royal Holloway, University of London"),
        ("start", "Từ", "Sep 2025"),
        ("end", "Đến", "Sep 2026"),
        ("note", "Điểm / hạng", "IPM 86 · Data Analysis 83"))


def _hang_hoc_van(e=None) -> str:
    v = {"degree": getattr(e, "degree", ""), "discipline": getattr(e, "discipline", ""),
         "school": getattr(e, "school", ""), "note": getattr(e, "note", "")}
    v["start"] = _khi(getattr(e, "start_month", 0), getattr(e, "start_year", 0))
    v["end"] = _khi(getattr(e, "end_month", 0), getattr(e, "end_year", 0))
    o = "".join(
        f"<label class='edufield {esc(key)}'><span>{esc(nhan)}</span>"
        f"<input class=txt type=text name='edu_{esc(key)}' value='{esc(v[key])}'"
        f" placeholder='{esc(vd)}' autocomplete=off></label>"
        for key, nhan, vd in _COT)
    return (f"<div class=edurow>{o}"
            f"<button type=button class=edudrop data-rowdrop title='bỏ bằng này'>×</button>"
            f"</div>")


def _khi(thang: int, nam: int) -> str:
    if not nam:
        return ""
    return f"{_THANG[thang - 1]} {nam}" if thang else str(nam)


_THANG = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _o_hoc_van(question: Question, answers: Answers) -> str:
    """Bằng cấp thành HÀNG có ô rời, không phải một khối chữ thô.

    Lý do không để text thô: ngữ pháp của ô này là thứ CÓ TẢI — apply/answer
    đọc nó ra ngày tốt nghiệp để điền vào form xin việc. Gõ thô thì sai một
    dấu gạch là mất tháng, và mỗi lá đơn Vin phải tự chọn lại ngày.

    Form ghi ra bằng `answer.line()`, đọc vào bằng `answer.educations()` —
    một ngữ pháp, hai chiều, không có bản sao nào để lệch.
    """
    from ...apply.answer import educations
    co = educations(str(answers.get(question.id, "")))
    hang = "".join(_hang_hoc_van(e) for e in co) or _hang_hoc_van()
    return (f"<div class=edurows data-rows>{hang}</div>"
            f"<button type=button class='mbtn tiny' data-rowadd>+ thêm bằng</button>")


def _o_khoi(question: Question, answers: Answers,
            kho: dict | None = None) -> str:
    """Kinh nghiệm / project: mỗi thứ một KHỐI, mỗi khối một hàng.

    Đây là thông tin cá nhân, nên chỗ sửa là hồ sơ. Chỗ LƯU vẫn là khối trong
    cv_text — bộ chấm điểm và bộ dựng CV đều đọc ở đó, nên viết ra bản sao thứ
    hai là chắc chắn có ngày hai bên lệch nhau.

    Mỗi dòng trong ô mô tả là MỘT CÂU có thể lên CV. Máy chọn câu nào hợp tin
    nào — viết thêm câu là CV trúng hơn, không phải chọn khéo hơn.
    """
    from ...cv.blocks import parse as parse_cv
    loai = question.block_kind
    co = [b for b in parse_cv(str(answers.get("cv_text") or "")) if b.kind == loai]
    hang = "".join(_hang_khoi(question, b) for b in co) or _hang_khoi(question)
    ten = "việc" if loai == "experience" else "project"
    return (f"<div class=blockrows data-rows>{hang}</div>"
            f"<button type=button class='mbtn tiny' data-rowadd>+ thêm {ten}</button>")


def _hang_khoi(question: Question, b=None) -> str:
    key = question.id
    title = getattr(b, "title", "")
    meta = getattr(b, "meta", "")
    body = "\n".join(getattr(b, "lines", []) or [])
    nhan_meta = ("Nơi làm · thời gian" if question.block_kind == "experience"
                 else "Ghi chú · thời gian")
    return (
        "<div class=blockrow>"
        f"<label class='edufield btitle'><span>Tên</span>"
        f"<input class=txt type=text name='{esc(key)}__title' value='{esc(title)}'"
        f" placeholder='Quantitative Analyst — Schonfeld' autocomplete=off></label>"
        f"<label class='edufield bmeta'><span>{esc(nhan_meta)}</span>"
        f"<input class=txt type=text name='{esc(key)}__meta' value='{esc(meta)}'"
        f" placeholder='Jan 2025 – Sep 2025' autocomplete=off></label>"
        f"<button type=button class=edudrop data-rowdrop title='bỏ khối này'>×</button>"
        f"<label class='edufield bbody'><span>Đã làm được gì — mỗi dòng một câu</span>"
        f"<textarea class=txt rows=4 name='{esc(key)}__body'"
        f" placeholder='{esc(question.placeholder)}'>{esc(body)}</textarea></label>"
        f"</div>")


def _tach(gia_tri: str, thoi: str) -> list[str]:
    """Chuỗi đã lưu -> danh sách thẻ. ĐỌC được cả hình dạng cũ.

    Dữ liệu cũ lưu kiểu "A · B · C" trên một dòng (CV viết vậy, máy nhập chép
    y nguyên). Chỉ cắt theo dấu nối mới thì cả cụm thành MỘT thẻ khổng lồ, mà
    cv/build.py lại đọc theo dòng nên nó vẫn tưởng chỉ có một chứng chỉ.

    Đọc rộng, ghi chặt: nhận cả hai kiểu, nhưng lưu lại luôn theo `thoi`. Lần
    bấm Lưu đầu tiên là dữ liệu cũ tự nắn về hình dạng đúng — không cần
    migration, không cần người dùng làm gì.
    """
    chinh = thoi.strip() or "\n"
    phan = [v for v in gia_tri.split(chinh)]
    if len(phan) <= 1:                       # chưa từng cắt được -> thử kiểu cũ
        for cu in (" · ", " | ", "; "):
            if cu in gia_tri:
                phan = gia_tri.split(cu)
                break
    return [v.strip() for v in phan if v.strip()]


def _shown(question: Question, answers: Answers) -> str:
    values = _values(answers, question.id)
    if not values:
        return "<em class=empty>— not answered —</em>"
    if question.options:
        labels = {o.value: o.label for o in question.options}
        return " · ".join(esc(labels.get(v, v)) for v in values)
    text = values[0]
    return f"<span class=val>{esc(text if len(text) <= 300 else text[:300] + '…')}</span>"


def render_summary(answers: Answers, versions: int, missing_gate: list[str]) -> str:
    questions = all_questions()

    if missing_gate:
        names = " · ".join(esc(questions[q].text) for q in missing_gate)
        gate = (
            f"<div class='gate block'><b>Can't search yet.</b> Still missing: {names}. "
            "<a href='/profile/muc_tieu'>Fill these in</a></div>"
        )
    else:
        gate = "<div class='gate ok'><b>Ready to search.</b> The system may now pull postings (M2).</div>"

    blocks: list[str] = []
    for section in SECTIONS:
        filled = sum(1 for q in section.questions if _values(answers, q.id))
        optional = "<span class=opt-tag>optional</span>" if section.optional else ""
        rows = "".join(
            f"<tr><th>{esc(q.text)}</th><td>{_shown(q, answers)}</td></tr>"
            for q in section.questions
        )
        blocks.append(
            f"<h2>{esc(section.title)}{optional}"
            f"<span class=count>{filled}/{len(section.questions)}</span>"
            f"<a class=edit href='/profile/{esc(section.id)}'>edit</a></h2>"
            f"<table class=sum>{rows}</table>"
        )

    return page(
        "Profile",
        "<h1>Your profile</h1>"
        + "<div class=frow style='margin:0 0 14px'>"
          "<a class='chip on' href='/profile/import'>Import a CV</a>"
          "<a class=chip href='/profile/health'>CV health</a></div>"
        f"<p class=lead>{versions} version(s) saved. Every edit writes a new version rather than "
        "overwriting — this profile is living data, not a form you fill in once.</p>"
        f"{gate}{''.join(blocks)}",
        active="/profile",
    )
