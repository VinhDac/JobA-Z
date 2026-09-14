"""The two founding laws WITH NOBODY WATCHING THEM — and where the other five
are watched.

Seven laws built this app. Five have real guards; two did not, and those two
are exactly what an outsider reading the README will believe at once:

    1  NO LLM                               -> guarded HERE
    2  The CV's sentences are Vin's own     -> tests/test_cv.py
    3  The mailbox is READ ONLY             -> tests/test_track.py
    4  The machine NEVER presses Send       -> tests/test_apply.py
    5  Secrets live only in the config      -> tests/test_privacy.py
    6  Blocked means STOP                   -> tests/test_browser.py
    7  Failures must SPEAK                  -> everywhere, clearest in
                                               test_journal.py

    + NO DEPENDENCIES (standard library only)  -> guarded HERE

A law with no guard is a sentence in the README, not a law.

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
    """Strip comment lines. It guards WHAT RUNS, not words in a comment — a
    comment recounting what was removed is the most worth keeping."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


# ---------------------------------------------------------------------------
print("[LAW: NO DEPENDENCIES — standard library only]")
# The README promises "nothing to install, no venv". One `import requests`
# slipping in kills that promise, and it dies SILENTLY: the machine it was
# built on already has the package, and only somebody else's machine blows
# up.

# PyObjC is THE ONLY EXCEPTION, and it has to be an exception WITH A FALLBACK:
# every use site sits behind a wrapper, and without it the app still runs (a
# Chrome window instead of a macOS window, hand-rolled PDF extraction instead
# of PDFKit).
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
check(f"no external package ({len(ngoai)} modules loaded)", not cam,
      ", ".join(f"{k} ({', '.join(sorted(v))})" for k, v in sorted(cam.items())))
check("PyObjC is still the only exception", set(ngoai_le) <= COCOA)

# And that exception has to HAVE A FALLBACK: no file may load Cocoa at module
# level and then be imported unconditionally. app.py does load it at module
# level, so its caller (__main__.py) has to wrap it in a try.
mac_module = sorted({f for v in ngoai_le.values() for f in v})
check(f"only the known files touch Cocoa ({', '.join(mac_module)})",
      set(mac_module) <= {"app.py", "shell.py", "import_cv.py"},
      str(mac_module))
_mainpy = khong_chu_thich((ROOT / "src/jobbot/__main__.py").read_text(encoding="utf-8"))
check("and __main__ wraps app.py in a try, so it runs without PyObjC",
      "from .app import run" in _mainpy
      and "except (ImportError, AttributeError)" in _mainpy)
_shell = khong_chu_thich((ROOT / "src/jobbot/shell.py").read_text(encoding="utf-8"))
check("shell.has_mac_native() tries before concluding",
      "import objc" in _shell and "except Exception" in _shell)
_icv = khong_chu_thich((ROOT / "src/jobbot/profile/import_cv.py").read_text(encoding="utf-8"))
check("PDF extraction falls back to the hand-rolled path without PyObjC",
      "_pdf_plain" in _icv and "except Exception" in _icv)

# run.py and scripts/ have to be clean too — they are the first thing a user types.
for _p in [ROOT / "run.py"] + sorted((ROOT / "scripts").glob("*.py")):
    _cay = ast.parse(io.open(_p, encoding="utf-8").read(), str(_p))
    _la = set()
    for n in ast.walk(_cay):
        if isinstance(n, ast.Import):
            _la |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            _la.add(n.module.split(".")[0])
    _la -= chuan | {"jobbot"} | COCOA
    check(f"{_p.name} needs no external package", not _la, str(sorted(_la)))


# ---------------------------------------------------------------------------
print("\n[LAW: NO LLM — no language model, nobody asked to judge on our behalf]")
# The whole app has no LLM, and that is a decision rather than an omission:
# every sentence on the CV is Vin's, and every score traces back to a line of
# rules. One API call somewhere and both of those stop being true, with
# nobody able to read it.
# BANNED BY API SURFACE, NOT BY COMPANY NAME. Cohere, Anthropic, Mistral and
# OpenAI are all EMPLOYERS — their names are in the board list and will be in
# the job data. Ban the name and the test goes red because a company posted a
# job, and whoever fixes it learns exactly one thing: turn this test off.
DAU_LLM = ("api.openai.com", "api.anthropic.com", "api.cohere",
           "api.mistral", "generativelanguage.googleapis.com",
           "api-inference.huggingface", "openrouter.ai", "api.together.xyz",
           "chat/completions", "/v1/completions", "/v1/messages",
           "llama_cpp", "sentence_transformers", "ollama")
for f in NGUON:
    than = khong_chu_thich(f.read_text(encoding="utf-8")).lower()
    dinh = [d for d in DAU_LLM if d in than]
    if dinh:
        check(f"{f.name} calls no model", False, ", ".join(dinh))
check(f"no file in src/ touches a model's API surface ({len(NGUON)} files)", True)
# THE STRONGEST LATCH is the law above: no external package is allowed, so NO
# SDK from any model provider can exist in this app at all. The two laws lock
# each other, and that is why the no-dependencies law is worth guarding.
check("and no model SDK can get in (the no-dependencies law locks it)",
      not {"openai", "anthropic", "cohere", "mistralai", "google",
           "transformers", "torch", "llama_cpp"} & set(ngoai))

# STRONGER THAN A BAN LIST: enumerate EVERY host the app calls out to. A ban
# list only catches what was thought of; an ALLOW list catches what was not —
# add a new provider and this test goes red, whatever its name.
import re as _re
CHO_PHEP = {
    "127.0.0.1",                     # this machine
    "localhost",
    "www.linkedin.com", "linkedin.com",   # a source (read, logged in by hand)
    "boards-api.greenhouse.io", "api.lever.co", "api.ashbyhq.com",  # public ATS
    "api.telegram.org",              # messages to the phone
    "github.com",                    # only sample text in a profile field
}
thay = set()
for f in NGUON:
    for u in _re.findall(r"https?://([A-Za-z0-9._~%-]+)",
                         khong_chu_thich(f.read_text(encoding="utf-8"))):
        thay.add(u.lower())
la_mat = sorted(thay - CHO_PHEP)
check(f"only {len(thay)} hosts called, all declared", not la_mat, str(la_mat))

# IMAP does not go through http:// so the regex above does not see it. And a
# mailbox is the most private place there is, so the host must NOT be
# hardcoded to one provider: the old version wrote "imap.gmail.com" straight
# in, with a filter accepting only Google app passwords — anyone on
# Outlook/iCloud/a company mailbox was turned away at the door by a sentence
# with nothing to do with the real reason.
from jobbot.track import mail as _ml
check("the mail host is derived from the domain, not hardcoded to Gmail",
      _ml.may_chu("x@outlook.com") == "outlook.office365.com")
check("an unknown domain still tries the imap.<domain> convention",
      _ml.may_chu("x@congty.co.uk") == "imap.congty.co.uk")
check("a provider that does not publish IMAP is SAID OUTRIGHT, never guessed",
      _ml.may_chu("x@proton.me") == "")
check("and config.toml overrides all of it", "host" in
      khong_chu_thich((ROOT / "config/config.example.toml").read_text(encoding="utf-8")))
check("the app password filter applies to Google only",
      _ml._la_google("imap.gmail.com") and not _ml._la_google("outlook.office365.com"))

# THE NETWORK LOCK during a test run — one switch for BOTH routes out. The
# test suite used to send real messages to the phone on every run; IMAP is the
# second route.
_srcmail = khong_chu_thich((ROOT / "src/jobbot/track/mail.py").read_text(encoding="utf-8"))
check("IMAP obeys JOBBOT_OFFLINE the same as Telegram", "khoa_mang()" in _srcmail)
check("and that latch sits BEFORE the socket opens",
      _srcmail.index("khoa_mang()") < _srcmail.index("IMAP4_SSL(host"))

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
