"""THE MARKING — before/after, and why each sentence was picked or dropped.

This is the only thing in the CV layer that talks to a PERSON. Every other
module decides; this one explains.

WHY IT IS NEEDED. The machine decides a great deal on each build — which
sentences go on, in what order, which are banned, which were reworded — and
there used to be nowhere for Vin to see it. A machine that decides without
explaining leaves the user two options: blind trust, or abandoning it. Both
are worse than reading the reason and fixing it themselves.

And it catches bugs. The rule `rules.sentence_ok` banned failure-telling
sentences from the CV from the start, but the builder never consulted it — 3
banned sentences went out on EVERY version, including "drawdown ran roughly
30% deeper than the model predicted". Nobody saw it, because there was no
explanation to read.

THE LAYOUT, in the order a reader needs it:

    summary     how much of the requirements is answered · sentences in ·
                sentences reworded
    per line    AFTER (printed) · BEFORE (as Vin wrote it) · what it answers
                · what is still missing
    dropped     split into TWO groups, because the two need different actions
    silent      what the posting asks that the profile cannot answer -> this
                is the work to do
"""

from __future__ import annotations

from html import escape as esc

from .build import TailoredCV, dang_ke

# Which drop reasons are BANS. This distinction decides what the user has to
# do: a banned sentence cannot be saved by rewording (it does not belong on a
# CV), while a weaker sentence needs no work at all — another posting will
# use it.
CAM = ("outcome failure", "opinion", "invites the reader", "too short")

VIET = {
    "outcome failure — belongs on the project page, not the CV":
        "tells a failure — belongs on a project page, not a CV",
    "opinion, not evidence of capability":
        "an opinion, not evidence of ability",
    "too short to carry evidence":
        "too short to carry evidence",
    "invites the reader to doubt you":
        "invites the reader to doubt you",
    "has hard evidence but wording may read badly — your call":
        "hard evidence but wording that reads badly — your call",
    "weaker than what this posting asks for":
        "weaker than what this posting asks — another posting will use it",
}


def vi(why: str) -> str:
    """The drop reason in plain words. Shared with the block editor."""
    return VIET.get(why, why)


def _la_cam(why: str) -> bool:
    return any(k in why for k in CAM)


def _bo(cv: TailoredCV) -> str:
    """Dropped sentences in TWO GROUPS — the two need different actions."""
    cam = [(t, w) for t, w in cv.dropped if _la_cam(w)]
    yeu = [(t, w) for t, w in cv.dropped if not _la_cam(w)]

    def _khoi(rows, tieu_de, dan) -> str:
        if not rows:
            return ""
        muc = "".join(
            f"<li><span class=dtext>{esc(t)}</span>"
            f"<span class=dwhy>{esc(vi(w))}</span></li>" for t, w in rows)
        return (f"<h4 class=cvsec>{esc(tieu_de)} ({len(rows)})</h4>"
                f"<ul class=droplist>{muc}</ul><div class=note>{dan}</div>")

    return (
        _khoi(cam, "The rules do not allow these on a CV",
              "Rewording cannot save them — these do not belong on a CV. They "
              "are NOT deleted from your profile: their place is the "
              "interview, where an experienced reader counts honesty as a "
              "strength. In front of someone sifting 200 CVs in an afternoon, "
              "it is not.")
        + _khoi(yeu, "Saved for another posting",
                "These are perfectly valid — THIS posting simply asks for "
                "something else. Nothing to fix; the CV for another posting "
                "will use them."))


def diem(cv: TailoredCV) -> dict:
    """This version's numbers. Computed in one place so the words and the
    figures cannot disagree."""
    lines = [l for s in cv.sections for l in s.lines
             if s.kind in ("experience", "project")]
    return {
        "vao": len(lines),
        "sua": sum(1 for l in lines if l.sua),
        "hong": sum(1 for l in lines if l.yeu),
        "xem": sum(1 for l in lines if l.review),
        "bo_cam": sum(1 for _, w in cv.dropped if _la_cam(w)),
        "bo_yeu": sum(1 for _, w in cv.dropped if not _la_cam(w)),
        # See live.cv_versions: wanted/covered is a LYING pair (the
        # denominator picks up the company blurb, the numerator skips the
        # Technical skills section).
        "doi": len(cv.asked),
        "tra_loi": len(cv.on_paper),
        "cam": len(cv.missing),
    }


def cho_xem(cv: TailoredCV) -> list:
    """Every SPOT worth looking at on this sheet, by kind. [(kind, label,
    count), …]

    Counted by SPOT rather than by sentence: one sentence can be both missing
    a measurement and too long, and that is two things to do, not one.
    """
    from collections import Counter
    dem: Counter = Counter()
    for sec in cv.sections:
        if sec.kind not in ("experience", "project"):
            continue
        for line in sec.lines:
            for v in getattr(line, "vet", ()) or ():
                dem[v.loai] += 1
    ten = {"thieu_so": "no measurement", "qua_dai": "too long",
           "lac_de": "does not touch this posting", "da_sua": "reworded"}
    thu_tu = ("thieu_so", "qua_dai", "lac_de", "da_sua")
    return [(k, ten[k], dem[k]) for k in thu_tu if dem[k]]


def head(cv: TailoredCV, xem_tin: str = "") -> str:
    """THE SCORE + WHAT TO LOOK AT + the Before/After toggle. At the very
    top, above the CV sheet.

    The first number has to answer "what is left to do on this sheet" —
    opening it should say at once that there are 5 spots to look at, not
    require clicking each line to find out.
    """
    d = diem(cv)
    ty = f"{d['tra_loi']}/{d['doi']}" if d["doi"] else "—"
    cho = cho_xem(cv)
    can = sum(n for k, _, n in cho if k != "da_sua")

    o = ("<div class=gsum>"
         f"<span class='gstat {'act' if can else ''}'><b>{can}</b>"
         f"chỗ cần bạn xem</span>"
         f"<span class=gstat><b>{ty}</b>of what this posting asks, the CV answers</span>"
         f"<span class=gstat><b>{d['vao']}</b>sentences on this version</span>"
         f"<span class=gstat><b>{len(cv.missing)}</b>things the profile cannot answer</span>"
         "</div>")
    # A LEGEND for the marks — without it the underlines are a puzzle.
    chu_giai = ("<div class=glegend>"
                + "".join(f"<span class='gleg v{k}'>{esc(nhan)} <b>{n}</b></span>"
                          for k, nhan, n in cho)
                + "<span class='gleg kw'>keywords this posting asks for</span></div>"
                if cho else "")
    # VIEW POSTING sits BESIDE the Before/After toggle; it does not take
    # Back's place. Back means "return to the page you left"; viewing the
    # posting is a different journey. Merge them and one of the two is
    # always wrong.
    di = (f"<a class='mbtn tiny' href='{esc(xem_tin)}'>Xem tin →</a>"
          if xem_tin else "")
    nut = ("<input type=checkbox id=cvtruoc class=gswitch hidden>"
           "<div class=gtoggle>"
           "<label for=cvtruoc><span class=gt1>Sau khi sửa</span>"
           "<span class=gt2>Before rewording</span></label>"
           "<span class=muted>click to see your original wording</span>"
           f"{di}</div>")
    chu = ("<div class=note>An underline is where the machine has an "
           "opinion — click that span to see how to fix it and to swap in "
           "another sentence you wrote. The machine only <b>cuts and "
           "reorders</b> your words; every word on the printed sheet comes "
           "from a sentence you wrote.</div>")
    return (f"{nut}<div class=cvaudit>"
            f"<h4 class=cvsec>Marking this version</h4>{o}{chu_giai}{chu}</div>")


def chi_tiet(cv: TailoredCV) -> str:
    """The section under the CV sheet — ONLY what belongs to no single line.

    Each sentence is already marked ON THE SHEET (see render._muc): clicking
    a line opens a card in place, saying what the posting asks, what the
    machine reworded, what is still missing, and what to swap in. So this
    does NOT repeat each sentence — repeating makes the reader read the same
    thing twice and then match "sentence 3 below" with one above.

    Exactly two things are left, and both are about THE SHEET rather than one
    line:
        sentences that did NOT make it — why they are absent
        what the posting asks that the profile cannot answer — the work to
        do, which no existing sentence can fill
    """
    cam = ""
    if cv.missing:
        cam = ("<h4 class=cvsec>Asked for, and the profile cannot answer</h4>"
               "<div class=chiprow>"
               + "".join(f"<span class='badge warn'>{esc(m)}</span>"
                         for m in cv.missing)
               + "</div><div class=note>No sentence in your profile fills "
                 "these — the machine can only pick words you have written. "
                 "Either you genuinely have not done it, or you have and "
                 "never wrote it down; the second is fixable tonight with one "
                 "sentence.</div>")
    # Wrapped in .cvaudit — the @media print rules already hide this class.
    return "<div class=cvaudit>" + _bo(cv) + cam + "</div>"
