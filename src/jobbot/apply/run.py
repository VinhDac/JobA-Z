"""Mở trang nộp, điền phần chứng minh được, DỪNG.

RANH GIỚI — viết bằng code chứ không bằng lời hứa:

    Máy phát ra đúng HAI loại cú bấm, và mỗi loại có một cái chốt kiểm ngay
    trước khi bấm:

      mở danh sách  -> thẻ đó phải BỌC CHÍNH Ô ĐÓ (`wraps`)
      chọn một dòng -> thẻ đó phải có role="option" (`_OPTION`)

    Và chốt chung cho cả hai: điểm sắp bấm phải THẬT SỰ NẰM TRÊN thẻ ấy —
    `elementFromPoint` phải trả về đúng nó (`hits`). Không có chốt này thì một
    toạ độ cũ vẫn bấm được, và bấm vào chỗ nào thì không ai biết.

    Không thẻ nào trong hai loại đó là nút Gửi. Nút Gửi không nằm trong bất kỳ
    đường nào của tệp này — nên máy không thể nộp thay Vin, kể cả khi hỏng.

VÌ SAO PHẢI BẤM CHUỘT THẬT. Đo trên form Point72: Greenhouse bản mới không còn
thẻ <select>. Mọi danh sách là react-select — một ô chữ. Đặt `.value` cho nó
chỉ là GÕ VÀO Ô LỌC; menu còn không mở (`aria-expanded` vẫn false), mà đọc lại
`el.value` thì đúng bằng chữ vừa gõ nên máy tự báo thành công. Bốn ô báo xanh
mà thật ra rỗng — kiểu hỏng tệ nhất, vì nó im lặng.

Cửa sổ ở lại sau khi điền: ba câu như sponsorship hay ngày tốt nghiệp là việc
của Vin, và cú bấm Gửi cũng vậy.

Cổng 9335, profile riêng — không đụng vòng quét (9333) hay máy in CV (9334).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field as _field
from pathlib import Path

from ..browser import cdp, chrome
from . import fields as F
from . import linkedin as lk
from .answer import Ans

PORT = chrome.APPLY_PORT

# Trang đòi đăng nhập. Gặp cái này mà im lặng là kiểu hỏng tệ nhất: máy báo
# "không thấy form" trên một trang thật ra chỉ đang hỏi mật khẩu, và Vin ngồi
# đoán. Nhận ra thì nói thẳng, kèm cách sửa.
LOGIN_WALL = re.compile(
    r"/login|/authwall|/signin|/sign-in|/uas/login|/checkpoint|/challenge", re.I)

MENU_WAIT = 2.5          # giây chờ danh sách bung ra
SHORT = 3                # tên ngắn hơn thế thì cấm khớp kiểu "nằm trong"
_OPTION = re.compile(r"__option|(^|\s)option(\s|$)")

# Đặt giá trị theo kiểu React hiểu được: gọi setter gốc của prototype rồi bắn
# sự kiện. Gán thẳng `el.value = x` thì React vẽ lại và xoá — ô nhìn có chữ mà
# state rỗng, bấm Gửi là báo thiếu.
SET_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el) return 'mất ô';
  const v = %VALUE%;
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
              : el.tagName === 'SELECT'   ? HTMLSelectElement.prototype
              : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input',  {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  el.dispatchEvent(new Event('blur',   {bubbles: true}));
  return el.value === v ? '' : 'không nhận';
})()
"""

# Kéo ô vào giữa màn hình. TÁCH RIÊNG khỏi bước đo, và ép 'instant':
# trang này đặt cuộn mượt, nên đo ngay sau khi gọi thì lấy về TOẠ ĐỘ CŨ —
# đo được y=1252 trong màn hình cao 900, cú bấm rơi ra ngoài trang và không
# trúng gì cả. Đó là lý do 4 ô danh sách im lặng không mở.
SCROLL_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el) return 'mất ô';
  el.scrollIntoView({block: 'center', behavior: 'instant'});
  return '';
})()
"""

# Thẻ bọc ô — chỗ người dùng bấm để danh sách bung ra.
CONTROL_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el) return JSON.stringify({err: 'mất ô'});
  const ctl = el.closest('[class*="control"]') || el.parentElement || el;
  const r = ctl.getBoundingClientRect();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  const on = document.elementFromPoint(x, y);
  return JSON.stringify({x: x, y: y, tag: ctl.tagName, wraps: ctl.contains(el),
                         hits: !!on && (on === ctl || ctl.contains(on))});
})()
"""

# Các dòng đang bung ra của CHÍNH ô này. Lọc bỏ danh sách mã vùng điện thoại
# (intl-tel-input) — nó luôn nằm sẵn trong trang và không phải của ta.
MENU_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el) return '[]';
  // KHÔNG thu hẹp theo thẻ cha: `closest('[class*="container"]')` bắt trúng
  // `select__input-container` — thẻ chỉ bọc mỗi ô chữ, menu nằm ngoài nó, nên
  // lúc nào cũng ra 0 dòng. Chỉ MỘT menu mở được tại một thời điểm, nên lấy
  // theo cả trang rồi lọc theo ĐANG HIỆN là đủ và đúng.
  let list = Array.from(document.querySelectorAll('[role="option"]'));
  list = list.filter(o => o.offsetParent && !(o.id || '').startsWith('iti'));
  return JSON.stringify(list.slice(0, 80).map((o, i) => {
    o.setAttribute('data-jbopt', i);
    return {i: i, text: (o.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 90)};
  }));
})()
"""

PICK_JS = r"""
(() => {
  const o = document.querySelector('[data-jbopt="%I%"]');
  if (!o) return JSON.stringify({err: 'mất dòng'});
  o.scrollIntoView({block: 'nearest', behavior: 'instant'});
  const r = o.getBoundingClientRect();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  const on = document.elementFromPoint(x, y);
  return JSON.stringify({x: x, y: y,
                         tag: o.tagName, role: o.getAttribute('role') || '',
                         cls: (o.className || '').toString(),
                         hits: !!on && (on === o || o.contains(on)),
                         text: (o.innerText || '').replace(/\s+/g, ' ').trim()});
})()
"""

# Đã chọn được hay chưa: react-select vẽ chữ đã chọn thành một "chip" trong ô.
CHOSEN_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el) return '';
  const ctl = el.closest('[class*="control"]') || el.parentElement;
  if (!ctl) return '';
  const chip = ctl.querySelector('[class*="ingleValue"], [class*="ingle-value"],'
                               + '[class*="ultiValue"], [class*="ulti-value"]');
  return chip ? (chip.innerText || '').replace(/\s+/g, ' ').trim() : '';
})()
"""


# Trang mô tả và trang nộp KHÔNG phải một. Greenhouse nhúng form ngay dưới mô
# tả; Ashby và Lever để form ở URL riêng (.../application, .../apply) và trang
# mô tả không có lấy một ô nào — đo được: 0 input trên cả hai.
#
# Không lập bảng "ATS nào thì thêm đuôi gì": bảng đó phải nuôi mãi và sai ngay
# khi gặp trang tuyển dụng riêng của công ty. Trang nào cũng tự chỉ đường bằng
# một thẻ <a> ghi "Apply" — đi theo chính nó, cùng tên miền.
APPLY_LINK_JS = r"""
(() => {
  for (const a of document.querySelectorAll('a[href]')) {
    const text = (a.innerText || '').trim();
    const raw  = a.getAttribute('href') || '';
    let u; try { u = new URL(raw, location.href); } catch (e) { continue; }
    if (u.host !== location.host) continue;           // ra ngoài miền: bỏ qua
    if (u.href.replace(/#.*$/, '') === location.href.replace(/#.*$/, '')) continue;
    const named = /^(apply|application)/i.test(text)
               || /\/(apply|application)\/?$/i.test(u.pathname);
    if (named) return u.href;
  }
  return '';
})()
"""


@dataclass
class Report:
    url: str = ""
    total: int = 0
    filled: list[tuple[str, str]] = _field(default_factory=list)
    failed: list[tuple[str, str]] = _field(default_factory=list)
    asks: list[tuple[str, str, bool]] = _field(default_factory=list)   # nhãn, lý do, bắt buộc
    skipped: list[str] = _field(default_factory=list)
    missing: list[str] = _field(default_factory=list)                  # hồ sơ thiếu
    note: str = ""
    needs_login: str = ""          # trang đòi đăng nhập; giá trị là địa chỉ đó
    # MÁY BÓ TAY, NGƯỜI LÀM ĐƯỢC. Giá trị là địa chỉ người dùng phải tự mở.
    #
    # Cờ RIÊNG chứ không đọc chữ trong `note`: bảng Quản lí gắn nhãn "phải tự
    # nộp tay" theo cờ này, và bắt nhãn bằng cách dò chuỗi tiếng Việt trong
    # một câu mô tả là thứ hỏng ngay lần đầu ai đó sửa câu chữ.
    tu_lam: str = ""

    def line(self) -> str:
        if self.needs_login:
            return "trang đòi đăng nhập — chưa điền được gì"
        if not self.total:
            return self.note or "không thấy form nộp trên trang này"
        need = sum(1 for _, _, must in self.asks if must)
        bits = [f"điền {len(self.filled)}/{self.total} ô"]
        if self.failed:
            bits.append(f"{len(self.failed)} ô không nhận")
        if self.asks:
            bits.append(f"{len(self.asks)} ô cần bạn"
                        + (f" ({need} bắt buộc)" if need else ""))
        if self.skipped:
            bits.append(f"{len(self.skipped)} ô nhân khẩu học bỏ qua")
        return " · ".join(bits)


# --- so khớp --------------------------------------------------------------

def match(want: Ans, options: list[str]) -> str:
    """Dòng nào trong danh sách là câu trả lời. Chặt trước, lỏng sau.

    Ba luật, theo đúng thứ tự này:

    1. ĐỘ CHẶT THẮNG. Vòng ngoài là mức chặt, vòng trong mới là các cách gọi.
       Ngược lại thì "UK" nằm-trong "Ukraine" và máy chọn Ukraine trước khi
       kịp thử "United Kingdom".
    2. Tên ngắn (<= 3 chữ) cấm khớp kiểu nằm-trong.
    3. Nhiều dòng cùng trúng thì trước hết giữ dòng HỢP VỚI PHẦN CÒN LẠI của
       hồ sơ (`want.prefer`). "London" trúng cả London-UK lẫn London-Ontario;
       Vin ở UK, nên London-UK.
    4. Vẫn còn nhiều thì lấy DÒNG NGẮN NHẤT — chữ thừa là lời khai thừa. Gõ
       "master" thì cả "Master's Degree" lẫn "Master of Business
       Administration (M.B.A.)" đều bắt đầu bằng "master", và máy đã chọn
       cái MBA; Vin học MSc.
    """
    if not options:
        return ""
    tries = [c for c in want.candidates() if c]
    head = want.value.split(",")[0].strip()
    if head and head not in tries:
        tries.append(head)
    low = [o.lower().strip() for o in options]

    for level in ("exact", "prefix", "inside"):
        for cand in tries:
            c = cand.lower().strip()
            # Chốt tên ngắn áp cho CẢ mức prefix, không riêng mức "nằm trong":
            # "UK".startswith-khớp "Ukraine" y như "UK" nằm trong "Ukraine".
            if not c or (level != "exact" and len(c) <= SHORT):
                continue
            hits = [i for i, o in enumerate(low) if o and (
                o == c if level == "exact" else
                o.startswith(c) if level == "prefix" else c in o)]
            if not hits:
                continue
            liked = [i for i in hits
                     if any(p.lower() in low[i] for p in want.prefer if p)]
            return options[min(liked or hits, key=lambda i: (len(low[i]), i))]
    return ""


def queries(want: Ans, limit: int = 3) -> list[str]:
    """Các chữ sẽ lần lượt gõ vào ô lọc, theo thứ tự thử.

    KHÔNG có mẹo đoán "chữ nào hay nhất". Đã thử hai mẹo và cả hai đều sai
    trên form thật: lấy chuỗi dài nhất thì gõ "United Kingdom of Great
    Britain" — không nước nào tên vậy, danh sách ra rỗng; lấy đúng `value`
    thì gõ "MSc" — Greenhouse ghi "Master's Degree", cũng rỗng.

    Nên: gõ, nhìn, không trúng thì xoá và gõ tên khác. Cắt ở dấu phẩy vì
    "Royal Holloway, University of London" viết lệch một dấu là rỗng.
    """
    out: list[str] = []
    for cand in want.candidates():
        text = (cand or "").split(",")[0].strip()[:24]
        if text and text.lower() not in [o.lower() for o in out]:
            out.append(text)
    return out[:limit]


# --- thao tác trình duyệt -------------------------------------------------

def _mouse(tab, x: float, y: float) -> None:
    for kind in ("mousePressed", "mouseReleased"):
        tab.call("Input.dispatchMouseEvent",
                 {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})


def _key(tab, name: str, code: int) -> None:
    for kind in ("rawKeyDown", "keyUp"):
        tab.call("Input.dispatchKeyEvent",
                 {"type": kind, "key": name, "code": name,
                  "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code})


def _clear(tab, count: int) -> None:
    """Xoá chữ đã gõ trong ô lọc. Backspace không gửi được form đi đâu cả."""
    for _ in range(min(count, 40)):
        _key(tab, "Backspace", 8)


def _js(tab, template: str, **kw):
    text = template
    for k, v in kw.items():
        text = text.replace(f"%{k}%", str(v))
    return tab.eval(text)


def _menu(tab, key: int) -> list[dict]:
    return json.loads(_js(tab, MENU_JS, KEY=key) or "[]")


def pick(tab, key: int, want: Ans) -> tuple[str, str]:
    """Chọn một dòng trong danh sách thả xuống. Trả (đã chọn, lỗi)."""
    if _js(tab, SCROLL_JS, KEY=key):
        return "", "mất ô"
    time.sleep(0.45)                            # cuộn xong rồi mới đo
    box = json.loads(_js(tab, CONTROL_JS, KEY=key))
    if box.get("err"):
        return "", box["err"]
    # CHỐT 1: thẻ phải đang bọc chính ô này (một thẻ bọc ô chữ thì không phải
    # nút Gửi), VÀ điểm sắp bấm phải thật sự nằm trên nó.
    if not box.get("wraps") or box.get("tag") in ("BUTTON", "A"):
        return "", "thẻ bọc không an toàn"
    if not box.get("hits"):
        return "", "điểm bấm không nằm trên ô"
    _mouse(tab, box["x"], box["y"])

    deadline = time.time() + MENU_WAIT
    while time.time() < deadline and not _menu(tab, key):
        time.sleep(0.25)

    chosen, rows, seen = "", [], 0
    for attempt, text in enumerate(queries(want)):
        if attempt:
            _clear(tab, len(previous))
        previous = text
        tab.call("Input.insertText", {"text": text})
        time.sleep(0.9)
        rows = _menu(tab, key)
        seen = max(seen, len(rows))
        chosen = match(want, [r["text"] for r in rows])
        if chosen:
            break
    if not chosen:
        _key(tab, "Escape", 27)                 # đóng lại, đừng để trang treo
        return "", f"không dòng nào khớp ({seen} dòng)"

    spot = json.loads(_js(tab, PICK_JS, I=next(r["i"] for r in rows if r["text"] == chosen)))
    if spot.get("err"):
        return "", spot["err"]
    # CHỐT 2: thẻ phải mang vai trò "một dòng lựa chọn", và điểm bấm phải
    # nằm trên chính nó.
    if spot.get("role") != "option" and not _OPTION.search(spot.get("cls", "")):
        return "", "dòng không phải lựa chọn"
    if not spot.get("hits"):
        return "", "điểm bấm không nằm trên dòng"
    _mouse(tab, spot["x"], spot["y"])
    time.sleep(0.5)

    shown = _js(tab, CHOSEN_JS, KEY=key) or ""
    if not shown:
        return "", "bấm rồi mà ô vẫn trống"
    # "Có chữ trong ô" CHƯA phải bằng chứng. Ô có thể đã sẵn một giá trị mặc
    # định từ trước, hoặc widget chọn nhầm dòng đang được tô sáng. Phải so với
    # ĐÚNG dòng vừa bấm.
    lean = lambda t: re.sub(r"[^a-z0-9]+", "", (t or "").lower())   # noqa: E731
    if lean(chosen) not in lean(shown) and lean(shown) not in lean(chosen):
        return "", f"bấm '{chosen[:28]}' mà ô hiện '{shown[:28]}'"
    return shown, ""


KEEP_DAYS = 7            # bản dàn để đính kèm sống bao lâu trước khi dọn


def _prune(root: Path, days: int = KEEP_DAYS) -> int:
    """Dọn bản dàn cũ. Một thư mục cho một lần nộp, không ai xoá thì nó phình
    mãi — mỗi bản ~200 KB, một năm tìm việc là vài trăm MB trùng lặp. Dọn ngay
    trong lúc dựng bản mới, khỏi cần một việc dọn dẹp riêng để rồi quên chạy."""
    if not root.exists():
        return 0
    cutoff = time.time() - days * 86400
    gone = 0
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            if child.stat().st_mtime >= cutoff:
                continue
            for f in child.iterdir():
                f.unlink()
            child.rmdir()
            gone += 1
        except OSError:
            pass                                     # đang mở thì để yên
    return gone


def sendable(resume: Path, book: dict[str, Ans], job: int | None) -> Path:
    """Bản CV để ĐÍNH KÈM, đặt tên theo Vin chứ không theo tin.

    Tên tệp trong kho là tên NHÓM: một bản CV dùng cho nhiều tin, đặt theo tin
    điểm cao nhất trong nhóm. Đính thẳng tệp đó thì nhà tuyển dụng Prima nhận
    được "qube-research-technologies-digital-assets-quantitative-trader.pdf" —
    họ đọc tên tệp trước cả khi mở, và thấy ngay tên đối thủ.

    Nên chép sang một chỗ riêng cho từng tin, đặt tên bằng tên Vin. Thư mục
    riêng theo tin, không dùng chung một tệp: hai đơn mở cùng lúc thì trình
    duyệt đọc tệp lúc bấm Gửi, ghi đè là đơn này mang CV của đơn kia.
    """
    who = (book.get("full_name") or Ans("")).value or "CV"
    name = re.sub(r"[^A-Za-z0-9]+", "-", who).strip("-") + "-CV.pdf"
    root = resume.parent / "send"
    _prune(root)
    stage = root / str(job if job is not None else "one")
    stage.mkdir(parents=True, exist_ok=True)
    out = stage / name
    try:
        out.write_bytes(resume.read_bytes())
        return out
    except OSError:
        return resume                                # chép hỏng thì đính bản gốc


def attach(tab, key: int, path: Path) -> str:
    """Gắn tệp. JS không đặt được value của input[type=file] — phải đi bằng
    lệnh CDP, đó là lý do hàm này đứng riêng."""
    try:
        tab.call("DOM.enable")
        root = tab.call("DOM.getDocument")["root"]["nodeId"]
        node = tab.call("DOM.querySelector",
                        {"nodeId": root, "selector": f'[data-jb="{key}"]'})["nodeId"]
        if not node:
            return "mất ô"
        tab.call("DOM.setFileInputFiles", {"files": [str(path)], "nodeId": node})
        return ""
    except Exception as exc:                          # noqa: BLE001
        return type(exc).__name__


# <select> thật: `value` của nó là GIÁ TRỊ của option, không phải chữ hiện ra.
# `<option value="GB">United Kingdom</option>` — gán "United Kingdom" vào
# `.value` thì không chọn được gì. Phải tìm option theo CHỮ rồi đặt
# selectedIndex.
CHOOSE_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el || !el.options) return 'mất ô';
  const want = %TEXT%;
  const flat = t => (t || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const target = flat(want);
  for (let i = 0; i < el.options.length; i++) {
    if (flat(el.options[i].text) === target) {
      el.selectedIndex = i;
      el.dispatchEvent(new Event('input',  {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      return flat(el.options[el.selectedIndex].text) === target ? '' : 'không nhận';
    }
  }
  return 'không thấy dòng đó';
})()
"""


def _choose(tab, key: int, text: str) -> str:
    try:
        return _js(tab, CHOOSE_JS, KEY=key, TEXT=json.dumps(text)) or ""
    except cdp.CDPError as exc:
        return str(exc)[:40]


def _set(tab, key: int, value: str) -> str:
    try:
        return _js(tab, SET_JS, KEY=key, VALUE=json.dumps(value)) or ""
    except cdp.CDPError as exc:
        return str(exc)[:40]


# --- vòng chính -----------------------------------------------------------

def fill(tab, book: dict[str, Ans], resume: Path | None,
         wait: float = 12.0, job: int | None = None) -> Report:
    """Điền form đang mở. KHÔNG mở trang, KHÔNG gửi — tách ra để đo được.

    Chờ Ô chứ không chờ thẻ <form>: boards.greenhouse.io chuyển hướng sang
    job-boards.greenhouse.io, và `<form>` của trang CŨ khớp điều kiện chờ
    trước khi trang mới thay DOM — đọc lúc đó ra rỗng, máy báo "không thấy
    form" trên một trang có 26 ô.
    """
    found = F.read(tab)
    deadline = time.time() + wait
    while not found and time.time() < deadline:
        time.sleep(0.6)
        found = F.read(tab)
    report = Report(total=len(found))
    if not found:
        return report

    used: set[str] = set()
    for item in found:
        label = item["label"] or item["name"] or "?"
        bucket, key, must = item["bucket"], item["key"], bool(item["required"])

        # Một sự thật điền MỘT ô. Lever có cả "Portfolio URL" lẫn "Other
        # website"; đổ cùng một đường dẫn vào cả hai là nói một câu hai lần.
        if bucket == F.FILL and key in used:
            report.asks.append((label, "đã điền ở ô trên", must))
            continue

        if bucket == F.SKIP:
            report.skipped.append(label)
            continue
        if bucket == F.ASK:
            report.asks.append((label, key, must))
            continue

        if key == "resume":
            if resume and resume.exists():
                paper = sendable(resume, book, job)
                bad = attach(tab, item["k"], paper)
                if not bad:
                    used.add(key)
                (report.filled if not bad else report.failed).append(
                    (label, paper.name if not bad else bad))
            else:
                report.asks.append((label, "chưa in PDF cho tin này", True))
            continue

        want = book.get(key) or Ans("")
        if not want:
            report.asks.append((label, f"hồ sơ chưa có {key}", must))
            report.missing.append(key)
            continue

        try:
            _one(tab, item, key, want, report, label, must, used)
        except cdp.CDPError as exc:
            # Một ô hỏng KHÔNG được giết cả lượt điền: mất báo cáo là mất luôn
            # 10 ô đã điền trước đó, và Vin không biết form đang ở trạng thái nào.
            report.failed.append((label, f"ô này hỏng: {str(exc)[:40]}"))
        continue

    return report


def _one(tab, item, key, want: Ans, report: Report, label: str,
         must: bool, used: set) -> None:
    """Điền MỘT ô. Tách hàm riêng để một ô hỏng chỉ mất một ô, không mất lượt."""
    if item["kind"] in ("checkbox", "radio"):
        # KHÔNG bao giờ gọi _set() cho ô đánh dấu. `value` của nó không phải
        # chữ hiện ra mà là MÃ form sẽ gửi đi; gán vào là viết lại mã đó mà
        # không tick gì cả, và `el.value === v` vẫn đúng nên máy báo thành
        # công. Đo trong Chrome thật: form gửi "London" thay vì
        # "london_office".
        report.asks.append((label, "ô đánh dấu — bạn tự chọn", must))
        return

    if item["kind"] == "combo":
        got, bad = pick(tab, item["k"], want)
    elif item["kind"] == "select":
        got = match(want, item["options"])
        bad = _choose(tab, item["k"], got) if got else "không dòng nào khớp"
    else:
        got, bad = want.value, _set(tab, item["k"], want.value)
        if bad:
            # Ô chữ mà không nhận chữ thì nó là danh sách gợi ý đội lốt ô chữ —
            # Lever dựng ô địa điểm bằng Google Places, không một thuộc tính
            # ARIA nào để nhận ra. Thử đúng đường người dùng đi; không có dòng
            # nào bung ra thì Escape, thành việc của Vin.
            got, bad = pick(tab, item["k"], want)

    if bad:
        report.asks.append((label, bad, must))
    else:
        used.add(key)
        report.filled.append((label, got))


def login_wall(tab) -> str:
    """Trang đang đòi đăng nhập? Trả về địa chỉ đó, không thì rỗng.

    Gặp tường đăng nhập mà im lặng là kiểu hỏng tệ nhất: máy báo "không thấy
    form" trên một trang thật ra chỉ đang hỏi mật khẩu, và Vin ngồi đoán.
    """
    try:
        here = tab.eval("location.href") or ""
    except cdp.CDPError:
        return ""
    return here if LOGIN_WALL.search(here) else ""


def _blocked(tab) -> "Report | None":
    """Trang có đang CHẶN không cho điền không. Có thì trả Report nói rõ.

    Ba chỗ trong open_and_fill() gọi hàm này, nhưng nó CHƯA BAO GIỜ được viết
    — commit f669e66 đổi sang hình dạng `stuck = _blocked(tab)` mà chỉ sửa
    chỗ gọi, không viết hàm, và xoá luôn hai hàm cũ nó thay thế. Kết quả: mọi
    lần nộp đơn đều chết bằng NameError trước khi chạm tới ô nào.
    """
    wall = login_wall(tab)
    return Report(url=wall, needs_login=wall) if wall else None


def _await(tab, wait: float) -> list[dict]:
    """Chờ Ô hiện ra. Chờ Ô chứ không chờ thẻ <form>: boards.greenhouse.io
    chuyển hướng sang job-boards.greenhouse.io, và <form> của trang CŨ khớp
    điều kiện chờ trước khi DOM mới thay vào — đọc lúc đó ra rỗng, máy báo
    "không thấy form" trên một trang có 26 ô.

    HÀM NÀY TỪNG BỊ XOÁ NHẦM ở commit f669e66 trong khi HAI chỗ gọi vẫn còn,
    nên mọi lần nộp đi tới nhánh "chưa thấy ô nào" đều chết bằng
    `NameError: name '_await' is not defined`. Không test nào bắt được, vì
    nhánh đó chỉ chạy khi có Chrome thật và một trang tuyển dụng thật.
    """
    found = F.read(tab)
    deadline = time.time() + wait
    while not found and time.time() < deadline:
        time.sleep(0.6)
        found = F.read(tab)
    return found


def open_and_fill(url: str, book: dict[str, Ans], resume: Path | None,
                  job: int | None = None) -> tuple[Report, object]:
    """Mở trang, tìm đến form, điền, TRẢ TAB CÒN MỞ.

    Ba chặng, chặng nào cũng có thể dừng sớm:

        1. tin LinkedIn  -> moi đường nộp thật ra (cần đăng nhập)
        2. chưa thấy ô   -> hoặc trang đòi đăng nhập, hoặc form ở trang riêng
        3. điền

    Mọi lối ra đều đi qua `done()`, nên trang LUÔN được đóng dấu số hiệu tin
    (`data-jbjob`) — đó là thứ nút Gửi ở tab Quản lí dùng để tìm lại đúng tab
    này, thay vì giữ tay cầm trong bộ nhớ máy chủ.
    """
    from .send import mark

    chrome.launch(headless=False, port=PORT)
    tab = cdp.open_tab("about:blank", port=PORT)
    tab.go(url, timeout=45)

    def done(report: Report):
        if job is not None:
            mark(tab, job)
        return report, tab

    hop = ""

    # 1. Tin LinkedIn chỉ là bảng tin; đường nộp thật nằm sau nút Apply và chỉ
    #    hiện khi đã đăng nhập. Moi ra rồi đi tiếp như mọi tin khác — phần điền
    #    không có nhánh riêng nào cho LinkedIn.
    if lk.JOBS.search(url):
        stuck = _blocked(tab)
        if stuck:
            return done(stuck)
        time.sleep(2.0)
        real = lk.apply_url(tab)
        if not real:
            return done(Report(
                url=url, tu_lam=url,
                note="tin LinkedIn này không lộ đường nộp — thường là môi "
                     "giới, nộp qua LinkedIn hoặc qua người tuyển"))
        tab.go(real, timeout=45)
        hop = real

    # 2. Chưa thấy ô nào. Hai khả năng, và phải phân biệt: trang đòi đăng nhập
    #    thì nói thẳng, còn form nằm ở trang riêng thì đi theo link Apply của
    #    chính trang đó.
    if not _await(tab, 8):
        stuck = _blocked(tab)
        if stuck:
            return done(stuck)
        link = tab.eval(APPLY_LINK_JS) or ""
        if link:
            tab.go(link, timeout=45)
            hop = link                      # GIỮ, không ghi đè bước 1 bằng rỗng
            _await(tab, 10)
            stuck = _blocked(tab)
            if stuck:
                return done(stuck)

    # 3. Điền.
    report = fill(tab, book, resume, wait=4, job=job)
    report.url = tab.eval("location.href") or url
    if hop:
        report.note = f"form ở trang riêng — {hop}"
    return done(report)
