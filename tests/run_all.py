"""Run EVERY test with one command, and trust none of them.

    python3 tests/run_all.py

Why it is needed: each test file is a self-running script, with no runner at
all. The real consequence was test_browser.py forgetting its sys.exit line —
it printed "48 ok, 0 fail" and exited 0 however many had failed, and a
run-and-check-the-exit-code loop would never have noticed.

So BOTH sides are checked here, and both have to agree:
    · the exit code has to be 0
    · the final summary line has to say 0 fail
    · there has to BE a summary line — silence is not a pass
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUMMARY = re.compile(r"^(\d+) ok, (\d+) fail\s*$", re.M)

# THE USER'S FILES — a test run must NOT touch them, not by one byte.
#
# This is not hypothetical. On 12/09 the test for the "start over" route
# really DELETED Vin's config/config.toml on every run, and another test wrote
# the fake address "a@b.c" over it — swallowing the Gmail app password he had
# just pasted in. Both were bright green, because no test was watching the
# tests.
CANH = ("config/config.toml", "config/boards.toml", "config/companies.toml",
        "config/profile.seed.json")


def _dau_van_tay() -> dict:
    """Hash the user's files. Their contents are never read out anywhere —
    the app password is in there."""
    import hashlib
    out = {}
    for ten in CANH:
        f = HERE.parent / ten
        out[ten] = (hashlib.sha1(f.read_bytes()).hexdigest()
                    if f.exists() else None)
    return out


def main() -> int:
    files = sorted(f for f in HERE.glob("test_*.py"))
    if not files:
        print("no test file found")
        return 1

    width = max(len(f.name) for f in files)
    total_ok = total_fail = broken = 0
    truoc = _dau_van_tay()

    # TESTS RUN IN A WORLD THAT HOLDS NOBODY'S SECRETS.
    #
    # No env was passed before, and the fingerprint above only watches for
    # WRITES over the user's files — not for READS. The measured consequence:
    # from the moment Telegram was connected, every test run sent REAL
    # messages to the user's phone, including a false alarm "⚠️ Session
    # failed" the tests themselves had staged. And five tests asserting "the
    # bot is not connected" went red — red because this machine has a config,
    # not because the code was wrong.
    #
    # JOBBOT_ROOT redirects config/ AND reset.run()'s delete path;
    # JOBBOT_OFFLINE is a hard lock at the network layer (core/tele.py). Two
    # layers, because either one could be walked around by a future test.
    gia = tempfile.mkdtemp(prefix="jobbot-test-")
    (Path(gia) / "config").mkdir(parents=True, exist_ok=True)
    moi_truong = {**os.environ, "JOBBOT_ROOT": gia, "JOBBOT_OFFLINE": "1"}

    for path in files:
        done = subprocess.run([sys.executable, str(path)], env=moi_truong,
                              capture_output=True, text=True, cwd=HERE.parent)
        out = done.stdout + done.stderr
        found = SUMMARY.search(out)

        if not found:
            print(f"  {path.name:<{width}}  NO SUMMARY LINE (exit {done.returncode})")
            print("\n".join("      " + line for line in out.strip().splitlines()[-8:]))
            broken += 1
            continue

        n_ok, n_fail = int(found.group(1)), int(found.group(2))
        total_ok += n_ok
        total_fail += n_fail

        note = ""
        if n_fail and done.returncode == 0:
            # this is exactly the test_browser.py bug: failures reported as success
            note = "  <-- FAILURES BUT EXITED 0 (missing sys.exit?)"
            broken += 1
        elif not n_fail and done.returncode != 0:
            note = f"  <-- 0 failures but exited {done.returncode}"
            broken += 1

        mark = "ok  " if not n_fail and done.returncode == 0 else "BROKEN"
        print(f"  {mark} {path.name:<{width}}  {n_ok:>3} ok, {n_fail} fail{note}")
        if n_fail:
            for line in out.splitlines():
                if line.lstrip().startswith("FAIL"):
                    print("       " + line.strip())

    # After the run, the user's files have to be untouched. A test that
    # touches one FAILS THE WHOLE RUN — even with every check green.
    sau = _dau_van_tay()
    dung = [t for t in CANH if truoc[t] != sau[t]]
    for ten in dung:
        cu_co, moi_co = truoc[ten] is not None, sau[ten] is not None
        sao = ("was DELETED" if cu_co and not moi_co else
               "was CREATED" if moi_co and not cu_co else "was MODIFIED")
        print(f"  BROKEN  the user file {ten} {sao} during the test run")
        broken += 1

    print(f"\n{len(files)} files · {total_ok} ok · {total_fail} fail"
          + (f" · {broken} files with a problem of their own" if broken else ""))
    return 1 if (total_fail or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
