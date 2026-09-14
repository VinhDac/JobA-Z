"""LinkedIn — PUBLIC job postings only, NEVER logged in.

The boundary, deliberate and not negotiable:

    YES  public posting pages, as a logged-out visitor, at a human pace
    NO   logging in with the user's account  -> that is the thing that can be
                                                lost, and losing it means
                                                losing a professional network
    NO   people pages, network graph, inbox  -> that is what LinkedIn sued
                                                Proxycurl over
    NO   arguing when blocked                -> blocked means stop, note it,
                                                move on

It runs on a separate Chrome profile, logged into nothing. With no account
there is no account to lose.

It uses the exact endpoint LinkedIn serves to logged-out visitors
(`/jobs-guest/jobs/api/seeMoreJobPostings/search`), 10 postings per page.

NOTE: this is still outside LinkedIn's Terms of Use (§8.2). Vin was told that
plainly and decided for himself. Recorded here so whoever reads this code
later knows.
"""

from __future__ import annotations

import random
import re
import time
import urllib.parse

from ...core.journal import SEARCH, log as jlog
from ..base import Posting, strip_html
from .base import Blocked, Health, grab, open_page

NAME = "linkedin"
GUEST = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
         "?keywords={q}&location={loc}&f_E={exp}&start={start}{tpr}")

# The time window, in seconds. MEASURED against the guest endpoint:
#
#   f_TPR=r86400   WORKS    — 10/10 returned postings were from the last 24h
#   sortBy=DD      ignored   — identical results to passing nothing
#   f_WT=2         ignored   — (measured the day before, same way)
#
# Each has to be tested rather than assumed: two of those three
# reasonable-looking parameters do nothing, while the endpoint still returns
# 200 so they look like they work.
NGAY = 86400
TUAN = 7 * NGAY
# The full description, still on the route LinkedIn serves to logged-out
# visitors.
GUEST_JOB = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
VIEW = "https://www.linkedin.com/jobs/view/{jid}/"
PER_PAGE = 10
# One journal line per this many deep-read postings. Not one per posting:
# 2,297 lines for a single scan makes the journal unreadable. None at all
# means 27 minutes of silence — measured on the 19:22 scan. 25 postings ≈ one
# line every 2 minutes.
NHIP_BAO = 25

# f_E: 1=internship 2=entry 3=associate 4=mid-senior
EXPERIENCE = {"intern": "1", "grad": "2", "grad_scheme": "2", "junior": "2,3",
              "mid": "3,4", "senior": "4", "lead": "4"}

# A much slower pace than the other sources. Not to evade anything — but
# because this is the one host we are a guest of, so tread lightly.
PAUSE = (2.5, 5.0)

# Three paces for the user to choose from. This module only KNOWS what a pace
# means at this endpoint; the caller decides which one — exactly like `worth`.
NHIP = {"nhe": (4.0, 7.0), "thuong": PAUSE, "nhanh": (1.2, 2.5)}

LIST_JS = """
(() => {
  try {
    const out = [];
    for (const li of document.querySelectorAll('li')) {
      const a = li.querySelector('a[href*="/jobs/view/"]');
      if (!a) continue;
      const pick = s => (li.querySelector(s) || {}).innerText || '';
      const t = li.querySelector('time');
      out.push({
        title: pick('h3').trim(),
        company: pick('a.hidden-nested-link').trim() || pick('h4').trim(),
        location: pick('[class*=location]').trim(),
        url: a.getAttribute('href').split('?')[0],
        posted: t ? (t.getAttribute('datetime') || t.innerText.trim()) : ''
      });
    }
    return JSON.stringify(out);
  } catch (e) { return "[]"; }
})()
"""

DETAIL_JS = """
(() => {
  try {
    const box = document.querySelector('[class*=show-more-less-html__markup]')
             || document.querySelector('[class*=description__text]')
             || document.querySelector('section[class*=description]');
    const crit = [...document.querySelectorAll('[class*=job-criteria__item]')]
        .map(e => e.innerText.replace(/\\s+/g, ' ').trim());
    return JSON.stringify([{
      // innerHTML, NOT innerText: innerText of <ul><li> returns bare lines
      // with the bullets gone — and the requirements extractor recognises a
      // list BY those bullets. strip_html() rebuilds '· ' from <li>.
      description: box ? box.innerHTML.slice(0, 60000) : '',
      criteria: crit.join(' | ').slice(0, 400)
    }]);
  } catch (e) { return "[]"; }
})()
"""

JOB_ID = re.compile(r"-(\d{6,})/?$")


def _pause(nhip: tuple[float, float] = PAUSE) -> None:
    time.sleep(random.uniform(*nhip))


def _from_row(row: dict) -> Posting | None:
    url = row.get("url") or ""
    found = JOB_ID.search(url)
    if not found or not row.get("title"):
        return None
    # A BUG THAT WAS FIXED: the href in search results points at a
    # country domain (uk.linkedin.com), and that domain redirects straight to
    # a signup page — so the deep-read pass only ever received "Sign Up |
    # LinkedIn". The URL is rebuilt from the id on www.
    jid = found.group(1)
    return Posting(
        source_id=jid,
        title=row["title"].strip(),
        company=(row.get("company") or "unknown").strip(),
        location=(row.get("location") or "").strip(),
        url=VIEW.format(jid=jid),
        posted_at=row.get("posted", ""),
        payload={"guest": True})


# The profile's markets -> places LinkedIn understands. The location used to
# be the hardcoded string "London" in a function signature that NOBODY passed
# — so the Markets field the user picked never reached anything.
MARKET_PLACE = {
    "uk_onsite": "United Kingdom",
    "uk_remote": "United Kingdom",
    "eu_remote": "European Union",
    "us_remote": "United States",
    "global_remote": "",            # empty = LinkedIn searches worldwide
    "relocate": "",
}


def places_for(markets: list[str], location: str = "") -> list[str]:
    """Which places to search. Profile order preserved, duplicates dropped.

    'United Kingdom' is wider than 'London' and contains it — take the wider
    place. Measured 12 Sep: of 290 kept jobs, 75 were in the UK outside
    London, and 71 of those 75 came from LinkedIn. Narrowing the query to
    exactly "London" loses those, because the boards do not cover them.

    With no market declared it searches WHERE YOU ARE, not a hardcoded
    "United Kingdom" in the source.
    """
    from ..filter import NOI, noi_o
    out: list[str] = []
    for m in markets or []:
        place = MARKET_PLACE.get(m)
        if place is not None and place not in out:
            out.append(place)
    if out:
        return out
    nha = noi_o(location)
    return [NOI[nha]["place"]] if nha else ["United Kingdom"]


# Job titles queried per pass. There is a CEILING, and hitting it is WRITTEN
# to the journal — not a silent cut like the old `titles[:5]`.
MAX_QUERIES = 20


def signed_in(tab) -> bool:
    """Is this profile logged into LinkedIn.

    `li_at` is LinkedIn's session cookie. JS cannot see it (httpOnly), so the
    browser is asked directly over CDP.
    """
    try:
        got = tab.call("Network.getCookies",
                       {"urls": ["https://www.linkedin.com/"]})
    except Exception:                                # noqa: BLE001
        return False
    return any(c.get("name") == "li_at" for c in got.get("cookies", []))


def read_deep(tab, items: list[Posting], skip: frozenset[str] = frozenset(),
              worth=None, pace: str = "thuong", stop=None,
              ten: str = NAME) -> Health:
    """Open each posting for its DESCRIPTION. Split from fetch() because it
    is A SEPARATE JOB.

    `ten` is the name of the SOURCE being read, used only for the journal.
    The page is still a LinkedIn page, but where the posting came from is a
    different matter: deep-reading 106 alert postings while the journal says
    "linkedin: 106 postings" makes the user think the LinkedIn scan is
    running when they have just switched it off.

    The three kinds of scan need three different jobs, and before the split
    all three had to go through the 30-minute search:

        first run  full search  -> deep read
        update     new only     -> deep read
        continue   (no search at all) -> finish what is left

    The third is why it had to be split. "Continue" that still runs the
    search is just another word for "scan again from the top" — re-finding
    the same 2,296 postings over 30 minutes in order to deep-read 11.

    It edits `items` in place (assigning description to each Posting) and
    returns the health.
    """
    nhip = NHIP.get(pace, PAUSE)
    fresh = [i for i in items if i.source_id not in skip]

    # FILTER BEFORE DEEP-READING. This is the most expensive part of the
    # whole scan — one page open per posting plus 2.5-5 seconds of pause —
    # and 89% of the postings opened are dropped by the filter immediately
    # afterwards. Measured on the real store: 2,389 LinkedIn postings, only
    # 257 through the filter, which is more than two hours per scan thrown
    # away.
    #
    # It can be filtered first because `judge()` only touches the TITLE,
    # COMPANY and LOCATION — the three things the list page already gives. It
    # does not need the description, and the description is the only thing
    # that requires opening a page.
    #
    # It takes a FUNCTION rather than the profile: this module fetches
    # postings and must know nothing about profiles or filter rules. The
    # caller decides.
    #
    # Skipped postings are STILL returned and still saved — which keeps the
    # "Dropped" pile intact, and leaves the Keep button something to keep.
    if worth is not None and fresh:
        truoc = len(fresh)
        fresh = [i for i in fresh if worth(i)]
        if truoc != len(fresh):
            jlog.emit(SEARCH,
                      f"filtered before deep-reading: {truoc} -> {len(fresh)}"
                      f" · skipped {truoc - len(fresh)} the filter would drop")

    health = Health(attempted=len(fresh), failed=0)
    jlog.emit(SEARCH, f"{ten}: {len(items)} postings in hand"
                      + (f", {len(items) - len(fresh)} already read"
                         f" -> deep-reading only {len(fresh)}" if skip else
                         f", deep-reading all {len(fresh)}"))
    for index, item in enumerate(fresh):
        # The REAL break point: this loop costs 8-16 minutes opening Chrome
        # per posting. Check the stop flag outside this loop and pressing Stop
        # still means waiting for the whole thing.
        if stop and stop():
            jlog.warn(SEARCH, f"stopped on request — deep-read {index}/{len(fresh)}")
            break
        # Where the scan sits longest — 2.5-5 seconds of pause per posting.
        # Without progress here the screen is silent throughout.
        #
        # Write THE POSTING'S NAME onto the bar, not just "deep-reading
        # LinkedIn": the user has to see what the machine is opening to know
        # it is still alive.
        jlog.progress(SEARCH, f"deep-read · {item.title[:44]} — {item.company[:22]}",
                      index + 1, len(fresh))
        if index and index % NHIP_BAO == 0:
            con = jlog.remaining(SEARCH)
            jlog.emit(SEARCH, f"deep-read {index}/{len(fresh)}"
                              f"{f' · {con} left' if con else ''}"
                              f" · reading: {item.title[:40]}")
        try:
            open_page(tab, GUEST_JOB.format(jid=item.source_id), timeout=30)
            detail = grab(tab, DETAIL_JS)
            raw = detail[0].get("description", "") if detail else ""
            if len(raw) < 200:            # page opened but no description = failed
                health.failed += 1
                health.note(f"{item.source_id}: empty description")
            else:
                item.raw_body = raw[:60000]
                item.description = strip_html(raw)[:20000]
                item.payload["criteria"] = detail[0].get("criteria", "")
        except Blocked:
            # Stop outright, do not argue — but it has to SAY it stopped,
            # and the postings left unread count as failures. Just note() and
            # break leaves failed=0 and this scan looks identical to a
            # successful one.
            health.block(f"blocked at posting {index + 1}/{len(fresh)}",
                         unread=len(fresh) - index)
            break
        except Exception as exc:           # noqa: BLE001
            health.failed += 1
            health.note(f"{type(exc).__name__}: {str(exc)[:44]}")
        _pause(nhip)
    return health


def fetch(tab, queries: list[str], location: str = "United Kingdom",
          levels: list[str] | None = None, pages: int = 3,
          deep: bool = True, skip: frozenset[str] = frozenset(),
          worth=None, pace: str = "thuong", recent: int = 0,
          covered: frozenset[str] = frozenset(), done_out=None,
          stop=None) -> list[Posting]:
    """Search, then deep-read LinkedIn postings.

    skip = the ids of postings that ALREADY have a description. The deep-read
    pass skips them.

    This is the most important fix in the whole of step 1: the deep-read pass
    used to reopen EVERY posting found, every hour. On the real machine 194
    of 196 already had a description, so 97% of the time was re-reading what
    had been read — 8-16 minutes of continuous Chrome every hour, ~4,600
    calls per day, and LinkedIn throttling 40-82% of them.
    """
    # The constraint at the top of this file — "with no account there is no
    # account to lose" — is now guarded BY THE MACHINE rather than by
    # memory. It happened once: the scan window and the apply window look
    # identical, and logging into the wrong one means every scan runs under
    # the real account.
    if signed_in(tab):
        raise Blocked(
            "the SCAN profile is logged into LinkedIn — scanning under a real "
            "account is how accounts are lost. Log out in the scan window; log "
            "in only in the APPLY window.")

    if len(queries) > MAX_QUERIES:
        jlog.warn(SEARCH, f"searching only {MAX_QUERIES}/{len(queries)} titles"
                          f" — dropped: {', '.join(queries[MAX_QUERIES:])}")
        queries = queries[:MAX_QUERIES]
    nhip = NHIP.get(pace, PAUSE)
    exp = ",".join(sorted({e for lv in (levels or ["grad", "junior"])
                           for e in EXPERIENCE.get(lv, "2").split(",")}))
    found: dict[str, Posting] = {}
    dut = ""                  # why it was cut short; empty = ran to the end

    # Pair up (title, place) in advance and run ONE loop — nesting two loops
    # indents the body one more level and skews the whole file.
    places = location if isinstance(location, list) else [location]
    pairs = [(q, p) for q in queries for p in places]

    for step, (query, place) in enumerate(pairs, 1):
        if stop and stop():
            jlog.warn(SEARCH, f"stopped on request — {step - 1}/{len(pairs)} queries done")
            break
        # An empty `place` means LinkedIn searches worldwide. Left as is the
        # screen shows "Operations Analyst · " — a dangling separator that
        # reads as truncated text.
        o_dau = place or "worldwide"
        # HAS THIS PAIR EVER BEEN ASKED FULLY. If not, ask fully; if so, ask
        # only for what is new. Both run in the SAME pass, so adding a title
        # does not force a full rescan of the grid — only the new pairs are
        # scanned fully.
        khoa = f"{query}|{place}"
        cua_so = 0 if khoa not in covered else recent
        jlog.progress(SEARCH, f"searching LinkedIn · {query} · {o_dau}"
                              + ("" if cua_so else " · full scan"),
                      step, len(pairs))
        truoc, so_trang = len(found), 0
        try:
            for page in range(pages):
                url = GUEST.format(q=urllib.parse.quote(query),
                                   loc=urllib.parse.quote(place),
                                   exp=urllib.parse.quote(exp), start=page * PER_PAGE,
                                   tpr=f"&f_TPR=r{cua_so}" if cua_so else "")
                open_page(tab, url, timeout=30)
                rows = grab(tab, LIST_JS)
                if not rows:
                    break
                so_trang += 1
                for row in rows:
                    item = _from_row(row)
                    if item:
                        found.setdefault(item.source_id, item)
                _pause(nhip)
        except Exception as exc:                     # noqa: BLE001
            # CUT SHORT MEANS KEEP WHAT WAS FOUND, not raise upward.
            #
            # An error here used to fly straight out of fetch(), so `items`
            # was never returned and save_batch() never ran: every posting
            # found was thrown away. It really happened at 17:18 — 48 of 76
            # queries done, one ConnectionResetError, fetched=0.
            #
            # A machine waking from sleep produces exactly this error: a dead
            # CDP socket, and with the app running 24/7 that is an everyday
            # event, not an accident.
            dut = f"{type(exc).__name__}: {str(exc)[:50]}"
            jlog.warn(SEARCH, f"cut off at query {step}/{len(pairs)} ({dut})"
                              f" — keeping the {len(found)} postings found")
            break
        # ONE LINE PER QUERY. This loop used to be silent: measured on the
        # 19:22 scan, 31 minutes of running left exactly one journal line at
        # the start. The user watched a progress bar inch along with no idea
        # which title the machine was typing, where, or what it found.
        # This pair was just asked FULLY and ran to the end -> record it as
        # covered. Only when cua_so == 0: a 24-hour-window query covers
        # nothing, it only glances at the newest slice.
        if done_out is not None and not cua_so:
            done_out.add(khoa)
        con = jlog.remaining(SEARCH)
        jlog.emit(SEARCH,
                  f"search · {query} · {o_dau} — {len(found) - truoc} new"
                  f" / {so_trang} pages · store {len(found)}"
                  f"{'' if cua_so else ' · covered'}"
                  f"{f' · {con} left' if con else ''}")

    if not deep or dut:
        # Once cut off, do not deep-read: the endpoint just refused us, and
        # opening 2,000 more pages only collects 2,000 more errors. Return the
        # postings for save_batch to write down and deep-read on the next scan
        # — save_batch patches the description into the existing row, so the
        # unfinished part does not become a hole.
        suc = Health(0, 0)
        if dut:
            suc.broke(f"cut off while searching: {dut}")
        return list(found.values()), suc

    health = read_deep(tab, list(found.values()), skip=skip, worth=worth,
                       pace=pace, stop=stop)
    return list(found.values()), health

