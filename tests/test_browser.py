"""Test the Chrome layer — WebSocket, CDP, and the safety rules.  python3 tests/test_browser.py

The parts needing a real Chrome skip themselves when Chrome is not running.
"""

import re, struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.browser import chrome, ws
from jobbot.ingest.web import base as webbase

ok = fail = skip = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}{' — ' + extra if extra else ''}")

print("\n[khung WebSocket]")
class FakeSock:
    def __init__(self): self.sent = b""
    def sendall(self, b): self.sent += b
    def settimeout(self, t): pass
    def close(self): pass

conn = ws.WebSocket.__new__(ws.WebSocket)
conn.sock, conn._buf = FakeSock(), b""
conn.send("hi")
frame = conn.sock.sent
check("bit FIN + opcode text", frame[0] == 0x81)
check("a client MUST mask", frame[1] & 0x80 == 0x80)
check("the length is right", (frame[1] & 0x7F) == 2)
mask, body = frame[2:6], frame[6:]
check("unmasking yields the right text",
      bytes(b ^ mask[i % 4] for i, b in enumerate(body)) == b"hi")

print("\n[the handshake: a frame in THE SAME packet as the 101 must not be lost]")
# Every test above goes around __init__ (using __new__), so none of them can
# see that __init__ assigns self._buf = b"" RIGHT AFTER _handshake — throwing
# away the very frame bytes _handshake had just kept. Chrome sending the 101
# and the first event in one TCP packet means a lost frame.
class HandshakeSock:
    """Returns the 101 and a 'hello' frame in ONE read."""
    RESPONSE = (b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\nConnection: Upgrade\r\n\r\n"
                + bytes([0x81, 5]) + b"hello")

    def __init__(self): self.sent, self.given = b"", False
    def sendall(self, b): self.sent += b
    def settimeout(self, t): pass
    def close(self): pass
    def recv(self, n):
        if self.given:
            return b""
        self.given = True
        return self.RESPONSE

made = HandshakeSock()
real_create = ws.socket.create_connection
ws.socket.create_connection = lambda *a, **k: made
try:
    live = ws.WebSocket("ws://127.0.0.1:9222/devtools/browser/abc")
    check("the handshake keeps the frame that came with it", live.recv() == "hello")
finally:
    ws.socket.create_connection = real_create

conn2 = ws.WebSocket.__new__(ws.WebSocket)
conn2.sock, conn2._buf = FakeSock(), bytes([0x81, 5]) + b"hello"
check("a server frame reads (unmasked)", conn2.recv() == "hello")

conn3 = ws.WebSocket.__new__(ws.WebSocket)
conn3.sock = FakeSock()
conn3._buf = bytes([0x01, 3]) + b"abc" + bytes([0x80, 3]) + b"def"
check("a fragmented frame is rejoined", conn3.recv() == "abcdef")

conn4 = ws.WebSocket.__new__(ws.WebSocket)
conn4.sock, conn4._buf = FakeSock(), bytes([0x81, 126]) + struct.pack(">H", 300) + b"x" * 300
check("a long payload reads (16-bit)", len(conn4.recv()) == 300)

print("\n[safety — cookies]")
js = webbase.REJECT_JS.lower()
check("NO 'accept' in the list of buttons to press", "accept all" not in js)
check("'reject' is there", "reject" in js)
check("'only necessary' is there", "only necessary" in js)
for word in ("agree", "allow all", "consent to", "i accept"):
    check(f"it never presses '{word}'", word not in js)

print("\n[safety — never argue with a block]")
for text in ("Just a moment...", "Attention Required! | Cloudflare",
             "Access Denied", "Verify you are human", "403 Forbidden"):
    check(f"a block is recognised: {text[:28]}", bool(webbase.BLOCKED.search(text)))
check("an ordinary page is NOT mistaken for one",
      not webbase.BLOCKED.search("Quantitative Analyst jobs in London | LinkedIn"))

print("\n[the deep-read pass must NOT reread what it already read]")
# THE ROOT of the whole step-1 chain of failures. On the real machine 194 of
# 196 LinkedIn postings already had a description, and the deep-read pass
# still reopened all of them — 97% of the work redone. That excess produced
# the rest: 17 minutes a round -> ~5,000 calls a day -> throttled 40-82% ->
# longer rests -> 12 job titles cut to 5. Fix one place and the chain
# dissolves.
from jobbot.ingest.web import linkedin as li
import jobbot.scan_runner as _sr_doc

class FakeTab:
    """Returns a list of 3 postings, and counts how many detail pages the deep-read pass opens."""
    def __init__(self): self.detail_opens = []
    def eval(self, js, timeout=None):
        if "show-more-less-html__markup" in js:      # DETAIL_JS
            return '[{"description":"' + "x" * 400 + '","criteria":""}]'
        return ('[{"title":"Quant Analyst","company":"A","location":"London",'
                '"url":"https://x/jobs/view/a-1000001","posted":""},'
                '{"title":"Data Scientist","company":"B","location":"London",'
                '"url":"https://x/jobs/view/b-1000002","posted":""},'
                '{"title":"Risk Analyst","company":"C","location":"London",'
                '"url":"https://x/jobs/view/c-1000003","posted":""}]')

real_open, real_pause = li.open_page, li._pause
opened = []
li.open_page = lambda tab, url, timeout=30: opened.append(url)
li._pause = lambda *a: None
try:
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True)
    all_read = sum(1 for u in opened if "jobPosting" in u)
    check("nothing known -> deep-read all 3", all_read == 3, f"read {all_read}")

    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True,
             skip=frozenset({"1000001", "1000002"}))
    again = sum(1 for u in opened if "jobPosting" in u)
    check("2 already read -> deep-read only the remaining 1", again == 1, f"read {again}")

    opened.clear()
    out = li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True,
                   skip=frozenset({"1000001", "1000002", "1000003"}))
    check("all already read -> it opens NO detail page",
          sum(1 for u in opened if "jobPosting" in u) == 0)
    check("but it still RETURNS every posting found", len(out[0]) == 3)
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[an update asks only for NEW postings — it does not rescan from scratch]")
# REALLY TRIED against the guest endpoint on 12/09:
#   f_TPR=r86400  WORKS   — 10/10 postings returned were from the last 24 hours
#   sortBy=DD     ignored — identical results to passing nothing
#   f_WT=2        ignored — (measured the day before, same shape)
# Each has to be tried: those two plausible-looking parameters do nothing at
# all, while the endpoint still returns 200 so it looks like it is working.
li.open_page = lambda tab, url, timeout=30: opened.append(url)
li._pause = lambda *a: None
try:
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False)
    check("a full scan does NOT carry a time window",
          not any("f_TPR" in u for u in opened))
    # THE WINDOW APPLIES ONLY TO A PAIR ALREADY COVERED. Ask only the last 24
    # hours for a pair never asked before and an old matching posting is never
    # found at all.
    _phu = frozenset({"Quant Analyst|United Kingdom"})
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False,
             recent=li.NGAY, covered=_phu)
    check("a pair ALREADY covered -> asks only the last 24 hours",
          all("f_TPR=r86400" in u for u in opened), str(opened[:1]))
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False,
             recent=li.TUAN, covered=_phu)
    check("after a few days off it widens to 7 days",
          all("f_TPR=r604800" in u for u in opened), str(opened[:1]))
    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False, recent=li.NGAY)
    check("a pair NOT yet covered -> asks in full, whatever the window",
          not any("f_TPR" in u for u in opened), str(opened[:1]))

    # BOTH SHAPES IN ONE PASS — this is the entire point of remembering by pair.
    opened.clear()
    _xong = set()
    li.fetch(FakeTab(), ["Quant Analyst", "Data Scientist"], pages=1, deep=False,
             recent=li.NGAY, covered=_phu, done_out=_xong)
    _day = [u for u in opened if "f_TPR" not in u]
    _hep = [u for u in opened if "f_TPR" in u]
    check("an old pair asks the window, a new pair asks in full — in one pass",
          len(_day) == 1 and len(_hep) == 1, f"{len(_day)} full / {len(_hep)} narrow")
    check("and only the pair just asked IN FULL is recorded as covered",
          _xong == {"Data Scientist|United Kingdom"}, str(_xong))
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[RESUME = finish reading what was left, NEVER search again]")
# "Resume" that still runs the search pass is only another word for "rescan
# from scratch": researching the identical 2,296 postings takes 30 minutes,
# only to then deep-read 11.
from jobbot.ingest.base import Posting as _P
li.open_page = lambda tab, url, timeout=30: opened.append(url)
li._pause = lambda *a: None
try:
    opened.clear()
    do_dang = [_P(source_id="1000001", title="Quant Analyst", company="A",
                  location="London", url="https://x/jobs/view/a-1000001")]
    suc = li.read_deep(FakeTab(), do_dang)
    check("read_deep runs ON ITS OWN, with no search pass", suc.attempted == 1)
    check("and it calls NO search page at all",
          not any("seeMoreJobPostings" in u for u in opened), str(opened[:2]))
    check("it opens exactly the detail page of the unfinished posting",
          sum(1 for u in opened if "jobPosting" in u) == 1)
    check("the description is patched straight onto that posting", len(do_dang[0].description) > 200)
    # THE SOURCE NAME IN THE JOURNAL HAS TO BE THE RIGHT SOURCE. The page is
    # still a LinkedIn page, but where the posting came from is another
    # matter: read 106 alert postings while the journal says "linkedin: 106
    # postings" and the user believes the LinkedIn scan is running, right
    # after they turned it off.
    from jobbot.core import journal as _jn
    _dong = []
    _that_emit = _jn.log.emit
    _jn.log.emit = lambda stream, text, **k: _dong.append(text)
    try:
        li.read_deep(FakeTab(), [_P(source_id="1000002", title="Q", company="A",
                                    location="London", url="https://x/b-1000002")],
                     ten="alert")
    finally:
        _jn.log.emit = _that_emit
    check("reading alert postings -> the journal says 'alert', NOT 'linkedin'",
          any(d.startswith("alert:") for d in _dong)
          and not any(d.startswith("linkedin:") for d in _dong), str(_dong[:3]))
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[the source switches: OFF has to really mean not running]")
# A source turned off that the scan still runs makes the switch decorative.
# Checked by counting how many API sources are actually called.
import tempfile as _tf, os as _os
from pathlib import Path as _P
with _tf.TemporaryDirectory() as _tmp:
    _cu_dir = _os.environ.get("JOBBOT_DATA_DIR")
    _cu_root_b = _os.environ.get("JOBBOT_ROOT")
    _os.environ["JOBBOT_DATA_DIR"] = _tmp
    # JOBBOT_ROOT: without it the test reads THE REAL config.toml, sees Vin's
    # mailbox connected, and turns the alert source on. A test has to run in a
    # world of its own, not depend on what somebody's machine has connected.
    (_P(_tmp) / "config").mkdir(exist_ok=True)
    _os.environ["JOBBOT_ROOT"] = _tmp
    try:
        from jobbot.core import db as _db, prefs as _pf
        from jobbot.core.paths import db_path as _dbp
        from jobbot.profile import store as _ps
        import jobbot.scan_runner as _sr
        # THE LATCH: a test must NOT touch the real DB. It happened once.
        assert str(_dbp()).startswith(_tmp), f"the test is pointing at THE REAL DB: {_dbp()}"
        _c = _db.connect()
        _ps.save(_c, {"job_titles": "Data Scientist", "markets": ["uk_onsite"],
                      "work_auth": "citizen", "location": "London"}, "t")
        _goi = []
        _that_run = _sr._run_source
        _that_chrome = _sr._chrome_pass
        _sr._run_source = lambda conn, name, fn, *a, log=None: (_goi.append(name), (0, 0))[1]
        _sr._chrome_pass = lambda *a, **k: (_goi.append("CHROME"), (0, 0))[1]
        try:
            _pf.set_flag(_c, _pf.SRC_BOARD, True)
            _pf.set_flag(_c, _pf.SRC_LINKEDIN, True)
            _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            check("both on -> boards and Chrome both run",
                  len(_goi) > 1 and "CHROME" in _goi, str(_goi[-3:]))

            _c = _db.connect(); _pf.set_flag(_c, _pf.SRC_BOARD, False); _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            # Alert mail has ITS OWN switch and does not sit under the board
            # switch — so turning boards off must not take it down too.
            check("boards off -> NO board is called",
                  not [g for g in _goi if ":" in g], str(_goi[:4]))

            # ONE ATS AT A TIME. The big switch and the small switches are two
            # layers; turning either off has to stop exactly that group, no
            # more and no less.
            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_BOARD, True)
            _pf.set_flag(_c, _pf.SRC_ATS["greenhouse"], False)
            _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            check("greenhouse off -> no greenhouse board is called",
                  not [g for g in _goi if g.startswith("greenhouse")],
                  str([g for g in _goi if g.startswith("greenhouse")][:3]))
            check("but lever/ashby still run",
                  any(g.startswith(("lever", "ashby")) for g in _goi),
                  str(_goi[:4]))
            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_ATS["greenhouse"], True)
            _c.close()

            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_BOARD, True)
            _pf.set_flag(_c, _pf.SRC_LINKEDIN, False)
            _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            # TURNING LINKEDIN OFF IS NOT TURNING CHROME OFF. Chrome is also
            # the route to a description for postings from ANOTHER source
            # (alert mail), and alert mail has a switch of its own. Merged,
            # turning one source off kills another — it really happened, with
            # 107 alert postings sitting unscored.
            check("LinkedIn off -> the Chrome pass STILL runs (it still reads other sources)",
                  "CHROME" in _goi, str(_goi[:4]))
            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_ALERT, False)
            _c.close()
            _goi.clear(); _sr.run_scan(manual=True, deep=False)
            # But with EVERY source needing a web page off, open no window at
            # all. Here _chrome_pass is replaced by a stub so it is still
            # called; the "no work means no Chrome" half is proved by the
            # RESUME test below.
            _c = _db.connect()
            _pf.set_flag(_c, _pf.SRC_ALERT, True)
            _pf.set_flag(_c, _pf.SRC_LINKEDIN, True)
            _c.close()
        finally:
            _sr._run_source, _sr._chrome_pass = _that_run, _that_chrome
    finally:
        for _k, _v in (("JOBBOT_DATA_DIR", _cu_dir), ("JOBBOT_ROOT", _cu_root_b)):
            if _v is None:
                _os.environ.pop(_k, None)
            else:
                _os.environ[_k] = _v

print("\n[remembering BY PAIR: never run the same thing twice]")
# The unit of a scan is A PAIR (job title × place), not the whole grid. A
# fingerprint over the whole grid is too coarse: removing one job title forces
# a full rescan, while removing one leaves nothing new to find.
_src = (Path(__file__).resolve().parent.parent
        / "src/jobbot/scan_runner.py").read_text(encoding="utf-8")
_than = _src.split("def _chrome_pass")[1]
_truoc = _than.split("prefs.put(conn, prefs.LI_DONE")[0].split("\n")[-8:]
_truoc = "\n".join(_truoc)
check("it only remembers when the run was HEALTHY", "health.ok" in _truoc, _truoc[-70:])
check("it ACCUMULATES rather than overwriting", "cu_phu | vua_phu" in _than)

print("\n[the call pace: the REAL performance knob, and it is a trade-off knob]")
# Why not "run N tabs in parallel": N tabs at pace P is identical to 1 tab at
# pace P/N — the same calls per second, the same throttling risk. Parallelism
# is only a more complicated way of writing a smaller number, plus N Chrome
# windows eating RAM and N places to die halfway.
check("three paces, no more", set(li.NHIP) == {"nhe", "thuong", "nhanh"})
check("the default is the old pace, changing no existing behaviour",
      li.NHIP["thuong"] == li.PAUSE)
check("fast calls more densely, gentle more sparsely",
      li.NHIP["nhanh"][1] < li.NHIP["thuong"][1] < li.NHIP["nhe"][1])
# An unknown pace (junk typed into the URL) must NOT become a 0-second pace.
_do = []
_that = li.time.sleep
li.time.sleep = lambda s: _do.append(s)
li.open_page = lambda tab, url, timeout=30: None
try:
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False, pace="madeup")
    check("an unknown pace -> falls back to the default, never 0 seconds",
          _do and min(_do) >= li.PAUSE[0], str(_do[:3]))
    _do.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=False, pace="nhanh")
    check("choosing 'fast' really does shorten the pace",
          _do and max(_do) <= li.NHIP["nhanh"][1], str(_do[:3]))
finally:
    li.time.sleep = _that
    li.open_page = real_open

print("\n[alert mail has to go the WHOLE pipeline, not stop at the fetch]")
# Alert mail and the Chrome scan point at exactly ONE page,
# /jobs/view/<id> — only the route that brought the id differs. With the
# deep-read pass looking only at source='linkedin', alert postings got half
# the pipeline: measured on 12/09, 195 postings in, the FILTER working
# correctly (110 kept / 85 dropped), but 0 with a description and 0 scored —
# and 181 of the 195 were jobs the Chrome scan did NOT find.
import tempfile as _tf2, os as _os2
from pathlib import Path as _P2
check("both sources share one deep-read pass",
      set(_sr_doc.DOC_KY) == {"linkedin", "alert"})
with _tf2.TemporaryDirectory() as _t2:
    _cu2 = _os2.environ.get("JOBBOT_DATA_DIR")
    _os2.environ["JOBBOT_DATA_DIR"] = _t2
    try:
        from jobbot.core import db as _db2, postings as _po2
        from jobbot.ingest.base import Posting as _P3
        _c2 = _db2.connect()
        assert str(_db2.paths.db_path()).startswith(_t2) if hasattr(_db2, "paths") else True
        for _ng in ("linkedin", "alert"):
            _po2.save_batch(_c2, _ng, [_P3(source_id="777", title="Quant",
                                           company="X", location="London",
                                           url="https://x/777", description="")])
        _c2.execute("UPDATE posting SET kept = 1")
        _c2.commit()
        _do = _sr_doc._tin_do_dang(_c2)
        check("an alert posting IS IN the deep-read queue", "alert" in _do, str(list(_do)))
        check("and it is split BY SOURCE, not thrown in one basket",
              set(_do) == {"linkedin", "alert"}, str(list(_do)))
        # save_batch writes by (source, id): merged and saved under one name
        # it creates a new row instead of patching the description onto the
        # existing one.
        check("exactly one posting per source", all(len(v) == 1 for v in _do.values()))
        # Read on one source and the other need not reopen it — the same page.
        _c2.execute("UPDATE posting SET description = ? WHERE raw_id IN"
                    " (SELECT id FROM raw_posting WHERE source='alert')",
                    ("x" * 300,))
        _c2.commit()
        check("read via alert mail and LinkedIn need not reopen it",
              "777" in _po2.already_read(_c2, _sr_doc.DOC_KY))
        _c2.close()
    finally:
        if _cu2 is None:
            _os2.environ.pop("JOBBOT_DATA_DIR", None)
        else:
            _os2.environ["JOBBOT_DATA_DIR"] = _cu2

print("\n[two sources, two switches: LinkedIn off and alert mail still runs in full]")
# "even though the alert also comes from linkedin, they are two different ways
# so they have to be two different sources, don't merge them, when i turn
# linkedin off it should just search from the alert email source"
#
# The whole Chrome region used to sit behind the linkedin switch, and the
# DEEP-READ pass was inside that region — so turning linkedin off left 107
# alert postings frozen: with a title, with a company, with no description and
# no score. This test really runs _chrome_pass with linkedin OFF and checks
# the description lands on the right alert row.
import tempfile as _tf4, os as _os4
with _tf4.TemporaryDirectory() as _t4:
    _cu4 = _os4.environ.get("JOBBOT_DATA_DIR")
    _cu4r = _os4.environ.get("JOBBOT_ROOT")
    _os4.environ["JOBBOT_DATA_DIR"] = _t4
    _os4.environ["JOBBOT_ROOT"] = _t4
    try:
        from jobbot.core import db as _db4, prefs as _pf4, postings as _po4
        from jobbot.ingest.base import Posting as _P4
        from jobbot.profile import store as _ps4
        from jobbot.browser import chrome as _ch4, cdp as _cdp4
        from jobbot.core.paths import db_path as _dbp4
        # THE LATCH: a test must NOT touch the real DB. It happened once.
        assert str(_dbp4()).startswith(_t4), f"the test is pointing at THE REAL DB: {_dbp4()}"

        _c4 = _db4.connect()
        _ps4.save(_c4, {"job_titles": "Quant Analyst", "markets": ["uk_onsite"],
                        "work_auth": "citizen", "location": "London"}, "t")
        # One ALERT MAIL posting with no description — exactly what alert mail brings in.
        _po4.save_batch(_c4, "alert", [_P4(
            source_id="1000001", title="Quant Analyst", company="A",
            location="London", url="https://x/jobs/view/a-1000001")])
        _c4.execute("UPDATE posting SET kept = 1")
        _c4.commit()
        _pf4.set_flag(_c4, _pf4.SRC_LINKEDIN, False)     # <- LinkedIn OFF
        _pf4.set_flag(_c4, _pf4.SRC_ALERT, True)
        _c4.commit()

        _kieu = _sr_doc.scan_mode(_c4)
        check("LinkedIn off with unfinished postings -> the button still offers Resume",
              _kieu["mode"] == _sr_doc.TIEP, f"{_kieu['mode']} · {_kieu['note']}")
        check("and it NO LONGER demands LinkedIn be turned on",
              "turn LinkedIn" not in _kieu["note"], _kieu["note"])
        check("alert mail is a source needing deep-read, independent of linkedin",
              _sr_doc.nguon_doc(_c4) == ("alert",), str(_sr_doc.nguon_doc(_c4)))

        _mo4, _dong4 = [], []
        _th_l, _th_s, _th_t = _ch4.launch, _ch4.shutdown, _cdp4.open_tab
        _th_w = _sr_doc.__dict__.get("in_human_window")
        class _Tab4(FakeTab):
            def close(self): _dong4.append(1)
        _ch4.launch = lambda **k: _mo4.append("launch")
        _ch4.shutdown = lambda: True
        _cdp4.open_tab = lambda *a, **k: _Tab4()
        li.open_page = lambda tab, url, timeout=30: opened.append(url)
        li._pause = lambda *a: None
        try:
            opened.clear()
            _s4, _n4 = _sr_doc._chrome_pass(_c4, _ps4.load(_c4),
                                            lambda _m: None, True, manual=True)
            check("LinkedIn OFF -> the deep-read pass STILL runs", _mo4 == ["launch"], str(_mo4))
            check("and it types NOT ONE keyword search",
                  not any("seeMoreJobPostings" in u for u in opened),
                  str([u for u in opened if "seeMore" in u][:2]))
            check("it opens exactly the alert posting's detail page",
                  sum(1 for u in opened if "jobPosting" in u) == 1, str(opened))
            _mo_ta = _c4.execute(
                "SELECT length(COALESCE(p.description,'')) FROM posting p"
                " JOIN raw_posting r ON p.raw_id = r.id"
                " WHERE r.source = 'alert'").fetchone()[0]
            check("the description lands on THE RIGHT alert row, no new linkedin row",
                  _mo_ta > 200, f"length {_mo_ta}")
            check("no linkedin source row is created",
                  _c4.execute("SELECT COUNT(*) FROM raw_posting WHERE source"
                              " = 'linkedin'").fetchone()[0] == 0)
            # vua_phu: this bug stayed hidden because `except Exception`
            # swallowed a NameError and then recorded the scan as FAILED while
            # the description had already been saved.
            _hong = _c4.execute("SELECT ok, error FROM source_run WHERE source"
                                " = 'alert' ORDER BY id DESC LIMIT 1").fetchone()
            check("and the run is recorded as HEALTHY, with no NameError",
                  _hong and _hong[0] == 1, str(tuple(_hong) if _hong else None))
            check("the tab is closed", _dong4 == [1], str(_dong4))

            # BOTH off -> no work needs a web page -> do not open Chrome.
            _c4.execute("UPDATE posting SET description = ''")
            _c4.commit()
            _pf4.set_flag(_c4, _pf4.SRC_ALERT, False)
            _c4.commit()
            _mo4.clear(); opened.clear()
            _sr_doc._chrome_pass(_c4, _ps4.load(_c4), lambda _m: None, True,
                                 manual=True)
            check("every source off -> NO Chrome window is opened", _mo4 == [],
                  str(_mo4))
        finally:
            _ch4.launch, _ch4.shutdown, _cdp4.open_tab = _th_l, _th_s, _th_t
            li.open_page, li._pause = real_open, real_pause
        _c4.close()
    finally:
        for _k4, _v4 in (("JOBBOT_DATA_DIR", _cu4), ("JOBBOT_ROOT", _cu4r)):
            if _v4 is None:
                _os4.environ.pop(_k4, None)
            else:
                _os4.environ[_k4] = _v4


print("\n[the deep-read is THE MOST EXPENSIVE part — only read postings that will be kept]")
# Measured on the real store: 2,389 LinkedIn postings, only 257 passing the
# sieve. 89% had their page opened, waited 2.5-5 seconds on, and were dropped
# immediately after — over two hours per scan thrown away.
#
# Filtering first works because judge() only touches the title/company/
# location, the three things the list page already provides; the description
# is the one thing that needs a page opened.
li.open_page = lambda tab, url, timeout=30: opened.append(url)
li._pause = lambda *a: None
try:
    opened.clear()
    tin, _ = li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True,
                      worth=lambda i: i.title == "Data Scientist")
    doc = [u for u in opened if "jobPosting" in u]
    check("only postings passing the sieve are deep-read", len(doc) == 1, f"read {len(doc)}/3")
    check("but it STILL returns every posting to save — the 'Dropped' pile is intact",
          len(tin) == 3, f"{len(tin)} tin")

    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True,
             worth=lambda i: False)
    check("the sieve rejecting everything -> no detail page opened",
          not [u for u in opened if "jobPosting" in u])

    opened.clear()
    li.fetch(FakeTab(), ["Quant Analyst"], pages=1, deep=True)
    check("passing no sieve -> deep-read everything, exactly as before",
          len([u for u in opened if "jobPosting" in u]) == 3)
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[cut off midway: KEEP what was already found]")
# It really happened at 17:18 on 11/09: 48 of 76 searches done, and a
# ConnectionResetError in the search pass flew straight out of fetch() —
# `items` was never returned, save_batch() never ran, and source_run recorded
# fetched=0. The whole store's worth was thrown away.
#
# Waking the machine from sleep hits EXACTLY this bug (a dead CDP socket), and
# the app runs 24/7, so it is everyday rather than a rare accident.
_dem = {"n": 0}
def _dut_o_lan_3(tab, url, timeout=30):
    _dem["n"] += 1
    if _dem["n"] >= 3:
        raise ConnectionResetError(54, "Connection reset by peer")
li.open_page = _dut_o_lan_3
li._pause = lambda *a: None
try:
    _tin, _suc = li.fetch(FakeTab(), ["Quant Analyst", "Data Scientist"],
                          location=["United Kingdom", ""], pages=1, deep=True)
    check("cut off, it still RETURNS what was found", len(_tin) == 3, f"{len(_tin)} postings")
    check("and it marks this scan NOT healthy", _suc.ok is False)
    check("it says CUT OFF, not BLOCKED",
          "CUT OFF" in _suc.summary and "BLOCKED" not in _suc.summary, _suc.summary)
    check("and it records the error's name for tracing later",
          "ConnectionResetError" in _suc.summary, _suc.summary)
    check("cut off it does NOT keep deep-reading — opening more only collects more errors",
          _dem["n"] <= 4, f"open_page called {_dem['n']} times")
finally:
    li.open_page, li._pause = real_open, real_pause

print("\n[a scan has to SAY what it is doing]")
# Measured on the 19:22 scan on 11/09: the SEARCH pass ran 31 minutes and left
# exactly one line, the DEEP-READ pass ran 27 minutes and left exactly one
# line. A progress bar moving with an empty journal leaves the user unable to
# tell which job title it is typing, which posting it is opening, or whether
# it hung long ago.
from jobbot.core.journal import SEARCH as _S, log as _jl
_nhip_that = li.NHIP_BAO
li.open_page = lambda tab, url, timeout=30: None
li._pause = lambda *a: None
li.NHIP_BAO = 2                      # 3 test postings is enough to hit the report tick
try:
    _truoc = len(_jl.tail(_S, 999))
    li.fetch(FakeTab(), ["Quant Analyst", "Data Scientist"],
             location=["United Kingdom", ""], pages=1, deep=True)
    _moi = [e.text for e in _jl.tail(_S, 999)[:len(_jl.tail(_S, 999)) - _truoc]]

    _tim = [t for t in _moi if t.startswith("search · ")]
    check("each search leaves one line (2 titles × 2 places)",
          len(_tim) == 4, f"{len(_tim)} lines: {_tim[:2]}")
    check("the line names the job title being typed",
          any("Quant Analyst" in t for t in _tim))
    check("and where it is searching", any("United Kingdom" in t for t in _tim))
    check("an empty place is named 'worldwide', not left as a dangling separator",
          any("worldwide" in t for t in _tim) and not any(t.endswith(" · ") for t in _tim))
    _doc = [t for t in _moi if t.startswith("deep-read ")]
    check("the deep-read pass reports as it goes", _doc, f"{_moi[:3]}")
    check("and the report names the posting being read",
          any("reading:" in t for t in _doc), f"{_doc[:2]}")
finally:
    li.NHIP_BAO = _nhip_that
    li.open_page, li._pause = real_open, real_pause

print("\n[the place is read from the profile, never a hardcoded string]")
check("uk_onsite + uk_remote -> United Kingdom (wider than London)",
      li.places_for(["uk_onsite", "uk_remote"]) == ["United Kingdom"])
check("duplicates dropped", len(li.places_for(["uk_onsite", "uk_remote", "uk_onsite"])) == 1)
check("global_remote -> empty, LinkedIn searches worldwide",
      li.places_for(["global_remote"]) == [""])
check("several markets -> several places",
      li.places_for(["uk_onsite", "us_remote"]) == ["United Kingdom", "United States"])
check("a profile choosing nothing -> there is still a default", li.places_for([]) == ["United Kingdom"])
check("NO hardcoded 'London' left in the signature",
      'location: str = "London"' not in Path("src/jobbot/ingest/web/linkedin.py").read_text())

print("\n[a job-title ceiling: there is one, but it has to be SAID]")
runner = Path("src/jobbot/scan_runner.py").read_text()
# Strip comment lines before examining — otherwise the very explanation of the
# bug just fixed turns this test red.
code_only = "\n".join(l for l in runner.split("\n")
                       if not l.strip().startswith("#"))
check("titles[:5] is gone from THE CODE", "titles[:5]" not in code_only)
check("but the explanation of why it went is kept", "titles[:5]" in runner)
li_src = Path("src/jobbot/ingest/web/linkedin.py").read_text()
check("the ceiling has a clear name", "MAX_QUERIES" in li_src)
check("and hitting it is journalled, never truncated silently",
      "searching only" in li_src and "jlog.warn" in li_src)

print("\n[closing Chrome: it has to REALLY close, and only the app's own]")
# THE REAL BUG: the old version called GET /json/close — that endpoint needs a
# target id, so it returned 404, the error was swallowed in an except, the
# function returned None and Chrome was still sitting there. A "close"
# function that closed nothing, running smoothly the whole time.
from jobbot.browser import chrome as ch
src_ch = Path("src/jobbot/browser/chrome.py").read_text()

def code_of(name, text=src_ch):
    """A function's body, WITHOUT comments and docstring — so the check does not
    trip over the explanation of the very bug it guards."""
    body = text.split(f"def {name}")[1]
    body = body.split("\ndef ")[0]
    body = re.sub(r'"""[\s\S]*?"""', "", body)
    return "\n".join(l for l in body.split("\n") if not l.strip().startswith("#"))

shut = code_of("shutdown")
check("it does NOT call the /json/close endpoint (needs a target id, returns 404)",
      "/json/close" not in shut)
check("it uses the CDP command Browser.close", "Browser.close" in shut)
check("over THE BROWSER's websocket", "webSocketDebuggerUrl" in shut)
check("shutdown returns a bool so the caller knows whether it closed",
      "-> bool" in src_ch.split("def shutdown")[1].split("\n")[0])
check("and it waits, rather than answering before it has closed", "alive(port)" in shut)
# A personal Chrome is also a "Google Chrome" process — killing BY NAME sweeps
# it up too, losing the user's own work. Killing a process WE SPAWNED
# (process.terminate() in launch) is fine.
check("it does NOT kill processes by name",
      not any(w in src_ch for w in ("pkill", "killall", "pgrep")))
check("its own debug port, not the default 9222", ch.PORT != 9222)
check("its own profile, never the user's",
      "chrome-profile" in str(ch.profile_dir()))
check("Chrome not running -> treated as already closed, not reported as broken",
      ch.shutdown(port=1) is True or not ch.alive(1))

# A correct close function is still useless if NOBODY CALLS IT. There used to
# be no call to shutdown() anywhere, so Chrome opened and sat on the screen
# until the next scan — an hour later.
runner_src = Path("src/jobbot/scan_runner.py").read_text()
app_src = Path("src/jobbot/app.py").read_text()
check("after a scan it closes Chrome", "chrome.shutdown()" in runner_src)
check("and it reports a failure to close", "could not close Chrome" in runner_src)
# THE CLOSE HAS TO BE IN A `finally`. It used to sit at the end of the
# function outside every try: one error in the middle — the DB locked while
# reading already_read, a dead socket after sleep — and the Chrome window
# stayed until the app quit. The app runs 24/7, so "until the app quits" means
# forever. Checked with the syntax tree, never by string search: the word
# "finally" somewhere in the file proves nothing.
import ast as _ast
def _trong_finally(nguon: str, ham: str, goi: str) -> bool:
    for node in _ast.walk(_ast.parse(nguon)):
        if isinstance(node, _ast.FunctionDef) and node.name == ham:
            for con in _ast.walk(node):
                if isinstance(con, _ast.Try):
                    if goi in _ast.unparse(_ast.Module(body=con.finalbody, type_ignores=[])):
                        return True
    return False
check("the Chrome close sits inside a finally — a mid-run failure still closes it",
      _trong_finally(runner_src, "_chrome_pass", "chrome.shutdown"))
# EVERY port, not only the scan port. The APPLY window (9335) is deliberately
# left open while running so Vin can make the final click, so quitting the app
# is the ONLY place that closes it; calling only shutdown() leaves it holding
# the profile lock, and the next time the app opens Chrome cannot reopen that
# profile.
check("quitting the app closes EVERY Chrome window of the app", "chrome.shutdown_all()" in app_src)
from jobbot.browser import chrome as _ch2
check("shutdown_all covers all three ports (scan · print PDF · apply)",
      set(_ch2.PROFILE) == {_ch2.PORT, _ch2.PDF_PORT, _ch2.APPLY_PORT})
# Really calling shutdown_all() here would CLOSE the real Chrome on the
# machine running the test — a test must have no side effects outside itself.
# alive() is stubbed out before calling.
_alive_that = _ch2.alive
_ch2.alive = lambda port=_ch2.PORT: False
try:
    check("no port running -> it returns 0 rather than reporting a failure", _ch2.shutdown_all() == 0)
finally:
    _ch2.alive = _alive_that

print("\n[LinkedIn — the safety boundary]")
from jobbot.ingest.web import linkedin as li
src = Path("src/jobbot/ingest/web/linkedin.py").read_text()
# A WORD BOUNDARY, not a substring: "assigning" contains "signin", so an
# ordinary English docstring is enough to turn this guard red. A guard that
# cries wolf teaches whoever fixes it exactly one thing — turn it off.
_dang_nhap = re.compile(
    r"(?<!\w)(password|signin|sign_in|credential)(?!\w)|login\s*\(", re.I)
_thay = _dang_nhap.search(src)
check("NO login code", not _thay, _thay.group(0) if _thay else "")
check("it does NOT touch personal profiles", not any(
    w in src for w in ("linkedin.com/in/", "/voyager/", "profileView",
                       "invitation", "messaging")))
check("guest endpoints only", "jobs-guest" in src)
check("a slower pace than the other sources", li.PAUSE[0] >= 2.0)
check("blocked means stop, never retry",
      "except Blocked" in src and "break" in src)

rows = [{"title": "Quant Analyst", "company": "Citi", "location": "London",
         "url": "/jobs/view/quant-analyst-at-citi-4443885925", "posted": "2026-09-05"}]
p1 = li._from_row(rows[0])
check("the posting id is parsed out", p1.source_id == "4443885925")
check("the full URL is rebuilt", p1.url.startswith("https://www.linkedin.com/jobs/view/"))
check("a row with no id is dropped", li._from_row({"title": "x", "url": "/jobs/view/no-id"}) is None)
check("a row with no title is dropped",
      li._from_row({"title": "", "url": "/jobs/view/a-1234567"}) is None)
check("seniority -> LinkedIn's experience code", li.EXPERIENCE["grad"] == "2")

print("\n[Chrome]")
check("Chrome is found on this machine", Path(chrome.binary()).exists())
check("ITS OWN profile, never the user's",
      "chrome-profile" in str(chrome.profile_dir())
      and "Application Support" not in str(chrome.profile_dir()))
check("its own port, not the default 9222", chrome.PORT != 9222)


print("\n[a broken source has to LOOK different from a good one]")
import tempfile
from jobbot.core import db as _db, postings as _po
from jobbot.ingest.web.base import Health

h = Health(attempted=10, failed=6)
h.note("TimeoutError"); h.note("empty description")
check("Health counts failures", h.failed == 6)
check("Health can summarise the reason", "6/10 failed" in h.summary and "TimeoutError" in h.summary)
check("no failures -> it reports nothing", Health(10, 0).summary == "")
check("a complete run is healthy", Health(10, 0).ok)

# THE REAL BUG: linkedin.fetch hitting Blocked mid-deep-read only note()d and
# broke — failed stayed 0, record_run saw 0/193 failures so it recorded ok=1,
# and the Settings screen showed a GREEN badge for a scan cut off at the third
# posting.
blocked = Health(attempted=193, failed=0)
check("unblocked it is healthy", blocked.ok)
blocked.block("blocked at posting 3/193", unread=191)
check("blocked -> NO LONGER healthy", not blocked.ok)
check("and the unread postings count as failures", blocked.failed == 191)
check("and it says outright that it was blocked", "BLOCKED" in blocked.summary)
early = Health(attempted=5)
early.block("blocked at the very first posting", unread=5)
check("blocked at the first posting is still not healthy", not early.ok)

with tempfile.TemporaryDirectory() as tmp:
    conn = _db.connect(Path(tmp) / "h.db")
    _po.record_run(conn, "s1", ok=True, fetched=4, attempted=10, failed=6)
    row = conn.execute("SELECT ok, error FROM source_run WHERE source='s1'").fetchone()
    check("60% failed -> the source is marked BROKEN even though postings came back", row["ok"] == 0)
    check("and it states the ratio", "6/10" in row["error"])

    _po.record_run(conn, "s2", ok=True, fetched=10, attempted=10, failed=1)
    check("10% failed -> still counted as a good run",
          conn.execute("SELECT ok FROM source_run WHERE source='s2'").fetchone()["ok"] == 1)

    _po.record_run(conn, "s3", ok=True, fetched=10)
    check("unmeasurable -> it does not judge blindly",
          conn.execute("SELECT ok FROM source_run WHERE source='s3'").fetchone()["ok"] == 1)
    conn.close()

print("\n[Posting and the DB table must not drift apart]")
from dataclasses import fields as _fields
from jobbot.core.postings import FIELD_MAP, NOT_COLUMNS
from jobbot.ingest.base import Posting as _P
_attrs = {f.name for f in _fields(_P)}
check("every Posting field is declared", not (_attrs - set(FIELD_MAP) - set(NOT_COLUMNS)))
check("no field is declared that does not exist",
      not ((set(FIELD_MAP) | set(NOT_COLUMNS)) - _attrs))
with tempfile.TemporaryDirectory() as tmp:
    conn = _db.connect(Path(tmp) / "c.db")
    cols = {x[1] for x in conn.execute("PRAGMA table_info(posting)")}
    check("every column declared in FIELD_MAP really exists in the table",
          set(FIELD_MAP.values()) <= cols)
    conn.close()

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
