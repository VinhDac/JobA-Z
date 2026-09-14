"""Search — step 1. Three panels, three questions.

    WHAT IT FOUND   what the machine turned up for me   (the tall, biggest panel)
    THE SIEVE       what I am asking for                (left panel, with Apply)
    THE JOURNAL     what it is doing right now          (bottom left, flat)

Two kinds of filtering, DELIBERATELY in two different places:

    the KEEP/DROP sieve  ingest/filter.judge  →  changing it re-judges 4,660
                         postings (1.1 seconds). It lives in the Sieve panel,
                         with an Apply button, because it really does cost.

    the VIEW chips       filters.JobFilter    →  only changes the screen.
                         They sit at the head of the list and act instantly.

Put both behind one Apply button and either "sort by score" has to wait for
Apply (absurd), or changing a job title — which re-judges the whole store —
becomes as casual as changing the sort order.

DRAWING ONLY.
"""

from __future__ import annotations

from html import escape as esc

from ..filters import BAND, CHANCE, FOUND, LOC, SHOW, SORT, VIA
from ..layout import deck, score_bar
from . import runtime

# The source badge: two blind searches run in two different places, so every
# row says at a glance which one brought it in. A posting both found carries
# two badges.
# The badge names THE SOURCE, not the method. "chrome" is a tool we use — the
# reader does not care, and it says nothing about the posting itself. That
# name was a leftover from when TWO sources went through Chrome (see live.py).
FOUND_BY = {"linkedin": ("⌕", "linkedin", "found by keyword on LinkedIn"),
            "board": ("◆", "board", "the company's own careers board"),
            "alert": ("✉", "alert", "a LinkedIn job alert email in the mailbox")}

CHANCE_TEXT = {"likely": ("worth applying", "ok"),
               "possible": ("possible", ""),
               "unlikely": ("long shot", "warn")}


# ---------------------------------------------------------------- the list

def _so(dem: dict, name: str, value: str) -> str:
    """The number on a filter chip — how many postings remain if you press it.

    Without the number a filter chip is a blind invitation: the user presses
    it to FIND OUT what it filters to, and when it filters to nothing at all
    (measured: "All of the UK" 407 out of 411) they have spent a click
    learning that the chip is useless. Print the number and they know in
    advance, and know it against TODAY's data.
    """
    if not dem:
        return ""
    n = dem.get(f"{name}:{value}")
    return f"<b>{n:,}</b>" if n is not None else ""


def _chips(name: str, options, current: str, flt, dem: dict | None = None) -> str:
    """A row of VIEW chips. Pressing acts at once — no Apply button."""
    dem = dem or {}
    return "".join(
        f"<a class='vchip{' on' if value == current else ''}"
        f"{' nil' if dem.get(f'{name}:{value}') == 0 else ''}'"
        f" href='{esc(flt.url(**{name: value}))}'>{esc(label)}"
        f"{_so(dem, name, value)}</a>"
        for value, label in options)


def _row(job: dict) -> str:
    marks = "".join(
        f"<i class='src {k}' title='{esc(FOUND_BY[k][2])}'>"
        f"{FOUND_BY[k][0]}<b>{FOUND_BY[k][1]}</b></i>"
        for k in job["found_by"] if k in FOUND_BY)
    if job["via_agency"]:
        marks += ("<i class='src agency' title='posted by a recruitment agency'>"
                  "⚠<b>agency</b></i>")

    chance = ""
    if job["realism"] in CHANCE_TEXT:
        text, kind = CHANCE_TEXT[job["realism"]]
        chance = (f"<span class='chance {kind}'"
                  f" title='{esc(job['realism_why'])}'>{text}</span>")

    # For a dropped posting THE REASON is the most worthwhile thing on the row
    # — it is the only way to see whether the sieve is cutting too hard.
    why = (f"<div class=dropwhy>dropped: {esc(job['drop_reason'])}</div>"
           if job["state"] == "dropped" and job["drop_reason"] else "")

    merged = (f"<span class=merged>+{job['merged'] - 1} places</span>"
              if job["merged"] > 1 else "")
    # This posting is in the list because A PERSON said so, not because the
    # machine scored it in. That has to be said: otherwise a posting whose
    # title matches nothing, sitting in the middle of the list, looks like a
    # broken filter.
    tay = ("<span class='chance keep' title='the machine dropped this one,"
           " you kept it by hand'>you kept</span>" if job.get("user_keep") else "")

    # ONE button, both ways. The filter is a mechanical rule — "title does not
    # match" alone dropped 2,595 postings, and that rule is only a substring
    # comparison against the 19 job titles declared in the profile. Anyone
    # glancing through the dropped pile will certainly pick out real ones.
    if job.get("user_keep"):
        giu = (f"<button class='mbtn tiny' data-post='/api/keep'"
               f" data-arg='{esc(job['id'])}'"
               f" title='Hand this posting back for the machine to re-judge'>"
               f"Unkeep</button>")
    elif job["state"] == "dropped":
        giu = (f"<button class='mbtn tiny' data-post='/api/keep'"
               f" data-arg='{esc(job['id'])}'"
               f" title='Move this posting into the kept list and score it now'>"
               f"Keep it</button>")
    else:
        giu = ""
    money = f" · {esc(job['salary'])}" if job["salary"] != "not stated" else ""
    score = (score_bar(job["score"]) if job["score"] is not None
             else "<span class=noscore>—</span>")

    return (
        f"<a class='jrow{' dropped' if job['state'] == 'dropped' else ''}'"
        f" href='/jobs/{esc(job['id'])}'>"
        f"<div class=jscore>{score}</div>"
        f"<div class=jmain><div class=jtitle>{esc(job['title'])}</div>"
        f"<div class=jsub><b>{esc(job['company'])}</b> · {esc(job['location'])}"
        f"{money}</div>{why}</div>"
        f"<div class=jtags>{tay}{chance}{marks}{merged}"
        f"<span class=jwhen>{esc(job['posted'])}</span>"
        # NO Apply button here. Applying is a DECISION: open Chrome, fill a
        # form, write a row into Track. That decision has to come after
        # READING — and reading happens on the detail page, which has the
        # per-requirement score, the evidence, and a link to the original
        # posting. Applying from the list is applying blind.
        #
        # The KEEP button is the opposite, and that is why it stays here:
        # sifting a pile of 4,055 dropped postings is SKIMMING work, running
        # the eye down dozens of rows at a time. Forcing a detail page open to
        # rescue one posting kills the sift.
        #
        # NO onclick stopPropagation. The [data-post] listener sits on
        # `document`, so stopping propagation kills the event before it
        # arrives — the button does nothing and reports no error either. The
        # listener already calls preventDefault(), which is enough to stop the
        # surrounding <a> from navigating.
        f"{giu}"
        f"</div></a>")


def _tim(flt) -> str:
    """THE SEARCH BOX over the store already scanned. Quite different from the
    Run button: Run goes out and fetches new postings, this box filters the
    ones already here.

    The backend has taken `q` from the very start — filtering by title or
    company, with proper parameter validation — and there was never anywhere
    to type it. A whole filter sitting there with no way to use it.

    A GET form, no JavaScript: the filter state lives entirely on the URL (see
    filters.py), so typing and pressing Enter gives an address that can be
    saved, gone Back from, and sent to someone else.

    The active filters travel along as hidden fields. Without them, one search
    would blow every selected chip back to its default.
    """
    an = "".join(f"<input type=hidden name='{esc(k)}' value='{esc(v)}'>"
                 for k, v in flt.pairs(q="", page=""))
    # The clear button only appears while searching. Showing it over an empty
    # box is a button that does nothing — the kind a user presses once and
    # then stops trusting the whole row.
    xoa = (f"<a class=jfindx href='{esc(flt.url(q=''))}'"
           f" title='Clear the search, show all'>×</a>" if flt.q else "")
    return (f"<form class=jfind method=get action='/search'>{an}"
            f"<input class=search type=search name=q value='{esc(flt.q)}'"
            f" autocomplete=off spellcheck=false"
            f" placeholder='search the store — title or company'>"
            f"{xoa}</form>")


def _thang(key: str, ten: str, options, current: str, flt,
           dem: dict | None = None) -> str:
    """A LADDER — adjoining steps, filled up to the one selected.

    Why not separate chips as before: "Worth applying / Possible / Long shot"
    HAVE AN ORDER, and four identical grey pills cannot express it — the user
    has to read all four and work it out. Drawn as one continuous bar it is
    obvious at a glance, including that picking a step means "from here up".

    Still <a> tags, still no JavaScript: the state lives on the URL like every
    other filter. This changes HOW IT IS DRAWN, not the mechanism.
    """
    muc = [v for v, _ in options]
    tai = muc.index(current) if current in muc else 0
    nac = "".join(
        f"<a class='lvlstep{' on' if i <= tai else ''}{' now' if i == tai else ''}'"
        f" href='{esc(flt.url(**{key: value, 'raw': ''}))}'>{esc(label)}"
        f"{_so(dem or {}, key, value)}</a>"
        for i, (value, label) in enumerate(options))
    return (f"<span class=lvl><span class=lvlname>{esc(ten)}</span>"
            f"<span class=lvltrack>{nac}</span></span>")


def _noi(flt, gan: str, vung: str, dem: dict | None = None) -> str:
    """THE PLACE chips — the words come from the "Where you're based" field.

    Where you live does not decide which jobs are ELIGIBLE: cutting to London
    loses 71 UK jobs outside it (measured 12/09), and those 71 came from
    LinkedIn, which the boards do not cover. It decides which are CONVENIENT —
    so it is a click to LOOK, not a pair of scissors.

    With no location declared the "Near me" chip is HIDDEN: a button that
    filters nothing is a button you press and see no change, and then the user
    stops trusting the whole row.
    """
    ten = {"near": f"Near me · {gan}" if gan else "", "home": f"All of {vung}"}
    chon = [(v, ten.get(v) or nhan) for v, nhan in LOC
            if not (v == "near" and not gan)]
    return ("<span class=vlabel>Place</span>"
            + _chips("loc", chon, flt.loc, flt, dem))


def _list(jobs: list[dict], flt, counts: dict,
          gan: str = "", vung: str = "UK", dem: dict | None = None) -> str:
    # ONE chip instead of two. "Can't tell" sat on the chance row and "Not
    # scorable" on the score row — and measured on the real store they are the
    # same pile (185 postings missing both, 0 missing only one). One cause:
    # the deep-read pass has not reached that posting, so there is no
    # description to read.
    #
    # Pressing it resets both ladders to "All": the ladders demand that the
    # machine could read the posting, this chip demands the opposite — leave
    # both on and the list is always empty.
    chua = (f"<a class='vchip{' on' if flt.raw else ''}'"
            f" href='{esc(flt.url(raw='' if flt.raw else '1', chance='', band=''))}'"
            f" title='Postings with no description yet, so the machine could not"
            f" score them — another deep-read pass fixes it'>Not read yet</a>")
    # THREE ROWS, TWO ENDS EACH. There used to be four rows all hugging the
    # left, each using 25-50% of the width and leaving the right side empty —
    # and this panel is nearly 2000px wide.
    #
    # Paired BY MEANING, not to fill space:
    #   row 1  which pile  ←→  sorted how    (two questions covering the whole list)
    #   row 2  the two ladders  ←→  the chip demanding THE OPPOSITE of them
    #   row 3  found how  ←→  who posted it
    hang = lambda trai, phai: (f"<div class=vbar><span class=vgrp>{trai}</span>"
                               f"<span class=vgrp>{phai}</span></div>")
    head = (_tim(flt)
            + hang(_chips("show",
                          [(v, f"{l} {counts.get(v, 0):,}") for v, l in SHOW],
                          flt.show, flt),
                   "<span class=vlabel>Sort by</span>"
                   + _chips("sort", SORT, flt.sort, flt))
            + hang(_thang("chance", "Chance", CHANCE, flt.chance, flt, dem)
                   + _thang("band", "Score", BAND, flt.band, flt, dem),
                   chua)
            # PLACE at the left end — that is the main question about a
            # posting. On the right is PROVENANCE: who posted it (agency or
            # employer) and how we found it. No fourth row: a row with only
            # one end leaves half the screen empty again, exactly what was
            # fixed yesterday.
            + hang(_noi(flt, gan, vung, dem),
                   _chips("via", VIA, flt.via, flt, dem)
                   + _chips("found", FOUND, flt.found, flt, dem)))
    if not jobs:
        # Say WHAT came back empty, and offer the way back. "no postings
        # match" while halfway through typing a word reads as an empty store.
        trong = (f"no posting contains “{esc(flt.q)}” — "
                 f"<a href='{esc(flt.url(q=''))}'>clear the search</a>" if flt.q
                 else "no posting matches")
        return head + f"<div class=empty-box>{trong}</div>"
    return (head + "<div class=jlist>" + "".join(_row(j) for j in jobs)
            + "</div>" + _pager(flt, counts.get(flt.show, 0)))


def _pager(flt, total: int) -> str:
    """Without page buttons, only 50 of 132 jobs can ever be seen — the other
    82 may as well not exist."""
    # Taken from flt.limit() rather than importing PER_PAGE: imported by
    # value, the number freezes at module load and a test cannot change it to
    # build a multi-page situation.
    per, _offset = flt.limit()
    pages = max(1, -(-total // per))
    if pages < 2:
        return ""
    prev = (f"<a class=vchip href='{esc(flt.url(page=flt.page - 1))}'>← prev</a>"
            if flt.page > 1 else "<span class='vchip off'>← prev</span>")
    nxt = (f"<a class=vchip href='{esc(flt.url(page=flt.page + 1))}'>next →</a>"
           if flt.page < pages else "<span class='vchip off'>next →</span>")
    return (f"<div class=pager>{prev}"
            f"<span class=muted>page {flt.page}/{pages:,} · {total:,} jobs</span>"
            f"{nxt}</div>")


# ---------------------------------------------------------------- the sieve

def _tags(titles: list[str]) -> str:
    """The tag box: type a title and press Enter to add, press × to remove.

    Each tag carries an <input hidden name=job_titles>, so the form submits a
    LIST of values — not a block of text the server then splits into lines.
    With a text block the user has to remember the "one per line" rule, and a
    blank line or a stray comma yields a junk job title.
    """
    chips = "".join(
        f"<span class=tag>{esc(t)}"
        f"<input type=hidden name=job_titles value='{esc(t)}'>"
        # type=button, or pressing × submits the whole form
        f"<button type=button class=untag data-untag title='remove'>×</button>"
        f"</span>" for t in titles)
    return (f"<div class=tagbox data-tags>{chips}"
            "<input class=taginput type=text autocomplete=off"
            " placeholder='add a job title…'></div>")


def _missed(missed: list[dict]) -> str:
    """Job titles the sieve is missing that look like Vin's kind of work.

    The sieve is a handful of hand-typed strings: one missing string loses a
    whole run of postings, and loses them IN SILENCE. Measured on 10/09:
    `Quantitative Trader` was dropped nine times, all at Jane Street; 47
    `machine learning` postings were dropped, while ML is the highest-demand
    slot (56/178).

    The machine does NOT widen the sieve itself — widening it changes the
    profile, and a changed profile means the whole table is re-judged. It only
    points; pressing drops the tag into the box above, and Apply still has to
    be pressed like any other change.
    """
    if not missed:
        return ""
    chips = "".join(
        f"<button type=button class=addtag data-addtag='{esc(m['title'])}'"
        f" title='{esc(', '.join(m['firms'][:3]))}'>"
        f"+ {esc(m['title'][:34])}<b>{m['n']}</b></button>" for m in missed)
    return (f"<div class=missed><div class=missedhead>"
            f"the sieve is missing these — press to add</div>{chips}</div>")


def _sieve(sieve: dict) -> str:
    """The KEEP/DROP sieve editor. A real FORM, not a read-only table.

    The values live in THE PROFILE — editing here edits the profile, and that
    changes the scores too (job titles are part of the scoring formula). That
    sentence has to be written out, not left unsaid.
    """
    levels = "".join(
        f"<label class=tick><input type=checkbox name=seniority value='{esc(v)}'"
        f"{' checked' if v in sieve['seniority'] else ''}>{esc(l)}</label>"
        for v, l in sieve["seniority_options"])
    markets = "".join(
        f"<label class=tick><input type=checkbox name=markets value='{esc(v)}'"
        f"{' checked' if v in sieve['markets'] else ''}>{esc(l)}</label>"
        for v, l in sieve["market_options"])

    # THE SOURCE SWITCHES — OUTSIDE the form. They are not profile data:
    # pressing acts at once, bypasses Apply, and re-judges no 5,000 postings.
    #
    # They sit at the top because they are the coarsest switch: turn a source
    # off and every knob below only acts on what is left.
    nguon = "".join(
        f"<button class='mbtn tiny srcbtn {esc(k)}{'' if on else ' off'}'"
        f" data-post='/api/source' data-arg='{esc(k)}'"
        f" title='{esc(mo)}'>{dau} {esc(k)} · {'on' if on else 'off'}</button>"
        for k, dau, on, mo in (
            ("board", FOUND_BY["board"][0], sieve.get("src_board", True),
             "the company's own careers board — plain HTTP, ~20 seconds"),
            ("linkedin", FOUND_BY["linkedin"][0], sieve.get("src_linkedin", True),
             "keyword search on LinkedIn — opens Chrome, far slower. Turning "
             "it off only stops the keyword typing; postings from other "
             "sources are still deep-read and scored"),
            ("alert", FOUND_BY["alert"][0], sieve.get("src_alert", True),
             "LinkedIn job alert emails in the mailbox — the fastest, and no "
             "scraping. A SOURCE OF ITS OWN: runs the whole line even while "
             "LinkedIn is off")))

    return (
        "<label class=slab>Sources<span>press to turn on/off · acts at once, "
        "no Apply needed</span></label>"
        f"<div class=srcrow>{nguon}</div>"
        "<form class=sieve method=post action='/api/sieve'>"
        "<label class=slab>Job titles aimed at<span>type and press Enter to "
        "add · they are both the keywords sent to LinkedIn and the condition "
        "for keeping a posting</span></label>"
        + _tags(sieve["titles"])
        + _missed(sieve.get("missed") or [])
        + "<label class=slab>Seniority accepted</label>"
        f"<div class=ticks>{levels}</div>"
        "<label class=slab>Markets<span>decides where LinkedIn searches, and "
        "which postings are kept</span></label>"
        f"<div class=ticks>{markets}</div>"
        # The button has to state the consequence FIRST. A bare "Save" leaves
        # whoever presses it unaware they just re-judged the whole table.
        "<div class=stick>"
        "<button class='mbtn apply' type=submit>Apply</button>"
        f"<div class=applynote>re-judges <b>{sieve['total']:,}</b> postings "
        f"already fetched (~{sieve['seconds']} seconds) · this is your "
        "<b>profile</b>, editing it here changes the scores too</div></div>"
        "</form>")


def adjust(sieve: dict) -> str:
    """The fragment for the ⚟ overlay — THE SIEVE.

    Why the sieve goes in here and THE FILTERS do not: the filters
    (show/chance/band/sort) get pressed every few seconds while skimming the
    list, and hiding them in a menu slows the skim right down. The sieve is
    changed every few months, and each change re-judges every posting in the
    store. The difference: FILTERING what you are looking at ≠ CHANGING what
    the machine goes out to collect.
    """
    return f"<div class=sheethead>Adjust · Search</div>{_sieve(sieve)}"


# ---------------------------------------------------------------- the page

def render(*, jobs: list[dict], flt, counts: dict, sieve: dict,
           stage: dict | None = None, dem: dict | None = None) -> str:
    info = stage or {}
    return runtime.render(
        title="Search", active="/search", stream="search",
        reload="search",
        # THIS STAGE's bar: its own metrics and its own run/stop buttons. The
        # two buttons "Run now"/"Auto-scan on" used to sit on an app-wide bar
        # while controlling only this stage.
        bar=deck(
            "search", "Search",
            info.get("state", "never scanned"),
            # role -> colour: see the rule in layout.deck()
            # "kept" is read from stage, NOT from counts: counts follow the
            # search box and the chips, while this bar speaks about THE STORE,
            # not the view. The view's number is already there — it is "shown"
            # at the end of the row.
            # EVERY NUMBER MUST ANSWER "what do I do tonight". The old bar had
            # four numbers and not one of them could: "363 kept" and "364
            # worth applying" are two counts of the same pile so they nearly
            # coincide, "0 new" is always 0 except right after a scan, and "50
            # shown" is the page size — the list right below already says it.
            [(f"{info.get('hang_doi', 0):,}", "to apply to", "act"),
             (f"{info.get('worth', 0):,}", "worth applying", "stock"),
             (f"{info.get('fresh', 0):,}", "just in", "new"),
             (f"{info.get('da_nop', 0):,}", "applied", "view")],
            adjust="/adjust/search",
            run=info.get("run_label", "Run"),
            run_note=info.get("run_note", ""),
            # HOW MANY POSTINGS ARE ABOUT TO GO sits right on the armed
            # button. "Are you sure?" cannot state the cost; "Drop 5,166
            # postings?" can.
            xoa=("/api/search/xoa", "Clear store",
                 f"Drop {info.get('ca_kho', 0):,} postings?",
                 "Delete the posting store to scan again from scratch. "
                 "Postings with an application are KEPT. The profile, the "
                 "applications and the sieve are untouched.")),
        # The sieve moved into ⚟, so the left column has nothing to do. The
        # list — what Vin actually reads — takes the full width. The journal
        # goes back to a flat strip along the bottom.
        cols=1, journal="bottom",
        panels=[
            runtime.panel("What it found",
                          _list(jobs, flt, counts, dem=dem,
                                gan=info.get("gan", ""),
                                vung=info.get("vung", "UK")), span=1),
        ],
    )
