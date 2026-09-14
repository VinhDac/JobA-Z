"""Test the cross-platform parts — macOS / Windows / Linux.

This test is written ON macOS but has to protect the Windows path. A real
Windows machine cannot be tried here, so the method is: force sys.platform and
look at what the code builds. It does not prove Windows works; it proves the
code is NOT hardwired to macOS.

Whatever can only be tried on a real machine is written down here rather than
pretended to be tested.

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
    """Force sys.platform inside a block, then put it back."""
    def __init__(self, module, name):
        self.module, self.name = module, name
    def __enter__(self):
        self.old = self.module.sys.platform
        self.module.sys.platform = self.name
        return self
    def __exit__(self, *_):
        self.module.sys.platform = self.old


print("[finding Chrome: a different place on each system]")
from jobbot.browser import chrome

with platform_is(chrome, "win32"):
    os.environ.setdefault("PROGRAMFILES", r"C:\Program Files")
    win = chrome._candidates()
    check("Windows looks for chrome.exe", any(c.endswith("chrome.exe") for c in win))
    check("and msedge.exe too (Edge is Chromium as well)",
          any(c.endswith("msedge.exe") for c in win))
    check("it does NOT look at macOS paths on Windows",
          not any("/Applications/" in c for c in win))
    check("it looks at per-account installs too (LOCALAPPDATA)",
          len(win) > 4)

with platform_is(chrome, "darwin"):
    mac = chrome._candidates()
    check("macOS looks in /Applications", all(c.startswith("/Applications/") for c in mac))

with platform_is(chrome, "linux"):
    lin = chrome._candidates()
    check("Linux looks in /usr/bin", any(c.startswith("/usr/bin/") for c in lin))

check("not finding it is reported outright, never silently",
      "ChromeError" in Path("src/jobbot/browser/chrome.py").read_text())


print("\n[notifications: a different command on each system]")
from jobbot.core import notify

with platform_is(notify, "darwin"):
    cmd = notify.command("jobbot", "5 new postings", "go and look")
    check("macOS uses osascript", cmd[0] == "osascript")

with platform_is(notify, "win32"):
    cmd = notify.command("jobbot", "5 new postings", "go and look")
    check("Windows uses powershell", cmd[0] == "powershell")
    check("no external module needed (no BurntToast)",
          "BurntToast" not in cmd[-1])
    # A string reaching a PowerShell command has to be quoted, the same
    # lesson AppleScript taught.
    hack = notify.command("a", "'; Remove-Item C:\\ -Recurse; '", "")
    check("a single quote in the body is doubled, it cannot escape the command",
          "''" in hack[-1] and "Remove-Item" in hack[-1])

with platform_is(notify, "linux"):
    check("Linux uses notify-send",
          notify.command("a", "b")[0] == "notify-send")

check("an unknown system falls back to notify-send, it does not blow up",
      notify.BUILDERS.get("freebsd13") is None)


print("\n[reading a PDF: it must not be macOS-only]")
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
    check("Windows reads an ordinary-text PDF", "ADA GRACE LOVELACE" in text)
    check("and picks up the lower part too", "Computational Finance" in text)
    # A font with its own embedded encoding (LaTeX, Canva) extracts as junk.
    # Stuffing junk into the profile is worse than reporting an error — the
    # user still has pasting as a way in.
    try:
        ic.from_pdf(_pdf(["\x01\x02\x03\x04\x05\x06\x07" * 40]))
        check("an embedded-font PDF -> an error, NO junk into the profile", False)
    except ic.ReadError as exc:
        check("an embedded-font PDF -> an error, NO junk into the profile", True)
        check("and it points at the other way in (pasting)", "PASTE" in str(exc))

check("it recognises real text", ic._looks_like_text("Analyst at Acme. " * 20))
check("it recognises junk", not ic._looks_like_text("\x01\x02\x03\x04" * 80))
check("too short a string does not count as a CV", not ic._looks_like_text("hello"))


print("\n[the window shell]")
from jobbot import shell

with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    with platform_is(shell, "win32"):
        check("Windows does NOT use the macOS shell", not shell.has_mac_native())
    # The interface window has to use ITS OWN profile: shared with the
    # scraping profile, closing the window kills the tab the machine is
    # driving.
    from jobbot.browser import chrome as ch
    check("the window profile differs from the scraping profile",
          shell.ui_profile_dir() != ch.profile_dir())
    src = Path("src/jobbot/shell.py").read_text()
    check("and it opens NO debug port on the interface window",
          "--remote-debugging-port" not in src.split('"""')[2])
    check("it opens --app, not an ordinary browser tab", "--app=" in src)
    os.environ.pop("JOBBOT_DATA_DIR", None)


print("\n[paths: no string joining, no hardcoded /]")
from jobbot.core import paths
src = Path("src/jobbot/core/paths.py").read_text()
check("pathlib only", "Path(" in src and '"/"' not in src)
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    check("the data directory can be moved with an environment variable",
          paths.data_dir() == Path(tmp))
    os.environ.pop("JOBBOT_DATA_DIR", None)


print("\n[the Windows entry points]")
for name in ("run.bat", "run-console.bat"):
    raw = Path(name).read_bytes()
    check(f"{name} exists", bool(raw))
    # cmd.exe misreads a file with LF only — the command lines run together.
    check(f"{name} uses CRLF line endings", b"\r\n" in raw)
    check(f"{name} is ASCII only (cmd.exe does not default to UTF-8)",
          all(b < 128 for b in raw))

run_py = Path("run.py").read_text()
check("run.py refuses too old a Python", "3, 11" in run_py)



print("\n[the macOS app window — the file picker]")
# WKWebView CANNOT open a file dialog by itself. Without the delegate,
# <input type=file> dies silently: pressing "Choose File" does nothing, with no
# error and no log — while the same page works normally in an ordinary
# browser.
if sys.platform == "darwin":
    try:
        from jobbot.app import Delegate
        _sel = (b"webView:runOpenPanelWithParameters:"
                b"initiatedByFrame:completionHandler:")
        _m = Delegate.webView_runOpenPanelWithParameters_initiatedByFrame_completionHandler_
        check("the Delegate has a file-picker method", _m.selector == _sel)
        # The signature has to be declared by hand. Left to PyObjC to infer,
        # the last parameter comes out "@" rather than "@?" (a block) —
        # `handler(...)` then calls into nothing and the file picker hangs
        # forever.
        check("the last parameter is declared as a BLOCK",
              _m.signature.decode().endswith("@?"))
        _src = (Path(__file__).resolve().parent.parent
                / "src/jobbot/app.py").read_text(encoding="utf-8")
        check("and the delegate is attached to the webview", "setUIDelegate_(delegate)" in _src)

        # THE WAY OUT. Job postings live on linkedin.com, greenhouse.io —
        # without this method an <a target=_blank> click does NOTHING: no
        # error, no log, exactly the class of bug the file picker hit once.
        _sel2 = (b"webView:createWebViewWithConfiguration:"
                 b"forNavigationAction:windowFeatures:")
        _m2 = Delegate.webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_
        check("the Delegate has a method for opening links out", _m2.selector == _sel2)
        # Left to PyObjC to infer, it sees `return None` and concludes the
        # return is VOID, while WKWebView calls this method to get back a
        # WKWebView* — with the wrong return type the runtime reads junk out
        # of a register, and it works sometimes and not others.
        check("the RETURN type is declared as object, not void",
              _m2.signature.decode().startswith("@@:"), _m2.signature.decode())
        # Opening it inside the app window loses the dashboard: that window
        # has no address bar and no Back button.
        check("it hands off to the machine's default browser",
              "NSWorkspace.sharedWorkspace().openURL_" in _src)
    except ImportError:
        check("skipped — no PyObjC on this machine", True)
else:
    check("skipped — not macOS", True)

print("\n[SYNTAX THAT RUNS ON THE PYTHON VERSION THE APP CLAIMS]")
# A BUG THAT REALLY HAPPENED, and of the kind that ONLY SHOWS ON SOMEBODY
# ELSE'S MACHINE: views/settings.py wrote f"...{" on" if x else ""}..." —
# double quotes nested in double quotes, i.e. PEP 701, valid only FROM Python
# 3.12. The development machine runs 3.13 so all 2,300 checks were green,
# while on a clean macOS (Python 3.9.6) the whole file would not compile:
# opening the Settings tab blew the app up.
#
# This test compiles EVERY file with AN OLDER interpreter. /usr/bin/python3 is
# always present on macOS, so this latch asks for nothing to be installed.
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
    check(f"every file compiles under Python {_ban}"
          + (f" — broken: {', '.join(_xau[:3])}" if _xau else ""), not _xau)
else:
    check("skipped — no /usr/bin/python3 on this machine", True)

print("\n[THE APP ICON — drawn as SHAPES, black and white, the same mark as the in-app logo]")
import importlib.util as _il
from pathlib import Path as _P
_goc = _P(__file__).resolve().parent.parent
_spec = _il.spec_from_file_location("make_app", _goc / "scripts/make_app.py")
_ma = _il.module_from_spec(_spec); _spec.loader.exec_module(_ma)
_src = (_goc / "scripts/make_app.py").read_text(encoding="utf-8")

# BLACK AND WHITE: all three colours have to be pure grey — three equal RGB channels.
for _ten, _h in (("ground", _ma.GROUND), ("rings", _ma.RING), ("key", _ma.INK)):
    _rgb = [int(_h.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)]
    check(f"the {_ten} colour is pure grey, with no cast",
          _rgb[0] == _rgb[1] == _rgb[2])
check("the rings contrast sharply with the ground",
      abs(int(_ma.GROUND.lstrip('#')[:2], 16) - int(_ma.RING.lstrip('#')[:2], 16)) > 200)
check("the key is the ground colour, so it is a shape CUT OUT of the rings",
      _ma.INK == _ma.GROUND)
# DRAWN AS SHAPES, NOT AS A CHARACTER. The previous version drew "◆" in the
# system font: optical size and baseline were the font's to decide, so a macOS
# update shifted the icon with nothing to say so.
# It guards WHAT RUNS, not words in a comment: a comment recounting what was
# removed is the most worth keeping, and banning it bans the wrong thing.
_code = "\n".join(l for l in _src.splitlines() if not l.lstrip().startswith("#"))
for _cam in ("NSAttributedString", "NSFont", "drawAtPoint_"):
    check(f"it no longer relies on «{_cam}»", _cam not in _code)
check("the key is drawn with paths, in a function of its own", hasattr(_ma, "_key"))
check("the three grip rings are STROKED, not filled — the holes are real holes",
      "setLineWidth_" in _src and ".stroke()" in _src)
# The Dock icon and the sidebar logo are ONE name.
# COUNT INSIDE THE LOGO, not the whole file: the sidebar icon set also has
# <circle>s (the magnifier, the person, the cog) — exactly the class of bug
# the "three key rings" test in test_web hit. The same trap, twice.
_lay = (_goc / "src/jobbot/dashboard/layout.py").read_text(encoding="utf-8")
_logo = _lay[_lay.index("LOGO = ("):]
_logo = _logo[:_logo.index("</svg>")]
check("the in-app logo is the same three-ring key", _logo.count("<circle cx=") == 3)
check("the set goes down to 16px for Finder", "16, 32, 128, 256, 512" in _src)
_icns = _goc / "jobbot.app/Contents/Resources/jobbot.icns"
if _icns.exists():
    check("the packaged .icns is not empty", _icns.stat().st_size > 10_000)

print("\n[OPENING THE APP — the port is NO LONGER fixed]")
import re as _re2
import subprocess as _sp2
_goc2 = _P(__file__).resolve().parent.parent

# --- the address file: write -> read -> delete ---------------------------
_cu_data = os.environ.get("JOBBOT_DATA_DIR")
_tmp2 = tempfile.mkdtemp()
os.environ["JOBBOT_DATA_DIR"] = _tmp2
try:
    import importlib as _ilib
    from jobbot.core import dia_chi as _dc
    _ilib.reload(_dc)
    _dc.ghi("http://127.0.0.1:8799/")
    check("written and read back gives the right address", _dc.doc() == ("http://127.0.0.1:8799/", os.getpid()))
    check("line 1 is readable with the shell's `head -1`",
          _sp2.run(["head", "-n", "1", str(_dc.tep())], capture_output=True,
                   text=True).stdout.strip() == "http://127.0.0.1:8799/")
    # A junk file returns None and does NOT blow up: it is a file on disk and
    # anybody can edit it.
    _dc.tep().write_text("junk\n", encoding="utf-8")
    check("a broken file -> None, no blow-up", _dc.doc() is None)
    _dc.tep().write_text("http://127.0.0.1:8799/\nnot-a-number\n", encoding="utf-8")
    check("a broken PID still yields the address", _dc.doc() == ("http://127.0.0.1:8799/", 0))
    _dc.xoa()
    check("deleted, it reads back as None", _dc.doc() is None)
    check("deleting a second time does not blow up", _dc.xoa() is None)
finally:
    if _cu_data is None: os.environ.pop("JOBBOT_DATA_DIR", None)
    else: os.environ["JOBBOT_DATA_DIR"] = _cu_data

# --- start.command must not ask for a hardcoded port ---------------------
_start = (_goc2 / "start.command").read_text(encoding="utf-8")
_start_code = "\n".join(l for l in _start.splitlines() if not l.lstrip().startswith("#"))
check("start.command NO LONGER hardcodes port 8765", "8765" not in _start_code)
check("start.command reads data/dang-chay.txt", "dang-chay.txt" in _start_code)
check("start.command verifies it is really jobbot answering, not just a 200",
      "api/alive" in _start_code)
check("start.command SPEAKS UP when it fails", "display alert" in _start_code)
check("start.command's syntax is valid",
      _sp2.run(["bash", "-n", str(_goc2 / "start.command")]).returncode == 0)

# --- EVERY entry point has to say where it is running --------------------
# The trap: add a third entry point (a service script, say) and forget to
# write the address, and double-clicking starts a second instance — exactly
# the bug just fixed, repeated.
_duong_vao = []
for _f in sorted((_goc2 / "src").rglob("*.py")):
    _t = _f.read_text(encoding="utf-8")
    # `= serve()` and not "serve()": that word also appears in comments and
    # docstrings of other modules, and catching a docstring would have the
    # test demand that dia_chi.py write the address for itself.
    if _re2.search(r"=\s*serve\(\)", _t):
        _duong_vao.append((_f, "dia_chi.ghi" in _t))
check("exactly two entry points found (__main__ and app)", len(_duong_vao) == 2,
      str([str(f.name) for f, _ in _duong_vao]))
for _f, _co in _duong_vao:
    check(f"{_f.name} calls serve() and writes the address too", _co)

# --- the .app wrapper: no baked-in Python, and it speaks when it fails ---
_ma_app = _il.module_from_spec(_spec); _spec.loader.exec_module(_ma_app)
_shell = _ma_app.SHELL_SCRIPT
check("the .app wrapper does NOT bake in a Python path", "/opt/anaconda3" not in _shell
      and "sys.executable" not in _shell)
check("the .app wrapper finds Python at run time, sharing start.command's finder",
      "scripts/find-python.sh" in _shell)
check("the .app wrapper checks the project is still there before cd", "run.py" in _shell.split("cd ")[0])
check("the .app wrapper SPEAKS UP when it fails, it does not exit silently",
      "display alert" in _shell and _shell.count("alert ") >= 2)
_shell_installed = _goc2 / "jobbot.app/Contents/MacOS/jobbot"
if _shell_installed.exists():
    # The version INSTALLED on this machine, not the one in the source: only a
    # rebuild takes effect.
    check("the installed .app is already the new wrapper", "find-python.sh" in
          _shell_installed.read_text(encoding="utf-8"))

# --- the Python finder: it picks by VERSION NUMBER, never by name --------
_finder = (_goc2 / "scripts/find-python.sh").read_text(encoding="utf-8")
check("the Python finder asks the version rather than trusting the name", "version_info >= (3, 11)" in _finder)
check("JOBBOT_PYTHON can point at it by hand on an unusual machine", "JOBBOT_PYTHON" in _finder)
_cu_py2 = Path("/usr/bin/python3")
if _cu_py2.exists():
    # On this machine /usr/bin/python3 is 3.9 — the filter MUST reject it, or
    # double-clicking runs on a build with no tomllib and dies on run.py's
    # first line.
    _thu = _sp2.run([str(_cu_py2), "-c",
                     "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"])
    check("that very filter rejects the old /usr/bin/python3", _thu.returncode == 1)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
