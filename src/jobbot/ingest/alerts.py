"""Jobs from LinkedIn's ALERT MAIL — the third source, and the cleanest.

LinkedIn sends job alerts into Vin's own mailbox. Reading your own mailbox
touches nobody's Terms — quite unlike the Chrome scan, which sits outside
§8.2 and which the app states plainly in `ingest/web/linkedin.py`.

Three strengths, measured on the real mailbox on 12 Sep:

    CLEAN  mail sent to you, no scraping, no pretending to be a browser
    FAST   LinkedIn sends within hours of a posting going up; the Chrome
           scan takes half an hour to work through 80 queries
    CHEAP  381 alert mails, ~6 jobs each, filtered on the IMAP server itself
           — seconds, no Chrome, no cool-downs

The weakness, stated up front: alert mail carries NO job description. It
gives the title, company, location and id — enough to filter, not enough to
score. The description still has to come from the deep-read pass opening each
page.

THE MAIL STRUCTURE. Each job is an <a> to /jobs/view/<id>, and right after it:

    line 1   the title
    line 2   company · location
    line 3   a label ("Fast growing", "Actively recruiting") — dropped

A job appears THREE times in the mail (logo, title, button) but carries text
only once. So group by id and take the first block with both lines.
"""

from __future__ import annotations

import html as _html
import re

from .base import Posting

NAME = "alert"

# The alert sender. Typed out because this is LinkedIn's fixed address —
# guessing with a general pattern ("*-noreply@") also catches rejections.
SENDER = "jobalerts-noreply@linkedin.com"

# The <a> pointing at a posting. The URL in the mail is a long tracking link
# (/comm/jobs/view/...?trk=...), so only the ID is captured and a clean URL
# rebuilt — exactly what `linkedin._from_row` already has to do with tracked
# hrefs.
JOB_LINK = re.compile(r'<a\b[^>]*href="[^"]*?/jobs/view/(\d{6,})[^"]*"[^>]*>')
VIEW = "https://www.linkedin.com/jobs/view/{jid}/"

MOC = "\x01"          # a character never present in mail, used as a cut marker


def parse(html: str) -> list[Posting]:
    """One alert mail's HTML body -> a list of postings.

    Tags are replaced with NEWLINES, not spaces: the title and the company
    name sit in two adjacent elements with nothing between them. Joining with
    a space gives "Data Analyst, Business Intelligence — Entry Level
    Jobright.ai", with no way to split it again.
    """
    if not html:
        return []
    text = JOB_LINK.sub(MOC + r"\1" + MOC, html)
    text = _html.unescape(re.sub(r"<[^>]+>", "\n", text))

    phan = text.split(MOC)
    thay: dict[str, Posting] = {}
    for i in range(1, len(phan) - 1, 2):
        jid, sau = phan[i], phan[i + 1]
        if not jid.isdigit() or jid in thay:
            continue
        dong = [d.strip() for d in sau.split("\n") if d.strip()][:2]
        if len(dong) < 2 or " · " not in dong[1]:
            continue                      # a logo/button block — carries no text
        cong_ty, _, noi = dong[1].partition(" · ")
        thay[jid] = Posting(
            source_id=jid, title=dong[0][:200],
            company=(cong_ty.strip() or "unknown")[:120],
            location=noi.strip()[:120],
            url=VIEW.format(jid=jid),
            payload={"alert": True})
    return list(thay.values())


def fetch(address: str, password: str, since_days: int = 30,
          limit: int = 200) -> list[Posting]:
    """Every job in the alert mail of the last `since_days` days.

    Deduplicated by id: the same job appearing in several alerts is normal,
    LinkedIn keeps re-sending until you click it.
    """
    from ..track import mail
    thu = mail.fetch(address, password, since_days=since_days, limit=limit,
                     sender=SENDER, want_html=True)
    thay: dict[str, Posting] = {}
    for msg in thu:
        for item in parse(msg.get("html") or ""):
            # NEWER mail overwrites older: fetch returns in mailbox order,
            # so a later message is newer, and so is the posting in it.
            thay[item.source_id] = item
    return list(thay.values())
