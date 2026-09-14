"""The applying layer — the answer book, bucketing, matching, and THE BOUNDARY.

Every number in this file comes from a REAL form (Point72/Greenhouse,
cohere/Ashby, zopa/Lever), not from imagination. Every bug that happened once
left exactly one case here.

    python3 tests/test_apply.py
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.apply import fields as F, run
from jobbot.apply.answer import Ans, LEVEL_WORDS, book, education

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ok   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}{' — ' + extra if extra else ''}")


# A FICTIONAL PERSON. This repo is public on GitHub: a real phone number and
# email in a test are what bots harvest for spam. A fixture needs no real
# person — it only needs a three-word name to test the "the last word is the
# surname" rule.
VIN = {
    "full_name": "Ada Grace Lovelace",
    "email": "you@example.com",
    "phone": "+44 7000 000000",
    "location": "London, UK",
    "links": "https://vinhdac.github.io\nLinkedIn\nGitHub",
    "education": ("MSc Computational Finance — Royal Holloway, University of "
                  "London, 2025–2026\n  Investment 86\n\nBA (Hons) Advanced "
                  "Finance — National Economics University, Vietnam"),
}

print("\n== the answer book ==")
edu = education(VIN["education"])
check("the degree", edu.degree == "MSc" and edu.level == "master", edu.degree)
check("the discipline", edu.discipline == "Computational Finance", edu.discipline)
check("the school", edu.school == "Royal Holloway, University of London", edu.school)
check("the years", (edu.start_year, edu.end_year) == (2025, 2026), str(edu.start_year))
check("a missing month is SAID", any("month" in m for m in edu.missing), str(edu.missing))
check("it takes the MOST RECENT degree, not the first", "Royal Holloway" in edu.school)

edu2 = education("MSc Data Science — Imperial College, Sep 2025 – Sep 2026")
check("the month is read when the profile states one",
      (edu2.start_month, edu2.end_month) == (9, 9) and not edu2.missing,
      str(edu2.missing))

b = book(VIN)
# The real bug: splitting on the FIRST word made the surname "Vinh Nguyen".
check("the surname is the last word", b["last_name"].value == "Lovelace", b["last_name"].value)
check("the given name is the rest", b["first_name"].value == "Ada Grace", b["first_name"].value)
check("the country is derived from where they live", b["country"].value == "United Kingdom", b["country"].value)
# The profile carries the bare word "LinkedIn" — that is a label, not an address.
check("the word 'LinkedIn' is not taken as a URL", not b["linkedin"].value, b["linkedin"].value)
check("the website is a real URL", b["website"].value.startswith("https://"), b["website"].value)
check("missing means EMPTY, never invented", not b["edu_end_month"].value)

print("\n== bucketing ==")
CASES = [
    # (label, field name, kind, expected bucket, expected key)
    ("First Name *", "first_name", "text", F.FILL, "first_name"),
    ("Last Name", "last_name", "text", F.FILL, "last_name"),
    ("Email", "email", "email", F.FILL, "email"),
    ("Resume/CV", "resume", "file", F.FILL, "resume"),
    ("School*", "school--0", "combo", F.FILL, "school"),
    ("Degree*", "degree--0", "combo", F.FILL, "degree"),
    ("End date year*", "end-year--0", "number", F.FILL, "edu_end_year"),
    ("End date month*", "end-month--0", "combo", F.FILL, "edu_end_month"),
    ("LinkedIn URL", "urls[LinkedIn]", "text", F.FILL, "linkedin"),
    ("GitHub URL", "urls[GitHub]", "text", F.FILL, "github"),
    # The three questions that must NOT be guessed — wrong ruins the application.
    ("Will you now or in the future require sponsorship?", "q1", "combo", F.ASK, None),
    ("What is your current cumulative GPA?", "question_68932242", "text", F.ASK, None),
    ("Will you graduate from January 2028-Summer 2028?", "q3", "combo", F.ASK, None),
    ("Expected salary", "q4", "text", F.ASK, None),
    ("I agree to the privacy policy", "consent", "checkbox", F.ASK, None),
    ("Cover Letter", "cover_letter", "file", F.ASK, None),
    ("", "opportunityLocationId", "text", F.ASK, None),
    # Protected characteristics — never touched, even when the form requires them.
    ("Gender", "gender", "combo", F.SKIP, None),
    ("Are you Hispanic/Latino?", "hispanic", "combo", F.SKIP, None),
    ("Race", "race", "combo", F.SKIP, None),
    ("Veteran Status", "veteran", "combo", F.SKIP, None),
    ("Have you served in the military?*", "q5", "combo", F.SKIP, None),
    ("Disability Status", "disability", "combo", F.SKIP, None),
    ("She/her", "pronouns", "checkbox", F.SKIP, None),
]
for label, name, kind, want_bucket, want_key in CASES:
    got_bucket, got_key = F.classify(
        {"label": label, "name": name, "dom_id": "", "kind": kind})
    fine = got_bucket == want_bucket and (want_key is None or got_key == want_key)
    check(f"{want_bucket:<4} {(label or name)[:44]}", fine, f"ra {got_bucket}/{got_key}")

check("every ASK rule carries a reason",
      all(reason.strip() for _, reason in F.ASK_RULES))
check("no rule both FILLS and ASKS",
      not {k for _, k in F.FILL_RULES} & {"gpa", "sponsor", "salary"})

print("\n== grouping and shadow fields ==")
raw = [
    {"k": 0, "name": "", "dom_id": "first_name", "kind": "text", "label": "First Name",
     "option": "", "group": "", "required": True, "options": [], "value": ""},
    # 4 tick boxes sharing a name = ONE question, not four.
    *[{"k": i, "name": "question_271[]", "dom_id": "", "kind": "checkbox",
       "label": "Preferred office", "option": city, "group": "question_271[]",
       "required": True, "options": [], "value": ""}
      for i, city in enumerate(["London", "Paris", "Hong Kong", "Tokyo"], start=1)],
]


class FakeTab:
    def __init__(self, payload):
        self.payload = payload

    def eval(self, _js, timeout=30.0):
        import json
        return json.dumps(self.payload)


folded = F.read(FakeTab(raw))
check("4 tick boxes fold into 1 question", len(folded) == 2, f"got {len(folded)}")
check("all 4 options are kept",
      folded[1]["options"] == ["London", "Paris", "Hong Kong", "Tokyo"],
      str(folded[1]["options"]))

print("\n== matching a dropdown ==")
DEG = ["Bachelor's Degree", "Master of Business Administration (M.B.A.)",
       "Master's Degree", "Doctorate"]
check("MSc -> Master's Degree, NOT the MBA",
      run.match(Ans("MSc", LEVEL_WORDS["master"]), DEG) == "Master's Degree",
      run.match(Ans("MSc", LEVEL_WORDS["master"]), DEG))
check("an MBA still yields the MBA",
      run.match(Ans("MBA", LEVEL_WORDS["mba"]), DEG).startswith("Master of Business"))
check("UK does not become Ukraine",
      run.match(Ans("United Kingdom", ("GB", "UK")),
                ["Ukraine", "United Kingdom", "United Arab Emirates"]) == "United Kingdom")
LON = ["London, Ontario, Canada", "London, England, United Kingdom"]
check("London is the UK London",
      run.match(Ans("London", ("London, UK",), ("United Kingdom", "England")), LON)
      == "London, England, United Kingdom")
check("nothing matching returns EMPTY, it does not grab one",
      run.match(Ans("Royal Holloway"), ["Oxford", "Cambridge"]) == "")
check("it types in order: the value first, the alternatives after",
      run.queries(Ans("MSc", LEVEL_WORDS["master"]))[0] == "MSc")
check("it cuts at the comma",
      run.queries(Ans("Royal Holloway, University of London")) == ["Royal Holloway"])

print("\n== the 12 bugs the audit found ==")
# (2) Greenhouse/Lever write it THE OTHER WAY ROUND: "authorized to work in
#     this country". The old version only caught "work authoriz…", so the
#     reversed sentence fell into the `country` rule and the machine answered
#     a yes/no question with the words "United Kingdom".
for _lab in ("Are you legally authorized to work in this country?",
             "Are you authorised to work in the UK?",
             "Do you require a work permit?"):
    check(f"right to work -> ASK: {_lab[:38]}",
          F.classify({"label": _lab, "name": "", "dom_id": "", "kind": "text"})[0] == F.ASK)
# (9) Nationality / place of birth is NOT where you currently live.
for _lab in ("What is your nationality?", "Country of birth", "Passport country"):
    check(f"nationality -> ASK: {_lab[:30]}",
          F.classify({"label": _lab, "name": "", "dom_id": "", "kind": "text"})[0] == F.ASK)
# (4) The FILL rules matched by substring, so a QUESTION that happened to
#     mention "city" was answered with a fact from the profile.
check("a narrative question -> ASK",
      F.classify({"label": "Do you have a driving licence valid in your city?",
                  "name": "", "dom_id": "", "kind": "text"})[0] == F.ASK)
check("a short factual label still FILLS",
      F.classify({"label": "City", "name": "", "dom_id": "", "kind": "text"})
      == (F.FILL, "city"))
# (1) A tick box's `value` is the CODE the form submits, not the text shown.
#     Assigning to it rewrites that code without ticking anything, and
#     `el.value === v` is still true so the machine reports success. Measured
#     in a real Chrome: the form submitted "London" instead of
#     "london_office".
for _kind in ("checkbox", "radio"):
    check(f"a {_kind} field never reaches the FILL bucket",
          F.classify({"label": "Which office? *", "name": "q[]", "dom_id": "",
                      "kind": _kind})[0] != F.FILL)
_fillsrc = (Path(__file__).resolve().parent.parent
            / "src/jobbot/apply/run.py").read_text(encoding="utf-8")
check("fill() separates tick boxes out before calling _set",
      _fillsrc.index('item["kind"] in ("checkbox", "radio")')
      < _fillsrc.index('bad = _set(tab, item["k"], want.value)')
      if 'bad = _set(tab, item["k"], want.value)' in _fillsrc else
      'item["kind"] in ("checkbox", "radio")' in _fillsrc)
# (10) "UK".startswith-matches "Ukraine" exactly as "UK" is inside "Ukraine".
check("a short name does not match by prefix",
      run.match(Ans("United Kingdom", ("GB", "UK")), ["Ukraine"]) == "")
check("but a long enough name still matches",
      run.match(Ans("United Kingdom", ("GB", "UK")),
                ["Ukraine", "United Kingdom"]) == "United Kingdom")
# (3) "There is text in the field" is not yet proof the ROW CLICKED was chosen.
check("pick() compares the chip against the row clicked", "and the field shows" in _fillsrc)
# (5)(6)(8) — see the "Submit button" section above.

print("\n== the boundary: the machine NEVER presses Submit ==")
source = Path(__file__).resolve().parent.parent / "src/jobbot/apply/run.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
calls = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        fn = node.func
        calls.append(fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", ""))
check("it calls .click() nowhere", "click" not in calls)
check("it calls .submit() nowhere", "submit" not in calls)
# THE PYTHON AST IS BLIND TO JAVASCRIPT, and JS is where the app REALLY drives
# the page: the scripts sent over CDP live inside Python strings, so
# `ast.walk` cannot see an `el.click()` in there. Founding law 4 — the machine
# NEVER presses Submit — has to be guarded at both layers.
import re as _reJ
_apply_dir = source.parent
_js_xau = []
for _f in sorted(_apply_dir.glob("*.py")):
    _t = _f.read_text(encoding="utf-8")
    for _m in _reJ.finditer(r"\.(click|submit)\s*\(", _t):
        _js_xau.append(f"{_f.name}:{_t[:_m.start()].count(chr(10)) + 1}")
check("NOWHERE — not even in JS — is .click()/.submit() called"
      + (f" — {', '.join(_js_xau[:3])}" if _js_xau else ""), not _js_xau)
# TWO CLICK SITES, AND THAT SPLIT IS FOUNDING LAW 4 ITSELF:
#   run.py  — fills the form, clicking only to open a dropdown and pick a row.
#             The machine runs this itself.
#   send.py — THE SUBMIT CLICK. Reachable only from /api/apply/send, i.e. from
#             exactly one press by the user on screen.
# Counted together that distinction is lost; a Submit click slipping into
# run.py would go unseen, which is precisely what this law exists to forbid.
_dem = {_f.name: _f.read_text(encoding="utf-8").count("Input.dispatchMouseEvent")
        for _f in sorted(_apply_dir.glob("*.py"))}
check("the self-driving fill (run.py) has EXACTLY ONE click site, already examined",
      _dem.get("run.py") == 1, str(_dem))
check("THE SUBMIT click lives apart in send.py, also exactly one",
      _dem.get("send.py") == 1, str(_dem))
check("NO other file in apply/ clicks a mouse",
      all(v == 0 for k, v in _dem.items() if k not in ("run.py", "send.py")),
      str(_dem))

body = source.read_text(encoding="utf-8")
check("it never types Enter", '"Enter"' not in body and "'Enter'" not in body)
# Both latches have to be intact: the click that opens a dropdown and the
# click that picks a row.
check("latch 1 — the element has to wrap that very field", 'box.get("wraps")' in body)
check("latch 1 — the click point has to sit on that element", 'box.get("hits")' in body)
check("latch 2 — only an element with role=option is clicked", 'spot.get("role") != "option"' in body)
check("latch 2 — the click point has to sit on that row", 'spot.get("hits")' in body)
check("every click goes through exactly one function", body.count("Input.dispatchMouseEvent") == 1)

print("\n== fields missed, leaving the application incomplete ==")
_fsrc = (Path(__file__).resolve().parent.parent
         / "src/jobbot/apply/fields.py").read_text(encoding="utf-8")
# Many ATS leave <input type=file> hidden, with no name and no id, driven by
# JS. Leave it out of the list and the application goes WITHOUT the CV, with
# nothing to say so.
check("a file field with no name/id is still kept", "type !== 'file') return" in _fsrc)
# A date-picker widget locks the text field to force a click on the calendar,
# and that field is usually REQUIRED.
check("a locked field still reaches the list", "el.disabled) return" in _fsrc
      and "el.readOnly) return" not in _fsrc)
check("but fill() is not allowed to type into it", 'f.get("locked")' in _fsrc)
_lab = {"label": "Expected graduation date *", "name": "g", "dom_id": "",
        "kind": "text", "locked": True, "required": True, "options": [],
        "option": "", "group": "", "k": 0, "value": ""}


class _One:
    def eval(self, js, timeout=30.0):
        import json as _j
        return _j.dumps([_lab])


_got = F.read(_One())
check("a locked field goes into the ASK bucket", _got[0]["bucket"] == F.ASK, _got[0]["bucket"])
check("and it keeps the required flag", _got[0]["required"] is True)

print("\n== the Education field: several separator styles ==")
from jobbot.apply.answer import education as _edu
for _sep in ("—", "-", "|"):
    _e = _edu(f"MSc Computational Finance {_sep} Royal Holloway, 2025-2026")
    check(f"separator {_sep!r}: the fields parse correctly",
          _e.school.startswith("Royal Holloway") and _e.discipline == "Computational Finance")

print("\n== the Submit button: check first, click after ==")
from jobbot.apply import send


class FormTab:
    """A fake tab: it returns exactly what READ_JS would return."""

    def __init__(self, items):
        self.items = items
        self.clicks = 0

    def eval(self, js, timeout=30.0):
        import json as _j
        return _j.dumps(self.items)

    def call(self, method, params=None, timeout=30.0):
        if method == "Input.dispatchMouseEvent":
            self.clicks += 1
        return {}


def _f(label, required, value, kind="text"):
    return {"k": 0, "name": label, "dom_id": "", "kind": kind, "label": label,
            "option": "", "group": "", "required": required, "options": [],
            "value": value}


full = FormTab([_f("First Name*", True, "Dac Vinh"), _f("Privacy *", True, "x")])
gap = FormTab([_f("First Name*", True, "Dac Vinh"), _f("Privacy *", True, ""),
               _f("Have you served in the military?*", True, "")])

check("a complete form -> no empty field left", send.missing(full) == [])
check("an incomplete form -> it names exactly which", send.missing(gap) ==
      ["Privacy *", "Have you served in the military?*"], str(send.missing(gap)))

refused = send.submit(gap)
check("incomplete -> it REFUSES to send", refused.ok is False)
check("and it says why", "required" in refused.why, refused.why)
check("it clicks the mouse NOT ONCE", gap.clicks == 0, str(gap.clicks))
# A demographic field the machine never fills — so it has to be in the
# blocking list rather than waved through.
check("a required demographic field blocks too",
      "Have you served in the military?*" in refused.missing)

body = (Path(__file__).resolve().parent.parent
        / "src/jobbot/apply/send.py").read_text(encoding="utf-8")
check("every click goes through one place", body.count("Input.dispatchMouseEvent") == 1)
check("the button has to belong to the form that was filled", 'aim.get("inform")' in body)
# Two copies of one button-picking rule will drift apart one day — and
# drifting here means approving one button and clicking another, on an action
# that cannot be undone.
# Measure the real invariant: only ONE place in the whole file knows how to
# pick the submit button. Counting querySelectorAll is wrong — that block also
# has to count filled fields to pick the form.
check("only ONE place picks the submit button", body.count('button[type="submit"]') == 1)
# Check by STRUCTURE, never by string search: the comment explaining the old
# bug contains that very string, and the test trips over its own explanation.
_code = "\n".join(l for l in body.splitlines() if not l.strip().startswith(("#", "//")))
check("the form is picked by NUMBER OF FILLED FIELDS", "querySelectorAll('[data-jb]')" in _code)
check("and counted per form", "tally.set" in _code and "n > best" in _code)
# With no button carrying a submit word, STOP. Falling back to "the only
# button left" is clicking blindly on "Save draft" / "Add another".
check("it does not fall back to any button", "named.length ? named" not in body)
check("a send needs PROOF, not merely that a click was dispatched",
      "said or moved or gone" in body)
check("and a baseline measured BEFORE the click", "before = json.loads" in body)
check("the button has to be inside the form holding FILLED fields", "[data-jb]" in body)
check("the click point has to sit on the button", 'aim.get("hits")' in body)
# THE FILLING code must not know how to send — that is why sending lives in a
# file of its own.
fill_body = (Path(__file__).resolve().parent.parent
             / "src/jobbot/apply/run.py").read_text(encoding="utf-8")
check("run.py does not call submit()", "send.submit" not in fill_body
      and "submit(" not in fill_body)

routes = (Path(__file__).resolve().parent.parent
          / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("exactly ONE route into the sending code", routes.count("apply_send.submit") == 1)
check("a failed send does NOT change the state",
      routes.index("if not done.ok") < routes.index("board.set_stage(conn, int(row[\"id\"])"))
# Pressing Send twice = two identical applications to one employer. Blocked at
# HAI tang: route tu choi dong khong con la nhap, va submit() tu choi khi trang
# khong con o nao (thuong la vua gui xong, trang da nhay sang loi cam on —
# luc do missing() tra rong vi khong o nao thi khong o nao trong).
# The latch has to be ATOMIC: comparing the stage and then sending is
# read-then-write, and the stage change happens on a background thread seconds
# later — two presses 2 seconds apart both read 'draft'. A single
# UPDATE ... WHERE stage='draft' lets only one win.
check("the route claims the send with a single UPDATE", "board.claim(conn" in routes)
check("a failed send hands it back to draft", routes.count("board.unclaim(") >= 3)
_bd = (Path(__file__).resolve().parent.parent
       / "src/jobbot/track/board.py").read_text(encoding="utf-8")
check("claim() changes the stage conditionally", "WHERE id = ? AND stage = ?" in _bd)
check("submit() refuses once the form is gone",
      "the page has no form left" in body)
check("and it blocks BEFORE counting the empty fields",
      body.index("the page has no form left") < body.index("gaps = missing(tab)"))

print("\n== not logged in means SAY SO, never stay silent ==")
check("it recognises LinkedIn's login page",
      bool(run.LOGIN_WALL.search("https://www.linkedin.com/login/?session_redirect=x")))
check("it recognises the authwall",
      bool(run.LOGIN_WALL.search("https://www.linkedin.com/authwall?trk=y")))
check("it does NOT mistake Lever's apply page (ending /apply)",
      not run.LOGIN_WALL.search("https://jobs.lever.co/zopa/abc/apply"))
check("it does NOT mistake a Greenhouse page",
      not run.LOGIN_WALL.search("https://job-boards.greenhouse.io/point72/jobs/729"))
_wall = run.Report(needs_login="https://www.linkedin.com/login/")
check("the report states the reason rather than 'no form found'",
      "login" in _wall.line(), _wall.line())
_routes = (Path(__file__).resolve().parent.parent
           / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("the server writes the ERROR to the journal", "NOT LOGGED IN" in _routes)
check("and it stops rather than logging on as if it had filled things",
      _routes.index("NOT LOGGED IN") < _routes.index('journal.log.ok(journal.SEARCH, f"{who} — {report.line()}")'))

print("\n== LinkedIn: digging out the real application link ==")
from jobbot.apply import linkedin as lk
_wrapped = ("https://www.linkedin.com/safety/go/?url=https%3A%2F%2Ftargetjobs%2Eco%2Euk"
            "%2Fjobs%2Fstructured-credit&urlhash=abcd")
check("a company URL is decoded",
      lk.unwrap(_wrapped) == "https://targetjobs.co.uk/jobs/structured-credit",
      lk.unwrap(_wrapped))
# LinkedIn encodes even the dots as %2E — splitting by hand yields 'targetjobs%2Eco%2Euk'
check("a %2E-encoded dot comes out right too", ".co.uk" in lk.unwrap(_wrapped))
check("an internal LinkedIn link is dropped",
      lk.unwrap("https://www.linkedin.com/jobs/view/123") == "")
check("an already-external link is taken as it is",
      lk.unwrap("https://jobs.lever.co/prima/x/apply") == "https://jobs.lever.co/prima/x/apply")
check("it recognises a LinkedIn posting page",
      bool(lk.JOBS.search("https://www.linkedin.com/jobs/view/4449348217/")))
check("it does not mistake another page",
      not lk.JOBS.search("https://job-boards.greenhouse.io/point72/jobs/729"))
_fill = (Path(__file__).resolve().parent.parent
         / "src/jobbot/apply/run.py").read_text(encoding="utf-8")
check("not logged in it stops rather than groping on",
      _fill.index("if lk.JOBS.search(url)") < _fill.index("real = lk.apply_url(tab)"))

print("\n== the filename of the CV that goes out ==")
import tempfile as _tf
from pathlib import Path as _P
with _tf.TemporaryDirectory() as _d:
    _kho = _P(_d) / "qube-research-technologies-digital-assets-quantitative-trader-4137.pdf"
    _kho.write_bytes(b"%PDF-1.4 fake")
    _out = run.sendable(_kho, b, 5294)
    # The name in the store is THE GROUP's (after the highest-scoring posting
    # sharing that CV). Attached directly, the recruiter at Prima reads the
    # name Qube on the file.
    check("named after the profile's owner", _out.name.endswith("-CV.pdf"), _out.name)
    check("it does not carry another company's name", "qube" not in _out.name.lower())
    check("the contents are identical", _out.read_bytes() == _kho.read_bytes())
    _other = run.sendable(_kho, b, 1288)
    check("one directory per posting, so they never overwrite each other",
          _out.parent != _other.parent, f"{_out.parent} vs {_other.parent}")

# One directory per application; with nobody deleting them it grows forever (~200 KB each).
import os as _os, time as _time
with _tf.TemporaryDirectory() as _d2:
    _root = _P(_d2) / "send"
    for _n in ("old", "new"):
        (_root / _n).mkdir(parents=True)
        (_root / _n / "cv.pdf").write_bytes(b"x")
    _past = _time.time() - (run.KEEP_DAYS + 1) * 86400
    _os.utime(_root / "old", (_past, _past))
    _gone = run._prune(_root)
    check("the old copy is cleaned up", _gone == 1)
    check("the new one is kept", (_root / "new").exists())
    check("the old one is deleted", not (_root / "old").exists())

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
