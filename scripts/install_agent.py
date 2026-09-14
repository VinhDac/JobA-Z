#!/usr/bin/env python3
"""Install jobbot as a macOS background service (launchd).

    python3 scripts/install_agent.py             install and start it now
    python3 scripts/install_agent.py --status    is it running?
    python3 scripts/install_agent.py --uninstall remove it

Once installed: it starts with the machine, and restarts itself after a crash.
Pressing "Quit jobbot" in the menu bar STOPS IT FOR GOOD, with no restart — which
is why this uses KeepAlive={SuccessfulExit:false} rather than KeepAlive=true.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL = "com.jobbot.agent"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = ROOT / "data" / "agent.log"


def plist_body() -> dict:
    return {
        "Label": LABEL,
        # Point at the bundle, not at run.py: only the app gets the right icon and
        # the right name in the Dock and in cmd-tab.
        "ProgramArguments": [str(ROOT / "jobbot.app" / "Contents" / "MacOS" / "jobbot")],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        # a dict, NOT True: restart after a crash, stay down after a clean exit.
        "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
            "PYTHONUNBUFFERED": "1",
        },
    }


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def domain() -> str:
    return f"gui/{os.getuid()}"


def install() -> int:
    bundle = ROOT / "jobbot.app"
    if not bundle.exists():
        print("\n  There is no jobbot.app yet. Run this first:  python3 scripts/make_app.py\n")
        return 1
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)

    _launchctl("bootout", f"{domain()}/{LABEL}")        # remove an older one, if any
    PLIST.write_bytes(plistlib.dumps(plist_body()))

    done = _launchctl("bootstrap", domain(), str(PLIST))
    if done.returncode != 0:                             # older macOS
        done = _launchctl("load", "-w", str(PLIST))
    if done.returncode != 0:
        print(f"Could not load it: {done.stderr.strip()}")
        return 1

    print(f"\n  Installed: {PLIST}")
    print(f"  Log:       {LOG}")
    print("\n  It starts with the machine. The ◆ icon sits in the menu bar.")
    # The port is handed out by the operating system, so it changes from run to run.
    # Printing a fixed 8765 here sends the user to a dead address whenever it differs.
    print(f"  Dashboard: the address is in {ROOT / 'data' / 'dang-chay.txt'}\n")
    return 0


def uninstall() -> int:
    _launchctl("bootout", f"{domain()}/{LABEL}")
    _launchctl("unload", "-w", str(PLIST))
    if PLIST.exists():
        PLIST.unlink()
    print(f"\n  Removed {LABEL}\n")
    return 0


def status() -> int:
    found = _launchctl("print", f"{domain()}/{LABEL}")
    if found.returncode != 0:
        print("\n  Not installed.\n")
        return 1
    state = next((l.strip() for l in found.stdout.splitlines() if "state =" in l), "?")
    pid = next((l.strip() for l in found.stdout.splitlines() if l.strip().startswith("pid =")), "pid = —")
    print(f"\n  {LABEL}\n  {state}\n  {pid}\n  plist: {PLIST}\n")
    return 0


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        sys.exit(uninstall())
    if "--status" in sys.argv:
        sys.exit(status())
    sys.exit(install())
