"""CV — every version the system WILL SEND, read before it goes.

This tab is NOT where a CV is written. The original is still `cv_text` in the
Profile — Vin's words, and the founding rule stands: the machine SELECTS and
ORDERS, it does not write (see cv/build).

This is where you LOOK FIRST. Before step 5 sends anything anywhere, Vin has
to be able to read every version that will go out, on one page.

Why duplicate versions are grouped: 101 postings worth applying to, but only
29 distinct versions. The CV structure is fixed — 2 roles · 3 projects · 2
education · 1 certificate · 4 skills = 16 sentences — so what changes is only
WHICH SENTENCE in each block gets picked. Listing all 101 rows means reading
the same version three or four times.

DRAWING ONLY.
"""

from __future__ import annotations

from html import escape as esc
from urllib.parse import quote

from . import runtime


def _khop(job: dict, q: str) -> bool:
    """Does this posting match the search text — by COMPANY or by TITLE."""
    return q in (job.get("company") or "").lower() \
        or q in (job.get("title") or "").lower()


def _row(index: int, ver: dict, q: str = "") -> str:
    """ONE row = one GROUP OF POSTINGS sharing a CV.

    NOBODY APPLIES TO A "VERSION", THEY APPLY TO A POSTING. So the row has to
    lead with the posting, not with the document.

    The old version printed the 4 English sentences unique to this CV. Those
    are Vin's own words — rereading them adds nothing, and times 28 rows
    nobody can read it at all. It also failed to answer the real question
    someone standing in front of 364 postings has: *which do I apply to now,
    and is this version good enough to send.*

    Four things, in the order they need reading:

        which posting  company — title — score, and it is what you click to apply
        good enough    how much of what THAT POSTING asks it answers  <- the gate
        how far it goes  how many other postings share this version
        what is missing  skills the posting asks that the CV is silent on  <- the work

    The detail (each sentence, what was changed, why something was dropped)
    lives on the page you click into — where the scoring sits too. The list is
    for SCANNING, the detail page for READING.
    """
    jobs = ver["jobs"]
    if q:
        jobs = sorted(jobs, key=lambda j: not _khop(j, q))
    # While searching, the row must open the posting whose name was typed, not
    # the group's highest-scoring one — somebody typing "Man Group" wants to
    # see the version going to Man Group.
    hop = [j for j in jobs if _khop(j, q)] if q else jobs
    best = max(hop or jobs, key=lambda j: j["score"] or 0)

    # COVERAGE — the row's decisive number. Computed over ONE posting (see
    # live.cv_versions): computed over the whole group it measures the group's
    # size, not the CV's quality.
    hoi = int(ver.get("hoi") or 0)
    tra = int(ver.get("tra_loi") or 0)
    pct = round(100 * tra / hoi) if hoi else 0
    # Three levels, because three levels lead to three different ACTIONS:
    # ready to send / sendable but weak / write more before sending.
    muc = "ok" if pct >= 60 else ("mid" if pct >= 35 else "low")
    thanh = (f"<span class='vbarc {muc}'><i style='width:{pct}%'></i></span>"
             if hoi else "")
    do = (f"<b>{tra}/{hoi}</b> of what this posting asks" if hoi
          else "<b>—</b> this posting names no skill at all")

    khac = (f" · shared by {len(jobs):,} postings" if len(jobs) > 1 else "")

    # TWO NUMBERS, TWO DIFFERENT QUESTIONS — and it has to be said outright,
    # or the reader works out 7−1=6, sees only 2 listed below, and thinks the
    # machine counted wrong:
    #   tra/hoi   how much of what THAT POSTING asks THIS VERSION answers
    #   cam       what THE WHOLE PROFILE has no sentence about
    # In between is what the profile HAS but this version had no room for —
    # that is a layout matter, and it is on the detail page.
    cam = ver.get("cam") or ver.get("missing") or []
    gap = ""
    if cam:
        chip = "".join(f"<span class=cvmiss>{esc(m)}</span>" for m in cam[:5])
        if len(cam) > 5:
            chip += f"<span class=cvmiss>+{len(cam) - 5}</span>"
        gap = f"<div class=cvgap>the profile has no sentence about: {chip}</div>"

    return (
        # CARRY THE WAY BACK. The CV view is reachable from here and from a
        # posting's detail page; without carrying it the Back button has to
        # hardcode one destination, and one of the two ways in becomes a dead
        # end.
        f"<a class=cvrow href='/jobs/{best['id']}/cv?tu=/cv'>"
        f"<div class=cvn>#{index}</div>"
        f"<div class=cvmain>"
        f"<div class=cvwho><b>{esc(best['company'])}</b>"
        f"<span class=vjob>{esc(best['title'])}</span></div>"
        f"<div class=vline>{thanh}<span class=vfrac>{do}</span>"
        f"<span class=muted>{esc(khac)}</span></div>"
        f"{gap}</div>"
        f"<div class=cvact><span class=cvscore>{best['score']}</span>"
        f"<button class='mbtn tiny' data-post='/cv/pdf'"
        f" data-arg='{best['id']}' onclick='event.preventDefault()'>PDF</button>"
        f"<span class=muted>open →</span></div></a>")


def _tim(q: str) -> str:
    """THE SEARCH BOX over the versions already built.

    The user's real question at this box is not "show me 28 versions" but
    "which version goes to Man Group". 28 rows cannot answer that; typing the
    company name answers it at once.

    A GET form, no JavaScript — like the search box on the Search tab: the
    state lives entirely on the URL, so typing and pressing Enter gives an
    address that can be saved and gone Back from.
    """
    xoa = ("<a class=jfindx href='/cv' title='Clear the search, show all'>×</a>"
           if q else "")
    return (f"<form class=jfind method=get action='/cv'>"
            f"<input class=search type=search name=q value='{esc(q)}'"
            f" autocomplete=off spellcheck=false"
            f" placeholder='who it goes to — type a company or a title'>"
            f"{xoa}</form>")


def _list(data: dict, q: str = "") -> str:
    versions = data["versions"]
    if not versions:
        return ("<div class=empty-box>no posting is worth applying to yet — run "
                "Search first, or loosen the filters</div>")

    lines = versions[0]["lines"]
    core = data["core"]
    gaps = "".join(f"<span class=cvmiss>{esc(g)}</span>" for g in data["gaps"][:14])

    # Say outright how much tailoring there really is. "29 distinct versions"
    # sounds like a lot, but 14 of 16 sentences are identical across every one
    # — only 2 sentences change with the JD.
    head = (f"<div class=gapnote><b>{len(versions)}</b> versions for "
            f"<b>{data['jobs']}</b> postings worth applying to. But "
            f"<b>{core}/{lines}</b> sentences are identical in every version — "
            f"only <b>{lines - core}</b> change with the JD. Each row below "
            f"prints only what is UNIQUE to that version.</div>")
    if gaps:
        head += (f"<div class=cvgaps>The profile can say NOTHING about: {gaps}"
                 f"<span class=muted>— this is what a new project should aim "
                 f"at</span></div>")

    head += _tim(q)

    # FILTER AFTER NUMBERING. A version's number has to stay the same while
    # searching — "#7" while searching that is "#3" otherwise cannot be talked
    # about.
    danh = list(enumerate(versions, 1))
    if q:
        low = q.lower()
        danh = [(i, v) for i, v in danh if any(_khop(j, low) for j in v["jobs"])]
        if not danh:
            return (head + "<div class=empty-box>no version goes to "
                    f"«{esc(q)}» — try another company or title</div>")
        head += (f"<div class=gapnote><b>{len(danh)}</b>/{len(versions)} versions "
                 f"have a posting matching «{esc(q)}»</div>")

    return head + "<div class=vlist>" + "".join(
        _row(i, v, q.lower()) for i, v in danh) + "</div>"


def render(*, versions: list[dict], jobs: int, gaps: list[str],
           core: int = 0, blocks: list[dict] | None = None,
           stage: dict | None = None, q: str = "",
           gap: dict | None = None, nhap: dict | None = None) -> str:
    """The CV tab. BLOCKS are Vin's raw material; VERSIONS are what the machine
    builds from them.

    Those two panels differ in who owns them, which is why only the right one
    waits for a Run button: a block is typed by Vin and shows at once, a
    version has to be built on request.
    """
    from ..layout import deck
    info = stage or {}
    data = {"versions": versions, "jobs": jobs, "gaps": gaps, "core": core}
    blocks = blocks or []
    words = sum(len(b["lines"]) for b in blocks)
    # THE LEAD LINE has to describe the real state. Saying "26 sentences -> 0
    # versions for 364 postings" before anything is built makes the user think
    # the builder is broken rather than that they have not pressed anything.
    note = (f"{words} sentences of raw material → {len(versions)} versions for "
            f"{jobs} postings. The sentence store is the CEILING of the whole "
            f"system: for a CV that lands better, write another block — not a "
            f"cleverer selection." if versions else
            f"{words} sentences of raw material in the store. Nothing built "
            f"yet — press Run on the bar above and the machine reads each "
            f"posting, then builds a version for it.")
    return runtime.render(
        title="CV", active="/cv", stream="cv", journal="corner",
        # Building CVs changes the version list -> redraw. The EDITOR screen
        # (cvsoan) declares NO `reload`: people are typing there, and a redraw
        # is a theft.
        reload="cv",
        bar=deck("cv", "CV", info.get("state", "nothing built yet"),
                 [(f"{words}", "sentences", "stock"),
                  (f"{len(versions)}", "versions", "act"),
                  (f"{info.get('worth', 0):,}", "worth applying to", "view")],
                 adjust="/adjust/cv",
                 run=info.get("label", "Run"),
                 run_note=info.get("note", ""),
                 sua=("/cv/soan", "Edit blocks",
                      "Open the block editor — full window, sentence by sentence"),
                 xoa=("/api/cv/xoa", "Delete versions", "Really delete?",
                      "Throw away every CV built. The words on the original CV "
                      "are NOT touched — press Run to rebuild")),
        note=note,
        cols=2, columns="minmax(360px, 1fr) 1.6fr",
        rows_tpl="1fr 140px", journal_at=(1, 2),
        panels=[
            # THE BLOCK STORE HAS MOVED OUT OF HERE. It has a home of its own
            # on the Edit blocks screen, where clicking a block edits it. Here
            # it was only to look at — while this tab answers two other
            # questions: *what do I write tonight* and *which version do I
            # send*.
            runtime.panel("What to write to close the gap", hut(gap or {}, nhap),
                          at=(1, 1)),
            runtime.panel("What will be sent", _list(data, q) if versions
                          else _chua_dung(info), rows=2, at=(2, 1)),
        ],
    )


def _chua_dung(info: dict) -> str:
    """The empty panel before Run has been pressed. It says WHAT THERE WILL BE,
    not merely that there is nothing.

    "No data yet" is a useless sentence: it does not tell the user what
    pressing the button gets them, so they do not press it.
    """
    ly_do = esc(info.get("note", ""))
    return (
        "<div class=empty-box>"
        "<b>No CV has been built yet.</b><br>"
        "Press <b>Run</b> on the bar above. The machine reads every posting "
        "worth applying to, asks your sentence store which sentences answer "
        "that posting's requirements, and builds a version for it — with a "
        "before/after comparison and the reason each sentence was picked or "
        "dropped."
        f"<br><span class=muted>{ly_do}</span></div>")


# ------------------------------------------------------ the ⚟ Adjust panel

# TWO KNOBS, that is all. Seven knobs were dropped — see the note in
# core/prefs.py.
#
# The user needs exactly two answers: how far each CV is tailored to its
# posting, and whether the machine handles what it can handle by itself.
# Everything else that used to be laid out here made them learn the machine's
# rules before they could use the machine.

NUM = (
    # TAILORING DEPTH — the knob that changes most. Measured on the real store
    # (358 postings): shared 25 versions · medium 89 · per-posting 157, with
    # the unchanging core falling from 12/16 to 9/16 sentences. All three
    # levels ONLY REORDER words the user already wrote.
    #
    # The numbers are NOT hardcoded into the labels: they differ per profile
    # and per store, and recounting costs three build runs. The real numbers
    # appear on the bar after a build.
    ("rieng", "Tailoring depth", "how far each version is tailored to its posting",
     (("chung", "Shared", "only picks sentences from experience and project blocks"),
      ("vua", "Medium", "+ moves the skills sections this posting asks for to the front"),
      ("rieng", "Per posting", "+ moves the items inside those sections to the front"))),
)

# THE SELF-SERVE SWITCH — the machine does everything it can without being
# asked.
TU_LO = (
    "tu_lo", "Machine handles it",
    "Turned on, the machine does two things unasked: builds a draft for EVERY "
    "gap labelled WRITE, and rebuilds every CV the moment the words on the CV "
    "change. The one part it cannot handle is THE NUMBERS — how many, over "
    "how much data, how much it changed. The machine does not know what you "
    "did, and a sentence on a CV is a sentence you have to hold up in the "
    "interview room.")


def adjust(num: dict | None = None) -> str:
    """The ⚟ overlay — the CV layer's TWO knobs.

    Pressing takes effect immediately, with NO Apply button — like the source
    switches on the Search tab.
    """
    dang = (num or {}).get("ten") or {}
    khoi = ""
    for ma, ten, y_nghia, chon in NUM:
        # THE ACTIVE LEVEL MUST CARRY A TICK, not just a different colour. The
        # previous version gave the other levels an `off` class — and
        # `.mbtn.off` never had any CSS, so all three buttons looked identical
        # and nobody could tell where they were. A ✓ reads even when the
        # colour breaks, and on paper.
        nut = ""
        for gia_tri, nhan, ghi in chon:
            on = dang.get(ma) == gia_tri
            nut += (f"<button class='mbtn tiny{' on' if on else ' off'}'"
                    f" data-post='/api/cv/num' data-arg='{esc(ma)}:{esc(gia_tri)}'"
                    f" title='{esc(ghi)}'>{'✓ ' if on else ''}{esc(nhan)}</button>")
        khoi += (f"<div class=adjrow><div class=adjname><b>{esc(ten)}</b>"
                 f"<span>{esc(y_nghia)}</span></div>"
                 f"<div class=srcrow>{nut}</div></div>")

    ma, ten, y_nghia = TU_LO
    on = bool((num or {}).get("tu_lo"))
    khoi += (f"<div class='swrow{'' if on else ' off'}'>"
             f"<button class='mbtn tiny swbtn{'' if on else ' off'}'"
             f" data-post='/api/cv/num' data-arg='{ma}:{'0' if on else '1'}'>"
             f"{'ON' if on else 'OFF'}</button>"
             f"<b class=swten>{esc(ten)}</b>"
             f"<span class=swnow>"
             + ("drafts prepared · rebuilt at once" if on else "you press it yourself")
             + f"</span>"
             f"<details class=swwhy><summary>why</summary>"
             f"<div class=swbody>{esc(y_nghia)}</div></details></div>")

    return ("<div class=sheethead>Adjust · CV</div>"
            f"<div class=adjbox>{khoi}</div>")


# ------------------------------------------------------------ THE GAP BLOCK

# THE CAPTION MUST DESCRIBE WHAT THE MACHINE MEASURES. An earlier version read
# "you have done this, you just have not written it down" — the machine does
# not know that and has never measured it; all it can measure is that these
# requirement lines name no product. Making a claim on the user's behalf is
# exactly the disease this whole app avoids.
def _nhap_dong(d: dict | None) -> str:
    """The draft for one gap row — or, said outright, why there is none."""
    if d is None:
        return ""                         # the switch is off
    if d.get("nhap"):
        return (f"<span class=hnhap>{esc(d['nhap'])}"
                f"<i>{esc(d['cong_ty'][:24])}'s words · click to fill in the "
                f"numbers and save</i>"
                f"</span>")
    if not d.get("nen_co"):
        return ("<span class='hnhap tho'>no posting asks for it in a line that "
                "DESCRIBES WORK — write it from scratch in your own words</span>")
    return ("<span class='hnhap tho'>the machine could not cut any of their "
            "lines down to the shape of a CV sentence — write it from scratch, "
            "using their line as the brief</span>")


VIEC = {"viet": ("WRITE", "viet",
                 "the lines asking for it name no product — it can be said in "
                 "your own words, if you have done it. One evening."),
        "hoc": ("LEARN", "hoc",
                "names a product outright — no sentence stands in for it")}


def hut(d: dict, nhap: dict | None = None) -> str:
    """Write a sentence about what, and how many POSTINGS CLEAR.

    The block that answers this tab's one question: *what do I write tonight?*

    THE UNIT IS POSTINGS CLEARED — postings where EVERY must line is answered.
    Counted by mentions, `cloud` comes top (50 lines) while unlocking only 19
    postings, and `visualisation` unlocks 28. Counting in the wrong unit
    orders the work wrongly.

    Each row is the MARGINAL value once the rows above it are done — three
    skills unlocking the same posting, added up separately, count it three
    times.
    """
    buoc = d.get("buoc") or []
    _np = nhap or {}
    tong, nen = d.get("tin") or 0, d.get("nen") or 0
    if not buoc or not tong:
        # THE GAP LADDER COMES WITH THE BUILD. Before Run is pressed there is
        # no measurement — so name the actual thing to do, and do not blame
        # Search while the posting store is sitting right there.
        return ("<div class=empty-box><b>The gap has not been measured.</b><br>"
                "Press <b>Run</b> on the bar above — the machine measures it "
                "during the same pass that builds the CVs, so the two panels "
                "always speak about the same moment.<br>"
                "<span class=muted>if nothing has been scored yet, run Search "
                "first.</span></div>")

    hang = []
    for b in buoc:
        nhan, lop, y = VIEC.get(b["viec"], VIEC["viet"])
        viet_duoc = b["dong"] - b["rieng"]
        # The bar length follows POSTINGS UNLOCKED, not the number of lines —
        # that is the number that decides.
        rong = round(100 * b["them"] / max(1, buoc[0]["them"]))
        hang.append(
            f"<div class=hrow title='{esc(y)}'>"
            f"<span class='hlab {lop}'>{nhan}</span>"
            f"<span class=hname>{esc(b['ky_nang'])}</span>"
            f"<span class=hbar><i style='width:{rong}%' class={lop}></i></span>"
            f"<span class=hplus>+{b['them']}<span>postings</span></span>"
            f"<span class=hcum>{b['cong_don']}<span>/{tong}</span></span>"
            # THE WRITE BUTTON only on rows THAT CAN BE WRITTEN. Inviting
            # someone to write a row that is nothing but product names is
            # inviting them to do something that cannot be done.
            + (f"<a class='mbtn tiny hgo'"
               f" href='/cv/soan?ky={quote(b['ky_nang'], safe='')}"
               + (f"&nen={quote(_np.get(b['ky_nang'], {}).get('nen', ''), safe='')}"
                  if (_np.get(b["ky_nang"]) or {}).get("nhap") else "")
               + f"'>{'Edit draft' if (_np.get(b['ky_nang']) or {}).get('nhap') else 'Write'}</a>"
               if b["dong"] - b["rieng"] > 0 else "")
            + f"<span class=hsplit>{b['dong']} lines ask · "
            f"<b>{viet_duoc}</b> writable"
            + (f" · <b>{b['rieng']}</b> to be learnt" if b["rieng"] else "")
            + "</span>"
            # THE DRAFT THE MACHINE PREPARED, on the very row it belongs to.
            # Turning a switch on and then having to hunt for the result on
            # another screen means the button says one thing and the screen
            # another. Three outcomes, and all three are said.
            + _nhap_dong(_np.get(b["ky_nang"]))
            + "</div>")

    het = buoc[-1]["cong_don"]
    cv_ = d.get("chi_viet") or nen
    nv = d.get("so_viet") or 0
    # TWO TARGETS, NOT ONE. "Do the whole table" folds in the rows that have
    # to be LEARNT — learning is counted in months, writing in evenings.
    # Folded together, the user is shown one target they cannot reach tonight.
    return (
        f"<div class=gapnote>The profile fully answers <b>{nen}</b>/{tong} "
        f"postings (<b>{nen * 100 // tong}%</b>).</div>"
        f"<div class=htarget>"
        f"<span class=ht1><b>{cv_}</b> postings ({cv_ * 100 // tong}%)"
        f"<span>needs only WRITING {nv} sentences — doable tonight</span></span>"
        f"<span class=ht2><b>{het}</b> postings ({het * 100 // tong}%)"
        f"<span>if the rest is learnt as well</span></span></div>"
        f"<div class=gapnote>Each row is how many postings it unlocks ON TOP OF "
        f"the rows above it — they do not add up.</div>"
        + "".join(hang)
        + "<div class=note><b>WRITE</b> = the requirement lines are general, so "
          "they can be answered in your own words if you have done the work. "
          "<b>LEARN</b> = they name a product outright, and no sentence stands "
          "in for it. The machine can only pick words you have already "
          "written, so these are yours to do.</div>")
