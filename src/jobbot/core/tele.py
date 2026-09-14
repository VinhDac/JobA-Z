"""Telegram — notifications to your phone, and remote commands back.

The machine sits at home 24/7. Operating-system notifications (notify.py)
appear on that same machine, which makes them useless for a 24/7 station:
nobody is standing there looking at it.

WHY TELEGRAM, and not something else:

  · The Bot API is HTTPS + JSON, so the stdlib's `urllib.request` is enough.
    No package to install — the app's no-dependency rule holds.
  · `getUpdates` is LONG POLLING: the machine at home only calls OUT. No
    router port to open, no static IP, no ngrok. Every alternative (webhook,
    a public server) requires opening a way INTO the user's home.

REJECTED, and why:
  · Gmail sending mail to itself — the mailbox is locked READ ONLY by four
    constraints in code (track/mail.py). Being able to send breaks that
    lock. Trading a small convenience for the app's biggest safety boundary:
    not worth it.
  · APNs push — needs a paid Apple Developer account.

THREE SAFETY GUARDS, all three of them HARD:

  1. ANYONE CAN MESSAGE A TELEGRAM BOT. Knowing the bot's name is enough. So
     every incoming message goes through `duoc_phep()`: a wrong chat_id is
     dropped and logged. Without this guard a stranger reads the whole job
     search and can start and stop the machine at home.
  2. THE TOKEN IS A SECRET — it lives in config/config.toml (chmod 600,
     gitignored). Never in the DB, never in the journal, never in HTML.
  3. THE "THE MACHINE DOES NOT PRESS SEND" BOUNDARY SURVIVES TELEGRAM. There
     is no remote apply command, at any control level. The Send click stays
     the user's, in front of the form.

NEVER RAISE OUT. The functions here run on background threads; an escaping
exception kills the 24/7 loop and the app silently stops working.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

# A HARD LOCK FOR TEST RUNS.
#
# This is not paranoia. The test suite reads the REAL config/config.toml (it
# was only guarded on WRITES, not on READS), so from the moment Vin connected
# his bot, EVERY test run sent real messages to his phone — including a fake
# "⚠️ Session failed" alarm a test had constructed. A test suite that
# bothers the real user is a broken test suite.
#
# The guard sits HERE, at the lowest layer and the only one that touches the
# network: every send and receive goes through goi(), so there is no way
# around it.
import os

OFFLINE = "JOBBOT_OFFLINE"


def khoa_mang() -> bool:
    return os.environ.get(OFFLINE, "") == "1"


API = "https://api.telegram.org"
MUC = "telegram"                 # the section name in config.toml

# Maximum wait per long-poll. 25 seconds: long enough not to hammer the API,
# short enough to stay under every proxy timeout on the way (usually 30-60).
CHO = 25
HET_GIO = CHO + 10


# --- CONFIGURATION --------------------------------------------------------

def cau_hinh() -> dict:
    """{token, chat_id} from config.toml. Unreadable means empty, never raise.

    Under test it reports NOT CONNECTED regardless of what is on disk: a test
    has to run in a world with nobody's secrets in it.
    """
    if khoa_mang():
        return {}
    try:
        from . import config
        return config.section(MUC) or {}
    except Exception:                       # noqa: BLE001
        return {}


def da_noi() -> bool:
    c = cau_hinh()
    return bool(str(c.get("token", "")).strip()
                and str(c.get("chat_id", "")).strip())


def che(token: str) -> str:
    """The token as shown to a person — the tail only. Used on Settings.

    Never print the whole token: in HTML it is readable through View Source
    and gets cached by the browser.
    """
    t = str(token or "").strip()
    return f"…{t[-4:]}" if len(t) > 4 else ("saved" if t else "")


# --- SENDING --------------------------------------------------------------

def goi(duong: str, tham: dict, giay: int = 12) -> tuple:
    """One API call -> (data, WHY IT FAILED).

    It returns the reason, not just None: the Test button exists to say WHERE
    it broke, and swallowing the reason leaves it able to say only "could not
    send" — the exact sentence the user already knew.

    The reason is turned into human words right here, because this is the
    only place that knows what a Telegram error code means: 401 is a bad
    token, 400 + "chat not found" is a bad chat id. Making the caller guess
    from a number is making them learn the API.
    """
    # LOCAL CHECKS FIRST, THE NETWORK LOCK SECOND. When both apply, the more
    # specific reason has to win: "no token pasted yet" names the thing to
    # do, while "running under test" helps nobody who is configuring.
    c = cau_hinh()
    token = str(c.get("token", "")).strip()
    if not token:
        return None, "no token yet — get one from @BotFather on Telegram"
    if khoa_mang():
        return None, "running under test — every outbound call is blocked"
    url = f"{API}/bot{token}/{duong}"
    data = urllib.parse.urlencode(
        {k: v for k, v in tham.items() if v is not None}).encode()
    try:
        req = urllib.request.Request(url, data=data,
                                     headers={"User-Agent": "jobbot"})
        with urllib.request.urlopen(req, timeout=giay) as r:
            return json.loads(r.read().decode("utf-8", "replace")), ""
    except urllib.error.HTTPError as e:
        than = ""
        try:
            than = json.loads(e.read().decode("utf-8", "replace")).get(
                "description", "")
        except Exception:                   # noqa: BLE001
            pass
        if e.code == 401:
            return None, "wrong or revoked token — make a new one at @BotFather"
        if e.code in (400, 403) and "chat" in than.lower():
            return None, ("wrong chat id, or you have not messaged the bot "
                          "yet. Send it a message, then press Save.")
        return None, f"Telegram returned error {e.code}" + (f" — {than[:70]}" if than else "")
    except urllib.error.URLError as e:
        return None, f"could not reach the network — {str(getattr(e, 'reason', e))[:60]}"
    except Exception as e:                  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:60]}"


def _goi(duong: str, tham: dict, giay: int = 12) -> dict | None:
    """The error-swallowing variant, for background callers where nobody
    reads the reason."""
    return goi(duong, tham, giay)[0]


def gui_chi_tiet(text: str) -> tuple:
    """Send, and return (did it work, WHY NOT). Used by the Test button."""
    c = cau_hinh()
    chat = str(c.get("chat_id", "")).strip()
    if not chat:
        return False, ("no chat id yet — message the bot once, then press "
                       "Save")
    ra, loi = goi("sendMessage", {"chat_id": chat, "text": str(text)[:4000],
                                  "parse_mode": "HTML",
                                  "disable_web_page_preview": "true"})
    if ra and ra.get("ok"):
        return True, ""
    return False, loi or str((ra or {}).get("description", ""))[:80] or "reason unknown"


def gui(text: str) -> bool:
    """Send one message to the pinned chat. False if not connected or broken.

    HTML rather than Markdown: company names often contain _ and * (for
    example "Susquehanna_UK"), and Telegram's Markdown reads those as
    formatting and returns a 400 for the whole message. HTML only needs three
    characters escaped.
    """
    c = cau_hinh()
    chat = str(c.get("chat_id", "")).strip()
    if not chat or not str(text or "").strip():
        return False
    ra = _goi("sendMessage", {"chat_id": chat, "text": text[:4000],
                              "parse_mode": "HTML",
                              "disable_web_page_preview": "true"})
    return bool(ra and ra.get("ok"))


def thoat(text) -> str:
    """The three HTML characters that must be escaped. Real company names
    contain all three."""
    return (str(text or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


# --- RECEIVING COMMANDS ---------------------------------------------------
#
# THREE CONTROL LEVELS. The user picks one under Settings · Notifications,
# and each level is a different attack surface — so the level has to be a
# checkable value, not a promise in the documentation.
TAT, XEM, DAY_DU = "tat", "xem", "day_du"

MUC_DIEU_KHIEN = {
    TAT: ("Notifications only, one way",
          "The bot only sends. It accepts no commands at all. No attack "
          "surface. The trade: if you are out and a session fails, you "
          "cannot fix it until you get home."),
    XEM: ("View, and start/stop the session",
          "Adds three harmless commands: /trangthai, /batphien, /tatphien. "
          "None of them touches the CV, the profile, or applying."),
    DAY_DU: ("Also approve mail remotely",
             "As above, plus /thu · /nhan <n> · /boqua <n> to approve the "
             "mail the machine proposes a status change for. Remote commands "
             "start WRITING to the table."),
}

# Which commands belong to which level. There is NO apply command at any
# level — see guard 3 at the top of this file.
LENH_XEM = ("trangthai", "batphien", "tatphien", "giupdo", "start")
LENH_GHI = ("thu", "nhan", "boqua")


def duoc_phep(tin: dict, chat_id: str) -> bool:
    """THE HARD GUARD: is this message really from the pinned chat.

    It is the only fence between the machine at home and anyone who knows the
    bot's name. So it is its own pure function with its own tests — not an
    `if` buried inside a loop.
    """
    if not chat_id:
        return False
    ai = ((tin or {}).get("message") or {}).get("chat") or {}
    return str(ai.get("id", "")) == str(chat_id).strip()


def doc_lenh(tin: dict) -> tuple:
    """(command, argument) from an update. Not a command -> ('', '').

    Accepts "/trangthai@bot_name" too — Telegram appends that in groups.
    """
    chu = str(((tin or {}).get("message") or {}).get("text", "")).strip()
    if not chu.startswith("/"):
        return "", ""
    dau, _, sau = chu[1:].partition(" ")
    return dau.split("@")[0].lower(), sau.strip()


def cho_phep_lenh(lenh: str, muc: str) -> bool:
    """Does this control level allow this command."""
    if muc == TAT or not lenh:
        return False
    if lenh in LENH_XEM:
        return True
    return muc == DAY_DU and lenh in LENH_GHI


def nhan(offset: int) -> tuple:
    """One long-poll. Returns (updates, next offset, error).

    A network failure returns ([], the old offset, why) — the outer loop
    sleeps and retries, and nobody has to handle an exception.
    """
    ra, loi = goi("getUpdates",
                  {"offset": offset, "timeout": CHO,
                   "allowed_updates": json.dumps(["message"])}, giay=HET_GIO)
    if loi or not ra or not ra.get("ok"):
        # RETURN THE REASON TOO. Without it the listener cannot tell "waited
        # 25 seconds and nobody messaged" (normal) from "401 token" (broken)
        # — and a 401 answers instantly, so the loop spins calling Telegram
        # without pause, without a single journal line.
        return [], offset, (loi or "Telegram did not return ok")
    ds = ra.get("result") or []
    if not ds:
        return [], offset, ""
    return ds, max(int(u.get("update_id", 0)) for u in ds) + 1, ""
