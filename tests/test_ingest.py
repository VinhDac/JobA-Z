"""Test step 1 — filtering by profile and merging duplicates.  python3 tests/test_ingest.py"""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db, postings
from jobbot.dedup import group
from jobbot.ingest import filter as jf
from jobbot.ingest.base import Posting, norm_company, norm_title, strip_html

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

def P(title, company="Acme", location="London", remote=False):
    return Posting(source_id="x", title=title, company=company,
                   location=location, remote=remote)

PROFILE = {"job_titles": "Quantitative Analyst\nData Scientist\nGraduate Analyst",
           "seniority": ["grad", "junior"], "markets": ["uk_onsite", "uk_remote"]}

print("\n[normalising]")
check("company suffixes dropped", norm_company("Monzo Bank Ltd") == norm_company("Monzo Bank"))
check("brackets dropped from a title", norm_title("Analyst (London)") == "analyst")
check("the requisition code dropped", norm_title("Analyst - REQ1042") == "analyst")
check("HTML tags dropped", strip_html("<p>a<br>b</p>").replace("\n", " ").strip() == "a b")

print("\n[filtering]")
keep, why = jf.judge(P("Quantitative Analyst"), PROFILE)
check("a matching title -> kept", keep)
check("it can explain why it was kept", "matched target title" in why)

keep, why = jf.judge(P("Product Manager"), PROFILE)
check("no match -> dropped", not keep and "does not match" in why)

# A BUG THAT ONCE EXISTED: 'analyst' was in JUNIOR_WORDS, letting every Senior posting through
for t in ["Senior Data Scientist", "Senior Quantitative Analyst", "Head of Data Scientist"]:
    keep, why = jf.judge(P(t), PROFILE)
    check(f"senior level dropped: {t}", not keep and "senior level" in why)

keep, _ = jf.judge(P("Graduate Analyst to Senior Analyst"), PROFILE)
check("a posting naming both grad and senior -> still kept", keep)

keep, why = jf.judge(P("Data Scientist", location="New York"), PROFILE)
check("outside the area -> dropped", not keep and "outside your area" in why)
# The reason has to NAME the area, because the area is now derived from the
# "Where you're based" field rather than hardcoded to the UK. Without it,
# reading the journal never says where the machine thinks home is.
check("and it names where home is", "(UK)" in why, )

# The "Where you're based" field NOW REALLY DOES SOMETHING. Not one line in
# the search or the filter used to read it — while its own `why` promised
# "Used to filter on-site and hybrid roles by commute".
# Living in the US, with the UK market NOT ticked -> a London job is outside the area.
o_my = dict(PROFILE, location="New York, NY", markets=["us_remote"])
keep, _ = jf.judge(P("Data Scientist", location="New York"), o_my)
check("in the US, a New York job is kept", keep)
keep, why = jf.judge(P("Data Scientist", location="London"), o_my)
check("and a London job becomes outside the area", not keep and "(US)" in why)

# The "markets" field IS A DECLARATION, not decoration. Living in the US and
# ticking "UK — onsite" means being willing to take UK work, so London has to
# be KEPT.
#
# The previous location_ok took `markets` and never read it once: a profile
# choosing "US — remote" still had its New York postings thrown away as
# "outside your area (UK)". Worse, LinkedIn translated those keys correctly
# into WHERE TO SEARCH — so the app searched in the US and then threw every
# result away itself.
o_my_uk = dict(PROFILE, location="New York, NY",
               markets=["uk_onsite", "uk_remote"])
keep, _ = jf.judge(P("Data Scientist", location="London"), o_my_uk)
check("in the US but with the UK market ticked -> a London job is kept", keep)
o_uk_us = dict(PROFILE, location="London, UK", markets=["us_remote"])
keep, _ = jf.judge(P("Data Scientist", location="New York, NY"), o_uk_us)
check("in the UK but with US remote ticked -> a New York job is kept", keep)
keep, _ = jf.judge(P("Data Scientist", location="Berlin, Germany"), o_uk_us)
check("but not Berlin — the EU was not ticked", not keep)
o_all = dict(PROFILE, location="London, UK", markets=["global_remote"])
keep, _ = jf.judge(P("Data Scientist", location="Berlin, Germany"), o_all)
check("global remote ticked -> the location latch is dropped entirely", keep)
# An empty field KEEPS THE OLD BEHAVIOUR, never silently changing what is kept.
keep, _ = jf.judge(P("Data Scientist", location="London"),
                   dict(PROFILE, location=""))
check("no location declared -> still treated as the UK", keep)

# A LATCH against colliding city names. "Birmingham, AL" is Alabama — and it
# was sitting in Vin's UK job list (measured 12/09, Mission Pet Health).
keep, _ = jf.judge(P("Data Scientist", location="Birmingham, AL"), PROFILE)
check("Birmingham, AL (Alabama) is NOT a UK job", not keep)
keep, _ = jf.judge(P("Data Scientist", location="Birmingham, England"), PROFILE)
check("but Birmingham, England still is the UK", keep)
# A STRONG signal beats the latch: with "United Kingdom" present, a state code
# cannot save it — a posting listed in several places is ordinary.
keep, _ = jf.judge(P("Data Scientist",
                     location="New York, NY; London, United Kingdom"), PROFILE)
check("posted in both places with an explicit UK -> still kept", keep)

keep, _ = jf.judge(P("Data Scientist", location="London, United Kingdom"), PROFILE)
check("several locations including London -> kept", keep)

keep, _ = jf.judge(P("Data Scientist", location="Remote - Europe", remote=True), PROFILE)
check("remote across Europe -> kept", keep)

keep, why = jf.judge(P("Anything At All"), {})
check("no job_titles yet -> keep everything", keep and "no job_titles" in why)

print("\n[the cache + merging duplicates]")
with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "t.db")
    batch = [P("Quantitative Analyst", "Monzo Bank Ltd"),
             P("Quantitative Analyst", "Monzo Bank"),      # same job, different name
             P("Data Scientist", "Wise")]
    for i, item in enumerate(batch):
        item.source_id = f"s{i}"
    seen, new = postings.save_batch(conn, "test", batch)
    check("the first write", (seen, new) == (3, 3))

    seen, new = postings.save_batch(conn, "test", batch)
    check("a rerun writes NO duplicate (this is the cache)", (seen, new) == (3, 0))
    check("the posting count is unchanged", postings.count(conn) == 3)

    # A BUG SINCE FIXED: the cache blocked enrichment too. The fast scan wrote
    # postings with no description, and the deep-read pass fetched a
    # description with nowhere to write it.
    deep = P("Quantitative Analyst", "Monzo Bank Ltd")
    deep.source_id, deep.description = "s0", "x" * 900
    seen, new = postings.save_batch(conn, "test", [deep])
    check("enrichment creates NO new row", (seen, new) == (1, 0))
    got = conn.execute("SELECT p.description FROM posting p"
                       " JOIN raw_posting r ON p.raw_id = r.id"
                       " WHERE r.source_id = 's0'").fetchone()[0]
    check("the description is written onto the existing posting", len(got) == 900)

    deep2 = P("Quantitative Analyst", "Monzo Bank Ltd")
    deep2.source_id, deep2.description = "s0", "much shorter"
    postings.save_batch(conn, "test", [deep2])
    kept_long = conn.execute("SELECT p.description FROM posting p"
                             " JOIN raw_posting r ON p.raw_id = r.id"
                             " WHERE r.source_id = 's0'").fetchone()[0]
    check("a long description is NOT overwritten by a short one", len(kept_long) == 900)

    # kept defaults to 0 (not judged) — only a real filter pass turns it on
    conn.execute("UPDATE posting SET kept = 1, drop_reason = ''")
    conn.commit()
    n_rows, n_groups = group.regroup(conn)
    check("Monzo Bank Ltd + Monzo Bank merged", (n_rows, n_groups) == (3, 2))

    groups = group.groups(conn)
    merged = next(g for g in groups if g["count"] == 2)
    check("a merged group can name its sources", merged["sources"] == ["test"])

    postings.log(conn, "test_event", "details")
    check("the journal writes", len(postings.recent_audit(conn)) == 1)
    conn.close()

print("\n[a location matches by WORD, never by substring]")
from jobbot.ingest.filter import location_ok as _loc
_P = lambda loc, co="", rm=False: Posting(source_id="x", title="t", company=co,
                                          location=loc, remote=rm)
for _loc_text, _co in [("London", ""), ("Manchester, UK", ""),
                       ("United Kingdom", ""), ("Edinburgh", "")]:
    check(f"kept {_loc_text!r}", _loc(_P(_loc_text, _co), []))
# 17 real postings slipped through because 'uk' is inside 'ukraine' and 'gb' inside 'gbagada'
for _loc_text, _co in [("Kyiv, Ukraine", ""), ("Köln", "teamZUKUNFT gGmbH"),
                       ("Paris", "Bigblue"), ("Bremen", "GBC Group"),
                       ("Gbagada, Lagos", "")]:
    check(f"dropped {_loc_text!r} {_co}", not _loc(_P(_loc_text, _co), []))
check("global remote is still kept", _loc(_P("Anywhere", "", True), []))

print("\n[the board list: what a person picked + what the machine learnt, NEITHER dropped]")
# THE REAL BUG: boards.toml was only a FALLBACK for an empty company table.
# The table had 53 rows, so the file was never read — aqr, cohere, palantir,
# ramp and synthesia had been typed in there and never scanned once, with
# nothing to say so.
import os as _os, tempfile as _tf
from pathlib import Path as _P
with _tf.TemporaryDirectory() as _tmp:
    _os.environ["JOBBOT_DATA_DIR"] = _tmp
    from jobbot.core import db as _db
    from jobbot.scan_runner import load_boards, seed_boards

    _conn = _db.connect(_P(_tmp) / "b.db")
    seed = seed_boards()
    seed_slugs = {s for v in seed.values() for s in v}
    check("boards.toml can be read", bool(seed_slugs))

    # an EMPTY company table -> the hand-typed list still has to come out
    got = {s for v in load_boards(_conn).values() for s in v}
    check("an empty table -> the hand-typed list is used", seed_slugs <= got)

    # a company table WITH data -> the hand-typed list must NOT disappear
    _conn.execute(
        "INSERT INTO company (name, key, ats, ats_slug, is_agency, checked_at,"
        " roles_found, note) VALUES (?,?,?,?,0,?,?,?)",
        ("Machine Found It", "machine found it", "greenhouse", "maynhat",
         "2026-01-01", 5, "seen in a posting"))
    _conn.commit()
    got = {s for v in load_boards(_conn).values() for s in v}
    check("a table with data -> the hand-typed list is still kept", seed_slugs <= got)
    check("and what the machine learnt is merged in", "maynhat" in got)

    every = [s for v in load_boards(_conn).values() for s in v]
    check("no duplicate slug", len(every) == len(set(every)))
    _conn.close()
    _os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[job alert mail — the third source, and the cleanest of them]")
# LinkedIn SENDS these itself to Vin's mailbox. Reading your own mailbox
# touches nobody's Terms — quite unlike the Chrome scan, which falls outside
# clause 8.2 and which the app has to say so about.
from jobbot.ingest import alerts as _al

_THU = """
<a href="https://www.linkedin.com/comm/jobs/view/4464889773/?trk=x"><img></a>
<a href="https://www.linkedin.com/comm/jobs/view/4464889773/?trk=y">
  <span>Data Analyst, Business Intelligence &mdash; Entry Level</span>
  <span>Jobright.ai &middot; United Kingdom (Remote)</span>
  <span>Fast growing</span>
</a>
<a href="https://www.linkedin.com/comm/jobs/view/4466042742/?trk=z">
  <span>Junior Data Analysis - 12 months FTC</span>
  <span>Slater and Gordon Lawyers (UK) &middot; London</span>
</a>
"""
_tin = _al.parse(_THU)
check("the right number of jobs parsed out", len(_tin) == 2)
_m = {t.source_id: t for t in _tin}
check("the title parses correctly",
      _m["4464889773"].title == "Data Analyst, Business Intelligence — Entry Level")
# The title and the company name are in ADJACENT elements with nothing
# between them. Joined with a space it becomes "…Entry Level Jobright.ai" and
# cannot be split again — so the TAG has to be replaced by A NEWLINE.
check("the company parses correctly", _m["4464889773"].company == "Jobright.ai")
check("the location parses correctly", _m["4464889773"].location == "United Kingdom (Remote)")
check("the promo label is dropped", "Fast growing" not in _m["4464889773"].title)
# The URL in the email is a long tracking link; a clean URL is rebuilt from the id.
check("a clean URL is rebuilt, tracking parameters dropped",
      _m["4464889773"].url == "https://www.linkedin.com/jobs/view/4464889773/")
check("the same job appearing 3 times -> taken once", len(set(_m)) == 2)
check("an empty email returns empty, it does not blow up", _al.parse("") == [])
check("an email with no jobs does not blow up either", _al.parse("<p>hello</p>") == [])
# A logo/button block carries no text -> it has to be dropped, never turned
# into an empty posting.
check("a block with no 'company · place' is dropped",
      not _al.parse('<a href="/jobs/view/9999999/"><img></a>'))

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
