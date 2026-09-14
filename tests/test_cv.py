"""Test step 3 — building a CV per JD.  python3 tests/test_cv.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.cv import rules
from jobbot.cv.blocks import parse, sentences
from jobbot.cv.build import build

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

CV = """DAC VINH NGUYEN
London, UK · +44 7000 000000 · me@example.com
Eligible for UK Graduate visa — no employer sponsorship required.
I want to work on interesting problems.
EXPERIENCE
Founder / Quantitative Developer — Trading Startup Jan 2026 – Present
Self-funded, across 17 instruments and five years of data. I designed and built two
systems in Python: signals, validation and risk. I was optimising for peak profit in the
most recent window — which rewards luck. A random train/test split leaks, because
adjacent dates are correlated. Live drawdown ran roughly 30% deeper than the model
predicted. The mistake was mine.
Research Consultant — WorldQuant Jan 2025 – Sep 2025
Generated systematic alpha signals in Python, scored on Sharpe ratio and drawdown.
I trained deep learning models in PyTorch on five years of tick data.
I built portfolio construction on the efficient frontier with explicit risk limits.
I wrote backtesting and walk-forward validation harnesses in pandas and NumPy.
Profit on its own means nothing: an edge can be faked.
SELECTED PROJECTS
Quant Trading Studio — the whole pipeline you can run: backtesting and risk budgeting.
EDUCATION
MSc Computational Finance — Royal Holloway 2025 – 2026
Deep Learning 83 · Data Analysis 83
Certifications — CFA Level I, top 10% of global candidates
TECHNICAL SKILLS
Programming — Python (pandas, NumPy, PyTorch), C++, SQL.
Compute — a GPU is fast at many simple operations at once.
Method — I direct Claude Code and Copilot rather than prompt them.
"""

PROFILE = {"cv_text": CV, "full_name": "Ada Grace Lovelace", "email": "me@example.com",
           "location": "London, UK", "skills_strong": "Python, pandas, PyTorch, C++, SQL",
           "education": "MSc Computational Finance — Royal Holloway 2025-2026",
           "certifications": "CFA Level I, top 10% of global candidates"}

print("\n[splitting into blocks]")
bs = parse(CV)
kinds = [b.kind for b in bs]
check("every block kind is recognised", {"header", "experience", "project", "education", "skill"} <= set(kinds))
exp = [b for b in bs if b.kind == "experience"]
check("exactly 2 roles, not split by a sentence containing a dash", len(exp) == 2)
check("the dates are read", exp[0].meta == "Jan 2026 – Present")
check("skill groups are split out separately", len([b for b in bs if b.kind == "skill"]) == 3)

joined = sentences(exp[0])
check("a PDF line broken mid-sentence is rejoined",
      any("adjacent dates are correlated" in s for s in joined))

print("\n[the rules — telling knowledge apart from failure]")
keep_cases = [
    "A random train/test split leaks, because adjacent dates are correlated",
    "I designed and built two systems in Python: signals, validation and risk",
]
drop_cases = [
    "Live drawdown ran roughly 30% deeper than the model predicted",
    "The mistake was mine: the regime split was a valid partition",
    "I never budgeted the time a proof would take, and the capital ran out",
]
# AN OPINION IS NOW 'ASK', NOT 'DROP'. Opinion and knowledge have the same
# shape — present simple, no number, no action — while knowledge is the
# STRONGEST thing on a technical CV. Left to guess, the machine will one day
# guess wrong about one of the two, and guessing wrong means deleting the
# strongest sentence. So it marks it and lets the writer decide.
review_cases = [
    "Profit on its own means nothing: an edge can be faked",
    "Good code is code other people can delete",
    "Reporting is only useful when someone acts on it",
]
for text in keep_cases:
    check(f"KEEP knowledge: {text[:40]}…", rules.sentence_ok(text)[0] == "keep")
for text in drop_cases:
    check(f"DROP a failure: {text[:40]}…", rules.sentence_ok(text)[0] == "drop")
for text in review_cases:
    check(f"ASK, never delete: {text[:38]}…", rules.sentence_ok(text)[0] == "review")

# THE RULE HAS TO BE GENERAL, not a lookup copied from one profile. The old
# version was a list of phrases taken straight out of one person's CV ("i was
# optimising for peak", "nobody has exploited"); measured on two other
# profiles it caught 0 of 5 sentences, though both plainly told a failure.
for _t in ("I honestly struggled with the first rebuild and it shipped two weeks late",
           "My first design leaked memory under load and I had to roll it back",
           "We missed the deadline and the pilot was rolled back"):
    check(f"SOMEBODY ELSE'S profile is caught too: {_t[:34]}…",
          rules.sentence_ok(_t)[0] == "drop")
# And it must NOT wrongly catch a sentence about an achievement containing the
# same word — that is the second half of the rule: "prevented data leakage"
# and "my design leaked" share the stem `leak`.
for _t in ("Prevented data leakage by splitting on regime boundaries",
           "Reduced failed builds from 12 a week to 1",
           "Detected and fixed a memory leak in the pricing loop"):
    check(f"an achievement sentence is NOT wrongly caught: {_t[:34]}…",
          rules.sentence_ok(_t)[0] == "keep")
# The third half: TENSE. "leaked" is something that happened to you, "leaks"
# is a general truth. The original rule's author recorded this very trap, and
# my first structural version walked straight into it again.
check("a KNOWLEDGE sentence in the present is NOT read as a failure",
      rules.sentence_ok(
          "A random train/test split leaks, because adjacent dates are "
          "correlated and information from the future ends up in training"
      )[0] == "keep")
# And the verdict must NOT change with the call signature.
_c1 = rules.sentence_ok("A random train/test split leaks, because adjacent "
                        "dates are correlated and future data leaks in")[0]
_c2 = rules.sentence_ok("A random train/test split leaks, because adjacent "
                        "dates are correlated and future data leaks in",
                        ["validation"])[0]
check("the same sentence -> the same verdict, with or without tags",
      _c1 == _c2)

verdict, why = rules.sentence_ok("Self-funded, across 17 instruments and five years of data")
check("a sensitive sentence WITH a number -> marked for review, not thrown away", verdict == "review")
check("and it says why", "your call" in why)
check("a button label stuck to the front of a sentence is stripped",
      rules.clean("Demo MetaTrader's backtester only measures edge").startswith("MetaTrader"))

print("\n[rewriting: only cutting and reordering Vin's own words]")
from jobbot.cv import rewrite as _rw
# DROPPING THE SUBJECT — a CV convention. It adds no fact.
for _t, _mong in (
    ("I designed and built every layer.", "Designed and built every layer."),
    ("I classified the market on two axes.", "Classified the market on two axes."),
    ("I rebuilt it without free parameters.", "Rebuilt it without free parameters."),
    ("I wrote the operating manual.", "Wrote the operating manual."),
):
    _ra, _da = _rw.sua(_t)
    check(f"drop the 'I' -> {_mong[:34]}", _ra == _mong)
check("and it says why, in plain words",
      "drop the subject" in _rw.sua("I built it and shipped it.")[1][0].vi_sao)

# THE DANGER: auxiliaries. "I was optimising" -> "Was optimising" is
# ungrammatical. The -ed / irregular rule excludes them by itself — this test
# is here so it is not loosened later.
for _t in ("I was optimising for peak profit.", "I had no capital left.",
           "My own capital ran out.", "I could not reproduce it.",
           "I am a quantitative developer."):
    check(f"an auxiliary is NOT touched: {_t[:30]}", _rw.sua(_t)[0] == _t)
# Mid-sentence it is not rewritten: changing mid-sentence changes the
# structure, and that is no longer cutting words.
check("first person MID-SENTENCE is NOT rewritten",
      _rw.sua("One signal has many configurations, so I chose on average.")[0]
      == "One signal has many configurations, so I chose on average.")

check("a capital at the start of a sentence is lowercased",
      _rw.sua("the whole pipeline turned into something you can run.")[0]
      .startswith("The whole"))
check("an already-correct sentence produces NO edit",
      _rw.sua("Built two systems in Python.")[1] == [])

# EVERY WORD has to be present in the original — this is the founding rule, at its smallest.
for _t in ("I designed and built every layer of two systems in MQL5.",
           "the whole pipeline turned into something you can run.",
           "I validated on two separate occurrences."):
    _ra, _ = _rw.sua(_t)
    check(f"no word is added: {_t[:28]}",
          not (set(_ra.lower().split()) - set(_t.lower().split())))

print("\n[weaknesses: the machine POINTS, the person writes]")
# This half the machine must not do for you: a sentence missing a measurement
# is missing A REAL NUMBER, and only Vin knows it. Inventing one produces a
# sentence Vin cannot defend in an interview.
# A CV SENTENCE IS ONE OF TWO THINGS, each demanding a different standard.
# Measured on the real profile: 12 of 16 sentences are KNOWLEDGE. Demand a
# measurement from all 16 and 12 of the marks are false alarms — and a mark on
# every line becomes the background, teaching the user to stop looking at
# marks.
check("AN ACHIEVEMENT missing a number -> caught",
      "khong_so" in {y.ma for y in _rw.diem_yeu("Built some models.", [], set())})
check("KNOWLEDGE is NOT asked for a number — there is no number to add",
      "khong_so" not in {y.ma for y in _rw.diem_yeu(
          "A random train/test split leaks, because adjacent dates correlate.",
          [], set())})
check("and knowledge is no longer criticised for not opening with a verb",
      "khong_dong_tu" not in {y.ma for y in _rw.diem_yeu(
          "A random train/test split leaks.", [], set())})
check("an achievement WITH a number is not flagged needlessly",
      "khong_so" not in {y.ma for y in _rw.diem_yeu(
          "Built 17 models across five years of data.", [], set())})
check("an over-long sentence is caught", "qua_dai" in {y.ma for y in _rw.diem_yeu(
      "Built " + "x" * 210, [], set())})
check("a sentence touching none of the posting's requirements is caught",
      "khong_tra_loi" in {y.ma for y in _rw.diem_yeu(
          "Built models in Python.", ["python"], {"c++"})})
check("every weakness carries SOMETHING TO DO, not general advice",
      all(y.lam_gi and len(y.lam_gi) > 20
          for y in _rw.diem_yeu("Built some models.", [], set())))

print("\n[building the CV]")
JD_ML = {"requirements": [{"text": "Strong Python and PyTorch for deep learning", "met": True,
                           "must": True, "evidence": ""}]}
JD_RISK = {"requirements": [{"text": "Portfolio construction and risk management", "met": True,
                             "must": True, "evidence": ""}]}
ml = build(PROFILE, JD_ML, "deep learning pytorch python")
risk = build(PROFILE, JD_RISK, "portfolio risk management")

def top_of(cv, title_part):
    section = next(s for s in cv.sections if title_part in s.title)
    return section.lines[0].text.lower()

check("a deep learning JD -> the first line is about PyTorch/deep learning",
      "pytorch" in top_of(ml, "WorldQuant") or "deep learning" in top_of(ml, "WorldQuant"))
check("a risk JD -> the first line is about portfolio/risk",
      "risk" in top_of(risk, "WorldQuant") or "portfolio" in top_of(risk, "WorldQuant"))
check("two different JDs -> a different order",
      [l.text for s in ml.sections for l in s.lines] !=
      [l.text for s in risk.sections for l in s.lines])

all_text = " ".join(l.text for s in ml.sections for l in s.lines)
# THE FOUNDING RULE OF THE WHOLE CV LAYER, and this is where it is guarded.
# The machine may CUT and REORDER Vin's words; the machine may NOT add a word
# Vin never wrote.
#
# The old test demanded that a printed sentence appear VERBATIM in the
# original CV. Strict, but strict in the wrong place: it also forbade dropping
# the "I" at the start — an edit that adds nothing at all.
# This version demands something stronger: every WORD on the printed page has
# to be present in the original sentence. Dropping words is allowed; adding
# one breaks the test.
_goc_all = CV.replace("\n", " ")
_bia = []
for _s in ml.sections:
    if _s.kind not in ("experience", "project"):
        continue
    for _l in _s.lines:
        _goc = _l.goc or _l.text
        if _goc.strip()[:40] not in _goc_all:
            _bia.append(("the original sentence is not in the CV", _goc[:60]))
            continue
        _them = set(_l.text.lower().split()) - set(_goc.lower().split())
        # The first letter is capitalised -> 'the' becomes 'The'; compared in
        # lower case that edit produces no new word, so any extra word really
        # is invented.
        if _them:
            _bia.append((f"added the word(s) {sorted(_them)}", _l.text[:60]))
check("NOTHING INVENTED: every WORD printed is in a sentence Vin wrote — " + str(_bia[:2]),
      not _bia)
# And every edited sentence has to leave a trace — edit without recording it
# and there is no "before" to compare against, turning the before/after view
# into a one-way claim.
check("an edited sentence records the edit and the reason",
      all(l.sua and all(x.vi_sao for x in l.sua)
          for s in ml.sections for l in s.lines
          if s.kind in ("experience", "project") and l.goc and l.goc != l.text))
check("a failure never reaches the CV", "mistake was mine" not in all_text)
check("an opinion never reaches the CV", "means nothing" not in all_text)

skill_titles = [s.title for s in ml.sections if s.kind == "skill"]
# A SKILLS SECTION IS JUDGED BY CONTENT, NEVER BY NAME. The old rule was a set
# of two section names taken from one person's CV (`{"compute","method"}`); on
# another profile it missed exactly the section most worth dropping — "Soft —
# communication, teamwork".
check("a section WITH recognised skills is kept", "Programming" in skill_titles)
from jobbot.cv.rules import bo_muc_ky_nang as _bmk
check("a soft-skills section is dropped whatever it is called", _bmk("Soft", "communication, teamwork"))
check("an interests section is dropped", _bmk("Interests", "chess, running"))
check("an unfamiliar technology section is KEPT — dropping it loses something real",
      not _bmk("Hardware", "VHDL, oscilloscopes"))
check("a section with real skills is kept, whatever it is called",
      not _bmk("Compute", "deep learning, machine learning"))

check("the dropped sentences are recorded", len(ml.dropped) >= 4)
check("every dropped sentence carries a reason", all(why for _, why in ml.dropped))
check("the summary is assembled from facts, never written",
      "MSc Computational Finance" in ml.summary and "CFA Level I" in ml.summary)

print("\n[missing skills — an 'any of' list]")
JD_OR = {"requirements": [{"text": "Programming in any of: C++, Java, MATLAB, R or Python",
                           "met": True, "must": True, "evidence": ""}]}
either = build(PROFILE, JD_OR, "C++ Java MATLAB R Python")
check("with C++/Python present, Java/MATLAB/R do NOT count as missing",
      not ({"java", "matlab", "r"} & set(either.missing)))

JD_GAP = {"requirements": [{"text": "Experience with equities and derivatives pricing",
                            "met": False, "must": True, "evidence": ""}]}
gap = build(PROFILE, JD_GAP, "equities derivatives")
check("a real gap is still reported", {"equities", "derivatives"} & set(gap.missing))


print("\n[the block editor — editing one block leaves every other INTACT]")
from jobbot.cv.blocks import write_block

CV_IN = PROFILE["cv_text"]
base = [(b.kind, b.title, b.meta) for b in parse(CV_IN)]
check("the fixture profile has blocks to edit", len(base) >= 3)

for blk in parse(CV_IN):
    if blk.kind not in ("experience", "project"):
        continue
    out = write_block(CV_IN, blk.kind, blk.title, blk.meta, ["I built a walk-forward tester across 17 instruments.",
                        "Live drawdown ran 30% deeper than the model said."])
    got = [(b.kind, b.title, b.meta) for b in parse(out)]
    # THE INVARIANT: this is the easiest place to break. parse() recognises a
    # new block BY THE SHAPE of its heading line — a project needs " — ", an
    # experience needs trailing dates. Write the wrong shape and the block is
    # swallowed into the one above it and DISAPPEARS; write one that cannot be
    # located and it spawns a duplicate under the same name.
    check(f"[{blk.kind}] {blk.title[:26]} — the block list is unchanged", got == base)
    again = [b for b in parse(out) if b.title == blk.title]
    check(f"[{blk.kind}] {blk.title[:26]} — it reads back with the new content",
          bool(again) and again[0].lines == ["I built a walk-forward tester across 17 instruments.",
                        "Live drawdown ran 30% deeper than the model said."])

fresh = write_block(CV_IN, "project", "Regime Detector", "", ["I built a walk-forward tester across 17 instruments.",
                        "Live drawdown ran 30% deeper than the model said."])
made = [b for b in parse(fresh) if b.title == "Regime Detector"]
check("a new block can be added", bool(made))
check("the new block lands in the project section", bool(made) and made[0].kind == "project")
check("adding a block does NOT disturb the existing ones",
      all(x in [(b.kind, b.title, b.meta) for b in parse(fresh)] for x in base))
check("the new block enters the evidence index at once",
      any("Regime Detector" in e.where
          for e in __import__("jobbot.scoring.score", fromlist=["x"])
          .build_index({**PROFILE, "cv_text": fresh})))

print("\n[certifications — the section name is not printed twice]")
from jobbot.cv.blocks import parse as _parse
_cv = ("EDUCATION\n"
       "MSc Computational Finance — Royal Holloway Sep 2025 – Sep 2026\n"
       "Certifications — CFA Level I, October 2024 · IBM Data Science\n"
       "TECHNICAL SKILLS\n"
       "Programming — Python, C++\n")
_cert = [b for b in _parse(_cv) if b.kind == "cert"]
check("there is exactly one certifications block", len(_cert) == 1)
# render.py sets the section heading from the kind ("cert" ->
# "Certifications"). Keep that word in the body too and the printed copy has
# two stacked lines — measured on the real CV.
check("the body does NOT repeat the word Certifications",
      bool(_cert) and not _cert[0].lines[0].lower().startswith("certification"))
check("the content is intact",
      bool(_cert) and _cert[0].lines[0].startswith("CFA Level I"))
check("the label becomes the block title", bool(_cert) and _cert[0].title == "Certifications")

print("\n[renaming a CV block — it must not duplicate]")
from jobbot.cv.blocks import write_block as _wb, parse as _pp
_cv2 = ("SELECTED PROJECTS\n"
        "Alpha Research — a cross-sectional alpha signal on equity data\n"
        "Walk-forward by construction.\n")
# The route has to delete the OLD name before writing the NEW one:
# write_block looks up the new name, does not find it, and so only ADDS — the
# CV keeps both and the printed copy has two identical sections.
_renamed = _wb(_wb(_cv2, "project", "Alpha Research", "", []),
               "project", "Alpha Signal", "", ["a cross-sectional alpha signal"])
_titles = [b.title for b in _pp(_renamed) if b.kind == "project"]
check("only ONE block remains after the rename", len(_titles) == 1)
check("and it carries the new name", _titles == ["Alpha Signal"])
_srv3 = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("the route reads the 'was' field", 'form.get("was"' in _srv3)
check("and deletes the old block before writing", "was != title" in _srv3)

print("\n[a block title in a URL has to be URL-encoded]")
from urllib.parse import quote as _q
# THE BLOCK STORE HAS MOVED off the CV tab onto the Block editor — it has a
# home of its own there, where clicking a block edits it.
_lst = (Path(__file__).resolve().parent.parent
        / "src/jobbot/dashboard/views/cvsoan.py").read_text(encoding="utf-8")
# esc() makes text safe to display in HTML; it does NOT stop an & from cutting a parameter.
check("quote() is used for the URL parameter", "quote(b['title']" in _lst)
check("an & is encoded", _q("Research & Development", safe="") == "Research%20%26%20Development")

print("\n[A GAP: an experience block is never dropped whole]")
# Filtering blocks on "does it hit what this posting asks" is right for a
# PROJECT (optional, dropping one leaves no trace) but WRONG for EXPERIENCE:
# it punches a hole in the timeline. Measured on the real store: 6 of the top
# 12 CVs lost the "WorldQuant, Jan–Sep 2025" block entirely — the page being
# sent declaring a 9-month gap about itself.
# HBS/Accenture 2021 survey: nearly half of employers screen out a CV with a
# gap over 6 months. A loosely-related block costs three lines of paper.
_moi_viec = [b.title for b in parse(CV) if b.kind == "experience"]
for _cv_thu, _ten in ((ml, "JD deep learning"), (risk, "JD risk")):
    _ra = [x.title for x in _cv_thu.sections if x.kind == "experience"]
    check(f"{_ten}: every experience block kept ({len(_ra)}/{len(_moi_viec)})",
          len(_ra) == len(_moi_viec))
# A JD touching none of the blocks must ALSO drop none of them.
_la = build(PROFILE, None, "we sell industrial adhesives to the marine sector")
check("a completely off-topic JD punches no gap either",
      len([x for x in _la.sections if x.kind == "experience"]) == len(_moi_viec))

print("\n[marking up the CV page ITSELF]")
# The previous version drew the CV page and then listed every sentence again
# below — the same sentence twice, leaving the reader to match "sentence 3
# below" to one above.
from jobbot.cv.render import paper as _pp, dem_lai as _dl
from jobbot.cv.report import head as _hd, chi_tiet as _ct
from jobbot.cv.build import dang_ke as _dk
import re as _re2

_dl(); _to = _pp(ml, cham=True)
_dl(); _to_sach = _pp(ml)
check("unmarked -> the CV page is as clean as before", "cjump" not in _to_sach
      and "cvpaper" in _to_sach and "cham" not in _to_sach)
check("marked -> every sentence has its own anchor", _re2.search(r"id='cau1'", _to))
check("and a mark BY KIND OF WORK, not a decorative colour",
      "dsua" in _to or "dhong" in _to)
check("clicking a line opens the correction card RIGHT THERE", "class=cdet" in _to
      and "class=ccard" in _to)
check("the keywords this posting ASKS FOR are highlighted inside the sentence", "'kw'" in _to or "kw " in _to)
check("the ORIGINAL is already in the DOM for the Before/After toggle", "class=ctruoc" in _to)

# ONE PLACE PER SENTENCE. A sentence may appear only on the page; the section
# below says what the page cannot (what the posting asks, why it was edited)
# and does NOT reprint the sentence.
_dl(); _to2 = _pp(ml, cham=True); _duoi = _ct(ml)
_cau_dai = [l.text for s2 in ml.sections for l in s2.lines
            if s2.kind in ("experience", "project") and len(l.text) > 40]
if _cau_dai:
    _c0 = _cau_dai[0][:40]
    check("the sentence is NOT reprinted in the detail section", _c0 not in _duoi)

# A DEAD LINK. The red pen on the page and the detail block have to ask THE
# SAME question; asked in two places they drift apart and clicking goes
# nowhere — silently.
# ONE PLACE PER SENTENCE. The correction card sits RIGHT ON the line, so the
# section below must NOT repeat each sentence any more — repeating it makes
# the reader read twice and match them up themselves.
check("the section below no longer repeats each sentence", "class='gcau" not in _duoi
      and "class=gcau" not in _duoi)
check("the section below holds only what belongs to no single sentence",
      "the profile cannot answer" in _duoi
      or "The rules do not allow" in _duoi
      or _duoi.strip().startswith("<div class=cvaudit>"))
check("only a sentence WITH SOMETHING TO SAY becomes a card — one place decides",
      _dk.__module__ == "jobbot.cv.build")

# THE BEFORE/AFTER TOGGLE uses a sibling selector, so the checkbox has to be
# A SIBLING of the CV page. Put it inside a <div> and it is a grandchild, and
# the toggle silently does nothing.
_h = _hd(ml)
check("the Before/After checkbox sits OUTSIDE every <div> of the header",
      _h.index("id=cvtruoc") < _h.index("<div class=gtoggle>"))
check("the scoring section is wrapped in .cvaudit so it does not print",
      "<div class=cvaudit>" in _h)
check("but the Before/After toggle sits outside that wrapper",
      _h.index("id=cvtruoc") < _h.index("<div class=cvaudit>"))

print("\n[re-picking: the machine offers OTHER SENTENCES YOU WROTE, it writes none]")
from jobbot.cv.build import bench as _bench, _pick as _pk2
from jobbot.cv.blocks import Block as _Bk
from jobbot.cv.render import to_khoa as _tk

# THE BENCH = rule-abiding sentences in the profile this version did not
# pick. This is what makes "re-pick" a REAL choice rather than a promise.
_bg = _bench(PROFILE, ml)
check("there are bench sentences to swap to", len(_bg) > 0)
_tren_giay = {l.goc or l.text for s2 in ml.sections for l in s2.lines}
check("a bench sentence is NOT one already printed on the page",
      not any(b["text"] in _tren_giay for b in _bg))
check("every bench sentence IS A SENTENCE FROM THE PROFILE — the machine invents none",
      all(b["text"][:38] in CV.replace("\n", " ") for b in _bg))
check("sentences hitting what this posting asks come first",
      not _bg or len(_bg[0]["trung"]) >= len(_bg[-1]["trung"]))
check("every bench sentence states WHAT SWAPPING TO IT GAINS",
      all("trung" in b and "khoi" in b for b in _bg))

# PIN / DROP: the person's choice beats the machine's ordering.
_kh = _Bk(kind="experience", title="X", meta="",
          lines=[f"Built system number {_i} with Python daily." for _i in range(6)])
_thuong = [l.text for l in _pk2(_kh, set(), {}, 2)]
_ghim = [l.text for l in _pk2(_kh, set(), {}, 2,
                              chon={"pin": [_kh.lines[5]]})]
check("pinning a sentence -> it goes on, unchanged weight or not",
      _kh.lines[5] in _ghim)
_gat = [l.text for l in _pk2(_kh, set(), {}, 2, chon={"drop": [_thuong[0]]})]
check("dropping a sentence -> it leaves the version", _thuong[0] not in _gat)
check("pinning does NOT break the line ceiling — one page is still one page",
      len(_ghim) == 2)

print("\n[keyword highlighting: one glance says whether the page speaks to what they ask]")
_h = _tk("Built models in Python and managed portfolio risk.", {"python", "risk"})
check("it highlights words really present in the sentence", ">Python<" in _h and "kw" in _h)
check("the rest of the text is untouched", "Built models in" in _h)
check("nothing asked for means nothing highlighted",
      "kw" not in _tk("Built models in Python.", set()))
# Nested tags are broken HTML: "machine learning" and "learning" overlap.
_ml = _tk("deep learning and machine learning models",
          {"machine learning", "deep learning"})
check("opening and closing tags balance even with overlapping marks",
      _ml.count("<span") == _ml.count("</span>"))
# OVERLAPPING MARKS are ordinary: one phrase can be a keyword, inside the
# "missing a measurement" stretch, and inside the "too long" stretch at once.
# Wrapping them one after another produces crossing tags.
from jobbot.cv.rewrite import vet as _vt, sua as _sa
_t2 = "Built two systems in MQL5 and Python: signals and risk."
_, _ds = _sa("I built two systems in MQL5 and Python: signals and risk.")
_h2 = _tk(_t2, {"python", "risk"}, _vt(_t2, ["python", "risk"], {"python", "risk"}, _ds))
check("overlapping marks still yield flat, balanced HTML",
      _h2.count("<span") == _h2.count("</span>"))
check("one phrase CAN carry several labels at once", "kw vthieu_so" in _h2)
# The user's text has to be escaped — a company name with an & is ordinary.
check("the text is still escaped",
      "&amp;" in _tk("Risk & return with Python", {"python"}))

print("\n[MARKS: underline the exact PHRASE, never the whole line]")
# This is where the previous version was wrong: it marked at LINE level with a
# 2px left border, and measured 0 marks landing ON ANY WORDS. Opening the CV
# you saw a few green lines with no idea what was wrong, and had to click each
# line to find out — the exact opposite of a marked-up page.
from jobbot.cv.rewrite import vet as _vt3, sua as _sa3, DAI_NHAT as _DN

# MISSING A NUMBER: underline the verb phrase — where the number SHOULD have
# been. A blank cannot be underlined, but the place it belongs can.
_t = "Built two systems in MQL5 and Python: signals and risk."
_v = _vt3(_t, ["python"], {"python"})
_ts = [x for x in _v if x.loai == "thieu_so"]
check("an achievement missing a number -> it has a mark", len(_ts) == 1)
check("the mark stops at the end of the first clause, it does not swallow the sentence",
      _ts and _t[_ts[0].dau:_ts[0].cuoi] == "Built two systems in MQL5 and Python")
check("and it says WHERE to put the number", _ts and "right here" in _ts[0].lam_gi)
check("with a number present it is NOT underlined",
      not [x for x in _vt3("Built 17 systems in Python.", ["python"], {"python"})
           if x.loai == "thieu_so"])
# KNOWLEDGE is not asked for a number — 12 of 16 sentences in the profile are knowledge.
check("a knowledge sentence is NOT underlined for a missing number",
      not [x for x in _vt3("A random train/test split leaks.", [], set())
           if x.loai == "thieu_so"])

# TOO LONG: underline EXACTLY THE EXCESS, from where the eye starts to slide — never the whole sentence.
_dai = "Built " + "x" * (_DN + 40)
_qd = [x for x in _vt3(_dai, [], set()) if x.loai == "qua_dai"]
check("too long -> underlined from exactly where the ceiling is passed", _qd and _qd[0].dau == _DN)
check("and not from the start of the sentence", _qd and _qd[0].dau > 0)

# THE MACHINE EDITED IT: mark the first word — where the "I" was just cut.
_, _ds3 = _sa3("I built two systems.")
_ms = [x for x in _vt3("Built two systems.", [], set(), _ds3) if x.loai == "da_sua"]
check("the machine edited a word -> it marks exactly the first word", _ms and _ms[0].dau == 0)

# EVERY MARK has to carry something doable, not a verdict.
check("every mark carries A SPECIFIC FIX",
      all(x.lam_gi and len(x.lam_gi) > 15 for x in _vt3(_t, ["python"], {"python"})))

# THE COUNTER BAR: opening the CV says how many spots there are, without clicking each line.
from jobbot.cv.report import cho_xem as _cx
_ds4 = _cx(ml)
check("the spots on the whole page can be counted", isinstance(_ds4, list))
check("counted by SPOT, not by sentence — one sentence can hold two jobs",
      all(len(x) == 3 and isinstance(x[2], int) for x in _ds4))
_h4 = _hd(ml)
check("the header bar says outright how many spots to look at", "spots to look at" in _h4)
check("and there is a legend, so the underlines are not a riddle",
      "glegend" in _h4 or not _ds4)

print("\n[A ROUND TRIP: saving one sentence must SWALLOW no other]")
# TWO REAL BUGS, both losing data, both with one root: `parse` and `_bounds`
# each guessed their own version of "which line opens a new project block".
from jobbot.cv.blocks import write_block as _wb2, parse as _ps2, _bounds as _bd2

_cv2 = ("SELECTED PROJECTS\nQuant Trading Studio\n"
        "the whole pipeline turned into something you can run.\n"
        "The Number That Lied\nKeep the best of many models.\n")

# BUG 1 — `_bounds` only stopped at a line containing " — ", while write_block
# writes a project name BARE on its own line. So saving one project wiped
# every project below it.
check("the block boundary stops in the right place, it does not swallow to end of file",
      _bd2(_cv2.splitlines(), "Quant Trading Studio") == (1, 3))
_sau2 = _wb2(_cv2, "project", "Quant Trading Studio", "",
             ["the whole pipeline turned into something you can run."])
check("saving one project does NOT delete the project below", "The Number That Lied" in _sau2)
check("and its sentence is intact", "Keep the best of many models." in _sau2)

# BUG 2 — a sentence the user saved into a block's body was read back as A
# BLOCK NAME, spawning an empty project, and that sentence was NEVER printed
# again. It really happened on Vin's profile with the sentence "Improved
# research frameworks, data pipelines".
_cau2 = "Improved research frameworks, data pipelines"
_sau2 = _wb2(_cv2, "project", "Quant Trading Studio", "",
             ["the whole pipeline turned into something you can run.", _cau2])
_pj2 = [b for b in _ps2(_sau2) if b.kind == "project"]
check("the sentence just saved sits in the block BODY, it does not become a block name",
      any(_cau2 in l for b in _pj2 for l in b.lines))
check("and it spawns NO empty block", all(b.lines for b in _pj2))
check("the project block count is unchanged", len(_pj2) == 2)
# A sentence opening with AN ACTION VERB is never a project name — not even
# when it carries a dash and looks exactly like a heading.
from jobbot.cv.blocks import mo_khoi_project as _mkp
check("a sentence with a dash that opens with a verb -> still A SENTENCE",
      not _mkp("Improved research frameworks — cut runtime to 90 s.", None))
check("while a real project name is still recognised",
      _mkp("Quant Trading Studio", None)
      and _mkp("The Number That Lied — MSc dissertation, PyTorch.", None))

print("\n[TAILORING DEPTH: reorder your own words, adding and removing none]")
# Measured on the real store: 98 DIFFERENT requirement sets across 120
# postings, yielding only 19 distinct CVs — because the skills sections, the
# densest part of the page for keywords, were poured out verbatim in profile
# order and never touched. Reordered: 19 -> 46 -> 68.
from jobbot.cv.build import _tach_mon as _tm, _xep_mon as _xm, _la_danh_sach as _lds

_ky = "Python (pandas, NumPy, PyTorch), C++, SQL, MQL5, Excel."
check("NEVER cut inside brackets — 'Python (pandas, NumPy)' is ONE item",
      _tm(_ky.rstrip(".")) [0] == "Python (pandas, NumPy, PyTorch)")
check("and it splits into the right number of items", len(_tm(_ky.rstrip("."))) == 5)

_sql = _xm(_ky, {"sql"})
check("the item this posting asks for moves to the FRONT of the line", _sql.startswith("SQL,"))
# NOT ONE WORD MAY BE LOST. This is a CV going to an employer.
import re as _reX
check("reordering loses no word",
      sorted(_reX.findall(r"\w+", _ky)) == sorted(_reX.findall(r"\w+", _sql)))
check("the full stop stays at the end of the LINE, not stuck to the last item", _sql.endswith("."))
check("a posting asking for nothing leaves the order untouched", _xm(_ky, set()) == _ky)
check("a list under 3 items is not touched", _xm("Python, SQL", {"sql"}) == "Python, SQL")

# THE REAL GATE: a PROSE line must not be reordered. My first version
# reordered every line, and the real profile's "Compute" section is a piece of
# prose — reordering it turns AN ARGUMENT inside out into nonsense, on the
# page being sent. 80 of 120 CVs were hit.
_van = ("a GPU is fast at many simple operations at once, which suits deep "
        "learning; most classical ML models run slower on one because moving "
        "the data costs more than the speed-up.")
check("it recognises a PROSE line, not a list", not _lds(_tm(_van)))
check("and leaves it alone", _xm(_van, {"machine learning"}) == _van)
check("while a real list is recognised",
      _lds(_tm("maximum drawdown, Sharpe ratio, risk limits, portfolio construction")))

# THE THREE LEVELS have to yield THREE DIFFERENT RESULTS — a knob that changes
# nothing is decoration, and this app has already dropped one of those
# (keyword density, changing 0 of 60 CVs).
from jobbot.core import prefs as _pfX
check("all three tailoring levels are named", set(_pfX.RIENG) == {"chung", "vua", "rieng"})

print("\n[CV SECTION NAMES — the app has to understand SOMEBODY ELSE'S CV, not only the author's]")
from jobbot.cv import blocks as _bl
_mau = ("Jane Doe\nlondon\n\n{}\n"
        "Built a pipeline in Python processing 2M rows.\n\nEDUCATION\nBSc\n")
# Really measured before the fix: the same CV with only the heading line
# changed scored 92 -> 22 and lost its experience block entirely — with not
# one word of warning.
for _ten, _mong in (("EXPERIENCE", "experience"),
                    ("WORK EXPERIENCE", "experience"),
                    ("Experience", "experience"),
                    ("EMPLOYMENT HISTORY", "experience"),
                    ("EXPERIENCE:", "experience"),
                    ("Professional Experience", "experience"),
                    ("Career History", "experience"),
                    ("Projects", "project"),
                    ("SELECTED PROJECTS", "project"),
                    ("TECHNICAL SKILLS", "skill"),
                    ("Core Competencies", "skill"),
                    ("CERTIFICATIONS", "cert"),
                    ("Academic Background", "education")):
    _ks = [b.kind for b in _bl.parse(_mau.format(_ten))]
    check(f"«{_ten}» -> {_mong} (ra {_ks})", _mong in _ks)
# THE SYSTEMIC LATCH, and it is the one that matters: a table of section names
# only knows the spellings SOMEBODY THOUGHT OF. Tomorrow someone writes
# "BERUFSERFAHRUNG" and it is mute again. This latch does not need to know
# what the section is called.
check("a long CV yielding no block at all -> SPEAK UP",
      _bl.khong_hieu("x" * 600, []))
check("a short CV (someone trying it out) does not trigger it", not _bl.khong_hieu("abc", []))
check("a CV it understands does not trigger it",
      not _bl.khong_hieu(_mau.format("EXPERIENCE"),
                         _bl.parse(_mau.format("EXPERIENCE"))))

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
