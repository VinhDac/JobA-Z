"""The shared base for sources that go through Chrome.

Two rules:

1. **Cookie banners: ALWAYS decline, NEVER accept.** Only press
   reject/decline/only-necessary. Never press "Accept all" under any
   circumstances — the system has no authority to agree to terms on the
   user's behalf.

2. **Never try to get past a block.** A site that returns an anti-bot
   challenge is noted and skipped. That site is saying no to a machine — do
   not argue back.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from ...browser.cdp import CDPError, Tab

# DECLINE buttons only. This list deliberately contains no word that means
# consent.
#
# A BUG THAT WAS FIXED: the list used to sit inside a regex literal that
# wrapped mid-line, and the whole block was then .replace("\n", " ")'d. The
# branch split across lines became " strictly necessary" — with a leading
# space, while the button label had already been .trim()'d, so that branch
# never matched. Made into a LIST, no line wrapping can break it again.
REJECT_LABELS = [
    "reject all", "reject", "decline all", "decline", "refuse",
    "only necessary", "strictly necessary", "essential only",
    "necessary only", "continue without accepting",
]

REJECT_JS = ("""
(() => {
  const want = new RegExp('^(' + %s + ')$', 'i');
  for (const e of document.querySelectorAll('button,a[role=button],[role=button]')) {
    const t = (e.innerText || '').trim();
    if (want.test(t) && e.offsetParent !== null) { e.click(); return t; }
  }
  return "";
})()
""" % json.dumps("|".join(REJECT_LABELS))).replace("\n", " ")

BLOCKED = re.compile(
    r"just a moment|attention required|access denied|verify you are human|"
    r"unusual traffic|are you a robot|captcha|403 (page|forbidden)|"
    r"enable javascript and cookies", re.I)


@dataclass
class Health:
    """The health of one read of one source.

    With it, a broken source LOOKS DIFFERENT from a healthy one. Without it,
    `except Exception: continue` turns a 100% failure into complete silence.
    """
    attempted: int = 0
    failed: int = 0
    # Being blocked is its OWN state, not "a few postings failed". When
    # linkedin.fetch hit Blocked mid deep-read it used to just note() and
    # break, so failed stayed 0, record_run saw 0/193 failures and wrote
    # ok=1 — and Settings showed a green badge for a scan that was cut off at
    # the third posting.
    blocked: bool = False
    # A BREAK is not a BLOCK. Blocked means the gate refused us; a break
    # means the connection died mid-way — the machine woke from sleep, Chrome
    # died, the network dropped. The two need different handling (blocked
    # means go gentler, a break means just run again), so the journal has to
    # name them correctly. But both mean "this read was NOT complete", so
    # both set ok = False.
    cut: str = ""
    samples: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        if len(self.samples) < 5:
            self.samples.append(message)

    def block(self, message: str, unread: int = 0) -> None:
        """Blocked: set the flag, and count the postings NOT read as failures."""
        self.blocked = True
        self.failed += max(0, unread)
        self.note(message)

    def broke(self, message: str) -> None:
        """Cut off mid-way (not blocked). Record why, and mark it UNHEALTHY."""
        self.cut = message
        self.note(message)

    @property
    def ok(self) -> bool:
        return not (self.blocked or self.cut)

    @property
    def summary(self) -> str:
        if not (self.failed or self.blocked or self.cut):
            return ""
        head = "BLOCKED · " if self.blocked else "CUT OFF · " if self.cut else ""
        return (f"{head}{self.failed}/{self.attempted} failed · "
                + " · ".join(self.samples[:2]))


class Blocked(RuntimeError):
    """The site refused automated access. Note it and move on, do not argue."""


def reject_cookies(tab: Tab) -> str:
    try:
        clicked = tab.eval(REJECT_JS, timeout=10) or ""
    except CDPError:
        return ""
    if clicked:
        time.sleep(1.2)
    return clicked


def check_open(tab: Tab) -> None:
    """Is the site blocking us. If so, stop; do not look for a way around."""
    title = (tab.eval("document.title") or "")[:120]
    head = (tab.text() or "")[:400]
    if BLOCKED.search(title) or BLOCKED.search(head):
        raise Blocked(f"the site refused automated access ({title.strip()[:50]})")


def open_page(tab: Tab, url: str, wait_for: str = "body", timeout: float = 35.0) -> None:
    tab.go(url, wait_for=wait_for, timeout=timeout)
    reject_cookies(tab)
    check_open(tab)


def grab(tab: Tab, js: str, timeout: float = 25.0) -> list[dict]:
    """Run JS returning JSON. On error return an empty list rather than
    killing the whole scan."""
    try:
        raw = tab.eval(js, timeout=timeout)
        return json.loads(raw) if raw else []
    except (CDPError, ValueError, TypeError):
        return []
