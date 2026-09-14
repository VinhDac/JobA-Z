#!/usr/bin/env python3
"""Đóng gói để chuyển sang máy khác.

    python3 scripts/handover.py            đóng gói ra jobbot-handover.zip
    python3 scripts/handover.py --check    chỉ xem sẽ mang gì, không đóng gói

Mang theo: mã nguồn + data/jobbot.db (toàn bộ tin, điểm, hồ sơ, nhật ký).
KHÔNG mang: chrome-profile (311 MB, tự sinh lại, chép sang còn dễ hỏng).
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Chép: mã, cấu hình, tài liệu, test — và ĐÚNG một file dữ liệu.
TAKE_DIRS = ["src", "scripts", "config", "docs", "tests"]
TAKE_FILES = ["run.py", "run.bat", "run-console.bat", "start.command",
              "pyproject.toml", "README.md", ".gitignore"]
TAKE_DATA = ["data/jobbot.db"]

SKIP = {"__pycache__", ".pyc", ".DS_Store", "chrome-profile", "chrome-ui"}

# --- BÍ MẬT KHÔNG BAO GIỜ ĐI THEO ---------------------------------------
#
# Luật nền số 5: app password Gmail và token Telegram chỉ được nằm trong
# config/config.toml (chmod 600, đã gitignore). Một gói zip thì đi qua
# AirDrop, USB, thư, cloud — tức là đi qua đúng những chỗ file 600 tránh.
#
# HAI LỚP, và lớp thứ hai mới là lớp hệ thống:
#   1. chặn theo TÊN những file đã biết
#   2. chặn theo NỘI DUNG: bất kỳ file văn bản nào có dòng gán bí mật.
# Lớp 2 bắt được cả file bí mật CHƯA TỒN TẠI — mai mốt thêm
# config/stripe.toml mà quên khai tên thì nó vẫn không lọt.
CAM_TEN = {"config.toml"}

# Dòng kiểu `app_password = "..."`. Bỏ qua giá trị rỗng và file .example:
# mẫu trống thì không phải bí mật, và mang nó đi mới là có ích.
CAM_NOI_DUNG = re.compile(
    r"^\s*(app_password|password|passwd|token|api_key|apikey|secret|"
    r"client_secret|chat_id)\s*=\s*[\"']?\S", re.I | re.M)

VAN_BAN = {".toml", ".json", ".env", ".ini", ".cfg", ".yaml", ".yml", ".txt"}


def co_bi_mat(path: Path) -> bool:
    """File này có chứa một dòng gán bí mật không."""
    if path.name in CAM_TEN:
        return True
    if "example" in path.name or "seed" in path.name or path.suffix not in VAN_BAN:
        return False
    try:
        return bool(CAM_NOI_DUNG.search(path.read_text(encoding="utf-8",
                                                       errors="replace")))
    except OSError:
        return False


def wanted(path: Path) -> bool:
    return not any(s in str(path) for s in SKIP)


def collect() -> list[Path]:
    out: list[Path] = []
    for name in TAKE_DIRS:
        out += [p for p in (ROOT / name).rglob("*") if p.is_file() and wanted(p)]
    for name in TAKE_FILES + TAKE_DATA:
        path = ROOT / name
        if path.is_file():
            out.append(path)
    # LỌC BÍ MẬT SAU CÙNG, và không có đường nào bỏ qua bước này.
    return sorted(p for p in set(out) if not co_bi_mat(p))


def bi_bo() -> list[Path]:
    """Mấy file bị chặn — để NÓI RA, không bỏ im lặng."""
    o = []
    for name in TAKE_DIRS:
        o += [p for p in (ROOT / name).rglob("*") if p.is_file() and wanted(p)]
    for name in TAKE_FILES + TAKE_DATA:
        if (ROOT / name).is_file():
            o.append(ROOT / name)
    return sorted(p for p in set(o) if co_bi_mat(p))


def human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def main() -> int:
    files = collect()
    total = sum(f.stat().st_size for f in files)

    db = ROOT / "data" / "jobbot.db"
    print(f"\n  {len(files)} file · {human(total)}\n")
    print(f"  DB          {'CÓ — ' + human(db.stat().st_size) if db.is_file() else 'KHÔNG THẤY'}")
    for name in ("chrome-profile", "chrome-ui"):
        path = ROOT / "data" / name
        if path.is_dir():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            print(f"  bỏ lại      {name} ({human(size)}) — tự sinh lại")

    # NÓI RA ĐÃ CHẶN GÌ. Bỏ im lặng thì người dùng bê gói sang máy mới, mở
    # app lên thấy hộp thư không nối, và không biết vì sao — rồi đi tìm lỗi
    # ở chỗ khác. Chặn thì phải kèm việc phải làm.
    chan = bi_bo()
    if chan:
        print()
        for path in chan:
            print(f"  KHÔNG mang  {path.relative_to(ROOT)} — có bí mật trong đó")
        print("  -> sang máy mới: mở Cài đặt, nhập lại app password Gmail và "
              "token Telegram.")

    if "--check" in sys.argv:
        print("\n  (--check: chưa đóng gói gì)\n")
        return 0

    out = ROOT / "jobbot-handover.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(ROOT))

    print(f"\n  -> {out.name}  ({human(out.stat().st_size)})")
    print("\n  Sang máy mới: giải nén, cài Python 3.11+ và Chrome,")
    print("  rồi bấm đúp run.bat (Windows) hoặc chạy python3 run.py.")
    print("  Chi tiết: docs/windows.md\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
