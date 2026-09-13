"""Tách CV thành các KHỐI rời để chọn và sắp lại theo từng JD.

Luật xuyên suốt thư mục này: **chỉ CHỌN và SẮP XẾP sự thật đã có.
Không thêm một chữ nào không có trong hồ sơ.**

Vì sao phải tách khối: không tách thì chỉ có một cục văn bản, mà một cục thì
hoặc lấy hết hoặc bỏ hết. Tách rồi mới trả lời được câu "JD này cần dòng nào".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..ingest.base import norm
from ..scoring.vocab import ALIASES

SECTION = re.compile(
    r"^(EXPERIENCE|SELECTED PROJECTS|PROJECTS|EDUCATION|TECHNICAL SKILLS|SKILLS|"
    r"CERTIFICATIONS?|PUBLICATIONS?|AWARDS?)\s*$")

# Ngày tháng bị dính vào cuối dòng chức danh khi trích từ PDF
DATE_TAIL = re.compile(
    r"\s+((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}"
    r"(?:\s*[–—-]\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*)?"
    r"(?:\d{4}|Present|present|Now))?"
    r"|\d{4}\s*[–—-]\s*(?:\d{4}|Present))\s*$")

CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.\w+|\+\d[\d ]{6,}|github\.io|linkedin|github", re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Block:
    kind: str                 # header|summary|experience|project|education|cert|skill
    title: str = ""
    meta: str = ""            # ngày tháng, tổ chức
    lines: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)   # kỹ năng nhận ra trong khối

    def text(self) -> str:
        return " ".join([self.title, self.meta, *self.lines])


def _tags(text: str) -> list[str]:
    low = f" {norm(text)} "
    found = []
    for alias, canonical in ALIASES.items():
        needle = f" {alias.strip()} " if len(alias.strip()) <= 3 else alias.strip()
        if needle in low and canonical not in found:
            found.append(canonical)
    return found


def _label(line: str) -> tuple[str, str]:
    """'Nhãn — nội dung' -> ('Nhãn', 'nội dung'). Không có gạch thì nhãn rỗng."""
    for dash in (" — ", " – "):
        head, sep, rest = line.partition(dash)
        if sep and rest.strip():
            return head.strip(), rest.strip()
    return "", line.strip()


def _split_role(line: str) -> tuple[str, str]:
    """'Research Consultant — WorldQuant Jan 2025 – Sep 2025' -> (chức danh, ngày)."""
    found = DATE_TAIL.search(line)
    if found:
        return line[:found.start()].strip(), found.group(1).strip()
    return line.strip(), ""


def _looks_like_role(line: str) -> bool:
    """Dòng chức danh, KHÔNG phải câu văn có gạch ngang.

    LỖI ĐÃ SỬA: chỉ cần thấy " — " là coi là chức danh, nên câu
    "...peak profit in the most recent window — which rewards luck" bị cắt
    thành một vai trò mới, xé đôi khối kinh nghiệm.
    """
    if DATE_TAIL.search(line):
        return True
    if len(line) > 90 or line.rstrip().endswith((".", ",", ";", ":")):
        return False
    if not (" — " in line or " – " in line):
        return False
    # dòng chức danh không mở đầu bằng chữ thường hay liên từ
    first = line.split()[0] if line.split() else ""
    return first[:1].isupper() and first.lower() not in {
        "the", "a", "an", "and", "but", "so", "then", "every", "one", "no", "it"}


def parse(cv_text: str) -> list[Block]:
    lines = [l.rstrip() for l in (cv_text or "").splitlines()]
    blocks: list[Block] = []
    section = "head"
    current: Block | None = None

    def flush():
        nonlocal current
        if current and (current.lines or current.title):
            current.tags = _tags(current.text())
            blocks.append(current)
        current = None

    truoc_do = None          # dòng chữ ngay trước — xem luật mở khối project
    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        found = SECTION.match(line)
        if found:
            flush()
            name = found.group(1).lower()
            section = ("experience" if name == "experience"
                       else "project" if "project" in name
                       else "education" if name == "education"
                       else "cert" if name.startswith("certification")
                       else "skill")
            continue

        # --- phần đầu: tên, liên hệ, tóm tắt ---
        if section == "head":
            if not blocks and not current:
                blocks.append(Block("header", line))          # tên
                continue
            if CONTACT.search(line) or "visa" in line.lower():
                blocks.append(Block("header", "", "", [line]))
                continue
            if current is None:
                current = Block("summary")
            current.lines.append(line)
            continue

        _truoc = truoc_do
        truoc_do = line
        # --- kinh nghiệm / project: dòng chức danh mở khối mới ---
        if section in ("experience", "project"):
            if section == "project":
                # TÊN PROJECT MỞ KHỐI MỚI — nhận bằng HÌNH DẠNG DÒNG, không
                # bắt buộc phải có dấu gạch ngang.
                #
                # Luật cũ đòi dòng phải chứa " — ". Thử năm kiểu viết thường
                # gặp: bốn kiểu hỏng, KỂ CẢ kiểu tên trần một dòng, và hai
                # project liền nhau dính thành một khối. Đó là luật viết cho
                # đúng một cách trình bày.
                #
                # Tên project: NGẮN, hoa đầu, và KHÔNG kết thúc như một câu.
                # Thêm một vế nữa để khỏi bắt nhầm dòng nội dung không có dấu
                # chấm: nó phải đứng ngay sau tiêu đề mục, hoặc sau một dòng
                # đã kết thúc bằng dấu câu.
                head = re.split(r"\s+[—–]\s+", line, maxsplit=1)[0]
                co_gach = head != line
                sau_cau = (_truoc is None
                           or _truoc.endswith((".", "!", "?")))
                # CÓ DẤU GẠCH thì chính nó đã đánh dấu ranh giới tiêu đề —
                # 'Quant Trading Studio — the whole pipeline you can run.' là
                # tên project cộng mô tả, và mô tả kết thúc bằng dấu chấm là
                # chuyện thường. Xét dấu chấm trên phần ĐẦU, không trên cả dòng.
                #
                # KHÔNG CÓ GẠCH thì phải chặt hơn, vì lúc đó tiêu đề và một
                # dòng nội dung trông giống hệt nhau: đòi cả dòng không kết
                # thúc như một câu, và nó phải đứng sau chỗ câu trước đã hết.
                sach = not head.endswith((".", ",", ";", ":"))
                starts_new = (len(head) <= 70 and head[:1].isupper() and sach
                              and (co_gach
                                   or (not line.endswith((".", ",", ";", ":"))
                                       and sau_cau)))
            else:
                starts_new = _looks_like_role(line) and (
                    current is None or len(current.lines) > 0)
            if starts_new:
                flush()
                title, meta = _split_role(line)
                # 'Tên project — mô tả' : phần mô tả là nội dung, không phải chức danh
                if section == "project" and " — " in title:
                    name, rest = title.split(" — ", 1)
                    current = Block("project", name.strip(), meta, [rest.strip()])
                else:
                    current = Block(section, title, meta)
                continue
            if current is None:
                current = Block(section)
            current.lines.append(line)
            continue

        # --- học vấn / chứng chỉ / kỹ năng: mỗi dòng một khối ---
        if line.lower().startswith("certification"):
            flush()
            # 'Certifications — CFA Level I, …'
            #
            # Chữ "Certifications" đã LÀ tên mục: render.py đặt tiêu đề theo
            # kind ("cert" -> "Certifications"). Để nguyên trong thân thì bản
            # in ra hai dòng chồng nhau:
            #     Certifications
            #     Certifications — CFA Level I, October 2024, …
            # Tách nhãn ra làm tiêu đề khối, đúng cách khối kỹ năng đang làm
            # với 'Programming — Python…'. Tiêu đề cũng là thứ write_block cần
            # để ghi ngược lại đúng hình dạng cũ.
            label, rest = _label(line)
            blocks.append(Block("cert", label, "", [rest]))
            continue
        # kỹ năng: mỗi nhóm ('Programming — ...') là một khối riêng
        if section == "skill":
            label = re.match(r"^([A-Z][A-Za-z /]{2,28})\s+[—–-]\s+(.+)$", line)
            if label:
                flush()
                current = Block("skill", label.group(1).strip(), "", [label.group(2).strip()])
            else:
                if current is None:
                    current = Block("skill")
                current.lines.append(line)
            continue

        if section in ("education", "cert"):
            if section == "education" and _looks_like_role(line):
                flush()
                title, meta = _split_role(line)
                current = Block("education", title, meta)
            else:
                if current is None:
                    current = Block(section)
                current.lines.append(line)
            continue

    flush()
    for block in blocks:
        if not block.tags:
            block.tags = _tags(block.text())
    return blocks


def sentences(block: Block) -> list[str]:
    """Bẻ văn xuôi trong khối thành từng câu — đơn vị nhỏ nhất để chọn.

    Không viết lại câu nào. Câu nào lên CV cũng là câu Vin đã viết.
    """
    # PDF ngắt dòng giữa câu ("...institutions combine\nthousands of simple alphas"),
    # nên phải nối hết lại rồi mới bẻ theo dấu câu.
    joined = re.sub(r"\s+", " ", " ".join(block.lines)).strip()
    return [part.strip() for part in SENTENCE.split(joined) if len(part.strip()) > 25]


# ---------------------------------------------------------------- ghi ngược

SECTION_FOR = {"experience": "EXPERIENCE", "project": "SELECTED PROJECTS"}


def _bounds(lines: list[str], title: str) -> tuple[int, int] | None:
    """Khối mang tiêu đề này nằm từ dòng nào tới dòng nào.

    Định vị bằng DÒNG TIÊU ĐỀ chứ không dựng lại cả tệp từ blocks: parse() bỏ
    dòng trống và cắt khoảng trắng cuối, nên dựng lại là mất định dạng của
    những khối mình không hề đụng tới.
    """
    # Khớp theo TIỀN TỐ. Không dùng bằng-nhau: khối kinh nghiệm có đuôi ngày
    # tháng ('… Startup Jan 2026 – Present') mà title đã cắt bỏ, và khối
    # project có phần mô tả nối sau ' — '. Không khớp được thì write_block rơi
    # vào nhánh thêm mới và đẻ ra một khối trùng tên.
    head = title.strip()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith(head)), None)
    if start is None:
        return None
    stop = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        if SECTION.match(line):                       # sang mục khác
            stop = i
            break
        # Dòng tiêu đề của khối kế tiếp: có " — " và đủ ngắn.
        head_part = re.split(r"\s+[—–]\s+", line, maxsplit=1)[0]
        if (re.search(r"\s+[—–]\s+", line) and len(head_part) < 60
                and head_part[:1].isupper()):
            stop = i
            break
    return start, stop


def write_block(cv_text: str, kind: str, title: str, meta: str,
                body: list[str]) -> str:
    """Thay khối `title`, hoặc thêm mới nếu chưa có. Trả về cv_text mới.

    Chỉ đụng đúng khối đó. Không có khối nào bị dựng lại, nên không khối nào
    bị đổi định dạng ngoài ý muốn.
    """
    lines = (cv_text or "").splitlines()
    body = [b.strip() for b in body if b.strip()]

    # Thân rỗng = XOÁ khối. Giữ lại một khối không hợp tin nào chỉ làm bẩn CV
    # gốc; đo được: `Compress EA` hợp 0/117 tin mà vẫn nằm đó.
    if not body:
        found = _bounds(lines, title)
        if not found:
            return cv_text
        start, stop = found
        return "\n".join(lines[:start] + lines[stop:]).rstrip() + "\n"

    # Mỗi loại khối có HÌNH DẠNG riêng, và parse() nhận ra khối mới bằng chính
    # hình dạng đó. Viết sai hình dạng thì khối vừa ghi bị nuốt vào khối trước
    # và biến mất — đã xảy ra khi ghi "Compress EA" trơ trọi, vì khối project
    # bắt buộc phải có " — " trên dòng tiêu đề.
    # Mỗi loại khối có HÌNH DẠNG riêng, và parse() nhận ra khối mới bằng chính
    # hình dạng đó. Viết sai hình dạng thì khối vừa ghi bị nuốt vào khối trước
    # và biến mất — đã xảy ra hai lần: khối project ghi trơ trọi "Compress EA"
    # (thiếu " — "), và khối kinh nghiệm ghi thiếu đuôi ngày tháng.
    if kind == "experience":
        # 'Chức danh — Tổ chức  Jan 2025 – Sep 2025'
        # KHÔNG thêm "· ": parse() không bóc dấu đó ra, nó dính nguyên vào
        # câu và đi thẳng lên CV.
        head = f"{title.strip()} {meta.strip()}".strip()
        chunk = [head] + body
    elif meta.strip():
        chunk = [f"{title.strip()} — {meta.strip()}"] + body
    else:
        # TÊN PROJECT ĐỨNG RIÊNG MỘT DÒNG.
        #
        # Bản cũ ghép 'Tên — câu đầu' vì parse() ngày đó CHỈ nhận ra tiêu đề
        # project khi dòng có dấu " — ". Luật đó đã bỏ (nó hỏng trên 4/5 kiểu
        # viết thường gặp), và giữ lại cách ghi này thì round-trip gãy: ghi ra
        # 'Tên — Câu đầu.' rồi đọc lại, dòng kết thúc bằng dấu chấm nên không
        # còn là tiêu đề, và khối mất tên.
        #
        # Tên riêng một dòng cũng đúng cách CV thật viết mục project.
        chunk = [title.strip()] + body

    found = _bounds(lines, title)
    if found:
        start, stop = found
        return "\n".join(lines[:start] + chunk + lines[stop:]).rstrip() + "\n"

    name = SECTION_FOR.get(kind, "SELECTED PROJECTS")
    at = next((i for i, l in enumerate(lines) if l.strip().upper() == name), None)
    if at is None:                                    # chưa có mục thì mở mục
        return "\n".join(lines + ["", name] + chunk).rstrip() + "\n"
    return "\n".join(lines[:at + 1] + chunk + lines[at + 1:]).rstrip() + "\n"
