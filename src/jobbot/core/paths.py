"""Đường dẫn — phải chạy giống nhau trên macOS / Windows / Linux.

Luật: không bao giờ ghép đường dẫn bằng chuỗi. Chỉ dùng pathlib.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent      # src/jobbot


def project_root() -> Path:
    """Gốc repo — nơi chứa config/ và data/.

    ĐỔI ĐƯỢC bằng JOBBOT_ROOT, và đó không phải tiện nghi: `reset.run()` xoá
    `config/config.toml` theo đường này. Hằng số cứng nghĩa là mọi lần chạy
    thử đường phá hoại đều xoá đúng tệp thật.
    """
    override = os.environ.get("JOBBOT_ROOT")
    return Path(override).expanduser() if override else PACKAGE_DIR.parent.parent


# Giữ tên cũ cho chỗ nào chỉ cần đường dẫn lúc nạp module. KHÔNG dùng nó ở
# đường phá hoại — chỗ đó phải gọi project_root() để còn chuyển hướng được.
PROJECT_ROOT = PACKAGE_DIR.parent.parent


def data_dir() -> Path:
    """Nơi chứa DB và cache. Đổi được bằng biến môi trường JOBBOT_DATA_DIR."""
    override = os.environ.get("JOBBOT_DATA_DIR")
    path = Path(override).expanduser() if override else project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "jobbot.db"


def web_dir() -> Path:
    return PACKAGE_DIR / "dashboard" / "web"
