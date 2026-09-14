"""The approval screen after a CV is uploaded.

It PROPOSES, it does not write. Each item has its own checkbox, ticked by
default only where the profile field is currently empty.
"""

from __future__ import annotations

from html import escape as esc

from ...profile.import_cv import Proposal
from ..layout import badge, card, empty, h1, page
from ...profile.schema import all_questions


def render_form(error: str = "") -> str:
    warn = f"<div class=\'gate block\'>{esc(error)}</div>" if error else ""
    return page(
        "Import CV",
        h1("Import a CV", "PDF, DOCX or plain text. Nothing is saved until you approve "
                          "each field on the next screen.")
        + warn
        + card(
            "<form method=post action=\'/profile/import\' enctype=\'multipart/form-data\'>"
            "<div class=frow><input class=search type=file name=file "
            "accept=\'.pdf,.docx,.txt,.md\'>"
            "<button class=primary type=submit>Read it</button></div>"
            "<div class=note>Or paste the text instead:</div>"
            "<textarea class=txt name=pasted rows=7 "
            "placeholder=\'Paste your CV here…\'></textarea>"
            "</form>")
        + card("<b>What happens next</b><div class=muted>The system pulls out name, "
               "contact, education, certifications and skills, then shows each one for "
               "you to approve. Fields you have already filled in are never overwritten."
               "</div>", "notice"),
        active="/profile")


def render_review(proposals: list[Proposal], text: str) -> str:
    if not proposals:
        return page("Import CV",
                    h1("Nothing new found")
                    + empty("Everything this CV mentions is already on your profile."),
                    active="/profile")

    def _doc_duoc(p: Proposal) -> str:
        """The value shown to a PERSON, not to the machine.

        Multi-select answers are stored as codes (`uk_onsite`). Showing the
        raw code on the approval screen means the user does not know what
        they are agreeing to — it has to be turned back into the exact label
        they will see in the profile form.
        """
        if not isinstance(p.value, list):
            return p.value
        q = all_questions().get(p.field)
        nhan = {o.value: o.label for o in (q.options or [])} if q else {}
        return " · ".join(nhan.get(v, v) for v in p.value)

    rows = ""
    for p in proposals:
        val = _doc_duoc(p)
        rows += (
            f"<label class=\'qrow safe\'>"
            f"<input type=checkbox name=accept value=\'{esc(p.field)}\' checked>"
            f"<span class=qbody><span class=qhead>{badge(p.label, 'ok')}"
            f"<b>{esc(p.field)}</b></span>"
            f"<span class=pval>{esc(val[:600])}"
            f"{'…' if len(val) > 600 else ''}</span>"
            + (f"<span class=risk>{esc(p.note)}</span>" if p.note else "")
            + "</span></label>")

    return page(
        "Import CV",
        h1("Approve what goes in",
           f"{len(proposals)} field(s) found. Untick anything you do not want.")
        + f"<form method=post action=\'/profile/import/save\'>"
        + f"<input type=hidden name=text value=\'{esc(text)}\'>"
        + f"<div class=qlist>{rows}</div>"
        + "<div class=actbar><button class=primary type=submit>Save selected</button>"
          "<a class=skip href=\'/profile\'>Cancel</a></div></form>",
        active="/profile")
