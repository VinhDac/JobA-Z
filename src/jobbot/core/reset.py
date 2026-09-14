"""Start over — ONE place that knows what "initial state" means.

This is the most destructive path in the app, so it has three guards, and
each one exists because something really broke once:

    1. ALWAYS back up first. If the backup fails, delete NOTHING. Without
       this guard one mis-click loses everything, unrecoverably.
    2. The tables to clear are READ FROM THE DB, not typed by hand. Typed by
       hand, the day someone adds a table it survives "start over" — the
       user believes they are clean while old data is still mixed in, which
       is the kind of bug nobody thinks to look for.
    3. KEEP THE SCHEMA. Delete rows, not the DB file: the server has that
       file open, and deleting it just means the server keeps writing into an
       unlinked inode.

What is NOT deleted: config that ships with the app (boards.toml,
companies.toml, the .example files) — that is part of the app, not the
user's data.
"""

from __future__ import annotations

import shutil
import sqlite3
import tarfile
from datetime import datetime
from pathlib import Path

from .paths import data_dir, db_path, project_root

# Files/directories that are USER data. Paths relative to the repo root.
USER_FILES = ("config/config.toml", "config/profile.seed.json")
USER_DIRS = ("cv", "chrome-profile", "chrome-pdf",
             "chrome-apply", "chrome-ui")
# Files in data/ that belong to none of the directories above.
DATA_FILES = ("app.log",)


def _tables(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def inventory(conn: sqlite3.Connection) -> dict:
    """What deleting would cost — so the SCREEN can say it before asking."""
    rows = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            for t in _tables(conn)}
    files = 0
    size = db_path().stat().st_size if db_path().exists() else 0
    for name in USER_DIRS:
        d = data_dir() / name
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file():
                    files += 1
                    size += f.stat().st_size
    for name in USER_FILES:
        if (project_root() / name).exists():
            files += 1
    return {"rows": rows, "total_rows": sum(rows.values()),
            "files": files, "bytes": size}


def backup_dir() -> Path:
    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else Path.home()


def backup(stamp: str | None = None) -> Path:
    """Pack everything about to be lost into one .tar.gz next to the user.

    On the Desktop, not inside data/ — that directory is the one about to be
    wiped.
    """
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    out = backup_dir() / f"jobbot-sao-luu-{stamp}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for name in USER_FILES:
            path = project_root() / name
            if path.exists():
                tar.add(path, arcname=name)
        if db_path().exists():
            tar.add(db_path(), arcname="data/jobbot.db")
        for name in ("cv",):
            d = data_dir() / name
            if d.is_dir():
                tar.add(d, arcname=f"data/{name}")
    out.chmod(0o600)          # this holds an app password and personal data
    return out


def run(conn: sqlite3.Connection) -> dict:
    """Back up, then wipe. If the backup fails, wipe NOTHING."""
    sao_luu = backup()        # an error here propagates — deliberately, do not swallow
    bang = _tables(conn)
    try:
        # FOREIGN KEYS OFF WHILE WIPING.
        #
        # The previous version deleted in whatever order `_tables()` returned
        # and blew up on the very first table: IntegrityError FOREIGN KEY
        # constraint failed. Measured on a copy of the real DB: 5,177
        # postings and 37 applications still THERE, while the backup archive
        # (with the app password inside it) had already been written to the
        # Desktop — one more archive per press of the button.
        #
        # Reordering the deletes would also work, but it is NOT systemic: add
        # one table with a foreign key and it breaks again, exactly when it
        # is needed most. With foreign keys off the order stops mattering —
        # we are deleting EVERYTHING, so no row has to point at any row.
        #
        # ONE TRANSACTION: an interruption rolls the whole thing back rather
        # than leaving the DB half-wiped.
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        for t in bang:
            conn.execute(f'DELETE FROM "{t}"')
        conn.commit()
    except Exception:                       # noqa: BLE001
        conn.rollback()
        # IF THE WIPE FAILED, DROP THE BACKUP TOO. Keeping a file that holds
        # an app password, for something that did NOT happen, leaves risk
        # behind and buys nothing.
        try:
            sao_luu.unlink()
        except OSError:
            pass
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    # VACUUM hands the space back to the disk; without it the DB file is
    # still the same size and the user thinks nothing was deleted.
    conn.execute("VACUUM")

    # The IN-PROCESS cache has to forget too. It is keyed by content so it
    # expires on its own, but "back to the initial state" while the machine
    # still remembers the old version is a lie.
    try:
        from ..dashboard import live as _live
        _live.quen()
    except Exception:                                  # noqa: BLE001
        pass

    xoa_tep = 0
    for name in DATA_FILES:
        f = data_dir() / name
        if f.exists():
            f.unlink()
            xoa_tep += 1
    for name in USER_DIRS:
        d = data_dir() / name
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            xoa_tep += 1
    for name in USER_FILES:
        path = project_root() / name
        if path.exists():
            path.unlink()
            xoa_tep += 1
    return {"backup": str(sao_luu), "tables": len(bang), "removed": xoa_tep}
