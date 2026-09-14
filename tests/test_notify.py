"""Test the macOS notification — the thing that had BEEN BROKEN ALL ALONG
without anybody knowing.

The old version built the AppleScript with shlex.quote, i.e. quoting for a
SHELL:

    display notification '5 new matches' with title Jobbot
    -> 21:22: syntax error ... found unknown token. (-2741)

Not one notification ever appeared. send() returned False, and callers threw
it away.

    python3 tests/test_notify.py
"""

import subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import notify

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}{' — ' + extra if extra else ''}")


def compiles(script: str) -> tuple[bool, str]:
    """Can AppleScript COMPILE it. No notification is shown, it is only
    compiled — which is the real check: quoting mistakes are invisible to the
    eye."""
    done = subprocess.run(["osascript", "-e", f"return 1"], capture_output=True)
    if done.returncode != 0:                 # no osascript on this machine -> skip
        return True, "no osascript"
    done = subprocess.run(["osacompile", "-o", "/dev/null", "-e", script],
                          capture_output=True)
    return done.returncode == 0, done.stderr.decode()[:120]


print("[the command produced has to be valid AppleScript]")
built = notify.script("jobbot", "5 new postings match the profile", "Open the dashboard to see")
check("quoted with DOUBLE quotes, not single",
      '"jobbot"' in built and "'jobbot'" not in built)
good, err = compiles(built)
check("it compiles", good, err)

print("\n[dangerous strings must be escaped, never break the command]")
for title, message in [
        ('Job"bot', 'a "quoted" title'),
        ("back\\slash", "path C:\\temp"),
        ("two lines", "line one\nline two"),
        ("command injection", '" & (do shell script "echo x") & "'),
        ("Vietnamese", "5 việc mới khớp hồ sơ của bạn"),
]:
    good, err = compiles(notify.script(title, message))
    check(f"{title:12} -> still compiles", good, err)

check("a quote inside the body is escaped",
      '\\"' in notify.script("t", 'say "hi"'))
check("a newline does not cut the command in half",
      "\n" not in notify.script("t", "one\ntwo"))

print("\n[send returns THE TRUTH, not always True]")
check("sent -> returns True", notify.send("jobbot", "test suite") is True)
real = notify.subprocess
class Dead:
    SubprocessError = subprocess.SubprocessError
    @staticmethod
    def run(*a, **k):
        raise FileNotFoundError("no osascript")
notify.subprocess = Dead
check("sending failed -> returns False", notify.send("jobbot", "x") is False)
notify.subprocess = real

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
