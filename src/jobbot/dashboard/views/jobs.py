"""ONE posting in detail — the score, each requirement, the evidence, the why.

The LIST page went with the Jobs tab. The list belongs in the Search tab,
because "searching" and "looking at what the search found" are one job, not
two.

This page IS STILL ALIVE at /jobs/<id> — it is where the new list points, and
where you read why a posting scored what it scored.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc
from urllib.parse import quote

from ..layout import card, duong_ve, empty, h1, page, score_bar

CHANCE_BADGE = {"likely": ("worth applying", "ok"),
                "possible": ("maybe", ""),
                "unlikely": ("long shot", "warn")}



CONF_NOTE = {"high": "", "medium": "few requirements found",
             "low": "requirements guessed from prose", "none": ""}


def _score(job: dict) -> str:
    """When it cannot score, SAY SO. An invented score is worse than none."""
    if job.get("score") is None:
        return "<span class=noscore>can&#39;t read requirements — judge it yourself</span>"
    note = CONF_NOTE.get(job.get("confidence", ""), "")
    tail = f"<span class=conf>{esc(note)}</span>" if note else ""
    return score_bar(job["score"]) + tail


def _breakdown(job: dict) -> str:
    """Where the score came from. A score that cannot be explained is not
    used to decide whether to apply."""
    data = job.get("explain")
    if not data or data.get("score") is None:
        return ""
    b = data["breakdown"]
    rows = "".join(
        f"<div class=bdrow><span class=bdl>{esc(label)}</span>"
        f"<span class=bdtrack><span class=bdfill style='width:{pts / cap * 100:.0f}%'></span></span>"
        f"<b>{pts:g}<i>/{cap}</i></b><span class=muted>{esc(why)}</span></div>"
        for label, pts, cap, why in [
            ("Must-have requirements", b["must"]["points"], 55,
             f"{b['must']['met']}/{b['must']['total']} met"),
            ("Nice-to-haves", b["nice"]["points"], 15,
             f"{b['nice']['met']}/{b['nice']['total']} met"),
            ("Level fit", b["level"]["points"], 20, b["level"]["why"]),
            ("Title match", b["title"]["points"], 10, b["title"]["why"]),
        ])
    notes = []
    if data.get("capped"):
        notes.append("Score capped at 55 — this posting asks for experience or a "
                     "qualification you do not have, so it is unlikely to pass screening "
                     "however well the rest matches.")
    if data.get("unknown"):
        notes.append(f"{data['unknown']} lines could not be judged automatically "
                     "(soft skills, culture fit) — left out of the maths entirely "
                     "rather than guessed at.")
    if data.get("weak_evidence"):
        notes.append(f"{data['weak_evidence']} matches rest on keywords you set rather than "
                     "evidence in your CV. Filling in your skills and CV would firm these up.")
    tail = "".join(f"<div class=note>{esc(n)}</div>" for n in notes)
    return card(f"<div class=bd>{rows}</div>{tail}", "bdcard")


# The source badge — SHARES both the glyph and the CSS class with the list in
# the Search tab, so one posting looks the same in both places.
#
# Derived from FOUND_BY rather than retyped: two glyph tables in two files
# agree right up until the day somebody edits one of them.
from .search import FOUND_BY

NGUON_DAU = {k: v[0] for k, v in FOUND_BY.items()}


def _mo_tin_goc(job: dict) -> str:
    """The link to the REAL POSTING. Without it this whole page is hearsay.

    Until now the detail page showed the score, every requirement, even the
    full description — and not one link to the original. A reader wanting to
    verify had to go and find it by hand, and verifying is something that
    MUST happen before applying: the stored description is a snapshot from
    scan time, and the real posting may have been edited or closed.

    A job posted in two places shows BOTH. They do not replace each other:
    the company board is where you apply directly, while LinkedIn has "who
    has applied", the applicant count, and who posted it.
    """
    links = job.get("links") or []
    if not links:
        return empty("This posting has no link — the older source did not "
                     "store the URL. A rescan will bring it back.")
    nut = "".join(
        # target=_blank: in a browser this opens a new tab; in the app window
        # the Delegate intercepts it and hands it to the default browser.
        # Without it, clicking an external link takes THE WHOLE APP WINDOW
        # away, with no Back button.
        # rel=noopener: the destination gets no handle on this window.
        f"<a class='jlink {esc(l['kind'])}' href='{esc(l['url'])}'"
        f" target='_blank' rel='noopener noreferrer'>"
        f"<i class='src {esc(l['kind'])}'>{NGUON_DAU.get(l['kind'], '◆')}"
        f"<b>{esc(l['name'])}</b></i>"
        f"<span class=jlinkhost>{esc(l['host'])}</span>"
        f"<span class=jlinkgo>↗</span></a>"
        for l in links)
    return card(f"<div class=jlinks>{nut}</div>", "jlinkcard")


def render_detail(job: dict, tu: str = "") -> str:
    reqs = "".join(
        f"<li class='{'met' if r['met'] else ('unk' if r['met'] is None else 'miss')}'>"
        f"<b>{esc(r['text'])}</b>"
        f"<span>{esc(r['evidence'])}</span></li>"
        for r in job["requirements"]
    )
    proj = job.get("project")
    return page(
        job["title"],
        f"<a class=back href='{esc(duong_ve(tu, '/search')[0])}'>"
        f"← {esc(duong_ve(tu, '/search')[1])}</a>"
        + h1(job["title"], f"{job['company']} · {job['location']} · {job['salary']}")
        + f"<div class=jmeta>{_score(job)}"
          f"<span class=spacer></span><span class=muted>{esc(job['posted'])}</span></div>"
        + "<h2>Mở tin gốc</h2>"
        + _mo_tin_goc(job)
        + "<h2>Why this score</h2>"
        + _breakdown(job)
        + (card(f"<ul class=reqs>{reqs}</ul>") if reqs
           else empty("Could not read any requirements from this posting. "
                      "Read it yourself — the system will not guess."))
        + "<h2>Tailored CV</h2>"
        + card(f"<a class=ghost href='/jobs/{esc(job['id'])}/cv"
               f"?tu={quote(tu or '/search', safe='')}'>"
               "Build a CV for this posting →</a>"
               "<div class=muted style='margin-top:6px'>Selects and orders lines from your "
               "own profile against what this posting asks for. Writes nothing new.</div>")
        + "<h2>Project write-up</h2>"
        + card(f"<a class=ghost href='/jobs/{esc(job['id'])}/project'>"
               "Build a one-page write-up for this posting →</a>"
               "<div class=muted style='margin-top:6px'>Five parts, 90 seconds to read. "
               "Uses the lines the CV builder cut out — that is where they belong.</div>")
        + "<h2>The posting</h2>"
        + card(f"<pre class=jd>{esc(job['jd'])}</pre>")
        # A REAL BUTTON, wired to the same route the list's Apply uses.
        #
        # This used to be two DRAWN buttons: "Queue for approval" and
        # "Reject…" — carrying no data-*, while every listener in live.js
        # binds on data-*, so clicking did nothing. They were left over from
        # an older design, when the detail page was meant to be the approval
        # gate. The real approval gate is now the Manage tab.
        #
        # Removing them outright would leave this page with nothing to do
        # after reading, forcing a trip back to the list to apply — so they
        # were replaced with a real button, not deleted.
        + f"<div class=actbar><button class='mbtn go' data-post='/api/apply'"
          f" data-arg='{esc(job['id'])}'>Apply to this</button>"
          "<span class=muted>Opens the application form in Chrome and adds a "
          "row to Manage. Nothing is sent — the Send button lives in "
          "Manage.</span></div>",
        active="/jobs",
    )
