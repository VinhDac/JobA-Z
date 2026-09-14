"""The queue — everything THE MACHINE CANNOT SETTLE, gathered in one place.

A sub-screen of Manage. It is separate for a reason, not for looks:

    /track        THE TABLE. Settled work, decided, read-only.
    /track/queue  THE QUEUE. What the machine is stuck on, needing a person.

Mixed into one page, the clean half is pushed down by the unresolved half —
16 mail cards pushed the table's search box more than a screen down, and
someone coming to read the table had to scroll past a pile of undone work to
reach what they came for.

And they differ in RHYTHM: the table is glanced at daily, the queue is sat
down with once and emptied. A place that can be emptied is a workplace; the
table never empties.

THE MACHINE CHANGES NOTHING HERE BY ITSELF. It proposes, a person clicks.
This is where that boundary takes visible form — see apply/run.py for the
same boundary in the applying layer.

DRAWING ONLY.
"""

from __future__ import annotations

from html import escape as esc

from ...track.board import STAGE_LABEL
from . import runtime


def _ask(items: list[dict], rows: list[dict] | None = None) -> str:
    """The NEEDS-VIN strip: mail proposing a status change.

    `rows` = the whole table, so a mail matching NO row can still be attached
    by hand. Such a mail used to have exactly one button — Skip. The machine
    read the outcome but could not work out the company, and then asked the
    user to throw the mail away: seeing something you can do nothing about is
    still losing it, just more loudly. Measured, the real mailbox has 3.
    """
    if not items:
        return ""
    chon = "".join(
        f"<option value='{r['id']}'>{esc(r['company'][:34])}"
        + (f" · {esc(r['role'][:26])}" if r.get("role") else "") + "</option>"
        for r in sorted(rows or [], key=lambda x: x["company"].lower()))
    rows = ""
    for p in items:
        who = p["company"] or p["company_guess"] or "?"
        # Vin applied for three roles at Point72; a rejection arrives and
        # the machine proposes demoting ONE row. Without showing the role,
        # Vin presses Accept without knowing which one he just closed.
        job = f" · {p['role'][:38]}" if p.get("role") else ""
        now = STAGE_LABEL.get(p["stage"], "—") if p["stage"] else "no row yet"
        to = STAGE_LABEL.get(p["kind"], p["kind"])
        rows += (
            f"<div class=askrow><div class=askmain>"
            f"<div class=askwho><b>{esc(who)}</b><i>{esc(job)}</i>"
            f"<span class=askmove>{esc(now)} → <b>{esc(to)}</b></span></div>"
            f"<div class=asksub>{esc(p['subject'][:88])}</div>"
            f"<div class=asksnip>{esc((p['snippet'] or '')[:130])}</div></div>"
            f"<div class=askact>"
            + (f"<button class='mbtn tiny apply' data-post='/api/track/mail'"
               f" data-arg='{p['id']}:yes'>Accept</button>"
               if p["app_id"] else
               (f"<form class=ganform method=post data-post='/api/track/mail/gan'>"
                f"<select name=app data-ganfor='{p['id']}'>"
                f"<option value=''>the machine cannot tell whose this is — pick…</option>"
                f"{chon}</select></form>" if chon else
                "<span class=muted>matches no row</span>"))
            + f"<button class='mbtn tiny' data-post='/api/track/mail'"
              f" data-arg='{p['id']}:no'>Skip</button></div></div>")
    return (f"<div class=asklist><div class=askhead>{len(items)} mail waiting "
            f"on you — the machine proposes, it does not change anything"
            f"</div>{rows}</div>")


# The four outcomes a user can assign to a mail the machine cannot read.
XEP = (("applied", "acknowledgement"), ("interview", "interview invitation"),
       ("rejected", "rejection"), ("offer", "offer"))


def _mu(items: list[dict]) -> str:
    """MAIL THE MACHINE CANNOT READ — and this is the mail layer's real
    promise.

    A table of phrasings is never complete: measured on the real mailbox,
    Maven's rejection ("Sorry, it's not quite a match") and Trading 212's
    acknowledgement ("Your application is in") both fell into `other` and
    vanished. Racing to add more keywords is a game with no end.

    So the machine does NOT promise to understand every mail. It promises NO
    MAIL DISAPPEARS: anything it is stuck on that belongs to an application
    on the table appears here, and one classification from the user settles
    it.
    """
    if not items:
        return ""
    rows = ""
    for m in items:
        nut = "".join(
            f"<button class='mbtn tiny' data-post='/api/track/mail/xep'"
            f" data-arg='{m['id']}:{ma}'>{esc(nhan)}</button>"
            for ma, nhan in XEP)
        rows += (
            f"<div class=askrow><div class=askmain>"
            f"<b>{esc(m['company'] or m['company_guess'] or '?')}</b>"
            f"<span class=askto>the machine could not read this — you classify it</span>"
            f"<div class=asksub>{esc(' '.join((m['subject'] or '').split())[:96])}</div>"
            f"<div class=asksnip>{esc(' '.join((m['snippet'] or '').split())[:130])}</div>"
            f"</div><div class=askact>{nut}"
            f"<button class='mbtn tiny' data-post='/api/track/mail/ignore'"
            f" data-arg='{m['id']}'>skip</button></div></div>")
    return (f"<div class='asklist mu'><div class=askhead>"
            f"<b>{len(items)}</b> mail the machine could NOT read — but they "
            f"belong to an application on the table, so none is left behind"
            f"</div>{rows}</div>")


# The stages REACHABLE from each stage. Moved here from the table: changing a
# stage is EDITING, and the table edits nothing.
NEXT = {"draft": [("applied", "sent by hand")],
        "applied": [("interview", "interview"), ("rejected", "rejected")],
        "interview": [("offer", "offer"), ("rejected", "rejected")],
        "rejected": [], "offer": []}


def _nhap(rows: list[dict]) -> str:
    """FILLED IN, WAITING ON YOUR SEND — the app's real work in progress.

    The machine opens the form, fills what it can prove, and STOPS: questions
    like sponsorship or the graduation date can only be answered by you, and
    the Send click is yours. That boundary lives in apply/run.py, and this is
    where it becomes a piece of work to do.
    """
    nhap = [r for r in rows if r.get("stage") == "draft"]
    if not nhap:
        return ""
    o = ""
    for r in nhap:
        o += (f"<div class=askrow><div class=askmain>"
              f"<div class=askwho><b>{esc(r['company'][:34])}</b>"
              f"<i>{esc((r.get('role') or '')[:38])}</i></div>"
              f"<div class=asksub>the machine has filled everything it can "
              f"prove — what is left is the questions only you can answer"
              f"</div></div>"
              f"<div class=askact>"
              f"<button class='mbtn tiny apply' data-post='/api/apply/send'"
              f" data-arg='{r['id']}'>Send it</button>"
              f"<button class='mbtn tiny' data-post='/api/track/drop'"
              f" data-arg='{r['id']}'>drop</button></div></div>")
    return (f"<div class=asklist><div class=askhead><b>{len(nhap)}</b> "
            f"application(s) filled in, waiting on your Send</div>{o}</div>")


def _tay(rows: list[dict]) -> str:
    """THE MACHINE IS STUCK — and it hands over the tools rather than just
    saying so.

    A LinkedIn posting that does not expose an application link (an agency,
    or LinkedIn's own form). The two things needed to do it yourself are THE
    APPLICATION LINK and THE CV, and the app holds both. When done, press
    Scan mail: the acknowledgement arriving changes the status by itself —
    no manual marking.
    """
    tay = [r for r in rows if (r.get("origin") or "") == "tay"]
    if not tay:
        return ""
    o = ""
    for r in tay:
        mo = (f"<a class='mbtn tiny apply' href='{esc(r['url'])}' target=_blank"
              f" rel=noopener>Open the application page ↗</a>" if r.get("url") else "")
        tai = (f"<button class='mbtn tiny' data-post='/api/cv/pdf'"
               f" data-arg='{r['posting_id']}'>Download the CV</button>"
               if r.get("posting_id") else "")
        o += (f"<div class=askrow><div class=askmain>"
              f"<div class=askwho><b>{esc(r['company'][:34])}</b>"
              f"<i>{esc((r.get('role') or '')[:38])}</i></div>"
              f"<div class=asksub>the machine cannot apply for you — open the "
              f"page, download the CV, apply by hand. Then press <b>Scan "
              f"mail</b>: when the acknowledgement arrives the row moves to "
              f"«applied» on its own</div></div>"
              f"<div class=askact>{mo}{tai}</div></div>")
    return (f"<div class='asklist mu'><div class=askhead><b>{len(tay)}</b> tin "
            f"the machine cannot apply for you — you apply</div>{o}</div>")


def _doi(rows: list[dict], doi: str = "") -> str:
    """CHANGE A STAGE BY HAND — an escape hatch, ONE of them, not 74 buttons.

    Why it must exist: mail is the table's only sensor. An interview
    invitation by phone leaves no mail, so the machine never learns of it —
    and after 20 days it quietly files that row under "counts as rejected".
    Without this hatch, that is a real opportunity lost outright.

    Why NOT on the table: there it becomes 74 buttons sitting beside the 37
    rows being read, and one mis-click changes a real status. Here it is two
    deliberate steps — pick the row, then pick the stage.

    THE TWO STEPS GO THROUGH THE URL (`?doi=`), not JavaScript: opening the
    address directly or pressing Back both behave correctly, the same way the
    Search box does.
    """
    that = [r for r in rows if r.get("stage") != "draft"]
    if not that:
        return ""
    chon = "".join(
        f"<option value='{r['id']}'{' selected' if str(r['id']) == doi else ''}>"
        + esc(r["company"][:34])
        + (f" · {esc(r['role'][:26])}" if r.get("role") else "")
        + f" — {esc(STAGE_LABEL.get(r['stage'], r['stage']))}</option>"
        for r in sorted(that, key=lambda x: x["company"].lower()))
    kia = next((r for r in that if str(r["id"]) == doi), None)
    nut = ""
    if kia:
        di = NEXT.get(kia["stage"], [])
        nut = ("".join(
            f"<button class='mbtn tiny{' apply' if to == 'applied' else ''}'"
            f" data-post='/api/track/state'"
            f" data-arg='{kia['id']}:{to}'>{esc(nhan)}</button>"
            for to, nhan in di)
            or "<span class=muted>this stage is already an outcome — there "
               "is nowhere further to go</span>")
        nut = (f"<div class=doinow><b>{esc(kia['company'][:40])}</b>"
               f"<span>currently «{esc(STAGE_LABEL.get(kia['stage'], ''))}»"
               f" — change to:</span><div class=askact>{nut}</div></div>")
    return (f"<div class=asklist><div class=askhead>Change a stage by hand"
            f"<span>for when the outcome arrives outside the mailbox — a "
            f"phone call, a text. The machine cannot see those.</span></div>"
            f"<form class=doiform method=get action='/track/queue'>"
            f"<select name=doi>{chon}</select>"
            f"<button class='mbtn tiny'>Pick</button></form>{nut}</div>")


def _trong() -> str:
    """An empty queue — and it CAN be empty; that is the point of this screen."""
    return ("<div class=empty-box><b>Nothing is waiting on you.</b><br>"
            "Any mail the machine could read an outcome from has already gone "
            "into the table. This lights up only when the machine is stuck — "
            "press <b>Scan mail</b> to read the mailbox again.</div>")


def render(*, rows: list[dict], asks: list[dict], mu: list[dict] | None = None,
           stage: dict | None = None, doi: str = "") -> str:
    """Two panels: MAIL (read / not read) · WORK & EDITS.

    The table at /track is facts only — not one button changes a row.
    Everything that asks for an opinion or edits anything lives here, grouped
    by WHO IS STUCK:

        the machine read an outcome and wants a nod    -> one click
        the machine could not read the mail            -> you classify it
        the application is filled in, Send is yours    -> you send
        the machine cannot apply for you               -> you apply by hand
        the machine saw nothing (a call, a text)       -> you change the stage

    The first three are mail, the last two are work — so two panels, not
    five.
    """
    from ..layout import deck
    info = stage or {}
    de = asks or []
    bi = mu or []
    tay = _tay(rows)
    nhap = _nhap(rows)
    viec = nhap + tay + _doi(rows, doi)
    con = len(de) + len(bi) + sum(1 for r in rows if r.get("stage") == "draft") \
        + sum(1 for r in rows if (r.get("origin") or "") == "tay")
    return runtime.render(
        title="Queue", active="/track", stream="search", journal="bottom",
        # REDRAW when the MANAGE stage finishes, not when the scan does. This
        # page is built from applications + mail, while the scan only
        # produces postings — jumping the page when a scan ends slams shut
        # every open row, exactly while the user is reading a mail. The
        # journal panel still watches the `search` stream because that is the
        # long-running stage and the one worth watching; two different jobs.
        reload="track",
        cols=2,
        bar=deck("track", "Manage · queue",
                 (f"{con} waiting on you" if con else "nothing waiting on you"),
                 [(f"{len(de)}", "proposed", "act"),
                  (f"{len(bi)}", "unreadable", "new"),
                  (f"{con - len(de) - len(bi)}", "waiting on you", "new"),
                  (f"{len(rows)}", "rows on the table", "view")],
                 run="Scan mail", run_note="read the mailbox and update the table",
                 sua=("/track", "← Table", "Back to the applications table")),
        panels=[runtime.panel("Mail · the machine is asking you",
                              (_ask(de, rows) + _mu(bi)) or _trong(), rows=2),
                runtime.panel("Work & edits · what the table cannot do",
                              viec or "<div class=empty-box>no application is "
                              "half-done, and the table matches what the mail "
                              "says.</div>",
                              rows=2)],
    )
