"""Pressing Send — DELIBERATELY separate from the filling.

`run.py` fills the form and contains NOT ONE click-to-send command; a test
guards that. Which means however `run.py` breaks, it cannot apply on Vin's
behalf. Sending lives entirely in this file, reached by one route only: Vin
presses Send on that specific row in the Manage tab. One click, one
application.

THREE RULES BEFORE THE CLICK — the machine re-reads the filled form and
REFUSES to send if:

    1. any required field is still empty  (including the fields it
       deliberately did not fill: sponsorship, GPA, graduation date, the
       terms checkbox)
    2. it cannot find exactly one submit button belonging to THE form it
       filled
    3. the point about to be clicked is not on that button

Why re-read rather than trust the report from filling time: between filling
and clicking, Vin sat and answered the remaining fields. The true state is on
the page, not
trong bộ nhớ.

The right tab is found again by the `data-jbjob` marker stamped on the page
at fill time — no handle is kept in server memory, so restarting the web
server still leaves it sendable.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field as _field

from ..browser import cdp, chrome
from . import fields as F

PORT = chrome.APPLY_PORT

# The submit-button wording of the measured ATSes: Greenhouse "Submit
# Ashby "Submit Application", Lever "Submit application".
SUBMIT_TEXT = re.compile(r"^(submit|apply|send|nộp|gửi)\b", re.I)

# FIND and AIM in ONE call. This used to be two JS blocks repeating the same
# button-selection logic: one to approve, one to read the coordinates. Two
# copies of one rule drift apart eventually — and drifting here means
# approving one button and clicking another, on an action that cannot be
# undone.
#
# The submit button has to be inside THE form holding the fields we just
# filled (`[data-jb]`), not some other form on the page.
AIM_JS = r"""
(() => {
  // The form holding the MOST FILLED FIELDS is ours. Using
  // `querySelector('[data-jb]')` — the FIRST field on the whole page — is
  // wrong: a job page often has a search or newsletter form before it, and
  // if that first field lands in one of those, the machine clicks that
  // form's button. The old `inform` guard compared the button against the
  // very form it had just picked, so it always passed — an empty guard.
  const tally = new Map();
  for (const el of document.querySelectorAll('[data-jb]')) {
    const f = el.closest('form');
    if (f) tally.set(f, (tally.get(f) || 0) + 1);
  }
  if (!tally.size) return JSON.stringify({err: 'the filled form was not found'});
  let form = null, best = -1;
  for (const [f, n] of tally) { if (n > best) { best = n; form = f; } }

  const all = Array.from(form.querySelectorAll(
      'button[type="submit"], input[type="submit"], button:not([type])'))
    .filter(b => !b.disabled && b.offsetParent);
  // ONLY buttons whose text says send. If there is none, STOP; do not fall
  // back to "the only button left" — that button could be "Save draft",
  // "Add another" or "Upload".
  const named = all.filter(b => %TEXT%.test(((b.innerText || b.value || '') + '').trim()));
  if (named.length !== 1)
    return JSON.stringify({err: `${named.length} submit-worded buttons out of ${all.length}`});
  const pick = named;

  const b = pick[0];
  b.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = b.getBoundingClientRect();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  const on = document.elementFromPoint(x, y);
  return JSON.stringify({
    x: x, y: y, tag: b.tagName,
    inform: form.contains(b),
    fields: best,
    hits: !!on && (on === b || b.contains(on)),
    text: ((b.innerText || b.value || '') + '').trim(),
  });
})()
"""

MARK_JS = "document.documentElement.setAttribute('data-jbjob', '%JOB%')"
AFTER_JS = r"""
(() => ({url: location.href,
         text: (document.body ? document.body.innerText : '').slice(0, 600)}))()
"""


@dataclass
class Sent:
    ok: bool = False
    why: str = ""
    missing: list[str] = _field(default_factory=list)
    button: str = ""
    landed: str = ""


def _js(tab, template: str, **kw):
    text = template
    for key, value in kw.items():
        text = text.replace(f"%{key}%", str(value))
    return tab.eval(text)


def mark(tab, job: int) -> None:
    """Stamp the posting id onto the page, so this tab can be found later."""
    try:
        _js(tab, MARK_JS, JOB=int(job))
    except cdp.CDPError:
        pass


def find(job: int, port: int = PORT):
    """The tab holding this posting's form. None if there is none."""
    for page in cdp.pages(port):
        try:
            tab = cdp.attach(page["id"], port)
        except Exception:                            # noqa: BLE001
            continue
        try:
            if str(tab.eval("document.documentElement.getAttribute('data-jbjob')")
                   or "") == str(job):
                return tab
        except cdp.CDPError:
            pass
        tab.ws.close()                               # not the tab we want
    return None


def missing(tab) -> list[str]:
    """The required fields still empty. Empty means the form is ready."""
    out = []
    for item in F.read(tab):
        if item.get("required") and not (item.get("value") or "").strip():
            out.append(item["label"] or item["name"] or "?")
    return out


def submit(tab, job: int | None = None) -> Sent:
    """Check, then click. Not ready means DO NOT click, and say why."""
    # NO FIELDS LEFT on the page means the form has gone — usually because it
    # was just sent and the page moved to a thank-you. At that moment
    # missing() returns empty (no fields means no empty fields), so without
    # this guard a second click would go looking for "any button in any form"
    # on the thank-you page.
    if not F.read(tab):
        return Sent(False, "the page has no form left — it may already be sent")
    gaps = missing(tab)
    if gaps:
        return Sent(False, "required fields are still unanswered", gaps)

    # Scroll first, measure second: with smooth scrolling enabled, measuring
    # immediately reads the OLD COORDINATES and the click lands off screen
    # (measured y=1252 on a 900-tall viewport).
    _js(tab, AIM_JS, TEXT=f"/{SUBMIT_TEXT.pattern}/i")
    time.sleep(0.45)
    aim = json.loads(_js(tab, AIM_JS, TEXT=f"/{SUBMIT_TEXT.pattern}/i"))
    if aim.get("err"):
        return Sent(False, aim["err"])
    if not aim.get("inform"):
        return Sent(False, "the button does not belong to the filled form")
    if not aim.get("hits"):
        return Sent(False, "the click point is not on the button")

    before = json.loads(json.dumps(tab.eval(AFTER_JS) or {}))
    for kind in ("mousePressed", "mouseReleased"):
        tab.call("Input.dispatchMouseEvent",
                 {"type": kind, "x": aim["x"], "y": aim["y"],
                  "button": "left", "clickCount": 1})
    time.sleep(3.5)
    after = json.loads(json.dumps(tab.eval(AFTER_JS) or {}))

    # EVIDENCE, not "a mouse event was dispatched". The old version computed
    # `good`, threw it away and always returned ok=True — so a form the ATS
    # rejected (a field it validates itself, an expired posting, anti-bot)
    # was still written into the table as "applied", and Vin believed he had
    # applied when he had not.
    body = (after.get("text") or "").lower()
    said = any(w in body for w in ("thank", "received", "submitted", "success",
                                   "application sent", "we have your", "received"))
    moved = (after.get("url") or "") != (before.get("url") or "")
    gone = not F.read(tab)                       # the form vanished = it went
    if not (said or moved or gone):
        return Sent(False, "clicked but the page did not change — it may not have sent",
                    button=aim.get("text", ""),
                    landed=(after.get("url") or "")[:120])
    why = "sent" + ("" if said else
                    " (the page changed but said no confirmation)")
    return Sent(True, why, button=aim.get("text", ""),
                landed=(after.get("url") or "")[:120])
