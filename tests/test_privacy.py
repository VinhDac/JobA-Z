"""PERSONAL DATA MUST NOT BE IN THE SOURCE.

This repo is public on GitHub. An earlier version had it straight in the
code: the full name, A REAL PHONE NUMBER, both email addresses, the education
with grades, and THE WHOLE CV — in `scripts/seed_profile.py` and three test
files. A phone number on a public repo is what bots harvest for SMS spam and
fraud.

This test reads the profile LIVING in the DB and then scans every git-tracked
file. It prints no value — only which file was hit, because the log line
itself goes into CI.

    python3 tests/test_privacy.py
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = Path(__file__).resolve().parent.parent
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ok   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}{' — ' + extra if extra else ''}")


def tracked() -> list[Path]:
    """Files that WILL reach GitHub: those tracked, PLUS new files not yet
    ignored.

    `ls-files` alone falls short: a file created today is untracked, but
    tomorrow's `git add .` puts it there. Measured — this guard originally
    missed exactly such a file.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files",
             "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    return [ROOT / line for line in out.stdout.split() if line]


def secrets() -> dict[str, str]:
    """The strings that must NOT appear in the source. Taken from the living
    profile rather than hardcoded here — hardcoding would make the test
    itself the leak.

    IT READS THE REAL PROFILE, DELIBERATELY BYPASSING THE SANDBOX. The shared
    runner (run_all.py) points JOBBOT_ROOT at a fake directory so no test can
    touch a secret — right for every test EXCEPT this one: its whole job is
    "did my real secrets get into a git-tracked file". Run inside the sandbox
    it scans for 0 strings and still reports green — a leak detector that has
    hollowed itself out.
    """
    giu = {k: os.environ.pop(k, None)
           for k in ("JOBBOT_ROOT", "JOBBOT_DATA_DIR")}
    out = {}
    try:
        from jobbot.core import db
        from jobbot.profile import store
        from jobbot.track import mail
        answers = store.load(db.connect())
        out["phone number"] = str(answers.get("phone") or "")
        out["profile email"] = str(answers.get("email") or "")
        out["app password"] = mail.account()[1]
    except Exception:                                # noqa: BLE001
        pass
    finally:
        for k, v in giu.items():
            if v is not None:
                os.environ[k] = v
    return {k: v for k, v in out.items() if v and len(v) >= 8}


def co_bi_mat_that() -> bool:
    """Does this machine HAVE a real secret to scan for? Read the config file
    directly.

    Used to tell apart two situations that look identical: "a clean machine
    with nothing to find" (valid) and "a broken detector that finds nothing"
    (must be RED).
    """
    tep = ROOT / "config" / "config.toml"
    if not tep.is_file():
        return False
    import re as _re
    return bool(_re.search(r"^\s*(app_password|password|token)\s*=\s*[\"']?\S",
                           tep.read_text(encoding="utf-8", errors="replace"),
                           _re.I | _re.M))


print("\n[personal data must not reach GitHub]")
files = tracked()
check("the git-tracked file list could be read", bool(files), f"{len(files)} files")

marks = secrets()

# AN EMPTY PROFILE is a valid state (a new user, or one who just started
# over) — there is nothing to leak then, so it must not count as a failure.
# But it must NOT pass empty either: the detector has to prove it works by
# finding a bait string that is certainly in a git-tracked file. Without this
# line, the day the file-reading function breaks, the test scans 0 files and
# still goes green.
def _dinh(needle: str) -> list[str]:
    got = []
    for path in files:
        try:
            if needle in path.read_text(encoding="utf-8", errors="ignore"):
                got.append(str(path.relative_to(ROOT)))
        except OSError:
            pass
    return got

check("the detector works (it found the bait string)", bool(_dinh("jobbot")))
# A CLEAN MACHINE is not A BROKEN DETECTOR. The two look identical from
# outside — both "found nothing" — so they are told apart by a different
# question: is there a real secret on disk. If there is and 0 items were
# found, the detector itself is broken.
_co = co_bi_mat_that()
check(f"{len(marks)} items to scan for" + ("" if marks else " — this machine is unconfigured"),
      bool(marks) or not _co)
if _co and not marks:
    check("THE DETECTOR IS BROKEN: config.toml holds a secret and no item was read", False)

for what, needle in marks.items():
    hits = _dinh(needle)
    # NO value is printed — only the name of the file hit.
    check(f"{what} appears in no file", not hits, " · ".join(hits))

# A file holding a secret has to be gitignored, not "happens not to be committed yet".
for name in ("config/config.toml", "config/profile.seed.json", "data/jobbot.db"):
    done = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", name],
                          capture_output=True)
    check(f"{name} is gitignored", done.returncode == 0)

# And it must never have reached history.
for name in ("config/config.toml", "config/profile.seed.json"):
    log = subprocess.run(["git", "-C", str(ROOT), "log", "--oneline", "--all", "--", name],
                         capture_output=True, text=True)
    check(f"{name} was never committed", not log.stdout.strip())

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
