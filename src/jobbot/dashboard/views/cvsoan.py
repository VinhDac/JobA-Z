"""THE BLOCK EDITOR — the CV tab's own screen, the place to sit and write.

WHY THIS SCREEN EXISTS. Block editing used to live in the right-hand overlay:
380px wide, laid over the page, and gone the moment it closed. An overlay
suits switches you flip and close — it does not suit sitting down to write for
fifteen minutes. And it was mute: you typed, pressed Save, and only learned
the sentence had been dropped by a rule if you went and rebuilt the whole run
of CVs yourself and read the "sentences that did not make it" section.

So this screen differs in exactly two ways, and both are why it exists:

    WIDE   the whole window, blocks on the left, sentences on the right, room
           to read
    SPEAKS each sentence carries what the rules say about it + how many
           postings are asking for what it mentions

AND IT IS THE ONLY PLACE TO WRITE. "Write a new sentence about X" used to have
an overlay of its own (/cv/viet): read the requirement on one screen, type on
another, two write paths into the same `cv_text` having to watch each other.
But writing a new sentence IS editing a block — the same write, the same
chair. So `?ky=` only opens a BRIEF above the editing box; it does not spawn a
second screen.

The founding rule stands: the words here are words THE USER typed. The machine
scores, the machine counts, the machine writes no sentence — see cv/build.py.

ONE SOURCE OF TRUTH: written straight into `cv_text`, with no separate block
table.

DRAWING ONLY.
"""

from __future__ import annotations

from html import escape as esc
from urllib.parse import quote

from . import runtime

KIND_TAG = {"experience": "experience", "project": "project"}

# A rule's verdict -> (label, CSS class). Three levels, three different
# actions: goes on the CV, needs the writer's eye, or the rules forbid it — in
# which case it will never be printed, so either reword it or keep it
# somewhere else.
PHAN = {"keep": ("goes on", "ok"),
        "review": ("look again", "warn"),
        "drop": ("rules forbid", "bad")}


def _khoi_list(blocks: list[dict], dang: str, mang: str = "") -> str:
    """The block store, ordered by HOW MANY POSTINGS IT REACHES. Click to open
    it on the right.

    `mang` = the URL tail that has to travel along (the target being aimed at
    and the draft base). The left column answers "write WHERE", so clicking a
    block must not throw away the answer to "write WHAT" — the user would have
    to choose it all over again.
    """
    rows = ""
    for b in blocks:
        skills = "".join(f"<span class=sk>{esc(s)}</span>" for s in b["skills"][:4])
        cls = "blk"
        if b["reach"] == 0:
            cls += " dead"
        if b["title"] == dang:
            cls += " on"
        # quote(), NOT esc(): this is a URL PARAMETER. The title "R & D"
        # HTML-escapes to "R &amp; D" — the & still cuts the parameter and the
        # page opens an empty block.
        rows += (
            f"<a class='{cls}'"
            f" href='/cv/soan?khoi={quote(b['title'], safe='')}{mang}'>"
            f"<div class=blkmain>"
            f"<div class=blkhead><b>{esc(b['title'][:44])}</b>"
            f"<span class=blkkind>{esc(KIND_TAG.get(b['kind'], b['kind']))}</span>"
            f"</div>"
            f"<div class=blktags>{skills or '<span class=muted>no skill named</span>'}</div>"
            f"</div>"
            f"<div class=blkreach><b>{b['reach']}</b><span>postings</span>"
            f"<i>{len(b['lines'])} sentences</i></div></a>")

    if not rows:
        rows = ("<div class=empty-box>The profile has no experience block yet. "
                "Press <b>+ New block</b> to write the first one.</div>")
    return (
        f"<div class=gapnote>Ordered by <b>how many postings the block "
        f"reaches</b>. A block at <b>0 postings</b> is taking up space without "
        f"proving anything.</div>"
        f"<div class=blklist>{rows}</div>"
        f"<div class=blkfoot><a class='mbtn apply' href='/cv/soan?moi=1'>"
        f"+ New block</a></div>")


def _hut(rows: list, khoi: str = "", dang: str = "") -> str:
    """What the market is short of — pick a TARGET for the sentence to come.

    Editing blocks without knowing what the market asks is only proofreading.
    Only the WRITABLE rows are printed: a row naming a product outright is
    something to go and learn, not work for this screen.

    Pressing one STAYS on this screen, keeps the open block, and only opens
    the brief.
    """
    if not rows:
        return ""
    giu = f"khoi={quote(khoi, safe='')}&" if khoi else ""
    muc = ""
    for b in rows:
        on = " on" if b["ky_nang"] == dang else ""
        muc += (f"<a class='hmini{on}'"
                f" href='/cv/soan?{giu}ky={quote(b['ky_nang'], safe='')}'>"
                f"<span class=hmname>{esc(b['ky_nang'])}</span>"
                f"<span class=hmplus>+{b['them']}<span>postings</span></span></a>")
    return (f"<div class=sntbrief>"
            f"<div class=slab>Write a sentence about these and this many "
            f"postings clear<span>press one to read, word for word, the real "
            f"requirement lines of the postings asking for it</span></div>"
            f"<div class=hminis>{muc}</div></div>")


def _buoc(so: int, ten: str, xong: bool, dang: bool, ruot: str) -> str:
    """ONE STEP of the writing screen. It has a number, a name and a state.

    WHY NUMBERED. The previous version poured the brief and the editing box
    onto one flat page, and the user's first reaction was "I don't know what
    to press, how to write, what I'm confirming". The page had everything
    needed and never said the order — and writing a CV sentence is a
    three-beat job, not a one-beat one.
    """
    lop = "buoc" + (" xong" if xong else "") + (" dang" if dang else "")
    dau = "✓" if xong else str(so)
    return (f"<section class='{lop}'>"
            f"<div class=buochead><span class=buocso>{dau}</span>"
            f"<b>{esc(ten)}</b></div>"
            f"<div class=buocruot>{ruot}</div></section>")


def _viet(d: dict, khoi: str, nen: str, loi: str, blocks: list,
          soan: str = "", gy: str = "", tho: bool = False) -> str:
    """WRITING ONE SENTENCE — three numbered steps, so you can see where you are.

    Quite unlike the BLOCK EDITOR below, and it has to be: someone comes here
    to write ONE new sentence, not to reread 16 old ones. Pouring out the whole
    block buries the box they need two screens down.

        1  pick one of their requirement lines as a starting point
        2  pick which block to write into
        3  rewrite it as work YOU did, then Save

    A finished step folds to a one-line "chosen" row, still changeable. The
    current step is open and lit. A step not yet reached still shows — locking
    it only confuses the user without teaching them anything.

    The machine still writes NO sentence. The words in step 3 are THE
    EMPLOYER's, verbatim, and `gap.qua_giong` blocks Save if the user has not
    rewritten them.
    """
    ky = d["ky"]
    dich = quote(ky, safe="")
    giu_nen = f"&nen={quote(nen, safe='')}" if nen else ""
    giu_khoi = f"&khoi={quote(khoi, safe='')}" if khoi else ""
    o = soan if soan else nen

    def _list(rows) -> str:
        return "".join(
            f"<li><span class=wq>{esc(m['chu'])}</span>"
            f"<span class=wco>{esc(m['cong_ty'])}</span></li>" for m in rows)

    # ---- STEP 1 · pick a line ------------------------------------------
    if nen:
        r1 = (f"<div class=dachon><span class=wq>{esc(nen)}</span>"
              f"<a class='mbtn tiny' href='/cv/soan?ky={dich}{giu_khoi}'>"
              f"Change line</a></div>")
    elif d["nen"]:
        r1 = "<div class=nenlist>"
        for m in d["nen"]:
            # The line takes THE FULL WIDTH; the company name and the
            # invitation drop to the line below. Squeeze the company onto the
            # same row and its column is crushed to "Bo…" — and the company
            # name is precisely what shows this is a REAL requirement.
            r1 += (f"<a class=nenone href='/cv/soan?ky={dich}{giu_khoi}"
                   f"&nen={quote(m['chu'], safe='')}'>"
                   f"<span class=wq>{esc(m['chu'])}</span>"
                   f"<span class=nenfoot>"
                   f"<span class=nengo>Use this line →</span>"
                   f"<span class=wco>{esc(m['cong_ty'])}</span></span></a>")
        r1 += "</div>"
    else:
        r1 = ("<div class=empty-box>No posting asks for this in a line that "
              "DESCRIBES WORK — the lines asking for it only describe a "
              "quality. You can still write it: go to step 2 and type your own "
              "sentence in step 3.</div>")

    phu = ""
    con = [m for m in d["chung"] if m not in d["nen"]][:5]
    if con:
        phu += (f"<details class=briefmore><summary>{len(con)} more lines ask "
                f"for {esc(ky)} — they describe a quality rather than work, "
                f"read them for context</summary>"
                f"<ul class=wlist>{_list(con)}</ul></details>")
    if d["rieng"]:
        phu += (f"<details class=briefmore><summary>{len(d['rieng'])} lines "
                f"name a product outright — no sentence stands in for those"
                f"</summary><ul class=wlist>{_list(d['rieng'])}</ul></details>")

    # ---- STEP 2 · pick a block -----------------------------------------
    r2 = "<div class=khoichon>"
    for b in blocks:
        on = " on" if b["title"] == khoi else ""
        r2 += (f"<a class='khoione{on}' href='/cv/soan?ky={dich}{giu_nen}"
               f"&khoi={quote(b['title'], safe='')}'>"
               f"<b>{esc(b['title'][:34])}</b>"
               f"<span>{len(b['lines'])} sentences · {b['reach']} postings</span></a>")
    r2 += (f"<a class=khoione href='/cv/soan?moi=1&ky={dich}{giu_nen}'>"
           f"<b>+ New block</b><span>name it on the block editor</span></a></div>")

    # ---- STEP 3 · write --------------------------------------------------
    if not khoi:
        r3 = ("<div class=empty-box>Pick a block in step 2 first — the sentence "
              "has to live inside a block.</div>")
    else:
        # THREE STATES of the box, each needing different words.
        dung_gy = bool(gy) and not tho and o == gy
        if loi:
            canh = f"<div class='sntwarn bad'>{esc(loi)}</div>"
        elif dung_gy:
            canh = ("<div class='sntwarn ok'>This is a <b>suggestion</b>: the "
                    "machine cut the excess out of their line and put it into "
                    "the past tense — the shape of a CV sentence. It <b>does "
                    "not know what you did</b>, so the <b>___</b> is for you "
                    "to fill in the real evidence: how many, over how much "
                    "data, how much it changed.</div>")
        elif nen:
            canh = ("<div class=sntwarn>The box below is still <b>the "
                    "employer's words</b>, not your sentence yet. Rewrite it "
                    "as work YOU did, with a real number.</div>")
        else:
            canh = ""

        # SWITCHING between the suggestion and the verbatim line. A LINK, not
        # JavaScript: the state lives on the URL, so Back works and the
        # address can be saved.
        lat = ""
        if gy and nen:
            if dung_gy:
                lat = (f"<a class='mbtn tiny' href='/cv/soan?ky={dich}"
                       f"{giu_khoi}{giu_nen}&tho=1'>Use their line "
                       f"verbatim</a>")
            else:
                lat = (f"<a class='mbtn tiny apply' href='/cv/soan?ky={dich}"
                       f"{giu_khoi}{giu_nen}'>↺ Suggest a CV sentence</a>")
        elif nen:
            lat = ("<span class=muted>this line cannot be cut down to the "
                   "shape of a CV sentence — use it as the brief and write "
                   "your own</span>")

        r3 = (
            f"<form class=vietform method=post action='/cv/block'>"
            f"<input type=hidden name=them value=1>"
            f"<input type=hidden name=title value='{esc(khoi)}'>"
            f"<input type=hidden name=ky value='{esc(ky)}'>"
            + (f"<input type=hidden name=nen value='{esc(nen)}'>" if nen else "")
            + canh
            + f"<textarea class=cvdraft name=line rows=4 id=viet"
              f" placeholder='One English sentence about work YOU did. Put in "
              f"a real number if you have one — that is what the profile is "
              f"shortest of.'>{esc(o)}"
              f"</textarea>"
            + (f"<div class=latrow>{lat}</div>" if lat else "")
            + f"<div class=vietfoot>"
              f"<button class='mbtn apply big' type=submit>Add this sentence to "
              f"«{esc(khoi[:26])}»</button>"
              f"<span class=applynote>written straight into the original CV · "
              f"the sentences already in the block are untouched</span></div>"
            + "</form>")

    hd = (f"<div class=viethead><span>Write a sentence about · "
          f"<b>{esc(ky)}</b></span>"
          f"<a class='mbtn tiny' href='/cv/soan{giu_khoi.replace('&', '?', 1)}'>"
          f"× drop the target</a></div>")
    return (f"<div class=vietbox>{hd}"
            + _buoc(1, "Pick one of their lines as a starting point",
                    bool(nen), not nen, r1 + phu)
            + _buoc(2, "Which block to write into", bool(khoi),
                    bool(nen) and not khoi, r2)
            + _buoc(3, "Rewrite it as work YOU did, then Save",
                    False, bool(khoi), r3)
            + "<div class=note>The machine writes NO sentence. It knows what "
              "the market asks, but not what you did — and a sentence on a CV "
              "is one you have to hold up in the interview room. Leave their "
              "words as they are and it will not let you save.</div></div>")


def _cau(c: dict) -> str:
    """ONE sentence: the editing box plus the verdict strip under it.

    The strip is what the old overlay had not got. It answers two questions,
    no more: do the rules let this sentence be printed, and is the market
    asking about what it mentions. Both are measured; both change the moment
    you press Save.
    """
    from ...cv.report import vi

    nhan, lop = PHAN.get(c["phan"], PHAN["keep"])
    sk = "".join(f"<span class=sk>{esc(t)}</span>" for t in c["tags"][:5])
    if not sk:
        sk = "<span class=muted>names no skill</span>"
    why = (f"<span class=svwhy>{esc(vi(c['vi_sao']))}</span>"
           if c["vi_sao"] else "")
    return (
        f"<div class='snt {lop}'>"
        f"<textarea class=cvdraft name=line rows=2>{esc(c['chu'])}</textarea>"
        f"<div class=sntfoot>"
        f"<span class='sv {lop}'>{nhan}</span>{why}"
        f"<span class=sntsk>{sk}</span>"
        f"<span class=sntreach><b>{c['reach']}</b> postings</span>"
        f"</div></div>")


def _form(chon: dict | None, cau: list[dict], ky: str = "",
          nen: str = "", loi: str = "", ten: str = "") -> str:
    """The editor for one block. Written straight into `cv_text`.

    `nen` drops into the first empty box. `loi` is the last Save's refusal —
    shown RIGHT ABOVE the box, next to the words the user still has, rather
    than as an error line somewhere else with everything just typed lost.
    """
    # `ten` = a block name the user has typed but NOT saved. Without keeping
    # it, a refused Save loses both the name and the sentences, and the user
    # types it all again.
    b = chon or {"kind": "project", "title": ten, "meta": "", "lines": [],
                 "skills": [], "reach": 0}
    kinds = "".join(
        f"<option value='{k}'{' selected' if k == b['kind'] else ''}>{esc(v)}"
        f"</option>" for k, v in KIND_TAG.items())
    # An existing sentence comes with its verdict strip; the empty boxes at
    # the end are for writing more, and having nothing to judge they have no
    # strip. A NEW block gets more boxes: editing a block, two boxes is enough
    # room to add on, while a new block starts from a blank page.
    # THE FIRST EMPTY BOX carries the ANCHOR `#viet`, NOT autofocus. autofocus
    # scrolls straight to the typing box — convenient in theory, but it
    # scrolls away the brief just above, exactly the thing put there to be
    # read BEFORE writing. With an anchor the user decides: read, then press
    # once to jump to the box.
    goi = (f"write a sentence about {ky}…" if ky else "write another sentence…")
    boxes = "".join(_cau(c) for c in cau)
    for i in range(2 if chon else 4):
        neo = " id=viet" if i == 0 else ""
        # THE FIRST BOX takes the base. The base is the employer's words, so
        # it has to be labelled right there — a user coming back ten minutes
        # later must still recognise this is not their own sentence yet.
        if i == 0 and nen:
            xau = ("<div class='sntwarn bad'>" + esc(loi) + "</div>") if loi else (
                "<div class=sntwarn>These are <b>the employer's words</b>, not "
                "your sentence yet. Rewrite it as work YOU did — put in a real "
                "number if you have one, that is what the profile is shortest "
                "of.</div>")
            boxes += (f"<div class='snt nen{' bad' if loi else ''}'{neo}>{xau}"
                      f"<textarea class=cvdraft name=line rows=3"
                      f" placeholder='{esc(goi)}'>{esc(nen)}</textarea></div>")
            continue
        boxes += (f"<div class=snt{neo}><textarea class=cvdraft name=line rows=2"
                  f" placeholder='{esc(goi)}'></textarea></div>")

    bo = sum(1 for c in cau if c["phan"] == "drop")
    xem = sum(1 for c in cau if c["phan"] == "review")
    tom = ""
    if chon:
        phan = [f"<b>{len(cau)}</b> sentences"]
        if bo:
            phan.append(f"<b class=bad>{bo}</b> the rules will not print")
        if xem:
            phan.append(f"<b class=warn>{xem}</b> waiting on your decision")
        tom = (f"<div class=gapnote>This block reaches <b>{b['reach']}</b> "
               f"postings · " + " · ".join(phan) + "</div>")

    return (
        "<form class=soanform method=post action='/cv/block'>"
        f"<input type=hidden name=was value='{esc(b['title'])}'>"
        + (f"<input type=hidden name=ky value='{esc(ky)}'>" if ky else "")
        # The base travels with the form so Save can compare what was typed
        # against their original words.
        + (f"<input type=hidden name=nen value='{esc(nen)}'>" if nen else "")
        +
        f"{tom}"
        "<div class=soanhead>"
        f"<label class=slab>Kind<select name=kind>{kinds}</select></label>"
        "<label class=slab>Block name"
        f"<input class=dfthead type=text name=title value='{esc(b['title'])}'"
        " placeholder='a company name, or a project name' autocomplete=off>"
        "</label>"
        "<label class=slab>Dates / organisation<span>leave empty for a project</span>"
        f"<input class=dfthead type=text name=meta value='{esc(b['meta'])}'"
        " placeholder='2023 — present' autocomplete=off></label>"
        "</div>"
        "<div class=slab>Sentences<span>one per box · empty boxes are skipped · "
        "the strip under each box is what the rules say, recomputed after "
        "Save</span></div>"
        f"{boxes}"
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Save into the original CV</button>"
        + ("<button class='mbtn kill' type=submit name=kill value=1>Delete block"
           "</button>" if chon else "")
        + "<span class=applynote>written straight into the profile · press "
          "Update on the bar above to rebuild every CV from it</span></div>"
        + (f"<div class=forced>No posting reaches this block. You do not have "
           f"to delete it — but it is taking up a place on the page without "
           f"proving anything.</div>" if chon and b["reach"] == 0 else "")
        + "</form>")


def render(*, khoi: list[dict], chon: dict | None, cau: list[dict],
           hut: list, brief: dict | None = None, ky: str = "",
           nen: str = "", soan: str = "", gy: str = "", tho: bool = False,
           loi: str = "", ten: str = "", dap: tuple = (0, 0), san: list = (),
           moi: bool = False, stage: dict | None = None) -> str:
    """The Block editor screen — ONE place for every write into the original CV.

    Three ways in, one screen:
        /cv/soan                 pick a block to edit
        /cv/soan?khoi=X          edit block X
        /cv/soan?ky=S            write a sentence about S — brief open, waiting
                                 for a block
        /cv/soan?khoi=X&ky=S     write into X, S's brief open above the box

    Keeping the CV stage's control bar has a reason: finish editing a block and
    the Run button turns itself into "Update — the words on the CV changed"
    (see cv/batch.stage). That is a reminder in the right place at the right
    time, not a line of advice.

    TODAY'S COVERAGE sits on the bar, NOT "just gained N postings". A delta
    belongs in the journal, where it has a timestamp; print it on screen and
    one F5 turns the number into a lie.
    """
    from ..layout import deck
    info = stage or {}
    words = sum(len(b["lines"]) for b in khoi)
    dang = chon["title"] if chon else ""

    # READING ORDER: what they ask -> what I write. The brief goes above the
    # editing box, always. The left column has to CARRY the target and the
    # base: clicking a block answers "write where", it must not discard the
    # answer to "write what".
    mang = (f"&ky={quote(ky, safe='')}" if ky else "")
    mang += (f"&nen={quote(nen, safe='')}" if nen else "")
    mang += "&tho=1" if tho else ""

    # A BLOCK THAT DOES NOT EXIST YET STILL GETS A FORM. Name a block that was
    # never saved — a Save just refused, or a block just renamed — and a screen
    # answering "no block chosen" loses the words just typed, with the user
    # unable to tell what they lost.
    moi = moi or bool(ten and chon is None)

    # TWO JOBS, TWO SHAPES — and this is the fix for the "I don't know what to
    # press" feedback.
    #
    #   `ky` set   WRITE A NEW SENTENCE -> three numbered steps, one box, one button
    #   otherwise  EDIT A BLOCK         -> the whole block, sentence by sentence,
    #                                      with verdict strips
    #
    # Both used to share one shape: someone arriving to write one sentence got
    # the full 16-sentence editor, with the box they needed buried two screens
    # down.
    ruot = _hut(hut, dang, ky)
    if brief:
        ruot += _viet(brief, dang or (ten if moi else ""), nen, loi, khoi,
                      soan, gy, tho)
        # A new block still needs somewhere to be NAMED — step 2 cannot do it.
        if moi and not dang:
            ruot += _form(None, [], ky, nen, loi, ten)
    elif chon or moi:
        ruot += _form(chon, cau, ky, nen, loi, ten)
    else:
        ruot += _san(list(san)) or _chua_chon()

    nhan = (f"about {ky}" if ky else
            chon["title"][:30] if chon else
            (ten[:30] or "New block") if moi else "nothing chosen")
    nen, tong = dap
    do = [(f"{len(khoi)}", "blocks", "stock"), (f"{words}", "sentences", "act")]
    # Coverage is the ONE number that says whether this screen is doing any
    # good: it ticks up every time a sentence lands in the right place.
    do.append((f"{nen}/{tong}" if tong else "—", "postings fully answered", "view"))
    return runtime.render(
        title="Block editor", active="/cv", stream="cv", journal="corner",
        bar=deck("cv", "CV · block editor",
                 info.get("state", "nothing built yet"),
                 do,
                 adjust="/adjust/cv",
                 run=info.get("label", "Run"),
                 run_note=info.get("note", ""),
                 sua=("/cv", "← CVs", "Back to the list of what will be sent"),
                 xoa=("/api/cv/xoa", "Delete versions", "Really delete?",
                      "Throw away every CV built. The words on the original CV "
                      "are NOT touched — press Run to rebuild")),
        cols=2, columns="minmax(330px, 1fr) 1.7fr",
        rows_tpl="1fr 150px", journal_at=(1, 2),
        panels=[
            runtime.panel("Raw material blocks", _khoi_list(khoi, dang, mang),
                          at=(1, 1)),
            runtime.panel(f"Editing · {nhan}", ruot, rows=2, at=(2, 1)),
        ],
    )


def _chua_chon() -> str:
    """Nothing chosen. Name THE JOB, do not say "no data yet"."""
    return (
        "<div class=empty-box><b>Pick a block on the left to edit</b>, press "
        "<b>+ New block</b>, or press something on the row above to write a "
        "new sentence about it.<br>Every sentence you type here is judged at "
        "once: whether the rules let it be printed, and how many postings are "
        "asking for what it mentions.</div>")


def _san(rows: list) -> str:
    """MACHINE HANDLES IT — a prepared draft for EVERY gap, on one screen.

    This is the only shape of "auto-fill" that does not lie. The machine does
    the whole part it can do beforehand — find a requirement line describing
    work, cut the excess, put it into the past — and then stops exactly where
    it does not know: THE NUMBER. The user fills the number in and presses,
    one sentence at a time.

    It does NOT write into the CV by itself. A draft sentence sitting inside
    `cv_text` would be counted by the scorer as a skill already answered, and
    coverage would jump with nothing real behind it — the app lying to the
    user about the user. That is the only reason, and it is enough.
    """
    if not rows:
        return ""
    o = ""
    for r in rows:
        cho = (f"/cv/soan?ky={quote(r['ky'], safe='')}"
               f"&nen={quote(r['nen'], safe='')}")
        o += (f"<a class=sanone href='{cho}'>"
              f"<span class=sanky>{esc(r['ky'])}<b>+{r['them']}</b>postings</span>"
              f"<span class=sannhap>{esc(r['nhap'])}</span>"
              f"<span class=sanco>{esc(r['cong_ty'])} · fill in the number and "
              f"save →</span>"
              f"</a>")
    return (f"<div class=sanbox><div class=briefhead>The machine has prepared "
            f"<b>{len(rows)}</b> drafts<span>one sentence per gap, excess "
            f"already cut and the tense already past. The <b>___</b> is the "
            f"evidence — the one thing the machine does not know. Press one to "
            f"fill it in and save.</span></div>{o}</div>")
