"""Dựng CV riêng cho một JD — CV LÀ TỜ TRẢ LỜI.

Mọi câu trên CV đều là câu Vin đã viết trong hồ sơ. Không có LLM ở đây.

ĐỔI GỐC (10/09): trước đây đây là bộ máy chọn THỨ HAI. Tầng chấm điểm tra hồ
sơ theo yêu cầu JD ra một con số; tầng này lại đi cân trọng số từ đầu rồi lấp
cho đủ `BUDGET`. Hai đường độc lập, nên lệch nhau — đo được: một tin 92 điểm
nhận bản CV mà **76% số câu không chạm gì tới nó**, và 2/18 câu là rác bóc từ
PDF ("·", "Sep 2025") vẫn đi ra ngoài vì có ô trống phải lấp.

Giờ chỉ còn MỘT bộ máy. `score.build_index` gom hồ sơ thành bằng chứng ở mức
CÂU; tầng này chỉ hỏi lại đúng chỉ số đó:

    họ hỏi gì  ->  câu nào của mình trả lời  ->  in ra, theo thứ tự họ hỏi

Câu không trả lời gì thì không lên. Không còn ngân sách, nên độ dài CV là SỐ
ĐO của hồ sơ chứ không phải một cái đích: năm câu nghĩa là hồ sơ trả được năm
thứ. Muốn dài hơn thì làm thêm project, không phải lấp thêm câu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..ingest.base import norm
from ..scoring.vocab import alias_hits
from . import rewrite, rules
from .blocks import Block, parse, sentences


@dataclass
class Line:
    text: str
    weight: float = 0.0
    hits: list[str] = field(default_factory=list)   # kỹ năng JD đòi mà câu này trúng
    review: str = ""                                # giữ nhưng cần Vin xem lại
    # BẢN SO SÁNH sống ở đây. `goc` là câu Vin viết, `text` là câu sẽ in ra —
    # khác nhau thì `sua` nói rõ phép nào đã áp và vì sao. Không giữ `goc` thì
    # không có "trước" nào để mà so, và người dùng phải tin lời máy.
    goc: str = ""
    sua: list = field(default_factory=list)         # [rewrite.Sua]
    yeu: list = field(default_factory=list)         # [rewrite.Yeu] — máy chỉ, Vin sửa
    # VẾT = chỗ nào TRONG câu, không phải câu nào. Gạch cả dòng thì người đọc
    # vẫn phải tự dò; gạch đúng cụm chữ thì mắt tới thẳng chỗ phải sửa.
    vet: list = field(default_factory=list)         # [rewrite.Vet]


def dang_ke(line: Line) -> bool:
    """Câu này có gì để GIẢI TRÌNH không.

    MỘT chỗ quyết. Bút đỏ trên bài và khối chi tiết ở dưới phải hỏi CÙNG một
    câu hỏi: hỏi ở hai chỗ thì chúng trôi khỏi nhau, và dấu bấm được trên bài
    trỏ xuống một cái neo không tồn tại — bấm vào không nhảy đi đâu cả, im
    lặng. Đã xảy ra với câu 6 và 7.
    """
    return bool(line.sua or line.yeu or line.review or line.hits)


@dataclass
class Section:
    kind: str
    title: str
    meta: str
    lines: list[Line] = field(default_factory=list)


@dataclass
class TailoredCV:
    header: list[str]
    summary: str
    sections: list[Section]
    dropped: list[tuple[str, str]]      # (câu, lý do bỏ)
    wanted: list[str]                   # kỹ năng JD quan tâm (rộng — để xếp thứ tự)
    covered: list[str]                  # trong đó CV này nói được
    missing: list[str]                  # JD đòi mà hồ sơ không có
    # HAI TRƯỜNG CHO CON SỐ HIỆN RA. Tách khỏi wanted/covered vì chúng đo
    # thứ khác: wanted rộng để xếp câu, asked hẹp để làm mẫu số thật thà.
    asked: list[str] = field(default_factory=list)    # tin THẬT SỰ đòi
    on_paper: list[str] = field(default_factory=list) # TỜ GIẤY nói ra được


def skills_in(text: str) -> set[str]:
    """Kỹ năng có mặt trong đoạn chữ. Luật khớp nằm ở vocab.alias_hits —
    MỘT chỗ, vì trước đây score._signals giữ một bản sao và hai bên phải tự
    nhớ mà sửa cùng nhau."""
    return set(alias_hits(norm(text)))


def wanted_skills(explain: dict | None, jd_text: str = "") -> set[str]:
    """Kỹ năng tin này quan tâm.

    Quét CẢ tin, không chỉ mấy dòng gạch đầu dòng: Jane Street nhắc
    "time series analysis, feature engineering" ở đoạn mở đầu chứ không
    nằm trong phần "About You".
    """
    out: set[str] = set(skills_in(jd_text))
    for req in (explain or {}).get("requirements", []):
        out |= skills_in(req["text"])
    return out


def asked_skills(explain: dict | None) -> set[str]:
    """Kỹ năng tin này THẬT SỰ ĐÒI — chỉ từ DÒNG YÊU CẦU, không từ cả tin.

    Khác `wanted_skills` ở đúng một chỗ, và chỗ đó quyết định con số hiện ra:

        wanted  quét cả tin  -> dùng để XẾP THỨ TỰ câu. Rộng là tốt: bắt nhầm
                một chữ thì cùng lắm xếp sai chỗ, không ai thấy.
        asked   chỉ dòng yêu cầu -> dùng làm MẪU SỐ của phân số hiện ra. Rộng
                ở đây là NÓI DỐI.

    Đo trên kho thật: NXP "đòi" cloud — chữ `cloud` chỉ nằm ở đoạn công ty tự
    giới thiệu. Bank of America: 3/4 chữ trong mẫu số là từ đoạn giới thiệu.
    Hậu quả: màn hình báo phủ 29% trong khi tờ giấy thật mang 63%, và nó
    khuyên Vin đừng nộp những tin tờ giấy đang trả lời tốt.
    """
    out: set[str] = set()
    for req in (explain or {}).get("requirements", []):
        out |= skills_in(req.get("text", ""))
    return out


def build(profile: dict, explain: dict | None, jd_text: str = "",
          num: dict | None = None, pick: dict | None = None) -> TailoredCV:
    from ..scoring.score import build_index, _matches

    blocks = parse(profile.get("cv_text") or "")
    wanted = wanted_skills(explain, jd_text)
    index = build_index(profile)
    header, summary = _identity(profile, blocks, wanted)

    # Câu nào TRẢ LỜI được thứ tin này hỏi — dùng CHUNG chỉ số với tầng chấm
    # điểm, nên hai bên không thể hiểu khác nhau về cùng một câu nữa.
    answers: dict[str, list[str]] = {}
    for signal in wanted:
        for ev in _matches(signal, index):
            if ev.kind:
                answers.setdefault(ev.text, []).append(signal)

    # ĐÃ THỬ VÀ BỎ (10/09): lọc bỏ mọi câu không trả lời gì. Đo được thì hỏng
    # hai lần. (1) Số câu trả lời được KHÔNG đo độ hợp — nó đo JD có tình cờ
    # gọi tên nhiều kỹ năng không; tin `unlikely` trung bình 10,1 câu còn tin
    # `likely` chỉ 6,9, và Millennium 84 điểm chỉ ra ĐÚNG MỘT câu. (2) Lọc
    # theo "có chứng minh kỹ năng nào không" thì cắt mất đúng những câu hay
    # nhất: "self-funded, across 17 instruments and five years of data",
    # "I never budgeted the time a proof would take". Quy mô, vết xước và
    # phán đoán không nằm trong vocab.SKILLS, mà đó mới là thứ thuyết phục.
    #
    # Nên TRẢ LỜI ĐƯỢC quyết định THỨ TỰ và quyết định khối nào bị cắt, chứ
    # không quyết định từng câu có được sống hay không.
    # KHỐI NÀO KHÔNG HỢP TIN NÀY THÌ KHÔNG LÊN. `cap` là TRẦN, không phải hạn
    # ngạch phải lấp cho đủ — đó là chỗ `Compress EA` (0 kỹ năng, hợp 0/117
    # tin) vẫn có mặt trên 115 bản CV, chỉ vì có đúng bốn project và ô cho ba.
    #
    # Lọc ở mức KHỐI, không ở mức CÂU: lọc câu theo từ khoá đã thử và bỏ, vì
    # nó cắt mất "self-funded, across 17 instruments" và "I never budgeted the
    # time a proof would take" — quy mô và vết xước không nằm trong từ vựng.
    sections: list[Section] = []
    # Câu bị LUẬT cấm, kèm lý do thật. Gom ở đây chứ không suy ra sau: suy ra
    # thì mọi câu vắng mặt đều nhận chung một lý do "yếu hơn thứ tin này hỏi",
    # và đó là lý do SAI cho câu bị cấm — nó không yếu, nó không thuộc CV.
    bi_cam: list[tuple[str, str]] = []
    for kind, cap in (("experience", rules.BUDGET["experience"]),
                      ("project", rules.BUDGET["project"])):
        chosen = [b for b in blocks if b.kind == kind and set(b.tags) & wanted]
        chosen.sort(key=lambda b: -len(set(b.tags) & wanted))
        # KINH NGHIỆM KHÔNG BAO GIỜ BỊ BỎ CẢ KHỐI — chỉ project mới được bỏ.
        #
        # Lọc khối theo "có trúng thứ tin này đòi không" là đúng với project
        # (project là tự chọn, bỏ một cái không để lại dấu vết). Với KINH
        # NGHIỆM thì nó đục một lỗ trên dòng thời gian: đo trên kho thật, 6/12
        # bản CV đầu bảng rơi mất hẳn khối "Research Consultant — WorldQuant,
        # Jan–Sep 2025", tức là bản gửi đi tự khai một khoảng trống 9 tháng.
        #
        # Khoảng trống đắt hơn nhiều so với một dòng kém liên quan: khảo sát
        # HBS/Accenture 2021 (8.000 lao động, 2.250 lãnh đạo tuyển dụng, có cả
        # UK) ghi nhận gần một nửa nhà tuyển dụng tự loại CV có khoảng trống
        # quá 6 tháng. Khối ít liên quan chỉ tốn ba dòng giấy.
        #
        # Vẫn XẾP theo độ liên quan: khối trúng nhiều đứng trước. Chỉ khác ở
        # chỗ khối không trúng gì thì xuống cuối, không biến mất.
        if kind == "experience" and (num or {}).get("moi_khoi_viec", True):
            con_lai = [b for b in blocks if b.kind == kind and b not in chosen]
            con_lai.sort(key=lambda b: -len(b.tags))
            chosen = chosen + con_lai
        if not chosen:
            # Không khối nào hợp — 9/117 tin rơi vào đây. CV rỗng thì không
            # gửi được, nên lấy khối mạnh nhất và để nguyên sự thật đó hiện ra.
            chosen = sorted((b for b in blocks if b.kind == kind),
                            key=lambda b: -len(b.tags))[:1]
        for block in chosen[:cap]:
            lines = _pick(block, wanted, answers,
                          int((num or {}).get("dong")
                              or rules.BUDGET["exp_bullets"]),
                          bo=bi_cam, num=num, chon=pick)
            if lines:
                sections.append(Section(kind, block.title, block.meta, lines))

    for block in blocks:
        if block.kind == "education":
            keep = [Line(l) for l in block.lines if _worth(l)]
            sections.append(Section("education", block.title, block.meta, keep))
    certs = [l for b in blocks if b.kind == "cert" for l in b.lines if _worth(l)]
    if certs:
        sections.append(Section("cert", "", "", [Line(l) for l in certs]))
    for block in blocks:
        bo = (not (num or {}).get("giu_muc")
              and rules.bo_muc_ky_nang(block.title, " ".join(block.lines)))
        if block.kind == "skill" and not bo:
            sections.append(Section("skill", block.title, "",
                                    [Line(" ".join(block.lines))]))

    have: set[str] = set()
    for block in blocks:
        have |= set(block.tags)
    have |= skills_in(profile.get("skills_strong", "") + " "
                      + profile.get("skills_weak", ""))

    # BỎ VÌ SAO — hai lý do khác hẳn nhau, và người dùng cần đọc ra được:
    #   bị CẤM   luật không cho lên CV (kể thất bại, ý kiến) -> sửa câu cũng vô ích
    #   YẾU HƠN  hợp lệ, nhưng tin này hỏi thứ khác          -> tin khác sẽ dùng
    shown = {l.text for s in sections for l in s.lines}
    goc_hien = {l.goc or l.text for s in sections for l in s.lines}
    cam_text = {t for t, _ in bi_cam}
    dropped = list(dict.fromkeys(bi_cam))
    dropped += [(rules.clean(t), "weaker than what this posting asks for")
                for b in blocks if b.kind in ("experience", "project")
                for t in sentences(b)
                if rules.clean(t) not in shown
                and rules.clean(t) not in goc_hien
                and rules.clean(t) not in cam_text and _worth(t)]

    # TỜ GIẤY NÓI ĐƯỢC GÌ — đọc từ chính thứ sắp in ra, gồm CẢ mục kỹ năng.
    # Bản cũ chỉ đếm kỹ năng chứng minh được bởi mấy câu được chọn, nên mục
    # TECHNICAL SKILLS đang in trên chính tờ giấy đó không được tính.
    tren_giay: set[str] = set()
    for sec in sections:
        # TIÊU ĐỀ MỤC CŨNG IN RA GIẤY. `render.paper` in nó dưới dạng
        # "<b>Git and GitHub</b> — every project version-controlled…", nên bỏ
        # tiêu đề khỏi phép đếm là tự báo thiếu: đo được `git` bị coi là rơi
        # ở 14/287 tin, trong khi chữ đó nằm ngay trên tờ giấy.
        tren_giay |= skills_in(sec.title)
        for line in sec.lines:
            tren_giay |= skills_in(line.text)
    doi = asked_skills(explain)
    return TailoredCV(header, summary, sections, dropped, sorted(wanted),
                      sorted({s for v in answers.values() for s in v} & wanted),
                      sorted(_real_missing(explain, wanted, have)),
                      asked=sorted(doi),
                      on_paper=sorted(doi & tren_giay))


def _real_missing(explain: dict | None, wanted: set[str], have: set[str]) -> set[str]:
    """Kỹ năng THẬT SỰ thiếu — bỏ qua danh sách 'hoặc'.

    JD viết "Programming in any of the following: C++, Java, MATLAB, R, Python"
    mà mình có C++ và Python thì Java/MATLAB/R KHÔNG phải là thiếu. Báo thiếu ở
    đây là báo động giả, và báo động giả thì lần sau không ai đọc nữa.
    """
    missing = wanted - have
    if not explain:
        return missing
    for req in explain.get("requirements", []):
        in_line = skills_in(req["text"])
        if in_line & have:                 # dòng này đã có ít nhất một cái đáp ứng
            missing -= in_line
    return missing


def _pick(block: Block, wanted: set[str], answers: dict, cap: int,
          bo: list | None = None, num: dict | None = None,
          chon: dict | None = None) -> list[Line]:
    """Câu trong một khối: trả lời được đứng trước, câu bị CẤM bỏ hẳn.

    HỎI `rules.sentence_ok` — trước đây KHÔNG hỏi, và đó là lỗ thật. Luật cấm
    câu kể thất bại và câu ý kiến lên CV, `cvhealth` báo đúng, nhưng bộ dựng
    này chưa bao giờ tra nên chúng vẫn đi ra ngoài. Đo trên hồ sơ thật ngày
    12/09: bản gửi Man Group mang 3 câu bị cấm, gồm cả "drawdown ran roughly
    30% deeper than the model predicted".

    Ba mảnh — luật, bộ chấm từng dòng, bộ dựng — nằm rời nhau thì luật chỉ là
    lời nói. Chỗ này là chỗ nối.
    """
    num = num or {}
    giong = str(num.get("giong", "cv"))
    kept: list[Line] = []
    for raw in sentences(block):
        goc = rules.clean(raw)
        if not _worth(goc):
            continue                      # "·", "Sep 2025" — rác bóc từ PDF
        tags = sorted(skills_in(goc))
        phan, ly_do = rules.sentence_ok(goc, tags, set((num or {}).get("giu") or ()))
        if phan == "drop":
            if bo is not None:
                bo.append((goc, ly_do))
            continue
        # SỬA bằng chính chữ của Vin — xem cv/rewrite.py. Sửa SAU khi phán để
        # luật vẫn đọc đúng câu Vin viết, không đọc bản máy vừa chỉnh.
        text, da_sua = rewrite.sua(goc, giong)
        hits = sorted(set(answers.get(raw, [])) | set(answers.get(goc, [])))
        kept.append(Line(
            text, rules.sentence_weight(text, wanted, tags), hits,
            review=ly_do if phan == "review" else "",
            goc=goc, sua=da_sua,
            yeu=rewrite.diem_yeu(text, tags, wanted),
            vet=rewrite.vet(text, tags, wanted, da_sua)))
    # NGƯỜI CHỌN THẮNG MÁY. Vin ghim một câu thì nó lên, dù trọng số thấp;
    # Vin gạt một câu thì nó xuống, dù trọng số cao. Máy xếp bằng luật chung,
    # còn Vin biết thứ luật chung không biết — tin này nghiêng về đâu, vừa
    # nói chuyện với ai.
    #
    # Ghim KHÔNG phá trần `cap`: một tờ giấy vẫn là một tờ giấy. Ghim quá số
    # ô thì câu ghim chiếm hết ô, và đó là ý Vin.
    ghim = set((chon or {}).get("pin") or ())
    gat = set((chon or {}).get("drop") or ())
    kept = [l for l in kept if (l.goc or l.text) not in gat]
    kept.sort(key=lambda l: ((l.goc or l.text) not in ghim,
                             -len(l.hits), -l.weight))
    return kept[:cap]


def _worth(text: str) -> bool:
    """Rác bóc từ PDF: dấu chấm trơ trọi, mẩu ngày tháng cụt. Trước đây chúng
    lên CV vì `BUDGET` có ô trống phải lấp — "·" và "Sep 2025" đi ra ngoài
    trong cả 117 bản."""
    body = text.strip().strip("·-–—• ")
    return len(body) >= 12 and any(c.isalpha() for c in body)


def _identity(profile: dict, blocks: list[Block],
              wanted: set[str]) -> tuple[list[str], str]:
    header = [profile.get("full_name") or "",
              " · ".join(x for x in [profile.get("location"), profile.get("phone"),
                                     profile.get("email")] if x)]
    links = (profile.get("links") or "").splitlines()
    if links:
        header.append(" · ".join(l.strip() for l in links if l.strip()))
    visa = next((" ".join(b.lines) for b in blocks
                 if b.kind == "header" and "visa" in " ".join(b.lines).lower()), "")
    if visa:
        header.append(visa)

    facts = []
    education = (profile.get("education") or "").splitlines()
    if education:
        facts.append(education[0].split("—")[0].strip())
    certs = (profile.get("certifications") or "").splitlines()
    if certs:
        facts.append(certs[0].split("—")[0].strip() if "—" in certs[0] else certs[0])
    strong = [s.strip() for s in (profile.get("skills_strong") or "").split(",") if s.strip()]
    want_norm = {norm(w) for w in wanted}
    hit = [s for s in strong if norm(s) in want_norm]
    rest = [s for s in strong if norm(s) not in want_norm]
    lead = (hit + rest)[:6]
    if lead:
        facts.append(" · ".join(lead))
    return header, " · ".join(f for f in facts if f)


# --- NGƯỜI CHỌN LẠI: ghim / gạt, và băng ghế dự bị --------------------

def picks(conn, posting_id: int) -> dict:
    """Lựa chọn của Vin cho MỘT tin: {'pin': [...], 'drop': [...]}."""
    ra: dict = {"pin": [], "drop": []}
    for row in conn.execute(
            "SELECT text, mode FROM cv_pick WHERE posting_id = ?", (posting_id,)):
        ra.setdefault(row["mode"], []).append(row["text"])
    return ra


def set_pick(conn, posting_id: int, text: str, mode: str) -> None:
    """Ghim / gạt một câu. `mode=''` là bỏ lựa chọn, về lại cách máy xếp."""
    if not mode:
        conn.execute("DELETE FROM cv_pick WHERE posting_id = ? AND text = ?",
                     (posting_id, text))
    else:
        from ..core.postings import now
        conn.execute(
            "INSERT INTO cv_pick (posting_id, text, mode, made_at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT(posting_id, text)"
            " DO UPDATE SET mode = excluded.mode, made_at = excluded.made_at",
            (posting_id, text, mode, now()))
    conn.commit()


def bench(profile: dict, cv: TailoredCV, block_title: str = "") -> list[dict]:
    """Câu DỰ BỊ — câu hợp luật trong hồ sơ mà bản này không chọn.

    Đây là thứ làm "chọn lại" thành chọn THẬT chứ không phải lời hứa: máy
    không viết câu mới, nó đưa ra mấy câu Vin ĐÃ VIẾT mà lần này không được
    gọi, xếp theo mức trúng thứ TIN NÀY đòi.

    Đo trên hồ sơ thật: 10 câu dự bị cho một tin — đủ để đổi có nghĩa.
    """
    in_ra = {l.goc or l.text for s in cv.sections for l in s.lines}
    # Dùng tập RỘNG: đây là gợi ý "đổi sang câu này thì trúng thêm gì", chứ
    # không phải con số chấm điểm. Hẹp quá thì mọi câu dự bị đều hiện "không
    # trúng thêm gì" và người dùng không có căn cứ nào để chọn.
    doi = set(cv.wanted)
    ra = []
    for block in parse(str(profile.get("cv_text") or "")):
        if block.kind not in ("experience", "project"):
            continue
        if block_title and block.title != block_title:
            continue
        for raw in sentences(block):
            text = rules.clean(raw)
            if text in in_ra or not _worth(text):
                continue
            phan, _ = rules.sentence_ok(text, sorted(skills_in(text)))
            if phan == "drop":
                continue
            trung = sorted(skills_in(text) & doi)
            ra.append({"text": text, "khoi": block.title, "trung": trung,
                       "diem": rules.sentence_weight(text, doi,
                                                     sorted(skills_in(text)))})
    # Câu trúng thứ tin này đòi đứng trước — đó là lý do để đổi sang nó.
    ra.sort(key=lambda x: (-len(x["trung"]), -x["diem"]))
    return ra
