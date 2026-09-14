"""One mailbox pass: read → classify → match → PROPOSE.

It NEVER changes a status by itself. A mail opening with "unfortunately"
could be a rejection, or it could be the opening line of an
interview-reschedule. Guess wrong and write it, and the table is wrong with
no way for Vin to know it is wrong.

Mail can RECONSTRUCT THE PAST: EVERY mail with an outcome — an
acknowledgement, an interview invitation, a rejection, an offer — is evidence
that an application was sent. If it matches no row, a new row is created at
exactly that stage. That application really happened; the app simply did not
know.

A BUG THAT WAS FIXED: only ACKNOWLEDGEMENT mail used to reconstruct a row. An
interview invitation from a company with no row showed "matches no row", Vin
pressed Accept and NOTHING happened — the interview invitation vanished. And
an invitation is stronger evidence than an acknowledgement. One rule for
every outcome, no exceptions.
"""

from __future__ import annotations

import sqlite3

from ..core.journal import SEARCH, log as jlog
from . import board, mail, sort


# `needs_you` — three levels, and the third one is this layer's whole idea:
#     0  you are not needed
#     1  the machine UNDERSTANDS and proposes a status change
#     2  the machine does NOT understand, but this mail belongs to an
#        application on the table
#
# WHY LEVEL 2 IS NEEDED. A table of phrasings is never complete — measured on
# the real mailbox: "Sorry, it's not quite a match" (Maven) and "Your
# application is in" (Trading 212) are both real mail, both fell into
# `other`, and both vanished without trace. Racing to add more keywords is a
# game with no end.
#
# So the rule changed: it does NOT promise to understand every mail, it
# promises NO MAIL DISAPPEARS. Mail the machine cannot read that matches an
# application is surfaced for the user to classify — and what they classify
# is what teaches the phrasing table.
CAN_BAN = 1
KHONG_HIEU = 2


def store(conn: sqlite3.Connection, msg: dict, kind: str,
          company: str, app_id: int | None) -> bool:
    """Record one mail. True if it is NEW."""
    found = conn.execute("SELECT id FROM message WHERE msg_id = ?",
                         (msg["msg_id"],)).fetchone()
    if found:
        return False
    conn.execute(
        "INSERT INTO message (msg_id, from_addr, from_name, subject,"
        " received_at, snippet, kind, company_guess, application_id, needs_you)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (msg["msg_id"], msg["from_addr"], msg["from_name"], msg["subject"],
         msg["received_at"], msg["snippet"], kind, company,
         app_id, _muc(kind, app_id)))
    conn.commit()
    return True


def _muc(kind: str, app_id: int | None) -> int:
    """How much this mail needs the user — see the note on CAN_BAN."""
    if kind != "other":
        return CAN_BAN
    return KHONG_HIEU if app_id else 0


def _so_ngay(conn: sqlite3.Connection) -> int:
    """How many days of mail to re-read — set in Settings · Gmail."""
    from ..core import prefs
    return prefs.num(conn, prefs.MAIL_DAYS, 1, 365)


def run(conn: sqlite3.Connection, days: int | None = None) -> dict:
    """One pass. Returns measurements, not prose."""
    address, password = mail.account()
    if not address or not password:
        jlog.warn(SEARCH, "no mailbox connected — open Settings · Gmail")
        return {"ok": False, "why": "no mailbox connected"}

    # The number of days is THE USER's, read at call time rather than baked
    # into the signature: baked in, changing it in Settings still needs an app
    # restart to take effect.
    if days is None:
        days = _so_ngay(conn)
    jlog.progress(SEARCH, f"reading {days} days of mail")
    try:
        messages = mail.fetch(address, password, since_days=days)
    except Exception as exc:                 # noqa: BLE001
        jlog.error(SEARCH, f"reading mail failed — {type(exc).__name__}: {exc}")
        return {"ok": False, "why": str(exc)}
    finally:
        jlog.done(SEARCH)

    seen = fresh = made = 0
    for msg in messages:
        seen += 1
        kind = sort.kind(msg)
        company = sort.company_of(msg)
        app_id = sort.match(conn, msg)

        # No matching row while the mail carries an outcome = an application
        # the app did not know about. Rebuild it at EXACTLY the stage the
        # mail states; do not force it to "applied": a rejection turned into
        # a "waiting" row makes the table wrong the moment it is created.
        # PUBLIC SERVICES ARE NOT JOBS. "Your application for a National
        # Insurance number" matched the `applied` rule and created a row on
        # the job-tracking table — measured on the real mailbox.
        # EVIDENCE BEATS INFERENCE.
        #
        # The domain filter is an INFERENCE ("mail from here is probably not
        # about a job"). `sort.kind()` reading "interview" is EVIDENCE taken
        # from the mail itself. An inference must not override evidence.
        #
        # The previous version did override, and the measured cost:
        # interview invitations from the Civil Service
        # (`...service.gov.uk`) and the NHS (`jobs.nhs.uk`) were correctly
        # read as "interview", then forced to "other" with needs_you = 0, and
        # vanished from every screen — breaking the exact promise that no
        # mail is left behind.
        #
        # This rule also holds for domains NOBODY HAS THOUGHT OF YET: however
        # much is added to the block list, it can never eat a mail carrying a
        # real outcome.
        if (kind not in sort.MANH
                and sort.KHONG_PHAI_VIEC.search(msg.get("from_addr") or "")):
            kind, company = "other", ""
        if app_id is None and company and kind in board.STAGES:
            # The LOCATION and the ORIGINAL POSTING are read as the row is
            # created. Without that link the Manage table cannot point back
            # at which posting and which CV version — and that link is
            # exactly where it joins Search to CV.
            vai_tro = sort.role_of(msg)
            app_id = board.add(conn, company, vai_tro, origin="mail",
                               posting_id=sort.match_posting(conn, company, vai_tro),
                               applied_at=msg["received_at"], stage=kind)
            made += 1

        fresh += store(conn, msg, kind, company, app_id)

    jlog.ok(SEARCH, f"mail: read {seen} · new {fresh} · reconstructed {made} applications")
    return {"ok": True, "seen": seen, "fresh": fresh, "made": made}


def noi_lai(conn: sqlite3.Connection) -> dict:
    """Re-link EVERY existing row to a posting in the store and to the
    location read from mail.

    Re-runnable: it only fills what is empty and never overwrites what the
    user edited. It exists because the first 37 rows were created before the
    machine could read a location.
    """
    noi = ten_vai = 0
    for a in conn.execute("SELECT id, company, role, posting_id FROM application"
                          ).fetchall():
        vai = a["role"] or ""
        if not vai:
            r = conn.execute(
                "SELECT subject, snippet FROM message WHERE application_id = ?"
                " ORDER BY received_at", (a["id"],)).fetchall()
            for m in r:
                vai = sort.role_of(dict(m))
                if vai:
                    conn.execute("UPDATE application SET role = ? WHERE id = ?",
                                 (vai, a["id"]))
                    ten_vai += 1
                    break
        if not a["posting_id"]:
            pid = sort.match_posting(conn, a["company"], vai)
            if pid:
                conn.execute("UPDATE application SET posting_id = ? WHERE id = ?",
                             (pid, a["id"]))
                noi += 1
    conn.commit()
    return {"noi_tin": noi, "them_vai_tro": ten_vai}


def kho_hieu(conn: sqlite3.Connection) -> list[dict]:
    """Mail the machine could NOT classify that belongs to an application.

    This is the last catch: it does not promise to understand every phrasing,
    only that no mail disappears. One classification from the user and the
    status changes at once.
    """
    return [dict(r) for r in conn.execute(
        "SELECT m.id, m.subject, m.snippet, m.received_at, m.from_addr,"
        " m.company_guess, a.id AS app_id, a.company, a.role, a.stage"
        " FROM message m JOIN application a ON a.id = m.application_id"
        " WHERE m.needs_you = ? ORDER BY m.received_at DESC", (KHONG_HIEU,))]


def xep(conn: sqlite3.Connection, message_id: int, kind: str) -> bool:
    """The user classifies a mail the machine could not read.

    It records the `kind` and changes the status immediately — the user has
    read the mail and decided, and asking again makes them click twice for
    one thing.
    """
    if kind not in board.STAGES:
        return False
    row = conn.execute("SELECT subject, application_id FROM message WHERE id = ?",
                       (message_id,)).fetchone()
    if row is None or not row["application_id"]:
        return False
    conn.execute("UPDATE message SET kind = ?, needs_you = 0 WHERE id = ?",
                 (kind, message_id))
    conn.commit()
    board.set_stage(conn, int(row["application_id"]), kind,
                    (row["subject"] or "")[:90])
    jlog.ok(SEARCH, f"you classified an unread mail -> {kind}")
    return True


def gan(conn: sqlite3.Connection, message_id: int, app_id: int) -> bool:
    """The user points: this mail belongs to WHICH application.

    THE MISSING HALF of the "no mail disappears" promise. The machine can
    read the mail's outcome but cannot work out the company — measured, the
    real mailbox has 3 of those, and until now they had exactly one button:
    Skip. Seeing something you can do nothing about is still losing it, just
    more loudly.
    """
    m = conn.execute("SELECT kind, subject FROM message WHERE id = ?",
                     (message_id,)).fetchone()
    a = conn.execute("SELECT id FROM application WHERE id = ?", (app_id,)).fetchone()
    if m is None or a is None:
        return False
    conn.execute("UPDATE message SET application_id = ?, needs_you = ?"
                 " WHERE id = ?", (app_id, CAN_BAN, message_id))
    conn.commit()
    if m["kind"] in board.STAGES:
        board.set_stage(conn, app_id, m["kind"], (m["subject"] or "")[:90])
        conn.execute("UPDATE message SET needs_you = 0 WHERE id = ?", (message_id,))
        conn.commit()
    jlog.ok(SEARCH, f"attached a mail to application #{app_id}")
    return True


def proposals(conn: sqlite3.Connection) -> list[dict]:
    """Mail PROPOSING a status change — nothing changes until Vin presses.

    It only proposes when the new status DIFFERS from the current one; an
    acknowledgement for a row already at 'applied' has nothing to ask.
    """
    out = []
    for r in conn.execute(
            "SELECT m.id, m.subject, m.snippet, m.kind, m.received_at,"
            " m.company_guess, a.id AS app_id, a.company, a.role, a.stage"
            " FROM message m LEFT JOIN application a ON a.id = m.application_id"
            " WHERE m.needs_you = ? ORDER BY m.received_at DESC", (CAN_BAN,)):
        row = dict(r)
        if row["app_id"] and row["kind"] == row["stage"]:
            continue                       # already at that status, do not ask again
        out.append(row)
    return out


def settle(conn: sqlite3.Connection, message_id: int, accept: bool) -> None:
    """Vin answers a proposal. Accept changes the status; skip goes quiet.

    OLD mail must not overwrite a NEWER status. Man Group sent "thank you for
    applying" on day 1 and "unfortunately" on day 20; Vin accepted the
    rejection first, then accepted the older acknowledgement — and the row
    went back to "waiting". The table said the application was alive when it
    was dead, which is the worst thing a tracking table can do.
    """
    row = conn.execute(
        "SELECT m.kind, m.subject, m.received_at, m.application_id,"
        " a.last_event_at FROM message m"
        " LEFT JOIN application a ON a.id = m.application_id"
        " WHERE m.id = ?", (message_id,)).fetchone()
    if row is None:
        return
    stale = bool(row["received_at"] and row["last_event_at"]
                 and row["received_at"] < row["last_event_at"])
    if accept and row["application_id"] and row["kind"] in board.STAGES and not stale:
        board.set_stage(conn, row["application_id"], row["kind"],
                        row["subject"][:90])
    elif accept and stale:
        jlog.warn(SEARCH, f"skipped mail older than the current status — "
                          f"{(row['subject'] or '')[:50]}")
    conn.execute("UPDATE message SET needs_you = 0 WHERE id = ?", (message_id,))
    conn.commit()
