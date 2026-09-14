"""THE GAP block — write a sentence about what, and how many POSTINGS CLEAR."""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else: fail += 1; print(f"  FAIL {name}")

from jobbot.scoring.gap import tin_tron, thang, NAMED_TOOL, _tin

print("[the unit is POSTINGS CLEARED, not mentions]")
# One posting = a list of must lines. Cleared = EVERY line is answered. A line
# is answered when it asks for at least one thing you have — the "or" rule:
# the JD says "C++, Java or Python" and you have Python, so that line is done.
_t = [
    [({"python"}, False), ({"sql"}, False)],            # needs both python and sql
    [({"python", "java"}, False)],                      # python OR java
    [({"cloud"}, True)],                                # cloud only
]
check("everything present -> the posting clears", tin_tron(_t, {"python", "sql", "cloud"}) == 3)
check("one line short -> that posting does NOT clear", tin_tron(_t, {"python"}) == 1)
check("the OR rule: python alone answers 'python or java'",
      tin_tron(_t, {"python"}) >= 1)
check("nothing at all -> 0 postings", tin_tron(_t, set()) == 0)
check("adding a skill nobody asks for -> nothing changes",
      tin_tron(_t, {"python"}) == tin_tron(_t, {"python", "rust"}))

print("\n[WRITE / LEARN: split by rule, not by judgement]")
for _s in ("experience with AWS", "Docker and Kubernetes", "Power BI dashboards",
           "kdb+/q", "Tableau reporting", "Apache Spark"):
    check(f"names a product -> LEARN: {_s[:28]}", bool(NAMED_TOOL.search(_s)))
for _s in ("present findings to stakeholders", "build data pipelines",
           "strong analytical skills", "visualise results clearly"):
    check(f"stated generally -> WRITABLE: {_s[:28]}", not NAMED_TOOL.search(_s))

print("\n[the cumulative ladder: MARGINAL value, never a sum]")
import sqlite3, json
_db = sqlite3.connect(":memory:")
_db.row_factory = sqlite3.Row
_db.execute("CREATE TABLE posting (id INTEGER PRIMARY KEY, kept INT,"
            " realism TEXT, score_json TEXT)")
def _them(i, dong):
    _db.execute("INSERT INTO posting VALUES (?,1,'likely',?)",
                (i, json.dumps({"requirements":
                                [{"text": d, "must": True} for d in dong]})))
# Three postings, all three missing visualisation -> it unlocks all three AT ONCE.
for i in (1, 2, 3):
    _them(i, ["strong Python", "data visualisation skills"])
_them(4, ["strong Python", "experience with AWS"])
_db.commit()
_d = thang(_db, {"python"})
check("it counts the postings with must lines correctly", _d["tin"] == 4)
check("the base = how many postings already clear", _d["nen"] == 0)
_b = _d["buoc"]
check("the first rung is what unlocks THE MOST POSTINGS", _b and _b[0]["ky_nang"] == "visualisation")
check("and it states how many more it unlocks", _b and _b[0]["them"] == 3)
check("cumulative is the TOTAL after that rung, not a sum of rungs",
      _b and _b[0]["cong_don"] == 3)
# The second rung has only 1 posting left to unlock — MARGINAL value, not a
# standalone value.
check("a later rung counts only WHAT IS LEFT", len(_b) < 2 or _b[1]["them"] == 1)
check("cloud names AWS outright -> the LEARN label",
      all(x["viec"] == "hoc" for x in _b if x["ky_nang"] == "cloud"))

print("\n[two targets: writable tonight vs must be learnt]")
check("there is a WRITING-ONLY figure of its own", "chi_viet" in _d)
check("writing only is <= doing the whole table", _d["chi_viet"] <= (_b[-1]["cong_don"] if _b else 0))
check("and it counts the sentences to write correctly",
      _d["so_viet"] == sum(1 for x in _b if x["viec"] == "viet"))
_db.close()

print("\n[an EMPTY store must not bring it down either]")
_e = sqlite3.connect(":memory:"); _e.row_factory = sqlite3.Row
_e.execute("CREATE TABLE posting (id INTEGER PRIMARY KEY, kept INT,"
           " realism TEXT, score_json TEXT)")
_r = thang(_e, {"python"})
check("an empty store -> returns 0, does not blow up", _r["tin"] == 0 and _r["buoc"] == [])
_e.close()

print("\n[writing a new sentence: the machine clears the space, THE PERSON writes]")
from jobbot.scoring.gap import (CHO_TRONG, con_trong, goi_y, ho_hoi,
                                nen_nhap, qua_giong, qua_khu, ta_viec)
from jobbot.dashboard.views import cvsoan as _cs

_c2 = sqlite3.connect(":memory:"); _c2.row_factory = sqlite3.Row
_c2.execute("CREATE TABLE posting (id INTEGER PRIMARY KEY, kept INT,"
            " realism TEXT, score TEXT, company TEXT, title TEXT, score_json TEXT)")
def _t2(i, cty, dong):
    _c2.execute("INSERT INTO posting VALUES (?,1,'likely','90',?,'Analyst',?)",
                (i, cty, json.dumps({"requirements":
                                     [{"text": d, "must": True} for d in dong]})))
_t2(1, "Bonhill", ["Improve research frameworks, data pipelines and models"])
_t2(2, "Durlston", ["ETL across an Azure-hosted Data Lake"])
# Several postings copy the same stock sentence — a brief that repeats itself eats the readable space.
_t2(3, "Nhai Lai", ["Improve research frameworks, data pipelines and models"])
_c2.commit()
_chung, _rieng = ho_hoi(_c2, "data pipeline")
check("WRITABLE lines are separated from lines naming a product",
      len(_chung) == 1 and len(_rieng) == 1)
check("a repeated line is printed ONCE, even when two postings ask for it",
      [m["cong_ty"] for m in _chung] == ["Bonhill"])
check("a general line is one naming no product",
      _chung and "Azure" not in _chung[0]["chu"])
check("printed VERBATIM, never summarised",
      _chung and _chung[0]["chu"].startswith("Improve research frameworks"))
check("with the company name, so it is clearly a REAL requirement",
      _chung and _chung[0]["cong_ty"] == "Bonhill")
_nn = nen_nhap(_c2, "data pipeline")
_c2.close()

# THE DRAFT BASE: only a line DESCRIBING WORK converts into a CV sentence.
#
# The gap ladder's WRITE label says "this line names no product, so it can be
# said in your own words". Having said that and then offering only an empty
# box makes the label an empty promise — so the WRITE label has to come with
# a draft base.
check("a line describing WORK can be used as a base",
      ta_viec("Build and maintain data pipelines, ensuring data quality"))
check("a gerund opening also describes work",
      ta_viec("Developing and maintaining data pipelines and live processes"))
# Measured on the real store: 12 of 22 general lines asking for
# `visualisation` describe a quality. What CV sentence does "Interest in
# statistics" rewrite into?
check("a line describing a QUALITY does NOT",
      not ta_viec("Interest in statistics, data visualisation or modelling"))
check("not even with adjectives in front",
      not ta_viec("Solid experience with SQL, Excel and at least one BI tool")
      and not ta_viec("Detailed understanding of data mining and warehousing"))
check("and an -ing industry noun is not work either",
      not ta_viec("Engineering degree or equivalent industrial experience"))
check("the base comes from a REAL requirement line, with the company name",
      len(_nn) == 1 and _nn[0]["cong_ty"] == "Bonhill")

# THE GATE: the base is the employer's words VERBATIM. Saving them as they
# are does two kinds of damage — whoever screens reads the words from their
# own job ad, and the user has to defend a claim they never made.
_ne = "Build and maintain data pipelines, ensuring data quality and consistency"
check("a verbatim copy -> caught", qua_giong(_ne, _ne) == 1.0)
# Changing only the TENSE is still their line, not your account of your work.
check("only the tense changed -> still caught",
      qua_giong("Built and maintained data pipelines, ensuring data quality", _ne) >= 0.6)
check("a sentence on the SAME subject but about your own work -> passes",
      qua_giong("Rebuilt the research pipeline so a 40-minute reconciliation "
                "runs in 90 seconds over 17 feeds.", _ne) < 0.6)
check("your own real sentence -> passes",
      qua_giong("Built a nightly pipeline in Python that validated 17 instrument "
                "feeds and cut reconciliation from 40 minutes to 90 seconds.",
                _ne) < 0.6)
check("writing at greater length does NOT dilute the measure",
      qua_giong(_ne + " across every desk and region we cover", _ne) == 1.0)

# THE SUGGESTION: the machine turns their line into the SHAPE of a CV
# sentence — it invents no claim.
check("an imperative verb -> past tense", qua_khu("build") == "built"
      and qua_khu("improve") == "improved" and qua_khu("apply") == "applied")
check("a gerund conjugates too", qua_khu("maintaining") == "maintained"
      and qua_khu("developing") == "developed")
_gy = goi_y("Build and maintain data pipelines, ensuring data quality and "
            "consistency across multiple sources", "data pipeline")
check("the suggestion has a CV sentence's shape, with the writer's excess cut",
      _gy.startswith("Built and maintained data pipelines"))
check("both verbs go to the past, never half and half",
      "and maintaining" not in _gy and "and maintain " not in _gy)
check("and it leaves THE BLANK for the evidence", CHO_TRONG in _gy)
# THE SKILL NAME MUST NOT BE CUT AWAY: a sentence that does not mention it
# fills no gap, and filling gaps is the entire reason the user is sitting
# here.
check("the suggestion still mentions the skill being aimed at", "data pipeline" in _gy.lower())
# The suggestion has to pass THE VERY gate Save applies. Measured on the real
# store: cut lightly, 12 of 19 lines come out as their line in the past tense
# — the machine suggesting what it will itself reject. Better to stay silent.
check("the suggestion passes the gate by itself", qua_giong(_gy, _ne) < 0.6)
check("a cut that does not get far enough STAYS SILENT, it does not guess",
      goi_y("Research and develop predictive alpha signals across global "
            "equity markets", "equities") == "")
check("a line describing a quality gets no suggestion",
      goi_y("Interest in statistics and data visualisation", "visualisation") == "")

# The blank still there = not finished.
check("the blank still there -> not allowed to save", con_trong(_gy))
check("filled in, it passes",
      not con_trong("Built data pipelines that cut a 40-minute job to 90s."))

# WRITING A NEW SENTENCE AND EDITING A BLOCK ARE ONE JOB. Both write into the
# same `cv_text`, so they share one screen (/cv/soan) — not a separate
# overlay where the requirement is read in one place and typed in another.
_c3 = sqlite3.connect(":memory:"); _c3.row_factory = sqlite3.Row
_c3.execute("CREATE TABLE posting (id INTEGER PRIMARY KEY, kept INT,"
            " realism TEXT, score TEXT, company TEXT, title TEXT, score_json TEXT)")
_c3.execute("INSERT INTO posting VALUES (1,1,'likely','90','Bonhill','Analyst',?)",
            (json.dumps({"requirements": [
                {"text": "Improve research frameworks and data pipelines",
                 "must": True}]}),))
_c3.commit()
_ch3, _ri3 = ho_hoi(_c3, "data pipeline")
_c3.close()
_kh3 = [{"title": "Block A", "kind": "project", "lines": ["x"], "reach": 9}]
_d3 = {"ky": "data pipeline", "chung": _ch3, "rieng": _ri3,
       "nen": [m for m in _ch3 if ta_viec(m["chu"])]}
_bf = _cs._viet(_d3, "", "", "", _kh3)

check("the brief prints the requirement line VERBATIM, right above the box",
      "Improve research frameworks" in _bf)
check("and with the company name — this is a REAL requirement of a real posting",
      "Bonhill" in _bf)
# A base line has to be CLICKABLE: pressing drops it into the editing box
# rather than making them retype it.
check("pressing a base line drops it into the editing box",
      "&nen=Improve%20research%20frameworks" in _bf)
check("and the target being aimed at is kept", "ky=data%20pipeline" in _bf)

# THREE NUMBERED STEPS. The user's real reaction to the earlier flat version:
# "I don't know what to press, how to write, what I'm confirming".
check("the writing screen is THREE NUMBERED STEPS", _bf.count("class=buocso") == 3)
check("step 1 says what to press", "Use this line" in _bf)
check("step 2 lets a block be picked right here",
      "Which block to write into" in _bf and "Block A" in _bf)
check("step 3 says what is being confirmed",
      "Rewrite it as work YOU did" in _bf)
# With no block chosen there is no box yet — say so, do not leave a dead box.
check("no block chosen -> step 3 points the way, it leaves no dead box",
      "Pick a block in step 2" in _bf and "name=line" not in _bf)

# With both chosen, steps 1-2 fold up and step 3 opens with a box and a button.
_bf2 = _cs._viet(_d3, "Block A", "Improve research frameworks", "", _kh3)
check("chosen, a finished step folds into a changeable line",
      "class=dachon" in _bf2 and "Change line" in _bf2)
check("and the box appears, with the base already in it", "name=line" in _bf2
      and "Improve research frameworks" in _bf2)
check("the Save button says WHERE this sentence goes", "Add this sentence to" in _bf2)
check("and it states that the existing sentences are NOT touched",
      "already in the block are untouched" in _bf2
      and "name=them value=1" in _bf2)
check("it says outright why the machine does not write it for you",
      "not what you did" in _bf)
check("it recalls that a CV sentence has to be DEFENDED in the interview",
      "interview room" in _bf)
check("there is NO 'the machine writes it' button",
      "write it for you" not in _bf.lower()
      and "machine writes" not in _bf.lower().replace(
          "machine writes no sentence", ""))

# The editing box has to be EMPTY. A hint in the placeholder is allowed — it
# says WHAT TO WRITE ABOUT; what is banned is handing over A SENTENCE for
# somebody to tweak a few words of and submit.
_fm = _cs._form(None, [], "data pipeline")
# The box WITH A BASE: text landing in it has to be labelled as whose, right
# there.
_d4 = {"ky": "data pipeline", "chung": [], "rieng": [], "nen": []}
_fn = _cs._viet(_d4, "Block A", _ne, "", _kh3, _ne)
check("the base lands in the editing box", _ne in _fn)
check("and it states this is NOT your sentence yet",
      "the employer's words" in _fn and "not your sentence yet" in _fn)
check("the base travels with the form so Save can compare",
      "name=nen value=" in _fn)
_fl = _cs._viet(_d4, "Block A", _ne, "This sentence is still almost verbatim", _kh3, _ne)
# With a suggestion the box opens as THE SUGGESTION, with a way back to their
# verbatim line.
_fg = _cs._viet(_d4, "Block A", _ne, "", _kh3, _gy, _gy)
check("with a suggestion the box opens as the suggestion", _gy in _fg)
check("and it says the ___ is where the evidence goes",
      "fill in the real evidence" in _fg)
check("there is a way back to their verbatim line", "tho=1" in _fg)
_ft = _cs._viet(_d4, "Block A", _ne, "", _kh3, _ne, _gy, True)
check("switched to verbatim there is a way back to the suggestion",
      "Suggest a CV sentence" in _ft)
check("a line that cannot be cut down says so, it leaves no dead button",
      "cannot be cut down" in _cs._viet(_d4, "Block A", _ne, "", _kh3, _ne))
check("refused, the refusal sits RIGHT ABOVE the box with the typed text intact",
      "This sentence is still almost verbatim" in _fl and _ne in _fl)
check("the editing box is empty — no template sentence sitting in it",
      "<textarea class=cvdraft name=line rows=2 placeholder=" in _fm
      and "></textarea>" in _fm)
check("the hint says only WHAT TO WRITE ABOUT, never a ready sentence",
      "placeholder='write a sentence about data pipeline…'" in _fm)
# autofocus IS GONE: it scrolled straight to the typing box, carrying away
# the brief just above — exactly what was put on this screen to be read
# BEFORE writing.
check("the first empty box carries an ANCHOR to jump to", "id=viet" in _fm)
check("and it does NOT steal the cursor, which would scroll the brief away", "autofocus" not in _fm)
check("the sentence written goes straight into the original CV, no separate table",
      "action='/cv/block'" in _fm)
check("and it carries the skill being aimed at, so the journal records the right job",
      "name=ky value='data pipeline'" in _fm)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
