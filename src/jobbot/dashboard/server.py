"""The local web server — standard library, nothing installed.

Routing only. Drawing is views/'s job, data is core/'s and live.py's.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from ..core import db
from ..core import journal, scheduler as sched
from ..core.paths import web_dir
from ..profile import store
from ..profile.schema import (BLOCKS, LONGTEXT, MULTI, ROWS, SECTIONS, TEXT,
                             all_questions, section_by_id)
from . import layout, live
from . import upload
from .views import cv as cvview
from .views import cvhealth, importcv
from .filters import JobFilter
# `trackcho`, NOT `queue`: line 9 already imports the standard library's
# `queue`, and the SSE loop catches `queue.Empty`. One name shadowing another
# here means the screen freezes, not an error anybody gets to see.
from .views import (cvlist, cvsoan, home, jobs, profile, search,
                    settings, track, trackcho)

HOST = "127.0.0.1"          # this machine only. Never exposed to the network.

# The pipeline's STAGES. The stage name is a parameter of /api/stage/*, so a
# new feature adds no new route. A stage with no Run button wired yet gets
# said outright by the route, never silently.
STAGES = {"search": "Search", "cv": "CV", "track": "Track"}
DEFAULT_PORT = 8765


# Whether a rebuild is already running in the background. Edit five blocks in
# a row and five 5-second builds must not stack up — only the last one is the
# right one, the other four just burn CPU and get overwritten.
_DANG_DUNG = threading.Lock()


def _tu_dung(conn) -> None:
    """The words on the CV just changed -> rebuild every version, IF the user
    turned it on.

    OFF by default. A build takes ~5 seconds; forcing it on someone who just
    corrected one word takes their decision away from them — exactly what the
    Adjust panel exists to give back.
    """
    from ..core import prefs
    if not prefs.flag(conn, prefs.CV_TU_LO):
        return

    def _chay():
        if not _DANG_DUNG.acquire(blocking=False):
            return                      # one is already running, it takes all
        try:
            from ..cv import batch
            c = db.connect()
            try:
                batch.run(c)
            finally:
                c.close()
        except Exception as exc:                    # noqa: BLE001
            journal.log.error(journal.CV,
                              f"auto rebuild failed — "
                              f"{type(exc).__name__}: {exc}")
        finally:
            _DANG_DUNG.release()

    threading.Thread(target=_chay, daemon=True, name="cv-tu-dung").start()


def _dap_tron(conn, answers: dict) -> int:
    """How many POSTINGS the profile answers IN FULL — every must line covered.

    The whole CV layer's unit. Counted by MATCHES, a skill appearing 50 times
    looks like the most important job while unlocking only 19 more postings;
    counted by postings cleared, the work comes out in the right order (see
    scoring/gap.py).

    Called TWICE around every write into the CV, so the journal can say "129
    -> 141" from a real measurement rather than a promise made before writing.
    """
    from ..scoring.gap import _tin, tin_tron
    from ..scoring.score import build_index
    from ..scoring.vocab import alias_hits
    co: set = set()
    for e in build_index(answers):
        co |= set(alias_hits(e.normal))
    return tin_tron(_tin(conn), co)


def _segments(path: str) -> list[str]:
    """Split the path into parts, then decode EACH part.

    The browser encodes a space as %20, so the key 'machine learning' arrives
    as 'machine%20learning' — matching nothing at all. It has to be decoded.

    Decoding the whole string AND THEN splitting is wrong: '%2F' would become
    '/' and invent a new part. Split first, decode after, and nothing can be
    invented.
    """
    return [unquote(part) for part in path.strip("/").split("/") if part]


def _ghi_khoi(form: dict[str, list[str]], question, cv_text: str) -> str:
    """The form's rows -> blocks inside cv_text.

    Renaming a block means NOTHING points at the old one any more, so it has
    to be deleted; otherwise every rename grows the CV another orphan block.
    Deleting = writing an empty block, which is write_block's existing rule.
    """
    from ..cv.blocks import parse as parse_cv, write_block

    key = question.id
    titles = form.get(f"{key}__title", [])
    metas = form.get(f"{key}__meta", [])
    bodies = form.get(f"{key}__body", [])

    moi = []
    for i, title in enumerate(titles):
        title = title.strip()
        if not title:
            continue
        meta = metas[i].strip() if i < len(metas) else ""
        body = [l.strip() for l in (bodies[i] if i < len(bodies) else "").splitlines()
                if l.strip()]
        moi.append((title, meta, body))

    con = {t for t, _, _ in moi}
    for b in parse_cv(cv_text):
        if b.kind == question.block_kind and b.title.strip() not in con:
            cv_text = write_block(cv_text, b.kind, b.title, "", [])
    for title, meta, body in moi:
        cv_text = write_block(cv_text, question.block_kind, title, meta, body)
    return cv_text


def _split_other(raw: str) -> list[str]:
    """A MULTI question's 'add your own' field -> a list, split on commas or
    newlines."""
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _form_to_answers(form: dict[str, list[str]], section_id: str,
                     current: dict | None = None) -> dict:
    """Read the form according to the SCHEMA's definition, never trusting what
    the browser sent."""
    section = section_by_id(section_id)
    answers: dict = {}
    if section is None:
        return answers

    for question in section.questions:
        values = form.get(question.id, [])
        allowed = {o.value for o in question.options}
        other_raw = form.get(question.id + "__other", [""])[0] if question.allow_other else ""

        if question.kind == MULTI:
            picked = [v for v in values if v in allowed]
            extra = _split_other(other_raw)
            answers[question.id] = picked + [e for e in extra if e not in picked]
        elif question.kind == BLOCKS:
            # Written straight into cv_text — ONE source of truth. The
            # profile is where it is EDITED; the scorer and the CV builder
            # still read the blocks from there, with no copy anywhere.
            answers["cv_text"] = _ghi_khoi(
                form, question, str((current or {}).get("cv_text") or ""))
        elif question.kind == ROWS:
            # Fields sharing a name arrive as PARALLEL ARRAYS in row order.
            # Rebuilt with answer.line() — exactly the grammar
            # answer.educations() reads back, so the form writes something the
            # machine is certain to understand.
            from ..apply.answer import line as edu_line
            cot = [form.get(f"edu_{k}", []) for k in
                   ("degree", "discipline", "school", "start", "end", "note")]
            dong = []
            for hang in zip(*cot):
                txt = edu_line(*(x.strip() for x in hang))
                if txt.strip():
                    dong.append(txt)
            answers[question.id] = "\n".join(dong)
        elif question.tags:
            # A tag box sends ONE hidden input per tag, all sharing a name.
            # Take values[0] as if it were an ordinary text field and every
            # tag but the first silently disappears.
            sach, thay = [], set()
            for v in values:
                v = v.strip()
                if v and v.lower() not in thay:
                    thay.add(v.lower())
                    sach.append(v)
            answers[question.id] = question.tags.join(sach)
        elif question.kind in (TEXT, LONGTEXT):
            answers[question.id] = values[0].strip() if values else ""
        else:                                       # SINGLE
            # A SINGLE question takes the free-text field VERBATIM — never
            # split on commas.
            chosen = values[0] if values and values[0] in allowed else ""
            answers[question.id] = chosen or other_raw.strip()
    return answers


class Handler(BaseHTTPRequestHandler):
    server_version = "jobbot"

    # --- helpers ----------------------------------------------------------
    def _send(self, body: bytes, status: int = 200,
              ctype: str = "text/html; charset=utf-8", no_cache: bool = False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if no_cache:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, markup: str, status: int = 200):
        self._send(markup.encode("utf-8"), status)

    def _redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _404(self):
        self._html(layout.page("Not found", "<h1>404</h1>"
                               "<p class=lead>No such page.</p>"), 404)

    def log_message(self, fmt, *args):            # quieter
        return

    # --- routing -----------------------------------------------------------
    # --- the event stream pushed to the browser ----------------------------
    def _events(self):
        """SSE: one long-lived connection, the server pushes, the browser
        never asks.

        SSE rather than polling: the journal travels ONE way, from the machine
        to the screen. Polling once a second, running 24/7, is 86,400 requests
        a day mostly answering "nothing new". A WebSocket would add a whole
        return direction nobody needs.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        chan = journal.log.subscribe()
        try:
            # Send the current state at once — a tab opened mid-run still
            # sees the truth, rather than waiting for the next event to learn
            # what the machine is doing.
            self._send_event({"type": "hello", **_state_payload(),
                              "events": [e.as_dict()
                                         for e in journal.log.tail(limit=40)][::-1]})
            while True:
                try:
                    self._send_event(chan.get(timeout=20))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")     # keep-alive, so no proxy cuts it
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ValueError):
            pass                     # closing a tab is normal, not an error
        finally:
            journal.log.unsubscribe(chan)

    def _send_event(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"data: {body}\n\n".encode())
        self.wfile.flush()

    def _json(self, payload: dict, status: int = 200):
        return self._send(json.dumps(payload, ensure_ascii=False).encode(),
                          status=status, ctype="application/json; charset=utf-8")

    @staticmethod
    def _start_apply(self, row: dict, pdf) -> None:
        """Open the application page and fill in what can be proved, IN THE
        BACKGROUND.

        The Chrome window stays. The machine does not press Submit — see
        `apply/run.py`: there is no click for it anywhere in there, so it
        cannot happen by accident.
        """
        def _run():
            from ..apply import run as apply_run
            from ..apply.answer import book
            from ..profile import store as pstore

            who = f"{row['company']}: {row['title'][:38]}"
            conn = db.connect()
            try:
                journal.log.emit(journal.SEARCH,
                                 f"opening the application form — {who}")
                report, _tab = apply_run.open_and_fill(
                    row["url"], book(pstore.load(conn)),
                    pdf if pdf and pdf.exists() else None, job=row["id"])
                if report.needs_login:
                    site = (report.needs_login.split("/")[2]
                            if "//" in report.needs_login else "this site")
                    journal.log.error(
                        journal.SEARCH,
                        f"{who} — NOT LOGGED IN to {site}. The apply Chrome "
                        f"window already has that page open: log in once, then "
                        f"press Apply again.")
                    return
                # THE MACHINE CANNOT, SO HAND IT BACK TO THE PERSON — do not
                # let that application drop. The row was already created at
                # /api/apply; relabel it so the Track table files it under
                # "apply by hand", with the application link and the CV link.
                if report.tu_lam:
                    conn.execute(
                        "UPDATE application SET origin = 'tay'"
                        " WHERE posting_id = ? AND stage = ?",
                        (row["id"], "draft"))
                    conn.commit()
                    live.quen()
                    journal.log.warn(
                        journal.SEARCH,
                        f"{who} — the machine could not apply; moved to "
                        f"«apply by hand» on the Track tab")
                journal.log.ok(journal.SEARCH, f"{who} — {report.line()}")
                if report.note:
                    journal.log.emit(journal.SEARCH, f"  {report.note}")
                for label, why, must in report.asks[:8]:
                    journal.log.warn(
                        journal.SEARCH,
                        f"  needs you{' (required)' if must else ''}: "
                        f"{label[:60]}" + (f" — {why}" if why else ""))
                for key in dict.fromkeys(report.missing):
                    journal.log.warn(journal.SEARCH,
                                     f"  the profile has no {key} — fill it in "
                                     f"on the Profile tab and the machine "
                                     f"fills it next time")
                if not pdf or not pdf.exists():
                    journal.log.warn(journal.SEARCH,
                                     "  no PDF printed for this posting — press "
                                     "Print all")
                elif self._stale_pdf(conn, pdf):
                    # Change the email or the phone number and forget to
                    # reprint, and the application carries the old CV — wrong
                    # in exactly the place the employer uses to get in touch.
                    journal.log.warn(journal.SEARCH,
                                     "  the PDF was printed BEFORE the last "
                                     "profile edit — reprint before sending")
                journal.log.emit(journal.SEARCH,
                                 "  the window is open — answer the fields "
                                 "above, then press Send on the Track tab (the "
                                 "machine checks again before it clicks)")
            except Exception as exc:                # noqa: BLE001
                journal.log.error(journal.SEARCH,
                                  f"{who} — opening the form failed: "
                                  f"{type(exc).__name__}: {exc}")
            finally:
                journal.log.done(journal.SEARCH)
                conn.close()

        threading.Thread(target=_run, daemon=True, name="apply").start()

    @staticmethod
    def _stale_pdf(conn, pdf) -> bool:
        """Is the printed copy older than the profile."""
        from datetime import datetime, timezone
        row = conn.execute(
            "SELECT created_at FROM profile_version ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None or not row["created_at"]:
            return False
        try:
            saved = datetime.fromisoformat(row["created_at"])
        except (TypeError, ValueError):
            return False
        if saved.tzinfo is None:
            saved = saved.replace(tzinfo=timezone.utc)
        printed = datetime.fromtimestamp(pdf.stat().st_mtime, tz=timezone.utc)
        return printed < saved

    def _start_send(self, row: dict) -> None:
        """Press Submit on one application, IN THE BACKGROUND.

        The row moves to "applied" ONLY IF the click really landed. Move the
        state on a failed click and the table lies — exactly what adding the
        draft stage was meant to avoid.
        """
        def _run():
            from ..apply import send as apply_send
            from ..track import board

            who = f"{row['company']}: {row['role'][:38]}"
            conn = db.connect()
            try:
                tab = apply_send.find(int(row["posting_id"]))
                if tab is None:
                    board.unclaim(conn, int(row["id"]))
                    journal.log.error(
                        journal.SEARCH,
                        f"{who} — the form window is gone. Press Apply again "
                        f"on the Search tab.")
                    return
                done = apply_send.submit(tab, int(row["posting_id"]))
                if not done.ok:
                    board.unclaim(conn, int(row["id"]))
                    journal.log.warn(journal.SEARCH,
                                     f"{who} — NOT sent: {done.why}")
                    for gap in done.missing[:8]:
                        journal.log.warn(journal.SEARCH,
                                         f"  still empty: {gap[:70]}")
                    return
                board.set_stage(conn, int(row["id"]), board.SENT,
                                "submitted from the app")
                journal.log.ok(journal.SEARCH,
                               f"{who} — {done.why} "
                               f"(button \"{done.button}\")")
                if done.landed:
                    journal.log.emit(journal.SEARCH,
                                     f"  the page after sending: {done.landed}")
            except Exception as exc:                # noqa: BLE001
                board.unclaim(conn, int(row["id"]))
                journal.log.error(journal.SEARCH,
                                  f"{who} — sending failed: "
                                  f"{type(exc).__name__}: {exc}")
            finally:
                journal.log.done(journal.SEARCH)
                conn.close()

        threading.Thread(target=_run, daemon=True, name="send").start()

    def _start_stage(self, stage: str) -> str | None:
        """Start one stage. A new feature adds ONE branch here, not a route.

        Returns None once it is running, or A REASON when it cannot run. It
        never answers "running…" for something the gate just blocked — that
        would be lying to the user.
        """
        if stage == "search":
            conn = db.connect()
            try:
                answers = store.load(conn)
                thieu = store.missing_for_ingest(answers)
            finally:
                conn.close()
            if thieu:
                # The same gate the Profile tab uses — asked in one place,
                # never copied here as a rule of its own.
                hoi = all_questions()
                ten = " · ".join(hoi[q].text for q in thieu if q in hoi)
                return f"the profile is still missing: {ten}"
            runner = sched.current()
            threading.Thread(target=runner.scan_once, daemon=True,
                             name="scan-manual").start()
            return None

        if stage == "track":
            # The Track stage's Run button IS the Scan mail button — one
            # stage, one button, exactly like Search and CV.
            def _quet():
                conn2 = db.connect()
                try:
                    from ..track import scan as tscan
                    tscan.run(conn2)
                    tscan.noi_lai(conn2)
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.SEARCH,
                                      f"the mail scan failed — "
                                      f"{type(exc).__name__}: {exc}")
                finally:
                    conn2.close()
                    live.quen()

            threading.Thread(target=_quet, daemon=True, name="mail-scan").start()
            return None

        if stage == "cv":
            # Building CVs for 364 postings takes 5.3 seconds — far too long
            # to run inside an HTTP response, so it runs IN THE BACKGROUND,
            # with progress in the cv journal stream.
            conn = db.connect()
            try:
                answers = store.load(conn)
                if not (answers.get("cv_text") or "").strip():
                    return ("the profile has no CV yet — import one on the "
                            "Profile tab first")
            finally:
                conn.close()

            def _dung_cv():
                from ..cv import batch
                conn2 = db.connect()
                try:
                    batch.run(conn2)
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.CV,
                                      f"the build failed — "
                                      f"{type(exc).__name__}: {exc}")
                finally:
                    journal.log.done(journal.CV)
                    conn2.close()

            threading.Thread(target=_dung_cv, daemon=True, name="cv-build").start()
            return None
        return f"{STAGES.get(stage, stage)} has no Run button wired yet"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)

        if path == "/static/app.css":
            return self._send((web_dir() / "app.css").read_bytes(),
                              ctype="text/css; charset=utf-8")
        if path == "/static/mau.css":
            # NEVER CACHED. This sheet is a few hundred bytes, and caching it
            # means a colour change is only visible after clearing the browser
            # cache — the user would conclude the button is broken.
            from . import mau as _mau
            conn = db.connect()
            try:
                from ..core import prefs as _prefs
                than = _mau.css(_prefs.get(conn, _prefs.MAU))
            finally:
                conn.close()
            return self._send(than.encode("utf-8"),
                              ctype="text/css; charset=utf-8", no_cache=True)

        if path == "/static/live.js":
            return self._send((web_dir() / "live.js").read_bytes(),
                              ctype="text/javascript; charset=utf-8")
        if path == "/events":
            return self._events()
        if path == "/api/state":
            return self._json(_state_payload())
        if path == "/api/alive":
            # AN IDENTITY MARK for anyone OUTSIDE the process (start.command,
            # the .app wrapper). The port is no longer fixed, and a port where
            # somebody answers 200 does NOT mean jobbot is running — after
            # jobbot dies that port may belong to another app. This line says
            # who is answering, with the PID to check against
            # data/dang-chay.txt.
            import os as _os
            return self._send(f"jobbot {_os.getpid()}\n".encode("utf-8"),
                              ctype="text/plain; charset=utf-8", no_cache=True)

        # --- WIRED TO REAL DATA (step 1) ---
        if path == "/" or path.startswith("/jobs/"):
            conn = db.connect()
            try:
                if path == "/":
                    # ONE read for the whole page (tongquan.tat_ca) —
                    # measured at 0.4s on a 5,166-posting store. Called per
                    # panel instead, each panel rescans the application table,
                    # and four panels can report four different numbers
                    # because they read at four different moments.
                    from . import tongquan
                    return self._html(home.render(
                        live.onboarding(conn),
                        so=tongquan.tat_ca(conn),
                        stage=live.phien_stage(conn)))
                parts = _segments(path)
                found = live.job_detail(conn, parts[1])
                if not found:
                    return self._404()
                if len(parts) == 3 and parts[2] == "cv":
                    import json as _json
                    from ..cv.build import build as build_cv
                    from ..profile import store as pstore
                    answers = pstore.load(conn)
                    explain = _json.loads(found["score_json"]) if found.get("score_json") else None
                    # VIN'S PICKS beat the machine's ordering — see
                    # cv/build.picks
                    from ..cv.build import picks as _picks
                    tailored = build_cv(answers, explain, found['jd'],
                                        pick=_picks(conn, int(found['id'])))
                    return self._html(cvview.render(
                        found, tailored, answers,
                        (query.get("tu") or [""])[0][:200]))
                return self._html(jobs.render_detail(
                    found, (query.get("tu") or [""])[0][:200]))
            finally:
                conn.close()

        if path == "/search":
            conn = db.connect()
            try:
                flt = JobFilter.from_query(query)
                return self._html(search.render(
                    jobs=live.jobs(conn, flt), flt=flt,
                    counts=live.job_counts(conn, flt),
                    sieve=live.sieve(conn),
                    stage=live.search_stage(conn),
                    dem=live.dem_chip(conn, flt)))
            finally:
                conn.close()

        if path == "/track":
            conn = db.connect()
            try:
                from ..core import prefs
                from ..track import board, mail, scan
                hang = board.all(conn)
                return self._html(track.render(
                    rows=hang, asks=scan.proposals(conn),
                    mu=scan.kho_hieu(conn), stage=live.track_stage(conn),
                    thu={r["id"]: board.thu_cua(conn, r["id"]) for r in hang},
                    loc={k: (query.get(k) or [""])[0][:40]
                         for k in ("q", "ng", "ai", "tt", "cv")},
                    counts=board.counts(conn),
                    mail_ready=all(mail.account()),
                    mail_address=mail.account()[0],
                    mail_days=prefs.num(conn, prefs.MAIL_DAYS, 1, 365)))
            finally:
                conn.close()

        if path == "/track/queue":
            # TRACK'S OWN SCREEN — everything the machine CANNOT SETTLE BY
            # ITSELF.
            #
            # It used to be the second panel on the Track tab, where 16 mail
            # cards pushed the table below the fold. The table is what is
            # finished, the queue is what is not — two different rhythms, so
            # two screens.
            conn = db.connect()
            try:
                from ..track import board, scan
                return self._html(trackcho.render(
                    rows=board.all(conn), asks=scan.proposals(conn),
                    mu=scan.kho_hieu(conn), stage=live.track_stage(conn),
                    doi=(query.get("doi") or [""])[0][:12]))
            finally:
                conn.close()

        if path == "/cv/soan":
            # THE CV TAB'S OWN SCREEN — the block editor. It replaces the old
            # /cv/block overlay: that overlay was 380px wide and mute, this
            # screen is the full window and judges every sentence. See
            # views/cvsoan.py.
            #
            # cv_versions is NOT called here. The old overlay called it only
            # to get the list of skills still unspoken — and that is a
            # 5.3-second build, paid every time the editor opens. The GAP
            # ladder (0.6 seconds, cached) answers the same question and
            # answers it better: write about what, and how many more postings
            # clear.
            conn = db.connect()
            try:
                from ..cv import batch
                d = live.cv_soan(conn, batch.saved(conn) or {},
                                 (query.get("khoi") or [""])[0],
                                 (query.get("ky") or [""])[0].strip()[:40],
                                 (query.get("nen") or [""])[0].strip()[:400],
                                 (query.get("soan") or [""])[0].strip()[:400],
                                 bool(query.get("tho")))
                return self._html(cvsoan.render(
                    khoi=d["khoi"], chon=d["chon"], cau=d["cau"], hut=d["hut"],
                    brief=d["brief"], ky=(d["brief"] or {}).get("ky", ""),
                    nen=d["nen"], soan=d["soan"], gy=d["goi_y"], tho=d["tho"],
                    loi=(query.get("loi") or [""])[0][:200],
                    ten=(query.get("khoi") or [""])[0][:120], dap=d["dap"],
                    san=d["san"],
                    moi=bool(query.get("moi")) and d["chon"] is None,
                    stage=batch.stage(conn)))
            finally:
                conn.close()

        if path == "/cv":
            conn = db.connect()
            try:
                # READ THE SAVED BUILD, never build here. Building while
                # drawing the page makes somebody who just finished a search
                # wait 5.3 seconds for something they never asked for. It runs
                # when it is pressed — see cv/batch.py.
                from ..cv import batch
                luu = batch.saved(conn) or {}
                return self._html(cvlist.render(
                    versions=luu.get("versions") or [],
                    jobs=luu.get("jobs") or 0,
                    gaps=luu.get("gaps") or [],
                    core=luu.get("core") or 0,
                    # BLOCKS are drawn at once, with no button: they are the
                    # words Vin just typed, and they cost one profile read.
                    blocks=live.cv_blocks(conn),
                    stage=batch.stage(conn),
                    q=(query.get("q") or [""])[0].strip()[:80],
                    # READ FROM THE SAVED BUILD, never recomputed. The whole
                    # tab shares one moment in time: built together, stale
                    # together, deleted together.
                    gap=luu.get("hut") or {},
                    # The drafts LIVE INSIDE the build, but only SHOW while
                    # the switch is on. Turn it off and leave the old drafts
                    # sitting there and the switch turns nothing off.
                    nhap=(luu.get("nhap") or {})
                    if live.cv_nut(conn).get("tu_lo") else {}))
            finally:
                conn.close()

        if path.startswith("/adjust/"):
            # ADJUST — different from Settings: Settings changes what THE APP
            # DOES (scan pace, time window, mailbox); Adjust changes what THIS
            # SCREEN works on. The same overlay, different contents.
            stage = _segments(path)[-1]
            if stage == "home":
                conn = db.connect()
                try:
                    return self._html(home.adjust(live.phien_stage(conn)["bat"]))
                finally:
                    conn.close()
            if stage not in STAGES:
                return self._404()
            conn = db.connect()
            try:
                if stage == "search":
                    return self._html(search.adjust(live.sieve(conn)))
                if stage == "cv":
                    return self._html(cvlist.adjust(live.cv_nut(conn)))
                if stage == "track":
                    d = live.track_stage(conn)
                    return self._html(track.adjust(
                        d.get("nop"), d.get("nguong") or 20, d.get("do")))
                return self._html(
                    f"<div class=sheethead>Adjust · {STAGES[stage]}</div>"
                    "<div class=sheetwait>nothing to adjust on this stage "
                    "yet</div>")
            finally:
                conn.close()

        if path == "/onboarding":
            # The profile-building run — an HTML FRAGMENT for the overlay.
            # Not a tab: it has a job only at the start.
            conn = db.connect()
            try:
                return self._html(home.sheet(live.onboarding(conn)))
            finally:
                conn.close()

        if path == "/settings":
            # Returns an HTML FRAGMENT, not a page: live.js loads it into the
            # overlay. Settings is a menu you open and close, not a tab.
            conn = db.connect()
            try:
                return self._html(settings.render(**live.settings(conn)))
            finally:
                conn.close()

        # --- profile: wired to the real backend ---
        conn = db.connect()
        try:
            answers = store.load(conn)
            if path == "/profile":
                return self._html(profile.render_summary(
                    answers, len(store.history(conn)),
                    store.missing_for_ingest(answers)))

            if path == "/profile/import":
                return self._html(importcv.render_form())
            if path == "/profile/health":
                return self._html(cvhealth.render(answers.get("cv_text", "")))

            if path == "/api/profile":
                payload = {"answers": answers, "versions": len(store.history(conn)),
                           "can_ingest": store.can_ingest(answers),
                           "missing_for_ingest": store.missing_for_ingest(answers)}
                return self._send(json.dumps(payload, ensure_ascii=False, indent=2).encode(),
                                  ctype="application/json; charset=utf-8")

            if path.startswith("/profile/"):
                section = section_by_id(_segments(path)[-1])
                if section is None:
                    return self._404()
                done = {s.id for s in SECTIONS if store.is_section_done(answers, s)}
                nxt = store.next_section(section.id)
                thieu = store.missing_for_ingest(answers)
                # Not yet enough to run, so the button does NOT promise
                # "continue" — after saving you are still kept here. A button
                # label has to name the job it is about to do.
                if thieu:
                    label = "Save — %d answers still needed" % len(thieu)
                elif nxt:
                    label = f"Save and continue → {nxt.title}"
                else:
                    label = "Save and review profile"
                from ..profile import titles as tvocab
                kho = {"titles": tvocab.cached(conn)}
                return self._html(profile.render_section(
                    section, answers, done, label, thieu, kho))

            self._404()
        finally:
            conn.close()

    def cung_nha(self) -> bool:
        """Did this request COME FROM THE APP ITSELF, or from another website.

        LISTENING ON 127.0.0.1 IS NOT PROTECTION. Any website the user has
        open can call in here with fetch() — the browser stops them READING
        the result, but THE WORK STILL HAPPENS. Really measured on this app: a
        foreign page could change the colour, turn the watch station on, and
        call both /api/reset and /api/apply/send. The second of those breaks
        founding law 4 outright — the machine must never press Send.

        The rules, in the order the browser tells the truth:
          · If `Sec-Fetch-Site` is present, trust it — the browser fills it in
            and a website cannot alter it.
          · Otherwise examine `Origin`, which has to be exactly our own.
          · With neither, it is NOT a browser (curl, a script on this same
            machine) — let it through. A browser ALWAYS sends `Origin` on a
            cross-origin POST, so the absence of both cannot be an attack from
            a website.
        """
        site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if site:
            return site in ("same-origin", "none")
        goc = (self.headers.get("Origin") or "").strip()
        if not goc:
            return True
        try:
            o = urlparse(goc)
        except ValueError:
            return False
        return (o.hostname in ("127.0.0.1", "localhost")
                and str(o.port or "") == str(self.server.server_address[1]))

    def do_POST(self):
        path = urlparse(self.path).path
        # THE LATCH SITS HERE, BEFORE EVERY ROUTE. Put it on each route and
        # every new route has to remember to add it, and one day somebody
        # forgets — and that once might be the route that wipes all the data.
        if not self.cung_nha():
            journal.log.warn(journal.SYSTEM,
                             f"BLOCKED a request from outside the app to "
                             f"{path} — unknown origin")
            return self._json({"ok": False,
                               "note": "requests are only accepted from the "
                                       "app itself"}, status=403)
        length = int(self.headers.get("Content-Length") or 0)
        ctype = self.headers.get("Content-Type", "")
        raw = self.rfile.read(length)

        if path == "/profile/import":
            return self._import_cv(ctype, raw)

        form = parse_qs(raw.decode("utf-8"), keep_blank_values=True)

        if path == "/profile/import/save":
            return self._save_import(form)

        if path == "/api/run":
            runner = sched.current()
            threading.Thread(target=runner.scan_once, daemon=True,
                             name="scan-manual").start()
            return self._json({"ok": True, "state": "running"})

        if path == "/settings":
            conn = db.connect()
            try:
                from ..core import prefs
                # EACH FORM EDITS ONLY ITS OWN PART. The Settings overlay has
                # several forms posting to one path; read blindly, the Sources
                # form (which carries no scan-interval field) would write the
                # 60-minute default over the number the user set.
                phan = form.get("phan", ["chay"])[0]
                if phan == "gmail":
                    prefs.put(conn, prefs.MAIL_DAYS,
                              form.get("mail_days", ["30"])[0])
                    journal.log.emit(journal.SYSTEM,
                                     "changed how many days of mail to reread")
                    return self._html(settings.render(**live.settings(conn),
                                                      mo="gmail"))
                if phan == "telegram":
                    # THE TOKEN GOES INTO config.toml, NOT the DB: the same
                    # place as the Gmail app password (chmod 600, gitignored).
                    # Checked at save time — see bao.luu().
                    from .. import bao as _bao
                    kq = _bao.luu(form.get("token", [""])[0].strip())
                    if form.get("test"):
                        # TEST runs AFTER the save: pasting a token and
                        # pressing Test straight away is normal, and testing
                        # with the old token reports wrongly on the one just
                        # pasted.
                        kq = _bao.thu(conn)
                    return self._html(settings.render(
                        **live.settings(conn), tin_test=kq, mo="bao"))
                if phan == "bao_so":
                    prefs.put(conn, prefs.BAO_NGUONG,
                              form.get("bao_nguong", ["10"])[0])
                    prefs.put(conn, prefs.BAO_GIO, form.get("bao_gio", ["20"])[0])
                    journal.log.emit(journal.SYSTEM,
                                     "changed the notification threshold/hour")
                    return self._html(settings.render(**live.settings(conn),
                                                      mo="bao"))
                if phan == "nguon":
                    bat = set(form.get("ats", []))
                    for ats, key in prefs.SRC_ATS.items():
                        prefs.set_flag(conn, key, ats in bat)
                    prefs.set_flag(conn, prefs.SRC_ALERT, "alert" in bat)
                    journal.log.emit(
                        journal.SYSTEM,
                        "API sources: " + (", ".join(sorted(bat)) or "ALL OFF"))
                    return self._html(settings.render(**live.settings(conn),
                                                      mo="nguon"))
                prefs.put(conn, prefs.SCAN_EVERY, form.get("every", ["60"])[0])
                prefs.put(conn, prefs.HOURS_FROM, form.get("from", ["8"])[0])
                prefs.put(conn, prefs.HOURS_TO, form.get("to", ["22"])[0])
                # Only the three real values are accepted. Junk typed into
                # the URL falls back to the default; a stray string must never
                # slip through and become the call pace.
                from ..ingest.web.linkedin import NHIP
                chon = form.get("pace", ["thuong"])[0]
                prefs.put(conn, prefs.PACE, chon if chon in NHIP else "thuong")
                journal.log.emit(journal.SYSTEM, "settings changed")
                return self._html(settings.render(**live.settings(conn),
                                                  mo="chay"))
            finally:
                conn.close()

        if path == "/api/sieve":
            # The KEEP/DROP sieve lives in THE PROFILE. Once saved, every
            # posting becomes due for re-judging by itself (judged_profile
            # falls behind the version) — derive handles that.
            #
            # AN EMPTY SIEVE IS NOT SAVED. A POST carrying no fields — a form
            # that failed to submit fully, or a stray request — would write
            # empty over the top and wipe the job title list; every posting
            # would then pass the sieve (measured: 197 -> 4,660) and Vin would
            # have no idea why the Search tab is full of junk. The destructive
            # path must not be the default path.
            titles = "\n".join(dict.fromkeys(
                t.strip() for t in form.get("job_titles", []) if t.strip()))
            if not titles:
                return self._json(
                    {"ok": False,
                     "note": "the sieve is empty — at least one job title is "
                             "needed"},
                    status=400)
            conn = db.connect()
            try:
                store.save(conn, {
                    # A tag box posts A LIST of values, one per tag.
                    # Duplicates dropped, the user's order kept.
                    "job_titles": titles,
                    "seniority": form.get("seniority", []),
                    "markets": form.get("markets", []),
                }, note="sieve edited on the Search tab")
            finally:
                conn.close()

            def _rejudge():
                from ..core.derive import derive
                conn = db.connect()
                try:
                    journal.log.emit(journal.SEARCH,
                                     "the sieve changed — re-judging everything")
                    derive(conn)
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.SEARCH,
                                      f"re-judging failed: "
                                      f"{type(exc).__name__} — {exc}")
                finally:
                    journal.log.done(journal.SEARCH)
                    journal.log.done(journal.SCORE)
                    conn.close()

            # Run it in the background and return at once: 1.1 seconds is
            # still 1.1 seconds of a frozen browser, and the journal already
            # shows the progress, so there is nothing to wait for.
            threading.Thread(target=_rejudge, daemon=True, name="rejudge").start()
            return self._redirect("/search")

        if path == "/api/cv/pick":
            # SWAP A SENTENCE on ONE posting. Pin the new one in, drop the
            # old one out — both are sentences Vin HAS ALREADY WRITTEN, so
            # this is still SELECTING, not writing.
            job = form.get("job", [""])[0].strip()
            vao = form.get("text", [""])[0]
            ra = form.get("out", [""])[0]
            if not job.isdigit() or not vao:
                return self._json({"ok": False}, status=400)
            conn = db.connect()
            try:
                from ..cv.build import set_pick
                set_pick(conn, int(job), vao, "pin")
                if ra and ra != vao:
                    set_pick(conn, int(job), ra, "drop")
                journal.log.ok(journal.CV,
                               f"posting #{job}: swapped a sentence on the CV")
            finally:
                conn.close()
            return self._redirect(f"/jobs/{job}/cv")

        if path == "/api/search/xoa":
            # CLEAR THE POSTING STORE to scan again from scratch. A two-layer
            # latch like the CV button, but far heavier: rebuilding the CVs
            # takes 15 seconds, rebuilding the posting store takes a full scan
            # with Chrome open. Postings with an application are KEPT — that
            # is work the user did, and a rescan cannot bring it back.
            if form.get("arg", [""])[0].strip() != "xoa":
                return self._json({"ok": False, "note": "confirmation needed"},
                                  status=400)
            conn = db.connect()
            try:
                from ..core import postings as _pst
                ket = _pst.xoa_kho(conn)
            finally:
                conn.close()
            live.quen()
            journal.log.ok(journal.SEARCH,
                           f"store cleared: dropped {ket['tin']:,} postings, "
                           f"kept {ket['giu']:,} with an application · "
                           f"dropped {ket['ban_cv']} CVs built from that store")
            return self._json({"ok": True, "reload": True,
                               "note": f"dropped {ket['tin']:,} postings"})

        if path == "/api/cv/xoa":
            # DELETE THE BUILT VERSIONS. A two-layer latch: the browser makes
            # it a two-beat press (live.js), the server demands arg="xoa".
            # Never trust the browser side alone — the fuzzing test that threw
            # junk at every route once destroyed the real app password 12
            # times in a row.
            if form.get("arg", [""])[0].strip() != "xoa":
                return self._json({"ok": False, "note": "confirmation needed"},
                                  status=400)
            conn = db.connect()
            try:
                from ..cv import batch
                n = batch.xoa(conn)
            finally:
                conn.close()
            live.quen()
            journal.log.ok(journal.CV,
                           f"deleted {n} built CVs — press Run to rebuild"
                           if n else "there was no version to delete")
            return self._json({"ok": True, "reload": True,
                               "note": f"deleted {n} CVs"})

        if path == "/api/cv/num":
            # The CV layer's KNOBS. Pressing saves at once and does NOT
            # rebuild by itself: a build takes 5 seconds and somebody just
            # trying a setting may not want to pay that. The Run button turns
            # itself into "Update" — see cv/batch.stage.
            from ..core import prefs
            ma, _, gia = form.get("arg", [""])[0].partition(":")
            # Multi-level KNOBS and on/off SWITCHES share one route: both are
            # "change a decision of the CV layer", and giving one job two
            # routes creates two places that can drift apart.
            NHIEU = {"rieng": (prefs.CV_RIENG, prefs.RIENG)}
            TAT_BAT = {"tu_lo": prefs.CV_TU_LO}
            if ma in NHIEU and gia in NHIEU[ma][1]:
                khoa, val = NHIEU[ma][0], gia
            elif ma in TAT_BAT and gia in ("0", "1"):
                khoa, val = TAT_BAT[ma], gia
            else:
                return self._json({"ok": False, "note": "unknown knob"},
                                  status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, val)
                live.quen()
                # MACHINE HANDLES IT handles this pass too: turn the knob and
                # have the screen stay unchanged until Run is pressed by hand,
                # and the switch's name is just talk.
                _tu_dung(conn)
                journal.log.emit(journal.CV, f"knob {ma} -> {val}")
            finally:
                conn.close()
            return self._json({"ok": True, "reload": True})

        if path in ("/api/stage/start", "/api/stage/stop"):
            # TWO routes for EVERY stage, not one route per tab. The stage
            # name is a parameter — a new feature adds no new path.
            from ..core import halt

            stage = form.get("arg", [""])[0].strip()
            if stage not in STAGES:
                return self._json({"ok": False, "note": "unknown stage"},
                                  status=400)
            if path.endswith("/stop"):
                halt.ask(stage)
                journal.log.warn(journal.SEARCH,
                                 f"asked {STAGES[stage]} to stop — it will "
                                 f"stop at the next break point")
                return self._json({"ok": True, "note": "stopping…"})
            halt.clear(stage)
            ly_do = self._start_stage(stage)
            if ly_do:
                return self._json({"ok": False, "note": ly_do}, status=400)
            return self._json({"ok": True, "note": "running…"})

        if path == "/api/apply":
            job = form.get("arg", [""])[0].strip()
            if not job.isdigit():
                return self._json({"ok": False}, status=400)
            conn = db.connect()
            try:
                row = conn.execute(
                    "SELECT id, title, company, url FROM posting WHERE id = ?",
                    (int(job),)).fetchone()
                if row is None:
                    return self._404()
                if not row["url"]:
                    return self._json(
                        {"ok": False, "note": "this posting has no link"},
                        status=400)
                pdf = live.cv_pdf_for(conn, row["id"])
                from ..track import board
                board.add(conn, row["company"], row["title"], posting_id=row["id"],
                          cv_file=pdf.name if pdf and pdf.exists() else "",
                          origin="apply", stage=board.DRAFT)
            finally:
                conn.close()
            self._start_apply(dict(row), pdf)
            return self._json({"ok": True, "note": "opening the form…"})

        if path == "/api/source":
            # TURN a source ON/OFF. The button carries the new state back, so
            # the page is never reloaded — the Adjust overlay stays open and
            # can be pressed again.
            from ..core import prefs
            which = form.get("arg", [""])[0].strip()
            # A lookup, not a chain of ifs: a fourth source changes one line,
            # and the "at least one source must stay on" rule follows by
            # itself.
            KHOA = {"board": prefs.SRC_BOARD, "linkedin": prefs.SRC_LINKEDIN,
                    "alert": prefs.SRC_ALERT}
            khoa = KHOA.get(which)
            if khoa is None:
                return self._json({"ok": False, "note": "unknown source"},
                                  status=400)
            conn = db.connect()
            try:
                dang = prefs.flag(conn, khoa)
                # TURNING THE LAST ONE OFF = scanning with nowhere to scan.
                # That path must not be one stray press away.
                #
                # It counts THE SOURCES LEFT rather than comparing against one
                # other source: the old version knew only two sources, so
                # adding a third let everything be turned off while it still
                # believed one remained.
                con_lai = [k for k in KHOA.values()
                           if k != khoa and prefs.flag(conn, k)]
                if dang and not con_lai:
                    return self._json(
                        {"ok": False, "again": True,
                         "note": "at least one source has to stay on"})
                prefs.set_flag(conn, khoa, not dang)
            finally:
                conn.close()
            bat = not dang
            journal.log.emit(journal.SEARCH,
                             f"source {which}: {'ON' if bat else 'OFF'}")
            # The button's new text has to carry THE SYMBOL too, or one press
            # strips the ◆/⌕ off that button while the other keeps its own.
            # The symbol comes from the one place that holds it, never typed a
            # third time.
            from .views.jobs import NGUON_DAU
            return self._json({"ok": True, "again": True, "on": bat,
                               "note": f"{NGUON_DAU.get(which, '')} {which}"
                                       f" · {'on' if bat else 'off'}"})

        if path == "/api/keep":
            # KEEP a posting the machine dropped — or unkeep it. One button,
            # both ways.
            #
            # `kept` is NEVER written directly: it is a derived column and
            # derive() would overwrite it next time. Here only THE INTENT is
            # written to a column of its own and the posting is marked stale,
            # leaving derive() — the ONE place allowed to judge — to recompute
            # it. That also means the posting just kept is SCORED in the same
            # pass, rather than waiting for the next scan.
            job = form.get("arg", [""])[0].strip()
            if not job.isdigit():
                return self._json({"ok": False}, status=400)
            conn = db.connect()
            try:
                row = conn.execute("SELECT user_keep FROM posting WHERE id=?",
                                   (int(job),)).fetchone()
                if row is None:
                    return self._404()
                moi_gia = 0 if row["user_keep"] else 1
                conn.execute(
                    "UPDATE posting SET user_keep=?, judged_rules='' WHERE id=?",
                    (moi_gia, int(job)))
                conn.commit()
                from ..core.derive import derive
                derive(conn)
            finally:
                conn.close()
            journal.log.emit(
                journal.SEARCH,
                f"posting #{job}: " + ("you KEPT it though the machine dropped "
                                       "it" if moi_gia else "you unkept it"))
            return self._json({"ok": True, "reload": True})

        if path == "/api/track/state":
            pid, _, stage = form.get("arg", [""])[0].partition(":")
            conn = db.connect()
            try:
                from ..track import board
                board.set_stage(conn, int(pid or 0), stage, "edited by hand")
            except ValueError:
                return self._json({"ok": False}, status=400)
            finally:
                conn.close()
            return self._json({"ok": True, "reload": True})

        if path == "/api/apply/send":
            # PRESS SUBMIT. This is the ONLY route into `apply/send.py`, and
            # it runs only when Vin presses that exact row. The machine
            # rereads the form before clicking and refuses while a required
            # field is empty — see send.submit.
            try:
                app_id = int(form.get("arg", ["0"])[0] or 0)
            except ValueError:
                return self._json({"ok": False}, status=400)
            from ..track import board

            conn = db.connect()
            try:
                row = conn.execute(
                    "SELECT a.id, a.company, a.role, a.posting_id, a.stage"
                    " FROM application a WHERE a.id = ?", (app_id,)).fetchone()
                if row is None or not row["posting_id"]:
                    return self._json(
                        {"ok": False, "note": "there is no original posting"},
                        status=400)
                # CLAIM IT, atomically. Comparing `row["stage"] != DRAFT` and
                # then sending is read-then-write: two presses two seconds
                # apart both read 'draft', because the stage change happens on
                # a background thread seconds later. A single
                # UPDATE ... WHERE stage='draft' lets only one press win.
                if not board.claim(conn, int(row["id"])):
                    return self._json(
                        {"ok": False,
                         "note": "this application is being sent, or was sent "
                                 "already"},
                        status=400)
                row = dict(row)
            finally:
                conn.close()
            self._start_send(row)
            return self._json({"ok": True, "note": "checking the form…"})

        if path == "/api/track/nop-tiep":
            # APPLY TO THE NEXT ONE — the bridge from the tracking table to
            # the Search tab. It picks the highest-scoring posting NOT YET
            # applied to anywhere, and only from the sources the user turned
            # on at ⚟ (see prefs.NOP).
            from ..core import prefs
            from ..track import board as tboard
            conn = db.connect()
            try:
                bat = [tboard.nguon_cua(n) for n, k in
                       (("board", prefs.NOP_BOARD), ("linkedin", prefs.NOP_LINKEDIN),
                        ("alert", prefs.NOP_ALERT)) if prefs.flag(conn, k)]
                if not bat:
                    return self._json(
                        {"ok": False,
                         "note": "all three apply sources are off at ⚟"},
                        status=400)
                row = None
                for r in conn.execute(
                        "SELECT id, title, company, url, source FROM posting"
                        " WHERE kept = 1 AND realism IN ('likely','possible')"
                        " AND score >= 80 AND url != ''"
                        " AND id NOT IN (SELECT posting_id FROM application"
                        "                WHERE posting_id IS NOT NULL)"
                        " ORDER BY score DESC, id DESC LIMIT 200"):
                    if tboard.nguon_cua(r["source"]) in bat:
                        row = r
                        break
                if row is None:
                    return self._json(
                        {"ok": False,
                         "note": "no posting worth applying to is left in the "
                                 "sources that are on"},
                        status=400)
                pdf = live.cv_pdf_for(conn, row["id"])
                tboard.add(conn, row["company"], row["title"],
                           posting_id=row["id"],
                           cv_file=pdf.name if pdf and pdf.exists() else "",
                           origin="apply", stage=tboard.DRAFT)
            finally:
                conn.close()
            self._start_apply(dict(row), pdf)
            live.quen()
            return self._json(
                {"ok": True,
                 "note": f"opening the form — {row['company']}"})

        if path == "/api/bao":
            # Four notification switches plus three control levels. One route
            # for the whole tab.
            from ..core import prefs, tele as _tele
            khoa, _, gia = form.get("arg", [""])[0].partition(":")
            if khoa in prefs.BAO and gia in ("0", "1"):
                ghi = (f"notification «{prefs.BAO[khoa][0]}» -> "
                       + ("on" if gia == "1" else "off"))
            elif khoa == "muc" and gia in _tele.MUC_DIEU_KHIEN:
                khoa = prefs.BAO_MUC
                ghi = f"remote control -> {_tele.MUC_DIEU_KHIEN[gia][0]}"
            else:
                return self._json({"ok": False, "note": "unknown knob"},
                                  status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, gia)
            finally:
                conn.close()
            journal.log.ok(journal.SYSTEM, ghi)
            return self._json({"ok": True, "reload": True})

        if path == "/api/chung":
            # WHOLE-APP SETTINGS — the accent colour and go-on-watch-at-open.
            # One route for the whole tab, the same shape as /api/cv/num and
            # /api/track/num.
            from . import mau as _mau
            from ..core import prefs
            khoa, _, gia = form.get("arg", [""])[0].partition(":")
            if khoa == "mau" and gia in _mau.BANG:
                khoa, ghi = prefs.MAU, f"accent colour -> {_mau.BANG[gia][0]}"
            elif khoa == "truc" and gia in ("0", "1"):
                khoa, ghi = (prefs.AUTORUN,
                             "go on watch when the app opens -> "
                             + ("on" if gia == "1" else "off"))
            else:
                return self._json({"ok": False, "note": "unknown knob"},
                                  status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, gia)
            finally:
                conn.close()
            # CHANGING GO-ON-WATCH TELLS THE BACKGROUND LOOP AT ONCE, rather
            # than waiting for the app to be reopened: the switch says "from
            # now", not "next time".
            if khoa == prefs.AUTORUN:
                runner = sched.current()
                runner.resume() if gia == "1" else runner.pause()
            journal.log.ok(journal.SYSTEM, ghi)
            return self._json({"ok": True, "reload": True})

        if path == "/api/home/num":
            # THE SESSION's three switches. The same shape as /api/cv/num and
            # /api/track/num: one layer, one route.
            from ..core import prefs
            khoa, _, gia = form.get("arg", [""])[0].partition(":")
            if khoa not in prefs.PHIEN or gia not in ("0", "1"):
                return self._json({"ok": False, "note": "unknown knob"},
                                  status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, gia)
            finally:
                conn.close()
            journal.log.ok(journal.SYSTEM,
                           f"session · {prefs.PHIEN[khoa][1]} -> "
                           + ("on" if gia == "1" else "off"))
            return self._json({"ok": True, "reload": True})

        if path in ("/api/session/start", "/api/session/stop"):
            # THE SESSION, not a stage. This button also turns THE WATCH
            # STATION on: it runs one round at once, then lets the background
            # loop repeat 24/7 (scheduler.phien_once).
            #
            # Turning the watch station on without running at once is wrong:
            # whoever just pressed it would have to wait for the next tick —
            # possibly an hour — before anything happened, and would think the
            # button was broken.
            from ..core import halt
            runner = sched.current()
            if path.endswith("/stop"):
                runner.pause()
                for khuc in STAGES:
                    halt.ask(khuc)
                return self._json({"ok": True, "reload": True,
                                   "note": "the watch station is off"})
            for khuc in STAGES:
                halt.clear(khuc)
            runner.resume()
            threading.Thread(target=runner.phien_once, daemon=True,
                             name="phien").start()
            return self._json({"ok": True, "reload": True,
                               "note": "the session is running…"})

        if path == "/api/track/num":
            # EVERY KNOB OF THE TRACK LAYER, ONE ROUTE — like /api/cv/num on
            # the CV side. The three source switches and the silence mark are
            # all "change a decision of this layer"; giving one job two routes
            # creates two places that can drift apart.
            #
            # Quite different from /api/source on Search: that one turns
            # SCANNING on and off, this one turns APPLYING on and off. Two
            # questions, two routes.
            from ..core import prefs
            khoa, _, gia = form.get("arg", [""])[0].partition(":")
            if khoa in prefs.NOP and gia in ("0", "1"):
                ghi = (f"apply from {prefs.NOP[khoa][0]} -> "
                       + ("on" if gia == "1" else "off"))
            elif khoa == "im_qua" and gia in prefs.IM_MUC:
                khoa, ghi = (prefs.IM_QUA,
                             f"treat as rejected after {gia} silent days")
            else:
                return self._json({"ok": False, "note": "unknown knob"},
                                  status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, gia)
            finally:
                conn.close()
            journal.log.ok(journal.SEARCH, ghi)
            return self._json({"ok": True, "reload": True})

        if path == "/api/track/xoa":
            # CLEAR THE TABLE — only the rows RECONSTRUCTED FROM MAIL. An
            # application the user made through the app is work they did, and
            # a rescan cannot rebuild it.
            if form.get("arg", [""])[0].strip() != "xoa":
                return self._json({"ok": False, "note": "confirmation needed"},
                                  status=400)
            conn = db.connect()
            try:
                n = conn.execute("SELECT COUNT(*) FROM application"
                                 " WHERE origin = 'mail'").fetchone()[0]
                conn.execute("UPDATE message SET application_id = NULL,"
                             " needs_you = 0 WHERE application_id IN"
                             " (SELECT id FROM application WHERE origin='mail')")
                conn.execute("DELETE FROM application WHERE origin = 'mail'")
                conn.commit()
            finally:
                conn.close()
            live.quen()
            journal.log.ok(journal.SEARCH,
                           f"deleted {n} applications reconstructed from mail "
                           f"— press Scan mail to rebuild them")
            return self._json({"ok": True, "reload": True,
                               "note": f"deleted {n} rows"})

        if path == "/api/track/mail/gan":
            # ATTACH a message to the right application. The missing half of
            # "no message disappears": when the machine reads an outcome but
            # cannot work out the company, the user points at it rather than
            # being offered only Ignore.
            ma, _, app = form.get("arg", [""])[0].partition(":")
            conn = db.connect()
            try:
                from ..track import scan as tscan
                xong = (ma.isdigit() and app.isdigit()
                        and tscan.gan(conn, int(ma), int(app)))
            finally:
                conn.close()
            if not xong:
                return self._json({"ok": False, "note": "could not attach it"},
                                  status=400)
            live.quen()
            return self._json({"ok": True, "reload": True})

        if path == "/api/track/mail/ignore":
            # IGNORE a message the machine could not read: it belongs to no
            # real application, or it is just marketing. The message is not
            # deleted — it simply stops being asked about.
            ma = form.get("arg", [""])[0].strip()
            if not ma.isdigit():
                return self._json({"ok": False}, status=400)
            conn = db.connect()
            try:
                conn.execute("UPDATE message SET needs_you = 0 WHERE id = ?",
                             (int(ma),))
                conn.commit()
            finally:
                conn.close()
            return self._json({"ok": True, "reload": True})

        if path == "/api/track/mail/xep":
            # THE USER FILES a message the machine could not read. This is
            # the other half of the promise that no message disappears: the
            # machine points at where it is stuck, the user decides, and the
            # state changes at once.
            ma, _, loai = form.get("arg", [""])[0].partition(":")
            conn = db.connect()
            try:
                from ..track import scan as tscan
                xong = ma.isdigit() and tscan.xep(conn, int(ma), loai)
            finally:
                conn.close()
            if not xong:
                return self._json({"ok": False, "note": "could not file it"},
                                  status=400)
            live.quen()
            return self._json({"ok": True, "reload": True})

        if path == "/api/track/drop":
            # Only a draft can be deleted — see board.drop.
            conn = db.connect()
            try:
                from ..track import board
                gone = board.drop(conn, int(form.get("arg", ["0"])[0] or 0))
            except ValueError:
                return self._json({"ok": False}, status=400)
            finally:
                conn.close()
            return self._json({"ok": gone, "reload": True})

        if path == "/api/track/mail":
            mid, _, answer = form.get("arg", [""])[0].partition(":")
            conn = db.connect()
            try:
                from ..track import scan
                scan.settle(conn, int(mid or 0), answer == "yes")
            except ValueError:
                return self._json({"ok": False}, status=400)
            finally:
                conn.close()
            return self._json({"ok": True, "reload": True})

        if path == "/api/mail/setup":
            # Vin pastes the app password here rather than opening the file
            # by hand. The password goes STRAIGHT into config.toml (chmod 600,
            # gitignored) and is NEVER drawn back out into HTML — the page
            # shows the address and the state only.
            from ..core import config as cfg
            from ..track import mail as tmail

            address = form.get("address", [""])[0].strip()
            # Google shows app passwords in groups of 4 with spaces, to make
            # copying easier. The spaces are stripped AT SAVE TIME, so what is
            # checked is exactly what is used to log in — the check used to
            # strip them while the login did not, leaving the two paths
            # looking at two different strings.
            secret = form.get("password", [""])[0].strip().replace(" ", "")
            # THE LATCH: the mailbox scanned has to be EXACTLY the mailbox
            # declared in the profile.
            #
            # The profile's address is the one printed on the CV and filled
            # into applications — i.e. the one employers press Reply to.
            # Connect a different mailbox and the app watches one place while
            # the mail arrives at another: the Track table reports "waiting"
            # forever for applications that were answered, with no sign
            # anything is wrong — exactly the worst kind of silent failure.
            conn_ho_so = db.connect()
            try:
                trong_ho_so = (store.load(conn_ho_so).get("email") or "").strip()
            finally:
                conn_ho_so.close()
            if trong_ho_so and address.lower() != trong_ho_so.lower():
                return self._json(
                    {"ok": False,
                     "note": f"this mailbox ({address}) differs from the "
                             f"profile's address ({trong_ho_so}) — replies "
                             f"will arrive at the profile's, not here. Change "
                             f"one of the two so they match."},
                    status=400)
            if not address:
                return self._json({"ok": False, "note": "the address is missing"},
                                  status=400)
            # CHECK FIRST, WRITE AFTER. The old version wrote and then
            # checked, so an account password pasted by mistake had already
            # landed in config.toml despite being rejected — Vin's real
            # password sitting on disk and useful for nothing.
            #
            # The "16 lowercase letters" filter IS GOOGLE'S. Applied to every
            # provider it turns Outlook/iCloud/company mailbox users away at
            # the door with a sentence that has nothing to do with the real
            # reason.
            if (secret and tmail._la_google(tmail.may_chu(address))
                    and not tmail.APP_PASSWORD.fullmatch(secret)):
                return self._json(
                    {"ok": False, "reload": False,
                     "note": "that is not an app password (16 lowercase "
                             "letters)"})
            cfg.write_value("mail", "address", address)
            if secret:
                cfg.write_value("mail", "password", secret)
            saved = tmail.account()
            why = (tmail.check(*saved) if all(saved)
                   else "there is no app password yet")
            if why:
                journal.log.warn(journal.SEARCH,
                                 f"the mailbox is not usable — {why}")
                return self._json({"ok": False, "note": why[:70], "reload": False})
            journal.log.ok(journal.SEARCH,
                           f"mailbox {address} connected — press Scan mail")
            return self._json({"ok": True, "reload": True})

        if path == "/api/titles/refresh":
            # Read the company boards for REAL job titles. No profile needed
            # (the gate only blocks FILTERED scans), no Chrome — plain HTTP.
            # Measured: 21 boards -> 2,226 postings -> 60 title phrases, ~13
            # seconds.
            from ..profile import titles as tvocab
            from ..scan_runner import load_boards
            conn = db.connect()
            try:
                tieu_de = tvocab.fetch_boards(
                    load_boards(conn),
                    log=lambda m: journal.log.warn(journal.SEARCH, m))
                cum = tvocab.extract(tieu_de)
                if not cum:
                    # NEVER write an empty store over the existing one — one
                    # network failure must not lose what was already fetched.
                    return self._json(
                        {"ok": False, "note": "no job title could be fetched"},
                        status=502)
                n = tvocab.save(conn, cum)
            finally:
                conn.close()
            journal.log.ok(journal.SEARCH,
                           f"title store: {n} phrases from {len(tieu_de)} real "
                           f"postings")
            return self._json({"ok": True, "reload": True,
                               "note": f"{n} job titles"})

        if path == "/api/reset":
            # START OVER. The same latch /api/mail/forget had: "xoa" must be
            # sent along, and an empty POST deletes nothing. The fuzzing test
            # that threw junk at every route once destroyed the real app
            # password 12 times in a row — the destructive path must not be
            # the default path.
            if form.get("arg", [""])[0].strip() != "xoa":
                return self._json({"ok": False, "note": "confirmation needed"},
                                  status=400)
            from ..core import reset as reset_mod
            conn = db.connect()
            try:
                ket = reset_mod.run(conn)
                db.migrate(conn)      # rebuild the empty schema, keep user_version
            except OSError as exc:
                # If the backup fails, NOTHING is deleted — reset_mod.run()
                # raises before touching a single row.
                return self._json({"ok": False,
                                   "note": f"could not back up: {exc}"},
                                  status=500)
            finally:
                conn.close()
            journal.log.warn(journal.SYSTEM,
                             f"started over — backup at {ket['backup']}")
            return self._json({"ok": True, "reload": True, "wipe_local": True,
                               "note": f"backed up to {ket['backup']}"})

        # /api/mail/forget IS GONE. Connecting a mailbox is a ONE-OFF, and
        # there is exactly ONE way to remove it: "Start over". Two destructive
        # paths to one thing means two places to press by mistake — and this
        # app password was lost three times in one day.
        #
        # Nothing is lost: pasting a new password has /api/mail/setup
        # overwrite it, so changing the password still works without a delete
        # path of its own.

        if path == "/api/track/mail/scan":
            def _mail():
                from ..track import scan
                conn = db.connect()
                try:
                    scan.run(conn)
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.SEARCH,
                                      f"the mail scan failed — "
                                      f"{type(exc).__name__}: {exc}")
                finally:
                    journal.log.done(journal.SEARCH)
                    conn.close()

            threading.Thread(target=_mail, daemon=True, name="mail").start()
            return self._json({"ok": True, "note": "reading…"})

        if path == "/cv/pdf":
            # Printed IN THE BACKGROUND: open headless Chrome, load the page,
            # print, close — measured in seconds. Doing it while drawing the
            # page freezes the browser.
            job = form.get("arg", [""])[0].strip()
            if not job.isdigit():
                return self._json({"ok": False}, status=400)
            base = f"http://127.0.0.1:{self.server.server_address[1]}"

            def _print():
                from ..cv.pdf import render
                conn = db.connect()
                try:
                    row = conn.execute(
                        "SELECT title, company FROM posting WHERE id = ?",
                        (int(job),)).fetchone()
                    # ONE source of filenames, shared with the batch printer
                    # and with the applying code. Building a name here would
                    # print a file the applying code never looks for.
                    out = live.cv_pdf_for(conn, int(job))
                    if row is None or out is None:
                        return
                    journal.log.progress(journal.CV,
                                         f"printing PDF — {row['title'][:40]}")
                    render(f"{base}/jobs/{job}/cv", out)
                    # HANDED OVER. Printing and then only writing the path
                    # into the journal leaves the user rummaging through
                    # data/cv — that is not "downloaded". It is copied to
                    # Downloads and Finder opened on it.
                    from ..cv.pdf import tai_ve
                    ve = tai_ve(out)
                    journal.log.ok(journal.CV,
                                   f"PDF downloaded: {ve}" if ve
                                   else f"PDF: {out} (could not copy to "
                                        f"Downloads)")
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.CV,
                                      f"printing the PDF failed — "
                                      f"{type(exc).__name__}: {exc}")
                finally:
                    journal.log.done(journal.CV)
                    conn.close()

            threading.Thread(target=_print, daemon=True, name=f"pdf-{job}").start()
            return self._json({"ok": True,
                               "note": "printing… it will appear in Finder"})

        if path == "/cv/block":
            # WRITING ONLY. The reading screen is /cv/soan; this route no
            # longer returns a page. Written straight into cv_text — ONE
            # source of truth. write_block touches only that one block, and
            # every other block keeps its formatting (there is a round-trip
            # test in test_cv.py, because this is the easiest place to swallow
            # a block).
            conn = db.connect()
            try:
                from ..cv.blocks import write_block
                title = form.get("title", [""])[0].strip()
                was = form.get("was", [""])[0].strip()
                ky = form.get("ky", [""])[0].strip()[:40]
                nen = form.get("nen", [""])[0].strip()[:400]
                body = [l.strip() for l in form.get("line", []) if l.strip()]
                if form.get("kill"):
                    body = []                      # an empty body = delete the block
                # TWO WRITE PATHS, ONE ROUTE. The BLOCK EDITOR sends the
                # whole block body; the WRITE ONE SENTENCE screen sends only
                # the new sentence, with `them=1` — it cannot see the old
                # sentences, so it must not be allowed to replace them. Both
                # go through `write_block`, the same latches, the same
                # measurement.
                if form.get("them") and title and body:
                    from ..cv.blocks import parse as parse_cv, sentences
                    cu = next((b for b in parse_cv(
                        store.load(conn).get("cv_text") or "")
                        if b.title == title), None)
                    if cu is not None:
                        body = [x.strip() for x in sentences(cu) if x.strip()] + body
                        form.setdefault("kind", [cu.kind])
                        form.setdefault("meta", [cu.meta])
                # THE GATE THE WHOLE SUGGESTION MECHANISM RESTS ON. The draft
                # base is the employer's words verbatim; leaving them and
                # pressing Save does two kinds of damage at once — whoever
                # screens the CV reads the words from their own job ad, and
                # the user has to defend a claim they never made. It refuses
                # the save but KEEPS what they typed, to carry on editing.
                if nen and not form.get("kill"):
                    from ..scoring.gap import CHO_TRONG, con_trong, qua_giong
                    xau = vi_sao = ""
                    for l in body:
                        if con_trong(l):
                            xau, vi_sao = l, (
                                f"The sentence still has the «{CHO_TRONG}» the "
                                f"machine left. That is the place for THE "
                                f"EVIDENCE, and only you have it: how many, "
                                f"over how much data, how much it changed. "
                                f"Fill it in and save again.")
                            break
                        if qua_giong(l, nen) >= 0.6:
                            xau, vi_sao = l, (
                                "This sentence is still almost word for word "
                                "the employer's line — not yet work YOU did. "
                                "Tell your own real work, with a number: how "
                                "many, over how much data, how much it "
                                "changed.")
                            break
                    if xau:
                        # THE COMPARISON MARK (`nen`) stays their original
                        # line; what the user half-typed travels separately in
                        # `soan`. Fold the two together and every refusal
                        # drags the mark along with the edit, so next time a
                        # verbatim copy passes.
                        cho = "/cv/soan?khoi=" + quote(title or was, safe="")
                        if ky:
                            cho += "&ky=" + quote(ky, safe="")
                        if form.get("moi"):
                            cho += "&moi=1"
                        return self._redirect(
                            cho + "&nen=" + quote(nen, safe="")
                            + "&soan=" + quote(xau, safe="")
                            + "&loi=" + quote(vi_sao, safe=""))
                if title and (body or form.get("kill")):
                    answers = store.load(conn)
                    text = answers.get("cv_text") or ""
                    # MEASURE BEFORE WRITING. "the profile fully answers 129
                    # -> 141 postings" is a real figure measured twice, not a
                    # promise — and it is the only answer to "was writing that
                    # sentence worth it".
                    truoc = _dap_tron(conn, answers)
                    # RENAMING a block: delete the OLD name first.
                    # write_block looks up the NEW name, does not find it, and
                    # so only adds a new block — leaving the CV with BOTH, and
                    # every printed copy carrying two identical sections.
                    if was and was != title:
                        text = write_block(text, form.get("kind", ["project"])[0],
                                           was, "", [])
                    store.save(conn, {"cv_text": write_block(
                        text, form.get("kind", ["project"])[0],
                        title, form.get("meta", [""])[0].strip(), body)},
                        note=f"block edited: {title[:40]}")
                    live.quen()
                    _tu_dung(conn)
                    sau = _dap_tron(conn, store.load(conn))
                    viec = (f"{len(body)} sentences" if body else "deleted")
                    # PRINT THE COVERAGE EVEN WHEN IT DOES NOT MOVE. "you
                    # wrote it and it unlocked no further posting" is exactly
                    # what the writer needs to know at once — silence at that
                    # point lets them believe the sentence landed.
                    doi = (f" — the profile fully answers {truoc} -> {sau} "
                           f"postings" if sau != truoc else
                           f" — the profile still fully answers {sau} postings")
                    # THE `CV` STREAM, not `SCORE`. The journal panel on the
                    # editor screen itself filters on stream="cv"; write it to
                    # another stream and the line "fully answers 129 -> 141
                    # postings" lands where whoever just pressed Save cannot
                    # see it — measured, and read by nobody.
                    journal.log.ok(journal.CV,
                                   f"block «{title[:40]}» — {viec}{doi}")
            finally:
                conn.close()
            # BACK TO WHERE THEY WERE STANDING. Saving and being thrown to
            # the CV list means editing three blocks is three hunts for the
            # fourth — and the verdict strip just recomputed for the edited
            # sentence is seen by nobody. `ky` is kept too: the open brief has
            # to stay, because people usually write two sentences about the
            # same gap.
            if form.get("kill") or not title:
                return self._redirect("/cv/soan")
            # ONCE SAVED the base is dropped: the employer's words have done
            # their job, and keeping them invites the user to save them by
            # mistake a second time.
            tiep = "/cv/soan?khoi=" + quote(title, safe="")
            return self._redirect(tiep + ("&ky=" + quote(ky, safe="") if ky else ""))

        if path == "/api/pause":
            runner = sched.current()
            runner.resume() if runner.paused else runner.pause()
            return self._json({"ok": True, **_state_payload()})

        if path.startswith("/profile/"):
            section_id = _segments(path)[-1]
            conn = db.connect()
            try:
                store.save(conn, _form_to_answers(form, section_id, store.load(conn)),
                           note=f"section: {section_id}")
                # THE SETUP RUN: while the app cannot run yet, go back to
                # what is still missing rather than on to the next section.
                # Drop this rule and the user skims all 5 sections, leaves the
                # three most important answers blank, and then wonders why
                # pressing Run produces nothing.
                giu_lai = store.next_gate_stop(store.load(conn))
                if giu_lai:
                    return self._redirect(giu_lai)
                nxt = store.next_section(section_id)
                return self._redirect(f"/profile/{nxt.id}" if nxt else "/profile")
            finally:
                conn.close()

        self._404()


    # --- importing a CV ----------------------------------------------------
    def _import_cv(self, ctype: str, raw: bytes):
        """Read a file or pasted text and show PROPOSALS — nothing is written
        yet."""
        from ..profile.import_cv import ReadError, propose, read
        try:
            fields = upload.parse(ctype, raw) if "multipart" in ctype else {}
            filename, blob = fields.get("file", ("", b""))
            pasted = fields.get("pasted", ("", b""))[1].decode("utf-8", "replace").strip()
            text = read(filename, blob) if blob else pasted
            if not text.strip():
                raise ReadError("No file chosen and nothing pasted.")
        except (upload.TooBig, ReadError) as exc:
            return self._html(importcv.render_form(str(exc)))
        except Exception as exc:                        # noqa: BLE001
            return self._html(importcv.render_form(f"Could not read it: {exc}"))

        conn = db.connect()
        try:
            found = propose(text, store.load(conn))
        finally:
            conn.close()
        self._html(importcv.render_review(found, text))

    def _save_import(self, form: dict):
        """Write only the fields the user left ticked. Never overwrite a
        field that already has a value."""
        from ..profile.import_cv import propose
        text = form.get("text", [""])[0]
        wanted = set(form.get("accept", []))
        conn = db.connect()
        try:
            found = {p.field: p.value for p in propose(text, store.load(conn))}
            picked = {k: v for k, v in found.items() if k in wanted}
            if picked:
                store.save(conn, picked, note=f"imported CV ({len(picked)} fields)")
            # After importing, do NOT drop the user on the summary page: the
            # machine cannot guess right to work, so there is almost certainly
            # still a question they must answer themselves. Take them straight
            # there rather than making them go looking.
            tiep = store.next_gate_stop(store.load(conn))
        finally:
            conn.close()
        self._redirect(tiep or "/profile")


def find_port(start: int = DEFAULT_PORT, tries: int = 20) -> int:
    for port in range(start, start + tries):
        with socket.socket() as sock:
            if sock.connect_ex((HOST, port)) != 0:
                return port
    raise RuntimeError(f"No free port from {start}")


def serve(port: int | None = None) -> tuple[ThreadingHTTPServer, str]:
    """Build the server. `port=0` -> let THE OPERATING SYSTEM hand out a free
    port.

    The address returned is read BACK from the bound socket rather than built
    from the number passed in: with port=0 the number passed in is 0, and 0 is
    not a port at all.

    Why port=0 exists: `find_port()` asks "is anybody listening on this port"
    and only then binds — and there is a gap between those two steps. Two
    processes running at once (two overlapping test runs) both see it free,
    both bind, and one dies with "Address already in use". Letting the OS hand
    one out leaves no gap to race in.
    """
    httpd = ThreadingHTTPServer((HOST, find_port() if port is None else port),
                                Handler)
    return httpd, f"http://{HOST}:{httpd.server_address[1]}/"


def _state_payload() -> dict:
    """The loop's REAL state, not a hardcoded string.

    The old live.run_status() returned 'idle' even mid-scan, because it looked
    only at the source_run table rather than asking the scheduler. This is the
    one place that knows the truth.
    """
    runner = sched.current()
    return {"state": runner.state(),
            "next_in": runner.next_in() // 60,      # minutes
            "running": journal.log.running()}
