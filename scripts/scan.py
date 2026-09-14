#!/usr/bin/env python3
"""One scan, run by hand.

    python3 scripts/scan.py               API + Chrome, deep-reading every posting
    python3 scripts/scan.py --shallow     Chrome takes the list only, opening no posting
    python3 scripts/scan.py --no-chrome   the API sources only

The background app calls this very function on a schedule — see
src/jobbot/core/scheduler.py. READ ONLY; nothing is sent anywhere. Safe to rerun
as often as you like (it caches).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.scan_runner import run_scan


def main() -> int:
    # --pages went with arbeitnow/remotive: the sources left are the company boards
    # (taken whole, with no paging) and LinkedIn (a fixed page count, set in
    # ingest/web/linkedin.py).
    chrome = "--no-chrome" not in sys.argv
    deep = "--shallow" not in sys.argv

    print("\nScanning the sources\n")
    # manual=True: a person pressed this, so the waking-hours window does not apply
    result = run_scan(log=print, chrome_sources=chrome, deep=deep, manual=True)
    if not result["ok"]:
        print(f"\n{result['summary']}: {result.get('missing')}")
        return 1
    print(f"\nTotal: {result['summary']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
