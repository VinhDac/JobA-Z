"""The page frame: left sidebar + master bar + widget area.

DRAWING ONLY. No business rules, no DB reads.

Laid out like a desktop app, not a web page:
    a fixed left sidebar, running to the very top of the window
    a master bar along the top: RUN / PAUSE / what is running
    the content is WIDGETS — each scrolls inside itself, THE PAGE does not

Why widgets scroll rather than the page: this app runs 24/7, and opening it
has to show the whole picture at once. With a scrolling page half the
information sits below the fold, and the thing that is running may be in the
part nobody can see.
"""

from __future__ import annotations

from html import escape as esc

# (path, label, symbol)
# The order is the order the work really runs in, not alphabetical.
# A tab marked (rt) HAS A RUNTIME -> it uses the views/runtime.py frame.
#
# REMOVED: Settings (now the cog menu on the top bar — it is not a job, just
# switches you open, adjust and close), Jobs and Score. The job list lives
# inside Search — "search" and "look at what the search found" are one job.
# Scoring is not a system of its own, it is the last stage of the same scan.
# /jobs/<id> and /jobs/<id>/cv ARE STILL LIVE — the new list points at them.
# --------------------------------------------------------------- ICON SET
#
# STROKED SVG, NOT UNICODE CHARACTERS. The previous version used ◈ ⌕ ▤ ▣ ◇ —
# and they are not a set: each glyph was drawn by a different type designer
# for a different purpose, so optical size, stroke weight and baseline all
# disagree. With the sidebar COLLAPSED, CSS blows them up to 22px and the
# mismatch becomes obvious: ⌕ is tiny, ▤ is a solid block, ◇ is thread-thin.
# On top of that ◈ ▣ ▤ cannot say what they are — the user has to memorise
# "double diamond = Home".
#
# This set: one 24×24 frame, one stroke weight (1.75), rounded caps, painted
# with `currentColor` so CSS changes the colour rather than an image editor.
# No external file, no font, no CDN — true to the app's no-dependency rule.
#
# THE ICON NAME MUST DESCRIBE THE TAB'S JOB, not the shape:
#     home     a roof         — where you see the whole picture
#     search   a magnifier    — going out to find work
#     cv       a sheet        — the pages that will be sent
#     track    clip + tick    — how far the applications have got
#     profile  a person       — your own profile
#     setting  a cog          — settings for the whole app
#     adjust   three sliders  — adjusts ONLY the open screen (the ⚟ button)
#     to       four corners   — enlarge one widget
#     gap      two « arrows   — collapse the sidebar (CSS rotates it 180°)
#
# The cog is built with trigonometry (6 teeth) rather than 24 hand-typed
# coordinates: typed by hand, one wrong number warps a tooth, and at 16px the
# eye cannot catch it — it only looks "slightly dirty" for no visible reason.
ICON = {
    "home": "<path d='M3.2 10.4 12 3.2l8.8 7.2'/>"
            "<path d='M5.6 9.1V20.3h12.8V9.1'/>"
            "<path d='M9.7 20.3v-5.1h4.6v5.1'/>",
    "search": "<circle cx='10.9' cy='10.9' r='6.7'/>"
              "<path d='M20.4 20.4 15.7 15.7'/>",
    "cv": "<path d='M13.6 3.2H7.4A2.2 2.2 0 0 0 5.2 5.4v13.2a2.2 2.2 0 0 0 2.2"
          " 2.2h9.2a2.2 2.2 0 0 0 2.2-2.2V8.4z'/>"
          "<path d='M13.6 3.2v5.2h5.2'/><path d='M8.8 13.1h6.4M8.8 16.6h6.4'/>",
    "track": "<path d='M9.2 4.6H7.4a2.2 2.2 0 0 0-2.2 2.2v11.8a2.2 2.2 0 0 0 2.2"
             " 2.2h9.2a2.2 2.2 0 0 0 2.2-2.2V6.8a2.2 2.2 0 0 0-2.2-2.2h-1.8'/>"
             "<rect x='9.2' y='2.8' width='5.6' height='3.6' rx='1.2'/>"
             "<path d='M9.3 13.6l2.1 2.1 4.3-4.3'/>",
    "profile": "<circle cx='12' cy='8.1' r='3.9'/>"
               "<path d='M4.9 20.6a7.1 7.1 0 0 1 14.2 0'/>",
    "setting": "<path d='M18.03 9.32 20.84 9.83 20.84 14.17 18.03 14.68 17.34"
               " 15.88 18.3 18.57 14.54 20.74 12.69 18.56 11.31 18.56 9.46"
               " 20.74 5.7 18.57 6.66 15.88 5.97 14.68 3.16 14.17 3.16 9.83"
               " 5.97 9.32 6.66 8.12 5.7 5.43 9.46 3.26 11.31 5.44 12.69 5.44"
               " 14.54 3.26 18.3 5.43 17.34 8.12Z'/>"
               "<circle cx='12' cy='12' r='3.3'/>",
    "adjust": "<path d='M4 6.4h3.1M11.1 6.4H20'/><circle cx='9.1' cy='6.4' r='2'/>"
              "<path d='M4 12h8.9M16.9 12H20'/><circle cx='14.9' cy='12' r='2'/>"
              "<path d='M4 17.6h3.1M11.1 17.6H20'/>"
              "<circle cx='9.1' cy='17.6' r='2'/>",
    "to": "<path d='M8.8 3.6H3.6v5.2M15.2 3.6h5.2v5.2M20.4 15.2v5.2h-5.2"
          "M3.6 15.2v5.2h5.2'/>",
    "gap": "<path d='M13.4 6.2 7.6 12l5.8 5.8M19.2 6.2 13.4 12l5.8 5.8'/>",
}


def ico(ten: str) -> str:
    """One icon. `aria-hidden` because the text beside it (or title=) has
    already said it — a screen reader saying it twice is worse than not
    saying it."""
    return (f"<svg class=ico viewBox='0 0 24 24' aria-hidden=true>"
            f"{ICON[ten]}</svg>")


NAV = [
    ("/",          "Home",     "home"),
    ("/search",    "Search",   "search"),    # step 1
    ("/cv",        "CV",       "cv"),        # everything that will be sent
    ("/track",     "Track",    "track"),     # steps 5-6: apply and follow up
    ("/profile",   "Profile",  "profile"),
]


# The app logo — a key. Drawn from primitives rather than one long path:
# the three rings are three <circle>s with a stroke and no fill, so the hole
# in the middle is a real hole, and changing the stroke weight later means
# changing ONE number. The colour comes from `currentColor`, so CSS recolours
# it without touching an image file.
LOGO = (
    "<svg class=logo viewBox='0 0 112 38' aria-hidden=true>"
    "<g fill=none stroke=currentColor stroke-width=4.4>"
    "<circle cx=12 cy=17.4 r=7.2 /><circle cx=25 cy=9.4 r=7.2 />"
    "<circle cx=24.4 cy=26 r=7.2 /></g>"
    "<g fill=currentColor>"
    "<rect x=26 y=14.6 width=84 height=5.6 rx=2.8 />"      # the shaft
    "<rect x=67.6 y=8 width=4.8 height=17 rx=2.4 />"       # the middle notch
    "<rect x=78 y=20.2 width=24 height=4.8 />"             # the bit spine
    "<rect x=78 y=25 width=6 height=11.6 />"
    "<rect x=87.6 y=25 width=5.4 height=11.6 />"
    "<rect x=96 y=25 width=6 height=11.6 />"
    "</g></svg>")


def deck(stage: str, name: str, state: str, metrics: list,
         adjust: str = "", run: str = "Run", run_note: str = "",
         sua: tuple = (), xoa: tuple = (), them: tuple = (),
         run_path: str = "/api/stage/start",
         stop_path: str = "/api/stage/stop") -> str:
    """ONE stage's bar: name + state · metrics · run/stop · adjust.

    ONE block for every feature. The top bar used to belong to the whole app
    — the same content on every tab — while what it controlled ("Run now",
    "Turn auto-scan on") belonged only to Search. A bar claiming to be the
    app's while doing one stage's job.

    `metrics` is [(number, label, role)]. It only takes numbers that answer
    "what should I do now" — the old Home died full of pretty numbers nobody
    acted on.

    THE ROLE decides THE COLOUR, and colour here carries meaning rather than
    decoration:

        act    work to be done    -> green (the app's action colour)
        stock  what is held       -> blue (background, read to know)
        new    just arrived, look -> orange (news)
        view   context / filters  -> grey (read to know, not work)

    And one rule over all of them: ZERO NEVER LIGHTS UP. "0 new" glowing
    orange is a lie — the bar may only light when something has happened.

    The ⚟ button reuses the Settings overlay (`data-settings` takes a URL), so
    it adds no new listener — every new path is another thing that can die.

    `run` is THE TEXT ON THE BUTTON, and it changes with the situation: Start
    / Resume / Update / Scanning…. A button reading "Run" in every situation
    says nothing — someone opening the app for the first time does not know
    what it will run, and someone who has just pressed Stop thinks pressing it
    loses the work already done. The stage computes the text (see
    live.search_stage), this only draws it. `data-run` keeps the original text
    so live.js can put it back after showing "Scanning…".
    """
    def _rong(v) -> bool:
        """Zero (or empty) -> colour off — see the rule in the docstring."""
        try:
            return int(str(v).replace(",", "").strip() or 0) == 0
        except ValueError:
            return False

    nums = "".join(
        f"<span class='metric {esc(kind)}{' zero' if _rong(v) else ''}'>"
        f"<b>{esc(str(v))}</b>{esc(label)}</span>"
        for v, label, kind in metrics)
    knob = (f"<button class='mbtn knob' data-settings='{esc(adjust)}'"
            f" title='Adjust {esc(name)}'>{ico('adjust')}</button>"
            if adjust else "")
    # `sua` = (path, label, description) — a button leading to ANOTHER SCREEN
    # of the same stage. An <a> tag, not an overlay button: an overlay suits a
    # few switches you flip and close, not a place to sit and write. A screen
    # of its own has its own address, can be saved, can be gone Back from, and
    # is as wide as the window.
    # THE DESTROY BUTTON — a TWO-BEAT latch (see live.js): the first beat
    # changes the text on the button, only the second sends. The server holds
    # one more latch, demanding arg="xoa" — never trust the browser side alone.
    #
    # `xoa` = (POST path, label, label once armed, description).
    pha = (f"<button class='mbtn kill' data-post='{esc(xoa[0])}'"
           f" data-arg='xoa' data-arm='{esc(xoa[2])}'"
           f" title='{esc(xoa[3] if len(xoa) > 3 else xoa[1])}'>"
           f"{esc(xoa[1])}</button>" if xoa else "")
    # `them` = (POST path, label, description) — one more BACKGROUND JOB of
    # this stage, next to Run. Unlike `xoa` it destroys nothing, so it needs
    # no latch.
    nut_them = (f"<button class='mbtn' data-post='{esc(them[0])}'"
                f" title='{esc(them[2] if len(them) > 2 else them[1])}'>"
                f"{esc(them[1])}</button>" if them else "")
    khac = (f"<a class='mbtn qua' href='{esc(sua[0])}'"
            f" title='{esc(sua[2] if len(sua) > 2 else sua[1])}'>"
            f"{esc(sua[1])}</a>" if sua else "")
    # ONE HORIZONTAL PILL: allowed to be WIDE, never TALL. Everything inside
    # one pill — stage name, metrics, buttons. Push the metrics outside and
    # the bar breaks into three disconnected tiers, which looks a mess.
    #
    # The status line ("auto: OFF · last scan 09:42") is NOT here: it is
    # app-wide news, and its place is the status bar at the bottom.
    return (
        f"<div class=deckwrap><div class=deckpill>"
        f"<span class=deckpillname><span class=rdot></span>"
        f"<b class=deckname>{esc(name)}</b></span>"
        f"<span class=metrics>{nums}</span>"
        f"<span class=deckbtns>"
        f"<button class='mbtn go' data-post='{esc(run_path)}'"
        f" data-arg='{esc(stage)}' data-run='{esc(run)}'"
        f" title='{esc(run_note)}'>{esc(run)}</button>"
        f"<button class=mbtn data-post='{esc(stop_path)}'"
        f" data-arg='{esc(stage)}'>Stop</button>"
        f"{nut_them}{khac}{pha}{knob}</span>"
        f"</div></div>")


# The label for the Back button, inferred from THE PATH TAKEN. Not hardcoded
# per page: a page with three ways in, hardcoded, lies about two of them.
# Ordered SPECIFIC to GENERAL: "/jobs/7/cv" is A CV, not a posting page —
# match "/jobs/" first and the button reads "← this posting" while it goes
# back to a CV.
_TEN_DUONG = (("/cv/soan", "Block editor"), ("/cv", "CVs"),
              ("/search", "Search"), ("/track/queue", "Queue"),
              ("/track", "Track"),
              ("/profile", "Profile"), ("/jobs/", "this posting"))


def duong_ve(tu: str, mac_dinh: str = "/cv") -> tuple:
    """(path, label) for the Back button. `tu` = the page just left.

    BACK MUST RETURN TO THE PAGE JUST LEFT, not to a hardcoded destination.
    The CV view is reachable from the CV tab and from a posting's detail page;
    hardcode one destination and one of those two becomes a dead end — you
    press Back and land somewhere you have never stood.

    The path travelled lives on the URL (`?tu=`), not in browser history: open
    an address directly, or open a new tab, and history is empty while the
    button still has to be right.

    IN-HOUSE PATHS ONLY. `tu` goes from the URL straight into an href
    attribute, so a value like "//bad-actor" or "https://…" turns Back into an
    exit. Anything not starting with "/", or starting with "//", is thrown
    away.
    """
    duong = (tu or "").strip()
    if not duong.startswith("/") or duong.startswith("//"):
        duong = mac_dinh
    goc = duong.split("?")[0]
    if goc.startswith("/jobs/") and goc.endswith("/cv"):
        return duong, "CVs"
    ten = next((t for d, t in _TEN_DUONG if goc.startswith(d)), "back")
    return duong, ten


def page(title: str, body: str, active: str = "",
         flow: bool = True, bar: str = "", setup: str = "",
         reload: str = "") -> str:
    """flow=True  the page scrolls as before — for pages NOT yet on widgets
    flow=False the page does not scroll, the content is a grid of widgets
    that scroll inside themselves

    `reload` — WHICH STAGE FINISHING SHOULD REDRAW THIS PAGE. "*" is any
    stage, "track" is that stage only, several stages are separated by spaces,
    and empty means NEVER redraw by itself.

    Why it is a parameter of its own rather than reusing the journal widget's
    `stream`: two different questions were folded into one, and both got
    answered wrongly.

        Home declared `stream=""` (meaning the journal takes EVERY stream).
        live.js reads the empty string as false, so the redraw branch NEVER
        ran — a page calling itself "live 24/7" whose numbers only changed
        when the user pressed F5.

        Track declared `stream="search"` to watch the scan journal. The
        result: the page JUMPED the moment a scan finished, slamming shut
        every row left open — a user reading an email lost their place with
        no idea why.
    """
    links = ""
    for href, label, mark in NAV:
        on = " on" if href == active else ""
        # title= so the collapsed sidebar still says which icon is which
        links += (f"<a class='navlink{on}' href='{esc(href)}'"
                  f" title='{esc(label)}'>"
                  f"<i>{ico(mark)}</i><span>{esc(label)}</span></a>")

    # Settings: a button, NOT a link. /settings returns an HTML fragment for
    # the overlay. `data-appset` rather than sharing `data-settings` with a
    # stage's ⚟ button: ⚟ adjusts what THIS SCREEN works on, this is settings
    # for THE WHOLE APP. One button cannot belong to both — hence a different
    # attribute and a different frame (⚟ opens the right-hand panel, Settings
    # opens a box in the middle).
    settings = ("<div class=navend>"
                "<button class=navlink data-appset title='Settings'>"
                f"<i>{ico('setting')}</i><span>Settings</span></button></div>")

    # THE APP'S BOTTOM STATUS BAR — shared news, belonging to no tab. It takes
    # no data from the view: live.js fills it from the SSE stream that is
    # already open, so nothing has to be threaded through a dozen render
    # functions and it is never stale.
    foot = ("<footer class=statusbar>"
            "<span class=sdot></span><b data-state>connecting…</b>"
            "<span class=smsg data-lastmsg></span></footer>")
    # The top bar IS the open stage's bar, not the app's. A page with no stage
    # has NO bar: the shared status already sits on the bottom bar, and
    # drawing the same line again at the top just says it twice.
    top = ((f"<header class=topbar>{bar}</header>" if bar else "")
           # The overlay for the Settings menu. Empty until the cog is
           # pressed — the content is loaded then, so every other page is
           # spared carrying settings data it does not use.
           + "<div class=sheet hidden data-sheet><div class=sheetbox></div></div>")

    # Read the collapsed/expanded choice INSIDE <head>, before drawing. Put it
    # at the foot of the page and every tab change flashes the sidebar open
    # then shut again. This is a display preference belonging to this machine
    # alone, not shared data, so localStorage: no need to ask the server, and
    # no parameter threaded through a dozen render functions.
    early = ("<script>try{if(localStorage.jobbotNav==='1')"
             "document.documentElement.classList.add('navmin')}catch(e){}</script>")

    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)} · jobbot</title>"
        "<link rel=stylesheet href='/static/app.css'>"
        # THE ACCENT COLOUR goes through a stylesheet OF ITS OWN, loaded after
        # app.css so it overrides.
        #
        # The preference is not read inside page(): layout is a DRAWING-ONLY
        # layer, and letting it touch the DB opens the door for everything
        # else to touch it too. A separate sheet also means the browser
        # cannot cache the wrong one — change the colour and you see it.
        "<link rel=stylesheet href='/static/mau.css'>"
        f"{early}</head><body"
        # THE SETUP FLAG: live.js seeing this attribute opens the
        # profile-building overlay as soon as the page is drawn. Only Home
        # sets it — set on every page it becomes a pop-up chasing the user.
        + (f" data-setup='{esc(setup)}'" if setup else "")
        + (f" data-reload='{esc(reload)}'" if reload else "") + ">"
        # THE TITLE BAR — the strip along the top of the window. The app
        # window has no frame, so macOS's traffic lights sit on top of the
        # page: that spot must ALWAYS be empty, and scrolling content up into
        # it loses text. With a real bar every page is spared automatically —
        # rather than each page remembering how much to leave, where
        # forgetting one breaks that page (exactly what happened to Home:
        # 16px left while 38px was needed).
        f"<header class=titlebar><b>{esc(title)}</b></header>"
        f"<aside class=side>"
        f"<div class=brandrow><div class=brand>{LOGO}jobbot</div>"
        f"<button class=navtoggle data-nav title='Collapse sidebar'>"
        f"{ico('gap')}</button></div>"
        f"<nav>{links}</nav>{settings}</aside>"
        f"<main class='{'flow' if flow else ''}'>{top}"
        f"<div class=inner>{body}</div></main>"
        f"{foot}"
        "<script src='/static/live.js'></script></body></html>"
    )


# ---------------------------------------------------------------- small parts

def h1(text: str, sub: str = "") -> str:
    return f"<h1>{esc(text)}</h1>" + (f"<p class=lead>{esc(sub)}</p>" if sub else "")


def badge(text: str, kind: str = "") -> str:
    return f"<span class='badge {kind}'>{esc(text)}</span>"


def score_bar(score: int) -> str:
    """Colour by threshold, not a gradient — quicker to read."""
    kind = "hi" if score >= 75 else ("mid" if score >= 55 else "lo")
    return (f"<span class='score {kind}'><span class=track>"
            f"<span class=fill style='width:{score}%'></span></span><b>{score}</b></span>")


def stat(value: str, label: str, note: str = "", key: bool = False) -> str:
    return (f"<div class='stat{' key' if key else ''}'><b>{esc(value)}</b>"
            f"<span>{esc(label)}</span>"
            + (f"<i>{esc(note)}</i>" if note else "") + "</div>")


def card(inner: str, cls: str = "") -> str:
    return f"<div class='card {cls}'>{inner}</div>"


def empty(text: str) -> str:
    return f"<div class=empty-box>{esc(text)}</div>"


def section(title: str, inner: str, action: str = "") -> str:
    return f"<h2>{esc(title)}{action}</h2>{inner}"


# ---------------------------------------------------------------- widgets

def widget(title: str, body: str, tools: str = "", span: int = 1,
           rows: int = 1, expand: bool = True, cls: str = "",
           at: tuple[int, int] | None = None) -> str:
    """One widget in the grid. Scrolls inside itself, never lengthens the page.

    span = how many columns it takes. expand=True gives it a button to open
    full-screen for a closer look or an edit; press again (or Esc) to shrink.
    """
    grow = (f"<button class=wexp data-expand title='Expand (Esc to shrink)'>"
            f"{ico('to')}</button>"
            if expand else "")
    # at=(column, row) puts the widget in AN EXACT place. Without it the
    # browser packs them itself — but a widget that must stay in one column
    # (the journal in the last one) would drift into the first empty slot it
    # finds.
    place = (f"grid-column:{at[0]} / span {span};grid-row:{at[1]} / span {rows}"
             if at else f"grid-column:span {span};grid-row:span {rows}")
    return (f"<section class='wid {cls}' data-widget style='{place}'>"
            f"<header class=whead><h3>{esc(title)}</h3>"
            f"<div class=wtools>{tools}{grow}</div></header>"
            f"<div class=wbody>{body}</div></section>")


def grid(*widgets: str, cols: int = 3,
         columns: str = "", rows: str = "") -> str:
    """A grid of widgets. Equal columns by default; pass columns/rows to split
    it your own way.

    Equal is the RIGHT default for most tabs. But some tabs hold widgets that
    are not peers — a job list deserves twice the width of a filter grid, and
    a journal strip only needs the height of three lines, not a full row.
    """
    style = f"grid-template-columns:{columns or f'repeat({cols},1fr)'}"
    if rows:
        style += f";grid-template-rows:{rows}"
    return f"<div class=wgrid style='{style}'>" + "".join(widgets) + "</div>"


def journal_box(stream: str = "") -> str:
    """The journal frame. live.js fills it — nothing is drawn here up front."""
    return f"<div class=journal data-journal='{esc(stream)}'></div>"


def progress_box(stream: str = "") -> str:
    return (f"<div class=progress data-progress='{esc(stream)}'>"
            "<div class=pidle>connecting…</div></div>")
