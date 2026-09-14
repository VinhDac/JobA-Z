#!/usr/bin/env python3
"""Run the app:  python3 run.py

Nothing to install. No venv. Just Python 3.11+.
"""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11 or later is needed. This machine has {sys.version.split()[0]}.")

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from jobbot.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
