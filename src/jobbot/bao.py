"""Decides WHAT TO NOTIFY, and answers remote commands.

Split from core/tele.py on purpose: tele owns the ROUTE (calling the API, the
chat_id guard, parsing commands), this file owns the CONTENT (is it worth
notifying, how is it worded, what does this command return). Mixed together,
neither is testable: trying out the wording would need a real token.

THE FOUNDING RULE: NOTIFY RARELY. Four kinds, and each has to answer "what
would I do differently for knowing this". A kind that cannot is noise, and
noise makes the user switch notifications off entirely — including the one
that mattered.

NEVER RAISES OUT. Runs on the scheduler's background thread.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .core import prefs, tele
from .core.journal import SYSTEM, log as jlog


def _hom_nay() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def bat(conn: sqlite3.Connection, khoa: str) -> bool:
    """Is this notification kind on — AND is the bot connected.

    Merging the two questions in one place is deliberate: forget the "is it
    connected" check and every scan calls the API with an empty token,
    failing quietly and filling the journal with rubbish.
    """
    return tele.da_noi() and prefs.flag(conn, khoa)


# --- THE FOUR KINDS ------------------------------------------------------

def _thu_moi(conn: sqlite3.Connection) -> list:
    """MOVED-FORWARD mail never notified about. The watermark lives in prefs
    rather than being recounted from scratch.

    Without a watermark every scan re-sends the same old mail, and the user
    switches notifications off after exactly two days.
    """
    try:
        moc = int(prefs.get(conn, prefs.BAO_MOC) or 0)
    except (TypeError, ValueError):
        moc = 0
    cho = ",".join(f"'{k}'" for k in ("interview", "offer"))
    return [dict(r) for r in conn.execute(
        f"SELECT m.id, m.subject, m.kind, m.received_at,"
        f" COALESCE(a.company, m.company_guess, '') AS cong_ty,"
        f" COALESCE(a.role, '') AS vai_tro"
        f" FROM message m LEFT JOIN application a ON a.id = m.application_id"
        f" WHERE m.kind IN ({cho}) AND m.id > ? ORDER BY m.id", (moc,))]


def di_tiep(conn: sqlite3.Connection) -> int:
    """Notify about new invitations. Returns how many were notified."""
    if not bat(conn, prefs.BAO_TIEP):
        return 0
    moi = _thu_moi(conn)
    if not moi:
        return 0
    dong = []
    for m in moi:
        ai = tele.thoat(m["cong_ty"] or "company unknown")
        vt = f" · {tele.thoat(m['vai_tro'])}" if m["vai_tro"] else ""
        loai = "INTERVIEW" if m["kind"] == "interview" else "OFFER"
        dong.append(f"<b>{loai}</b>\n{ai}{vt}\n"
                    f"<i>{tele.thoat(m['subject'][:110])}</i>")
    if tele.gui("🔔 " + "\n\n".join(dong)):
        prefs.put(conn, prefs.BAO_MOC, str(max(m["id"] for m in moi)))
        jlog.ok(SYSTEM, f"messaged Telegram: {len(moi)} moved-forward mails")
        return len(moi)
    return 0


def phien_hong(conn: sqlite3.Connection, hong: list) -> bool:
    """Notify which stage of the session just failed.

    A SILENT FAILURE is the worst kind: the machine sits idle for days while
    the board stays green, and the user only notices when nothing new has
    arrived for too long.
    """
    if not hong or not bat(conn, prefs.BAO_HONG):
        return False
    ten = {khuc: nhan for _k, (khuc, nhan, _y) in prefs.PHIEN.items()}
    ds = ", ".join(ten.get(k, k) for k in hong)
    return tele.gui(f"⚠️ <b>Session failed</b>\nStage(s) that could not run: "
                    f"{tele.thoat(ds)}\nOpen the app and read the journal for why.")


def hang_cho(conn: sqlite3.Connection) -> bool:
    """Notify when the queue piles past the threshold the user set."""
    if not bat(conn, prefs.BAO_CHO):
        return False
    from .track import scan as tscan
    n = len(tscan.proposals(conn)) + len(tscan.kho_hieu(conn))
    nguong = prefs.num(conn, prefs.BAO_NGUONG, 1, 999)
    if n < nguong:
        return False
    return tele.gui(f"📥 <b>{n} items waiting on your decision</b>\n"
                    f"Mail the machine could not settle. Open Manage → Queue.")


def ban_tin_ngay(conn: sqlite3.Connection, ep: bool = False) -> bool:
    """The end-of-day report — today's four numbers, sent EXACTLY ONCE.

    It remembers which date it was sent for (`BAO_NGAY_CUOI`): the background
    loop ticks every 30 seconds, and without that marker it would message
    continuously from the chosen hour until midnight.
    """
    if not bat(conn, prefs.BAO_NGAY):
        return False
    hom_nay = _hom_nay()
    if not ep:
        if prefs.get(conn, prefs.BAO_NGAY_CUOI) == hom_nay:
            return False
        if datetime.now().hour < prefs.num(conn, prefs.BAO_GIO, 0, 23):
            return False
    from .dashboard import tongquan
    hn = tongquan.hom_nay(conn)
    ok = tele.gui(
        f"📊 <b>Today</b> · {hn['ngay']}\n"
        f"postings found: <b>{hn['tim']}</b>\n"
        f"applications sent: <b>{hn['nop']}</b>\n"
        f"moved forward: <b>{hn['tiep']}</b>\n"
        f"rejections: <b>{hn['truot']}</b>")
    if ok and not ep:
        prefs.put(conn, prefs.BAO_NGAY_CUOI, hom_nay)
    return ok


def sau_phien(conn: sqlite3.Connection, ket_qua: dict) -> None:
    """ONE place that fires every kind of notification, after each session.

    Scattering the calls across four places means a new kind has to be
    remembered in four places, and one of them will be forgotten.
    """
    try:
        phien_hong(conn, (ket_qua or {}).get("hong") or [])
        di_tiep(conn)
        hang_cho(conn)
        ban_tin_ngay(conn)
    except Exception as exc:                # noqa: BLE001
        jlog.error(SYSTEM, f"Telegram message failed — {type(exc).__name__}: {exc}")


# --- ANSWERING REMOTE COMMANDS --------------------------------------------

GIUP = ("<b>jobbot</b>\n"
        "/trangthai — today's four numbers + the queue\n"
        "/batphien — start the 24/7 station\n"
        "/tatphien — stop the station\n"
        "/thu — mail waiting on your decision\n"
        "/nhan &lt;n&gt; — accept that mail's proposal\n"
        "/boqua &lt;n&gt; — skip that mail\n\n"
        "<i>There is no apply command, at any level: the Send click is "
        "yours, in front of the form.</i>")


def _trang_thai(conn: sqlite3.Connection) -> str:
    from .core import scheduler
    from .dashboard import tongquan
    from .track import scan as tscan
    hn = tongquan.hom_nay(conn)
    k = tongquan.ket_qua(conn)
    cho = len(tscan.proposals(conn)) + len(tscan.kho_hieu(conn))
    sch = scheduler.current()
    truc = ("RUNNING" if sch.running
            else "OFF" if sch.paused else f"on watch · next loop in {sch.next_in() // 60}m")
    return (f"📊 <b>Today</b> · {hn['ngay']}\n"
            f"found <b>{hn['tim']}</b> · applied <b>{hn['nop']}</b> · "
            f"forward <b>{hn['tiep']}</b> · rejected <b>{hn['truot']}</b>\n\n"
            f"applied in total <b>{k['tong']}</b> · moved forward <b>{k['di_tiep']}</b>"
            + (f" ({k['pc_di']:g}%)" if k["pc_di"] is not None else "") + "\n"
            f"queue <b>{cho}</b> items\n"
            f"station: <b>{truc}</b>")


def _thu_cho(conn: sqlite3.Connection) -> str:
    from .track import scan as tscan
    ds = tscan.proposals(conn)[:8]
    if not ds:
        return "No mail is waiting on your decision."
    o = []
    for p in ds:
        ai = tele.thoat(p.get("company") or p.get("company_guess") or "?")
        o.append(f"<b>{p['id']}</b> · {ai} → {tele.thoat(p['kind'])}\n"
                 f"   <i>{tele.thoat((p.get('subject') or '')[:70])}</i>")
    return ("📥 <b>Mail waiting on you</b>\n" + "\n".join(o)
            + "\n\n/nhan &lt;n&gt; or /boqua &lt;n&gt;")


def tra_loi(conn: sqlite3.Connection, lenh: str, tham: str) -> str:
    """Run a command that HAS ALREADY PASSED the permission guard, and
    return the reply.

    This does NOT check chat_id itself — that is tele.duoc_phep's job, called
    by the outer loop. Split out so the wording can be tested without
    constructing a whole fake Telegram update.
    """
    from .core import scheduler
    if lenh in ("giupdo", "start"):
        return GIUP
    if lenh == "trangthai":
        return _trang_thai(conn)
    if lenh == "batphien":
        sch = scheduler.current()
        sch.resume()
        return "▶️ The station is ON. The next loop runs on schedule."
    if lenh == "tatphien":
        scheduler.current().pause()
        return "⏸ The station is OFF. No further loops will run on their own."
    if lenh == "thu":
        return _thu_cho(conn)
    if lenh in ("nhan", "boqua"):
        if not tham.strip().isdigit():
            return "Missing the mail number. For example: /nhan 42 — use /thu to get one."
        from .track import scan as tscan
        mid = int(tham)
        co = conn.execute("SELECT 1 FROM message WHERE id = ? AND needs_you = 1",
                          (mid,)).fetchone()
        if not co:
            return "That mail is not in the queue — it may already be settled."
        # `settle` returns nothing; it also blocks OLD mail from overwriting a
        # NEWER status by itself (see track/scan.py). Here we only re-ask the
        # table whether anything actually changed.
        tscan.settle(conn, mid, lenh == "nhan")
        return ("✅ Accepted — the table now follows that mail."
                if lenh == "nhan" else "🗑 That mail was skipped.")
    return "Command not recognised. Send /giupdo for the list."


# --- SAVING THE CONFIG, AND CHECKING IT AS IT IS SAVED --------------------

def dang_token(t: str) -> bool:
    """A BotFather token looks like `<digits>:<string>`. Checks the SHAPE,
    not whether it is alive.

    Catches a truncated or wrong paste without going to the network. A
    correctly shaped token can still have been revoked — only `getMe` knows.
    """
    d, co, r = str(t or "").strip().partition(":")
    return bool(co and d.isdigit() and len(d) >= 6 and len(r) >= 20)


def dang_chat(x: str) -> bool:
    """A chat id is an INTEGER (negative for groups). NOT a phone number.

    This is where users go wrong most often, and go wrong silently: paste a
    phone number and Telegram answers "chat not found", a sentence that
    suggests nothing.
    """
    return str(x or "").strip().lstrip("-").isdigit()


def _cac_chat(ra: dict) -> list:
    """[(chat id, name)] in arrival order — newest LAST, deduplicated.

    The name is taken so the user can BE TOLD which chat is being connected.
    For a group Telegram returns `title`, for a person
    `first_name`/`last_name`, and some people only have a `username`. With
    none of them it returns empty and the caller falls back to the id.
    """
    thay = []
    for u in (ra or {}).get("result") or []:
        ch = ((u.get("message") or {}).get("chat")) or {}
        cid = str(ch.get("id", ""))
        if not cid or not dang_chat(cid):
            continue
        ten = (ch.get("title")
               or " ".join(str(x) for x in (ch.get("first_name"),
                                            ch.get("last_name")) if x)
               or (f"@{ch['username']}" if ch.get("username") else ""))
        thay = [(c, t) for c, t in thay if c != cid] + [(cid, ten.strip())]
    return thay


def luu(tok: str = "") -> tuple:
    """Save the token, verify it, AND FIND THE CHAT ID — one button, one press.

    The previous version made the user take three steps: Save token → Find
    chat → Test. The middle step asked them nothing: the chat id is something
    the machine can read from Telegram itself, so asking the user is asking a
    question they have no way to answer. A step that carries no new
    information is a step too many.

    So now: paste the token, press Save. The machine asks Telegram what the
    bot is called and whether anyone has messaged it. Found means done; not
    found means an error, WITH THE BOT NAMED — people often have several
    bots, and "message your bot" gets the wrong one.
    """
    from .core import config as cfg

    if tok:
        if not dang_token(tok):
            return False, ("That is not a token. A @BotFather token looks "
                           "like <b>7123456789:AAH…</b> — paste the whole "
                           "line, including the digits before the colon.")
        cfg.write_value(tele.MUC, "token", tok)

    me, loi = tele.goi("getMe", {})
    if loi:
        return False, f"Telegram rejected the token: {loi}"
    ten = ((me or {}).get("result") or {}).get("username", "")
    nhan_bot = f"<b>@{tele.thoat(ten)}</b>" if ten else "bot"

    # FIND THE CHAT ID. goi() rather than nhan(): nhan() swallows the
    # reason, so a dead token also reports "no messages seen" — pointing the
    # wrong way is worse than saying nothing.
    ra, loi = tele.goi("getUpdates", {"offset": 0, "timeout": 0})
    if loi:
        return False, f"The token is alive ({nhan_bot}) but messages could not be read: {loi}"
    ai = _cac_chat(ra)

    if ai:
        # TAKE THE NEWEST, AND SAY WHICH ONE WAS TAKEN. The previous version
        # took `ai[-1]` and reported "found your chat" — but if the bot has
        # ever been messaged by someone else (or added to a group), "your
        # chat" is someone else's, and every job notification goes straight
        # there. Nobody notices, because the screen never says which one it
        # picked.
        cid, ten = ai[-1]
        cfg.write_value(tele.MUC, "chat_id", cid)
        jlog.ok(SYSTEM, f"Telegram connected — {nhan_bot} -> {ten or cid}")
        goi_la = f"<b>{tele.thoat(ten)}</b>" if ten else f"id <b>{cid}</b>"
        if len(ai) == 1:
            return True, (f"Done. The token works, the bot is {nhan_bot}, and "
                          f"your chat was found: {goi_la}. Press <b>Test</b> "
                          f"to receive a test message.")
        khac = ", ".join(tele.thoat(t or c) for c, t in ai[:-1])
        return True, (f"The token works, the bot is {nhan_bot}. <b>{len(ai)}</b> "
                      f"chats have messaged it ({khac}, {tele.thoat(ten or cid)}) "
                      f"— the <b>most recent</b> one was chosen: {goi_la}. If "
                      f"that is wrong, message the bot from your own device "
                      f"and press <b>Save</b> again. Press <b>Test</b> to see "
                      f"where messages land.")

    # No messages. If a chat id was already saved earlier this still counts
    # as done — Telegram deletes messages once delivered, so "nothing left"
    # is the normal state of a bot that has already been used.
    if dang_chat(tele.cau_hinh().get("chat_id", "")):
        return True, (f"The token works, the bot is {nhan_bot}, and the chat "
                      f"id was already saved. Press <b>Test</b> to try it.")

    return False, (f"The token works, the bot is {nhan_bot} — but nobody has "
                   f"messaged it yet. Open Telegram, find {nhan_bot}, send "
                   f"<b>/start</b>, then press <b>Save</b> again.")


# --- THE TEST BUTTON ------------------------------------------------------

def tin_thu(conn: sqlite3.Connection) -> str:
    """The TEST message — which is also the instructions.

    A test message that only says "ok" proves the ROUTE is open; it proves
    nothing about the CONFIGURATION. The user would still have to go back to
    Settings to see which level they are on and which kinds are enabled — and
    at that moment they are holding their phone.

    So this message says all three things, right there on the phone: which
    MODE, which COMMANDS, and WHEN it will message.
    """
    muc = prefs.get(conn, prefs.BAO_MUC) or tele.TAT
    ten_muc = tele.MUC_DIEU_KHIEN.get(muc, ("?", ""))[0]

    if muc == tele.TAT:
        lenh = ("<i>You are on one-way notifications — the bot accepts no "
                "commands. Change it under Settings · Notifications on the "
                "machine.</i>")
    else:
        co = [l for l in tele.LENH_XEM if l not in ("giupdo", "start")]
        if muc == tele.DAY_DU:
            co += list(tele.LENH_GHI)
        lenh = "Commands available: " + " ".join(f"/{l}" for l in co)

    bat_ds = [prefs.BAO[k][0] for k in prefs.BAO if prefs.flag(conn, k)]
    tat_ds = [prefs.BAO[k][0] for k in prefs.BAO if not prefs.flag(conn, k)]
    khi = ("Will message when:\n" + "\n".join(f"• {tele.thoat(x)}" for x in bat_ds)
           if bat_ds else
           "<b>No notification kind is enabled</b> — nothing will be sent.")
    if tat_ds:
        khi += f"\n<i>(off: {tele.thoat(' · '.join(tat_ds))})</i>"

    gio = prefs.num(conn, prefs.BAO_GIO, 0, 23)
    them = (f"\nThe end-of-day report is sent at <b>{gio}:00</b>."
            if prefs.flag(conn, prefs.BAO_NGAY) else "")

    return (f"✅ <b>jobbot is connected</b>\n"
            f"This message arriving means the token and chat id are both right.\n\n"
            f"<b>Mode:</b> {tele.thoat(ten_muc)}\n{lenh}\n\n"
            f"{khi}{them}\n\n"
            f"<i>Press Test under Settings · Notifications to send this again.</i>")


def thu(conn: sqlite3.Connection) -> tuple:
    """Press Test -> (did it work, the sentence shown on Settings).

    It sends a REAL message rather than simulating one: the whole chain token
    → chat id → network → Telegram can only be proven by going all the way
    round. Checking each link and concluding "it probably works" is exactly
    the self-deception this app avoids.
    """
    ok, loi = tele.gui_chi_tiet(tin_thu(conn))
    if ok:
        jlog.ok(SYSTEM, "Telegram: test message sent")
        return True, ("Sent. Open Telegram — that message also tells you "
                      "which mode you are on and which commands you have.")
    jlog.warn(SYSTEM, f"Telegram: the test message did NOT send — {loi}")
    return False, f"Could not send: {loi}"


# --- THE LISTENER THREAD --------------------------------------------------

def _mot_luot(conn: sqlite3.Connection, tin: dict, chat_id: str, muc: str) -> None:
    """Handle ONE incoming message. Split out so it is testable without a
    network."""
    # THE PERMISSION GUARD BEFORE ANYTHING ELSE — even before reading the
    # content. Anyone can message a Telegram bot; this is the only fence.
    if not tele.duoc_phep(tin, chat_id):
        ai = ((tin.get("message") or {}).get("chat") or {}).get("id")
        jlog.warn(SYSTEM, f"dropped a Telegram message from an unknown chat "
                          f"({ai}) — not the pinned chat")
        return
    lenh, tham = tele.doc_lenh(tin)
    if not lenh:
        return
    if not tele.cho_phep_lenh(lenh, muc):
        tele.gui("The current control level does not allow that command. "
                 "Change it under Settings · Notifications on the machine.")
        return
    tele.gui(tra_loi(conn, lenh, tham))
    jlog.ok(SYSTEM, f"Telegram command: /{lenh}")


def nghe(dung) -> None:
    """The command listener — long polling, calling OUT only.

    `dung` is a threading.Event: set it and the loop exits. Runs on its own
    background thread, NOT shared with the scheduler: each long-poll sleeps
    for 25 seconds, and the scan must not sleep with it.

    The control level is re-read EVERY ITERATION, not once at startup:
    switching from "notify only" to "control" in Settings has to take effect
    at once, without restarting the app.
    """
    from .core import db
    offset = 0
    keu_lan_truoc = ""
    while not dung.is_set():
        try:
            c = cau_hinh_nghe()
            if not c:
                dung.wait(20)               # not connected, or the level is OFF
                continue
            ds, offset, loi = tele.nhan(offset)
            if loi:
                # ON FAILURE, BACK OFF, and shout ONCE per distinct reason:
                # half an hour without a network at one line every 30 seconds
                # turns the journal into rubbish and pushes the line worth
                # reading off the top.
                if loi != keu_lan_truoc:
                    jlog.warn(SYSTEM, f"the Telegram listener paused — {loi}")
                    keu_lan_truoc = loi
                dung.wait(60)
                continue
            keu_lan_truoc = ""
            if not ds:
                continue
            conn = db.connect()
            try:
                for tin in ds:
                    _mot_luot(conn, tin, c["chat_id"], c["muc"])
            finally:
                conn.close()
        except Exception as exc:            # noqa: BLE001
            # Never let this thread die: it is the only remote-control path,
            # and dying quietly means the user messages forever and nobody
            # answers.
            jlog.error(SYSTEM, f"the Telegram listener failed — "
                               f"{type(exc).__name__}: {str(exc)[:60]}")
            dung.wait(30)


def cau_hinh_nghe() -> dict | None:
    """{chat_id, muc} while genuinely listening; None if not connected or
    the level is OFF."""
    from .core import db
    if not tele.da_noi():
        return None
    conn = db.connect()
    try:
        muc = prefs.get(conn, prefs.BAO_MUC) or tele.TAT
    finally:
        conn.close()
    if muc == tele.TAT:
        return None
    return {"chat_id": str(tele.cau_hinh().get("chat_id", "")).strip(),
            "muc": muc}
