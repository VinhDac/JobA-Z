"""Chạy TOÀN BỘ bài test bằng một lệnh, và không tin bài test nào cả.

    python3 tests/run_all.py

Vì sao cần: mỗi file test là một script tự chạy, không có runner nào. Hậu quả
thật là test_browser.py quên mất dòng sys.exit — nó in "48 ok, 0 fail" rồi
thoát 0 dù có hỏng bao nhiêu đi nữa, và vòng lặp chạy-rồi-xem-mã-thoát không
đời nào phát hiện ra.

Nên ở đây kiểm CẢ HAI phía, và bên nào cũng phải khớp:
    · mã thoát phải là 0
    · dòng tổng kết cuối phải nói 0 fail
    · phải CÓ dòng tổng kết — im lặng không phải là đạt
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

# TỆP CỦA NGƯỜI DÙNG — chạy test KHÔNG được đụng tới, dù chỉ một byte.
#
# Đây không phải lo xa. Ngày 12/09 bài test đường "làm lại từ đầu" XOÁ thật
# config/config.toml của Vin ở mọi lần chạy, và một bài khác ghi đè địa chỉ
# giả "a@b.c" vào đó — nuốt mất app password Gmail anh vừa dán. Cả hai đều
# xanh lè, vì không bài test nào canh chính bài test.
CANH = ("config/config.toml", "config/boards.toml", "config/companies.toml",
        "config/profile.seed.json")


def _dau_van_tay() -> dict:
    """Băm mấy tệp người dùng. Không đọc nội dung ra đâu cả — trong đó có
    app password."""
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
        print("không tìm thấy file test nào")
        return 1

    width = max(len(f.name) for f in files)
    total_ok = total_fail = broken = 0
    truoc = _dau_van_tay()

    # BÀI TEST CHẠY TRONG MỘT THẾ GIỚI KHÔNG CÓ BÍ MẬT CỦA AI CẢ.
    #
    # Trước đây không truyền env nào, mà dấu vân tay ở trên chỉ canh việc GHI
    # đè tệp người dùng — không canh việc ĐỌC. Hậu quả đo được: từ lúc nối
    # Telegram, mỗi lượt chạy test gửi tin THẬT về điện thoại người dùng,
    # trong đó có báo động giả "⚠️ Phiên hỏng" do chính bài test dựng ra. Và
    # năm bài khẳng định "chưa nối bot" thì đỏ — đỏ vì máy này có cấu hình,
    # không phải vì code sai.
    #
    # JOBBOT_ROOT chuyển hướng config/ VÀ đường xoá của reset.run();
    # JOBBOT_OFFLINE là khoá cứng ở tầng mạng (core/tele.py). Hai lớp, vì
    # lớp nào cũng có thể bị một bài test tương lai đi vòng.
    gia = tempfile.mkdtemp(prefix="jobbot-test-")
    (Path(gia) / "config").mkdir(parents=True, exist_ok=True)
    moi_truong = {**os.environ, "JOBBOT_ROOT": gia, "JOBBOT_OFFLINE": "1"}

    for path in files:
        done = subprocess.run([sys.executable, str(path)], env=moi_truong,
                              capture_output=True, text=True, cwd=HERE.parent)
        out = done.stdout + done.stderr
        found = SUMMARY.search(out)

        if not found:
            print(f"  {path.name:<{width}}  KHÔNG CÓ DÒNG TỔNG KẾT (thoát {done.returncode})")
            print("\n".join("      " + line for line in out.strip().splitlines()[-8:]))
            broken += 1
            continue

        n_ok, n_fail = int(found.group(1)), int(found.group(2))
        total_ok += n_ok
        total_fail += n_fail

        note = ""
        if n_fail and done.returncode == 0:
            # đây chính là lỗi test_browser.py: hỏng mà vẫn báo thành công
            note = "  <-- CÓ HỎNG MÀ VẪN THOÁT 0 (thiếu sys.exit?)"
            broken += 1
        elif not n_fail and done.returncode != 0:
            note = f"  <-- 0 hỏng mà thoát {done.returncode}"
            broken += 1

        mark = "ok  " if not n_fail and done.returncode == 0 else "HỎNG"
        print(f"  {mark} {path.name:<{width}}  {n_ok:>3} ok, {n_fail} fail{note}")
        if n_fail:
            for line in out.splitlines():
                if line.lstrip().startswith("FAIL"):
                    print("       " + line.strip())

    # Chạy xong, mấy tệp của người dùng phải y nguyên. Bài test nào đụng vào
    # thì HỎNG CẢ LƯỢT — kể cả khi mọi câu check đều xanh.
    sau = _dau_van_tay()
    dung = [t for t in CANH if truoc[t] != sau[t]]
    for ten in dung:
        cu_co, moi_co = truoc[ten] is not None, sau[ten] is not None
        sao = ("bị XOÁ" if cu_co and not moi_co else
               "bị TẠO ra" if moi_co and not cu_co else "bị SỬA")
        print(f"  HỎNG  tệp người dùng {ten} {sao} trong lúc chạy test")
        broken += 1

    print(f"\n{len(files)} file · {total_ok} ok · {total_fail} fail"
          + (f" · {broken} file có vấn đề về chính nó" if broken else ""))
    return 1 if (total_fail or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
