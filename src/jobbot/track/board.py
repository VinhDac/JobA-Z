"""The tracking table — one row per application.

A row is born when Vin applies, and changes status when mail arrives. Mail is
the SENSOR, the table is the STATE — not two features, one loop.

`silence` is NOT stored as a column. It is a subtraction computed at read
time: applied long ago with no mail since. Stored, it would have to be
updated every day, and one day it would be forgotten — exactly how `gap` went
wrong on the project grid.
"""

from __future__ import annotations

import sqlite3

from ..ingest.base import norm

# Five stages. Each maps to a different thing Vin does — a stage that maps to
# nothing is not allowed to exist.
#
# `draft` is born when the machine opens a form and fills it in. It is NOT
# "applied": the form still has questions only Vin can answer, and the Send
# click is his. Writing "applied" there makes the table lie on its very first
# row — and Vin reads this table every day. The acknowledgement mail will
# push it to "applied" on its own; that is exactly mail's sensor role, not a
# new mechanism.
DRAFT = "draft"
SENT, INTERVIEW, REJECTED, OFFER = "applied", "interview", "rejected", "offer"
STAGES = (DRAFT, SENT, INTERVIEW, REJECTED, OFFER)
STAGE_LABEL = {DRAFT: "filling in", SENT: "applied", INTERVIEW: "interview",
               REJECTED: "rejected", OFFER: "offer"}
# Waiting for an OUTCOME. A draft waits on nobody else — it waits on Vin, so
# it is excluded here and is never called "silent".
OPEN = (SENT, INTERVIEW)

# The DEFAULT for "how many days of silence counts as a rejection". The user
# can turn it (⚟ on the Manage deck — see core/prefs.IM_QUA); this number is
# only the fallback before anyone turns it, and when `all()` is called with
# nothing passed.
#
# 20, not 14: 14 is the MEASURED figure (the latest reply in the real
# mailbox came back on day 14), but a measured figure is a figure from the
# past — using it verbatim as the cut-off leaves no room for the 38th reply.
SILENT_AFTER = 20


def nguong(conn: sqlite3.Connection) -> int:
    """The silence threshold in use. ONE reader, so the table and the deck
    count the same.

    Two separate readers means the deck eventually reports "32 rejected"
    while the table below files 34 rows under that heading, and nobody can
    tell which one is wrong.
    """
    from ..core import prefs
    return prefs.num(conn, prefs.IM_QUA, 3, 365)


def _now() -> str:
    from ..core.postings import now
    return now()


def add(conn: sqlite3.Connection, company: str, role: str,
        posting_id: int | None = None, cv_file: str = "",
        origin: str = "manual", applied_at: str = "",
        stage: str = SENT) -> int:
    """Record an application. Applying again for the same role at the same
    company does NOT create a new row — that is one application, not two."""
    key = norm(company)
    found = conn.execute(
        "SELECT id, stage, posting_id FROM application"
        " WHERE company_key = ? AND role = ?", (key, role)).fetchone()
    if found:
        app_id = int(found["id"])
        if cv_file:
            conn.execute("UPDATE application SET cv_file = ? WHERE id = ?",
                         (cv_file, app_id))
        # A row rebuilt from mail has no posting id. Without attaching one,
        # the Send button looks for a window by posting_id and reports "no
        # original posting".
        if posting_id and not found["posting_id"]:
            conn.execute("UPDATE application SET posting_id = ? WHERE id = ?",
                         (posting_id, app_id))
        # REAPPLYING somewhere that rejected you (the company reopened the
        # posting) is a NEW application. Keeping the old stage leaves the
        # table saying "rejected", the Send button hidden, and the
        # application Vin just filled in never goes. Pull it back to draft,
        # but SAY what the old outcome was — losing history is also a lie.
        if stage == DRAFT and found["stage"] in (REJECTED, OFFER):
            conn.execute(
                "UPDATE application SET stage = ?, last_event = ?,"
                " last_event_at = ? WHERE id = ?",
                (DRAFT, f"reapplied — previously: {STAGE_LABEL[found['stage']]}",
                 _now(), app_id))
        conn.commit()
        return app_id
    cur = conn.execute(
        "INSERT INTO application (company, company_key, role, posting_id,"
        " origin, applied_at, stage, cv_file) VALUES (?,?,?,?,?,?,?,?)",
        (company, key, role, posting_id, origin, applied_at or _now(),
         stage if stage in STAGES else SENT, cv_file))
    conn.commit()
    return int(cur.lastrowid)


def set_stage(conn: sqlite3.Connection, app_id: int, stage: str,
              event: str = "") -> None:
    if stage not in STAGES:
        return
    conn.execute(
        "UPDATE application SET stage = ?, last_event_at = ?, last_event = ?"
        " WHERE id = ?",
        (stage, _now(), event or STAGE_LABEL[stage], app_id))
    conn.commit()


SENDING = "sending"          # mid-click — a TEMPORARY stage, never shown as a label


def claim(conn: sqlite3.Connection, app_id: int) -> bool:
    """Claim the right to send this application. True if the claim succeeds.

    A single UPDATE ... WHERE stage = 'draft' is ATOMIC: two clicks two
    seconds apart and only one statement changes the row, the other counts 0.
    Read-then-write at the route layer means both see 'draft' and both go and
    press Submit — two identical applications to the same employer.
    """
    cur = conn.execute(
        "UPDATE application SET stage = ? WHERE id = ? AND stage = ?",
        (SENDING, app_id, DRAFT))
    conn.commit()
    return cur.rowcount == 1


def unclaim(conn: sqlite3.Connection, app_id: int) -> None:
    """Return it to draft when sending failed."""
    conn.execute("UPDATE application SET stage = ? WHERE id = ? AND stage = ?",
                 (DRAFT, app_id, SENDING))
    conn.commit()


def drop(conn: sqlite3.Connection, app_id: int) -> bool:
    """Delete a row — ONLY while it is still a draft.

    Opening a form and changing your mind is normal, and a forgotten draft
    row makes the table dirty. But a REAL application is not deleted by one
    click: that is history, and with the history gone there is nothing to
    look back at after 30 days.

    Mail is deleted before the row: `message.application_id` has no
    ON DELETE CASCADE, so the other order hits the foreign key.
    """
    row = conn.execute("SELECT stage FROM application WHERE id = ?",
                       (app_id,)).fetchone()
    if row is None or row["stage"] != DRAFT:
        return False
    conn.execute("DELETE FROM message WHERE application_id = ?", (app_id,))
    conn.execute("DELETE FROM application WHERE id = ?", (app_id,))
    conn.commit()
    return True


def note(conn: sqlite3.Connection, app_id: int, text: str) -> None:
    conn.execute("UPDATE application SET note = ? WHERE id = ?", (text, app_id))
    conn.commit()


def _days(stamp: str) -> int | None:
    from datetime import datetime, timezone
    if not stamp:
        return None
    try:
        then = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - then).total_seconds() // 86400)


# The VITALITY of an application — what the table has to answer and `stage`
# alone cannot. "Applied" 40 days ago in silence is nothing like "applied"
# yesterday.
SONG_NONG = "nong"        # they are talking to you — interview, offer
SONG_CHO = "cho"          # still inside the reply window
SONG_IM = "im"            # past the window with not one word
SONG_XONG = "xong"        # it has an outcome

# WHO APPLIED — and the user needs all of these kept apart.
#     mail   you applied yourself BEFORE using the app; rebuilt from mail
#     apply  you applied through the app
#     tay    the machine meant to apply and could not (LinkedIn locked) —
#            you do it yourself
AI_NOP = {"mail": "applied before the app", "apply": "applied through the app",
          "auto": "the machine applied", "tay": "you have to apply by hand",
          "manual": "added by hand"}


def nguon_cua(source: str) -> str:
    """`greenhouse:imc` -> board · `linkedin` -> linkedin · `alert` -> alert.

    ONE translation, shared with the Search tab (views/search.FOUND_BY).
    Translating in two places means the two tabs eventually call the same
    posting by two different source names.
    """
    s = (source or "").strip().lower()
    if not s:
        return ""
    return s if s in ("linkedin", "alert") else "board"


def all(conn: sqlite3.Connection, im_qua: int | None = None) -> list[dict]:
    """The whole table, with MEASUREMENTS of time and mail.

    SILENCE IS MEASURED FROM THE LAST MAIL, NOT FROM `last_event_at`, which
    is only written when the user ACCEPTS a proposal; so a company that has
    replied four times while the user has not pressed anything was still
    counted as "silent". Measured on the real mailbox: the table reported 35
    silent when there were only 28 — 7 companies that had replied were
    recorded as silent.
    """
    moc = nguong(conn) if im_qua is None else int(im_qua)
    thu = {}
    for r in conn.execute(
            "SELECT application_id, COUNT(*) n, MAX(received_at) cuoi,"
            " MIN(received_at) dau FROM message"
            " WHERE application_id IS NOT NULL GROUP BY application_id"):
        thu[r["application_id"]] = (r["n"], r["cuoi"], r["dau"])

    rows = []
    for r in conn.execute(
            "SELECT a.*, p.url AS url, p.score AS score, p.source AS source_tin,"
            " p.title AS tin_title FROM application a"
            " LEFT JOIN posting p ON p.id = a.posting_id ORDER BY a.id DESC"):
        row = dict(r)
        n, cuoi, dau = thu.get(row["id"], (0, "", ""))
        row["so_thu"] = n
        row["thu_cuoi"] = cuoi or ""
        row["days"] = _days(row["applied_at"])
        row["event_days"] = _days(row["last_event_at"])
        # THE LAST CONTACT = the latest of three: the newest mail, the event
        # timestamp the user confirmed, and the time of applying.
        #
        # Leaving out `last_event_at` is wrong: the user accepting an
        # interview invitation IS a contact, even if that mail is old.
        # Without it, a row that is mid-interview still counts as "silent".
        row["im_ngay"] = _days(max(
            x for x in (cuoi, row["last_event_at"], row["applied_at"]) if x)
            if any((cuoi, row["last_event_at"], row["applied_at"])) else "")
        row["ho_tra_loi"] = n > 1 or bool(cuoi and dau and cuoi != dau)
        row["silent"] = (row["stage"] in OPEN
                         and (row["im_ngay"] or 0) >= moc)
        if row["stage"] in (INTERVIEW, OFFER):
            row["song"] = SONG_NONG
        elif row["stage"] not in OPEN:
            row["song"] = SONG_XONG
        else:
            row["song"] = SONG_IM if row["silent"] else SONG_CHO
        row["nguon"] = nguon_cua(row.get("source_tin") or "")
        row["ai_nop"] = AI_NOP.get(row.get("origin") or "", row.get("origin") or "")
        row["co_cv"] = bool(row.get("cv_file")) or bool(row.get("posting_id"))
        rows.append(row)
    # Drafts first: that is work in progress, and work in progress has to
    # be the first thing you see.
    rows.sort(key=lambda r: (r["stage"] != DRAFT, r["stage"] not in OPEN,
                             -(r["days"] or 0)))
    return rows


def im_da_pha(conn: sqlite3.Connection) -> dict:
    """Every SILENCE THAT WAS EVENTUALLY BROKEN — the measurement for
    choosing the threshold correctly.

    The real question behind "counts as rejected after how many days" is not
    "how long do they usually take to reply". It is: WITH THIS THRESHOLD, HOW
    MANY REPLIES WOULD I HAVE CLOSED WRONGLY? And that has an exact answer in
    the mailbox already here — each time a reply arrived after a stretch of
    silence, that stretch is one case where a threshold of that length would
    have been wrong.

    So this returns EVERY silence that was broken. A threshold M closes
    wrongly exactly as many times as there are stretches >= M.

    NOT `max(im_ngay)` — that is what the table used to measure by mistake.
    `im_ngay` is "how long ago the last contact was", which is a silence
    STILL RUNNING and not yet broken; using it as "the latest reply" gave 40
    days on the real mailbox when the right answer is 18.
    """
    from datetime import datetime, timezone

    def _moc(x):
        try:
            t = datetime.fromisoformat((x or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t

    thu = {}
    for m in conn.execute("SELECT application_id, received_at FROM message"
                          " WHERE application_id IS NOT NULL"
                          " ORDER BY application_id, received_at"):
        thu.setdefault(m["application_id"], []).append(m["received_at"])

    khoang, ai, lau = [], "", 0
    for a in conn.execute("SELECT id, company, applied_at FROM application"):
        moc = [x for x in [_moc(a["applied_at"])]
               + [_moc(t) for t in thu.get(a["id"], [])] if x]
        for truoc, sau in zip(moc, moc[1:]):
            n = int((sau - truoc).total_seconds() // 86400)
            if n < 0:
                continue
            khoang.append(n)
            if n > lau:
                lau, ai = n, a["company"] or ""
    return {"lau": lau, "ai": ai, "so": len(khoang), "khoang": sorted(khoang)}


def thu_cua(conn: sqlite3.Connection, app_id: int) -> list[dict]:
    """Every mail of ONE application, newest first. The detail card's content."""
    return [dict(r) for r in conn.execute(
        "SELECT id, subject, snippet, kind, received_at, from_addr"
        " FROM message WHERE application_id = ? ORDER BY received_at DESC",
        (app_id,))]


def counts(conn: sqlite3.Connection) -> dict:
    out = {s: 0 for s in STAGES}
    silent = 0
    for row in all(conn):
        out[row["stage"]] = out.get(row["stage"], 0) + 1
        silent += bool(row["silent"])
    out["silent"] = silent
    # "Total" means applications REALLY SENT. A draft has gone nowhere, and
    # counting it is flattering yourself.
    out["total"] = sum(out[s] for s in STAGES if s != DRAFT)
    return out
