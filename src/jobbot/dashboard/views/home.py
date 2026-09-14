"""Home — the profile-building run. This is the app's FRONT DOOR.

This page used to be blank: a new user opened the app, landed here first, and
nobody told them what to do. The other four tabs all knew how to point the way
("run Search first", "three sentences still missing") — only the front door
was silent.

This page invents NO rule of its own. It reads `live.onboarding()` — the same
gate Search and Profile read — and draws the route: what is done, what is not,
what comes next, and clicking takes you straight to the field.

Three sentences open the gate, 35 is enough. So the page has two phases:

    gate NOT open  -> there is only one job: finish those three sentences.
                      Nothing else in the app can run yet, and showing more
                      only gets in the way.
    gate open      -> this list becomes a "make it stronger" MENU: each part
                      says what adding it lets the app do better.
"""

from __future__ import annotations

from html import escape as esc

from ..layout import page

# What adding this part lets the app do better — said as a consequence, not as
# a field name. "Add skills" persuades nobody; "scoring stops guessing" does.
LOI = {
    "muc_tieu": "Without this the app does not know what to look for — it cannot scan.",
    "rang_buoc": "Filtering here is far cheaper than reading first and rejecting after.",
    # The most frequently asked question: "is there no work experience
    # section?". There is — it is read straight from the CV you imported (the
    # EXPERIENCE section) into blocks on the CV tab. Typing it again here
    # would create two sources for one truth.
    "nang_luc": "The raw material for scoring and CV building. Without it, scoring is guesswork.",
    "kinh_nghiem": "The first thing an employer reads. Every sentence you write here "
                   "is a sentence that can go on a CV.",
    "project": "A match gets you past the filter; evidence gets you into the called-back pile.",
    "danh_tinh": "Needed when building a CV and filling an application. Until then it can stay empty.",
}


def _thanh(xong: int, tong: int) -> str:
    pc = round(xong * 100 / tong) if tong else 0
    return (f"<div class=obar><span style='width:{pc}%'></span></div>"
            f"<div class=obarnum><b>{xong}</b>/{tong} questions answered</div>")


def _the(s: dict, mo: bool) -> str:
    """One part of the profile. `mo` = is the gate open — it changes the
    wording, not the rule."""
    if s["done"]:
        dau, lop, nut = "✓", " done", "Edit"
    else:
        dau, lop, nut = "", "", ("Fill it in" if s["required"] else "Add")

    nhan = ""
    if s["required"] and not s["done"]:
        nhan = "<span class='blkkind req'>REQUIRED</span>"
    elif s["optional"]:
        nhan = "<span class=blkkind>optional</span>"

    # Before the gate opens only the required parts speak up; the rest recede.
    mo_nhat = " dim" if (not mo and not s["required"] and not s["done"]) else ""
    return (
        f"<a class='blk ostep{lop}{mo_nhat}' href='{esc(s['href'])}'>"
        f"<span class=blkmain>"
        f"<span class=blkhead><b>{dau} {esc(s['title'])}</b>{nhan}"
        f"<span class=ocount>{s['answered']}/{s['total']}</span></span>"
        f"<span class=osub>{esc(LOI.get(s['id'], s['why']))}</span></span>"
        f"<span class='mbtn tiny'>{nut}</span></a>")


def sheet(state: dict) -> str:
    """The profile-building run — an HTML FRAGMENT for the overlay, not a page.

    It no longer occupies the Home tab: it has a job only at the start, while
    the Home tab is where the pipeline dashboard belongs. Before the gate
    opens this overlay raises itself on entering the app — that is the "make
    them fill it in" moment. Once open it disappears, and can be reopened from
    the Profile tab.
    """
    mo = state["gate_open"]
    ke = state["next"]

    if mo:
        gate = ("<div class='gate ok'><b>The profile is enough to run.</b> "
                "Go to the Search tab and press Run.</div>")
    else:
        thieu = " · ".join(esc(q["text"]) for q in state["gate_missing"])
        gate = (f"<div class='gate block'><b>Nothing can run yet.</b> "
                f"The app needs exactly these {len(state['gate_missing'])} "
                f"answers first: {thieu}</div>")

    if state["answered"] == 0:
        nut = ("<div class=octa>"
               "<a class='mbtn apply big' href='/profile/import'>"
               "Import a CV — the app fills it in →</a>"
               + (f"<a class=oalt href='{esc(ke['href'])}'>or type it yourself</a>"
                  if ke else "")
               + "</div>"
               "<p class=omeo>The machine reads the CV and PROPOSES each field "
               "— nothing is written until you tick it through. It deliberately "
               "does not guess <b>right to work</b>: the CV does not say, and a "
               "wrong guess ruins the whole application.</p>")
    elif ke:
        nut = (f"<a class='mbtn apply big' href='{esc(ke['href'])}'>"
               f"Continue — {esc(ke['title'])} →</a>")
    else:
        nut = ""

    return ("<div class=sheethead>Your profile</div>"
            "<div class=setupbody>"
            + _thanh(state["answered"], state["total"])
            + gate + nut
            + "<div class=blklist>"
            + "".join(_the(s, mo) for s in state["sections"])
            + "</div></div>")


# ---------------------------------------------------------------- OVERVIEW
#
# Home has NO job of its own, and that is the whole point of it: each of the
# other four tabs watches one stage, while the question "is this whole process
# actually working" cannot be answered from inside a single stage.
#
# EXACTLY ONE SCREENFUL, NO SCROLLING. The previous version laid everything
# out and ran twice the height of the window — showing more is not saying
# more, it is failing to choose. An overview page that has to scroll has
# stopped being an overview.
#
# So each panel holds EXACTLY ONE answer, and the explanation sits in
# `.chitiet` — shown only when that panel is opened with ⤢. Pure CSS
# (`.wid.big .chitiet`), not one extra line of JS: the ⤢ button is already on
# every panel.

def _ct(x: str) -> str:
    """The part SHOWN ONLY WHEN THE PANEL IS ENLARGED. Brief at a glance,
    complete under inspection."""
    return f"<div class=chitiet>{x}</div>"


def _ket_qua(k: dict) -> str:
    """THE HEART OF THE PAGE: apply to this many places, how many call back.

    One big number, not three equal ones. Three equal numbers are three
    numbers with none of them important, leaving the reader to choose for
    themselves — and choosing for the reader is exactly an overview page's
    job.
    """
    from . import bieudo as bd
    if not k.get("tong"):
        return ("<div class=empty-box>nothing applied to yet — nothing to judge. "
                "Go to <a href='/search'>Search</a> and press Apply on a posting."
                "</div>")
    pc = k["pc_di"]
    # THE HERO AND THE TWO SECONDARY NUMBERS SHARE A ROW. Stacked, the number
    # block alone eats 150px and this panel has to scroll on a short window —
    # and an overview panel that scrolls has stopped being an overview.
    hero = (f"<div class=qtop><div class=hero>"
            f"<b>{'—' if pc is None else f'{pc:g}%'}</b>"
            f"<span>taken further</span>"
            f"<i>{k['di_tiep']}/{k['tong']} applications</i></div>"
            f"<div class=hphu>"
            f"<span><b>{k['pc_hoi']:g}%</b>got a reply"
            f"<i>{k['hoi_am']}/{k['tong']}</i></span>"
            f"<span><b>{k['pc_truot']:g}%</b>rejected / treated as rejected"
            f"<i>{k['truot']}/{k['tong']}</i></span></div></div>")
    phu = ""
    thanh = bd.thanh_chia(
        [("taken further", k["di_tiep"], "qdi"),
         ("they said no", k["ho_noi"], "qtu"),
         (f"silent over {k['nguong_im']} days", k["suy"], "qim"),
         ("still waiting", k["cho"], "qcho")], k["tong"])
    # THE SAMPLE SIZE comes before any conclusion — but it is said WHEN
    # ENLARGED, because it is an instruction for reading rather than a number.
    # NOTHING SETTLED YET means there is NO ratio at all — `pc_di_xong` is
    # None.
    #
    # That case is not rare: a first-day user, every application still inside
    # the reply window. The previous version fed it straight into `:g` and the
    # Home page BLEW UP — on precisely the most important day for it to work.
    them = (f"<p>The ratio above is over the <b>settled</b> ones (leaving out "
            f"the {k['cho']} still waiting): <b>{k['pc_di_xong']:g}%</b> — "
            f"{k['di_tiep']}/{k['xong']}.</p>"
            if k["pc_di_xong"] is not None else
            f"<p>All <b>{k['cho']}</b> applications are still inside the reply "
            f"window — nothing has settled, so there is no ratio to state "
            f"yet.</p>"
            + (f"<p>Only <b>{k['tong']}</b> applications so far. Under 30, a "
               f"single call-back moves the number several points — read it as "
               f"a direction, not a conclusion.</p>" if k["tong"] < 30 else "")
            + f"<p>«Treated as rejected» is an <b>inference</b>, not something "
              f"they said: over {k['nguong_im']} days of silence and it is "
              f"closed. Change that mark at the ⚟ button on "
              f"<a href='/track'>Track</a>.</p>")
    return hero + phu + thanh + _ct(them)


def _nang_suat(n: dict, q: dict) -> str:
    """How much gets done each day, and whether the scan loop runs steadily."""
    from . import bieudo as bd
    dai = "".join(bd.dai_viec(v) for v in n["viec"].values())
    nhip = (f"<div class=nhip><b>{q['luot']}</b> scans / "
            f"<b>{q['ngay']}</b> days"
            + (f" · <b>{q['pc_ok']}%</b> clean" if q["pc_ok"] is not None else "")
            + (f" · <b class=xau>{q['hong_luot']}</b> failed scans"
               if q["hong_luot"] else "")
            + (f" · <b class=xau>{len(q['cam'])}</b> silent sources"
               if q["cam"] else "")
            + "</div>") if q["luot"] else ""
    return dai + nhip + _ct(_thoi_quen(n))


def _thoi_quen(n: dict) -> str:
    """By WEEKDAY and by MONTH — only series long enough IN THEMSELVES are drawn.

    Each series guards itself. Use the longest series as a shared gate and the
    "postings found by weekday" chart gets drawn over 2 days of data, where it
    will announce "Friday is nine times Saturday" — arithmetically right,
    entirely wrong in meaning.
    """
    from . import bieudo as bd
    o = ""
    for ma, v in n["viec"].items():
        if not v["du_thu"] and not v["du_thang"]:
            continue
        o += f"<div class=tqten>{esc(v['ten'])}</div>"
        if v["du_thu"]:
            o += bd.cot_thu(n["thu"][ma], list(n["ten_thu"]), v.get("mau", ""))
        if v["du_thang"]:
            o += bd.thang_gan(n["thang"][ma], mau=v.get("mau", ""))
    chua = [v["ten"] for v in n["viec"].values()
            if not v["du_thu"] and not v["du_thang"]]
    if not o:
        return bd.chua_du(n["ngay_co"], n["can_thu"])
    if chua:
        o += (f"<div class=note>Not grouped yet: {esc(' · '.join(chua))} — it "
              f"takes {n['can_thu']} days of data before this means "
              f"anything.</div>")
    return "<div class=tqhead>By weekday · by month</div>" + o


MUC = {"chac": ("solid", "counted directly, nothing inferred"),
       "vua": ("fair", "enough sample to believe, not enough to be sure"),
       "yeu": ("weak", "small sample — take it as a hint only")}


def _chan_doan(ds: list) -> str:
    """Signs of trouble, ORDERED BY HOW SOLID THEY ARE, not by how alarming.

    The confidence label sits on the face of the card: a directly counted
    number and an inference drawn from four samples that look alike send the
    user off fixing the wrong thing — and that is the worst way a statistics
    page can fail: it is not silent, it points the wrong way.

    Collapsed, only the NAME shows; the explanation and the "measured over how
    many" declaration sit behind ⤢. Four paragraphs stacked and nobody reads
    any of them.
    """
    if not ds:
        return ("<div class=empty-box>No sign of trouble so far. "
                "Run a few more rounds and come back.</div>")
    # THE FIRST THREE WHEN COLLAPSED. The list is already ordered by how solid
    # each is, so the first three are the three most trustworthy — and four
    # cards stacked in a 190px panel means none of them can be read. The rest
    # appear on ⤢.
    o = ""
    for i, x in enumerate(ds):
        nhan, y = MUC.get(x["muc"], ("", ""))
        o += (f"<a class='cdrow {esc(x['muc'])}{' chitiet' if i >= 3 else ''}'"
              f" href='{esc(x['di'])}'>"
              f"<span class=cdso>{esc(x['so'])}</span>"
              f"<span class=cdmain><b>{esc(x['ten'])}</b>"
              f"<span class=chitiet>{esc(x['y'])}</span>"
              f"<i class=chitiet>measured over {esc(x['tren'])}</i></span>"
              f"<span class=cdend><span class='cdmuc {esc(x['muc'])}'"
              f" title='{esc(y)}'>{esc(nhan)}</span>"
              f"<span class='mbtn tiny'>{esc(x['nut'])}</span></span></a>")
    con = len(ds) - 3
    them = (f"<div class=cdmore><b>{con}</b> more signs — press ⤢ to see them"
            f"</div>" if con > 0 else "")
    return f"<div class=cdlist>{o}</div>{them}"


def _pheu(d: dict, k: dict) -> str:
    """Drop-off from postings fetched to call-backs — TWO stages, with the join
    named."""
    from . import bieudo as bd
    noi, dang = d["noi"], d["dang"]
    chu = (f"<b>{d['cho_nop']}</b> postings worth applying to are waiting. "
           + (f"Only <b>{noi}</b> of them have been applied to — so the lower "
              f"stage is almost NOT the result of the upper one: most of the "
              f"applications happened before the app existed, and were "
              f"reconstructed from email."
              if noi < dang else ""))
    duoi = [("applied", k["tong"], "/track"),
            ("got a reply", k["hoi_am"], "/track"),
            ("taken further", k["di_tiep"], "/track")]
    return (bd.pheu(d["tim"]) + "<div class=pseam>· applied ·</div>"
            + bd.pheu(duoi) + _ct(f"<p>{chu}</p>"))


def adjust(bat: dict | None = None) -> str:
    """Home's ⚟ panel — THE THREE STAGES of a session.

    Different from Search's and Track's ⚟: those ask "which sources to scan",
    "apply to postings from which source" — questions inside one stage. Here
    the question is WHICH STAGES A SESSION CONTAINS, i.e. a layer above all
    three.

    Why each stage has to be switchable: the three cost very different
    amounts — reading mail 12 seconds, building CVs 5.3 seconds, while
    scanning LinkedIn has to open Chrome and takes half an hour. Someone who
    only wants the mailbox watched overnight turns the other two off, rather
    than choosing between "run everything" and "run nothing".
    """
    from ...core import prefs
    d = bat or {}
    hang = ""
    for khoa, (_khuc, ten, y) in prefs.PHIEN.items():
        on = bool(d.get(khoa))
        hang += (f"<div class='swrow{'' if on else ' off'}'>"
                 f"<button class='mbtn tiny swbtn{'' if on else ' off'}'"
                 f" data-post='/api/home/num' data-arg='{esc(khoa)}:"
                 f"{'0' if on else '1'}'>{'ON' if on else 'OFF'}</button>"
                 f"<b class=swten>{esc(ten)}</b>"
                 f"<span class=swnow>{'runs' if on else 'skipped'}</span>"
                 f"<details class=swwhy><summary>why</summary>"
                 f"<div class=swbody>{esc(y)}</div></details></div>")
    so_bat = sum(1 for k in prefs.PHIEN if d.get(k))
    return ("<div class=sheethead>Adjust · Session</div>"
            "<div class=adjbox>"
            "<div class=adjsec>What a session contains"
            "<span>run one after another, never in parallel</span></div>"
            + hang
            + ("<div class=note>The order is fixed: <b>Search → Make CV → "
               "Manage mail</b>. Building CVs reads the posting store, so it "
               "has to run after the search; run first and it lays out against "
               "the previous round's store.</div>"
               if so_bat else
               "<div class='note xau'>All three are OFF — the session will run "
               "and do nothing. Turn at least one stage on.</div>")
            + "</div>")


def render(state: dict, so: dict | None = None, stage: dict | None = None) -> str:
    """The Home tab — the overview board, ONE SCREENFUL, updating on the stream.

    AN EMPTY STREAM (`stream=""`) is deliberate: a journal panel with no stream
    named takes EVERY stream. REDRAWING the page is a parameter of its own
    (`reload="*"`) — two different questions, and folding them into one gets
    both wrong (see layout.page).

    FOUR PANELS, two rows, no scrolling. Left to right goes from CONCLUSIONS
    (the ratio, the diagnosis) to THE EVIDENCE BEHIND THEM (productivity, the
    funnel) — people open an overview to learn "is this all right", not to read
    a table of numbers.
    """
    from ..layout import deck
    from . import runtime
    d = so or {}
    info = stage or {}
    pheu = d.get("pheu") or {}
    k = d.get("ket_qua") or {}
    n = d.get("nang_suat") or {}
    q = d.get("nhip") or {}
    hn = d.get("hom_nay") or {}

    # THIS BAR IS TODAY'S BULLETIN, not a summary.
    #
    # The summary is already in the four panels below, and a number like "37
    # applied" looks the same whichever day you look — it cannot answer the one
    # question people ask a 24/7 watch station: DID IT GET ANYTHING DONE TODAY.
    #
    # The four numbers follow one application's life: found → applied → they
    # call → they reject. Reading left to right is reading a working day.
    do = [(f"{hn.get('tim', 0)}", "postings found", "stock"),
          (f"{hn.get('nop', 0)}", "applications sent", "act"),
          (f"{hn.get('tiep', 0)}", "taken further", "new"),
          (f"{hn.get('truot', 0)}", "rejections", "view")]
    return runtime.render(
        title="Overview", active="/", stream="", journal="bottom", cols=2,
        # "*" = ANY stage finishing redraws it. This is where the word "live"
        # becomes true; live.js used to read `stream=""` as false, so the
        # redraw branch never ran and Home only changed its numbers when the
        # user pressed F5.
        reload="*",
        setup="" if state.get("gate_open") else "/onboarding",
        # `stage="search"` is still the stage name sent with the Stop button —
        # the stop flag is set per stage, and Search is the only stage running
        # long enough to need interrupting.
        bar=deck("search", "Today", info.get("phien", "the session is OFF"), do,
                 adjust="/adjust/home",
                 run=info.get("nhan_phien", "Start session"),
                 run_note="runs the whole line — Search → Make CV → Manage "
                          "mail — then repeats 24/7. Choose which stages run at ⚟",
                 run_path="/api/session/start", stop_path="/api/session/stop"),
        # TWO ROWS SIZED BY THEIR CONTENT, with the slack all going to the
        # journal.
        #
        # `1fr 1fr` splitting evenly is wrong at both ends: on a tall window
        # the other four panels get a big empty band under each, and on a
        # short one they have to scroll. `auto` makes each panel exactly as
        # tall as what it holds — no waste, no scrolling — and the slack falls
        # to the journal, the ONE panel that deserves to scroll: there is
        # always another journal line.
        #
        # minmax(130px,1fr) keeps the journal from being squeezed to a hairline
        # on a short screen; below that the whole page scrolls, which is the
        # right way to fail.
        # `minmax(min-content,auto)`, NOT a bare `auto`: `auto` still lets the
        # grid compress a row on a narrow window, and since panels no longer
        # have a scroll frame their contents SPILL OUT — uglier than scrolling.
        # `min-content` is a hard floor: too little room and the whole page
        # scrolls, with every panel intact.
        rows_tpl="minmax(min-content,auto) minmax(min-content,auto)"
                 " minmax(130px,1fr)",
        # `cls="vua"` = this panel is NOT a scroll frame.
        #
        # This fixes the root cause rather than shaving off a few pixels:
        # `.wbody` defaults to `overflow:auto`, and a scroll frame has a
        # min-content of 0 — so the grid is free to SQUEEZE the panel as far as
        # it likes, leaving the contents to scroll. Drop the overflow and the
        # panel demands the height it needs, the `auto` row grants it, and when
        # the window really is too short THE WHOLE PAGE scrolls — failing the
        # right way, instead of four panels quietly scrolling at once.
        panels=[
            runtime.panel("Results · the whole process", _ket_qua(k),
                          at=(1, 1), cls="vua"),
            runtime.panel("Output per day", _nang_suat(n, q),
                          at=(2, 1), cls="vua"),
            runtime.panel("Diagnosis · what is going wrong",
                          _chan_doan(d.get("chan_doan") or []),
                          at=(1, 2), cls="vua"),
            runtime.panel("Funnel · where they drop off",
                          _pheu(pheu, k) if pheu else "",
                          at=(2, 2), cls="vua"),
        ],
    )
