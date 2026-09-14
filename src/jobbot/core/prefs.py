"""APP preferences — remembered across restarts.

Not the same as profile_answer: that is the USER's profile (versioned, with
history). These are just switches belonging to the app itself, and they need
no history.

A failed read returns the default. One unreadable switch must never be the
reason the app will not open.
"""

from __future__ import annotations

import sqlite3

# Scan as soon as the app opens. OFF BY DEFAULT, deliberately: opening the
# app and having it launch Chrome to scrape LinkedIn before the user has even
# reached Settings is wrong. They turn it on when they decide they are
# configured.
AUTORUN = "autorun"

# The three knobs a user actually changes. Everything else stays in the code
# — offering a knob nobody wants to turn is clutter, not choice.
SCAN_EVERY = "scan_every_min"    # rescan every N minutes
HOURS_FROM = "hours_from"        # Chrome only runs inside this window
HOURS_TO = "hours_to"

# LinkedIn PACE. This is the real performance knob of the scan, and it is a
# TRADE-OFF knob, not a "free speed" knob: going faster means calling more
# often, and LinkedIn is the one host this app is a guest of.
#
# Why not "run several tabs in parallel": N tabs at pace P is identical to 1
# tab at pace P/N — the same calls per second, the same throttling risk.
# Parallelism is just a more complicated way of writing a smaller number,
# plus N Chrome windows eating RAM and N places to die half-way.
PACE = "linkedin_pace"

# ON/OFF per source. The two ways of searching produce very different
# postings — a company board gives the full description for free (22
# seconds), LinkedIn needs a page opened per posting and costs half an hour —
# so sometimes you only want one.
#
# BOTH ON BY DEFAULT. A source silently off is the worst kind of failure: the
# scan finishes with far fewer postings and nobody knows why.
SRC_BOARD = "src_board"
SRC_LINKEDIN = "src_linkedin"

# ... and each ATS on its own. These three providers yield very different
# postings (measured on the real store, 12 Sep: greenhouse 1,520 fetched, 82
# kept; lever 442 / 18; ashby 600 / 6, but 523 with a genuine remote flag).
# Anyone for whom one source is all noise can switch it off outright instead
# of putting up with it every hour.
SRC_ATS = {"greenhouse": "src_greenhouse", "lever": "src_lever",
           "ashby": "src_ashby"}

# LinkedIn job-alert emails landing in the mailbox. The third source, and the
# only one that touches nobody's Terms — mail sent to you is yours to read.
SRC_ALERT = "src_alert"

# The (title × place) PAIRS that have been fully scanned at least once, JSON.
#
# The unit of scanning is the PAIR, not the whole grid. One fingerprint for
# the whole grid is too coarse: dropping a title would force a full rescan,
# and dropping a title cannot produce anything new. Remembering per pair
# reduces the rule to a single sentence —
#
#     a pair never scanned gets scanned fully, a pair already scanned only
#     gets asked for what is new.
#
# And both of those run in the SAME pass.
LI_DONE = "li_done"

# The seniority levels (the f_E parameter) of the previous scan. It applies
# to EVERY pair, so it cannot live inside the pair key. WIDENING the levels
# makes every pair uncovered again; NARROWING does not, because narrowing
# cannot produce a new posting.
LI_LEVELS = "li_levels"

# How many days of mail to re-read on a mailbox pass. Default 30: enough to
# catch a reply to an application sent last month without dragging the whole
# mailbox down.
MAIL_DAYS = "mail_days"

# --- THREE SOURCES, BUT A DIFFERENT QUESTION -----------------------------
#
# `SRC_*` above asks: do we SCAN this source.
# `NOP_*` below asks: do we APPLY to postings from this source.
#
# Same three names, two entirely different jobs, so two sets of switches —
# each tab asks its own question. Merge them and switching LinkedIn off to
# stop applying also removes 2,409 postings from the store, and the user
# cannot work out why Search is empty.
#
# LINKEDIN IS NOT SWITCHED OFF WHOLESALE. Most LinkedIn postings lead to the
# company's own application page (see apply/linkedin.py) — those apply
# normally. Only postings that FORCE applying inside LinkedIn are out of
# reach; they get their own label and a manual path, rather than dragging the
# whole source down with them.
NOP_BOARD = "nop_board"
NOP_LINKEDIN = "nop_linkedin"
NOP_ALERT = "nop_alert"
NOP = {NOP_BOARD: ("board", "the company's own careers page — applies directly"),
       NOP_LINKEDIN: ("linkedin", "LinkedIn postings; the ones that lead out "
                      "to the company site can be applied to, the ones that "
                      "force LinkedIn's own form are left to you"),
       NOP_ALERT: ("alert", "postings that arrived in a job-alert email")}

# --- NOTIFICATIONS TO YOUR PHONE ----------------------------------------
#
# notify.py's founding rule still holds: NOTIFY RARELY. Notify often and the
# user switches it off, and the one message that mattered goes with it.
#
# So four kinds, no more, and each has to answer "what would I do
# differently for knowing this":
#
#   tiep  someone moved you forward — measured on the real mailbox: once in
#         60 days. The rarest and the most important. Knowing early means
#         replying early.
#   hong  a stage of the session failed — LinkedIn blocked, app password
#         revoked. A SILENT FAILURE is the worst kind: the machine sits
#         still for days while the board stays green, and the user only
#         notices when nothing new has arrived for too long.
#   cho   the queue has piled past a threshold — work waiting on a person,
#         and nobody else will do it.
#   ngay  the end-of-day report — today's four numbers.
#
# NO "finished scanning 515 postings". That is news about the machine, not
# news about the job search.
BAO_TIEP = "bao_tiep"
BAO_HONG = "bao_hong"
BAO_CHO = "bao_cho"
BAO_NGAY = "bao_ngay"
BAO = {BAO_TIEP: ("Someone moved you forward",
                  "An interview invitation or an offer just arrived. The "
                  "rarest and the most worth knowing — knowing early means "
                  "replying early."),
       BAO_HONG: ("A session failed",
                  "A stage could not run: LinkedIn blocked it, the app "
                  "password was revoked, the network dropped. A silent "
                  "failure means the machine sits idle for days with nothing "
                  "on screen saying so."),
       BAO_CHO: ("The queue is piling up",
                 "Mail the machine could not settle is stacking up, waiting "
                 "on your decision."),
       BAO_NGAY: ("End-of-day report",
                  "Today's four numbers: found, applied, moved forward, "
                  "rejected. Sent once, at the hour you choose.")}

# The threshold for `cho`: how many items have to pile up before it messages
# you. Below that it is not worth interrupting — the user sees it whenever
# they open the app.
BAO_NGUONG = "bao_nguong"
BAO_GIO = "bao_gio"          # what hour to send the end-of-day report (0-23)

# HOW FAR NOTIFICATIONS HAVE GOT — the id of the last mail already sent to
# the phone. Without it, every scan re-sends the same old mail and the user
# switches notifications off after exactly two days.
BAO_MOC = "bao_moc"
BAO_NGAY_CUOI = "bao_ngay_cuoi"   # which date the daily report was sent for

# REMOTE CONTROL LEVEL. The valid values live in core/tele.py (TAT / XEM /
# DAY_DU). Default TAT: a bot that starts accepting commands the moment it
# connects opens a door before the user has understood where it leads.
BAO_MUC = "bao_muc"


# THE ACCENT COLOUR of the whole app. The valid values and the palette live
# in dashboard/mau.py — only the KEY lives here, because core is not allowed
# to know anything about drawing.
MAU = "mau_nhan"


# --- A SESSION: THREE STAGES, ONE LOOP ----------------------------------
#
# Home is a 24/7 station. A SESSION is one pass through the whole pipeline,
# and these three switches say which stages it contains.
#
# THE ORDER IN THE DICT IS THE ORDER OF EXECUTION, not an accident: search
# first (that is what fills the store), build CVs second (they are laid out
# against what is in the store), read mail last (it updates the table
# according to what was applied to). Reverse it and the CV pass is laying out
# against the previous loop's store.
#
# WHY EACH STAGE MUST BE SWITCHABLE: the three cost wildly different amounts.
# Reading mail 12 seconds, building CVs 5.3 seconds, and scanning LinkedIn
# needs Chrome and half an hour. Someone who only wants the mailbox watched
# overnight turns the other two off, instead of choosing between "run
# everything" and "run nothing".
#
# ALL THREE ON BY DEFAULT. A stage silently off is the worst kind of failure:
# the session runs all night and in the morning there is no new CV, and
# nobody can work out why.
PHIEN_SEARCH = "phien_search"
PHIEN_CV = "phien_cv"
PHIEN_MAIL = "phien_mail"
PHIEN = {PHIEN_SEARCH: ("search", "Search",
                        "find new postings on company boards and LinkedIn, "
                        "filter them, score them. The most expensive stage: "
                        "it has to open Chrome."),
         PHIEN_CV: ("cv", "Make CV",
                    "re-lay the CV against each posting in the store. Writes "
                    "no new sentences — only picks and orders the ones you "
                    "wrote."),
         PHIEN_MAIL: ("track", "Manage mail",
                      "read the mailbox and update the Manage table. Read "
                      "only; it touches nothing in your mailbox.")}


# --- THE MANAGE LAYER'S KNOB --------------------------------------------
#
# HOW MANY DAYS OF SILENCE COUNTS AS A REJECTION.
#
# This is the knob that turns a pile of "don't know" into "done" — and
# without it the table only ever grows: measured on the real mailbox, 28 of
# 37 applications never received a single word back. They sat at "waiting"
# forever, and "waiting" after 40 days is a polite lie.
#
# THIS NUMBER IS AN INFERENCE, NOT A FACT — so it is NOT written to the
# `stage` column. It is recomputed every time the table is read; drop it to
# 10 and raise it back to 45 and every row returns to where it was. Writing
# it down would make it a one-way street, and one day a reply arriving on day
# 31 will land on a row that was closed permanently.
IM_QUA = "im_qua"

# Five steps, and each has to answer "what changes if I pick this" — not a
# 1..365 slider for the user to guess with.
IM_MUC = ("10", "14", "20", "30", "45")

# --- THE CV LAYER'S TWO KNOBS -------------------------------------------
#
# TWO, no more. Each knob has to answer "what does turning it change about
# the CV" with a number — a knob that cannot is decoration, and one
# decorative knob costs the user their trust in the whole panel.
#
# SEVEN KNOBS WERE REMOVED, and here is why each one went:
#
#   keyword density  turning it to "dense" changed EXACTLY 0 of 60 builds. It
#                    also rests on something that does not exist: no ATS
#                    vendor publishes a "keyword density" formula.
#   tone of voice    6 of 26 sentences had a subject to drop. Dropping the
#                    subject is a CV convention everyone follows — offering
#                    it as a choice is asking a question nobody wants.
#   layout           changed 19 -> 22 builds, but "how many lines per block"
#                    is a typesetter's question, not a job-seeker's.
#   keep failure lines · keep opinion lines · keep lines that invite doubt ·
#   keep the soft-skills section · keep every experience block
#                    five switches that reverse five RULES. The rules are
#                    right in most cases and have measurements behind them;
#                    offering them as switches forces the user to learn five
#                    rules before they can use the app. They now run fixed at
#                    the measured defaults, and the report (report.py) still
#                    states exactly which sentence was dropped and why.
#
# The user needs exactly two things: how far the CV is tailored per posting,
# and whether the machine handles what it can handle on its own.

CV_RIENG = "cv_rieng"
RIENG = {"chung": "one shared version across many postings",
         "vua": "order the skills section per posting",
         "rieng": "order the items inside each section too"}

# SELF-DRIVING — the machine does everything it can do without being asked.
#
#   1  every WRITE-labelled gap gets a draft prepared, waiting for evidence
#   2  changing a CV sentence rebuilds every version at once, in the background
#
# The ONE part the machine cannot do for you is the number: how many, over
# how much data, how much it moved. The machine does not know what the user
# did, and a line on a CV is a line they have to stand behind in the room.
#
# This IS part of the freshness stamp (`cv/batch.stamp`): it decides whether
# a build ships with drafts, so flipping it genuinely makes existing builds
# stale.
CV_TU_LO = "cv_tu_lo"


DEFAULTS = {AUTORUN: "0", SCAN_EVERY: "60",
            HOURS_FROM: "8", HOURS_TO: "22", PACE: "thuong",
            SRC_BOARD: "1", SRC_LINKEDIN: "1", SRC_ALERT: "1", LI_DONE: "", LI_LEVELS: "", MAIL_DAYS: "30",
            NOP_BOARD: "1", NOP_LINKEDIN: "1", NOP_ALERT: "1",
            CV_TU_LO: "0", CV_RIENG: "rieng", IM_QUA: "20",
            PHIEN_SEARCH: "1", PHIEN_CV: "1", PHIEN_MAIL: "1", MAU: "la",
            BAO_TIEP: "1", BAO_HONG: "1", BAO_CHO: "0", BAO_NGAY: "0",
            BAO_NGUONG: "10", BAO_GIO: "20", BAO_MUC: "tat",
            BAO_MOC: "0", BAO_NGAY_CUOI: "",
            **{k: "1" for k in SRC_ATS.values()}}


def get(conn: sqlite3.Connection, key: str) -> str:
    try:
        row = conn.execute("SELECT value FROM pref WHERE key = ?", (key,)).fetchone()
    except Exception:                       # noqa: BLE001
        return DEFAULTS.get(key, "")
    return row[0] if row else DEFAULTS.get(key, "")


def flag(conn: sqlite3.Connection, key: str) -> bool:
    return get(conn, key) == "1"


def put(conn: sqlite3.Connection, key: str, value: str) -> None:
    try:
        conn.execute("INSERT INTO pref (key, value) VALUES (?,?)"
                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, str(value)))
        conn.commit()
    except Exception:                       # noqa: BLE001
        pass


def set_flag(conn: sqlite3.Connection, key: str, on: bool) -> None:
    put(conn, key, "1" if on else "0")


def num(conn: sqlite3.Connection, key: str, low: int, high: int) -> int:
    """An integer inside a range. A broken value falls back to the default
    rather than raising.

    Whatever the user types into a box must not be able to kill the
    background scan.
    """
    try:
        value = int(get(conn, key))
    except (TypeError, ValueError):
        value = int(DEFAULTS.get(key, low))
    return max(low, min(high, value))
