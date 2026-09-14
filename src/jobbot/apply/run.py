"""Open the application page, fill in what can be proved, STOP.

THE BOUNDARY — written in code, not in promises:

    The machine emits exactly TWO kinds of click, and each has a latch checked
    immediately before the click:

      open a dropdown  -> that element must WRAP THAT VERY FIELD (`wraps`)
      choose a row     -> that element must carry role="option" (`_OPTION`)

    And one latch shared by both: the point about to be clicked must REALLY
    SIT ON that element — `elementFromPoint` has to return it (`hits`).
    Without this latch a stale coordinate still clicks, and nobody knows what
    it clicked.

    Neither kind of element is a Submit button. The Submit button appears on
    no path in this file — so the machine cannot apply on Vin's behalf, not
    even when it breaks.

WHY IT HAS TO BE A REAL MOUSE CLICK. Measured on the Point72 form: the
current Greenhouse has no <select> elements left. Every dropdown is a
react-select — a text box. Setting its `.value` only TYPES INTO THE FILTER
BOX; the menu does not even open (`aria-expanded` stays false), and reading
`el.value` back gives exactly what was typed, so the machine reports success
to itself. Four fields reported green while actually empty — the worst kind
of failure, because it is silent.

The window stays open after filling: three questions like sponsorship or
graduation date are Vin's to answer, and so is pressing Submit.

Port 9335, its own profile — it never touches the scan loop (9333) or the CV
printer (9334).
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

# A page demanding a login. Meeting one of these in silence is the worst kind
# of failure: the machine reports "no form found" on a page that is only
# asking for a password, and Vin sits there guessing. Recognise it, say so
# outright, and say how to fix it.
LOGIN_WALL = re.compile(
    r"/login|/authwall|/signin|/sign-in|/uas/login|/checkpoint|/challenge", re.I)

MENU_WAIT = 2.5          # seconds to wait for a dropdown to open
SHORT = 3                # a name shorter than this may not match "contains"
_OPTION = re.compile(r"__option|(^|\s)option(\s|$)")

# Set a value the way React understands: call the prototype's own setter, then
# fire the events. Assigning `el.value = x` directly makes React redraw and
# wipe it — the box looks filled while the state is empty, and Submit reports
# it missing.
SET_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el) return 'field gone';
  const v = %VALUE%;
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
              : el.tagName === 'SELECT'   ? HTMLSelectElement.prototype
              : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input',  {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  el.dispatchEvent(new Event('blur',   {bubbles: true}));
  return el.value === v ? '' : 'not accepted';
})()
"""

# Scroll the field to the middle of the screen. KEPT SEPARATE from measuring,
# and forced to 'instant': this page enables smooth scrolling, so measuring
# straight after the call returns THE OLD COORDINATES — measured y=1252 in a
# 900-high window, and the click landed off the page hitting nothing. That is
# why 4 dropdowns silently failed to open.
SCROLL_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el) return 'field gone';
  el.scrollIntoView({block: 'center', behavior: 'instant'});
  return '';
})()
"""

# The element wrapping the field — where a person clicks to open the dropdown.
CONTROL_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el) return JSON.stringify({err: 'field gone'});
  const ctl = el.closest('[class*="control"]') || el.parentElement || el;
  const r = ctl.getBoundingClientRect();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  const on = document.elementFromPoint(x, y);
  return JSON.stringify({x: x, y: y, tag: ctl.tagName, wraps: ctl.contains(el),
                         hits: !!on && (on === ctl || ctl.contains(on))});
})()
"""

# The rows currently open for THIS field. Filters out the phone country-code
# list (intl-tel-input) — it is always present in the page and is not ours.
MENU_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el) return '[]';
  // DO NOT narrow by ancestor: `closest('[class*="container"]')` matches
  // `select__input-container` — an element wrapping only the text box, with
  // the menu outside it, so it always yields 0 rows. Only ONE menu can be
  // open at a time, so taking the whole page and filtering by VISIBLE is
  // both enough and correct.
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
  if (!o) return JSON.stringify({err: 'row gone'});
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

# Was anything actually chosen: react-select draws the chosen text as a "chip"
# inside the field.
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


# The description page and the application page are NOT the same. Greenhouse
# embeds the form right below the description; Ashby and Lever put the form on
# a URL of its own (.../application, .../apply) and the description page has
# not a single field — measured: 0 inputs on both.
#
# No lookup of "which ATS needs which suffix": that table has to be fed
# forever and is wrong the moment a company's own careers site turns up. Every
# page points the way itself, with an <a> reading "Apply" — follow that, on
# the same domain.
APPLY_LINK_JS = r"""
(() => {
  for (const a of document.querySelectorAll('a[href]')) {
    const text = (a.innerText || '').trim();
    const raw  = a.getAttribute('href') || '';
    let u; try { u = new URL(raw, location.href); } catch (e) { continue; }
    if (u.host !== location.host) continue;           // off-domain: skip
    if (u.href.replace(/#.*$/, '') === location.href.replace(/#.*$/, '')) continue;
    const named = /^(apply|application)/i.test(text)
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
    asks: list[tuple[str, str, bool]] = _field(default_factory=list)   # label, reason, required
    skipped: list[str] = _field(default_factory=list)
    missing: list[str] = _field(default_factory=list)                  # missing from the profile
    note: str = ""
    needs_login: str = ""          # the page demands a login; the value is that address
    # THE MACHINE CANNOT, A PERSON CAN. The value is the address the user has
    # to open themselves.
    #
    # A FLAG OF ITS OWN rather than reading words out of `note`: the Track
    # table marks a row "apply by hand" from this flag, and deriving that mark
    # by searching for a phrase inside a sentence breaks the first time
    # somebody rewords the sentence.
    tu_lam: str = ""

    def line(self) -> str:
        if self.needs_login:
            return "the page demands a login — nothing could be filled"
        if not self.total:
            return self.note or "no application form on this page"
        need = sum(1 for _, _, must in self.asks if must)
        bits = [f"filled {len(self.filled)}/{self.total} fields"]
        if self.failed:
            bits.append(f"{len(self.failed)} fields not accepted")
        if self.asks:
            bits.append(f"{len(self.asks)} fields need you"
                        + (f" ({need} required)" if need else ""))
        if self.skipped:
            bits.append(f"{len(self.skipped)} demographic fields skipped")
        return " · ".join(bits)


# --- matching -------------------------------------------------------------

def match(want: Ans, options: list[str]) -> str:
    """Which row in the list is the answer. Strict first, loose after.

    Three rules, in exactly this order:

    1. STRICTNESS WINS. The outer loop is the strictness level, the inner loop
       is the alternative names. The other way round and "UK" is contained in
       "Ukraine", so the machine picks Ukraine before it ever tries "United
       Kingdom".
    2. A short name (<= 3 characters) may not match by containment.
    3. When several rows match, first keep the row that AGREES WITH THE REST
       of the profile (`want.prefer`). "London" matches both London-UK and
       London-Ontario; Vin is in the UK, so London-UK.
    4. Still several, take THE SHORTEST ROW — extra words are extra claims.
       Type "master" and both "Master's Degree" and "Master of Business
       Administration (M.B.A.)" start with "master", and the machine picked
       the MBA; Vin read an MSc.
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
            # The short-name latch applies to the prefix level TOO, not just
            # "contains": "UK".startswith-matches "Ukraine" exactly as "UK"
            # is contained in "Ukraine".
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
    """The strings to type into the filter box, in the order they are tried.

    NO trick for guessing "the best string". Two tricks were tried and both
    were wrong on real forms: take the longest string and it types "United
    Kingdom of Great Britain" — no country is named that, the list comes back
    empty; take `value` exactly and it types "MSc" — Greenhouse writes
    "Master's Degree", also empty.

    So: type, look, and if nothing matches, clear it and type another name.
    Cut at the comma, because "Royal Holloway, University of London" typed one
    character off yields nothing.
    """
    out: list[str] = []
    for cand in want.candidates():
        text = (cand or "").split(",")[0].strip()[:24]
        if text and text.lower() not in [o.lower() for o in out]:
            out.append(text)
    return out[:limit]


# --- driving the browser --------------------------------------------------

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
    """Clear what was typed into the filter box. Backspace submits nothing."""
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
    """Choose a row in a dropdown. Returns (what was chosen, error)."""
    if _js(tab, SCROLL_JS, KEY=key):
        return "", "field gone"
    time.sleep(0.45)                            # measure only once it has scrolled
    box = json.loads(_js(tab, CONTROL_JS, KEY=key))
    if box.get("err"):
        return "", box["err"]
    # LATCH 1: the element must be wrapping this very field (an element
    # wrapping a text box is not a Submit button), AND the point about to be
    # clicked must really sit on it.
    if not box.get("wraps") or box.get("tag") in ("BUTTON", "A"):
        return "", "the wrapping element is not safe"
    if not box.get("hits"):
        return "", "the click point is not on the field"
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
        _key(tab, "Escape", 27)                 # close it, do not leave the page stuck
        return "", f"no row matched ({seen} rows)"

    spot = json.loads(_js(tab, PICK_JS, I=next(r["i"] for r in rows if r["text"] == chosen)))
    if spot.get("err"):
        return "", spot["err"]
    # LATCH 2: the element must carry the role of "a choosable row", and the
    # click point must sit on that row itself.
    if spot.get("role") != "option" and not _OPTION.search(spot.get("cls", "")):
        return "", "that row is not an option"
    if not spot.get("hits"):
        return "", "the click point is not on the row"
    _mouse(tab, spot["x"], spot["y"])
    time.sleep(0.5)

    shown = _js(tab, CHOSEN_JS, KEY=key) or ""
    if not shown:
        return "", "clicked, and the field is still empty"
    # "There is text in the field" is NOT yet proof. The field may have held a
    # default value already, or the widget may have taken the highlighted row
    # instead. It has to be compared against THE ROW THAT WAS CLICKED.
    lean = lambda t: re.sub(r"[^a-z0-9]+", "", (t or "").lower())   # noqa: E731
    if lean(chosen) not in lean(shown) and lean(shown) not in lean(chosen):
        return "", f"clicked '{chosen[:28]}' and the field shows '{shown[:28]}'"
    return shown, ""


KEEP_DAYS = 7            # how long an attachable copy lives before cleanup


def _prune(root: Path, days: int = KEEP_DAYS) -> int:
    """Clean up old attachable copies. One directory per application, and with
    nobody deleting them it grows forever — ~200 KB each, so a year of job
    hunting is a few hundred MB of duplicates. Cleaned while a new one is
    built, so there is no separate cleanup job to forget to run."""
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
            pass                                     # in use: leave it alone
    return gone


def sendable(resume: Path, book: dict[str, Ans], job: int | None) -> Path:
    """The CV TO ATTACH, named after Vin rather than after the posting.

    The filename in the store is the GROUP's name: one CV serves several
    postings and is named after the highest-scoring one in the group. Attach
    that file directly and the recruiter at Prima receives
    "qube-research-technologies-digital-assets-quantitative-trader.pdf" — they
    read the filename before they even open it, and a competitor's name is the
    first thing they see.

    So it is copied somewhere of its own for each posting, named with Vin's
    name. A directory per posting rather than one shared file: with two
    applications open at once the browser reads the file at the moment Submit
    is pressed, and overwriting means one application carries the other's CV.
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
        return resume                                # copy failed: attach the original


def attach(tab, key: int, path: Path) -> str:
    """Attach a file. JS cannot set the value of an input[type=file] — it has
    to go through a CDP command, which is why this function stands alone."""
    try:
        tab.call("DOM.enable")
        root = tab.call("DOM.getDocument")["root"]["nodeId"]
        node = tab.call("DOM.querySelector",
                        {"nodeId": root, "selector": f'[data-jb="{key}"]'})["nodeId"]
        if not node:
            return "field gone"
        tab.call("DOM.setFileInputFiles", {"files": [str(path)], "nodeId": node})
        return ""
    except Exception as exc:                          # noqa: BLE001
        return type(exc).__name__


# A real <select>: its `value` is the option's VALUE, not the text shown.
# `<option value="GB">United Kingdom</option>` — assigning "United Kingdom" to
# `.value` selects nothing. The option has to be found BY TEXT and
# selectedIndex set.
CHOOSE_JS = r"""
(() => {
  const el = document.querySelector('[data-jb="%KEY%"]');
  if (!el || !el.options) return 'field gone';
  const want = %TEXT%;
  const flat = t => (t || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const target = flat(want);
  for (let i = 0; i < el.options.length; i++) {
    if (flat(el.options[i].text) === target) {
      el.selectedIndex = i;
      el.dispatchEvent(new Event('input',  {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      return flat(el.options[el.selectedIndex].text) === target ? '' : 'not accepted';
    }
  }
  return 'no such row';
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


# --- the main loop --------------------------------------------------------

def fill(tab, book: dict[str, Ans], resume: Path | None,
         wait: float = 12.0, job: int | None = None) -> Report:
    """Fill the open form. It does NOT open a page and does NOT submit —
    separated so it can be measured.

    It waits for FIELDS, not for a <form> element: boards.greenhouse.io
    redirects to job-boards.greenhouse.io, and the OLD page's `<form>` matches
    the wait condition before the new page replaces the DOM — read at that
    moment it comes back empty, and the machine reports "no form found" on a
    page with 26 fields.
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

        # One fact fills ONE field. Lever has both "Portfolio URL" and "Other
        # website"; pouring the same link into both says one thing twice.
        if bucket == F.FILL and key in used:
            report.asks.append((label, "already filled in a field above", must))
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
                report.asks.append((label, "no PDF printed for this posting yet", True))
            continue

        want = book.get(key) or Ans("")
        if not want:
            report.asks.append((label, f"the profile has no {key}", must))
            report.missing.append(key)
            continue

        try:
            _one(tab, item, key, want, report, label, must, used)
        except cdp.CDPError as exc:
            # One broken field must NOT kill the whole run: losing the report
            # loses the 10 fields already filled too, and Vin has no idea what
            # state the form is in.
            report.failed.append((label, f"this field broke: {str(exc)[:40]}"))
        continue

    return report


def _one(tab, item, key, want: Ans, report: Report, label: str,
         must: bool, used: set) -> None:
    """Fill ONE field. A function of its own so a broken field costs one field,
    not the whole run."""
    if item["kind"] in ("checkbox", "radio"):
        # NEVER call _set() for a tick box. Its `value` is not the text shown
        # but the CODE the form will submit; assigning to it rewrites that
        # code without ticking anything, and `el.value === v` is still true so
        # the machine reports success. Measured in a real Chrome: the form
        # submitted "London" instead of "london_office".
        report.asks.append((label, "a tick box — choose it yourself", must))
        return

    if item["kind"] == "combo":
        got, bad = pick(tab, item["k"], want)
    elif item["kind"] == "select":
        got = match(want, item["options"])
        bad = _choose(tab, item["k"], got) if got else "no row matched"
    else:
        got, bad = want.value, _set(tab, item["k"], want.value)
        if bad:
            # A text box that will not take text is a dropdown in disguise —
            # Lever builds its location field with Google Places, with not one
            # ARIA attribute to recognise it by. Try the path a person takes;
            # if no row opens, press Escape and it becomes Vin's job.
            got, bad = pick(tab, item["k"], want)

    if bad:
        report.asks.append((label, bad, must))
    else:
        used.add(key)
        report.filled.append((label, got))


def login_wall(tab) -> str:
    """Is the page demanding a login? Returns that address, else empty.

    Meeting a login wall in silence is the worst kind of failure: the machine
    reports "no form found" on a page that is only asking for a password, and
    Vin sits there guessing.
    """
    try:
        here = tab.eval("location.href") or ""
    except cdp.CDPError:
        return ""
    return here if LOGIN_WALL.search(here) else ""


def _blocked(tab) -> "Report | None":
    """Is the page BLOCKING the fill. If so, return a Report saying so.

    Three places in open_and_fill() call this function, but it HAD NEVER BEEN
    WRITTEN — commit f669e66 moved to the shape `stuck = _blocked(tab)` and
    only changed the call sites, never writing the function, while deleting
    the two old functions it replaced. The result: every application died with
    a NameError before touching a single field.
    """
    wall = login_wall(tab)
    return Report(url=wall, needs_login=wall) if wall else None


def _await(tab, wait: float) -> list[dict]:
    """Wait for FIELDS to appear. Fields, not a <form> element:
    boards.greenhouse.io redirects to job-boards.greenhouse.io, and the OLD
    page's <form> matches the wait condition before the new DOM replaces it —
    read at that moment it comes back empty, and the machine reports "no form
    found" on a page with 26 fields.

    THIS FUNCTION WAS DELETED BY MISTAKE in commit f669e66 while TWO call
    sites remained, so every application reaching the "no fields yet" branch
    died with `NameError: name '_await' is not defined`. No test caught it,
    because that branch only runs with a real Chrome and a real careers page.
    """
    found = F.read(tab)
    deadline = time.time() + wait
    while not found and time.time() < deadline:
        time.sleep(0.6)
        found = F.read(tab)
    return found


def open_and_fill(url: str, book: dict[str, Ans], resume: Path | None,
                  job: int | None = None) -> tuple[Report, object]:
    """Open the page, find the form, fill it, RETURN THE TAB STILL OPEN.

    Three legs, any of which can stop early:

        1. a LinkedIn posting -> dig out the real application link (login needed)
        2. no fields yet      -> either a login wall, or the form is on its own page
        3. fill

    Every way out goes through `done()`, so the page is ALWAYS stamped with
    the posting's number (`data-jbjob`) — which is what the Submit button on
    the Track tab uses to find this tab again, instead of holding a handle in
    the server's memory.
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

    # 1. A LinkedIn posting is only a noticeboard; the real application link
    #    sits behind the Apply button and only appears once logged in. Dig it
    #    out and carry on like any other posting — the filling code has no
    #    LinkedIn-specific branch.
    if lk.JOBS.search(url):
        stuck = _blocked(tab)
        if stuck:
            return done(stuck)
        time.sleep(2.0)
        real = lk.apply_url(tab)
        if not real:
            return done(Report(
                url=url, tu_lam=url,
                note="this LinkedIn posting does not reveal an application "
                     "link — usually an agency, applied to through LinkedIn "
                     "or through the recruiter"))
        tab.go(real, timeout=45)
        hop = real

    # 2. No fields found. Two possibilities, and they have to be told apart: a
    #    login wall gets said outright, while a form on its own page is
    #    reached by following that page's own Apply link.
    if not _await(tab, 8):
        stuck = _blocked(tab)
        if stuck:
            return done(stuck)
        link = tab.eval(APPLY_LINK_JS) or ""
        if link:
            tab.go(link, timeout=45)
            hop = link                      # KEEP it, do not blank out step 1
            _await(tab, 10)
            stuck = _blocked(tab)
            if stuck:
                return done(stuck)

    # 3. Fill.
    report = fill(tab, book, resume, wait=4, job=job)
    report.url = tab.eval("location.href") or url
    if hop:
        report.note = f"the form is on its own page — {hop}"
    return done(report)
