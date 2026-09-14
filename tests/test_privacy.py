"""Dữ liệu cá nhân KHÔNG được nằm trong mã nguồn.

Repo này công khai trên GitHub. Bản trước để thẳng trong mã: họ tên, SỐ ĐIỆN
THOẠI THẬT, cả hai địa chỉ email, học vấn kèm điểm, và TOÀN VĂN CV — trong
`scripts/seed_profile.py` và ba tệp test. Số điện thoại trên repo công khai là
thứ bot quét về để spam SMS và lừa đảo.

Bài này đọc hồ sơ ĐANG SỐNG trong DB rồi dò từng tệp git theo dõi. Nó không in
giá trị nào ra — chỉ nói tệp nào dính, vì bản thân dòng log cũng đi vào CI.

    python3 tests/test_privacy.py
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = Path(__file__).resolve().parent.parent
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ok   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}{' — ' + extra if extra else ''}")


def tracked() -> list[Path]:
    """Tệp SẼ lên GitHub: đang theo dõi, CỘNG tệp mới chưa bị ignore.

    Chỉ lấy `ls-files` là hụt: một tệp tạo hôm nay chưa được theo dõi, nhưng
    `git add .` ngày mai là nó lên. Đo được — bài canh này lúc đầu bỏ sót đúng
    một tệp như vậy.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files",
             "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    return [ROOT / line for line in out.stdout.split() if line]


def secrets() -> dict[str, str]:
    """Những chuỗi KHÔNG được có trong mã. Lấy từ hồ sơ đang sống, không viết
    cứng ở đây — viết cứng là chính bài test làm rò.

    ĐỌC HỒ SƠ THẬT, CỐ Ý BỎ QUA SANDBOX. Bộ chạy chung (run_all.py) trỏ
    JOBBOT_ROOT vào thư mục giả để không bài nào chạm được bí mật — đúng cho
    mọi bài, TRỪ bài này: việc của nó chính là "bí mật thật của tôi có lọt
    vào tệp git theo dõi không". Chạy trong sandbox thì nó dò 0 chuỗi và
    vẫn báo xanh — một máy dò rò rỉ tự rỗng ruột.
    """
    giu = {k: os.environ.pop(k, None)
           for k in ("JOBBOT_ROOT", "JOBBOT_DATA_DIR")}
    out = {}
    try:
        from jobbot.core import db
        from jobbot.profile import store
        from jobbot.track import mail
        answers = store.load(db.connect())
        out["số điện thoại"] = str(answers.get("phone") or "")
        out["email hồ sơ"] = str(answers.get("email") or "")
        out["app password"] = mail.account()[1]
    except Exception:                                # noqa: BLE001
        pass
    finally:
        for k, v in giu.items():
            if v is not None:
                os.environ[k] = v
    return {k: v for k, v in out.items() if v and len(v) >= 8}


def co_bi_mat_that() -> bool:
    """Trên máy này CÓ bí mật thật để mà dò không? Đọc thẳng tệp cấu hình.

    Dùng để phân biệt hai chuyện trông giống hệt nhau: "máy sạch, không có gì
    để dò" (hợp lệ) và "máy dò hỏng nên không thấy gì" (phải ĐỎ).
    """
    tep = ROOT / "config" / "config.toml"
    if not tep.is_file():
        return False
    import re as _re
    return bool(_re.search(r"^\s*(app_password|password|token)\s*=\s*[\"']?\S",
                           tep.read_text(encoding="utf-8", errors="replace"),
                           _re.I | _re.M))


print("\n[dữ liệu cá nhân không được lên GitHub]")
files = tracked()
check("đọc được danh sách tệp git theo dõi", bool(files), f"{len(files)} tệp")

marks = secrets()

# Hồ sơ TRỐNG là trạng thái hợp lệ (người dùng mới, hoặc vừa xoá làm lại) —
# lúc đó không có gì để rò, nên không được coi là hỏng. Nhưng cũng KHÔNG được
# pass rỗng: máy dò phải tự chứng minh nó chạy được bằng một chuỗi mồi chắc
# chắn có thật trong tệp git theo dõi. Thiếu dòng này thì một hôm hàm đọc tệp
# hỏng, bài test quét 0 tệp và vẫn xanh.
def _dinh(needle: str) -> list[str]:
    got = []
    for path in files:
        try:
            if needle in path.read_text(encoding="utf-8", errors="ignore"):
                got.append(str(path.relative_to(ROOT)))
        except OSError:
            pass
    return got

check("máy dò chạy được (tìm ra chuỗi mồi)", bool(_dinh("jobbot")))
# MÁY SẠCH khác MÁY DÒ HỎNG. Hai chuyện này trông giống hệt nhau từ ngoài —
# cả hai đều "không tìm thấy gì" — nên phải tách bằng một câu hỏi khác:
# trên đĩa CÓ bí mật thật không. Có mà dò ra 0 mục thì chính máy dò hỏng.
_co = co_bi_mat_that()
check(f"có {len(marks)} mục để dò" + ("" if marks else " — máy này chưa cấu hình"),
      bool(marks) or not _co)
if _co and not marks:
    check("MÁY DÒ HỎNG: config.toml có bí mật mà không đọc ra mục nào", False)

for what, needle in marks.items():
    hits = _dinh(needle)
    # KHÔNG in giá trị — chỉ in tên tệp dính.
    check(f"{what} không nằm trong tệp nào", not hits, " · ".join(hits))

# Tệp chứa bí mật phải bị git bỏ qua, không phải "tình cờ chưa commit".
for name in ("config/config.toml", "config/profile.seed.json", "data/jobbot.db"):
    done = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", name],
                          capture_output=True)
    check(f"{name} đã gitignore", done.returncode == 0)

# Và chưa từng lọt vào lịch sử.
for name in ("config/config.toml", "config/profile.seed.json"):
    log = subprocess.run(["git", "-C", str(ROOT), "log", "--oneline", "--all", "--", name],
                         capture_output=True, text=True)
    check(f"{name} chưa từng bị commit", not log.stdout.strip())

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
