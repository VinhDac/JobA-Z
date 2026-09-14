"""Paths — must behave identically on macOS / Windows / Linux.

Rule: never join paths by string concatenation. Only pathlib.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent      # src/jobbot


def project_root() -> Path:
    """The repo root — where config/ and data/ live.

    OVERRIDABLE with JOBBOT_ROOT, and that is not a convenience: `reset.run()`
    deletes `config/config.toml` down this path. A hardcoded constant means
    every test of the destructive path deletes the real file.
    """
    override = os.environ.get("JOBBOT_ROOT")
    return Path(override).expanduser() if override else PACKAGE_DIR.parent.parent


# The old name, kept for places that only need a path at import time. Do NOT
# use it on a destructive path — that code must call project_root() so it can
# still be redirected.
PROJECT_ROOT = PACKAGE_DIR.parent.parent


def data_dir() -> Path:
    """Where the DB and caches live. Override with JOBBOT_DATA_DIR."""
    override = os.environ.get("JOBBOT_DATA_DIR")
    path = Path(override).expanduser() if override else project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "jobbot.db"


def web_dir() -> Path:
    return PACKAGE_DIR / "dashboard" / "web"
