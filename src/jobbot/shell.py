"""The window shell — pick the best one this machine can actually do.

    macOS + PyObjC   a real NSWindow, with a Dock icon and a menu-bar icon
    everything else  a Chrome window in --app mode: no address bar, no tabs,
                     its own icon on the taskbar

Why Chrome --app rather than just opening the browser: a browser tab makes
this a web page lost among twenty other tabs. --app gives a window that
stands on its own and opens and closes like an application. It is not an
NSWindow, but it is the closest thing that needs NO package installed — and
this whole app installs no packages.

Chrome is already required (step 1 drives it to read LinkedIn), so using it
as the shell adds no new constraint.

IMPORTANT: the UI window uses its OWN PROFILE, separate from the scraping
profile. Share one and the user's open window fights the tab the machine is
driving, and closing one kills the other.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .core.paths import data_dir

WINDOW = (1440, 900)


def ui_profile_dir() -> Path:
    path = data_dir() / "chrome-ui"
    path.mkdir(parents=True, exist_ok=True)
    return path


def has_mac_native() -> bool:
    """Does this macOS have PyObjC. If not, fall back to a Chrome window."""
    if sys.platform != "darwin":
        return False
    try:
        import objc                                        # noqa: F401
        from AppKit import NSApplication                   # noqa: F401
    except Exception:                                      # noqa: BLE001
        return False
    return True


def open_window(url: str) -> subprocess.Popen | None:
    """Open an app window pointing at url. Returns the process, or None if it
    could not be opened."""
    from .browser import chrome

    try:
        binary = chrome.binary()
    except chrome.ChromeError:
        return None

    args = [
        binary,
        f"--app={url}",
        f"--user-data-dir={ui_profile_dir()}",
        f"--window-size={WINDOW[0]},{WINDOW[1]}",
        "--no-first-run", "--no-default-browser-check",
        "--disable-background-networking", "--disable-sync",
        # Do NOT turn on --remote-debugging-port here: that port belongs to
        # the scraping window. Two windows on one port and cdp.open_tab()
        # can steer into the window the user is looking at.
    ]
    try:
        return subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except OSError:
        return None


def describe() -> str:
    """One line telling the user which shell is running."""
    if has_mac_native():
        return "macOS window (PyObjC)"
    try:
        from .browser import chrome
        return f"Chrome --app window ({Path(chrome.binary()).name})"
    except Exception:                                      # noqa: BLE001
        return "no shell — server only, opens your browser"
