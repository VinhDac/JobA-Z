"""Test the user-driven filters.  python3 tests/test_filters.py"""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.core import db, postings
from jobbot.dashboard import live
from jobbot.dashboard.filters import BAND, PER_PAGE, JobFilter
from jobbot.dedup import group
from jobbot.ingest.base import Posting, to_ts

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

Q = lambda **kw: JobFilter.from_query({k: [str(v)] for k, v in kw.items()})

print("\n[the agency filter]")
check("by default it shows direct employers only", "via_agency = 0" in Q().where()[0])
check("'all' filters nothing", "via_agency" not in Q(via="all").where()[0])
check("'agency' shows agencies only", "via_agency = 1" in Q(via="agency").where()[0])
check("an unknown value -> back to the direct default", Q(via="hack").via == "direct")

print("\n[reading the URL]")
check("the default is 'matched'", Q().show == "matched")
check("an unknown value is thrown away", Q(show="'; DROP TABLE--").show == "matched")
check("an unknown loc is thrown away", Q(loc="mars").loc == "")
check("an unknown sort falls back to the default", Q(sort="hack").sort == "score")
check("a negative page -> 1", Q(page="-5").page == 1)
check("a non-numeric page -> 1", Q(page="abc").page == 1)
check("q is length-capped", len(Q(q="x" * 500).q) == 120)

print("\n[building the SQL — always with bound parameters]")
where, args = Q(q="quant'; DROP TABLE posting;--").where()
check("a hostile string goes into ARGS, never into the SQL", "DROP" not in where and any("drop" in str(a).lower() for a in args))
check("kept=1 khi show=matched", "kept = 1" in Q().where()[0])
check("kept=0 khi show=dropped", "kept = 0" in Q(show="dropped").where()[0])
check("show=all does not filter on kept", "kept" not in Q(show="all").where()[0])
check("days produces a timestamp bound", Q(days="7").where()[1][-1] > 0)

print("\n[building the URL]")
f = Q(q="quant", loc="london", page="3")
check("the filters survive a page change", "q=quant" in f.url(page=4) and "page=4" in f.url(page=4))
check("changing a filter goes back to page 1", "page" not in f.url(loc="uk"))
# The job list moved into the Search tab — the Jobs tab is gone.
check("default values are left out of the URL", f.url(q="", loc="", page=1) == "/search")
check("each chip can be switched off on its own", any(u == "/search?loc=london&page=3" or "q=" not in u
                                    for _, u in f.active()))

print("\n[filtering real data]")
with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "t.db")
    # The profile has to declare WHERE THEY LIVE, because the place filter now
    # works from it rather than from a hardcoded "london" in the source.
    from jobbot.profile import store as _st
    _st.save(conn, {"job_titles": "Data Scientist", "markets": ["uk_onsite"],
                    "work_auth": "citizen", "location": "London"}, "t")
    items = []
    for i, (title, comp, loc, when) in enumerate([
        ("Quantitative Analyst", "Man Group", "London", "2026-09-01T00:00:00+00:00"),
        ("Data Scientist", "Monzo", "London", "2026-01-01T00:00:00+00:00"),
        ("Product Manager", "Acme", "New York", "2026-09-01T00:00:00+00:00"),
    ]):
        p = Posting(source_id=f"s{i}", title=title, company=comp, location=loc, posted_at=when)
        items.append(p)
    postings.save_batch(conn, "greenhouse:test", items)
    conn.execute("UPDATE posting SET kept = 1, drop_reason = ''")
    conn.execute("UPDATE posting SET kept=0, drop_reason='title does not match'"
                 " WHERE title='Product Manager'")
    conn.commit()
    group.regroup(conn)

    check("by default only kept postings show", len(live.jobs(conn, Q())) == 2)
    check("show=dropped shows the dropped ones", len(live.jobs(conn, Q(show="dropped"))) == 1)
    check("show=all shows everything", len(live.jobs(conn, Q(show="all"))) == 3)
    check("a dropped posting carries its reason",
          live.jobs(conn, Q(show="dropped"))[0]["drop_reason"] == "title does not match")
    check("search by text", len(live.jobs(conn, Q(q="quantitative"))) == 1)
    check("search matches the company name too", len(live.jobs(conn, Q(q="monzo"))) == 1)
    check("filter by company", len(live.jobs(conn, Q(company="Man Group"))) == 1)
    # PLACE IS COMPUTED FROM THE PROFILE, never a hardcoded city. The id is a
    # RELATION — near me / my country / elsewhere — and where "near" is comes
    # from the "Where you're based" field. "london" used to sit straight in
    # the source, which made the filter right for exactly one user.
    check("my country (UK) -> 2 London jobs", len(live.jobs(conn, Q(show="all", loc="home"))) == 2)
    check("elsewhere -> 1 New York job", len(live.jobs(conn, Q(show="all", loc="other"))) == 1)
    # The PROFILE declares location="London", so "near me" = London.
    check("near me -> exactly the London job",
          len(live.jobs(conn, Q(show="all", loc="near"))) == 2)

    # "Near me" with no location declared filters NOTHING — filtering by a
    # made-up place is worse than not filtering.
    _w, _ = Q(loc="near").where("uk", "")
    check("no location declared -> 'near me' adds no condition",
          "LOWER(location)" not in _w)
    _w2, _a2 = Q(loc="near").where("uk", "London")
    check("declared, it filters on exactly that place", _a2 == ["%london%"])
    # Changing where you live changes what "my country" means — no hardcoded UK.
    _w3, _a3 = Q(loc="home").where("us", "")
    check("in the US, 'my country' means the United States", "%united states%" in _a3)
    check("and not a trace of UK is left", "%united kingdom%" not in _a3)
    check("filter by date", len(live.jobs(conn, Q(days="30"))) == 1)
    check("sort by company", live.jobs(conn, Q(sort="company"))[0]["company"] == "Man Group")
    check("the default sort is by score", Q().sort == "score")
    check("the score threshold produces the right SQL", "score >= ?" in Q(band="75").where()[0])
    # "Not scorable" IS GONE from the score row. It and "Can't tell" on the
    # chance row are THE SAME pile — measured on the real store: 185 postings
    # missing both, 0 missing only one. Two buttons on two rows for one thing
    # is asking twice.
    check("the score row no longer has 'not scorable'",
          "none" not in {v for v, _ in BAND})
    check("folded into ONE chip: raw=1 finds postings the machine could not read",
          "score IS NULL" in Q(raw="1").where()[0]
          and "unknown" in Q(raw="1").where()[0])

    # A LADDER IS A FLOOR, not an equals. Pick "Possible" and hiding "Worth
    # applying" hides exactly the best postings — nobody wants that.
    _sql = Q(chance="possible").where()[0]
    check("the chance ladder produces >= SQL, not =",
          ">= ?" in _sql and "realism = ?" not in _sql)
    check("the 'possible' floor is rank 2", Q(chance="possible").where()[1] == [2])
    check("the 'worth applying' floor is rank 3", Q(chance="likely").where()[1] == [3])
    check("All adds no chance condition at all",
          "realism" not in Q(chance="").where()[0])

    # THE SOURCE CHIPS — filtering by HOW IT WAS FOUND.
    check("linkedin = LinkedIn only", "source = 'linkedin'" in Q(found="linkedin").where()[0])
    check("board = everything but LinkedIn", "source <> 'linkedin'" in Q(found="board").where()[0])
    check("all sources filters nothing", "source" not in Q(found="").where()[0])
    check("an unknown source is thrown away", Q(found="madeup").found == "")

    counts = live.job_counts(conn, Q())
    check("the count is right for each tab", (counts["matched"], counts["dropped"], counts["all"]) == (2, 1, 3))
    check("facets read the real sources", live.facets(conn)["sources"] == ["greenhouse"])
    check("page 2 is empty when there are only 2 postings", len(live.jobs(conn, Q(page="2"))) == 0)
    conn.close()


print("\n[a filter chooses WHICH POSTINGS SHOW, never what a POSTING LOOKS LIKE]")
# THE REAL BUG: the source badges, "+N places" and the score were computed
# over THE FILTERED part. So one press of the LinkedIn source chip stripped
# the Man Group posting of its board badge, of "+1 places", and of its score
# of 100 — because its LinkedIn row had not been deep-read and had no score.
# One job, two filters, two faces.
with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "m.db")
    JD = ("Requirements:\n· Python and pandas\n· SQL\n" + "detail " * 80)
    # THE SAME job posted in two places: the board has a description (so it
    # can be scored) while LinkedIn has not been deep-read and is empty —
    # exactly the shape seen on the real machine.
    postings.save_batch(conn, "greenhouse:mangroup", [
        Posting(source_id="g1", title="Quant Researcher", company="Man Group",
                location="London", url="https://g/1", description=JD)])
    postings.save_batch(conn, "linkedin", [
        Posting(source_id="l1", title="Quant Researcher", company="Man Group",
                location="London", url="https://l/1", description="")])
    conn.execute("UPDATE posting SET kept = 1")
    conn.execute("UPDATE posting SET score = 100 WHERE source LIKE 'greenhouse%'")
    conn.commit()
    group.regroup(conn)

    het = live.jobs(conn, Q())[0]
    chr_ = live.jobs(conn, Q(found="linkedin"))[0]
    api = live.jobs(conn, Q(found="board"))[0]
    check("unfiltered: both sources show", het["found_by"] == ["board", "linkedin"])
    check("filtered to linkedin: both sources STILL show", chr_["found_by"] == ["board", "linkedin"])
    check("filtered to board: both sources STILL show", api["found_by"] == ["board", "linkedin"])
    check("the '+N places' figure does not follow the filter",
          het["merged"] == chr_["merged"] == api["merged"] == 2)
    check("the score does not follow the filter",
          het["score"] == chr_["score"] == api["score"] == 100)
    check("but the filter STILL picks the right postings",
          len(live.jobs(conn, Q(found="linkedin"))) == 1)
    conn.close()

print("\n[paging has to COVER the count exactly — nothing missed, nothing twice]")
# THE REAL BUG: jobs() paged by ROW and only then merged duplicates in
# Python, while job_counts() counted GROUPS. On the real machine the header
# said 139 jobs and walking every page counted 144 cards: 5 groups split
# across a page boundary.
with tempfile.TemporaryDirectory() as tmp:
    import jobbot.dashboard.filters as filters_mod
    from jobbot.core.derive import derive
    from jobbot.profile import store

    conn = db.connect(Path(tmp) / "p.db")
    store.save(conn, {"job_titles": "Data Scientist", "seniority": ["grad", "junior"],
                      "markets": ["uk_onsite"], "work_auth": "citizen"}, "t")
    JD = ("Requirements:\n· Python and pandas\n· SQL\n" + "detail " * 80)
    items = []
    for n in range(11):
        # every second posting is A DUPLICATE (same company + title) -> one
        # group of two rows, exactly where paging tends to split them
        items.append(Posting(source_id=f"a{n}", title="Data Scientist",
                             company=f"Co{n}", location="London",
                             url=f"https://x/a{n}", description=JD))
        if n % 2 == 0:
            items.append(Posting(source_id=f"b{n}", title="Data Scientist",
                                 company=f"Co{n}", location="London",
                                 url=f"https://y/b{n}", description=JD))
    postings.save_batch(conn, "greenhouse:t", items)
    derive(conn)

    real_per = filters_mod.PER_PAGE
    filters_mod.PER_PAGE = 3                    # a small page -> many boundaries
    try:
        total = live.job_counts(conn, Q())["matched"]
        seen, sizes = [], []
        for page in range(1, 40):
            got = live.jobs(conn, Q(page=page))
            if not got:
                break
            sizes.append(len(got))
            seen += [j["id"] for j in got]
        check("walking every page gives EXACTLY the header's count", len(seen) == total)
        check("no card appears twice", len(seen) == len(set(seen)))
        check("every page is full except the last",
              all(n == 3 for n in sizes[:-1]) and 0 < sizes[-1] <= 3)
        check("duplicates are merged, never counted twice", total < len(items))
        merged = [j for j in live.jobs(conn, Q()) if j["merged"] > 1]
        check("a merged group keeps its row count", bool(merged))
    finally:
        filters_mod.PER_PAGE = real_per
    conn.close()

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
