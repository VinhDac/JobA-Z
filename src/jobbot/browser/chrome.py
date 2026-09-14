"""Launch and manage a SEPARATE Chrome.

BA RÀNG BUỘC, cố ý:

1. **Its own profile.** Chrome will not let two processes open one profile,
   so using the main profile would mean closing every browsing window each
   time the app runs. A separate profile -> log in once, then run in the
   background independently.
2. **Its own port** (9333), not the default 9222 — so it cannot collide with
   another tool.
3. **It never touches the Chrome the user has open.**
4. **One port = one profile.** Chrome locks the profile directory: two
   processes on one `--user-data-dir` and the second dies silently, with the
   debug port never opening. Measured: 9333 came up, 9334 on the same profile
   -> "Chrome did not come up within 8s". So the profile is derived FROM THE
   PORT, not an argument somebody has to remember to pass.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..core.paths import data_dir

PORT = 9333          # the scan — visible window, Vin can watch
PDF_PORT = 9334      # in CV — ẩn
APPLY_PORT = 9335    # filling the application form — visible, Vin clicks last

# One port, one profile. See constraint 4 at the top of this file.
PROFILE = {PORT: "chrome-profile", PDF_PORT: "chrome-pdf",
           APPLY_PORT: "chrome-apply"}


def _candidates() -> list[str]:
    """Where Chrome usually lives, per operating system.

    Windows: the paths contain environment variables (%LOCALAPPDATA% for a
    per-user install, Program Files for a machine-wide one), so they have to
    be built at runtime and cannot be constants.
    """
    if sys.platform == "win32":
        roots = [os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                 os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                 os.environ.get("LOCALAPPDATA", "")]
        out = []
        for root in filter(None, roots):
            out += [str(Path(root) / "Google/Chrome/Application/chrome.exe"),
                    str(Path(root) / "Chromium/Application/chrome.exe"),
                    str(Path(root) / "BraveSoftware/Brave-Browser/Application/brave.exe"),
                    str(Path(root) / "Microsoft/Edge/Application/msedge.exe")]
        return out
    if sys.platform == "darwin":
        return ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    return ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium", "/usr/bin/chromium-browser",
            "/snap/bin/chromium"]


CANDIDATES = _candidates()


# Flags for RUNNING UNATTENDED. This app scans 24/7 and most of that time
# nobody is looking at the screen — so the only thing allowed to appear in
# that window is a job posting. Each flag below blocks exactly ONE thing that
# has pushed, or would push, its way in:
KHONG_NGUOI_TRONG = (
    # A hard shutdown / power cut -> the next launch shows "Restore pages?"
    # over the content. Nobody presses Close at 3am.
    "--disable-session-crashed-bubble",
    "--hide-crash-restore-bubble",
    # The "Translate this page?" bar — French and Portuguese postings arrive
    # regularly, and that bar pushes the content down, sometimes hiding the
    # first line.
    "--disable-features=Translate,TranslateUI",
    # A site asking for notification permission -> a modal that blocks and
    # waits for a person to click.
    "--disable-notifications",
    # An unfocused window (the definition of "unattended") makes Chrome
    # throttle timers and freeze the renderer to save battery. The
    # consequence: the page's scripts never finish, grab() returns empty, and
    # that scan reports "0 postings" — a failure that looks exactly like
    # "there were no jobs today".
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    # Chrome updating a component mid-scan stalls the page being read.
    "--disable-component-update",
    # A cache ceiling. Without one the profile grows without bound —
    # measured at 134 MB after a day. 50 MB is plenty for reopening a few
    # thousand job pages.
    "--disk-cache-size=52428800",
)


class ChromeError(RuntimeError):
    pass


# Command names to look for in PATH, when Chrome is installed somewhere odd.
ON_PATH = ["google-chrome", "google-chrome-stable", "chromium",
           "chromium-browser", "chrome", "msedge"]


def binary() -> str:
    for path in _candidates():
        if Path(path).is_file():
            return path
    for name in ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    raise ChromeError(
        "Chrome not found. Install Google Chrome and try again "
        f"(checked {len(_candidates())} usual locations on {sys.platform}).")


def profile_dir(port: int = PORT) -> Path:
    path = data_dir() / PROFILE.get(port, f"chrome-{port}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def alive(port: int = PORT) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version",
                                    timeout=2) as resp:
            return json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def launch(headless: bool = True, port: int = PORT,
           wait: float = 15.0) -> subprocess.Popen | None:
    """Open the separate Chrome. Reuse it if it is already running."""
    if alive(port):
        return None

    args = [
        binary(),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir(port)}",
        "--no-first-run", "--no-default-browser-check",
        "--disable-background-networking", "--disable-sync",
        "--mute-audio", "--window-size=1440,900",
        *KHONG_NGUOI_TRONG,
    ]
    if headless:
        args.append("--headless=new")

    process = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    deadline = time.time() + wait
    while time.time() < deadline:
        if alive(port):
            return process
        time.sleep(0.4)
    process.terminate()
    raise ChromeError(f"Chrome did not come up within {wait:g}s")


def shutdown(port: int = PORT, wait: float = 6.0) -> bool:
    """Close the SEPARATE Chrome. It never touches the user's own Chrome.

    Returns True if it genuinely shut down.

    A BUG THAT WAS FIXED: the old version called GET /json/close — that
    endpoint needs a target id (/json/close/<id>), so it returned 404 and the
    error was swallowed in an except. The function ran smoothly, returned
    None, and Chrome was still there. The correct way is the CDP
    Browser.close command on the BROWSER's WebSocket, not a tab's.

    Why not kill the process directly: the user's personal Chrome is also a
    "Google Chrome" process. Going through debug port 9333 touches only the
    instance running under the app's own profile.
    """
    from .ws import WebSocket, WSError

    if not alive(port):
        return True
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=3) as r:
            browser_ws = json.load(r)["webSocketDebuggerUrl"]
        control = WebSocket(browser_ws)
        try:
            control.send(json.dumps({"id": 1, "method": "Browser.close"}))
            # Do not wait for a reply: Chrome closes the connection AS SOON
            # as it receives the command, so recv() here would raise — which
            # is the sign of success, not of failure.
            try:
                control.recv()
            except (WSError, OSError):
                pass
        finally:
            try:
                control.close()
            except Exception:                      # noqa: BLE001
                pass
    except Exception:                              # noqa: BLE001
        return False

    deadline = time.time() + wait
    while time.time() < deadline:
        if not alive(port):
            return True
        time.sleep(0.3)
    return not alive(port)


def shutdown_all(wait: float = 6.0) -> int:
    """Close EVERY Chrome the app owns. Returns how many really shut down.

    Quitting the app while closing only the default port leaves the APPLY
    window (9335) behind: it is DELIBERATELY left open while running so Vin
    can make the final click, so nobody else closes it. An orphaned window
    holds the profile directory lock, and the next launch cannot reopen that
    profile — a failure with no visible cause.
    """
    return sum(1 for port in PROFILE if alive(port) and shutdown(port, wait))
