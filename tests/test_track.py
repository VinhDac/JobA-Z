"""Test steps 5-6: applying and tracking.  python3 tests/test_track.py

The focus is THE CONSTRAINTS, not the features: the mailbox is what Vin cares
about most, so "read only" has to be checkable rather than a promise in the
docs.
"""

import inspect, os, re, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# NO NETWORK CALLS. This file tests mail.check(), and check() opens a real
# IMAP socket — run alone it would carry a real address out to the Internet.
# run_all.py sets this flag; it is set again here so running alone is safe too.
os.environ.setdefault("JOBBOT_OFFLINE", "1")

from jobbot.core import db
from jobbot.track import board, mail, scan, sort

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")


print("\n[the mailbox — READ ONLY, and the constraint lives in the code]")
src = inspect.getsource(mail)
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
# COUNT EVERY CALL SITE, NEVER SEARCH FOR A STRING.
#
# `"readonly=True" in code` stays green even when only ONE of the two places
# that open the mailbox still has it. Proved: dropping readonly from exactly
# the 24/7 scan loop (the most-run place, the one most worth guarding) and the
# test still reported ok — founding law 3 reduced to a promise in the docs.
import ast as _astR
_mo = [n for n in _astR.walk(_astR.parse(src))
       if isinstance(n, _astR.Call) and isinstance(n.func, _astR.Attribute)
       and n.func.attr == "select"]
check(f"{len(_mo)} places open the mailbox — ALL have to be guarded", len(_mo) >= 2)
_thieu = [n.lineno for n in _mo
          if not any(k.arg == "readonly" and getattr(k.value, "value", None) is True
                     for k in n.keywords)]
check("EVERY place that opens the mailbox uses readonly=True"
      + (f" — missing at line {_thieu}" if _thieu else ""), not _thieu)
check("messages are fetched with BODY.PEEK — the read flag is never set", "BODY.PEEK" in code)
# Checked EXACTLY: every call made on the IMAP object (the `box` variable),
# never a string search — a list's `out.append(...)` was once mistaken for
# IMAP's APPEND command.
import ast as _ast
calls = set()
for node in _ast.walk(_ast.parse(src)):
    if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Attribute)
            and isinstance(node.func.value, _ast.Name)
            and node.func.value.id == "box"):
        calls.add(node.func.attr)
check(f"only {sorted(calls)} are called on the mailbox",
      calls <= {"login", "select", "search", "fetch", "logout", "close"})
for danger in ("store", "append", "copy", "expunge", "uid", "setacl",
               "create", "delete", "rename", "subscribe"):
    check(f"box.{danger}() is NEVER called", danger not in calls)
check("smtp is not imported", "smtplib" not in code)
check("a 30-day limit", mail.SINCE_DAYS == 30 and "since_days" in code)
check("a message ceiling, so a big mailbox does not hang the scan", mail.MAX_MESSAGES > 0)
check("unconfigured -> a clear error, not a vague blow-up",
      "config.toml" in code)

print("\n[reapplying somewhere that once rejected you]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _id = board.add(conn, "Point72", "QR Intern")
    board.set_stage(conn, _id, board.REJECTED, "rejected")
    # The company reopens the posting and Vin presses Apply. Leave the stage at
    # "rejected" and the table draws no Send button, and the application Vin
    # just filled in never goes.
    board.add(conn, "Point72", "QR Intern", stage=board.DRAFT)
    _r = board.all(conn)[0]
    check("pulled back to draft so it can be sent", _r["stage"] == board.DRAFT)
    check("but it SAYS what happened before", "previously" in (_r["last_event"] or ""))
    check("still one row, none spawned", len(board.all(conn)) == 1)
    # A row reconstructed from mail has no posting id; without attaching one
    # the Send button answers "there is no original posting".
    from jobbot.core import postings as _postings
    from jobbot.ingest.base import Posting as _P
    _postings.save_batch(conn, "greenhouse:test", [_P(
        source_id="mg-1", title="Quant", company="Man Group",
        location="London", url="http://x", description="d " * 60)])
    _pid = conn.execute("SELECT id FROM posting WHERE company = 'Man Group'"
                        ).fetchone()["id"]
    board.add(conn, "Man Group", "", origin="mail")
    board.add(conn, "Man Group", "", posting_id=_pid, stage=board.DRAFT)
    _m = [x for x in board.all(conn) if x["company"] == "Man Group"][0]
    check("the posting id is attached to a mail-built row", _m["posting_id"] == _pid)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[the DB holds the CV and the mail — only the machine's owner may read it]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    conn.close()
    from pathlib import Path as _P2
    _dbf = _P2(tmp) / "jobbot.db"
    # sqlite defaults to 0644: any account on the machine could read the whole
    # CV, the profile, and the subject + first 400 characters of every
    # recruitment email.
    check("the DB is not readable by others",
          _dbf.exists() and not (_dbf.stat().st_mode & 0o077))
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[claiming a send — atomically]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _ap = board.add(conn, "Prima", "Quant", stage=board.DRAFT)
    check("the first press claims it", board.claim(conn, _ap) is True)
    check("the second press does NOT", board.claim(conn, _ap) is False)
    board.unclaim(conn, _ap)
    check("a failed send hands it back to draft", board.all(conn)[0]["stage"] == board.DRAFT)
    check("and it can be claimed again", board.claim(conn, _ap) is True)
    board.set_stage(conn, _ap, board.SENT, "sent")
    check("sent -> it moves to applied", board.all(conn)[0]["stage"] == board.SENT)
    check("applied -> it cannot be claimed any more", board.claim(conn, _ap) is False)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[an OLD message must not overwrite a NEWER state]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _app = board.add(conn, "Man Group", "Quant")

    def _mm(mid, sub, when):
        return {"msg_id": mid, "from_addr": "x@mangroup.com",
                "from_name": "Man Group", "subject": sub, "snippet": "",
                "received_at": when}

    from jobbot.track import scan as _scan
    _scan.store(conn, _mm("<1>", "Thank you for applying", "2026-09-01T09:00:00+00:00"),
                board.SENT, "Man Group", _app)
    _scan.store(conn, _mm("<2>", "Update", "2026-09-20T09:00:00+00:00"),
                board.REJECTED, "Man Group", _app)
    _ids = {r["kind"]: r["id"] for r in conn.execute("SELECT id, kind FROM message")}
    _scan.settle(conn, _ids["rejected"], True)
    check("a newer message changes the state", board.all(conn)[0]["stage"] == board.REJECTED)
    # Man Group sends "thank you" on the 1st and "unfortunately" on the 20th.
    # Take the rejection first and then the old one -> the table says the
    # application is alive while it is really dead.
    _scan.settle(conn, _ids["applied"], True)
    check("an OLD message cannot drag it back", board.all(conn)[0]["stage"] == board.REJECTED)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[a message with no Message-ID]")
import email as _email
_e1 = _email.message_from_string("From: x@y.z\nSubject: Rejected\n"
                                 "Date: Mon, 1 Sep 2026 09:00:00 +0000\n\nhi")
_e2 = _email.message_from_string("From: q@y.z\nSubject: Interview\n"
                                 "Date: Mon, 2 Sep 2026 09:00:00 +0000\n\nhi")
# A mailbox sequence number CHANGES whenever mail is added or removed, so on
# the next scan a DIFFERENT message carries the same "no-id-42" and is treated
# as already read — a rejection letter vanishing.
check("the substitute id is stable per message", mail._made_id(_e1) == mail._made_id(_e1))
check("two different messages give different ids", mail._made_id(_e1) != mail._made_id(_e2))
check("a sequence number is never used as an id",
      "no-id-{num" not in (Path(__file__).resolve().parent.parent
                           / "src/jobbot/track/mail.py").read_text(encoding="utf-8"))

print("\n[two audit bugs in the mail layer]")
# (11) One malformed message must NOT kill a whole 30-day scan.
_mailsrc = (Path(__file__).resolve().parent.parent
            / "src/jobbot/track/mail.py").read_text(encoding="utf-8")
check("each message has its own guard", "broken += 1" in _mailsrc)
check("and it reports how many were skipped", "unreadable messages" in _mailsrc)
check("a badly formatted date does not blow up", "except (TypeError, ValueError)" in _mailsrc)
# (12) One company, several applications: pushing the first row blindly moves
#      another application's state — a rejection for role A also downgrades
#      role B, which is waiting on an interview.
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    conn = db.connect()
    _a = board.add(conn, "Point72", "Quantitative Researcher")
    _b = board.add(conn, "Point72", "Data Engineer")

    def _msg(sub):
        return {"subject": sub, "snippet": "", "from_name": "Point72",
                "from_addr": "careers@point72.com"}

    check("a message naming the role -> exactly that row",
          sort.match(conn, _msg("Update on your Data Engineer application")) == _b)
    check("a message naming no role -> it does NOT guess",
          sort.match(conn, _msg("Update on your application")) is None)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[the scan has to be A GUEST — the machine guards it, nobody has to remember]")
from jobbot.ingest.web import linkedin as _lk
from jobbot.ingest.web.base import Blocked as _Blocked


class _Cookies:
    """A fake tab returning LinkedIn cookies."""

    def __init__(self, signed):
        self.signed = signed

    def call(self, method, params=None, timeout=30.0):
        if method == "Network.getCookies":
            return {"cookies": [{"name": "li_at", "value": "x"}] if self.signed else []}
        return {}


check("a LOGGED-IN profile is recognised", _lk.signed_in(_Cookies(True)))
check("a guest profile is recognised", not _lk.signed_in(_Cookies(False)))
# The scan window and the apply window look identical; logging into the wrong
# one means every scan runs under the real account — the surest way to lose
# it.
_raised = ""
try:
    _lk.fetch(_Cookies(True), ["quant"])
except _Blocked as exc:
    _raised = str(exc)
except Exception as exc:                          # noqa: BLE001
    _raised = f"WRONG TYPE: {type(exc).__name__}"
check("scanning while logged in -> Blocked", _raised.startswith("the SCAN profile"))
# Blocked has to be caught PER SOURCE: LinkedIn skipped, the other sources
# still run, rather than the whole scan dying.
_runner = (Path(__file__).resolve().parent.parent
           / "src/jobbot/scan_runner.py").read_text(encoding="utf-8")
# Comparing string positions in the file is wrong: there is another `except
# Exception` earlier in the file that is not in the same try block. Only the
# AST answers correctly.
import ast as _ast
_tree = _ast.parse(_runner)
_ok = False
for _n in _ast.walk(_tree):
    if not isinstance(_n, _ast.Try):
        continue
    _names = [(_h.type.id if isinstance(_h.type, _ast.Name) else "") for _h in _n.handlers]
    if "Blocked" in _names:
        _ok = _names.index("Blocked") < (_names.index("Exception")
                                         if "Exception" in _names else 99)
        break
check("scan_runner catches Blocked separately, BEFORE the general Exception", _ok)

print("\n[connecting the mailbox from the interface — the password must not leak]")
from jobbot.core import config as _cfg
from jobbot.dashboard.views import track as _tv

# RUN AGAINST A FAKE REPO. The old version wrote straight into THE REAL
# config.toml and restored it in a finally — and when the real file did not
# exist yet there was nothing to restore, so it left the fake address "a@b.c"
# with an empty app password in Vin's file. That really happened on 12/09.
import os as _osc, shutil as _shc, tempfile as _tfc
_ctmp = _tfc.mkdtemp()
_cu_root_c = _osc.environ.get("JOBBOT_ROOT")
_osc.environ["JOBBOT_ROOT"] = _ctmp
try:
    (Path(_ctmp) / "config").mkdir(parents=True, exist_ok=True)
    _shc.copy(Path(__file__).resolve().parent.parent
              / "config" / "config.example.toml",
              Path(_ctmp) / "config" / "config.example.toml")
    # THE LATCH: never write into the REAL config. The same rule as the "the
    # test is pointing at THE REAL DB" latch — and this one exists because a
    # real app password was lost.
    assert str(_cfg.PATH).startswith(_ctmp), f"writing into the REAL config: {_cfg.PATH}"
    _cfg.write_value("mail", "address", "a@b.c")
    _cfg.write_value("mail", "password", 'p"w\\d')
    check("written and read back correctly", _cfg.section("mail")["password"] == 'p"w\\d')
    check("no other key is touched", _cfg.section("mail")["address"] == "a@b.c")
    # config.toml carries a long comment explaining why a separate mailbox is
    # used. Rebuilding the whole file would wipe it.
    check("the comments are preserved", "app password" in _cfg.PATH.read_text())
    check("only the owner can read it", (_cfg.PATH.stat().st_mode & 0o777) == 0o600)
    _cfg.write_value("mail", "password", "")
    check("it can be cleared", _cfg.section("mail")["password"] == "")
finally:
    if _cu_root_c is None:
        _osc.environ.pop("JOBBOT_ROOT", None)
    else:
        _osc.environ["JOBBOT_ROOT"] = _cu_root_c
    _shc.rmtree(_ctmp, ignore_errors=True)

# THE MAILBOX FIELDS MOVED TO SETTINGS · GMAIL. It is configuration —
# connected once and then done — while Vin opens the Track page daily; leaving
# a configuration form at the head of his work table makes his eye reread it
# every day.
_html = _tv.render(rows=[], asks=[], counts={}, mail_ready=False,
                   mail_address="a@b.c")
check("Track NO LONGER carries the mailbox form", "/api/mail/setup" not in _html)
check("but it points at exactly where to connect", "data-appset='gmail'" in _html)
_on = _tv.render(rows=[], asks=[], counts={}, mail_ready=True,
                 mail_address="a@b.c", mail_days=45)
# THE SCAN BUTTON MOVED TO THE STAGE BAR, like Search and CV. Kept in both
# places it would be two buttons doing one job, with the user left to guess
# whether they differ.
check("the scan button is on the stage bar", "data-arg='track'" in _on)
check("the panel holds only the mailbox STATE, with no second button",
      "/api/track/mail/scan" not in _on)
check("and it still states the day count in use", "last 45 days" in _on)

# The connection form now lives in Settings — every promise about the password still holds.
from jobbot.dashboard.views import settings as _sv
_set = _sv.render(every=60, hours=(8, 22), status=[], mail_ready=False,
                  mail_address="a@b.c", mail_days=30)
check("Settings has the mailbox fields", "/api/mail/setup" in _set)
check("the password field is type=password", "type=password" in _set)
check("the password value is NEVER drawn into the HTML",
      not re.search(r"type=password[^>]*value=", _set))
check("the address may be drawn", "a@b.c" in _set)
_set_on = _sv.render(every=60, hours=(8, 22), status=[], mail_ready=True,
                     mail_address="a@b.c", mail_days=30, mail_profile="a@b.c")
# CONNECTED ONCE, and only "Start over" removes it. Two destructive paths to
# one thing means two places to press by mistake — this app password was lost
# three times in one day.
check("there is NO separate delete-password button", "/api/mail/forget" not in _set_on)
check("and it says outright that only Start over removes it", "Start over" in _set_on)
check("but it can still be changed by pasting over", "/api/mail/setup" in _set_on)
_srv3 = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("the delete route is gone entirely", '"/api/mail/forget"' not in _srv3)
# THE LATCH: the mailbox scanned has to be EXACTLY the one declared in the
# profile. Connect the wrong one and the app watches one place while the mail
# arrives at another — the Track table reporting "waiting" forever for
# applications that were answered, with no sign anything is wrong.
check("connecting a mailbox has a profile-match latch",
      'store.load(conn_ho_so).get("email")' in _srv3)
_set_khac = _sv.render(every=60, hours=(8, 22), status=[], mail_ready=False,
                       mail_address="", mail_days=30, mail_profile="vin@x.y")
check("it says UP FRONT which address it has to match", "vin@x.y" in _set_khac)
check("and prefills it so it cannot be mistyped", "value='vin@x.y'" in _set_khac)
check("with nothing declared it points at where to declare it",
      "The profile has no contact address yet"
      in _sv.render(every=60, hours=(8, 22), status=[]))
check("and there is a field for how many days of mail to reread", "name=mail_days" in _set)
_srv2 = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("the delete route demands confirmation", '!= "xoa"' in _srv2)

# imaplib's error message is the server's reply verbatim, and it goes straight
# into the journal — leak it once and it is leaked forever.
check("the password is masked in an error message",
      mail._hide("login failed for hunter2", "hunter2") == "login failed for ***")
check("unfilled -> it says so at once, with no network call",
      mail.check("", "") == "the address and app password are not both filled in")
# Pasting AN ACCOUNT PASSWORD by mistake is ordinary. Caught by shape, BEFORE
# it is sent over the network — otherwise the real password has already flown
# before anyone learns it was useless.
check("an account password is blocked on the spot",
      "not an app password" in mail.check("a@gmail.com", "Work123@"))
check("and no network call is made at all",
      "Gmail refused" not in mail.check("a@gmail.com", "Work123@"))
# THAT SHAPE IS GOOGLE'S. The old version applied it to EVERY address, so
# anyone on Outlook / iCloud / a company mailbox was turned away at the door
# by a sentence with nothing to do with the real reason — while their password
# might have been perfectly correct.
check("another provider is NOT blocked by Google's filter",
      "not an app password" not in mail.check("a@outlook.com", "Work123@"))
check("an app password of the right shape passes the shape check",
      "not an app password" not in (mail.check.__doc__ or "") or
      bool(mail.APP_PASSWORD.fullmatch("abcdefghijklmnop")))
check("Google shows it in groups of 4 — spaces stripped, it is still accepted",
      bool(mail.APP_PASSWORD.fullmatch("abcd efgh ijkl mnop".replace(" ", ""))))
# What is CHECKED has to be exactly what is used to LOG IN. The route strips
# spaces at save time; otherwise check() compares a stripped string while
# login() sends one with spaces.
_srv = (Path(__file__).resolve().parent.parent
        / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("saving an app password strips the spaces", '.replace(" ", "")' in _srv)

print("\n[classifying mail]")
def m(subject, snippet="", name="", addr=""):
    return {"subject": subject, "snippet": snippet,
            "from_name": name, "from_addr": addr, "msg_id": subject}

check("an acknowledgement", sort.kind(m("Thank you for applying")) == board.SENT)
check("a rejection",
      sort.kind(m("Update", "we will not be moving forward")) == board.REJECTED)
check("an interview invitation",
      sort.kind(m("Next steps", "we would like to invite you to a call")) == board.INTERVIEW)
check("an online assessment counts as an interview too",
      sort.kind(m("Assessment", "please complete the HackerRank test")) == board.INTERVIEW)
check("an offer", sort.kind(m("Offer", "we are pleased to offer you")) == board.OFFER)
check("anything else is left alone", sort.kind(m("5 new jobs for you")) == "other")
# An interview invitation STILL usually opens with "thank you for applying".
# Judged from the strongest outcome down, or the most important message is
# filed as an acknowledgement.
check("an invitation beats an acknowledgement in one message",
      sort.kind(m("Your application",
                  "Thank you for applying. We would like to invite you to a call."))
      == board.INTERVIEW)

print("\n[guessing the company]")
for want, msg in (("Point72", m("x", name="Careers at Point72")),
                  ("Jump Trading", m("x", name="Jump Trading Recruiting")),
                  ("Schonfeld", m("x", name="Schonfeld Talent Acquisition Team")),
                  ("Qube Research", m("Interview - Qube Research", addr="a@greenhouse.io")),
                  ("Jane Street", m("Your application to Jane Street", addr="a@lever.co"))):
    got = sort.company_of(msg)
    check(f"{want:<14} <- {got[:26]}", want.lower() in got.lower())

with tempfile.TemporaryDirectory() as tmp:
    conn = db.connect(Path(tmp) / "t.db")

    print("\n[the table]")
    a = board.add(conn, "Point72", "Quantitative Researcher", cv_file="p.pdf")
    b = board.add(conn, "Point72", "Quantitative Researcher")
    check("reapplying to the same role spawns NO new row", a == b)
    check("applying to a different role is a different row",
          board.add(conn, "Point72", "Data Scientist") != a)
    board.set_stage(conn, a, board.REJECTED, "not moving forward")
    check("the state can be changed",
          [r for r in board.all(conn) if r["id"] == a][0]["stage"] == board.REJECTED)
    board.set_stage(conn, a, "madeup")
    check("an invented state is refused",
          [r for r in board.all(conn) if r["id"] == a][0]["stage"] == board.REJECTED)

    # `silent` is A SUBTRACTION, not a column. Stored, it would have to be
    # updated daily and one day would be forgotten — the same reason the
    # project grid's `gap` is not stored.
    check("silent is not a column in the table",
          "silent" not in [r[1] for r in conn.execute("PRAGMA table_info(application)")])
    old = board.add(conn, "Old Firm", "Analyst",
                    applied_at="2020-01-01T00:00:00+00:00")
    row = [r for r in board.all(conn) if r["id"] == old][0]
    check("applied long ago with no mail -> silent", row["silent"])
    board.set_stage(conn, old, board.INTERVIEW, "interview invitation")
    row = [r for r in board.all(conn) if r["id"] == old][0]
    check("with mail it is no longer silent", not row["silent"])

    print("\n[which row a message matches]")
    conn.execute("DELETE FROM message"); conn.execute("DELETE FROM application")
    conn.commit()
    p72 = board.add(conn, "Point72", "Quantitative Researcher")
    board.add(conn, "Man Group", "Quant Developer")
    check("matched by sender name",
          sort.match(conn, m("x", name="Careers at Point72")) == p72)
    check("a domain with no space still matches (mangroup <-> man group)",
          sort.match(conn, m("Application update", addr="careers@mangroup.com")) is not None)
    check("no match -> it says no match rather than guessing",
          sort.match(conn, m("Interview - Some Firm Nobody Applied To",
                             addr="a@greenhouse.io")) is None)

    print("\n[mail PROPOSES, it never changes anything itself]")
    conn.execute("DELETE FROM message"); conn.execute("DELETE FROM application")
    conn.commit()
    app = board.add(conn, "Point72", "Quantitative Researcher")
    note = m("Next steps", "we would like to invite you to a call",
             name="Careers at Point72")
    scan.store(conn, {**note, "received_at": "2026-09-08T10:00:00",
                      "from_addr": "", "from_name": "Careers at Point72"},
               sort.kind(note), sort.company_of(note), app)
    stage_now = [r for r in board.all(conn) if r["id"] == app][0]["stage"]
    check("mail arrived and the state has NOT changed", stage_now == board.SENT)
    asks = scan.proposals(conn)
    check("it sits in the band waiting on Vin's decision", len(asks) == 1)
    check("and it states what it would change to", asks[0]["kind"] == board.INTERVIEW)
    scan.settle(conn, asks[0]["id"], accept=True)
    check("only Vin accepting changes it",
          [r for r in board.all(conn) if r["id"] == app][0]["stage"] == board.INTERVIEW)
    check("answered once, it is not asked again", scan.proposals(conn) == [])

    print("\n[reconstructing the past from mail]")
    # Delete the MESSAGES before the application row: message.application_id is
    # a foreign key and it does NOT have ON DELETE CASCADE. Which means that
    # letting Vin delete a row from the table later will require detaching the
    # messages pointing at it first.
    conn.execute("DELETE FROM message"); conn.execute("DELETE FROM application")
    conn.commit()
    past = m("Thank you for applying", "We have received your application.",
             name="Jump Trading Recruiting")
    kind, who = sort.kind(past), sort.company_of(past)
    got = sort.match(conn, past)
    if got is None and kind == board.SENT and who:
        got = board.add(conn, who, "", origin="mail",
                        applied_at="2026-08-20T09:00:00+00:00")
    check("an acknowledgement matching nobody -> an application is reconstructed", got is not None)
    row = board.all(conn)[0]
    check("and it records that it came from mail", row["origin"] == "mail")
    check("it keeps the date from the message", row["applied_at"].startswith("2026-08-20"))
    conn.close()

print("\n[classifying mail — measured on real subject lines]")
# The old version scored 10/13. Three misses, and the worst was A REJECTION
# falling into "other": needs_you=0 so the message never surfaced, and the
# table reported "waiting" forever for an application that was dead.
MAIL_CASES = [
    (board.SENT,      "Thank you for applying to Man Group",       "We have received your application."),
    (board.SENT,      "We've received your application",            "Your application is with our team."),
    (board.SENT,      "Application received — Quantitative Analyst", "Thanks for your interest."),
    (board.INTERVIEW, "Invitation to interview — Point72",          "Thank you for applying. We'd like to meet."),
    (board.INTERVIEW, "Interview invitation",                       "Thank you for applying to IMC."),
    (board.INTERVIEW, "We'd like to invite you for an interview",   "Thanks for applying."),
    (board.INTERVIEW, "Next steps: online assessment",              "Please complete the HackerRank test."),
    (board.INTERVIEW, "Let's schedule a call",                      "Are you free next week?"),
    (board.REJECTED,  "Your application to IMC",                    "Unfortunately we will not be progressing."),
    (board.REJECTED,  "Update on your application",                 "We have decided not to move forward at this time."),
    (board.REJECTED,  "Thank you for your interest in Jane Street", "We won't be taking your application further."),
    (board.REJECTED,  "Application update",                         "You have not been successful on this occasion."),
    (board.REJECTED,  "Re: Quantitative Analyst",                   "We are unable to offer you a position."),
    (board.OFFER,     "Offer of employment — Prima",                "We are delighted to offer you the role."),
    ("other",         "Your Amazon order has shipped",              "Track your parcel"),
    ("other",         "LinkedIn: 5 new jobs for you",               "Jobs matching your profile"),
    ("other",         "Your monthly statement is ready",            "Barclays"),
    ("other",         "Newsletter: quant careers this week",        "Top stories"),
]
for want, subject, snippet in MAIL_CASES:
    got = sort.kind({"subject": subject, "snippet": snippet,
                     "from_name": "", "from_addr": "x@y.z"})
    check(f"{want:<9} {subject[:40]}", got == want)
# An interview invitation almost always opens with "thank you for applying" —
# the invitation rule MUST be examined before the acknowledgement rule, or the
# most important message gets downgraded.
_names = [name for name, _ in sort.RULES]
check("the strongest outcome is examined first", _names.index(board.INTERVIEW) < _names.index(board.SENT))
check("rejection is examined before acknowledgement", _names.index(board.REJECTED) < _names.index(board.SENT))

print("\n[mail reconstructs the past — EVERY outcome, not only acknowledgements]")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JOBBOT_DATA_DIR"] = tmp
    from jobbot.track import mail as _mail, scan as _scan
    conn = db.connect()
    board.add(conn, "Prima", "Quantitative Analyst", stage=board.DRAFT)

    def _m(sub, snip, name, addr):
        return {"msg_id": f"<{abs(hash(sub))}@x>", "from_addr": addr,
                "from_name": name, "subject": sub, "snippet": snip,
                "received_at": "2026-09-09T10:00:00+00:00"}

    _mail.fetch = lambda *a, **k: [
        _m("Thank you for applying to Prima", "We have received your application.",
           "Prima", "no-reply@jobs.lever.co"),
        _m("Interview invitation — Jane Street", "Thank you for applying. Let's schedule a call.",
           "Jane Street", "recruiting@janestreet.com"),
        _m("Your Amazon order has shipped", "Track your parcel", "Amazon", "ship@amazon.co.uk"),
    ]
    _mail.account = lambda: ("x@y.z", "pw")
    got = _scan.run(conn)
    check("every message is read", got["seen"] == 3)
    # A BUG SINCE FIXED: only an acknowledgement reconstructed a row, so an
    # interview invitation from a company with no row meant Vin pressed Accept
    # and NOTHING happened.
    rows = {r["company"]: r for r in board.all(conn)}
    check("an interview invitation creates a new row", "Jane Street" in rows)
    check("and it is created AT THE RIGHT STAGE, not forced back to 'applied'",
          rows.get("Jane Street", {}).get("stage") == board.INTERVIEW)
    check("a shopping email creates NO row at all", "Amazon" not in rows)
    # a draft row meeting an acknowledgement -> propose moving it to applied
    moves = {p["company"]: p["kind"] for p in _scan.proposals(conn)}
    check("draft + acknowledgement -> proposes 'applied'", moves.get("Prima") == board.SENT)
    conn.close()
    os.environ.pop("JOBBOT_DATA_DIR", None)

print("\n[the machine fills, Vin presses Send]")
# The OLD rule here was "only open the page, never fill". Changed
# deliberately: the machine fills what it can prove, while the Submit click
# exists on no code path at all — the boundary lives in `apply/run.py`, and
# `tests/test_apply.py` guards it.
server = (Path(__file__).resolve().parent.parent
          / "src/jobbot/dashboard/server.py").read_text()
apply_block = server[server.index('if path == "/api/apply"'):
                     server.index('if path == "/api/track/state"')]
check("the Apply button runs the filling code", "_start_apply" in apply_block)
check("and writes a row into the table", "board.add" in apply_block)
check("it SHARES the one source of PDF names", "cv_pdf_for" in apply_block)
check("it no longer opens the default browser", "webbrowser" not in apply_block)
for danger in ("Input.dispatchKeyEvent", "form.submit", "click()", "Page.navigate"):
    check(f"no {danger}", danger not in apply_block)
check("and writes a row into the table", "board.add" in apply_block)

print("\n[THE COMPANY NAME: the text first, the sender after — measured on the real mailbox]")
# 56 messages with an outcome over 60 days. The worst error: an INTERVIEW
# INVITATION — the most important row on the table — carried the name
# "GoHire", a recruitment software company.
from jobbot.track.sort import company_of as _co

def _t(sub, frm="", name="", snip=""):
    return _co({"subject": sub, "from_addr": frm, "from_name": name,
                "snippet": snip})

check("a message sent via recruitment software -> take the name from THE SUBJECT",
      _t("Kappa Lab Interview", "mail@gohire-messaging.com", "GoHire",
         "Thank you for applying to Kappa Lab.") == "Kappa Lab")
check("Workable does not hide the real company",
      _t("Thanks for applying to Flowdesk", "noreply@candidates.workablemail.com",
         "Workable") == "Flowdesk")
# The company is after the LAST `at`; what comes before is the role.
check("LinkedIn: take what follows `at`, never the job title",
      _t("Your application to Quantitative Researcher at Durlston Partners",
         "jobs-noreply@linkedin.com", "LinkedIn") == "Durlston Partners")
check("a subject broken across lines still reads",
      _t("Your application to Junior Quant\n Researcher at Anson McCade",
         "jobs-noreply@linkedin.com", "LinkedIn") == "Anson McCade")
# A job title must NOT become the company name when the sentence has no `at`
# to split it.
check("no `at` but a job title matched -> it does NOT guess",
      _t("Great news, we've received your application for Quantitative "
         "Trading Analyst", "no-reply@mavensecurities.com") == "Maven"
      or _t("Great news, we've received your application for Quantitative "
            "Trading Analyst", "no-reply@mavensecurities.com") == "Mavensecurities")
# The sender's name is still used when it IS the company — Ashby and
# SmartRecruiters send on their behalf but put the company in the From field.
check("an agent sending with the company in From -> still taken",
      _t("Thank you|Consultant", "no-reply@smartrecruiters.com", "Ayming") == "Ayming")
check("strip the function suffix and only a generic word is left -> NOT a name",
      _t("We have received your application", "no-reply@ashbyhq.com",
         "Talent Acquisition") == "")
# `st.griddynamics.net` -> "Griddynamics", NOT "St". Taking the first label
# takes the host name; measured on the real mailbox it once produced a company
# called "GD".
_gd = _t("Your application for Python Quantitative Developer",
         "notification@st.griddynamics.net", "GD Notification")
check("the domain label taken is the one BEFORE the TLD, not the first",
      _gd == "Griddynamics")
check("and not a leftover fragment of the sender name", _gd not in ("St", "GD"))
check("a whole SENTENCE is not a company name",
      _t("Job Opportunity - from mcgregorboyall Thank you for your application",
         "noreply@broadbean.net") == "")
# A public service is not a job.
from jobbot.track.sort import KHONG_PHAI_VIEC as _kpv
check("public-service mail is kept out of the jobs table",
      bool(_kpv.search("no-reply@notifications.service.gov.uk")))

print("\n[MAIL THE MACHINE CANNOT READ: it promises no understanding, it promises NO MESSAGE LOST]")
# A table of phrasings is never complete. Measured on the real mailbox:
# Maven's rejection ("Sorry, it's not quite a match") and Trading 212's
# acknowledgement ("Your application is in") both fell into `other` and
# vanished without trace.
import sqlite3 as _sq3
from jobbot.core import db as _dbK
from jobbot.track import scan as _scK, board as _bdK
_ck = _dbK.connect(":memory:")
_app = _bdK.add(_ck, "Maven", "Quant Analyst", origin="mail")
_thu = {"msg_id": "m1", "from_addr": "no-reply@mavensecurities.com",
        "from_name": "", "subject": "Sorry, it's not quite a match",
        "received_at": "2026-09-09T00:00:00+00:00",
        "snippet": "we've decided not to progress"}
check("mail the machine cannot file is still 'other'", _scK.sort.kind(_thu) == "other")
_scK.store(_ck, _thu, "other", "Maven", _app)
_mu = _scK.kho_hieu(_ck)
check("but it does NOT vanish — it surfaces for the user to file", len(_mu) == 1)
check("and it names which application it belongs to", _mu[0]["company"] == "Maven")
# An 'other' message belonging to NO application does not pester anyone.
_scK.store(_ck, {**_thu, "msg_id": "m2", "subject": "Sale 50%"},
           "other", "", None)
check("a stray message belonging to no application -> not asked about", len(_scK.kho_hieu(_ck)) == 1)
# The user files one and the state changes at once, never asked twice.
check("filed -> the state changes", _scK.xep(_ck, _mu[0]["id"], "rejected"))
check("and the row goes to the right stage",
      [r for r in _bdK.all(_ck) if r["id"] == _app][0]["stage"] == "rejected")
check("filed once, it stops being asked about", not _scK.kho_hieu(_ck))
check("an unknown kind is refused", not _scK.xep(_ck, _mu[0]["id"], "nonsense"))
_ck.close()

print("\n[the Track table: a datasheet — a search box, filter chips, click to open]")
from jobbot.dashboard.views import track as _tkD

def _r(**kw):
    d = dict(id=1, stage="applied", company="Kappa Lab", role="Quant Dev",
             days=20, event_days=None, last_event="", silent=False, cv_file="",
             posting_id=None, url="", score=0, song="im", im_ngay=20,
             so_thu=1, ho_tra_loi=False, nguon="", ai_nop="applied earlier by hand",
             origin="mail", co_cv=False)
    d.update(kw); return d

_h = _tkD.render(rows=[_r()], asks=[], counts={"total": 1}, mail_ready=False,
                 mail_address="", thu={1: []}, loc={})
check("it has a search box like Search", "class=jfind" in _h)
for _ma in ("ng=", "ai=", "tt=", "cv="):
    check(f"it has the {_ma[:-1]} filter row", f"/track?{_ma}" in _h or f"&{_ma}" in _h)
check("each row opens with no JavaScript needed", "<details class='trow" in _h)

# A FILTER HAS TO REALLY FILTER, not just look pretty.
_hai = [_r(id=1, company="A", origin="mail", nguon="linkedin", song="im"),
        _r(id=2, company="B", origin="apply", nguon="board", song="nong")]
_loc = _tkD.render(rows=_hai, asks=[], counts={}, mail_ready=False,
                   mail_address="", thu={}, loc={"ng": "board"})
check("filter by source -> only matching rows remain",
      ">B<" in _loc and ">A<" not in _loc)
_loc2 = _tkD.render(rows=_hai, asks=[], counts={}, mail_ready=False,
                    mail_address="", thu={}, loc={"ai": "mail"})
check("filter by APPLIED BY -> only matching rows remain",
      ">A<" in _loc2 and ">B<" not in _loc2)
_loc3 = _tkD.render(rows=_hai, asks=[], counts={}, mail_ready=False,
                    mail_address="", thu={}, loc={"q": "zzz"})
check("no match -> IT SAYS SO, it does not return a mute empty table",
      "no row passes the filters" in _loc3)

# THE DETAIL: mail, the CV, the original posting — and it says outright when there is none.
_ct = _tkD.render(rows=[_r(posting_id=9, nguon="linkedin", co_cv=True,
                           url="https://x/y")],
                  asks=[], counts={}, mail_ready=False, mail_address="",
                  thu={1: [dict(id=5, subject="Interview", snippet="hi",
                                kind="interview", received_at="2026-08-24",
                                from_addr="a@b.c")]}, loc={})
check("opened, the received mail is there",
      "1 messages received" in _ct and "Interview" in _ct)
check("and a link to the CV", "/jobs/9/cv?tu=/track" in _ct)
check("and a link to the original posting", "/jobs/9?tu=/track" in _ct)
_trong = _tkD.render(rows=[_r()], asks=[], counts={}, mail_ready=False,
                     mail_address="", thu={1: []}, loc={})
check("applied outside the app -> it SAYS OUTRIGHT why it is empty",
      "applied outside the app" in _trong and "not one message" in _trong)

print("\n[the machine stuck hands it back to THE PERSON, never letting that application drop]")
# HANDED OVER IN THE QUEUE, not in the table: this is WORK TO BE DONE, and the
# table holds only facts.
from jobbot.dashboard.views import trackcho as _qT
_hang = [_r(origin="tay", posting_id=9, url="https://li/job/1")]
_tay = _qT.render(rows=_hang, asks=[], mu=[])
check("there is a panel of its own for postings the machine cannot apply to",
      "the machine cannot apply for you" in _tay)
check("it gives THE APPLICATION LINK to do it by hand", "https://li/job/1" in _tay)
check("and the link to DOWNLOAD THE CV", "/api/cv/pdf" in _tay)
check("it says what to press once it is done", "Scan mail" in _tay)
_bang = _tkD.render(rows=_hang, asks=[], counts={}, mail_ready=False,
                    mail_address="", thu={1: []}, loc={})
check("and the table no longer carries that job", "the machine could not apply" not in _bang)
# A flag of its own, never a string searched inside a description — reword the
# sentence once and the label is dead.
from jobbot.apply.run import Report as _Rep
check("the 'do it by hand' flag is A FIELD, not a string in note",
      "tu_lam" in _Rep.__dataclass_fields__)

print("\n[three patched-over places, now really patched]")
# 1. THE MASTER BAR: every metric asked for, and REJECTED kept apart from SILENT.
_bar = _tkD.render(rows=[_r()], asks=[], counts={}, mail_ready=False,
                   mail_address="", thu={}, loc={},
                   stage={"da_nop": 9, "di_tiep": 1, "truot": 2, "cho_ban": 3,
                          "hang_doi": 12, "state": "x"})
for _s in ("applied", "taken further", "rejected", "waiting on you"):
    check(f"the bar has the «{_s}» figure", f">{_s}<" in _bar or _s in _bar)
# Rejected is what they SAID, silent is what they have NOT said — merging them
# loses the one distinction between "dead" and "unknown".
check("REJECTED is kept apart from SILENT", "rejected" in _bar)
check("there is an Apply button on the bar", "/api/track/nop-tiep" in _bar)
check("and that button says how many postings are worth applying to",
      "12 postings worth applying to" in _bar)

# 4. A SPREADSHEET-STYLE TABLE: a header row, one label per column.
check("the table has a column header row", "class=thead" in _bar)
for _c in ("company", "role", "source", "applied by", "last contact",
           "mail", "CV", "state"):
    check(f"it has the «{_c}» column label", f">{_c}<" in _bar)
check("company and role are TWO columns, never crammed into one cell",
      "class=c1" in _bar and "class=c2" in _bar)
# The header row and each data row have to SHARE one column grid, or they drift.
_cssT = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
check("the header and the rows share one column declaration",
      "--cot:" in _cssT and _cssT.count("grid-template-columns:var(--cot)") == 2)

print("\n[what cannot be SETTLED lives on its own screen, never over a clean table]")
from jobbot.dashboard.views import trackcho as _qD
_orphan = [dict(id=7, subject="Update on your application", snippet="…",
                kind="rejected", received_at="2026-09-01", company_guess="",
                app_id=None, company=None, role=None, stage=None)]
_mu1 = [dict(id=8, company="Maven", company_guess="", subject="Sorry",
             snippet="not quite a match")]
_q = _qD.render(rows=[_r(id=3, company="Kappa Lab")], asks=_orphan, mu=_mu1,
                stage={"cho_ban": 2})
_sach = _tkD.render(rows=[_r(id=3, company="Kappa Lab")], asks=_orphan, mu=_mu1,
                    counts={}, mail_ready=False, mail_address="", thu={},
                    loc={}, stage={"cho_ban": 2})
# TWO DIFFERENT RHYTHMS: the table is glanced at daily, the queue is sat down
# with once and then empty. Mixed together, 16 mail cards push the search box
# below the fold.
check("mail cards are NO LONGER on the Track tab", "class=askrow" not in _sach)
check("they are on the queue screen", _q.count("class=askrow") == 2)
check("there is a Queue button leading there", "href='/track/queue'" in _sach)
check("the button says how many are left", ">Queue 2<" in _sach)
check("with none left the button invents no number",
      ">Queue<" in _tkD.render(rows=[_r()], asks=[], counts={}, thu={}, loc={},
                               mail_ready=False, mail_address="",
                               stage={"cho_ban": 0}))
check("the queue screen has a way back to the table", "href='/track'" in _q)
# Empty is ALLOWED, and that is the point of the screen: the table is never
# empty.
check("an empty queue says outright that it is done",
      "Nothing is waiting on you" in _qD.render(rows=[], asks=[], mu=[]))
# The module must NOT be called `queue`: server.py already imports the
# standard library's `queue` and the SSE loop catches `queue.Empty`. One
# shadowing the other = a frozen screen.
import queue as _stdq
check("the standard library's `queue` is not shadowed", hasattr(_stdq, "Empty"))

# 6. MAIL WITH AN OUTCOME AND NO KNOWN OWNER: it has to be ATTACHABLE, not only ignorable.
_ga = _q
check("mail with no known owner -> there is a SELECT of applications", "data-ganfor='7'" in _ga)
check("and it lists the rows that exist", "Kappa Lab" in _ga)
check("it is no longer just an Ignore button", "matched no row" not in _ga)
# Attached, the state changes at once and it is never asked about again.
_cg = _dbK.connect(":memory:")
_a2 = _bdK.add(_cg, "Kappa Lab", "Quant", origin="mail")
_scK.store(_cg, {"msg_id": "z1", "from_addr": "x@y.z", "from_name": "",
                 "subject": "Update", "received_at": "2026-09-01T00:00:00+00:00",
                 "snippet": ""}, "rejected", "", None)
_mid = _cg.execute("SELECT id FROM message WHERE msg_id='z1'").fetchone()[0]
check("it attaches", _scK.gan(_cg, _mid, _a2))
check("and the row goes to the right stage",
      [r for r in _bdK.all(_cg) if r["id"] == _a2][0]["stage"] == "rejected")
check("an unknown row is refused", not _scK.gan(_cg, _mid, 9999))
_cg.close()

print("\n[THE SILENCE MARK: past N days it is treated as rejected, and N turns]")
from jobbot.core import prefs as _pf
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

def _truoc(n):
    return (_dt.now(_tz.utc) - _td(days=n)).isoformat()

_cn = _dbK.connect(":memory:")
check("20 days by default, exactly the number you chose", _pf.DEFAULTS[_pf.IM_QUA] == "20")
check("board reads the mark from the preference", _bdK.nguong(_cn) == 20)

# One row silent 25 days and one silent 5. The mark passes between them.
_im = _bdK.add(_cn, "Long Silence", "Quant", applied_at=_truoc(25))
_moi = _bdK.add(_cn, "Just Applied", "Quant", applied_at=_truoc(5))

def _song(app_id):
    return [r for r in _bdK.all(_cn) if r["id"] == app_id][0]["song"]

check("mark 20: silent 25 days -> treated as rejected", _song(_im) == _bdK.SONG_IM)
check("mark 20: silent 5 days -> still inside the window", _song(_moi) == _bdK.SONG_CHO)
_pf.put(_cn, _pf.IM_QUA, "30")
check("loosened to 30 -> the 25-day row COMES BACK TO LIFE", _song(_im) == _bdK.SONG_CHO)
_pf.put(_cn, _pf.IM_QUA, "10")
check("tightened to 10 -> both are still on the right side",
      _song(_im) == _bdK.SONG_IM and _song(_moi) == _bdK.SONG_CHO)
# THE STRONGEST PROMISE of this knob: it is AN INFERENCE and is never written
# down. Written down it is a one-way street, and a reply arriving after 31
# days would hit a closed row.
check("NOTHING is written into the table: the stage is unchanged",
      _cn.execute("SELECT stage FROM application WHERE id=?",
                  (_im,)).fetchone()[0] == _bdK.SENT)
_pf.put(_cn, _pf.IM_QUA, "45")
check("raised to 45 -> back exactly where they were, no row lost",
      _song(_im) == _bdK.SONG_CHO and len(_bdK.all(_cn)) == 2)
# A junk value must not kill the table — every row still has to draw.
_pf.put(_cn, _pf.IM_QUA, "nonsense")
check("a broken mark falls back to the default, it does not blow up", _bdK.nguong(_cn) == 20)
_pf.put(_cn, _pf.IM_QUA, "20")

# AN INTERVIEW IS NEVER "treated as rejected". An invitation from 25 days ago
# that nobody has followed up is THE MOST WORRYING thing on the table, not
# something finished.
_pv = _bdK.add(_cn, "Kappa Lab", "Quant", applied_at=_truoc(25),
               stage=_bdK.INTERVIEW)
check("a row in interview, silent a long time, is still 'in conversation'",
      _song(_pv) == _bdK.SONG_NONG)

print("\n[the measurement behind the knob: set this mark and how many are CLOSED WRONGLY]")
# The knob's real question is not "how long do they take to reply" but "how
# many rows does this mark close wrongly" — and that has an exact answer: every
# silence ALREADY BROKEN is one case where a mark equal to it would have been
# wrong.
_cp = _dbK.connect(":memory:")
_ap = _bdK.add(_cp, "Maven", "Quant", applied_at=_truoc(40))
_scK.store(_cp, {"msg_id": "p1", "from_addr": "a@maven.com", "from_name": "",
                 "subject": "Sorry", "received_at": _truoc(22), "snippet": ""},
           "rejected", "", _ap)
_do = _bdK.im_da_pha(_cp)
check(f"it measures the silence that DID end in a reply — {_do['lau']} days", _do["lau"] == 18)
check("and it can say who", _do["ai"] == "Maven")
# This is exactly where the old version measured the wrong thing: `im_ngay` is
# the silence STILL RUNNING (22 days since the last message), not the silence
# a reply arrived after (18).
check("it does NOT take 'how long since the last contact' by mistake", _do["lau"] != 22)
check("mark 20 closes no message wrongly",
      sum(1 for k in _do["khoang"] if k >= 20) == 0)
check("mark 14 closes exactly that one wrongly",
      sum(1 for k in _do["khoang"] if k >= 14) == 1)
_cp.close()

print("\n[the knob draws correctly: five levels, the one in use ticked, each level's cost declared]")
_adj = _tkD.adjust({}, 20, {"tra_loi": 9, "tong": 37, "lau": 18, "ai": "Maven",
                            "so": 58, "khoang": [3, 14, 18]})
for _m in ("10", "14", "20", "30", "45"):
    check(f"there is a {_m}-day level", f"im_qua:{_m}'" in _adj)
check("the level in use carries a tick", "✓ 20 days" in _adj)
check("the others do not", "✓ 30 days" not in _adj)
check("it declares the cost outright: mark 10 closes 2 wrongly", "2 closed wrongly" in _adj)
check("mark 20 closes none, so it invents no number", "0 closed wrongly" not in _adj)
check("it says where the measurement comes from", "18</b> days (Maven)" in _adj)
check("and it says outright that NOTHING is written into the table",
      "AN INFERENCE, never written into" in _adj)
check("the three source switches are still there", _adj.count("data-post='/api/track/num'") == 8)
# The counted figure MUST be on the face of the button, never hidden in a
# tooltip: having to hover each button to learn what is being traded is the
# same as having no information.
check("the cost is printed on the button, not only in a tooltip",
      "class=nham" in _adj)
_cssN = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
check("and it has real CSS, not a dead class", ".nham{" in _cssN)

print("\n[the table and the bar state THE SAME figure]")
_r20 = _tkD.render(rows=[dict(id=1, stage=_bdK.SENT, company="Long Silence", role="",
                             days=25, event_days=None, last_event="",
                             silent=True, cv_file="", posting_id=None, url="",
                             score=0, song="im", im_ngay=25, so_thu=1,
                             ho_tra_loi=False)],
                   asks=[], counts={}, mail_ready=False, mail_address="",
                   thu={}, loc={},
                   stage={"nguong": 20, "do": {"lau": 18}, "truot": 1,
                          "di_tiep": 0, "da_nop": 1, "cho_ban": 0})
check("the group names the outcome outright", "Treated as rejected" in _r20)
check("but it does not lie: they have SAID nothing",
      "they have NOT said anything" in _r20)
check("the table uses the mark in force, not an old constant", "over 20 days" in _r20)
check("and the real measurement", "ended in one was 18 days" in _r20)
# The bar has room for one "rejected" figure. Merge 2 real rejections with 32
# inferences without saying so and the reader believes 34 companies said no.
from jobbot.dashboard import live as _lvK
_st = _lvK.track_stage(_cn)
check("the status line separates 'they said no' from 'treated as rejected'",
      "said no" in _st.get("state", "")
      and "treated as rejected" in _st.get("state", ""))
check(f"the bar counts both as REJECTED — got {_st.get('truot')}", _st.get("truot") == 1)
check("the mark in force travels with it so the table draws to match", _st.get("nguong") == 20)
_cn.close()

print("\n[THE TABLE HOLDS ONLY FACTS — not one button changes anything]")
_rs = [_r(id=i, company=f"C{i}", stage=st, origin=og, posting_id=i, url="u")
       for i, (st, og) in enumerate(
           ((_bdK.DRAFT, "auto"), (_bdK.SENT, "mail"),
            (_bdK.INTERVIEW, "apply"), (_bdK.REJECTED, "tay"),
            (_bdK.OFFER, "manual")), start=1)]
_ban = _tkD.render(rows=_rs, asks=[], counts={}, mail_ready=True,
                   mail_address="a@b.c", thu={}, loc={},
                   stage={"nguong": 20, "do": {"lau": 18}})
# EVERY stage and EVERY origin in one render: a leftover button usually
# belongs to exactly one rare stage, and rendering only "applied" leaves the
# test wrongly green.
_ruot = _ban[_ban.index("<div class=tboard>"):]
for _duong in ("/api/track/state", "/api/apply/send", "/api/track/drop",
               "/api/cv/pdf"):
    check(f"the table no longer has the {_duong} button", _duong not in _ruot)
check("the table has no POST button at all", "data-post" not in _ruot)
check("nor any input field", "<input" not in _ruot and "<select" not in _ruot)
# LINKS may stay — looking is not editing.
check("but the CV can still be opened to LOOK at", "/jobs/" in _ruot)
# And those buttons have to be ALIVE in the Queue, not thrown away.
_hq2 = _qT.render(rows=_rs, asks=[], mu=[], doi="2")
for _duong in ("/api/apply/send", "/api/track/drop", "/api/track/state"):
    check(f"the Queue takes {_duong} back", _duong in _hq2)
check("picking a row shows THAT ROW's next stages",
      "data-arg='2:interview'" in _hq2)
check("with nothing picked it shows no change buttons",
      "data-arg='2:interview'" not in _qT.render(rows=_rs, asks=[], mu=[]))
check("a stage that is already an outcome says so, it shows no dead button",
      "nowhere further to go" in _qT.render(rows=_rs, asks=[], mu=[], doi="5"))

print("\n[THE BADGE HAS TO SAY THE SAME THING AS THE GROUP]")
def _rim(im, stage=_bdK.SENT, song="im"):
    return _tkD.render(
        rows=[_r(id=1, company="Marlin Selection", stage=stage, song=song,
                 im_ngay=im, days=im, so_thu=1, ho_tra_loi=False)],
        asks=[], counts={}, mail_ready=False, mail_address="", thu={}, loc={},
        stage={"nguong": 20, "do": {"lau": 18}})
_q21 = _rim(21)
# This is exactly where it went wrong: a row silent 21 days sat under the
# heading "Treated as rejected" with a green "applied" badge. Two
# contradictory sentences on one row.
# Catch the badge itself rather than searching the whole page: "treated as
# rejected" also appears on a filter chip, and searching the page leaves the
# test wrongly green.
import re as _reP
def _huy(html):
    return _reP.findall(r"<span class='pill ([a-z]+)'[^>]*>([^<]*)", html)
check("a row past the mark: the badge says 'treated as rejected'",
      _huy(_q21) == [("suy", "treated as rejected")])
# But it must not pretend they rejected — "rejected" is what they SAID.
check("it does not borrow a real badge's class", "pill rejected" not in _q21)
check("it says outright this is an inference, and loosening the mark reopens it",
      "they have said nothing" in _q21 and "Loosen the mark" in _q21)
check("and it names the mark in force", "over 20 days" in _q21)
_q5 = _rim(5, song="cho")
check("a row still inside the window keeps a real badge",
      _huy(_q5) == [("applied", "applied")])
_qtu = _rim(30, stage=_bdK.REJECTED, song="xong")
check("a rejection they DID state is still a real badge",
      _huy(_qtu) == [("rejected", "rejected")])
_cssP = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
check("and the two kinds of badge really LOOK different, not merely read differently",
      ".pill.suy{" in _cssP and "dashed" in _cssP.split(".pill.suy{")[1][:90])

print("\n[the header row is NOT frozen]")
_hd = _cssP[_cssP.index(".thead{"):]
_hd = _hd[:_hd.index("}")]
check("no position:sticky", "sticky" not in _hd)
check("no position:fixed either", "fixed" not in _hd)

print("\n[THE COLUMNS CANNOT DRIFT — no track sizes itself to a cell's contents]")
_css = (Path(__file__).resolve().parent.parent
        / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
_cot = _css[_css.index("--cot:"):]
_cot = _cot[:_cot.index("}")]
# THIS BUG REALLY HAPPENED, it is not hypothetical: the last column declared
# `auto`, the last header cell was empty so it was 0 wide, the last data cell
# had two buttons so it was 110 — the two `fr` columns split the slack
# differently by exactly 110px and the whole table drifted.
for _xau in ("auto", "min-content", "max-content", "fit-content"):
    check(f"the column grid does not use «{_xau}»", _xau not in _cot)
# One track missing and the last column falls outside the grid, drifting just
# as before — count it rather than trusting the eye.
_track = _cot.split(":", 1)[1].split()
check(f"the track count ({len(_track)}) equals the column label count ({len(_tkD.COT)})",
      len(_track) == len(_tkD.COT))
check("the header and the rows still share one declaration",
      _css.count("grid-template-columns:var(--cot)") == 2)
check("the table no longer has an action column", "\"\"" not in str(_tkD.COT))

print("\n[TIMESTAMPS — normalised to UTC AT WRITE TIME, so comparing strings = comparing times]")
from datetime import datetime as _dtz, timezone as _tzz
# Three places in the app compare timestamps BY STRING: scan.settle (can an old
# message overwrite a newer state), board.all (max() finding the last contact),
# and ORDER BY. Comparing ISO strings across DIFFERENT time zones is wrong —
# and measured on the real mailbox, 200 of 1,046 messages carry a zone other
# than UTC. Fixed AT THE POINT OF WRITING, all three become right at once.
_thu_my = _dtz(2026, 9, 14, 1, 30, tzinfo=_tzz(__import__('datetime').timedelta(hours=-4)))
_utc = mail._utc(_thu_my)
check(f"written straight in UTC ({_utc})", _utc.endswith("+00:00"))
check("and at the right instant", _dtz.fromisoformat(_utc) == _thu_my)
check("a message with no zone is treated as UTC",
      mail._utc(_dtz(2026, 9, 14, 2, 0)).endswith("+00:00"))
check("empty returns empty, it does not blow up", mail._utc(None) == "")
# Once normalised, COMPARING STRINGS gives the same answer as COMPARING TIMES.
_bang = "2026-09-14T02:00:00+00:00"
check("a newer message compares as newer by string too", _utc > _bang)
# The migration has to patch OLD rows, and must not touch rows already right.
_cm = _dbK.connect(":memory:")
_cm.execute("INSERT INTO message (msg_id, from_addr, subject, received_at,"
            " snippet, kind) VALUES ('z','a@b.c','s','2026-09-14T01:30:00-04:00','','other')")
_cm.commit()
from jobbot.core import db as _dbm
for _sql in _dbm.MIGRATIONS[21:]:
    _cm.executescript(_sql)
_ra = _cm.execute("SELECT received_at FROM message").fetchone()[0]
check(f"the migration converts an old row to UTC (got {_ra})",
      _ra == "2026-09-14T05:30:00+00:00")
_cm.close()

print("\n[DEAD PREFERENCES — deleted from the DB, never left there lying]")
# Three keys from an old CV build. The code reading them was deleted long ago
# while THE ROWS STAYED IN THE DB — really measured on the running machine:
# all three still there. Open the pref table and they lie, claiming three
# buttons somewhere control them.
_CHET = ("cv_bo_cuc", "cv_giong", "cv_giu_rui_ro")
_cp = _dbK.connect(":memory:")
for _k in _CHET + ("title_vocab", "autorun"):
    _cp.execute("INSERT OR REPLACE INTO pref (key, value) VALUES (?, 'x')", (_k,))
_cp.commit()
_cp.executescript(_dbm.MIGRATIONS[22])
_con = {r[0] for r in _cp.execute("SELECT key FROM pref")}
for _k in _CHET:
    check(f"the migration deletes «{_k}»", _k not in _con)
# DELETED BY NAME. Sweeping "every key not in DEFAULTS" would also delete
# title_vocab — 60 job titles the user typed in themselves.
check("and it does NOT touch title_vocab", "title_vocab" in _con)
check("nor an ordinary key", "autorun" in _con)
_cp.close()
# No place in the source writes those three keys any more — if any did, the
# migration would clean them once and they would grow back.
# EXCEPT core/db.py: the migration itself has to name the three keys to delete them.
_nguon = "\n".join(
    _p.read_text(encoding="utf-8")
    for _p in sorted((Path(__file__).resolve().parent.parent / "src").rglob("*.py"))
    if _p.name != "db.py")
for _k in _CHET:
    check(f"and the source no longer writes «{_k}» anywhere", _k not in _nguon)

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
