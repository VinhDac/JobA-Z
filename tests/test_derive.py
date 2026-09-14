"""Test the derive layer — recomputable, versioned, one transaction.

    python3 tests/test_derive.py
"""

import sqlite3, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db, postings, versions
from jobbot.core.derive import derive, rebuild, stale_count
from jobbot.ingest.base import Posting, strip_html
from jobbot.profile import store

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

PROFILE = {"job_titles": "Quantitative Analyst\nData Scientist",
           "seniority": ["grad", "junior"], "markets": ["uk_onsite"],
           "work_auth": "citizen"}

def fresh(tmp):
    conn = db.connect(Path(tmp) / "t.db")
    store.save(conn, PROFILE, "test")
    # A real source strips the HTML BEFORE handing it to save_batch (see
    # linkedin.py), so the fixture has to do the same — feeding raw HTML in
    # builds a world that does not exist, and the tests below check the wrong
    # thing.
    RAW_A = "<p>Requirements:</p><ul><li>Strong Python and SQL</li></ul>"
    RAW_B = "<p>Manage products</p>"
    items = [
        Posting(source_id="a", title="Quantitative Analyst", company="Man Group",
                location="London", description=strip_html(RAW_A), raw_body=RAW_A),
        Posting(source_id="b", title="Product Manager", company="Acme",
                location="London", description=strip_html(RAW_B), raw_body=RAW_B),
    ]
    postings.save_batch(conn, "test", items)
    return conn

print("\n[the raw layer really is raw]")
with tempfile.TemporaryDirectory() as tmp:
    conn = fresh(tmp)
    body = conn.execute("SELECT body FROM raw_posting WHERE source_id='a'").fetchone()[0]
    # Comparing body against description only says "two different strings" —
    # weak. What has to be guaranteed is that body is EXACTLY the string fed
    # in, not one character off.
    check("raw keeps it VERBATIM, character for character",
          body == "<p>Requirements:</p><ul><li>Strong Python and SQL</li></ul>")
    stripped = conn.execute(
        "SELECT description FROM posting WHERE title='Quantitative Analyst'"
    ).fetchone()[0]
    check("the stripped version has no tags", "<li>" not in stripped and "<p>" not in stripped)
    check("and keeps the bullet marks", "·" in stripped)
    conn.close()

print("\n[versioning]")
with tempfile.TemporaryDirectory() as tmp:
    conn = fresh(tmp)
    check("newly loaded postings -> need judging", stale_count(conn) == 2)
    derive(conn)
    check("judged -> nothing stale", stale_count(conn) == 0)

    real = versions.FILTER_RULES
    versions.FILTER_RULES = "changed-rules"
    check("CHANGED RULES -> detected as needing recomputation", stale_count(conn) == 2)
    derive(conn)
    check("recomputed -> nothing stale", stale_count(conn) == 0)
    versions.FILTER_RULES = real
    check("rules put back -> stale again", stale_count(conn) == 2)
    derive(conn)

    store.save(conn, {"salary_floor": "£50,000"}, "profile changed")
    check("CHANGED PROFILE -> detected as needing recomputation", stale_count(conn) == 2)
    derive(conn)
    check("done -> nothing stale", stale_count(conn) == 0)
    conn.close()

print("\n[filtering and scoring]")
with tempfile.TemporaryDirectory() as tmp:
    conn = fresh(tmp)
    result = derive(conn)
    check("it keeps the posting whose title matches", result["kept"] == 1)
    check("the count is the TOTAL kept, not just what was judged",
          derive(conn)["kept"] == 1)
    row = conn.execute("SELECT kept, drop_reason FROM posting"
                       " WHERE title='Product Manager'").fetchone()
    check("a non-matching posting -> dropped, with a reason", row["kept"] == 0 and row["drop_reason"])
    check("a kept posting gets scored", result["scored"] == 1)
    check("the rules used to score it are recorded", conn.execute(
        "SELECT scored_rules FROM posting WHERE kept=1").fetchone()[0] == versions.SCORE_RULES)
    conn.close()

print("\n[rebuilding from raw]")
with tempfile.TemporaryDirectory() as tmp:
    conn = fresh(tmp)
    derive(conn)
    # simulate a broken HTML stripper: the description is destroyed
    conn.execute("UPDATE posting SET description = 'JUNK'")
    conn.commit()
    check("the description is broken", conn.execute(
        "SELECT description FROM posting LIMIT 1").fetchone()[0] == "JUNK")
    rebuild(conn)
    fixed = conn.execute("SELECT description FROM posting"
                         " WHERE title='Quantitative Analyst'").fetchone()[0]
    check("rebuilt from raw -> the description is back", "Python" in fixed and "JUNK" not in fixed)
    check("and no HTML tag is left", "<li>" not in fixed)
    conn.close()

print("\n[a verdict has to GO STALE when its inputs change]")
# Three real bugs with one root: the score was versioned against the RULES
# only, never against the PROFILE, and a description arriving late cleared no
# version stamp at all. The consequence on the real machine: 72 of 204 kept
# postings sat at score=NULL because they were scored while the description
# was still empty, and even derive(force=True) could not shake them loose.
with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "t.db")
    store.save(conn, dict(PROFILE, skills_strong="Python"), "v1")
    LATE = ("Requirements:\n· Python and pandas\n· SQL\n· Machine learning\n"
            + "detail " * 80)

    postings.save_batch(conn, "s", [Posting(source_id="x", title="Data Scientist",
        company="Monzo", location="London", url="u", description="")])
    derive(conn)
    check("scored with no description -> it says outright it could not score",
          conn.execute("SELECT score_conf FROM posting").fetchone()[0] == "none")

    postings.save_batch(conn, "s", [Posting(source_id="x", title="Data Scientist",
        company="Monzo", location="London", url="u", description=LATE)])
    check("a late description -> the posting goes stale by itself", stale_count(conn) == 1)
    derive(conn)
    first = conn.execute("SELECT score, score_conf FROM posting").fetchone()
    check("and it is rescored with the new description", first[0] is not None and first[1] != "none")

    store.save(conn, {"skills_strong": "Python, pandas, SQL, machine learning"}, "v2")
    check("profile changed -> the old score goes stale by itself", stale_count(conn) == 1)
    derive(conn)
    second = conn.execute("SELECT score FROM posting").fetchone()[0]
    check("and the score follows the new profile", second > first[0])
    check("once recomputed nothing is stale", stale_count(conn) == 0)

    # force has to reach THE SCORING pass too, not only the filter pass
    conn.execute("UPDATE posting SET score = 1")
    conn.commit()
    derive(conn, force=True)
    check("force=True rescores even a posting that is not stale",
          conn.execute("SELECT score FROM posting").fetchone()[0] == second)
    conn.close()

with tempfile.TemporaryDirectory() as tmp:
    conn = fresh(tmp)
    derive(conn)
    check("after scoring it is clean", stale_count(conn) == 0)
    conn.execute("UPDATE posting SET scored_rules = 'old rules' WHERE kept = 1")
    conn.commit()
    check("stale_count sees the SCORING rules change, not only the FILTER rules", stale_count(conn) > 0)
    conn.close()

print("\n[one transaction]")
with tempfile.TemporaryDirectory() as tmp:
    conn = fresh(tmp)
    before = conn.execute("SELECT COUNT(*) FROM posting WHERE kept=1").fetchone()[0]

    import jobbot.core.derive as d
    real_score = d.score_job
    d.score_job = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("broke halfway"))
    try:
        derive(conn)
        check("an error halfway has to be raised", False)
    except RuntimeError:
        check("an error halfway is raised out", True)
    d.score_job = real_score

    after = conn.execute("SELECT COUNT(*) FROM posting WHERE kept=1").fetchone()[0]
    check("broken halfway -> NOTHING half-written", before == after)
    check("and it is still stale", stale_count(conn) == 2)
    conn.close()

print("\n[A PERSON keeps a posting the machine dropped — the decision must SURVIVE]")
# The trap: `kept` is a DERIVED column. Set kept=1 by hand and derive()
# overwrites it on the next recomputation — and changing one word in the
# profile makes every posting stale, so the person's decision evaporates
# silently, taking the fresh score with it.
with tempfile.TemporaryDirectory() as tmp:
    conn = fresh(tmp)
    derive(conn)
    bo = conn.execute("SELECT id, kept, drop_reason FROM posting"
                      " WHERE title = 'Product Manager'").fetchone()
    check("the machine drops a posting whose title does not match", bo["kept"] == 0 and bo["drop_reason"])

    conn.execute("UPDATE posting SET user_keep=1, judged_rules='' WHERE id=?",
                 (bo["id"],))
    conn.commit()
    derive(conn)
    sau = conn.execute("SELECT kept, drop_reason, score, scored_rules FROM posting"
                       " WHERE id=?", (bo["id"],)).fetchone()
    check("the person keeps it -> it joins the kept list", sau["kept"] == 1)
    # The old invariant holds: an empty drop_reason <=> it is being kept.
    # Loading extra meaning into that column makes every reader learn a new
    # rule.
    check("and drop_reason is cleared", sau["drop_reason"] == "")
    # Joining the kept list means being SCORED in the same pass — made to
    # wait for the next scan, pressing Keep leaves the screen blank and looks
    # like a broken button.
    check("it is scored in that same pass",
          sau["scored_rules"] == versions.SCORE_RULES)

    # THIS IS THE REAL TEST: change the profile -> everything goes stale ->
    # derive() rejudges the lot. If the person's decision lived in `kept`,
    # this is exactly where it would be wiped, silently.
    store.save(conn, {"job_titles": "Quantitative Analyst"}, "profile changed")
    derive(conn)
    check("A CHANGED PROFILE still keeps it — a person's decision is not overwritten",
          conn.execute("SELECT kept FROM posting WHERE id=?",
                       (bo["id"],)).fetchone()["kept"] == 1)

    # rebuild() reconstructs EVERY verdict from raw — the most destructive path.
    rebuild(conn)
    check("rebuild() does not wipe the person's decision either",
          conn.execute("SELECT kept FROM posting WHERE id=?",
                       (bo["id"],)).fetchone()["kept"] == 1)

    conn.execute("UPDATE posting SET user_keep=0, judged_rules='' WHERE id=?",
                 (bo["id"],))
    conn.commit()
    derive(conn)
    lai = conn.execute("SELECT kept, drop_reason, score FROM posting WHERE id=?",
                       (bo["id"],)).fetchone()
    check("unkept -> handed back for the machine to rejudge", lai["kept"] == 0 and lai["drop_reason"])
    check("and the old score is cleared with it", lai["score"] is None)
    conn.close()

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
