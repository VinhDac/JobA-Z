"""Hai luật nền CHƯA CÓ AI CANH — và chỗ canh năm luật còn lại.

Bảy luật dựng nên app này. Năm cái đã có bài canh thật; hai cái thì không, và
đúng hai cái đó là thứ người ngoài đọc README sẽ tin ngay:

    1  KHÔNG LLM                      -> canh ở ĐÂY
    2  Câu chữ trên CV là của Vin     -> tests/test_cv.py
    3  Hộp thư CHỈ ĐỌC                -> tests/test_track.py
    4  Máy KHÔNG bấm Gửi              -> tests/test_apply.py
    5  Bí mật chỉ nằm trong config    -> tests/test_privacy.py
    6  Bị chặn thì DỪNG               -> tests/test_browser.py
    7  Hỏng thì phải KÊU              -> rải khắp, rõ nhất ở test_journal.py

    + KHÔNG PHỤ THUỘC (chỉ thư viện chuẩn)  -> canh ở ĐÂY

Luật không có bài canh thì nó là một câu trong README, không phải một luật.

    python3 tests/test_luat.py
"""

import ast
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ok   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}{' — ' + extra if extra else ''}")


NGUON = sorted((ROOT / "src").rglob("*.py"))


def khong_chu_thich(text: str) -> str:
    """Bỏ dòng chú thích. Canh THỨ ĐANG CHẠY, không canh chữ trong chú thích —
    dòng chú thích kể lại cái đã bỏ là dòng đáng giữ nhất."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


# ---------------------------------------------------------------------------
print("[LUẬT: KHÔNG PHỤ THUỘC — chỉ thư viện chuẩn]")
# README hứa "không cần cài gì thêm, không venv". Một dòng `import requests`
# lọt vào là lời hứa đó chết, mà nó chết ÂM THẦM: máy đang dựng thì có sẵn
# gói đó, chỉ máy người khác mới nổ.

# PyObjC là NGOẠI LỆ DUY NHẤT, và nó phải là ngoại lệ CÓ ĐƯỜNG LÙI: mỗi chỗ
# dùng đều nằm sau một lớp bọc, thiếu nó thì app vẫn chạy (cửa sổ Chrome thay
# cửa sổ macOS, bóc PDF bằng tay thay PDFKit).
COCOA = {"objc", "AppKit", "Foundation", "PyObjCTools", "WebKit", "Quartz"}

ngoai: dict[str, set[str]] = {}
for f in NGUON:
    cay = ast.parse(io.open(f, encoding="utf-8").read(), str(f))
    for n in ast.walk(cay):
        if isinstance(n, ast.Import):
            for a in n.names:
                ngoai.setdefault(a.name.split(".")[0], set()).add(f.name)
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            ngoai.setdefault(n.module.split(".")[0], set()).add(f.name)

chuan = set(sys.stdlib_module_names)
la = {k: v for k, v in ngoai.items() if k not in chuan and k != "jobbot"}
ngoai_le = {k: v for k, v in la.items() if k in COCOA}
cam = {k: v for k, v in la.items() if k not in COCOA}
check(f"không gói ngoài nào ({len(ngoai)} module được nạp)", not cam,
      ", ".join(f"{k} ({', '.join(sorted(v))})" for k, v in sorted(cam.items())))
check("PyObjC vẫn là ngoại lệ duy nhất", set(ngoai_le) <= COCOA)

# Và ngoại lệ đó phải CÓ ĐƯỜNG LÙI: không tệp nào nạp Cocoa ở mức module rồi
# được import vô điều kiện. app.py nạp ở mức module, nên chỗ gọi nó
# (__main__.py) phải bọc try.
mac_module = sorted({f for v in ngoai_le.values() for f in v})
check(f"đúng những tệp đã biết mới chạm Cocoa ({', '.join(mac_module)})",
      set(mac_module) <= {"app.py", "shell.py", "import_cv.py"},
      str(mac_module))
_mainpy = khong_chu_thich((ROOT / "src/jobbot/__main__.py").read_text(encoding="utf-8"))
check("và __main__ bọc app.py trong try, thiếu PyObjC vẫn chạy",
      "from .app import run" in _mainpy
      and "except (ImportError, AttributeError)" in _mainpy)
_shell = khong_chu_thich((ROOT / "src/jobbot/shell.py").read_text(encoding="utf-8"))
check("shell.has_mac_native() hỏi thử rồi mới kết luận",
      "import objc" in _shell and "except Exception" in _shell)
_icv = khong_chu_thich((ROOT / "src/jobbot/profile/import_cv.py").read_text(encoding="utf-8"))
check("bóc PDF thiếu PyObjC thì lùi về bóc tay",
      "_pdf_plain" in _icv and "except Exception" in _icv)

# run.py và scripts/ cũng phải sạch — chúng là thứ người dùng gõ đầu tiên.
for _p in [ROOT / "run.py"] + sorted((ROOT / "scripts").glob("*.py")):
    _cay = ast.parse(io.open(_p, encoding="utf-8").read(), str(_p))
    _la = set()
    for n in ast.walk(_cay):
        if isinstance(n, ast.Import):
            _la |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            _la.add(n.module.split(".")[0])
    _la -= chuan | {"jobbot"} | COCOA
    check(f"{_p.name} không cần gói ngoài", not _la, str(sorted(_la)))


# ---------------------------------------------------------------------------
print("\n[LUẬT: KHÔNG LLM — không mô hình ngôn ngữ, không gọi ai chấm hộ]")
# Cả app không có LLM, và đó là quyết định chứ không phải thiếu sót: mọi câu
# chữ trên CV là của Vin, mọi điểm số đều truy ra được một dòng luật. Một lời
# gọi API ở đâu đó là cả hai điều trên hết đúng, và không ai đọc ra được.
# CẤM THEO MẶT API, KHÔNG CẤM THEO TÊN CÔNG TY. Cohere, Anthropic, Mistral,
# OpenAI đều là NHÀ TUYỂN DỤNG — tên họ nằm trong danh sách board và sẽ nằm
# trong dữ liệu việc làm. Cấm cái tên thì bài test đỏ vì một công ty đăng
# tuyển, và người sửa sẽ học được đúng một điều: tắt bài test này đi.
DAU_LLM = ("api.openai.com", "api.anthropic.com", "api.cohere",
           "api.mistral", "generativelanguage.googleapis.com",
           "api-inference.huggingface", "openrouter.ai", "api.together.xyz",
           "chat/completions", "/v1/completions", "/v1/messages",
           "llama_cpp", "sentence_transformers", "ollama")
for f in NGUON:
    than = khong_chu_thich(f.read_text(encoding="utf-8")).lower()
    dinh = [d for d in DAU_LLM if d in than]
    if dinh:
        check(f"{f.name} không gọi mô hình nào", False, ", ".join(dinh))
check(f"không tệp nào trong src/ chạm mặt API của mô hình ({len(NGUON)} tệp)", True)
# CHỐT MẠNH NHẤT nằm ở luật trên: không gói ngoài nào được phép, nên KHÔNG
# CÓ SDK nào của bất kỳ nhà cung cấp mô hình nào tồn tại được trong app này.
# Hai luật khoá lẫn nhau, và đó là lý do luật "không phụ thuộc" đáng canh.
check("và không SDK mô hình nào lọt vào được (luật không-phụ-thuộc khoá)",
      not {"openai", "anthropic", "cohere", "mistralai", "google",
           "transformers", "torch", "llama_cpp"} & set(ngoai))

# MẠNH HƠN MỘT DANH SÁCH CẤM: liệt kê MỌI máy chủ app gọi ra ngoài. Danh sách
# cấm chỉ bắt được cái mình nghĩ ra; danh sách CHO PHÉP bắt cả cái chưa nghĩ
# tới — thêm một nhà cung cấp mới là bài này đỏ, dù tên nó chưa ai biết.
import re as _re
CHO_PHEP = {
    "127.0.0.1",                     # chính máy này
    "localhost",
    "www.linkedin.com", "linkedin.com",   # nguồn tin (đọc, đã đăng nhập tay)
    "boards-api.greenhouse.io", "api.lever.co", "api.ashbyhq.com",  # ATS công khai
    "api.telegram.org",              # báo về điện thoại
    "github.com",                    # chỉ là chữ mẫu trong ô hồ sơ
}
thay = set()
for f in NGUON:
    for u in _re.findall(r"https?://([A-Za-z0-9._~%-]+)",
                         khong_chu_thich(f.read_text(encoding="utf-8"))):
        thay.add(u.lower())
la_mat = sorted(thay - CHO_PHEP)
check(f"chỉ gọi ra {len(thay)} máy chủ, đều đã khai", not la_mat, str(la_mat))

# IMAP không đi qua http:// nên regex trên không thấy. Và hộp thư là chỗ
# riêng tư nhất, nên máy chủ KHÔNG được đóng cứng vào một nhà cung cấp: bản
# cũ ghi thẳng "imap.gmail.com", kèm một bộ lọc chỉ nhận app password của
# Google — ai dùng Outlook/iCloud/hộp thư công ty thì bị chặn ngay cửa, bằng
# một câu chẳng liên quan gì tới lý do thật.
from jobbot.track import mail as _ml
check("máy chủ thư suy từ tên miền, không đóng cứng Gmail",
      _ml.may_chu("x@outlook.com") == "outlook.office365.com")
check("tên miền lạ vẫn thử được quy ước imap.<tên miền>",
      _ml.may_chu("x@congty.co.uk") == "imap.congty.co.uk")
check("nhà cung cấp không nói IMAP ra ngoài thì NÓI THẲNG, không đoán bừa",
      _ml.may_chu("x@proton.me") == "")
check("và config.toml đè được tất cả", "host" in
      khong_chu_thich((ROOT / "config/config.example.toml").read_text(encoding="utf-8")))
check("bộ lọc app password chỉ áp cho Google",
      _ml._la_google("imap.gmail.com") and not _ml._la_google("outlook.office365.com"))

# KHOÁ MẠNG lúc chạy thử — một công tắc cho CẢ HAI đường ra ngoài. Bộ test
# từng nhắn tin thật về điện thoại mỗi lần chạy; IMAP là đường thứ hai.
_srcmail = khong_chu_thich((ROOT / "src/jobbot/track/mail.py").read_text(encoding="utf-8"))
check("IMAP cũng nghe JOBBOT_OFFLINE như Telegram", "khoa_mang()" in _srcmail)
check("và chốt đó đặt TRƯỚC lúc mở socket",
      _srcmail.index("khoa_mang()") < _srcmail.index("IMAP4_SSL(host"))

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
