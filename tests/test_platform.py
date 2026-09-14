"""Test phần chạy đa nền tảng — macOS / Windows / Linux.

Bài test này viết TRÊN macOS nhưng phải bảo vệ được đường Windows. Không chạy
thử máy Windows thật được, nên cách kiểm là: ép sys.platform rồi xem code
dựng ra cái gì. Nó không chứng minh Windows chạy được; nó chứng minh code
KHÔNG cắm cứng macOS.

Chỗ nào chỉ có thể thử trên máy thật thì ghi rõ ở đây, đừng giả vờ đã test.

    python3 tests/test_platform.py
"""

import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}{' — ' + extra if extra else ''}")


class platform_is:
    """Ép sys.platform trong một khối, rồi trả lại như cũ."""
    def __init__(self, module, name):
        self.module, self.name = module, name
    def __enter__(self):
        self.old = self.module.sys.platform
        self.module.sys.platform = self.name
        return self
    def __exit__(self, *_):
        self.module.sys.platform = self.old


print("[tìm Chrome: mỗi hệ một chỗ]")
from jobbot.browser import chrome

with platform_is(chrome, "win32"):
    os.environ.setdefault("PROGRAMFILES", r"C:\Program Files")
    win = chrome._candidates()
    check("Windows dò chrome.exe", any(c.endswith("chrome.exe") for c in win))
    check("và cả msedge.exe (Edge cũng là Chromium)",
          any(c.endswith("msedge.exe") for c in win))
    check("KHÔNG dò đường macOS trên Windows",
          not any("/Applications/" in c for c in win))
    check("dò cả chỗ cài cho riêng một tài khoản (LOCALAPPDATA)",
          len(win) > 4)

with platform_is(chrome, "darwin"):
    mac = chrome._candidates()
    check("macOS dò /Applications", all(c.startswith("/Applications/") for c in mac))

with platform_is(chrome, "linux"):
    lin = chrome._candidates()
    check("Linux dò /usr/bin", any(c.startswith("/usr/bin/") for c in lin))

check("không tìm thấy thì báo rõ, không im lặng",
      "ChromeError" in Path("src/jobbot/browser/chrome.py").read_text())


print("\n[thông báo: mỗi hệ một lệnh]")
from jobbot.core import notify

with platform_is(notify, "darwin"):
    cmd = notify.command("jobbot", "5 việc mới", "xem đi")
    check("macOS dùng osascript", cmd[0] == "osascript")

with platform_is(notify, "win32"):
    cmd = notify.command("jobbot", "5 việc mới", "xem đi")
    check("Windows dùng powershell", cmd[0] == "powershell")
    check("không cần cài module ngoài (không BurntToast)",
          "BurntToast" not in cmd[-1])
    # Chuỗi lọt vào lệnh PowerShell phải được rào, y như bài học AppleScript.
    hack = notify.command("a", "'; Remove-Item C:\\ -Recurse; '", "")
    check("nháy đơn trong nội dung bị nhân đôi, không thoát ra được lệnh",
          "''" in hack[-1] and "Remove-Item" in hack[-1])

with platform_is(notify, "linux"):
    check("Linux dùng notify-send",
          notify.command("a", "b")[0] == "notify-send")

check("hệ lạ thì lùi về notify-send, không nổ",
      notify.BUILDERS.get("freebsd13") is None)


print("\n[đọc PDF: không được chỉ chạy trên macOS]")
import zlib
from jobbot.profile import import_cv as ic

def _pdf(lines):
    body = "BT /F1 11 Tf 40 750 Td " + " ".join(
        f"({l}) Tj 0 -14 Td" for l in lines) + " ET"
    st = zlib.compress(body.encode("latin-1"))
    return (b"%PDF-1.4\n4 0 obj<</Length " + str(len(st)).encode()
            + b"/Filter/FlateDecode>>stream\n" + st + b"\nendstream endobj\n%%EOF")

CV = _pdf(["ADA GRACE LOVELACE  London, UK  you@example.com"]
          + ["EXPERIENCE  Analyst at Acme, built pipelines in Python and SQL"] * 4
          + ["EDUCATION  MSc Computational Finance, Royal Holloway 2026"])

with platform_is(ic, "win32"):
    text = ic.from_pdf(CV)
    check("Windows đọc được PDF chữ thường", "ADA GRACE LOVELACE" in text)
    check("và lấy được cả phần dưới", "Computational Finance" in text)
    # Font nhúng bảng mã riêng (LaTeX, Canva) bóc ra là rác. Nhét rác vào hồ
    # sơ còn tệ hơn báo lỗi — người dùng còn đường dán chữ.
    try:
        ic.from_pdf(_pdf(["\x01\x02\x03\x04\x05\x06\x07" * 40]))
        check("PDF font nhúng -> báo lỗi, KHÔNG nhét rác vào hồ sơ", False)
    except ic.ReadError as exc:
        check("PDF font nhúng -> báo lỗi, KHÔNG nhét rác vào hồ sơ", True)
        check("và chỉ đường khác (dán chữ)", "PASTE" in str(exc))

check("nhận ra chữ thật", ic._looks_like_text("Analyst at Acme. " * 20))
check("nhận ra rác", not ic._looks_like_text("\x01\x02\x03\x04" * 80))
check("chuỗi quá ngắn không tính là CV", not ic._looks_like_text("hello"))


print("\n[vỏ cửa sổ]")
from jobbot import shell

with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    with platform_is(shell, "win32"):
        check("Windows KHÔNG dùng vỏ macOS", not shell.has_mac_native())
    # Cửa sổ giao diện phải dùng profile RIÊNG: chung với profile đi cào thì
    # người dùng đóng cửa sổ là giết luôn tab máy đang lái.
    from jobbot.browser import chrome as ch
    check("profile cửa sổ khác profile đi cào",
          shell.ui_profile_dir() != ch.profile_dir())
    src = Path("src/jobbot/shell.py").read_text()
    check("và KHÔNG mở cổng debug ở cửa sổ giao diện",
          "--remote-debugging-port" not in src.split('"""')[2])
    check("mở --app, không phải tab trình duyệt thường", "--app=" in src)
    os.environ.pop("JOBBOT_DATA_DIR", None)


print("\n[đường dẫn: không ghép chuỗi, không cắm cứng dấu /]")
from jobbot.core import paths
src = Path("src/jobbot/core/paths.py").read_text()
check("chỉ dùng pathlib", "Path(" in src and '"/"' not in src)
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    check("đổi được chỗ chứa dữ liệu bằng biến môi trường",
          paths.data_dir() == Path(tmp))
    os.environ.pop("JOBBOT_DATA_DIR", None)


print("\n[lối chạy trên Windows]")
for name in ("run.bat", "run-console.bat"):
    raw = Path(name).read_bytes()
    check(f"{name} có", bool(raw))
    # cmd.exe đọc sai file chỉ có LF — dòng lệnh dính vào nhau.
    check(f"{name} xuống dòng kiểu CRLF", b"\r\n" in raw)
    check(f"{name} chỉ ASCII (cmd.exe mặc định không phải UTF-8)",
          all(b < 128 for b in raw))

run_py = Path("run.py").read_text()
check("run.py chặn Python quá cũ", "3, 11" in run_py)



print("\n[cửa sổ app macOS — ô chọn tệp]")
# WKWebView KHÔNG tự mở được hộp thoại chọn tệp. Thiếu delegate thì
# <input type=file> chết câm: bấm "Choose File" không có gì xảy ra, không lỗi,
# không log — mà trong trình duyệt thường thì cùng trang đó chạy bình thường.
if sys.platform == "darwin":
    try:
        from jobbot.app import Delegate
        _sel = (b"webView:runOpenPanelWithParameters:"
                b"initiatedByFrame:completionHandler:")
        _m = Delegate.webView_runOpenPanelWithParameters_initiatedByFrame_completionHandler_
        check("Delegate có hàm mở hộp thoại chọn tệp", _m.selector == _sel)
        # Chữ ký phải khai tay. Để PyObjC tự suy thì tham số cuối ra "@" chứ
        # không phải "@?" (block) — `handler(...)` gọi vào hư không và ô chọn
        # tệp treo vĩnh viễn.
        check("tham số cuối khai đúng là BLOCK",
              _m.signature.decode().endswith("@?"))
        _src = (Path(__file__).resolve().parent.parent
                / "src/jobbot/app.py").read_text(encoding="utf-8")
        check("và delegate được gắn vào webview", "setUIDelegate_(delegate)" in _src)

        # Đường RA NGOÀI. Tin tuyển dụng nằm ở linkedin.com, greenhouse.io —
        # không có hàm này thì <a target=_blank> bấm vào KHÔNG có gì xảy ra:
        # không lỗi, không log, đúng lớp lỗi hộp chọn tệp đã mắc một lần.
        _sel2 = (b"webView:createWebViewWithConfiguration:"
                 b"forNavigationAction:windowFeatures:")
        _m2 = Delegate.webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_
        check("Delegate có hàm mở đường ra ngoài", _m2.selector == _sel2)
        # Để PyObjC tự suy thì nó nhìn `return None` và kết luận trả về VOID,
        # trong khi WKWebView gọi hàm này để lấy về một WKWebView* — sai kiểu
        # trả về thì runtime đọc rác ở thanh ghi, lúc chạy được lúc không.
        check("kiểu TRẢ VỀ khai là object, không phải void",
              _m2.signature.decode().startswith("@@:"), _m2.signature.decode())
        # Mở ngay trong cửa sổ app là mất luôn dashboard: cửa sổ đó không có
        # thanh địa chỉ, không có nút Back.
        check("đẩy sang trình duyệt mặc định của máy",
              "NSWorkspace.sharedWorkspace().openURL_" in _src)
    except ImportError:
        check("bỏ qua — máy này không có PyObjC", True)
else:
    check("bỏ qua — không phải macOS", True)

print("\n[CÚ PHÁP CHẠY ĐƯỢC TRÊN BẢN PYTHON APP TỰ KHAI]")
# LỖI ĐÃ XẢY RA THẬT, và nó là loại CHỈ HIỆN RA Ở MÁY NGƯỜI KHÁC:
# views/settings.py viết f"...{" on" if x else ""}..." — nháy kép lồng nháy
# kép, tức PEP 701, chỉ hợp lệ TỪ Python 3.12. Máy đang phát triển chạy 3.13
# nên 2.300 phép kiểm đều xanh, trong khi trên macOS sạch (Python 3.9.6) cả
# file không biên dịch nổi: mở tab Cài đặt là app nổ.
#
# Bài này biên dịch MỌI file bằng một trình thông dịch CŨ HƠN. /usr/bin/python3
# luôn có sẵn trên macOS, nên chốt này không đòi cài thêm gì.
import subprocess as _sp
_cu_py = Path("/usr/bin/python3")
if _cu_py.exists():
    _ban = _sp.run([str(_cu_py), "-c",
                    "import sys;print('%d.%d' % sys.version_info[:2])"],
                   capture_output=True, text=True).stdout.strip() or "?"
    _ma = (
        "import io,pathlib\n"
        "h=[]\n"
        "for f in sorted(pathlib.Path('src').rglob('*.py'))+"
        "sorted(pathlib.Path('tests').rglob('*.py'))+[pathlib.Path('run.py')]:\n"
        "    try: compile(io.open(f,encoding='utf-8').read(),str(f),'exec')\n"
        "    except SyntaxError as e: h.append('%s:%s'%(f,e.lineno))\n"
        "print('|'.join(h))\n")
    _ra = _sp.run([str(_cu_py), "-c", _ma], capture_output=True, text=True,
                  cwd=str(Path(__file__).resolve().parent.parent))
    _xau = [x for x in _ra.stdout.strip().split("|") if x]
    check(f"mọi file biên dịch được bằng Python {_ban}"
          + (f" — hỏng: {', '.join(_xau[:3])}" if _xau else ""), not _xau)
else:
    check("bỏ qua — máy này không có /usr/bin/python3", True)

print("\n[ICON APP — vẽ bằng HÌNH, đen trắng, cùng dấu với logo trong app]")
import importlib.util as _il
from pathlib import Path as _P
_goc = _P(__file__).resolve().parent.parent
_spec = _il.spec_from_file_location("make_app", _goc / "scripts/make_app.py")
_ma = _il.module_from_spec(_spec); _spec.loader.exec_module(_ma)
_src = (_goc / "scripts/make_app.py").read_text(encoding="utf-8")

# ĐEN TRẮNG: ba màu phải là xám thuần — ba kênh RGB bằng nhau.
for _ten, _h in (("nền", _ma.NEN), ("vòng", _ma.VONG), ("chìa", _ma.NET)):
    _rgb = [int(_h.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)]
    check(f"màu {_ten} là xám thuần, không ám màu nào",
          _rgb[0] == _rgb[1] == _rgb[2])
check("vòng tròn tương phản hẳn với nền",
      abs(int(_ma.NEN.lstrip('#')[:2], 16) - int(_ma.VONG.lstrip('#')[:2], 16)) > 200)
check("chìa cùng màu nền nên nó là hình CẮT RA khỏi vòng tròn",
      _ma.NET == _ma.NEN)
# VẼ BẰNG HÌNH, KHÔNG BẰNG KÝ TỰ. Bản trước vẽ "◆" bằng font hệ thống: cỡ
# quang học và baseline do font quyết, nên đổi macOS là icon xê dịch và không
# có gì báo.
# Canh THỨ ĐANG CHẠY, không canh chữ trong chú thích: dòng chú thích kể lại
# cái đã bỏ là dòng đáng giữ nhất, cấm nó là cấm nhầm.
_code = "\n".join(l for l in _src.splitlines() if not l.lstrip().startswith("#"))
for _cam in ("NSAttributedString", "NSFont", "drawAtPoint_"):
    check(f"không còn dựa vào «{_cam}»", _cam not in _code)
check("chìa vẽ bằng đường, có hàm riêng", hasattr(_ma, "_khoa"))
check("ba vòng tay cầm là NÉT, không tô — lỗ là lỗ thật",
      "setLineWidth_" in _src and ".stroke()" in _src)
# Icon ở Dock và logo trên thanh bên phải là MỘT cái tên.
# ĐẾM TRONG LOGO, không đếm cả file: bộ icon thanh bên cũng có <circle>
# (kính lúp, người, bánh răng) — đúng lớp lỗi bài "ba vòng chìa" bên test_web
# đã dính. Cùng một cái bẫy, hai lần.
_lay = (_goc / "src/jobbot/dashboard/layout.py").read_text(encoding="utf-8")
_logo = _lay[_lay.index("LOGO = ("):]
_logo = _logo[:_logo.index("</svg>")]
check("logo trong app cũng là chìa khoá ba vòng", _logo.count("<circle cx=") == 3)
check("bộ đủ cỡ tới 16px cho Finder", "16, 32, 128, 256, 512" in _src)
_icns = _goc / "jobbot.app/Contents/Resources/jobbot.icns"
if _icns.exists():
    check("bản .icns đã đóng gói không rỗng", _icns.stat().st_size > 10_000)

print("\n[MỞ APP — cổng KHÔNG cố định nữa]")
import re as _re2
import subprocess as _sp2
_goc2 = _P(__file__).resolve().parent.parent

# --- tệp địa chỉ: ghi -> đọc -> xoá -------------------------------------
_cu_data = os.environ.get("JOBBOT_DATA_DIR")
_tmp2 = tempfile.mkdtemp()
os.environ["JOBBOT_DATA_DIR"] = _tmp2
try:
    import importlib as _ilib
    from jobbot.core import dia_chi as _dc
    _ilib.reload(_dc)
    _dc.ghi("http://127.0.0.1:8799/")
    check("ghi rồi đọc lại ra đúng địa chỉ", _dc.doc() == ("http://127.0.0.1:8799/", os.getpid()))
    check("dòng 1 đọc được bằng `head -1` của shell",
          _sp2.run(["head", "-n", "1", str(_dc.tep())], capture_output=True,
                   text=True).stdout.strip() == "http://127.0.0.1:8799/")
    # Tệp rác thì trả None, KHÔNG nổ: nó là tệp trên đĩa, ai cũng sửa được.
    _dc.tep().write_text("rác\n", encoding="utf-8")
    check("tệp hỏng -> None, không nổ", _dc.doc() is None)
    _dc.tep().write_text("http://127.0.0.1:8799/\nkhong-phai-so\n", encoding="utf-8")
    check("PID hỏng vẫn lấy được địa chỉ", _dc.doc() == ("http://127.0.0.1:8799/", 0))
    _dc.xoa()
    check("xoá rồi thì đọc ra None", _dc.doc() is None)
    check("xoá lần hai không nổ", _dc.xoa() is None)
finally:
    if _cu_data is None: os.environ.pop("JOBBOT_DATA_DIR", None)
    else: os.environ["JOBBOT_DATA_DIR"] = _cu_data

# --- start.command không được hỏi một cổng cắm cứng ---------------------
_start = (_goc2 / "start.command").read_text(encoding="utf-8")
_start_code = "\n".join(l for l in _start.splitlines() if not l.lstrip().startswith("#"))
check("start.command KHÔNG còn cắm cứng cổng 8765", "8765" not in _start_code)
check("start.command đọc data/dang-chay.txt", "dang-chay.txt" in _start_code)
check("start.command xác minh đúng jobbot đang trả lời, không chỉ 200",
      "api/alive" in _start_code)
check("start.command hỏng thì KÊU LÊN", "display alert" in _start_code)
check("cú pháp start.command chạy được",
      _sp2.run(["bash", "-n", str(_goc2 / "start.command")]).returncode == 0)

# --- MỌI đường vào đều phải nói mình chạy ở đâu -------------------------
# Bẫy: thêm một đường vào thứ ba (ví dụ một kịch bản dịch vụ) mà quên ghi
# địa chỉ thì bấm đúp lại bật lượt thứ hai — đúng lỗi vừa sửa, lặp lại.
_duong_vao = []
for _f in sorted((_goc2 / "src").rglob("*.py")):
    _t = _f.read_text(encoding="utf-8")
    # `= serve()` chứ không phải "serve()": chữ đó còn nằm trong chú thích
    # và docstring của các module khác, và bắt nhầm docstring thì bài test
    # đòi dia_chi.py phải tự ghi địa chỉ cho chính nó.
    if _re2.search(r"=\s*serve\(\)", _t):
        _duong_vao.append((_f, "dia_chi.ghi" in _t))
check("tìm được đúng hai đường vào (__main__ và app)", len(_duong_vao) == 2,
      str([str(f.name) for f, _ in _duong_vao]))
for _f, _co in _duong_vao:
    check(f"{_f.name} gọi serve() thì cũng ghi địa chỉ", _co)

# --- vỏ .app: không nướng cứng Python, hỏng thì nói ---------------------
_ma_app = _il.module_from_spec(_spec); _spec.loader.exec_module(_ma_app)
_vo = _ma_app.VO
check("vỏ .app KHÔNG nướng cứng đường Python", "/opt/anaconda3" not in _vo
      and "sys.executable" not in _vo)
check("vỏ .app đi tìm Python lúc chạy, dùng chung bản với start.command",
      "scripts/tim-python.sh" in _vo)
check("vỏ .app kiểm dự án còn đó không trước khi cd", "run.py" in _vo.split("cd ")[0])
check("vỏ .app hỏng thì KÊU LÊN, không thoát lặng lẽ",
      "display alert" in _vo and _vo.count("keu ") >= 2)
_vo_thu = _goc2 / "jobbot.app/Contents/MacOS/jobbot"
if _vo_thu.exists():
    # Bản ĐANG cài trên máy, không phải bản trong mã nguồn: dựng lại mới ăn.
    check("bản .app đang cài đã là vỏ mới", "tim-python.sh" in
          _vo_thu.read_text(encoding="utf-8"))

# --- bộ tìm Python: chọn theo SỐ HIỆU, không theo cái tên ---------------
_tim = (_goc2 / "scripts/tim-python.sh").read_text(encoding="utf-8")
check("bộ tìm Python hỏi version chứ không tin cái tên", "version_info >= (3, 11)" in _tim)
check("chỉ tay được bằng JOBBOT_PYTHON khi máy lạ", "JOBBOT_PYTHON" in _tim)
_cu_py2 = Path("/usr/bin/python3")
if _cu_py2.exists():
    # Máy này /usr/bin/python3 là 3.9 — bộ lọc PHẢI loại nó, nếu không thì
    # bấm đúp sẽ chạy bằng bản thiếu tomllib rồi chết ở dòng đầu run.py.
    _thu = _sp2.run([str(_cu_py2), "-c",
                     "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"])
    check("chính câu lọc đó loại được /usr/bin/python3 cũ", _thu.returncode == 1)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
