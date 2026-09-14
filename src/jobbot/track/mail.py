"""Read the job mailbox over IMAP — READ ONLY, with the constraints in code.

Why a SEPARATE mailbox rather than the main one: a Google app password is a
FULL-ACCESS key — read, send, delete, the whole mailbox, forever until
revoked. Google offers no read-only variant and no date limit. That key sits
in plain text in config.toml. Putting it on the main mailbox is putting it in
the wrong place; putting it on a mailbox that holds nothing but job
rejections costs nothing if it leaks.

FOUR CONSTRAINTS, written as code rather than as promises:

    1. SELECT only with readonly=True — mail is never marked as read
    2. NO function sends, deletes or changes a flag. What does not exist
       cannot be called by mistake.
    3. only mail from the last SINCE_DAYS days
    4. only the SUBJECT and the first few lines — no full body, no attachments

See tests/test_track.py: one test per constraint.
"""

from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header

# ------------------------------------------------------------- the mail host
#
# GMAIL IS THE DEFAULT, NOT THE RULE. The old version hardcoded `HOST =
# "imap.gmail.com"` and came with a filter accepting only Google app
# passwords (16 lowercase letters). Anyone on Outlook, iCloud, Fastmail or a
# company mailbox COULD NOT use the mail stage at all — and the refusal they
# got was "that is not an app password", a sentence with nothing to do with
# the real reason.
#
# Three layers, in that order:
#   1. `host` under [mail] in config.toml — whatever the user says goes
#   2. the address's domain, looked up in the table below
#   3. `imap.<domain>` — the common convention, and when it fails the error
#      points at exactly what to fix
MAC_DINH_HOST = "imap.gmail.com"
PORT = 993

NHA_CUNG_CAP = {
    "gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com", "hotmail.com": "outlook.office365.com",
    "hotmail.co.uk": "outlook.office365.com", "live.com": "outlook.office365.com",
    "live.co.uk": "outlook.office365.com", "msn.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com", "yahoo.co.uk": "imap.mail.yahoo.com",
    "ymail.com": "imap.mail.yahoo.com",
    "icloud.com": "imap.mail.me.com", "me.com": "imap.mail.me.com",
    "mac.com": "imap.mail.me.com",
    "fastmail.com": "imap.fastmail.com", "fastmail.fm": "imap.fastmail.com",
    "zoho.com": "imap.zoho.com", "zohomail.com": "imap.zoho.com",
    "aol.com": "imap.aol.com",
    "gmx.com": "imap.gmx.com", "gmx.net": "imap.gmx.net", "gmx.de": "imap.gmx.net",
    "yandex.com": "imap.yandex.com", "yandex.ru": "imap.yandex.ru",
    "mail.com": "imap.mail.com", "hey.com": "imap.hey.com",
}

# Proton does NOT speak IMAP over the internet — it goes through Proton Mail
# Bridge running on this machine, port 1143, and that port is NOT SSL.
# Guessing a host for them leaves them waiting on a meaningless network
# error; saying so plainly tells them what to do.
CAN_CAU = {"proton.me", "protonmail.com", "protonmail.ch", "pm.me"}


def ten_mien(address: str) -> str:
    return address.strip().rpartition("@")[2].lower()


def may_chu(address: str = "") -> str:
    """The IMAP host for this address. Empty = the user has to be asked (see
    CAN_CAU)."""
    from ..core.config import section
    cfg = section("mail")
    khai = str(cfg.get("host") or "").strip()
    if khai:
        return khai
    mien = ten_mien(address or str(cfg.get("address") or ""))
    if not mien:
        return MAC_DINH_HOST
    if mien in CAN_CAU:
        return ""
    return NHA_CUNG_CAP.get(mien) or f"imap.{mien}"


def cong() -> int:
    """The IMAP port. Changeable so it can reach a Bridge or a company host."""
    from ..core.config import section
    try:
        return int(str(section("mail").get("port") or PORT))
    except (TypeError, ValueError):
        return PORT


def _chi_cach(mien: str) -> str:
    """The directions when the host cannot be guessed — it has to SAY where
    to fix it."""
    return (f"the mail host for «{mien}» is unknown. Open "
            "config/config.toml, section [mail], and add:\n"
            '  host = "imap.ten-nha-cung-cap.com"')

# A TIMEOUT ON EVERY IMAP CALL.
#
# Without one the socket waits FOREVER. The consequence is not "slow": the
# mail stage runs inside the background loop and HOLDS the scheduler's lock
# (`_gate`), so one hang means the station stands still permanently — the
# screen still says "running", no later loop can run, and nothing says so.
# The worst kind of silent failure.
#
# 30 seconds: Gmail answers in a second or two on a normal network; past 30
# it is broken rather than slow. On a flaky network the next loop retries.
HET_GIO = 30
SINCE_DAYS = 30
# A HARD CEILING, so a large mailbox cannot hang the scan. 400 was far too
# low and it CUT SILENTLY: the real mailbox holds 1,041 messages over 60
# days, and taking the newest 400 reads only 19 days — the other 41 days
# never arrive, and the interview invitation is in them. The user pressed
# "scan 60 days" and got 19.
#
# The expensive part is the fetch, not this number: 0.27 seconds per mail.
MAX_MESSAGES = 3000
SNIPPET = 400               # characters taken from the body

# A Google app password: exactly 16 lowercase letters. Google displays it in
# groups of 4 with spaces for easy copying, so spaces are stripped first.
APP_PASSWORD = re.compile(r"[a-z]{16}")


class MailError(RuntimeError):
    pass


def account() -> tuple[str, str]:
    """(address, app password) from config.toml. Empty when unset."""
    from ..core.config import section
    cfg = section("mail")          # NOT named `box` — `box` is the IMAP mailbox
    return (str(cfg.get("address") or "").strip(),
            str(cfg.get("password") or "").strip())


def check(address: str, password: str) -> str:
    """Log in once and leave. Empty = fine, non-empty = why it failed.

    It exists because otherwise Vin pastes a password and does not know
    whether it is right until the first scan — and by then the error is
    buried in the journal.

    The password must NEVER reach the returned string: imaplib's error is the
    server's verbatim reply, and that string goes straight into the journal.
    """
    if not address or not password:
        return "the address and app password are not both filled in"
    # Recognise an ACCOUNT password before sending it anywhere. A Google app
    # password is always 16 lowercase letters, no digits, no symbols. Pasting
    # the account password by mistake is common, and simply trying to log in
    # means the real password has already crossed the network before anyone
    # learns it was pointless.
    host = may_chu(address)
    mien = ten_mien(address)
    if not host:
        return (f"{mien} only allows IMAP through Proton Mail Bridge running "
                "on this machine. Install Bridge, then put its host/port "
                "under [mail] in config/config.toml.")
    # THIS FILTER IS GOOGLE'S, and applies to Google only. Applying it to
    # everyone blocks the door with a sentence that has nothing to do with
    # the real reason.
    if _la_google(host) and not APP_PASSWORD.fullmatch(password.replace(" ", "")):
        return ("that is not an app password. An app password is 16 lowercase "
                "letters, no digits, no symbols. Get one at "
                "myaccount.google.com/apppasswords after turning on 2-step "
                "verification.")
    # THE NETWORK LOCK for test runs — THE SAME switch as Telegram. Placed
    # HERE, after every local check: checking a shape costs no packets, and
    # the tests still have to be able to check them.
    #
    # Without this guard a test calling check() opens a real socket to the
    # internet carrying a real address. The same class of bug that already
    # happened with Telegram: the test suite sent real messages to the phone
    # on every run.
    from ..core.tele import khoa_mang
    if khoa_mang():
        return "JOBBOT_OFFLINE — no network calls during tests"
    try:
        box = imaplib.IMAP4_SSL(host, cong(), timeout=HET_GIO)
        try:
            box.login(address, password)
            box.select("INBOX", readonly=True)
        finally:
            try:
                box.logout()
            except Exception:            # noqa: BLE001
                pass
    except imaplib.IMAP4.error as exc:
        why = _hide(str(exc), password)
        if "AUTHENTICATIONFAILED" in why or "Invalid credentials" in why:
            if _la_google(host):
                return ("Gmail refused. Remember it is a 16-character app "
                        "password, NOT the account password — Gmail stopped "
                        "accepting account passwords for IMAP in 2022.")
            return (f"{host} refused. Most providers require an "
                    "application-specific password rather than the account "
                    "password — and IMAP has to be enabled in the mailbox "
                    "settings.")
        return why[:160]
    except OSError as exc:
        doan = not str(_section_host()).strip()
        them = ("\n" + _chi_cach(mien)) if doan and mien not in NHA_CUNG_CAP else ""
        return (f"could not reach {host}: "
                f"{_hide(str(exc), password)[:100]}{them}")
    return ""


def _la_google(host: str) -> bool:
    return host.endswith("gmail.com") or host.endswith("googlemail.com")


def _section_host() -> str:
    from ..core.config import section
    return str(section("mail").get("host") or "")


def _hide(text: str, secret: str) -> str:
    """Mask the password if it leaks into an error. Cheap, and one leak is a
    permanent leak into the journal."""
    return text.replace(secret, "***") if secret else text


def _made_id(msg) -> str:
    """A fallback id for mail with no Message-ID — hashed from the sender,
    subject and date. The same mail gives the same id, wherever it sits."""
    import hashlib

    seed = "|".join(str(msg.get(h) or "") for h in ("From", "Subject", "Date"))
    return "no-id-" + hashlib.sha1(seed.encode("utf-8", "replace")).hexdigest()[:20]


def _utc(when) -> str:
    """An ISO timestamp string, ALWAYS in UTC. That makes string comparison
    equal time comparison."""
    if not when:
        return ""
    from datetime import timezone
    if when.tzinfo is None:                 # no timezone in the mail -> treat as UTC
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).isoformat(timespec="seconds")


def _text(raw) -> str:
    out = []
    for part, enc in decode_header(raw or ""):
        out.append(part.decode(enc or "utf-8", "replace")
                   if isinstance(part, bytes) else part)
    return " ".join(out).strip()


def _body(msg) -> str:
    """The first few lines of text. Attachments are NOT touched."""
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() != "text/plain":
            continue
        if part.get_filename():          # an attachment, skip
            continue
        try:
            body = part.get_payload(decode=True) or b""
        except Exception:                # noqa: BLE001
            continue
        text = body.decode(part.get_content_charset() or "utf-8", "replace")
        got = re.sub(r"\s+", " ", text).strip()
        if got:
            return got[:SNIPPET]
    # NO PLAIN TEXT -> EXTRACT FROM THE HTML.
    #
    # Many ATSes send an HTML body only. Measured on the real mailbox:
    # 307 of 1,047 messages (29%) had an EMPTY snippet, and 296 of those were
    # filed as "other" — meaning `sort.kind()` could only see the SUBJECT. A
    # rejection with a neutral subject ("Update on your application") whose
    # body says "unfortunately" was unreadable, and that application sat at
    # "waiting" forever.
    return _tu_html(msg)


def _tu_html(msg) -> str:
    """Text extracted from an HTML body. Empty if the mail has no HTML part."""
    tho = _html_body(msg)
    if not tho:
        return ""
    from ..ingest.base import strip_html
    return re.sub(r"\s+", " ", strip_html(tho)).strip()[:SNIPPET]


def _html_body(msg) -> str:
    """The verbatim HTML body. Empty if the mail is plain text only."""
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() != "text/html" or part.get_filename():
            continue
        try:
            body = part.get_payload(decode=True) or b""
        except Exception:                    # noqa: BLE001
            continue
        return body.decode(part.get_content_charset() or "utf-8", "replace")
    return ""


def fetch(address: str, password: str, since_days: int = SINCE_DAYS,
          limit: int = MAX_MESSAGES, sender: str = "",
          want_html: bool = False) -> list[dict]:
    """Mail from the last `since_days` days. Nothing on the server changes.

    `sender` filters on the IMAP server itself — far cheaper than pulling the
    whole mailbox down and filtering in Python, and it is what makes the
    "job alert mail" source viable: Vin's mailbox holds 381 alerts among
    5,513 messages.

    `want_html` is only set when the caller GENUINELY needs it: an alert's
    HTML body is 86 KB, while the application scan needs 400 characters of
    plain text.
    """
    if not address or not password:
        raise MailError("[mail] address/password are not filled in in config.toml")

    from ..core.tele import khoa_mang
    if khoa_mang():
        raise MailError("JOBBOT_OFFLINE — the mailbox is not opened during tests")

    host = may_chu(address)
    if not host:
        raise MailError(f"{ten_mien(address)} needs Proton Mail Bridge — put "
                        "the Bridge's host/port under [mail] in config.toml")

    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
    box = imaplib.IMAP4_SSL(host, cong(), timeout=HET_GIO)
    try:
        box.login(address, password)
        # readonly=True: the server does NOT mark mail as read.
        box.select("INBOX", readonly=True)
        loc = f'(SINCE "{since}"'
        if sender:
            # Escape the quote: this string goes into an IMAP command, not
            # SQL, but the same rule holds — user-supplied text is never
            # concatenated straight into a command.
            loc += f' FROM "{sender.replace(chr(34), "")}"'
        ok, data = box.search(None, loc + ")")
        if ok != "OK":
            raise MailError(f"the search failed: {ok}")
        tat_ca = (data[0] or b"").split()
        ids = tat_ca[-limit:]
        # A CUT HAS TO BE ANNOUNCED. Taking the newest `limit` messages means
        # dropping the older ones, which means dropping the first days of the
        # range the user asked for. Silence here reports "scanned 60 days"
        # while only 19 were read.
        if len(tat_ca) > len(ids):
            from ..core.journal import SEARCH, log as jlog
            jlog.warn(SEARCH,
                      f"the mailbox holds {len(tat_ca):,} messages over "
                      f"{since_days} days, the ceiling is {limit:,} — only the "
                      f"NEWEST {len(ids):,} were read, the older ones were not")

        out, broken = [], 0
        for num in ids:
            # ONE malformed message must NOT kill the whole pass. A bad date
            # format, an odd encoding, broken MIME — parsedate_to_datetime and
            # decode_header can all raise, and one such message would lose the
            # other 29 with it. A broken advert can be dropped; a rejection
            # must not be dropped because the message next to it is broken.
            try:
                # BODY.PEEK: fetch WITHOUT setting \Seen. Plain BODY[] sets it.
                ok, chunk = box.fetch(num, "(BODY.PEEK[])")
                if ok != "OK" or not chunk or not isinstance(chunk[0], tuple):
                    continue
                msg = email.message_from_bytes(chunk[0][1])
                addr = email.utils.parseaddr(msg.get("From", ""))
                try:
                    when = email.utils.parsedate_to_datetime(msg.get("Date", "")) \
                        if msg.get("Date") else None
                except (TypeError, ValueError):
                    when = None
            except Exception:                    # noqa: BLE001
                broken += 1
                continue
            out.append({
                # Do NOT use the sequence number as a fallback id: it changes
                # whenever the mailbox gains or loses a message, so on the
                # next scan a DIFFERENT message carries the same "no-id-42"
                # and counts as already read — and a rejection vanishes.
                # Hashing the content keeps the id stable per message.
                "msg_id": msg.get("Message-ID") or _made_id(msg),
                "from_addr": addr[1], "from_name": _text(addr[0]),
                "subject": _text(msg.get("Subject")),
                # NORMALISE TO UTC AT WRITE TIME, rather than keeping the
                # sender's timezone.
                #
                # Three other places compare timestamps by STRING COMPARISON:
                # scan.settle (may old mail overwrite a newer status),
                # board.all (max() finding the last contact), and ORDER BY
                # received_at. String comparison across ISO values in
                # different timezones is wrong: '...01:30-04:00' (05:30 UTC)
                # sorts BEFORE '...02:00+00:00' alphabetically, so a message
                # 3.5 hours newer counted as older and was dropped.
                #
                # Measured on the real mailbox: 200 of 1,046 messages carry a
                # non-UTC timezone. Fixing it HERE makes all three correct at
                # once — patching each comparison means remembering forever,
                # and one will be forgotten.
                "received_at": _utc(when),
                "snippet": _body(msg),
                **({"html": _html_body(msg)} if want_html else {}),
            })
        if broken:
            from ..core.journal import SEARCH, log as jlog
            jlog.warn(SEARCH, f"skipped {broken} unreadable messages (odd format)")
        return out
    finally:
        # logout() raises when the connection has already broken, and imaplib
        # does NOT close the underlying socket by itself. Scanning hourly on a
        # flaky network leaks file descriptors.
        try:
            box.logout()
        except Exception:                # noqa: BLE001
            pass
        try:
            sock = getattr(box, "sock", None)
            if sock is not None:
                sock.close()
        except Exception:                # noqa: BLE001
            pass
