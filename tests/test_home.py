"""Test the Home tab — the overview.  python3 tests/test_home.py

The focus is NOT "does it draw a picture". It is: does the picture TELL THE
TRUTH.

A broken statistics page is not silent, it merely points the wrong way — and
the user goes off fixing the wrong thing without knowing. So most of the
checks here guard three things:

    · a day the app WAS NOT RUNNING has to differ from a day that PRODUCED 0
    · every ratio has to carry its denominator and its sample size
    · not enough data has to be SAID, never drawn as an empty grid
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "src"))

# RUNNING THIS FILE ALONE HAS TO WORK TOO.
#
# run_all.py builds a fake project root + a network lock for every test. But
# running one file on its own (python3 tests/test_web.py) has no such latch,
# and the checks asserting "the bot is not connected" go red — red because
# this machine has a config, not because the code is wrong. Worse: running
# alone could send real messages to the user's phone.
#
# Set RIGHT HERE, before any jobbot import, so there is no way around it.
import os as _os, tempfile as _tf, pathlib as _pl
_os.environ.setdefault("JOBBOT_OFFLINE", "1")
if "JOBBOT_ROOT" not in _os.environ:
    _gia = _tf.mkdtemp(prefix="jobbot-test-")
    _pl.Path(_gia, "config").mkdir(parents=True, exist_ok=True)
    _os.environ["JOBBOT_ROOT"] = _gia

from jobbot.core import db
from jobbot.dashboard import tongquan as T
from jobbot.dashboard.views import bieudo as bd
from jobbot.dashboard.views import home
from jobbot.track import board

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")


def truoc(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def kho():
    """A fixture: 1 taken further · 1 they said no · 1 silent past the mark · 1 still open."""
    c = db.connect(":memory:")
    board.add(c, "Kappa Lab", "Quant", applied_at=truoc(9),
              stage=board.INTERVIEW)
    board.add(c, "Maven", "Quant", applied_at=truoc(30), stage=board.REJECTED)
    board.add(c, "Long Silence", "Quant", applied_at=truoc(40))
    board.add(c, "Just Applied", "Quant", applied_at=truoc(3))
    return c


print("\n[THE FUNNEL — two stages, and the join has to tell the truth]")
c = kho()
p = T.pheu(c)
check("the FIND stage has four steps", len(p["tim"]) == 4)
check("each step leads back to its own tab", all(b[2].startswith("/") for b in p["tim"]))
check("an empty store makes every step 0", all(b[1] == 0 for b in p["tim"]))
# The "worth applying" threshold has to MATCH the Apply button on Track. Two
# thresholds in two places and one day Home says 130 postings are worth
# applying to while pressing Apply reports none left.
_nop = (GOC / "src/jobbot/dashboard/live.py").read_text(encoding="utf-8")
check("the same score threshold as Track's Apply button",
      f"score >= {T.DIEM_DANG_NOP}" in _nop)

print("\n[RESULTS — every ratio has to carry its DENOMINATOR]")
k = T.ket_qua(c)
check("it counts 4 applications", k["tong"] == 4)
check("taken further = interview + offer", k["di_tiep"] == 1)
# REJECTED folds two things together while still keeping each: "they said so"
# and "we inferred it" are two different truths, and folding them without
# being able to split again loses that distinction.
check("rejected = they said no + treated as rejected", k["truot"] == 2)
check("and each kind is still separable", k["ho_noi"] == 1 and k["suy"] == 1)
check("the rest is UNKNOWN, never pushed into rejected", k["cho"] == 1)
check("the ratio over THE TOTAL", k["pc_di"] == 25.0)
check("and the ratio over WHAT HAS SETTLED differs from it", k["pc_di_xong"] == round(100 / 3, 1))
check("with the silence mark in use, to explain the figure",
      k["nguong_im"] == board.nguong(c))
_rong = T.ket_qua(db.connect(":memory:"))
check("nothing applied to -> the ratio is None, NOT 0%", _rong["pc_di"] is None)
check("and 0% is never printed in place of «no figure yet»",
      "0%" not in home._ket_qua(_rong))

_css = (GOC / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
print("\n[OUTPUT — each series GUARDS ITSELF]")
# This is a bug that really happened: the LONGEST series was used as a shared
# gate, so the "postings found by weekday" chart was drawn over 2 days of data
# and announced "Friday is nine times Saturday" — arithmetically right,
# entirely wrong in meaning.
c2 = db.connect(":memory:")
for i in range(60):                       # rejection mail: 60 days, easily enough to group
    c2.execute("INSERT INTO message (msg_id, from_addr, subject, received_at,"
               " snippet, kind) VALUES (?,?,?,?,?,?)",
               (f"m{i}", "a@b.c", "s", truoc(i), "", "rejected"))
board.add(c2, "X", "R", applied_at=truoc(1))   # applications: exactly 1 day
c2.commit()
n = T.nang_suat(c2)
check("the rejection series is long enough -> weekday grouping allowed", n["viec"]["truot"]["du_thu"])
check("the applications series at 1 day -> weekday grouping NOT allowed",
      not n["viec"]["nop"]["du_thu"])
check("the gate belongs to EACH series, not to one shared figure",
      n["viec"]["truot"]["du_thu"] != n["viec"]["nop"]["du_thu"])

print("\n[FOUR STRIPS = EXACTLY THE FOUR NUMBERS ON THE MASTER BAR]")
# The bar says "how much today produced", the strips below say "and how about
# the days before". One question at two lengths — so it has to be one set of
# numbers, not two different sets placed side by side.
_hn = T.hom_nay(c2)
check("four strips", len(n["viec"]) == 4)
check("and exactly the four keys of the «today» bar",
      set(n["viec"]) == set(_hn) - {"ngay"})
check("«mail in» was dropped — 95% of it is noise", "thu" not in n["viec"])
# COLOUR CARRIES MEANING. A tall column of REJECTION mail painted green reads
# as "a productive day", i.e. the exact opposite of the truth.
check("rejections take the BAD colour", n["viec"]["truot"]["mau"] == "xau")
check("taken further takes the GOOD colour", n["viec"]["tiep"]["mau"] == "tot")
check("and the CSS really paints them differently",
      ".spark.xau rect{fill:var(--bad)" in _css and ".spark.tot rect{" in _css)
# The two outcome strips are built from MAIL, so "when the app started"
# belongs to THE MAILBOX, not to the first rejection letter. Without this rule
# every day before the first invitation is recorded as "the app was not
# running" — while the mailbox ran throughout, and a day WHEN NOBODY CALLED is
# a real 0.
check("a day nobody called is a REAL 0, not «the app was not running»",
      n["viec"]["tiep"]["truoc"] == 0)
check("its start mark is THE MAILBOX's",
      n["viec"]["tiep"]["tu"] == n["viec"]["truot"]["tu"])
check("the enough-to-group threshold is stated as a number", n["can_thu"] == T.DU_NGAY)
# The series comes back SPARSE: a day with nothing has NO key. Filling in 0s
# mixes "produced 0" with "the app was not running" at the data layer itself.
_ch = T._chuoi(c2, "application", "applied_at", 30)
check("the day series comes back sparse, with no 0s filled in", len(_ch) == 1)
check("and it states how many days in the window the app was not running",
      n["viec"]["nop"]["truoc"] > 0)

print("\n[CHARTS — «produced 0» DIFFERS from «the app was not running»]")
h = bd.cot_ngay([("2026-09-01", 5), ("2026-09-02", 0)], 5, truoc=3)
check("a day the app was not running has its own class", h.count("class=ngoai") == 3)
check("a day that produced 0 has a DIFFERENT class", "class=khong" in h)
check("the two class names do not collide", "class=ngoai" in h and "khong" in h)
check("and the CSS really paints them differently",
      ".spark rect.ngoai{" in _css and ".spark rect.khong{" in _css)
check("every column carries a text label for hovering", h.count("<title>") == 5)
check("an empty series draws no empty frame", bd.cot_ngay([], 0) == "")
# Not enough data has to be SAID. An empty chart looks exactly like a
# "productivity is zero" chart, and the user will believe the second one.
_cd = bd.chua_du(2, 21)
check("not enough is said outright", "Not enough to say" in _cd)
check("and it states how many there are and how many are needed", ">2<" in _cd and ">21<" in _cd)
check("a ratio always carries its denominator",
      "1/37" in bd.ti_le(2.7, "1/37 applications", "taken further"))
check("with no figure it prints «—», never 0%", "—" in bd.ti_le(None, "x", "y"))
check("a 0 segment is NOT drawn, and gets no caption either",
      "qtu" not in bd.thanh_chia([("a", 3, "qdi"), ("b", 0, "qtu")], 3))

print("\n[DIAGNOSIS — it states HOW SOLID it is]")
ds = T.chan_doan(c)
check("every sign declares how solid it is", all(x["muc"] in T.MUC_HET for x in ds))
check("every sign declares how many samples it is measured over",
      all(x.get("tren") for x in ds))
check("and where to go to fix it",
      all(x.get("di", "").startswith("/") and x.get("nut") for x in ds))

print("\n[THE HOME PAGE — ONE screenful, with no panel scrolling]")
d = T.tat_ca(c)
_h = home.render({"gate_open": True}, so=d,
                 stage={"state": "x", "cho_ban": 3, "label": "Scan jobs"})
check("it has a stage bar like every tab", "class=deckpill" in _h)
check("it has a journal", "data-journal" in _h)
for _o in ("Results", "Output per day", "Diagnosis", "Funnel"):
    check(f"it has the «{_o}» panel", _o in _h)
# TWO DIFFERENT QUESTIONS, and the old test folded them into one exactly as
# the code did:
#   data-journal  = which stream's lines the journal panel SHOWS ("" = all)
#   data-reload   = which stage finishing REDRAWS the page ("*" = any)
# The old test asserted `"mine && m.stream === mine" in _js` and called that
# "it understands an empty stream as every stream" — while JavaScript reads
# the empty string as FALSE, so that branch never ran and Home NEVER redrew
# itself. The test guarded the very line causing the bug, and nodded at it.
check("the journal listens to EVERY stream", "data-journal=''" in _h)
check("and the page redraws when ANY stage finishes", "data-reload='*'" in _h)
_js = (GOC / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
check("live.js reads the page's flag rather than inferring from the journal panel",
      "dataset.reload" in _js and "mine && m.stream === mine" not in _js)
check("and «*» really does mean every stage", "=== '*'" in _js)
# A Home panel must NOT be a scroll frame: `.wbody{overflow:auto}` makes the
# panel's min-content 0, so the grid can squeeze it as far as it likes and the
# contents are left to scroll.
check("the four panels declare themselves CONTENT-SIZED, not scroll frames", _h.count("wid vua") == 4)
check("and the CSS removes the scroll frame for them", ".wid.vua > .wbody{overflow:visible" in _css)
check("the content rows have a min-content floor and cannot be squeezed",
      "minmax(min-content,auto)" in _h)
check("the journal is the ONLY panel taking the slack", "minmax(130px,1fr)" in _h)

print("\n[BRIEF AT A GLANCE, COMPLETE UNDER INSPECTION]")
check("the detail is hidden behind the ⤢ button", "class=chitiet" in _h)
check("and every panel has a ⤢ to open it", _h.count("data-expand") >= 4)
# SPECIFICITY HAS TO WIN: `.chitiet{display:none}` and `.cdrow{display:flex}`
# are both 0,1,0 — whichever is declared later wins, and `.cdrow` sits about
# 200 lines below. The result: a card carrying .chitiet still shows, failing
# SILENTLY.
check("the hiding class does not lose the cascade to .cdrow", ".cdrow.chitiet{display:none}" in _css)
check("enlarged it shows again", ".wid.big .cdrow.chitiet{display:flex}" in _css)
_nhieu = [dict(muc="chac", ma=f"m{i}", so=f"{i}", ten=f"sign {i}", y="y",
               tren="t", di="/cv", nut="Xem") for i in range(5)]
_cd5 = home._chan_doan(_nhieu)
check("collapsed it shows 3 signs", _cd5.count("cdrow chac'") == 3)
check("the other 2 carry the hiding class", _cd5.count("chac chitiet") == 2)
# Truncate without saying so and the user believes that is all there is.
check("and it SAYS how many more", "<b>2</b> more signs" in _cd5)
check("with exactly 3 it does not invent a «0 more» line",
      "more signs" not in home._chan_doan(_nhieu[:3]))

print("\n[THE MASTER BAR = TODAY'S BULLETIN]")
from jobbot.core import prefs
c3 = db.connect(":memory:")
board.add(c3, "Today", "R", applied_at=truoc(0))
board.add(c3, "Yesterday", "R", applied_at=truoc(1))
for i, (k, d) in enumerate((("interview", 0), ("rejected", 0), ("rejected", 5))):
    c3.execute("INSERT INTO message (msg_id, from_addr, subject, received_at,"
               " snippet, kind) VALUES (?,?,?,?,?,?)",
               (f"h{i}", "a@b.c", "s", truoc(d), "", k))
c3.commit()
hn = T.hom_nay(c3)
check("it counts applications sent TODAY, not the total", hn["nop"] == 1)
check("it counts invitations TODAY", hn["tiep"] == 1)
check("it counts rejections TODAY, dropping the one from 5 days ago", hn["truot"] == 1)
_trang = home.render({"gate_open": True}, so=T.tat_ca(c3),
                     stage={"phien": "the session is OFF",
                            "nhan_phien": "Start session"})
# CUT OUT JUST THE BAR. Searching the whole page also hits "applied" in the
# Funnel panel, and the test goes red for a reason with nothing to do with its
# own name.
_bar = _trang[_trang.index("<div class=deckpill>"):]
_bar = _bar[:_bar.index("</div></div>")]
for _n in ("postings found", "applications sent", "taken further",
           "rejections"):
    check(f"the bar has the «{_n}» figure", f">{_n}<" in _bar)
# The summary is already in the four panels below. Keep them on the bar too
# and the bar says something that looks the same whichever day you look, and
# it stops answering «what is new today».
# The OLD label was "<b>37</b>applied"; the NEW label is "applications sent"
# (today). Searching for "applied<" catches both — it has to be anchored to
# `</b>` to tell them apart.
for _cu in ("worth applying unapplied", "</b>applied<", "waiting on your decision", "Job store"):
    check(f"the bar NO LONGER has «{_cu}»", _cu not in _bar)
check("the button is renamed Start session", ">Start session<" in _bar)
check("and pressing it runs THE SESSION, not one stage",
      "data-post='/api/session/start'" in _bar)
check("the Stop button stops the whole session too", "data-post='/api/session/stop'" in _bar)
check("there is a ⚟ button for the session", "data-settings='/adjust/home'" in _bar)

print("\n[THE SESSION — one round, three stages, run in order]")
from jobbot import phien
check("three stages, in pipeline order",
      phien.dang_bat(c3) == ["search", "cv", "track"])
prefs.set_flag(c3, prefs.PHIEN_CV, False)
check("turning a stage off drops exactly that stage",
      phien.dang_bat(c3) == ["search", "track"])
# The order comes from prefs.PHIEN and is never retyped in phien.py —
# retyping is two sources for one truth, and one day the ⚟ panel lists one
# order while the session runs another.
check("the run order comes from THE SAME table as the ⚟ panel",
      [v[0] for v in prefs.PHIEN.values()] == ["search", "cv", "track"])
for k in prefs.PHIEN:
    prefs.set_flag(c3, k, False)
_ra = phien.chay(c3)
check("all three off and the session SAYS SO rather than running empty", _ra["tat"])
check("and no stage runs", _ra["xong"] == [])
_adj = home.adjust({k: False for k in prefs.PHIEN})
check("the ⚟ panel warns when all three are off", "All three are OFF" in _adj)
check("and it shows all three switches", _adj.count("/api/home/num") == 3)
for _t in ("Search", "Make CV", "Manage mail"):
    check(f"there is a «{_t}» switch", f">{_t}<" in _adj)
_adj_on = home.adjust({k: True for k in prefs.PHIEN})
check("turned on the button lights, not merely changes its text", "swbtn'" in _adj_on)
check("it states the fixed order and WHY",
      "Building CVs reads the posting store" in _adj_on)
c3.close()

print("\n[MESSAGES TO THE PHONE — message RARELY, and never repeat an old one]")
from jobbot import bao as _bao
from jobbot.core import tele as _tele, prefs as _pf2
c4 = db.connect(":memory:")
_ap = board.add(c4, "Kappa Lab", "Quant", applied_at=truoc(9))
for i, k in enumerate(("interview", "rejected", "other")):
    c4.execute("INSERT INTO message (msg_id, from_addr, subject, received_at,"
               " snippet, kind, application_id) VALUES (?,?,?,?,?,?,?)",
               (f"b{i}", "a@b.c", f"mail {k}", truoc(0), "", k, _ap))
c4.commit()
# ONLY A TAKEN-FURTHER message may be sent. Send rejections and marketing too
# and the user turns notifications off within two days, losing the one that
# mattered with them.
_moi = _bao._thu_moi(c4)
check("only TAKEN FURTHER mail is picked to message about", [m["kind"] for m in _moi] == ["interview"])
check("and it carries the company name, not just the subject",
      _moi[0]["cong_ty"] == "Kappa Lab")
# THE ALREADY-SENT MARK: without it every scan messages the same old letter again.
_pf2.put(c4, _pf2.BAO_MOC, str(_moi[0]["id"]))
check("already messaged -> NOT messaged again", _bao._thu_moi(c4) == [])
# With no bot connected, no function may send anything anywhere.
check("no bot connected -> nothing is sent", _bao.di_tiep(c4) == 0)
check("and no session-failure message either", not _bao.phien_hong(c4, ["search"]))
check("even with the switch turned on",
      _pf2.flag(c4, _pf2.BAO_TIEP) and not _bao.bat(c4, _pf2.BAO_TIEP))
# The end-of-day report is sent EXACTLY ONCE: the background loop runs every
# 30 seconds, and with no date mark it would message continuously from the
# chosen hour until midnight.
check("the daily report has a mark against repeating",
      _pf2.BAO_NGAY_CUOI in _pf2.DEFAULTS)
# Four kinds, no more — each has to answer "what would I do differently for
# knowing this".
check("exactly four kinds of notification", len(_pf2.BAO) == 4)
check("each kind has a name and a reason for the user to read",
      all(len(v) == 2 and v[0] and v[1] for v in _pf2.BAO.values()))
check("only the two MOST WORTHWHILE are on by default",
      [k for k in _pf2.BAO if _pf2.DEFAULTS[k] == "1"]
      == [_pf2.BAO_TIEP, _pf2.BAO_HONG])

print("\n[REMOTE COMMANDS — authorise FIRST, read the content after]")
check("an unknown command points the way rather than staying silent",
      "giupdo" in _bao.tra_loi(c4, "xyz", ""))
check("/giupdo states outright that there is NO apply command",
      "no apply command" in _bao.GIUP.lower())
check("/nhan with no number says what is missing",
      "Missing the mail number" in _bao.tra_loi(c4, "nhan", ""))
check("/nhan with an unknown number does not blow up, it reports not found",
      "not in the queue" in _bao.tra_loi(c4, "nhan", "99999"))
_tt = _bao.tra_loi(c4, "trangthai", "")
for _so in ("found", "applied", "forward", "rejected", "station"):
    check(f"/trangthai contains «{_so}»", _so in _tt)
c4.close()

print("\n[NO INVENTION — an empty store still has to draw]")
_r = db.connect(":memory:")
_hr = home.render({"gate_open": True}, so=T.tat_ca(_r), stage={})
check("an empty store does not blow the page up", "Overview" in _hr)
check("and it says outright that there is nothing to judge yet",
      "nothing applied to yet" in _hr)
check("it invents no ratio", "%" not in re.sub(r"width:[\d.]+%", "", _hr))
c.close(); c2.close(); _r.close()

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
