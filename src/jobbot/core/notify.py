"""Operating-system notifications — macOS, Windows, Linux. Nothing to install.

    macOS    osascript (AppleScript)
    Windows  PowerShell + WinRT toast — NOT yet tried on a real Windows box
    Linux    notify-send

The rule: NOTIFY RARELY. Notify often and you get ignored, and at that point
the Yes/No gate is worthless. Only notify when A PERSON HAS TO DO SOMETHING,
never "finished scanning 47 postings".

A BUG THAT WAS FIXED: the command used to be built with shlex.quote — that
quotes for a SHELL, not for AppleScript. shlex.quote("Jobbot") returns a bare
Jobbot, and AppleScript reads it as a noun it does not know:

    display notification '5 new matches' with title Jobbot
    -> 21:22: syntax error ... found unknown token. (-2741)

Which means NOT ONE notification ever appeared, and send() returned False
with nobody reading it. AppleScript quotes with DOUBLE quotes, escaping \\
and " with a backslash.
"""

from __future__ import annotations

import subprocess
import sys


def _as_string(text: str) -> str:
    """A valid AppleScript string. Newlines must be escaped too, or the
    command gets cut in half."""
    escaped = (str(text).replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\r", ""))
    return f'"{escaped}"'


def script(title: str, message: str, subtitle: str = "") -> str:
    parts = [f"display notification {_as_string(message)}",
             f"with title {_as_string(title)}"]
    if subtitle:
        parts.append(f"subtitle {_as_string(subtitle)}")
    return " ".join(parts)


def _mac(title: str, message: str, subtitle: str) -> list[str]:
    return ["osascript", "-e", script(title, message, subtitle)]


def _windows(title: str, message: str, subtitle: str) -> list[str]:
    """A Windows 10/11 toast through PowerShell — nothing to install.

    Uses the WinRT that ships with the system. BurntToast is nicer but needs
    a module installed, and this whole app installs no packages.

    NOT TRIED ON A REAL WINDOWS BOX — written from the docs. If it fails,
    send() returns False and the scheduler writes 'notify_failed' to the
    journal. It does not go quiet.
    """
    body = message + (f"\n{subtitle}" if subtitle else "")
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager,"
        "Windows.UI.Notifications,ContentType=WindowsRuntime] > $null;"
        "$t=[Windows.UI.Notifications.ToastNotificationManager]::"
        "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        f"$x=$t.GetXml();$n=$t.GetElementsByTagName('text');"
        f"$n.Item(0).AppendChild($t.CreateTextNode({_ps_quote(title)}))>$null;"
        f"$n.Item(1).AppendChild($t.CreateTextNode({_ps_quote(body)}))>$null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::"
        "CreateToastNotifier('jobbot').Show("
        "[Windows.UI.Notifications.ToastNotification]::new($t))"
    )
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps]


def _linux(title: str, message: str, subtitle: str) -> list[str]:
    body = message + (f"\n{subtitle}" if subtitle else "")
    return ["notify-send", title, body]


def _ps_quote(text: str) -> str:
    """A PowerShell string quoted with SINGLE quotes; inside, a single quote
    is doubled."""
    return "'" + str(text).replace("'", "''").replace("\r", "") + "'"


BUILDERS = {"darwin": _mac, "win32": _windows}


def command(title: str, message: str, subtitle: str = "") -> list[str]:
    """The command this platform would run. Split out so it can be tested
    without actually running it."""
    build = BUILDERS.get(sys.platform, _linux)
    return build(title, message, subtitle)


def send(title: str, message: str, subtitle: str = "") -> bool:
    """True = it appeared. False = it did NOT — the caller must handle that,
    not swallow it."""
    try:
        subprocess.run(command(title, message, subtitle),
                       check=True, capture_output=True, timeout=10)
        return True
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
