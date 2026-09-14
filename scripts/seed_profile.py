#!/usr/bin/env python3
"""Load the profile into the DB.  Run:  python3 scripts/seed_profile.py

Safe to rerun — each run makes a new version and overwrites no history.

THE DATA LIVES OUTSIDE THE CODE, in `config/profile.seed.json` (gitignored).

Why: this repo is public on GitHub, and an earlier version put the full name, a
REAL PHONE NUMBER, education with grades, certifications and THE WHOLE CV
straight into the source. A phone number in a public repo is what bots harvest
for spam and fraud. Personal data does not belong in source code.

Copy `config/profile.seed.example.json` to `config/profile.seed.json` and fill
it in.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db
from jobbot.profile import store

SEED = Path(__file__).resolve().parent.parent / "config" / "profile.seed.json"


def load_seed() -> dict:
    """Read the profile from the outside file. With no file, say how to make one."""
    if not SEED.exists():
        raise SystemExit(
            f"There is no {SEED} yet.\n"
            f"Copy {SEED.with_name('profile.seed.example.json')} and fill it in.")
    return json.loads(SEED.read_text(encoding="utf-8"))


# ------------------------------------------------------------ [left blank]
# visa_expiry    — the Graduate visa expiry date. Not supplied. A REAL DEADLINE.
# sponsor_future — whether a sponsoring employer will be needed later. The user decides.
# email          — not supplied.
# available_from — depends on the official MSc end date.
# urgency        — only the user knows.
# salary_floor   — only the user knows.
# skills_strong / skills_weak — have to be taken from the full CV, not yet available.
MUST_ASK = ["visa_expiry", "sponsor_future", "email", "available_from",
            "urgency", "salary_floor", "skills_strong"]


def main() -> int:
    seed = load_seed()
    conn = db.connect()
    version = store.save(conn, seed, note="seed: profile from config/profile.seed.json")
    answers = store.load(conn)

    print(f"\n  Loaded — version {version}\n")
    print(f"  {len(seed)} answers from {SEED.name}")
    print(f"  {len(MUST_ASK)} answers NOT guessed — you have to fill them in yourself\n")

    missing = store.missing_for_ingest(answers)
    if missing:
        print(f"  NOTHING CAN BE SEARCHED YET. Still missing: {', '.join(missing)}")
    else:
        print("  There is enough to start searching.")
    print()
    print("  Still for you to fill in:")
    for qid in MUST_ASK:
        print(f"     - {qid}")
    print()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
