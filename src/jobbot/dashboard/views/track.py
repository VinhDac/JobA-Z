"""Track — steps 5 and 6. One row per application.

    THE MACHINE FILLS -> a "filling in" row appears
    VIN SENDS         -> the confirmation email arrives, the row becomes "applied"
    MAIL COMES BACK   -> it proposes the next state change
    THE TABLE         -> every row, readable and editable

Mail is THE SENSOR, the table is THE STATE. Not two features, one loop.

The machine does NOT press Submit. It fills in what it can prove and stops;
three questions like sponsorship or graduation date are Vin's, and so is the
final click. That boundary lives in `apply/run.py` — there is no Submit click
anywhere in it.

DRAWING ONLY.
"""

from __future__ import annotations

from html import escape as esc
from urllib.parse import quote

from ...track.board import OPEN, SILENT_AFTER, SONG_IM, STAGE_LABEL
from . import runtime

# FOUR GROUPS, ordered by WHAT HAS TO BE DONE rather than alphabetically.
#
# `stage` alone is not enough: "applied" yesterday and "applied" 40 days ago
# followed by total silence are two very different situations, and the old
# table drew them identically.
NHOM = (
    ("nong", "They are talking to you",
     "the most important thing on this screen"),
    ("cho", "Still inside the reply window",
     "under {n} days since the last contact — there may still be news"),
    # "TREATED AS REJECTED", not "silent too long". This is the user's
    # decision rather than something the machine invented, so it is said in
    # the words of an outcome — "silent too long" describes the weather,
    # "treated as rejected" is a closed box. The words "treated as" keep it
    # truthful: they have said nothing at all.
    ("im", "Treated as rejected",
     "over {n} days without a word — they have NOT said anything, this is "
     "your inference. Measured on your mailbox: {tl} applications did get a "
     "reply, and the longest silence that ever ended in one was {max} days. "
     "Change the mark at the ⚟ button on the bar"),
    ("xong", "Settled", "there is an outcome; kept here for the full picture"),
)


# --------------------------------------------------------- search + filters
#
# Built to the same pattern as "What it found" on Search: a GET search form,
# a chip row acting at once with no Apply button, and all the state on the URL
# so it can be saved and gone Back from. Learn one tab and you know all three.

LOC = (
    ("ng", "Source", (("", "all"), ("board", "board"), ("linkedin", "linkedin"),
                      ("alert", "alert"), ("ngoai", "outside the app"))),
    ("ai", "Applied by", (("", "all"), ("mail", "applied earlier by hand"),
                          ("apply", "through the app"), ("auto", "the machine"),
                          ("tay", "you have to do by hand"))),
    ("tt", "Situation", (("", "all"), ("nong", "in conversation"),
                         ("cho", "still open"), ("im", "treated as rejected"),
                         ("xong", "settled"))),
    ("cv", "CV", (("", "all"), ("co", "have one"), ("khong", "none yet"))),
)


def _url(loc: dict, **doi) -> str:
    d = {**loc, **doi}
    cap = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in d.items() if v)
    return "/track" + ("?" + cap if cap else "")


def _hop_loc(r: dict, loc: dict) -> bool:
    """Does this row pass the filters currently set."""
    ng = loc.get("ng") or ""
    if ng == "ngoai" and r.get("nguon"):
        return False
    if ng and ng != "ngoai" and r.get("nguon") != ng:
        return False
    if (loc.get("ai") or "") and (r.get("origin") or "") != loc["ai"]:
        return False
    if (loc.get("tt") or "") and (r.get("song") or "") != loc["tt"]:
        return False
    cv = loc.get("cv") or ""
    if cv == "co" and not r.get("co_cv"):
        return False
    if cv == "khong" and r.get("co_cv"):
        return False
    q = (loc.get("q") or "").strip().lower()
    if q and q not in f"{r.get('company','')} {r.get('role','')}".lower():
        return False
    return True


def _thanh_loc(loc: dict, rows: list[dict]) -> str:
    """The search box plus four chip rows. Each chip carries THE ROW COUNT it
    would leave behind.

    That number is what turns a row of buttons into a tool: a chip that leads
    to 0 rows says so in advance, rather than being pressed only to reveal an
    empty table.
    """
    an = "".join(f"<input type=hidden name='{esc(k)}' value='{esc(v)}'>"
                 for k, v in loc.items() if k != "q" and v)
    xoa = (f"<a class=jfindx href='{esc(_url(loc, q=''))}'"
           f" title='Clear the search, show all'>×</a>" if loc.get("q") else "")
    o = (f"<form class=jfind method=get action='/track'>{an}"
         f"<input class=search type=search name=q value='{esc(loc.get('q') or '')}'"
         f" autocomplete=off spellcheck=false"
         f" placeholder='search the table — company or role'>{xoa}</form>")
    def _nhom(ma, ten, chon) -> str:
        nut = ""
        for gia, nhan in chon:
            dem = sum(1 for r in rows if _hop_loc(r, {**loc, ma: gia}))
            on = (loc.get(ma) or "") == gia
            nut += (f"<a class='vchip{' on' if on else ''}"
                    f"{' nil' if not dem else ''}'"
                    f" href='{esc(_url(loc, **{ma: gia}))}'>{esc(nhan)}"
                    f"<b>{dem}</b></a>")
        return f"<span class=vgrp><span class=locten>{esc(ten)}</span>{nut}</span>"

    # TWO GROUPS PER ROW, exactly how "What it found" lays them out. Four
    # separate rows and the filters alone eat 120px, leaving the 37-row table
    # below with exactly two rows of space.
    d = {ma: (ten, chon) for ma, ten, chon in LOC}
    hang = (f"<div class=vbar>{_nhom('ng', *d['ng'])}{_nhom('ai', *d['ai'])}</div>"
            f"<div class=vbar>{_nhom('tt', *d['tt'])}{_nhom('cv', *d['cv'])}</div>")
    return o + f"<div class=locbox>{hang}</div>"


# ------------------------------------------------------------ one row

def _chi_tiet(r: dict, thu: list[dict]) -> str:
    """THE INSIDE of a row — opened by clicking.

    Three things, and all three are ways ONWARD rather than text to read:
        mail received   the evidence behind every state on this row
        the CV sent     opens the exact page that went out
        the original    the JD the app found, if it can be connected
    """
    o = ""
    if thu:
        muc = "".join(
            f"<li><span class=dtkind>{esc(m['kind'])}</span>"
            f"<span class=dtsub>{esc(' '.join((m['subject'] or '').split())[:96])}</span>"
            f"<span class=dtwhen>{esc(str(m['received_at'])[:10])}</span>"
            f"<span class=dtsnip>{esc(' '.join((m['snippet'] or '').split())[:150])}</span>"
            f"</li>" for m in thu)
        o += (f"<div class=dtblock><b>{len(thu)} messages received</b>"
              f"<ul class=dtlist>{muc}</ul></div>")
    else:
        o += ("<div class=dtblock><span class=muted>not one message — the "
              "company has not replied, or the message falls outside the "
              "window being read</span></div>")

    # NO BUTTON HERE CHANGES THIS ROW. The inside of a row is A RECORD: mail
    # received, the CV sent, the original posting. All of it is for LOOKING.
    # The job "the machine could not apply for you, do it yourself" moved to
    # the Queue — it is work, and this table holds no work.
    duong = ""
    if r.get("posting_id"):
        duong += (f"<a class='mbtn tiny' href='/jobs/{r['posting_id']}/cv?tu=/track'>"
                  f"The CV sent</a>"
                  f"<a class='mbtn tiny' href='/jobs/{r['posting_id']}?tu=/track'>"
                  f"Original · {esc(r.get('nguon') or 'posting')}</a>")
        if r.get("url"):
            duong += (f"<a class='mbtn tiny' href='{esc(r['url'])}'"
                      f" target=_blank rel=noopener>Open the live posting ↗</a>")
    else:
        # SAY OUTRIGHT WHY IT IS EMPTY. "Nothing here" in silence makes the
        # user think the app is broken; said outright, they know this was an
        # application made outside the app.
        duong += ("<span class=muted>applied outside the app — there is no JD "
                  "and no machine-built CV. The machine knows about this "
                  "application only from the email.</span>")
    return f"<div class=dtail>{o}<div class=dtact>{duong}</div></div>"


# NINE COLUMNS, EACH WITH A LABEL — a spreadsheet, not a list of cards.
#
# The previous version crammed company and role into one cell and DROPPED the
# header row entirely when it moved to clickable cards. Losing the column
# labels loses the way to read it: the user has to guess whether "20 days" is
# days since applying or days of silence.
#
# Still <details> so a row opens in place — a <table> cannot open without
# JavaScript, and these screens of the app have not one line of JS. The header
# row uses EXACTLY the same column grid as a data row, so they line up.
#
# THE ACTION COLUMN IS GONE, and it was why the table was crooked all along:
# the last column declared `auto`, and `auto` sizes to CONTENT. The last
# header cell was empty so it was 0 wide; the last data cell had two buttons
# so it was 110 — and the two leading `fr` columns split the slack differently
# by exactly 110px, so every row drifted off its own label. No track sizes to
# content now: see `--cot` in app.css.
COT = ("company", "role", "source", "applied by", "applied", "last contact",
       "mail", "CV", "state")


def _dau_bang() -> str:
    return ("<div class=thead>" + "".join(
        f"<span>{esc(c)}</span>" for c in COT) + "</div>")


def _trang_thai(r: dict, nguong: int) -> str:
    """The badge in the STATE column — and it must SAY THE SAME THING as the
    group heading.

    The previous version printed `stage` straight through, so a row silent for
    21 days sat under the heading "Treated as rejected" with a green "applied"
    badge. Two contradictory sentences on the same row, and the eye reads the
    badge rather than a group heading five rows up — so the user concluded the
    threshold was not working.

    BUT IT MUST NOT PRETEND THEY SAID NO. "rejected" is something they SAID;
    this is something we INFERRED. So the words differ ("treated as rejected")
    and the face differs — a dashed outline, grey, unfilled, unlike a real
    badge. One glance tells the two kinds apart.
    """
    stage = r["stage"]
    if r.get("song") == SONG_IM:
        return (f"<span class='pill suy' title='they have said nothing — over"
                f" {nguong} days without a word, so it was closed. Loosen the"
                f" mark at ⚟ and this row opens again'>treated as rejected</span>")
    return (f"<span class='pill {esc(stage)}'>"
            f"{esc(STAGE_LABEL.get(stage, stage))}</span>")


def _dong(r: dict, thu: list[dict], nguong: int = SILENT_AFTER) -> str:
    """ONE application = one spreadsheet row; clicking opens its inside below.

    FACTS ONLY. No button here changes any row — everything needing a decision
    or an edit lives in the Queue. A table that is both a place to read and a
    place to press can never be read in peace: the eye is tracking a column
    while the hand is next to a button that really changes a state.
    """
    stage = r["stage"]
    im = r.get("im_ngay")
    qua = im is not None and im >= nguong
    cham = (f"<b>{im}</b>d" if im is not None else "—")
    if r.get("ho_tra_loi"):
        cham += "<i>they replied</i>"
    elif (r.get("so_thu") or 0) <= 1:
        cham += "<i>not a word</i>"
    ng = r.get("nguon") or ""
    cv = ("<a class=plink href='/jobs/%s/cv?tu=/track'>open</a>" % r["posting_id"]
          if r.get("posting_id") else "<span class=muted>—</span>")
    return (
        f"<details class='trow {esc(stage)} s{esc(r.get('song') or '')}"
        f"{' qua' if qua else ''}'>"
        f"<summary>"
        f"<span class=c1><b>{esc(r['company'][:34])}</b></span>"
        f"<span class=c2>{esc((r.get('role') or '—')[:44])}</span>"
        f"<span class=c3>" + (f"<i class='src {esc(ng)}'>{esc(ng)}</i>" if ng
                              else "<i class='src ngoai'>outside</i>") + "</span>"
        f"<span class=c4>{esc(r.get('ai_nop') or '—')}</span>"
        f"<span class=c5>{r['days']}d</span>"
        f"<span class=c6>{cham}</span>"
        f"<span class=c7>{r.get('so_thu') or 0}</span>"
        f"<span class=c8>{cv}</span>"
        f"<span class=c9>{_trang_thai(r, nguong)}</span>"
        f"</summary>{_chi_tiet(r, thu)}</details>")


def _table(rows: list[dict], thu: dict | None = None,
           loc: dict | None = None, nguong: int = SILENT_AFTER,
           lau: int = 0) -> str:
    loc = loc or {}
    thu = thu or {}
    if not rows:
        return ("<div class=empty-box>nothing applied to yet. Go to the Search "
                "tab and press <b>Apply</b> on a posting — the machine opens "
                "the application page, fills in what it can prove, and leaves "
                "you to press Submit.</div>")
    loc_ui = _thanh_loc(loc, rows)
    hien = [r for r in rows if _hop_loc(r, loc)]
    if not hien:
        return (loc_ui + "<div class=empty-box>no row passes the filters "
                "currently set — drop one of the chips above.</div>")
    nhap = [r for r in hien if r["stage"] == "draft"]
    tong = [r for r in hien if r["stage"] != "draft"]
    tra_loi = [r for r in tong if r.get("ho_tra_loi")]

    body = "".join(_dong(r, thu.get(r["id"], []), nguong) for r in nhap)
    da_ve = set()
    for ma, ten, y in NHOM:
        trong = [r for r in tong if r.get("song") == ma]
        if not trong:
            continue
        da_ve.update(id(r) for r in trong)
        chu = y.format(n=nguong, tl=len(tra_loi), max=lau)
        body += (f"<div class='tgroup g{ma}'><b>{esc(ten)}</b>"
                 f"<span>{len(trong)}</span><i>{esc(chu)}</i></div>")
        body += "".join(_dong(r, thu.get(r["id"], []), nguong) for r in trong)
    # NO ROW MAY VANISH. Grouping means a row falling into no group does not
    # get drawn — a real application quietly leaves the screen with nothing to
    # announce it.
    con = [r for r in tong if id(r) not in da_ve]
    if con:
        body += (f"<div class=tgroup><b>Could not be grouped</b>"
                 f"<span>{len(con)}</span></div>"
                 + "".join(_dong(r, thu.get(r["id"], []), nguong) for r in con))
    return loc_ui + f"<div class=tboard>{_dau_bang()}{body}</div>"


def _mailbox(ready: bool, address: str, days: int = 30) -> str:
    """The mailbox line at the head of the table — WORK ONLY, no configuration.

    The address + app password fields moved to Settings · Gmail. That is
    something connected once and then forgotten, while Vin opens this page
    daily; leaving a configuration form at the head of his work table makes
    his eye reread it every day.

    What stays here is THE WORK: press Scan mail. Not connected yet, and it
    points at exactly where to connect.
    """
    if not ready:
        return ("<div class=boxrow><span class=muted>no job mailbox connected "
                "— replies will not update this table by themselves</span>"
                "<button class='mbtn apply' data-appset='gmail'>"
                "Connect a mailbox…</button></div>")
    # "saved", NOT "connected": all this place knows is that the config HAS a
    # string, not whether that string can still log in. Have Google revoke the
    # app password and this line stays green, and Vin believes the mailbox is
    # running.
    # THE SCAN BUTTON MOVED TO THE STAGE BAR. Leaving one here too gives two
    # buttons doing one job, and the user has to guess whether they differ.
    return (f"<div class=boxrow><span class=boxok>mailbox "
            f"<b>{esc(address)}</b> · reading the last {days} days — press "
            f"<b>Scan mail</b> on the bar above</span></div>")


def _nguong_num(dang: int, do: dict | None = None) -> str:
    """The SILENCE MARK knob — how many days of silence counts as a rejection.

    FIVE LEVELS, not a number field. A number field hands the user a question
    they have no data to answer ("is 87 better than 86?"); five levels each
    have a readable meaning, and the one in use carries a ✓.

    THE NUMBERS IN THE CAPTION ARE MEASURED, not hardcoded: reply times belong
    to each individual mailbox. Hardcode "14 days" and on the day a reply
    arrives after 19, the app still lectures with the old number.
    """
    from ...core import prefs
    d = do or {}
    tl, tong = d.get("tra_loi", 0), d.get("tong", 0)
    lau, ai, khoang = d.get("lau", 0), d.get("ai", ""), d.get("khoang") or []
    nut = ""
    for muc in prefs.IM_MUC:
        n = int(muc)
        on = n == dang
        # EVERY LEVEL DECLARES ITS OWN COST, counted on real mail: set this
        # mark and how many messages actually arrived LATER THAN THAT — i.e.
        # how many rows would have been closed wrongly. That is the only
        # question this knob has to answer; "more days or fewer" the user can
        # already read off the number.
        nham = sum(1 for k in khoang if k >= n)
        y = (f"set {n} days and {nham} REAL messages in your mailbox arrived "
             f"after the row had been closed" if nham else
             f"set {n} days and not one message in your mailbox would have "
             f"been closed out wrongly")
        nut += (f"<button class='mbtn tiny{' on' if on else ' off'}'"
                f" data-post='/api/track/num' data-arg='im_qua:{muc}'"
                f" title='{esc(y)}'>{'✓ ' if on else ''}{muc} days"
                + (f"<i class=nham>{nham} closed wrongly</i>" if nham else "")
                + "</button>")
    dem = (f"measured on your mailbox: <b>{tl}/{tong}</b> applications did get "
           f"a reply, and the longest silence that EVER ENDED IN ONE was "
           f"<b>{lau}</b> days"
           + (f" ({esc(ai)})" if ai else "")
           if tong else "no application yet to measure on")
    return (f"<div class=adjrow><div class=adjname><b>Treat as rejected after</b>"
            f"<span>how long a silence closes the row</span></div>"
            f"<div class=srcrow>{nut}</div></div>"
            f"<div class=note>{dem}. This is AN INFERENCE, never written into "
            f"the table: they have said nothing. Change the number and every "
            f"row regroups at once, and raising it puts them back exactly "
            f"where they were — no row is lost.</div>")


def adjust(nop: dict | None = None, nguong: int = SILENT_AFTER,
           do: dict | None = None) -> str:
    """The Track stage's ⚟ overlay — THE SILENCE MARK, then THE THREE SOURCES.

    THE MARK COMES FIRST because it changes what the user SEES on the table in
    front of them; the three source switches change what happens on the next
    application run. The knob that takes effect sooner goes on top.

    On Search the three identically named switches ask "should this source be
    SCANNED"; here they ask "should postings from this source be APPLIED TO".
    Two quite different jobs, so two sets of switches — merge them and turning
    LinkedIn off to stop applying also loses 2,409 postings from the store,
    leaving the user unable to explain why Search is empty.
    """
    from ...core import prefs
    d = nop or {}
    hang = ""
    for khoa, (ten, y) in prefs.NOP.items():
        on = bool(d.get(khoa))
        hang += (f"<div class='swrow{'' if on else ' off'}'>"
                 f"<button class='mbtn tiny swbtn{'' if on else ' off'}'"
                 f" data-post='/api/track/num' data-arg='{esc(khoa)}:"
                 f"{'0' if on else '1'}'>{'ON' if on else 'OFF'}</button>"
                 f"<b class=swten>{esc(ten)}</b>"
                 f"<span class=swnow>{'applies' if on else 'skipped'}</span>"
                 f"<details class=swwhy><summary>why</summary>"
                 f"<div class=swbody>{esc(y)}</div></details></div>")
    return ("<div class=sheethead>Adjust · Track</div>"
            "<div class=adjbox>"
            "<div class=adjsec>When to stop waiting"
            "<span>the table can only shrink if there is a mark that closes a "
            "row</span>"
            "</div>"
            + _nguong_num(nguong, do)
            + "<div class=adjsec>Which sources to apply to"
            "<span>different from the Search switches — those decide what is "
            "SCANNED</span></div>"
            + hang
            + "<div class=note>Turning LinkedIn off does <b>not</b> drop every "
              "LinkedIn posting: most of them lead out to the company's own "
              "application page and can still be applied to. Only the ones "
              "that force LinkedIn's own form are left to you.</div></div>")


def render(*, rows: list[dict], asks: list[dict] | None = None,
           counts: dict | None = None,
           mu: list[dict] | None = None, stage: dict | None = None,
           thu: dict | None = None, loc: dict | None = None,
           mail_ready: bool = False, mail_address: str = "",
           mail_days: int = 30) -> str:
    from ..layout import deck
    info = stage or {}
    scan = _mailbox(mail_ready, mail_address, mail_days)
    # THE OLD `note` LINE IS GONE. It printed "37 applications · 35 waiting ·
    # 35 silent" — "waiting" and "silent" were nearly equal because most of
    # what is waiting IS what has gone silent. Two counts of one pile, and
    # neither said what to do. Replaced by `_tom`: four numbers, one job each.
    return runtime.render(
        title="Track", active="/track", stream="search", journal="bottom",
        # REDRAW when the TRACK stage finishes, not when the scan finishes.
        # This table is built from applications + mail, while a scan only
        # produces postings — jumping the page when a scan ends slams shut
        # every half-open row, right while the user is reading an email. The
        # journal panel still watches the `search` stream because that is the
        # long-running stage and the one worth watching; two different things.
        reload="track",
        cols=1,
        bar=deck("track", "Track", info.get("state", "nothing applied to yet"),
                 # REJECTED and SILENT are TWO numbers, never merged: rejected
                 # is something they SAID, silent is something they have NOT
                 # said — merging them loses the one distinction between "dead"
                 # and "unknown".
                 [(f"{info.get('da_nop', 0)}", "applied", "stock"),
                  (f"{info.get('di_tiep', 0)}", "taken further", "act"),
                  (f"{info.get('truot', 0)}", "rejected", "view"),
                  (f"{info.get('cho_ban', 0)}", "waiting on you", "new")],
                 adjust="/adjust/track",
                 # THE QUEUE BUTTON — the door to the Queue screen. The number
                 # on it is precisely the "waiting on you" figure to its left:
                 # the only place that can be dealt with. Without the number
                 # the button is mute, and the user has no reason to press it.
                 sua=("/track/queue",
                      f"Queue {info.get('cho_ban', 0)}" if info.get("cho_ban")
                      else "Queue",
                      "Messages the machine could not settle — decide them "
                      "there in one pass"),
                 run="Scan mail", run_note="read the mailbox and update the table",
                 # THE APPLY BUTTON — opens the application page for the next
                 # worth-applying posting not yet applied to. It is the bridge
                 # to the Search tab: this table says "how many places are
                 # worth applying to", this button goes and applies to the
                 # first.
                 them=("/api/track/nop-tiep", "Apply",
                       f"{info.get('hang_doi', 0)} postings worth applying to "
                       f"are unapplied — open the application page for the "
                       f"highest-scoring one"),
                 xoa=("/api/track/xoa", "Clear table", "Really delete?",
                      "Drop every application RECONSTRUCTED FROM MAIL. The "
                      "ones you applied to through the app, and the mail "
                      "already read, are untouched")),
        panels=[runtime.panel(
            "Applied",
            # THE SAME ORDER AS "WHAT IT FOUND": search box -> chip rows ->
            # table.
            #
            # The previous version squeezed 16 mail cards in between, so the
            # search box sat more than a screen down — the user had to scroll
            # past a heap of mail to reach the thing that filters the table.
            # Mail needing a decision is A DIFFERENT JOB, so it got its own
            # screen.
            f"<div class=tracktop>{scan}</div>"
            + _table(rows, thu, loc, info.get("nguong") or SILENT_AFTER,
                     (info.get("do") or {}).get("lau", 0)),
            # ONE PANEL, taking the full height. Mail needing a decision moved
            # to /track/queue — this tab holds only what is settled, so it is
            # clean and it is the table.
            span=1, rows=1)],
    )
