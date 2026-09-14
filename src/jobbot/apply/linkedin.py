"""Extract the REAL application link out of a LinkedIn posting. NEEDS A LOGIN.

Kept separate from `ingest/web/linkedin.py` deliberately: that file promises
in its first line that it never logs in, and that promise still holds — the
scan runs on the guest endpoint, with no account to lose. THIS file only runs
when Vin presses Apply on one posting, in the apply browser, reading EXACTLY
one page. Two different boundaries, two files.

Measured (the guest page against the logged-in page, same posting):

    guest        0 apply elements in 262 KB, only "sign in to apply"
    logged in    <a>Apply</a> -> linkedin.com/safety/go/?url=<company URL>

So 111 LinkedIn postings are not a dead end — just a door locked by a login.

LinkedIn encodes even the dots as %2E inside the `url` parameter, so it has
to be decoded rather than sliced by hand.
"""

from __future__ import annotations

import re
import urllib.parse

# The apply button on the logged-in page. LinkedIn's CSS classes are hashes
# and change constantly — anchor on the TEXT and on the path instead, both of
# which are far more stable.
FIND_JS = r"""
(() => {
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const text = (a.innerText || '').trim();
    const href = a.href || '';
    if (!/^apply\b/i.test(text) && !/\/safety\/go\?|\/safety\/go\//.test(href)) continue;
    out.push(href);
  }
  return JSON.stringify(out.slice(0, 6));
})()
"""

SAFETY = re.compile(r"linkedin\.com/safety/go", re.I)
JOBS = re.compile(r"linkedin\.com/(jobs|job)/", re.I)


def unwrap(href: str) -> str:
    """'linkedin.com/safety/go/?url=https%3A%2F%2Fcompany…' -> the company URL."""
    if not href:
        return ""
    if not SAFETY.search(href):
        # ONLY http/https. LinkedIn's Apply button is very often
        # <a href="javascript:void(0)"> opening a dialog; returning that
        # as-is sends tab.go() to a non-web scheme.
        low = href.lower()
        if "linkedin.com" in low or not low.startswith(("http://", "https://")):
            return ""
        return href
    query = urllib.parse.urlparse(href).query
    found = urllib.parse.parse_qs(query).get("url") or []
    out = urllib.parse.unquote(found[0]) if found else ""
    return out if out.lower().startswith(("http://", "https://")) else ""


def apply_url(tab) -> str:
    """The real application link of the open posting. Empty if not found."""
    import json
    try:
        found = json.loads(tab.eval(FIND_JS) or "[]")
    except Exception:                                # noqa: BLE001
        return ""
    for href in found:
        out = unwrap(href)
        if out and not JOBS.search(out):
            return out
    return ""
