"""Test M0 — the user profile. Run: python3 tests/test_profile.py"""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db
import os as _os
from jobbot.profile import store
from jobbot.profile.schema import INGEST_GATE, SECTIONS, all_questions, section_by_id
from jobbot.dashboard.server import _form_to_answers

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

print("\n[schema]")
qs = all_questions()
ids = [q.id for s in SECTIONS for q in s.questions]
check("no duplicate question id", len(ids) == len(set(ids)))
check("every choice question has options", all(
    q.options for q in qs.values() if q.kind in ("single", "multi")))
check("the ingest gate's questions exist in the schema", all(q in qs for q in INGEST_GATE))
check("job_titles is free text, not a fixed list",
      qs["job_titles"].kind == "longtext" and not qs["job_titles"].options)
# The three DEAD questions of the old project feature (proof_jds,
# existing_projects, project_numbers) are gone — nowhere in the app read
# them. The project feature came back in a different shape: BLOCKS, written
# straight into cv_text, which is what the scorer and the CV builder really
# read.
check("the three dead questions are gone",
      not any(q in all_questions() for q in
              ("proof_jds", "existing_projects", "project_numbers")))
check("experience & projects are sections of THE PROFILE — that is personal information",
      section_by_id("kinh_nghiem") is not None
      and section_by_id("project") is not None)
check("and they are stored as cv_text blocks, with no copy",
      all_questions()["experience_blocks"].block_kind == "experience"
      and all_questions()["project_blocks"].block_kind == "project")
# Once the CV import has extracted the blocks it has to COUNT AS DONE.
# Looking only at the profile_answer table has Home reporting "0/1 — not
# done" while the data is already there.
_cv_khoi = ("DAC VINH NGUYEN\n\nEXPERIENCE\n"
            "Quant Analyst — Schonfeld Jan 2025 – Sep 2025\n  did a thing\n")
check("a block in cv_text means that question is answered",
      store.has_answer({"cv_text": _cv_khoi}, all_questions()["experience_blocks"]))
check("no block means it is not",
      not store.has_answer({"cv_text": _cv_khoi}, all_questions()["project_blocks"]))
check("and the experience section counts as DONE",
      store.is_section_done({"cv_text": _cv_khoi}, section_by_id("kinh_nghiem")))
check("work_auth belongs to the goals section, not to identity",
      any(q.id == "work_auth" for q in section_by_id("muc_tieu").questions))
check("no Vietnam-specific market option is left",
      not any(o.value.startswith("vn_") for q in all_questions().values() for o in q.options))
check("no required question sits outside the ingest gate",
      {q.id for q in qs.values() if q.required} == set(INGEST_GATE))

print("\n[storage]")
with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "t.db")

    check("an empty DB -> an empty profile", store.load(conn) == {})
    check("an empty DB -> cannot search yet", not store.can_ingest({}))
    check("it names exactly what is missing", store.missing_for_ingest({}) == list(INGEST_GATE))

    store.save(conn, {"job_titles": "Backend Engineer"}, "t")
    check("missing markets + work_auth -> still blocked",
          store.missing_for_ingest(store.load(conn)) == ["markets", "work_auth"])

    store.save(conn, {"markets": ["uk_remote"], "work_auth": "citizen"}, "t")
    answers = store.load(conn)
    check("all 3 answered -> the gate opens", store.can_ingest(answers))
    check("the old answer is carried over", answers["job_titles"] == "Backend Engineer")
    check("history keeps 2 versions", len(store.history(conn)) == 2)

    store.save(conn, {"khong_ton_tai": "x"}, "junk")
    check("a question outside the schema is ignored", "khong_ton_tai" not in store.load(conn))

    check("the next section is in the right order", store.next_section("muc_tieu").id == "rang_buoc")
    check("the last section -> none", store.next_section(SECTIONS[-1].id) is None)
    conn.close()

print("\n[reading the form]")
a = _form_to_answers({"markets": ["uk_remote", "HACK"],
                      "markets__other": ["Ireland, Netherlands"]}, "muc_tieu")
check("a value not in the options is dropped", "HACK" not in a["markets"])
check("a valid value is kept", "uk_remote" in a["markets"])
check("the free-text field is merged in", a["markets"] == ["uk_remote", "Ireland", "Netherlands"])

b = _form_to_answers({"work_auth__other": ["Graduate visa, expires 03/2027"]}, "muc_tieu")
check("a single-choice question takes the free-text field too", b["work_auth"] == "Graduate visa, expires 03/2027")

c = _form_to_answers({"job_titles": ["  Backend Engineer\nSWE  "]}, "muc_tieu")
check("text is whitespace-trimmed", c["job_titles"] == "Backend Engineer\nSWE")



print("\n[a blocking gate has to SAY SO, never give up silently]")
# A new user presses Run with an empty profile: run_scan used to `return`
# silently, the API still answered "running…", the journal was empty and no
# posting came back — an endless wait.
import os as _os
_tmp = tempfile.mkdtemp()
# JOBBOT_DATA_DIR, NOT JOBBOT_DB — no such variable exists. The old version
# typed the name wrong, so this test ran straight into THE REAL DB: with the
# profile still empty it stayed green (the gate closed, the scan refused), but
# the moment the profile passed the gate it REALLY SCANNED — 2,226 postings
# written into the user's DB purely by running a test.
_os.environ["JOBBOT_DATA_DIR"] = _tmp
try:
    # And check again rather than trusting the assignment: this test calls
    # run_scan, i.e. it can open the network and write thousands of rows. One
    # wrong path once and real data is damaged.
    from jobbot.core.paths import db_path as _dbp
    assert str(_dbp()).startswith(_tmp), f"the test is pointing at THE REAL DB: {_dbp()}"
    from jobbot.core import journal as _journal
    from jobbot import scan_runner as _sr
    _conn = db.connect()
    db.migrate(_conn)
    _journal.log.open()
    _noi = []
    _kq = _sr.run_scan(log=_noi.append, chrome_sources=False, deep=False)
    check("an empty profile refuses the scan", _kq["ok"] is False)
    check("and it SAYS why", bool(_noi) and "profile is incomplete" in _noi[0])
    check("the reason names the missing questions",
          bool(_noi) and all(all_questions()[q].text[:20] in _noi[0]
                             for q in _kq["missing"]))
    _dong = _conn.execute(
        "SELECT COUNT(*) FROM audit WHERE level='warn' AND detail LIKE '%cannot scan yet%'"
    ).fetchone()[0]
    check("and it is written to the journal", _dong >= 1)
finally:
    _os.environ.pop("JOBBOT_DATA_DIR", None)


print("\n[importing a CV has to OPEN THE GATE, not just fill in the identity]")
# The import used to extract 9 fields with NOT ONE of them in the gate
# (job_titles, markets, work_auth) — after importing a CV nothing could run,
# and it all still had to be typed by hand.
from jobbot.profile.import_cv import propose as _propose
_cv = """DAC VINH NGUYEN
London, United Kingdom | vin@example.com | +44 7000 000000

EXPERIENCE
Quantitative Analyst Intern — Schonfeld
  Built an analyst dashboard for the risk team using Python and pandas.
Research Consultant — WorldQuant BRAIN

TECHNICAL SKILLS
Python, pandas, SQL, machine learning, backtesting

References available on request.
"""
_p = {x.field: x.value for x in _propose(_cv, {})}
check("it proposes job titles", "job_titles" in _p)
# The two rules below came out of a REAL CV read badly: the job title +
# company + dates were ON ONE LINE (81 characters), and there was a SELECTED
# PROJECTS section that looked exactly the same.
_that = """DAC VINH NGUYEN
London, United Kingdom

EXPERIENCE
Founder / Quantitative Developer — Algorithmic Trading Startup Jan 2024 – Present
  Built the whole pipeline end to end.
Research Consultant — WorldQuant (BRAIN platform) Jan 2025 – Sep 2025

SELECTED PROJECTS
Quant Trading Studio — the whole pipeline turned into something a firm could run

TECHNICAL SKILLS
Python, pandas
"""
_pt = {x.field: x.value for x in _propose(_that, {})}
_tt = (_pt.get("job_titles") or "").splitlines()
check("a long line (title + company + dates) is still extracted",
      "Founder / Quantitative Developer" in _tt)
check("the trailing dates are cut", "Research Consultant" in _tt)
check("a project name under SELECTED PROJECTS is NOT taken as a job title",
      not any("Quant Trading Studio" in t for t in _tt))
check("the title is read correctly, with the company dropped",
      _p.get("job_titles", "").splitlines()[:1] == ["Quantitative Analyst Intern"])
check("a description sentence is NOT taken as a job title",
      "Built an analyst dashboard" not in _p.get("job_titles", ""))
check("'References available on request' is NOT taken either",
      "References" not in _p.get("job_titles", ""))
check("it proposes markets from the location",
      _p.get("markets") == ["uk_onsite", "uk_remote"])
check("it proposes seniority from the words on the CV", "intern" in (_p.get("seniority") or []))
# This is A DELIBERATE rule, not an omission: right to work is a legal fact
# about a person, the CV does not say it, and a wrong guess ruins the whole
# application.
check("it NEVER guesses right to work", "work_auth" not in _p)
_con = [q for q in INGEST_GATE if q not in _p]
check("after importing exactly 1 question is left to answer by hand", _con == ["work_auth"])
# It never overwrites what the user filled in themselves.
_p2 = {x.field for x in _propose(_cv, {"job_titles": "Quant Researcher"})}
check("a field already filled is not proposed over", "job_titles" not in _p2)
# ONE exception, deliberately: cv_text. "Import a new CV" plainly means
# replacing the old one, and the paste-a-CV field is gone from the form —
# refuse the replacement here and the CV is frozen forever, with no way left
# to change it.
_p3 = {x.field: x for x in _propose(_cv, {"cv_text": "OLD CV", "full_name": "X"})}
check("importing a new CV CAN replace the old one", "cv_text" in _p3)
# THE GENERAL RULE. store.save() filters by schema, so EVERY field the import
# proposes has to be in the schema — one missing and it silently never gets
# saved, while the review screen still ticks green.
_lac = [f for f in _p if f not in all_questions()]
check(f"every field the import proposes CAN be saved {_lac or ''}", not _lac)
check("and it says outright that it replaces", "REPLACES the stored CV" in _p3["cv_text"].note)
check("other fields still obey the no-overwrite rule", "full_name" not in _p3)
# cv_text is NOT drawn on the form, but it MUST stay in the schema.
# store.save() filters by schema — remove it and it silently stops being
# savable. A whole CV was lost to exactly this: the import reported "13
# fields" while only 12 answers reached the DB.
check("cv_text stays in the schema so it CAN be saved", "cv_text" in all_questions())
check("but it is not drawn on the form", all_questions()["cv_text"].hidden)
_tmpdb = tempfile.mkdtemp()
_env_cu = _os.environ.get("JOBBOT_DATA_DIR")
_os.environ["JOBBOT_DATA_DIR"] = _tmpdb
try:
    import importlib as _il2
    from jobbot.core import paths as _p2
    _il2.reload(_p2)
    _c2 = db.connect(Path(_tmpdb) / "t.db")
    db.migrate(_c2)
    store.save(_c2, {"cv_text": "EXPERIENCE\nQuant Analyst — X Jan 2025 – Sep 2025\n"}, "t")
    check("cv_text saves and reads back",
          "Quant Analyst" in str(store.load(_c2).get("cv_text") or ""))
    _c2.close()
finally:
    if _env_cu is None:
        _os.environ.pop("JOBBOT_DATA_DIR", None)
    else:
        _os.environ["JOBBOT_DATA_DIR"] = _env_cu
    import importlib as _il3
    from jobbot.core import paths as _p3
    _il3.reload(_p3)

print("\n[education & certifications — THE SHAPE has to match the grammar the system reads]")
# cv/build.py does `certs.splitlines()[0]` to take the strongest
# certification, and score.py reads by line too. A real CV writes "A · B · C"
# on ONE line — kept as it is, the machine counts 1 certification where there
# are 3, and the CV packs the whole run in as one "fact".
_cv2 = """DAC VINH NGUYEN
London, UK

EDUCATION
MSc Computational Finance — Royal Holloway, University of London 2025 – 2026
Investment & Portfolio Management 86 · Data Analysis 83
BA (Hons) Advanced Finance — National Economics University, Vietnam
·
Certifications — CFA Level I, October 2024 · IBM Data Science · IBM Machine Learning
"""
_d2 = {x.field: x.value for x in _propose(_cv2, {})}
_ce = str(_d2.get("certifications", "")).splitlines()
check("one certification per line", len(_ce) == 3)
check("none is swallowed", "IBM Machine Learning" in _ce)
_ed = str(_d2.get("education", "")).splitlines()
check("a junk line of just a bullet is dropped", "·" not in _ed)
check("but the module-grades line is kept",
      any("Investment & Portfolio Management" in l for l in _ed))
# And the certifications field has to be A TAG BOX, so editing by hand cannot
# break that shape either.
check("certifications is a tag box joined by newlines",
      all_questions()["certifications"].tags == "\n")
# The education grammar has to be STATED where people type — apply/answer
# needs exactly that shape to fill in a graduation date on an application.
check("the education field states the grammar the system reads",
      "ONE DEGREE PER LINE" in all_questions()["education"].why)

print("\n[education — ONE grammar, shared by the writer and the reader]")
# This field CARRIES WEIGHT: apply/answer reads a graduation date out of it to
# fill in applications. The form writes with line(), the machine reads with
# educations() — let them drift and the form writes something the machine
# cannot read, and Vin picks the date again on every application.
from jobbot.apply.answer import educations as _eds, line as _eline, education as _ed1
from jobbot.profile.schema import ROWS as _ROWS
check("the education field is of kind ROWS, not raw text",
      all_questions()["education"].kind == _ROWS)
_l = _eline("MSc", "Computational Finance", "Royal Holloway", "Sep 2025", "Sep 2026", "IPM 86")
_back = _eds(_l)[0]
check("written and read back gives the right degree", _back.degree == "MSc")
check("the right discipline", _back.discipline == "Computational Finance")
check("the right school", _back.school == "Royal Holloway")
check("THE MONTH survives — the thing applications ask for",
      (_back.start_month, _back.start_year) == (9, 2025)
      and (_back.end_month, _back.end_year) == (9, 2026))
check("and it no longer reports a missing month", _ed1(_l).missing == [])
check("the note becomes a secondary line, not a second degree",
      len(_eds(_l)) == 1 and "IPM 86" in _back.note)
# A real CV writes module grades FLUSH LEFT, not indented. Misread, it shows
# up as a degree called "Investment".
_ban = ("MSc Computational Finance — Royal Holloway, 2025 – 2026\n"
        "Investment & Portfolio Management 86 · Data Analysis 83\n"
        "BA (Hons) Advanced Finance — National Economics University")
_hai = _eds(_ban)
check("a flush-left module-grades line is NOT read as a degree", len(_hai) == 2)
check("but as a note on the degree right above it",
      "Investment & Portfolio Management 86" in _hai[0].note)


print("\n[the job title store is extracted from REAL POSTINGS, never typed]")
# The question says "write them EXACTLY as the posting does", so the only
# correct source is the postings themselves. A list typed into the source is
# wrong from the day it is written and rots from there.
from jobbot.profile.titles import extract as _extract
from jobbot.profile.schema import suggestions as _sug
check("the schema has NO hand-typed job title list", _sug("titles") == [])
check("the skill store still comes from the scoring vocabulary", len(_sug("skills")) > 20)
# The industry store is NOT hand-typed either: it is exactly the industry set
# projects/inventory.py uses to label real postings. A separate list for the
# screen lets the user pick an industry the machine cannot recognise.
from jobbot.scoring.vocab import INDUSTRY as _IND
check("the industry store comes from the engine ACTUALLY used to recognise industries",
      _sug("industries") == sorted(_IND))
check("the industry field is a tag box", all_questions()["industries"].tags == ", ")
check("and it says outright that empty = no industry preference",
      "Leaving it EMPTY" in all_questions()["industries"].why)

# Real titles look like this — used as they are, they are useless as suggestions.
_that = ["2027 Point72 Academy Investment Analyst Summer Internship - Japan (BCF)",
         "Investment Analyst", "Investment Analyst - London",
         "Quantitative Researcher", "Quantitative Researcher (Systematic)",
         "Quantitative Researcher — New York", "Software Engineer, Platform",
         "Software Engineer", "Software Engineer - Backend"]
_cum = dict(_extract(_that, least=2))
check("it extracts A ROLE PHRASE rather than keeping the whole title",
      "Quantitative Researcher" in _cum)
check("a trailing location is dropped", _cum.get("Quantitative Researcher") == 3)
check("a bracketed part is dropped", "Investment Analyst" in _cum)
check("a phrase carrying a year is NOT kept", not any(c[0].isdigit() for c in _cum))
check("a phrase has to END in a role word",
      all(c.split()[-1].lower() in
          {"analyst","engineer","scientist","developer","researcher","manager",
           "trader","strategist","consultant","associate","specialist",
           "architect","lead","intern","quant","technologist","administrator"}
          for c in _cum))
# A floor: a phrase seen once is usually one company's own programme name.
check("there is a posting-count floor, a phrase seen once is not taken",
      all(v >= 2 for v in _cum.values()))

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
