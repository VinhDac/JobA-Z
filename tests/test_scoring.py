"""Test step 2 — the match score.  python3 tests/test_scoring.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.scoring import extract
from jobbot.scoring.score import _degrees_needed, _years_needed, build_index, score_job

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

PROFILE = {
    "job_titles": "Quantitative Analyst\nData Scientist",
    "seniority": ["grad", "junior"],
    "years_real": "0-1",
    "education": "MSc Computational Finance — Royal Holloway, 2026\nBA Finance, GPA 3.59",
    "certifications": "CFA Level I — top 10% of global candidates",
    "skills_strong": "Python, pandas, SQL",
    "search_keywords": "machine learning, backtesting",
}

JD = """About the role
We do things.

Requirements:
· Strong knowledge of Python and pandas
· Degree in a quantitative discipline
· 5+ years of commercial experience
· Exceptional communication skills

Nice to have:
· Experience with kdb+

What we offer
· 25 days holiday
· Private healthcare
"""

print("\n[extracting the requirements]")
reqs = extract.requirements(JD)
texts = [r.text for r in reqs]
check("the bullets are picked up", len(reqs) == 5)
check("the benefits are dropped", not any("holiday" in t or "healthcare" in t for t in texts))
check("a nice-to-have is recognised", any(t.startswith("Experience with kdb") and not r.must
                               for t, r in zip(texts, reqs)))
check("the rest are required", sum(1 for r in reqs if r.must) == 4)
check("confidence is high with real bullets", extract.confidence(reqs) == "high")
check("an empty JD -> cannot be scored", extract.confidence(extract.requirements("")) == "none")

prose = ("We are a research firm. If you have experience in time series analysis "
         "and knowledge of Python we would like to hear from you. "
         "You will have 25 days holiday and private healthcare.")
preqs = extract.requirements(prose)
check("prose still yields requirements", len(preqs) >= 1)
check("prose -> low confidence", extract.confidence(preqs) == "low")
check("prose still drops the benefits sentence",
      not any("holiday" in r.text for r in preqs))

print("\n[degrees — a bug since fixed]")
check("'MS or PhD' takes BOTH, not just the highest",
      set(_degrees_needed("Undergraduate, MS, or PhD candidates")) >= {"phd", "masters"})
check("'PhD required' yields PhD only", _degrees_needed("PhD required") == ["phd"])
check("'database' is NOT read as a BA", _degrees_needed("experience with databases") == [])
check("'systems' is NOT read as an MS", "masters" not in _degrees_needed("distributed systems"))

print("\n[years]")
check("'5+ years' is read", _years_needed("5+ years of experience") == 5)
check("'3-5 years' is read", _years_needed("3-5 years required") == 3)
check("no years -> None", _years_needed("Strong Python") is None)

print("\n[strong / weak evidence]")
index = build_index(PROFILE)
labels = [e.where for e in index]
# THE JOB SEARCH FIELDS ARE NOT EVIDENCE. Their own label says "(not proof)",
# yet they were in the index, so a requirement counted as MET on the strength
# of what Vin typed into a JOB SEARCH field. Measured on the real store: 249
# lines across 153 of 472 postings met that way. "I want a job with Kafka" is
# not evidence that I know Kafka.
check("the JOB SEARCH KEYWORD field is kept out of the evidence index",
      not any("keyword" in l for l in labels))
check("the 'want to move into' field too",
      not any("want to move into" in l for l in labels))
check("but strong skills ARE in it", "your strong skills" in labels)
# A skill BEING LEARNT is different from a search field: it is a statement
# about yourself, only a weak one. Kept, marked weak — not thrown out the way
# a search field is.
_hoc = build_index({**PROFILE, "skills_weak": "rust"})
check("a skill being learnt is kept, at the WEAK level",
      any("still learning" in e.where and not e.strong for e in _hoc))

print("\n[scoring]")
result = score_job("Graduate Quantitative Analyst", JD, PROFILE)
by_text = {r["text"]: r for r in result["requirements"]}
check("Python is in the profile -> met",
      by_text["Strong knowledge of Python and pandas"]["met"] is True)
check("a quantitative degree -> met",
      by_text["Degree in a quantitative discipline"]["met"] is True)
check("5+ years against 0-1 -> not met",
      by_text["5+ years of commercial experience"]["met"] is False)
check("a soft skill -> NO verdict (kept out of the denominator)",
      by_text["Exceptional communication skills"]["met"] is None)
check("the evidence is quoted from the real profile",
      "Python" in by_text["Strong knowledge of Python and pandas"]["evidence"])
check("missing years -> capped at 55", result["score"] <= 55 and result["capped"])
check("the blocking line is named", len(result["blockers"]) == 1)
check("nice-to-haves are kept apart from requirements", result["breakdown"]["nice"]["total"] == 1)

soft = score_job("Graduate Quantitative Analyst",
                 JD.replace("· 5+ years of commercial experience\n", ""), PROFILE)
check("drop the years requirement and the score jumps", soft["score"] > result["score"])
check("aiming junior at a Senior posting -> a heavy deduction",
      score_job("Senior Quantitative Analyst", JD, PROFILE)["breakdown"]["level"]["points"] == 0)
check("a Graduate posting -> full marks", soft["breakdown"]["level"]["points"] == 20)

blank = score_job("Analyst", "We are a great company. Join us.", PROFILE)
check("a JD with no requirements -> NO invented score", blank["score"] is None)
check("and it says why", "Could not read" in blank["reason"])

print("\n[a profile MISSING a field must not bring the scorer down]")
# THE REAL BUG: "".splitlines() is [] and not [""], so judge_one took [0] and
# raised IndexError. It blew up INSIDE derive()'s transaction, rolling back
# the whole scan — a profile with no education filled in meant the whole
# pipeline dying silently.
_DEGREE_JD = ("Requirements:\n· A degree in a quantitative discipline\n"
              "· Strong Python\n· SQL\n")
for _missing in ["education", "skills_strong", "certifications", "years_real",
                 "seniority", "job_titles"]:
    _thin = {k: v for k, v in PROFILE.items() if k != _missing}
    try:
        _out = score_job("Data Scientist", _DEGREE_JD, _thin)
        check(f"missing {_missing!r} still scores", _out["score"] is not None)
    except Exception as _exc:                        # noqa: BLE001
        check(f"missing {_missing!r} still scores", False)
        print(f"       {type(_exc).__name__}: {_exc}")

check("a COMPLETELY empty profile does not bring it down either",
      score_job("Data Scientist", _DEGREE_JD, {}) is not None)
_empty = score_job("Data Scientist", _DEGREE_JD, {"education": ""})
_edu = [r for r in _empty["requirements"] if "degree" in r["text"].lower()]
check("and it says outright that the profile has no education",
      bool(_edu) and "nothing on your profile" in _edu[0]["evidence"])

print("\n[skills match by WORD, never by substring]")
# THE REAL BUG, the largest in the whole review: 'excel' is inside
# 'excellent', so 70 of 204 kept postings were tagged with the Excel skill
# purely because the JD said "excellent communication" — and the LARGEST
# project group on /projects grew out of that shadow, meaning the whole
# project-generation step was aiming at the wrong thing.
from jobbot.scoring.vocab import alias_hits
from jobbot.ingest.base import norm as _norm
_hits = lambda t: alias_hits(_norm(t))

for _text, _bad in [("Excellent communication skills", "excel"),
                    ("highly scalable systems", "scala"),
                    ("we build trust with clients", "rust"),
                    ("evaluation of trading models", "asset pricing"),
                    ("javascript front end", "java")]:
    check(f"{_text[:34]!r} does NOT yield {_bad!r}", _bad not in _hits(_text))

for _text, _want in [("Excel and VBA", "excel"),
                     ("Rust and C++", "rust"),
                     ("Scala on the JVM", "scala")]:
    check(f"{_text!r} still yields {_want!r}", _want in _hits(_text))

# Ban substrings outright and most of the CORRECT matches go — English
# inflects.
for _text, _want in [("backtesting engines", "backtesting"),
                     ("derivatives pricing", "derivatives"),
                     ("building data pipelines", "data pipeline"),
                     ("containerisation with docker", "docker"),
                     ("managing portfolios", "portfolio"),
                     ("running simulations", "backtesting")]:
    check(f"an inflected ending still matches: {_text!r}", _want in _hits(_text))

# The two layers have to read words THE SAME WAY — each used to keep its own
# copy of the rule.
from jobbot.cv.build import skills_in as _skills_in
_probe = "Excellent communication, Excel, backtesting and scalable pipelines"
check("cv.skills_in and scoring share one rule",
      _skills_in(_probe) == set(_hits(_probe)))

print("\n[names with punctuation: C++ · ci/cd · kdb+ — ONCE LOST ENTIRELY]")
# TWO bugs on top of each other meant 208 postings asking for C++ never
# matched, even with C++ on the CV:
#   norm() dropped every non-alphanumeric character -> "C++" became "c"
#   the alias pattern ended with \\b                 -> there is never a word
#                                             boundary after a '+', so even
#                                             keeping the + it still would not
#                                             match
from jobbot.ingest.base import norm as _nm
from jobbot.scoring.vocab import alias_hits as _ah
check("norm keeps the + in C++", "c++" in _nm("Strong C++ and Python"))
check("norm keeps the / in CI/CD", "ci/cd" in _nm("CI/CD pipelines"))
check("C++ matches", "c++" in _ah(_nm("Strong C++ and Python")))
check("ci/cd matches", "ci/cd" in _ah(_nm("CI/CD and Docker")))
check("C++ at the end of a sentence matches too", "c++" in _ah(_nm("experience with C++")))
# Loosening the boundary must NOT produce careless matches — this is the
# 'excel' inside 'excellent' class of bug, which has bitten once already.
check("'abc' does NOT yield c++", "c++" not in _ah(_nm("abc company")))
check("'arc welding' does NOT yield r", "r" not in _ah(_nm("arc welding")))
check("'excellent' still does NOT yield excel", "excel" not in _ah(_nm("excellent communication")))
check("'scalable' still does NOT yield scala", "scala" not in _ah(_nm("highly scalable")))

print("\n[a list with NO bullet marks — LinkedIn]")
# The real bug: LinkedIn returns the JD via innerText, and every <li> loses
# its '·'. The extractor recognised a list BY that mark and so returned
# nothing, and 46 of 204 kept postings — PIMCO, L&G, Smarkets — were reported
# as "could not read the requirements" while carrying a full list.
LINKEDIN = """Data Analyst

Nando's is on a journey to Create Lasting Happiness across the communities we work in.

What you'll bring

Writing complex SQL to query, transform and model data across our cloud platform
Building and maintaining data models in Dataform or a similar transformation tool
Building reports and dashboards in Looker or a similar BI tool for the business
Using Git as standard practice - branching, pull requests and code review
Applying relevant statistical methods to support analysis

Benefits

Competitive salary and non-contributory pension
25 days annual leave plus bank holidays
"""
reqs = extract.requirements(LINKEDIN)
check("the list is read even with no bullet marks", len(reqs) >= 4)
check("taken verbatim", any("Dataform" in r.text for r in reqs))
check("the source is marked 'list', not 'bullet'",
      all(r.source == "list" for r in reqs))
check("confidence is medium, not 'high'",
      extract.confidence(reqs) == "medium")
check("the benefits are NOT swallowed as requirements",
      not any("pension" in r.text.lower() or "annual leave" in r.text.lower()
              for r in reqs))
scored = score_job("Data Analyst", LINKEDIN, PROFILE)
check("and it produces a real score", scored["score"] is not None)

# A lone prose paragraph between two blank lines must NOT be read as a list item
PROSE_ONLY = """About us

We are a great company with a long history of doing interesting things.

We believe in people and in building software that lasts a long time.
"""
check("a lone paragraph is not read as a list",
      not [r for r in extract.requirements(PROSE_ONLY) if r.source == "list"])

print("\n[SENIORITY — it has to work for EVERYBODY, not just a grad profile]")
from jobbot.scoring.score import _level_fit as _lf, _bac_tieu_de as _bt, BAC as _BAC

def _diem(title, muc):
    return _lf(title, {"seniority": muc})

# The most important test in this block: the old version ONLY asked "are they
# aiming junior", so a profile aiming senior got 0.6 for every posting —
# including ones with "Graduate" in large letters in the title. Working
# correctly for one person is not working correctly.
check("aiming SENIOR: a senior posting scores high",
      _diem("Senior Software Engineer", ["senior"])[0] == 1.0)
check("aiming SENIOR: a graduate posting is ruled out, not 0.6",
      _diem("Graduate Software Engineer", ["senior"])[0] == 0.0)
check("aiming SENIOR: one step off scores half",
      _diem("Staff Engineer", ["senior"])[0] == 0.5)
check("aiming MID: a mid posting matches", _diem("Mid-level Developer", ["mid"])[0] == 1.0)
check("aiming LEAD: an internship is the furthest off",
      _diem("Summer Internship", ["lead"])[0] == 0.0)
check("aiming grad+junior: a senior posting is still ruled out as before",
      _diem("Senior Software Engineer", ["grad", "junior"])[0] == 0.0)
check("aiming grad+junior: a graduate posting is still 1.0 as before",
      _diem("Graduate Analyst", ["grad", "junior"])[0] == 1.0)

# Not knowing has to be SAID, and it has to say WHAT is not known.
check("a title that does not state a level -> 0.6, and it says so",
      _diem("Software Engineer", ["senior"]) == (0.6, "level not stated in the title"))
_d, _vi = _diem("Senior Software Engineer", [])
check("a profile leaving seniority blank -> still 0.6 but with THE REAL REASON",
      _d == 0.6 and "haven't said" in _vi)
check("stray free text in the profile does not make it lie",
      "haven't said" in _diem("Senior Software Engineer", ["cap-bac-la"])[1])

# "Program Manager" is NOT a graduate posting. Really measured: 34 postings
# in the DB matched "program|programme" without being graduate postings, and
# the old rule gave them 1.0 "explicitly graduate/junior" — senior postings
# jumping from 0 to 20 points.
check("«Program Manager» is not read as a graduate posting",
      _bt("Technical Program Manager") is None)
check("«Senior Technical Program Manager» is SENIOR, not graduate",
      _diem("Senior Technical Program Manager", ["grad", "junior"])[0] == 0.0)
check("but «Summer Analyst Programme» really is a graduate posting",
      _bt("2027 MUFG UK Summer Analyst Programme") == 0)
check("«Graduate Programme» likewise", _bt("Graduate Programme, Technology") == 0)

# Senior words the old version missed.
for _t in ("Portfolio Analytics Engineer - Vice President", "Chief of Staff",
           "Head of Engineering", "Director of Data"):
    check(f"«{_t[:34]}» is recognised as senior", _bt(_t) == 4)
check("«Early Careers» is recognised as entry level", _bt("Software Engineer, Early Careers") == 0)

# A title matching both ends of the ladder -> take the LOWER rung: losing a
# posting is worse than seeing a spare one.
check("a title with both graduate and senior -> counted as graduate",
      _bt("Graduate Programme — Senior Analyst track") == 0)

# The ladder has to cover EVERY option in the profile, with none missed.
from jobbot.profile.schema import all_questions as _aq
_o = _aq()["seniority"].options
_thieu = [x.value for x in _o if x.value not in _BAC]
check(f"every seniority option in the profile has a rung on the ladder{' — missing: ' + str(_thieu) if _thieu else ''}",
      not _thieu)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
