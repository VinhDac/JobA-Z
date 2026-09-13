"""Làm lại từ đầu — MỘT chỗ biết "trạng thái ban đầu" nghĩa là gì.

Đây là đường phá hoại mạnh nhất trong app, nên nó có ba chốt, và cả ba đều
do một lần làm hỏng thật mà có:

    1. LUÔN sao lưu trước. Sao lưu hỏng thì KHÔNG xoá. Không có chốt này thì
       một cú bấm nhầm là mất hết, không lấy lại được.
    2. Bảng cần dọn ĐỌC TỪ DB, không gõ tay. Gõ tay thì hôm nào thêm bảng mới
       là bảng đó sống sót qua "làm lại từ đầu" — người dùng tưởng sạch mà
       vẫn còn dữ liệu cũ lẫn vào, đây là kiểu lỗi không ai ngờ tới.
    3. Giữ nguyên SCHEMA. Xoá dòng chứ không xoá tệp DB: server đang mở tệp
       đó, xoá tệp thì nó vẫn ghi tiếp vào inode đã bị gỡ tên.

Thứ KHÔNG xoá: cấu hình đi kèm app (boards.toml, companies.toml, các tệp
.example) — đó là phần của app, không phải dữ liệu người dùng.
"""

from __future__ import annotations

import shutil
import sqlite3
import tarfile
from datetime import datetime
from pathlib import Path

from .paths import data_dir, db_path, project_root

# Tệp/thư mục là dữ liệu NGƯỜI DÙNG. Đường dẫn tương đối so với gốc repo.
USER_FILES = ("config/config.toml", "config/profile.seed.json")
USER_DIRS = ("cv", "chrome-profile", "chrome-pdf",
             "chrome-apply", "chrome-ui")
# Tệp trong data/ không thuộc thư mục nào ở trên.
DATA_FILES = ("app.log",)


def _tables(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def inventory(conn: sqlite3.Connection) -> dict:
    """Xoá đi sẽ mất những gì — để MÀN HÌNH nói ra trước khi hỏi."""
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
    """Gói mọi thứ sắp mất vào một tệp .tar.gz cạnh người dùng.

    Để ở Desktop chứ không để trong data/ — chỗ đó chính là chỗ sắp bị dọn.
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
    out.chmod(0o600)          # trong này có app password và dữ liệu cá nhân
    return out


def run(conn: sqlite3.Connection) -> dict:
    """Sao lưu rồi dọn sạch. Sao lưu hỏng thì KHÔNG dọn gì cả."""
    sao_luu = backup()        # lỗi ở đây là ném ra ngoài — cố ý, đừng nuốt
    bang = _tables(conn)
    for t in bang:
        conn.execute(f'DELETE FROM "{t}"')
    conn.commit()
    # VACUUM trả lại chỗ trống cho đĩa; không có nó thì tệp DB vẫn to như cũ
    # và người dùng tưởng chưa xoá được gì.
    conn.execute("VACUUM")

    # Cache TRONG TIẾN TRÌNH cũng phải quên. Nó khoá theo nội dung nên tự hết
    # hạn, nhưng "về trạng thái ban đầu" mà máy còn nhớ bản cũ là nói dối.
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
