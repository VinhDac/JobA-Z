#!/usr/bin/env python3
"""Rebuild THE WHOLE derived layer from the raw layer.

    python3 scripts/rebuild.py

Use it when: the filtering or scoring rules changed, the HTML stripper changed, or
the derived data is suspect. Nothing is lost — the raw layer is never touched.

This is what the old architecture did NOT have: a description existed only in its
stripped form, so one bug in strip_html was permanent damage.
"""

import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db
from jobbot.core.derive import rebuild

if __name__ == "__main__":
    conn = db.connect()
    t0 = time.time()
    print("\nRebuilding from the raw layer\n")
    result = rebuild(conn, log=print)
    print(f"\n  done in {time.time() - t0:.1f}s\n")
