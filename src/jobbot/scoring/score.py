"""Chấm điểm khớp CV <-> JD, và LUÔN giải thích được vì sao ra điểm đó.

Luật: điểm không giải thích được thì không dùng để quyết định nộp đơn.
Vì vậy mọi hàm ở đây trả về kèm BẰNG CHỨNG — câu chữ lấy thẳng từ hồ sơ.

Thang 100 điểm:
    55  yêu cầu BẮT BUỘC đáp ứng được bao nhiêu
    15  yêu cầu ĐIỂM CỘNG
    20  đúng cấp bậc (nhắm graduate mà tin đòi senior thì trừ nặng)
    10  chức danh trùng khớp

Yêu cầu không phán được (không có từ khoá nào nhận ra) KHÔNG tính vào mẫu số —
tính vào đó là tự bịa ra sự chắc chắn mình không có. Nó chỉ hạ độ tin cậy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..ingest.base import norm
from . import extract
from .vocab import (DEGREE_WORDS, QUANT_FIELD, SKILLS, YEARS,
                    alias_hits)

YEARS_BAND = {"0-1": 0.5, "1-3": 2, "3-5": 4, "5-8": 6.5, "8+": 10}
# ---------------------------------------------------------------- cấp bậc
#
# MỘT TRỤC SỐ, không phải một cái cờ "có phải junior không".
#
# Bản cũ chỉ biết đúng một câu hỏi: người dùng có nhắm junior không. Vin nhắm
# grad+junior nên nó chạy đúng CHO VIN, và sai hẳn cho mọi người khác: ai
# chọn "senior" thì `junior` là False, và hàm trả 0.6 "level not stated in
# the title" cho MỌI tin — kể cả tin ghi to "Graduate Intern" ngay đầu đề.
# Cấp bậc chiếm 20 trên 100 điểm, nên cả bảng xếp hạng lệch mà không có gì
# kêu lên. Đó là lối mòn "chạy được cho trường hợp của mình", không phải
# phương án.
#
# Số là KHOẢNG CÁCH, không phải thứ hạng: grad và senior cách nhau 3 bậc, nên
# "hợp hay không" đo bằng cách trừ, và cùng một phép trừ chạy cho mọi người —
# người nhắm senior gặp tin thực tập cũng lệch 3 bậc y như chiều ngược lại.
BAC = {"intern": 0, "grad": 0, "grad_scheme": 0, "junior": 1,
       "mid": 2, "senior": 3, "lead": 4}
TEN_BAC = {0: "entry/graduate", 1: "junior", 2: "mid", 3: "senior",
           4: "lead/principal"}

# Đọc cấp bậc TỪ ĐẦU ĐỀ. Xếp từ cao xuống thấp: đầu đề khớp nhiều mức thì
# giữ mức THẤP NHẤT khớp được (xem `_bac_tieu_de`).
#
# "programme" TRẦN KHÔNG tính là tin sinh viên mới ra trường, và đây là lỗi
# đo được: 34 tin trong DB khớp "program|programme" mà không phải tin grad —
# "Senior Technical Program Manager", "GRC Program Manager", "Swag Program
# Manager". Luật cũ cho chúng 1.0 "explicitly graduate/junior" VÀ xoá luôn
# hình phạt cấp cao, tức tin senior nhảy từ 0 lên 20 điểm. Nên chữ đó chỉ
# tính khi đi kèm thứ làm nó thành chương trình tuyển mới: graduate, summer,
# analyst, internship, rotational, pathway, campus, early careers.
BAC_TIEU_DE = (
    (4, re.compile(r"\b(lead|principal|staff|head of|director|vp|chief|"
                   r"vice president)\b", re.I)),
    (3, re.compile(r"\b(senior|snr|sr)\b", re.I)),
    (2, re.compile(r"\b(mid[- ]?level|midweight|intermediate)\b", re.I)),
    (1, re.compile(r"\b(junior|jr)\b", re.I)),
    (0, re.compile(r"\b(graduate|grad|intern|internship|placement|entry|"
                   r"trainee|campus|academy|apprentice|scheme|rotational|"
                   r"early careers?)\b"
                   r"|\b(graduate|summer|analyst|internship|rotational|"
                   r"pathway|campus|early careers?)\s+programme?\b", re.I)),
)

# Giữ tên cũ: realism.py và vài chỗ khác vẫn hỏi "tin này có phải cấp cao không".
SENIOR_TITLE = BAC_TIEU_DE[1][1]
JUNIOR_TITLE = BAC_TIEU_DE[4][1]
JUNIOR_LEVELS = {"intern", "grad", "grad_scheme", "junior"}


@dataclass
class Evidence:
    where: str
    text: str
    normal: str
    strong: bool
    kind: str = ""        # experience | project | "" (trường hồ sơ)
    meta: str = ""        # ngày tháng / tổ chức, để dựng CV


@dataclass
class Judged:
    text: str
    must: bool
    met: bool | None          # None = không phán được
    evidence: str = ""
    signals: list[str] = field(default_factory=list)
    weak_only: bool = False   # chỉ dựa vào từ khoá/mong muốn, không phải bằng chứng


def build_index(answers: dict) -> list[Evidence]:
    """Gom hồ sơ thành bằng chứng tra cứu được — ở mức CÂU, không mức TRƯỜNG.

    Trước đây cả `cv_text` là MỘT mẩu. Khớp được thì bằng chứng trả về là 80
    ký tự đầu của toàn bộ CV — tầng chấm điểm *biết* hồ sơ có gì, nhưng không
    biết CÂU NÀO chứng minh. Nên tầng dựng CV phải tự đi chọn lại từ đầu bằng
    một bộ trọng số riêng, và hai bên lệch nhau: đo ngày 10/09, một tin 92
    điểm nhận bản CV mà 76% số câu không chạm gì tới nó.

    Ở mức câu thì một chỉ số phục vụ được cả ba việc:

        chấm điểm  bao nhiêu câu hỏi của họ mình trả được
        dựng CV    chính những câu đó, theo thứ tự họ hỏi
        lưới       câu hỏi nào KHÔNG có câu nào trả lời
    """
    from ..cv.blocks import parse as parse_cv, sentences as split_cv

    out: list[Evidence] = []

    # Từng câu trong CV, mang theo khối chứa nó — để dựng CV còn biết xếp nó
    # dưới đầu mục nào.
    for block in parse_cv(str(answers.get("cv_text") or "")):
        if block.kind not in ("experience", "project"):
            continue
        for line in split_cv(block):
            text = line.strip()
            if len(text) < 25:            # mẩu vụn do bóc PDF, không phải câu
                continue
            out.append(Evidence(block.title or block.kind, text, norm(text), True,
                                kind=block.kind, meta=block.meta))

    # Các trường còn lại vẫn ở mức trường: chúng vốn là danh sách, không phải văn.
    fields = [
        ("your strong skills", "skills_strong", True),
        ("your education", "education", True),
        ("your certifications", "certifications", True),
        ("skills you're still learning", "skills_weak", False),
    ]
    # BỎ `search_keywords` VÀ `stack_want` KHỎI BẰNG CHỨNG.
    #
    # Nhãn của chính chúng đã tự khai "(not proof)" — rồi vẫn được nạp vào chỉ
    # số bằng chứng, nên một dòng yêu cầu vẫn tính là ĐẠT nhờ chữ Vin gõ vào ô
    # TÌM VIỆC. Đo trên kho thật: 249 dòng yêu cầu ở 153/472 tin đạt kiểu đó.
    #
    # "Tôi muốn tìm việc có Kafka" không phải bằng chứng tôi biết Kafka. Để
    # chúng trong chỉ số thì mọi con số phủ đều thổi lên, và bảng "hồ sơ còn
    # hụt gì" — thứ nói cho Vin biết phải VIẾT gì — chỉ ra chỗ hụt giả.
    #
    # Điểm sẽ TỤT sau khi sửa. Đó là điểm thật.
    for label, key, strong in fields:
        value = answers.get(key)
        if not value:
            continue
        text = " ".join(value) if isinstance(value, list) else str(value)
        out.append(Evidence(label, text.strip(), norm(text), strong))
    return out


def _signals(text: str) -> list[str]:
    """Những kỹ năng/khái niệm mà dòng yêu cầu này thực sự đang đòi.

    Luật khớp ở vocab.alias_hits — dùng chung với cv.build.skills_in, để
    tầng chấm điểm và tầng dựng CV không bao giờ hiểu khác nhau về cùng
    một chữ.
    """
    return alias_hits(norm(text))


def _find(signal: str, index: list[Evidence]) -> tuple[bool, str, bool]:
    """Hồ sơ có bằng chứng cho tín hiệu này không, ở đâu, và có MẠNH không."""
    hit = _match(signal, index)
    if hit is None:
        return False, "", False
    return True, f"{hit.where} — {hit.text}", hit.strong


def _match(signal: str, index: list[Evidence]) -> Evidence | None:
    """Mẩu bằng chứng ĐẦU TIÊN trả lời được tín hiệu này."""
    for ev in _matches(signal, index):
        return ev
    return None


def _matches(signal: str, index: list[Evidence]):
    """MỌI mẩu trả lời được tín hiệu này. Tầng dựng CV cần cả danh sách."""
    forms = SKILLS.get(signal, {signal}) | {signal}
    for ev in index:
        for form in forms:
            needle = f" {form.strip()} " if len(form.strip()) <= 3 else form.strip()
            if needle in f" {ev.normal} ":
                yield ev
                break


def _years_needed(text: str) -> int | None:
    found = YEARS.search(text)
    return int(found.group(1)) if found else None


# Chấm dứt giữa các CHỮ CÁI ĐƠN, dán lại trước khi norm(). norm() thay dấu
# chấm bằng khoảng trắng, nên "B.S., M.S. or PhD" thành "b s m s or phd" —
# mất sạch bachelors và masters, chỉ còn phd. Hậu quả: JD viết "B.S., M.S.
# HOẶC PhD" bị đọc thành "bắt buộc PhD", tin đó thành blocker và bị chặn trần
# 55 điểm, dù Vin có MSc và thừa điều kiện. "B.Sc." còn tệ hơn: không nhận ra
# bằng nào cả.
# Bỏ dấu chấm nằm GIỮA hai chữ cái, trước khi norm(). norm() thay dấu chấm
# bằng khoảng trắng, nên "B.S., M.S. or PhD" thành "b s m s or phd" — mất sạch
# bachelors và masters, chỉ còn phd. Hậu quả: JD viết "B.S., M.S. HOẶC PhD"
# bị đọc thành "bắt buộc PhD", tin đó thành blocker và bị chặn trần 55 điểm,
# dù Vin có MSc và thừa điều kiện.
#
# Chỉ bỏ dấu chấm CÓ CHỮ CÁI HAI BÊN, nên dấu chấm hết câu không bị đụng:
#   B.S. -> BS.    M.Sc. -> MSc.    Ph.D. -> PhD.    "...field. The" giữ nguyên
_DOTTED = re.compile(r"(?<=[A-Za-z])\.(?=[A-Za-z])")


def _undot(text: str) -> str:
    return _DOTTED.sub("", text or "")


def _degrees_needed(text: str) -> list[str]:
    """MỌI bằng cấp được nhắc tới, không phải cái cao nhất.

    LỖI ĐÃ SỬA (1): trước đây lấy bằng cao nhất rồi đòi đúng cái đó, nên dòng
    "Undergraduate, MS, or PhD candidates" bị chấm trượt dù có MSc — JD viết
    "hoặc", mình đọc thành "phải là PhD".

    LỖI ĐÃ SỬA (2): dạng viết tắt có dấu chấm. Xem _undot.
    """
    low = f" {norm(_undot(text))} "
    return [level for level in ("phd", "masters", "bachelors")
            if any(f" {word.strip()} " in low for word in DEGREE_WORDS[level])]


def judge_one(req: extract.Requirement, index: list[Evidence], answers: dict) -> Judged:
    text = req.text

    # --- yêu cầu số năm ---
    needed = _years_needed(text)
    if needed is not None:
        have = YEARS_BAND.get(str(answers.get("years_real") or ""), 0)
        met = have >= needed
        return Judged(text, req.must, met,
                      f"you have about {have:g} years, they ask for {needed}+",
                      [f"{needed}+ years"])

    # --- yêu cầu bằng cấp ---
    levels = _degrees_needed(text)
    if levels:
        education = norm(str(answers.get("education") or ""))
        padded = f" {education} "
        has = {"phd": any(f" {w} " in padded for w in ("phd", "doctorate")),
               "masters": any(f" {w} " in padded for w in ("msc", "master", "masters", "mba")),
               "bachelors": any(f" {w} " in padded for w in
                                ("bsc", "ba", "bachelor", "bachelors", "msc", "master", "phd"))}
        quant = any(f in education for f in QUANT_FIELD)
        met = any(has[level] for level in levels)      # JD viết "hoặc" thì là hoặc
        note = "quantitative field" if quant else "field not obviously quantitative"
        # "".splitlines() là [] chứ không phải [""] — lấy [0] là IndexError, và
        # nó nổ giữa giao dịch của derive() nên CẢ lần quét bị cuộn lại. Dòng
        # ngay dưới đã lường trước ô trống, chỉ là không bao giờ chạy tới.
        lines = str(answers.get("education") or "").splitlines()
        raw = lines[0][:80] if lines else ""
        return Judged(text, req.must, met,
                      f"{raw} — {note}" if raw else "nothing on your profile about education",
                      levels)

    # --- yêu cầu kỹ năng ---
    signals = _signals(text)
    if not signals:
        return Judged(text, req.must, None, "no recognisable skill in this line", [])

    hits = [(s, *_find(s, index)) for s in signals]
    strong = [(s, e) for s, ok, e, is_strong in hits if ok and is_strong]
    weak = [(s, e) for s, ok, e, is_strong in hits if ok and not is_strong]
    if strong:
        return Judged(text, req.must, True, strong[0][1], signals)
    if weak:
        # Chỉ có bằng chứng yếu -> tính là ĐẠT NHƯNG đánh dấu, vì nó dựa trên
        # thứ Vin khai muốn làm chứ không phải thứ chứng minh được.
        return Judged(text, req.must, True, weak[0][1], signals, weak_only=True)
    return Judged(text, req.must, False,
                  f"nothing on your profile mentions: {', '.join(signals[:4])}", signals)


def _bac_tieu_de(title: str) -> int | None:
    """Cấp bậc đọc được từ đầu đề, hoặc None nếu đầu đề không nói.

    Khớp nhiều mức thì lấy mức THẤP NHẤT. "Graduate Programme — Senior
    Analyst track" là tin tuyển sinh viên mới ra trường, không phải tin
    senior; và đoán nhầm theo chiều đó thì người nhắm entry mất tin họ cần,
    còn đoán nhầm chiều kia chỉ làm người nhắm senior thấy thêm một tin lạc.
    Mất tin tệ hơn thấy thừa một tin.
    """
    thay = [bac for bac, mau in BAC_TIEU_DE if mau.search(title or "")]
    return min(thay) if thay else None


def _level_fit(title: str, answers: dict) -> tuple[float, str]:
    """Điểm hợp cấp bậc, 0..1 — và một câu nói THẬT vì sao.

    Ba trường hợp, không trường hợp nào được im: đầu đề không nói cấp bậc,
    hồ sơ không nói nhắm cấp nào, và cả hai đều nói (lúc đó mới trừ được).
    """
    muon = sorted({BAC[w] for w in (answers.get("seniority") or []) if w in BAC})
    tin = _bac_tieu_de(title)

    if tin is None:
        return 0.6, "level not stated in the title"
    if not muon:
        # Hồ sơ bỏ trống, hoặc chỉ điền chữ tự do mà thang này chưa biết.
        # Nói đúng như vậy — 0.6 kèm câu "không rõ đầu đề" là câu SAI.
        return 0.6, (f"posting is {TEN_BAC[tin]} level, but you haven't said "
                     "which levels you'd accept")

    lech = min(abs(tin - m) for m in muon)
    cua_ban = ", ".join(TEN_BAC[m] for m in muon)
    if lech == 0:
        return 1.0, f"posting is {TEN_BAC[tin]} level — matches your target"
    if lech == 1:
        return 0.5, (f"posting is {TEN_BAC[tin]} level, you target "
                     f"{cua_ban} — one step off")
    return 0.0, f"posting is {TEN_BAC[tin]} level, you target {cua_ban}"


def _title_fit(title: str, answers: dict) -> tuple[float, str]:
    targets = [norm(t) for t in str(answers.get("job_titles") or "").splitlines() if t.strip()]
    low = norm(title)
    hit = next((t for t in targets if t and t in low), None)
    if hit:
        return 1.0, f"title contains your target '{hit}'"
    words = set(low.split())
    best, name = 0.0, ""
    for t in targets:
        tw = set(t.split())
        if tw:
            overlap = len(words & tw) / len(tw)
            if overlap > best:
                best, name = overlap, t
    return best, (f"partly matches '{name}'" if best else "no overlap with your target titles")


def score_job(title: str, description: str, answers: dict) -> dict:
    reqs = extract.requirements(description)
    # Nửa còn lại của JD: việc tin này bảo mình SẼ LÀM. Không dùng để chấm
    # điểm — chấm điểm ứng viên bằng mô tả công việc là sai. Cất lại vì đó là
    # thứ mô tả sẵn một project trông thế nào (xem projects/frame.py).
    todo = extract.duties(description)
    confidence = extract.confidence(reqs)
    if confidence == "none":
        return {"score": None, "confidence": "none", "requirements": [],
                "duties": todo,
                "reason": "Could not read any requirements from this posting — read it yourself.",
                "breakdown": {}}

    index = build_index(answers)
    judged = [judge_one(r, index, answers) for r in reqs]

    must = [j for j in judged if j.must and j.met is not None]
    nice = [j for j in judged if not j.must and j.met is not None]
    unknown = [j for j in judged if j.met is None]

    must_ratio = (sum(1 for j in must if j.met) / len(must)) if must else 0.5
    nice_ratio = (sum(1 for j in nice if j.met) / len(nice)) if nice else 0.5
    level_ratio, level_why = _level_fit(title, answers)
    title_ratio, title_why = _title_fit(title, answers)

    points = (55 * must_ratio + 15 * nice_ratio + 20 * level_ratio + 10 * title_ratio)

    # chặn trần chỉ khi PhD là bằng DUY NHẤT được chấp nhận
    blockers = [j.text for j in must if j.met is False
                and (_years_needed(j.text) or _degrees_needed(j.text) == ["phd"])]
    capped = False
    if blockers:
        # Đòi PhD, hoặc số năm mình không có -> dù mọi thứ khác khớp cũng khó qua vòng lọc
        if points > 55:
            capped = True
        points = min(points, 55)

    return {
        "score": int(round(points)),
        "confidence": confidence,
        "requirements": [
            {"text": j.text, "met": j.met, "must": j.must, "evidence": j.evidence}
            for j in judged],
        "duties": todo,
        "blockers": blockers,
        "capped": capped,
        "weak_evidence": sum(1 for j in judged if j.weak_only),
        "unknown": len(unknown),
        "breakdown": {
            "must": {"met": sum(1 for j in must if j.met), "total": len(must),
                     "points": round(55 * must_ratio, 1)},
            "nice": {"met": sum(1 for j in nice if j.met), "total": len(nice),
                     "points": round(15 * nice_ratio, 1)},
            "level": {"points": round(20 * level_ratio, 1), "why": level_why},
            "title": {"points": round(10 * title_ratio, 1), "why": title_why},
        },
    }
