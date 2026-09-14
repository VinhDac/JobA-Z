"""Print a CV version to PDF — with the Chrome already here, no library.

Why not reportlab/weasyprint: the whole app is stdlib, and adding a PDF
renderer means TWO ways of drawing the same CV — the screen version and the
paper version drift apart, and it is the paper version the employer reads.

Chrome prints EXACTLY the page on screen, through `@media print` in app.css.
One
one source of truth for both.

Chrome runs HEADLESS on its own port: 9333 belongs to the scan, which has a
real window open reading LinkedIn. Pressing Print and stealing the scan's tab
would break work in flight.
"""

from __future__ import annotations

import base64
import re
import threading
from pathlib import Path

from ..browser import cdp, chrome
from ..core.journal import CV, log as jlog

PORT = chrome.PDF_PORT   # its OWN port and profile — see chrome.PROFILE

# ONE print at a time. Both single and batch printing open and then CLOSE
# Chrome on this port; overlapping runs mean the thread that finishes first
# closes the other thread's Chrome, and the remaining 37 versions silently
# never print.
_ONE_AT_A_TIME = threading.Lock()

PAPER = {                                    # A4, 14mm margins — matches @page in the CSS
    "paperWidth": 8.27, "paperHeight": 11.69,
    "marginTop": 0.55, "marginBottom": 0.55,
    "marginLeft": 0.59, "marginRight": 0.59,
    "printBackground": False,                # the app's dark background must not print
    "preferCSSPageSize": True,
}


def slug(text: str) -> str:
    keep = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return keep[:60] or "cv"


# --- A QUALITY CHECK RIGHT BEFORE PRINTING ------------------------------
#
# All three bugs below REALLY HAPPENED, and every one of them only showed up
# by printing a sheet and looking at the image — no HTML test caught any:
#
#   app junk    the status bar printed over the last line, carrying a local
#               file path ("PDF: /Users/davi/…") onto the sheet sent to an
#               employer; the window title printed as the first line
#   pale text   the print colour rules listed each class to blacken, so any
#               class forgotten kept the DARK interface colour — measured
#               .cvskill at 192/255, which made the whole TECHNICAL SKILLS
#               section nearly invisible on white paper
#   bad margin  `main` is position:fixed left:226px (leaving room for the
#               sidebar); when printing, Chrome positions fixed elements
#               against the page box and left cannot be overridden — the CV
#               was pushed to the middle, wasting a quarter of the sheet
#
# So the check runs ON THE PAGE ABOUT TO PRINT, not on an HTML string. It does
# not block printing — the file still comes out, but it says plainly what is
# wrong with the sheet.
SANG_NHAT = 90          # 0 = black. Lighter than this does not read on paper.

_SOI = r"""(() => {
  const den = c => { const m = c.match(/\d+/g); return m ? (+m[0] + +m[1] + +m[2]) / 3 : 255 };
  const to = document.querySelector('.cvpaper');
  if (!to) return JSON.stringify(['no CV sheet (.cvpaper) found on the page']);
  const loi = [];

  // 1. APP JUNK: a visible element with text that is NOT inside the CV sheet.
  for (const e of document.querySelectorAll('body *')) {
    if (to.contains(e) || e.contains(to)) continue;
    if (e.children.length || !e.textContent.trim()) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    if (getComputedStyle(e).visibility === 'hidden') continue;
    loi.push('app junk on the sheet: ' + (e.className || e.tagName) + ' «'
             + e.textContent.trim().slice(0, 40) + '»');
    if (loi.length > 4) break;
  }

  // 2. PALE TEXT inside the CV sheet itself.
  let nhat = 0, ai = '';
  for (const e of to.querySelectorAll('*')) {
    if (e.children.length || !e.textContent.trim()) continue;
    const v = den(getComputedStyle(e).color);
    if (v > nhat) { nhat = v; ai = (e.className || e.tagName) + ' «'
                                  + e.textContent.trim().slice(0, 30) + '»' }
  }
  if (nhat > SANG_NHAT) loi.push('text too pale (' + Math.round(nhat) + '/255): ' + ai);

  // 3. MARGINS: the sheet must start at the left edge and use most of the width.
  const p = to.getBoundingClientRect(), W = document.documentElement.clientWidth;
  if (p.left > 8) loi.push('the CV sheet is inset ' + Math.round(p.left) + 'px — wasted left margin');
  if (p.width < W * 0.9) loi.push('the CV sheet is only ' + Math.round(p.width / W * 100) + '% of the page wide');
  return JSON.stringify(loi);
})()"""


def kiem(tab) -> list[str]:
    """Inspect THE PAGE ABOUT TO PRINT. Returns the problems; empty is clean.

    IF THIS GATE ITSELF BREAKS IT MUST SAY SO. The first version used
    `_SOI % SANG_NHAT` to inject the threshold, while the JS string contains
    a real `%` character ('% of the sheet') — Python raised ValueError, the
    `except` swallowed it, and the gate reported "clean" on every print. A
    gate that silently reports clean when it is itself broken is worse than
    no gate.
    """
    import json
    tab.call("Emulation.setEmulatedMedia", {"media": "print"})
    js = _SOI.replace("SANG_NHAT", str(SANG_NHAT))
    try:
        return json.loads(tab.eval(js)) or []
    except Exception as exc:            # noqa: BLE001
        return [f"COULD NOT INSPECT the sheet ({type(exc).__name__}: {exc}) — "
                f"nobody checked this sheet"]


def _print_one(tab, url: str, out: Path, timeout: float) -> Path:
    tab.go(url, wait_for=".cvpaper", timeout=timeout)
    for loi in kiem(tab):
        jlog.warn(CV, f"the printed CV sheet has problems — {loi}")
    reply = tab.call("Page.printToPDF", PAPER, timeout=timeout)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(reply["data"]))
    return out


def render(url: str, out: Path, timeout: float = 45.0) -> Path:
    """Print ONE version."""
    return next(iter(render_many([(url, out)], timeout=timeout)))


def render_many(jobs, timeout: float = 45.0, on_done=None):
    """Print MANY versions, sharing ONE Chrome and ONE tab.

    Launching and closing Chrome is most of the cost of a print. Relaunching
    per version means 41 versions take minutes and Chrome starts and stops 41
    times; keeping one tab and navigating it pays the fixed cost once.

    `jobs` = [(url, output path)]. `on_done(i, total, path)` reports progress.
    """
    jobs = list(jobs)
    if not jobs:
        return []
    with _ONE_AT_A_TIME:
        return _render_all(jobs, timeout, on_done)


def _render_all(jobs, timeout, on_done):
    started = chrome.launch(headless=True, port=PORT)
    tab = cdp.open_tab("about:blank", port=PORT)
    made = []
    try:
        for index, (url, out) in enumerate(jobs, 1):
            try:
                made.append(_print_one(tab, url, Path(out), timeout))
            except Exception:                       # noqa: BLE001
                # One broken version must NOT kill the batch. The rest print.
                made.append(None)
            if on_done:
                on_done(index, len(jobs), made[-1])
    finally:
        try:
            tab.close()
        finally:
            if started is not None:
                chrome.shutdown(port=PORT)
    return [m for m in made if m]


# --- HANDING THE FILE OVER ----------------------------------------------

def tai_ve(src: Path) -> Path | None:
    """Copy the printed file to ~/Downloads and reveal it in Finder.

    WHY NOT A DOWNLOAD LINK. The app shell is WKWebView (see app.py), and
    WKWebView does NOT download files by itself: without a WKDownloadDelegate
    a `Content-Disposition: attachment` does nothing at all — press the
    button, silence, no file, no error. Verify by reading app.py: it only
    declares delegates for the file picker and for new windows.

    And this is an app RUNNING ON YOUR OWN MACHINE: the file is already on
    disk. All that is missing is putting it somewhere findable. So copy it to
    Downloads and open Finder — works immediately, works in both shells, and
    needs no PyObjC delegate.

    THE ORIGINAL STAYS IN `data/cv/`: the apply flow looks for the attachment
    there (live.cv_pdf_for). Moving it outright kills the apply path.
    """
    import shutil
    import subprocess
    if not src.exists():
        return None
    dest_dir = Path.home() / "Downloads"
    if not dest_dir.is_dir():
        return None
    dest = dest_dir / src.name
    # A name collision adds a number rather than OVERWRITING: the old file
    # may be open, or already sent and still needed for comparison.
    if dest.exists():
        for i in range(2, 100):
            thu = dest_dir / f"{src.stem}-{i}{src.suffix}"
            if not thu.exists():
                dest = thu
                break
    shutil.copy2(src, dest)
    try:
        # -R: reveal in Finder with the file SELECTED, not just the folder
        # opened. The user sees which file just appeared and can drag it
        # straight into the application's attachment field.
        subprocess.run(["open", "-R", str(dest)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass                      # if Finder will not open, the file is still there
    return dest

