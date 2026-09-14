"""The numbers for the Home tab — ONE place computes them, not scattered
through the rendering.

Home has no work of its own. It reads back the other four tabs' work and
answers the four questions no single tab can answer from inside itself:

    THE FUNNEL   where things fall away — how many found, kept, applied to,
                 answered
    RESULTS      what percentage moved forward, what percentage was rejected
    PRODUCTIVITY how much gets done per day, and how evenly
    DIAGNOSIS    what is broken, and how sure we are

THE BIGGEST RULE IN THIS FILE: NEVER INVENT A DATA SERIES.

The app has been running for a few days. A 30-day chart with 28 zero columns
is not "honest data" — it READS as "productivity collapsed", while the truth
is the app did not exist on those days. So every series here carries THE
NUMBER OF REAL DAYS, and anywhere there is not enough to conclude, it says so
rather than drawing an empty grid and leaving the reader to misread it.

READ ONLY. It writes nothing and decides nothing.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

# How many days are enough to say "even or uneven".
#
# BY WEEKDAY needs at least three weeks: over two weeks each weekday has two
# points, and with two points anything looks like a "trend". BY MONTH needs
# two months, because one month compares with nothing.
DU_NGAY = 21
DU_THANG = 2

# At or above this score the machine calls a posting WORTH applying to. The
# same threshold as the Apply button in Manage (live.track_stage) — two
# thresholds in two places means Home eventually says 130 postings are worth
# applying to while pressing Apply says there are none.
DIEM_DANG_NOP = 80

# The two mail kinds that carry an OUTCOME. Declared once and used by both
# the «today» bar and the daily strips — defining "moved forward" twice means
# the two numbers eventually disagree.
TIEP = ("interview", "offer")
FAIL = ("rejected",)


def _ngay(x) -> str:
    return str(x or "")[:10]


def _hom_nay() -> date:
    return datetime.now(timezone.utc).date()


def _chuoi(conn: sqlite3.Connection, bang: str, cot: str, ngay: int,
           loc: str = "") -> dict:
    """{date: count} for the last `ngay` days. A day with nothing has NO key.

    Returned sparse (only days with a value) rather than padded with zeros:
    that is how the renderer can tell "0 done that day" from "the app was not
    running that day" — two entirely different things, and merging them is
    the origin of the lying chart.
    """
    tu = (_hom_nay() - timedelta(days=ngay - 1)).isoformat()
    them = f" AND {loc}" if loc else ""
    return {_ngay(r[0]): r[1] for r in conn.execute(
        f"SELECT substr({cot},1,10) d, COUNT(*) FROM {bang}"
        f" WHERE {cot} IS NOT NULL AND substr({cot},1,10) >= ?{them}"
        f" GROUP BY d", (tu,))}


def _khoang(conn: sqlite3.Connection, bang: str, cot: str,
            loc: str = "") -> tuple:
    """(first day, last day, how many DISTINCT days have a value) for a table."""
    them = f" AND {loc}" if loc else ""
    r = conn.execute(
        f"SELECT MIN(substr({cot},1,10)), MAX(substr({cot},1,10)),"
        f" COUNT(DISTINCT substr({cot},1,10)) FROM {bang}"
        f" WHERE {cot} IS NOT NULL AND {cot} <> ''{them}").fetchone()
    return (r[0] or "", r[1] or "", r[2] or 0)


# ----------------------------------------------------------------- TODAY

# Four numbers for TODAY ALONE. The bar on Home is TODAY'S BULLETIN, not a
# summary — the summary is in the four panels below, and a number like "37
# applied" looks the same every day, so it cannot say whether the app is
# working.
#
# The last two come from MAIL, not from the `stage` column: "what news
# arrived today" is a question about mail that arrived today. The stage column
# changes when the user presses Accept, possibly three days later, and would
# then land on that day instead.
def hom_nay(conn: sqlite3.Connection) -> dict:
    t = _hom_nay().isoformat()

    def m(sql, *a) -> int:
        try:
            return conn.execute(sql, a).fetchone()[0] or 0
        except Exception:                   # noqa: BLE001
            return 0

    def thu(loai) -> int:
        cho = ",".join("?" * len(loai))
        return m(f"SELECT COUNT(*) FROM message WHERE kind IN ({cho})"
                 f" AND substr(received_at,1,10) = ?", *loai, t)

    return {"ngay": t,
            "tim": m("SELECT COUNT(*) FROM raw_posting"
                     " WHERE substr(fetched_at,1,10) = ?", t),
            "nop": m("SELECT COUNT(*) FROM application"
                     " WHERE substr(applied_at,1,10) = ?", t),
            "tiep": thu(TIEP), "truot": thu(FAIL)}


# ---------------------------------------------------------------- FUNNEL

def pheu(conn: sqlite3.Connection) -> dict:
    """Drop-off through each stage. TWO segments, and the join must be honest.

    The SEARCH segment runs from postings fetched to postings worth applying
    to — that is Search's work.
    The APPLY segment runs from applications sent to callbacks — that is
    Manage's work.

    They are NOT one continuous funnel. Most of the user's applications
    predate the app (rebuilt from mail), so there is no original posting to
    join them to. Drawn as one run, the "applied" number looks like the
    consequence of the "worth applying to" number, when in fact the two are
    almost disconnected. The join is returned separately in `noi`.
    """
    def m(sql, *a) -> int:
        return conn.execute(sql, a).fetchone()[0] or 0

    ve = m("SELECT COUNT(*) FROM raw_posting")
    giu = m("SELECT COUNT(*) FROM posting WHERE kept = 1")
    that = m("SELECT COUNT(*) FROM posting WHERE kept = 1"
             " AND realism IN ('likely','possible')")
    dang = m("SELECT COUNT(*) FROM posting WHERE kept = 1"
             " AND realism IN ('likely','possible') AND score >= ?",
             DIEM_DANG_NOP)
    da_nop_kho = m(
        "SELECT COUNT(*) FROM posting p WHERE p.kept = 1"
        " AND p.realism IN ('likely','possible') AND p.score >= ?"
        " AND p.id IN (SELECT posting_id FROM application"
        "              WHERE posting_id IS NOT NULL)", DIEM_DANG_NOP)
    return {
        "tim": [("postings fetched", ve, "/search"),
                ("kept after filtering", giu, "/search"),
                ("actually applicable", that, "/search"),
                (f"worth applying to (score ≥{DIEM_DANG_NOP})", dang, "/search")],
        "dang": dang,
        "cho_nop": dang - da_nop_kho,
        "noi": da_nop_kho,
    }


# --------------------------------------------------------------- RESULTS

def ket_qua(conn: sqlite3.Connection) -> dict:
    """% forward · % rejected · % that replied, with the DENOMINATOR and the
    SAMPLE SIZE.

    A ratio with no denominator is an empty statement: "2.7%" of 37
    applications and "2.7%" of 3,700 applications are entirely different
    truths, and the percentage alone cannot tell them apart.

    TWO denominators, because they answer two questions:
        over the TOTAL     37 applications, how many called back — the number
                           for the whole process
        over the SETTLED   excluding what is still waiting — the number for
                           what is finished
    """
    from ..track import board
    rows = [r for r in board.all(conn) if r["stage"] != board.DRAFT]
    tong = len(rows)
    di = sum(1 for r in rows if r["stage"] in (board.INTERVIEW, board.OFFER))
    ho_noi = sum(1 for r in rows if r["stage"] == board.REJECTED)
    suy = sum(1 for r in rows if r.get("song") == board.SONG_IM)
    truot = ho_noi + suy
    hoi = sum(1 for r in rows if r.get("ho_tra_loi"))

    def pc(a, b):
        return round(a * 100 / b, 1) if b else None

    xong = di + truot
    return {"tong": tong, "di_tiep": di, "truot": truot, "ho_noi": ho_noi,
            "suy": suy, "cho": tong - xong, "hoi_am": hoi, "xong": xong,
            "pc_di": pc(di, tong), "pc_di_xong": pc(di, xong),
            "pc_truot": pc(truot, tong), "pc_hoi": pc(hoi, tong),
            "nguong_im": board.nguong(conn)}


# --------------------------------------------------------- PRODUCTIVITY

# FOUR METRICS — EXACTLY THE FOUR NUMBERS ON THE MASTER BAR, only per day
# rather than today alone. The bar says "how much today", the strips below say
# "and the days before" — the same question at two lengths.
#
# "MAIL RECEIVED" WAS DROPPED. Measured on the real mailbox: of 1,046
# messages, 991 fell into `other` — adverts, job alerts, signup
# confirmations. A strip of 687 messages that is 95% noise says nothing about
# anyone's productivity; it says the mailbox is busy. Replaced with the two
# OUTCOME numbers, which are what is worth watching daily.
#
# THEY ARE NOT ON ONE SCALE: a day's scan returns 4,651 postings against 4
# applications and 0 invitations. On a shared axis the lower three strips
# flatten into three lines. So each strip normalises to ITS OWN peak, and
# prints that peak in text.


def _la(loai) -> str:
    """The SQL condition filtering by mail kind. `loai` is a constant in the
    code, not user input — so it can be concatenated without a parameter."""
    return "kind IN (" + ",".join(f"'{x}'" for x in loai) + ")"


VIEC = (
    {"ma": "tim", "ten": "postings found", "bang": "raw_posting",
     "cot": "fetched_at", "loc": "", "di": "/search", "mau": "kho"},
    {"ma": "nop", "ten": "applications sent", "bang": "application",
     "cot": "applied_at", "loc": "", "di": "/track", "mau": "lam"},
    # `goc` = WHAT DEFINES "since when has the app been running" for this strip.
    #
    # Without it, the "moved forward" strip takes the day of the FIRST
    # INVITATION as its start, and every day before that is recorded as "the
    # app was not running" — plainly wrong: the mailbox ran for all 61 days,
    # there simply were no invitations. A day WITH NO CALLBACK is a real zero,
    # and it is the most worth-looking-at zero on this page.
    {"ma": "tiep", "ten": "moved forward", "bang": "message",
     "cot": "received_at", "loc": _la(TIEP), "di": "/track", "mau": "tot",
     "goc": ("message", "received_at")},
    # RED, not green. A tall column of rejections drawn in green reads as
    # "a good day" — colour here carries meaning, it is not decoration.
    {"ma": "truot", "ten": "rejections", "bang": "message",
     "cot": "received_at", "loc": _la(FAIL), "di": "/track", "mau": "xau",
     "goc": ("message", "received_at")},
)

THU = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def nang_suat(conn: sqlite3.Connection, ngay: int = 30) -> dict:
    """One daily strip per metric, with the number of REAL days and whether
    that is enough to conclude anything.

    `du_thu` / `du_thang` is where this file refuses to conclude. Grouping by
    weekday over two days of data yields "Friday is 9× as productive as
    Saturday" — arithmetically correct, completely wrong in meaning, and the
    reader has no way to know.
    """
    het = _hom_nay()
    lich = [(het - timedelta(days=i)).isoformat() for i in range(ngay - 1, -1, -1)]
    ra = {}
    for v in VIEC:
        ma, bang, cot, loc = v["ma"], v["bang"], v["cot"], v["loc"]
        chuoi = _chuoi(conn, bang, cot, ngay, loc)
        _d, _c, so_ngay = _khoang(conn, bang, cot, loc)
        # THE START comes from `goc` (the source), not from the filtered
        # strip itself — see the note on VIEC. A strip that declares no goc
        # is its own source.
        g_bang, g_cot = v.get("goc") or (bang, cot)
        dau, cuoi, _n = _khoang(conn, g_bang, g_cot)
        # COUNT ONLY FROM THE FIRST DAY WITH DATA. Before that the app was
        # not running, and counting those days as 0 drags your own average
        # down for no reason.
        song = [d for d in lich if dau and d >= dau]
        ra[ma] = {
            "ten": v["ten"], "di": v["di"], "mau": v["mau"],
            "cot": [(d, chuoi.get(d, 0)) for d in song],
            # Days INSIDE the window that fall BEFORE the first day with
            # data. The renderer needs this number to keep the frame width:
            # two days of data drawn as two columns filling the strip looks
            # like "there is always data", while the truth is the app has run
            # for two days.
            "truoc": len(lich) - len(song),
            "mep_trai": lich[0] if lich else "",
            "dinh": max(chuoi.values()) if chuoi else 0,
            "tong": sum(chuoi.get(d, 0) for d in song),
            "ngay_song": len(song),
            "ngay_co": so_ngay, "tu": dau, "den": cuoi,
            "tb": round(sum(chuoi.get(d, 0) for d in song) / len(song), 1)
            if song else 0,
        }

    # BY WEEKDAY and BY MONTH group over the WHOLE history, not the 30-day
    # window: both are questions about habit, and habit needs more than a
    # month.
    thu, thang = {}, {}
    for v in VIEC:
        ma, bang, cot = v["ma"], v["bang"], v["cot"]
        them = f" AND {v['loc']}" if v["loc"] else ""
        d_thu = [0] * 7
        for r in conn.execute(f"SELECT substr({cot},1,10) d, COUNT(*) FROM {bang}"
                              f" WHERE {cot} IS NOT NULL AND {cot} <> ''{them}"
                              f" GROUP BY d"):
            try:
                d_thu[date.fromisoformat(r[0]).weekday()] += r[1]
            except (TypeError, ValueError):
                continue
        thu[ma] = d_thu
        thang[ma] = {r[0]: r[1] for r in conn.execute(
            f"SELECT substr({cot},1,7) t, COUNT(*) FROM {bang}"
            f" WHERE {cot} IS NOT NULL AND {cot} <> ''{them}"
            f" GROUP BY t ORDER BY t")}

    # EACH SERIES GUARDS ITSELF; there is no shared number.
    #
    # Measured on the real store: the mail series has 61 days, the
    # postings-found series has 3. Using the largest as a shared gate draws
    # "postings found by weekday" over 3 days — and it says "Friday is 9×
    # Saturday". Arithmetically correct, completely wrong in meaning, and the
    # reader has no way to know.
    for ma in ra:
        ra[ma]["du_thu"] = ra[ma]["ngay_co"] >= DU_NGAY
        ra[ma]["du_thang"] = len(thang[ma]) >= DU_THANG
        ra[ma]["thang_co"] = len(thang[ma])
    return {"viec": ra, "lich": lich, "thu": thu, "thang": thang,
            "ten_thu": THU, "can_thu": DU_NGAY, "can_thang": DU_THANG,
            # The shared number ONLY says "how long the app has been
            # running"; it gates no series.
            "ngay_co": max((ra[v["ma"]]["ngay_co"] for v in VIEC), default=0)}


# ------------------------------------------------------ IS SEARCH STEADY

def nhip_quet(conn: sqlite3.Connection) -> dict:
    """Is the scan running steadily, and which source has gone quiet.

    A QUIET SOURCE is something no other tab can see: Search only shows what
    it found, so a source failing silently just makes the results smaller
    without saying anything. Here it appears by name.
    """
    r = conn.execute("SELECT COUNT(*), SUM(ok), SUM(failed), SUM(new_rows),"
                     " COUNT(DISTINCT substr(started_at,1,10))"
                     " FROM source_run").fetchone()
    luot, ok, hong, moi, ngay = (r[0] or 0, r[1] or 0, r[2] or 0,
                                 r[3] or 0, r[4] or 0)
    cam = [x[0] for x in conn.execute(
        "SELECT source FROM source_run GROUP BY source"
        " HAVING SUM(new_rows) = 0 OR SUM(ok) = 0 ORDER BY source")]
    loi = [dict(nguon=x[0], khi=_ngay(x[1]), vi_sao=(x[2] or "")[:90])
           for x in conn.execute(
               "SELECT source, started_at, error FROM source_run"
               " WHERE ok = 0 ORDER BY started_at DESC LIMIT 4")]
    return {"luot": luot, "ok": ok, "hong_luot": luot - ok, "hong_tin": hong,
            "moi": moi, "ngay": ngay, "cam": cam, "loi": loi,
            "luot_moi_ngay": round(luot / ngay, 1) if ngay else 0,
            "pc_ok": round(ok * 100 / luot) if luot else None}


# ------------------------------------------------------------- DIAGNOSIS

# How CERTAIN a signal is. Showing a signal without saying how sure you are
# is the fastest way to send the user off fixing the wrong thing: a direct
# count (130 unapplied postings) and an inference over 5 samples must NOT
# look the same.
CHAC, VUA, YEU = "chac", "vua", "yeu"
MUC_HET = (CHAC, VUA, YEU)


def chan_doan(conn: sqlite3.Connection) -> list[dict]:
    """Signals of something broken, ORDERED BY CERTAINTY rather than drama.

    Each signal has to say: how many samples it measured, what it means, and
    where to click to fix it. Missing any of the three makes it a complaint,
    not a diagnosis.
    """
    from ..cv import batch
    ra = []
    p, k = pheu(conn), ket_qua(conn)

    # 1. A DIRECT COUNT — no inference at all, so the most certain.
    if p["cho_nop"] > 0:
        ra.append(dict(
            muc=CHAC, ma="cho_nop", so=f"{p['cho_nop']}",
            ten=f"{p['cho_nop']} worthwhile postings not applied to",
            y=f"The machine scored them ≥{DIEM_DANG_NOP} and judged them "
              f"genuinely applicable. This is the largest piece of work "
              f"waiting.",
            tren=f"a direct count over {p['dang']} worthwhile postings",
            di="/search", nut="Open the store"))

    # 2. ARE THE APPLICATIONS GOING TO THE RIGHT PLACES — only scoreable for
    #    applications linked to an original posting.
    diem = [r[0] for r in conn.execute(
        "SELECT p.score FROM application a JOIN posting p ON p.id = a.posting_id"
        " WHERE p.score IS NOT NULL")]
    ngoai = k["tong"] - len(diem)
    if diem:
        thap = [d for d in diem if d < DIEM_DANG_NOP]
        if thap:
            ra.append(dict(
                muc=VUA if len(diem) >= 5 else YEU, ma="nop_thap",
                so=f"{len(thap)}/{len(diem)}",
                ten=f"{len(thap)}/{len(diem)} scoreable applications are all "
                    f"below {DIEM_DANG_NOP}",
                y=f"The lowest is {min(thap)}. You are applying where the "
                  f"machine scores low while {p['cho_nop']} high-scoring "
                  f"postings sit untouched.",
                tren=f"{len(diem)} applications linked to an original posting "
                     f"— the other {ngoai} were applied to outside the app and "
                     f"cannot be scored",
                di="/track", nut="Open the table"))

    # 3. WHERE IT FALLS AWAY — did they read it at all, or read it and pass.
    if k["tong"] >= 10 and k["pc_hoi"] is not None:
        doc = k["pc_hoi"] >= 20
        ra.append(dict(
            muc=VUA, ma="roi",
            so=f"{k['pc_hoi']:g}%",
            ten=("People read it, and did not call" if doc
                 else "Most of them never replied at all"),
            y=(f"{k['hoi_am']} of {k['tong']} applications got a reply, and "
               f"only {k['di_tiep']} moved forward. The loss is at their "
               f"decision, not at the machine filter." if doc else
               f"Only {k['hoi_am']} of {k['tong']} applications ever got a "
               f"word back. Silence from the start usually means being cut by "
               f"the CV-reading machine."),
            tren=f"{k['tong']} applications",
            di="/cv", nut="Open the CV"))

    # 4. HOW MUCH OF THE STORE THE CV ANSWERS — the CV layer's own number.
    luu = batch.saved(conn) or {}
    hut = luu.get("hut") or {}
    if hut.get("tin"):
        nen, tin = hut.get("nen") or 0, hut["tin"]
        pc = round(nen * 100 / tin) if tin else 0
        if pc < 70:
            ra.append(dict(
                muc=CHAC, ma="phu", so=f"{pc}%",
                ten=f"The CV fully answers {nen}/{tin} postings",
                y=f"{tin - nen} postings ask for something no sentence on the "
                  f"CV mentions. Each sentence written in the right place "
                  f"moves this number up.",
                tren=f"{tin} tin trong kho",
                di="/cv/soan", nut="Edit blocks"))
    return ra


def tat_ca(conn: sqlite3.Connection, ngay: int = 30) -> dict:
    """The whole Home page in ONE read."""
    return {"hom_nay": hom_nay(conn), "pheu": pheu(conn), "ket_qua": ket_qua(conn),
            "nang_suat": nang_suat(conn, ngay), "nhip": nhip_quet(conn),
            "chan_doan": chan_doan(conn)}
