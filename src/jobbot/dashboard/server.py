"""Web server chạy local — thư viện chuẩn, không cài gì thêm.

Chỉ định tuyến. Vẽ là việc của views/, dữ liệu là việc của core/ và live.py.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

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
from .views import (cvlist, home, jobs, profile, search,
                    settings, track)

HOST = "127.0.0.1"          # chỉ máy này truy cập được. Không mở ra mạng.

# Các KHÚC của dây chuyền. Tên khúc là tham số của /api/stage/*, nên thêm một
# chức năng mới thì không đẻ thêm route. Khúc nào chưa nối nút Chạy thì route
# nói thẳng, không im lặng.
STAGES = {"search": "Search", "cv": "CV", "track": "Quản lí"}
DEFAULT_PORT = 8765


def _segments(path: str) -> list[str]:
    """Tách path thành từng mảnh rồi giải mã TỪNG mảnh.

    Trình duyệt mã hoá khoảng trắng thành %20, nên khoá cụm 'machine learning'
    tới đây là 'machine%20learning' — không khớp với gì cả. Phải giải mã.

    Giải mã cả chuỗi RỒI mới tách là sai: '%2F' sẽ hoá thành '/' và tự đẻ ra
    một mảnh mới. Tách trước, giải mã sau thì không đẻ được.
    """
    return [unquote(part) for part in path.strip("/").split("/") if part]


def _ghi_khoi(form: dict[str, list[str]], question, cv_text: str) -> str:
    """Các hàng trên form -> khối trong cv_text.

    Đổi tên một khối = khối cũ KHÔNG còn ai trỏ tới, nên phải xoá nó đi; nếu
    không thì mỗi lần sửa tên là CV mọc thêm một khối mồ côi. Xoá = ghi khối
    rỗng, đúng luật sẵn có của write_block.
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
    """Ô 'add your own' của câu CHỌN-NHIỀU -> danh sách, ngăn bằng phẩy hoặc xuống dòng."""
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _form_to_answers(form: dict[str, list[str]], section_id: str,
                     current: dict | None = None) -> dict:
    """Đọc form theo ĐỊNH NGHĨA trong schema, không tin những gì trình duyệt gửi lên."""
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
            # Ghi thẳng vào cv_text — MỘT nguồn sự thật. Hồ sơ là nơi SỬA;
            # bộ chấm điểm và bộ dựng CV vẫn đọc khối ở đó, không có bản sao.
            answers["cv_text"] = _ghi_khoi(
                form, question, str((current or {}).get("cv_text") or ""))
        elif question.kind == ROWS:
            # Các ô cùng tên gửi lên thành MẢNG SONG SONG theo thứ tự hàng.
            # Dựng lại bằng answer.line() — đúng ngữ pháp answer.educations()
            # đọc vào, nên form ghi ra thứ máy chắc chắn hiểu.
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
            # Ô thẻ gửi MỘT input ẩn cho mỗi thẻ, cùng tên. Lấy values[0] như
            # ô chữ thường thì mọi thẻ trừ cái đầu lặng lẽ biến mất.
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
            # Câu chọn-một lấy NGUYÊN VĂN ô tự do — không cắt theo dấu phẩy.
            chosen = values[0] if values and values[0] in allowed else ""
            answers[question.id] = chosen or other_raw.strip()
    return answers


class Handler(BaseHTTPRequestHandler):
    server_version = "jobbot"

    # --- tiện ích ---------------------------------------------------------
    def _send(self, body: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
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

    def log_message(self, fmt, *args):            # bớt ồn
        return

    # --- định tuyến -------------------------------------------------------
    # --- dòng sự kiện đẩy xuống trình duyệt --------------------------------
    def _events(self):
        """SSE: một kết nối sống lâu, server đẩy xuống, trình duyệt không hỏi.

        Chọn SSE chứ không polling: nhật ký chỉ đi MỘT chiều từ máy xuống màn
        hình. Polling mỗi giây thì 24/7 là 86.400 lượt/ngày cho phần lớn là
        "chưa có gì mới". WebSocket thì thừa nguyên chiều ngược lại.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        chan = journal.log.subscribe()
        try:
            # Gửi ngay trạng thái hiện tại — mở tab giữa chừng vẫn thấy đúng,
            # không phải chờ sự kiện kế tiếp mới biết máy đang làm gì.
            self._send_event({"type": "hello", **_state_payload(),
                              "events": [e.as_dict()
                                         for e in journal.log.tail(limit=40)][::-1]})
            while True:
                try:
                    self._send_event(chan.get(timeout=20))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")     # giữ kết nối, proxy không cắt
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ValueError):
            pass                     # đóng tab là chuyện thường, không phải lỗi
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
        """Mở trang nộp và điền phần chứng minh được, ở NỀN.

        Cửa sổ Chrome ở lại. Máy không bấm Gửi — xem `apply/run.py`: trong đó
        không có lệnh bấm nào, nên không thể lỡ tay.
        """
        def _run():
            from ..apply import run as apply_run
            from ..apply.answer import book
            from ..profile import store as pstore

            who = f"{row['company']}: {row['title'][:38]}"
            conn = db.connect()
            try:
                journal.log.emit(journal.SEARCH, f"mở form nộp — {who}")
                report, _tab = apply_run.open_and_fill(
                    row["url"], book(pstore.load(conn)),
                    pdf if pdf and pdf.exists() else None, job=row["id"])
                if report.needs_login:
                    site = report.needs_login.split("/")[2] if "//" in report.needs_login else "trang này"
                    journal.log.error(
                        journal.SEARCH,
                        f"{who} — CHƯA ĐĂNG NHẬP {site}. Cửa sổ Chrome nộp đang "
                        f"mở sẵn trang đó: đăng nhập một lần rồi bấm Nộp lại.")
                    return
                journal.log.ok(journal.SEARCH, f"{who} — {report.line()}")
                if report.note:
                    journal.log.emit(journal.SEARCH, f"  {report.note}")
                for label, why, must in report.asks[:8]:
                    journal.log.warn(
                        journal.SEARCH,
                        f"  cần bạn{' (bắt buộc)' if must else ''}: "
                        f"{label[:60]}" + (f" — {why}" if why else ""))
                for key in dict.fromkeys(report.missing):
                    journal.log.warn(journal.SEARCH,
                                     f"  hồ sơ thiếu {key} — điền ở tab Hồ sơ, "
                                     f"lần sau máy tự điền")
                if not pdf or not pdf.exists():
                    journal.log.warn(journal.SEARCH,
                                     "  chưa in PDF cho tin này — bấm In hàng loạt")
                elif self._stale_pdf(conn, pdf):
                    # Đổi email hay số điện thoại xong mà quên in lại thì lá
                    # đơn mang bản CV cũ — sai chính chỗ nhà tuyển dụng dùng
                    # để liên lạc.
                    journal.log.warn(journal.SEARCH,
                                     "  PDF in TRƯỚC lần sửa hồ sơ gần nhất — "
                                     "in lại trước khi gửi")
                journal.log.emit(journal.SEARCH,
                                 "  cửa sổ đang mở — trả nốt mấy ô trên, rồi bấm "
                                 "Gửi ở tab Quản lí (máy kiểm lại trước khi bấm)")
            except Exception as exc:                # noqa: BLE001
                journal.log.error(journal.SEARCH,
                                  f"{who} — mở form hỏng: "
                                  f"{type(exc).__name__}: {exc}")
            finally:
                journal.log.done(journal.SEARCH)
                conn.close()

        threading.Thread(target=_run, daemon=True, name="apply").start()

    @staticmethod
    def _stale_pdf(conn, pdf) -> bool:
        """Bản in có cũ hơn hồ sơ không."""
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
        """Bấm Gửi cho một lá đơn, ở NỀN.

        Chuyển dòng sang "đã nộp" CHỈ KHI thật sự bấm được. Bấm hụt mà vẫn đổi
        trạng thái thì bảng nói dối, đúng cái đã tránh khi thêm chặng nháp.
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
                        f"{who} — không thấy cửa sổ form. Bấm Nộp lại ở tab Search.")
                    return
                done = apply_send.submit(tab, int(row["posting_id"]))
                if not done.ok:
                    board.unclaim(conn, int(row["id"]))
                    journal.log.warn(journal.SEARCH, f"{who} — KHÔNG gửi: {done.why}")
                    for gap in done.missing[:8]:
                        journal.log.warn(journal.SEARCH, f"  còn trống: {gap[:70]}")
                    return
                board.set_stage(conn, int(row["id"]), board.SENT, "bấm gửi từ app")
                journal.log.ok(journal.SEARCH,
                               f"{who} — {done.why} (nút \"{done.button}\")")
                if done.landed:
                    journal.log.emit(journal.SEARCH, f"  trang sau khi gửi: {done.landed}")
            except Exception as exc:                # noqa: BLE001
                board.unclaim(conn, int(row["id"]))
                journal.log.error(journal.SEARCH,
                                  f"{who} — gửi hỏng: {type(exc).__name__}: {exc}")
            finally:
                journal.log.done(journal.SEARCH)
                conn.close()

        threading.Thread(target=_run, daemon=True, name="send").start()

    def _start_stage(self, stage: str) -> str | None:
        """Khởi động một khúc. Thêm chức năng mới = thêm MỘT nhánh ở đây,
        không phải thêm một route.

        Trả None nếu đã chạy, hoặc CÂU LÝ DO nếu không chạy được. Không đáp
        "đang chạy…" cho một việc vừa bị cổng chặn — đó là nói dối người dùng.
        """
        if stage == "search":
            conn = db.connect()
            try:
                answers = store.load(conn)
                thieu = store.missing_for_ingest(answers)
            finally:
                conn.close()
            if thieu:
                # Cùng một cổng mà tab Profile đang dùng — hỏi một chỗ, không
                # chép luật sang đây.
                hoi = all_questions()
                ten = " · ".join(hoi[q].text for q in thieu if q in hoi)
                return f"hồ sơ còn thiếu: {ten}"
            runner = sched.current()
            threading.Thread(target=runner.scan_once, daemon=True,
                             name="scan-manual").start()
            return None

        if stage == "cv":
            # Dựng bản CV cho 364 tin mất 5,3 giây — quá lâu để chạy trong
            # lúc trả lời HTTP, nên ở NỀN, tiến độ xem ở nhật ký luồng cv.
            conn = db.connect()
            try:
                answers = store.load(conn)
                if not (answers.get("cv_text") or "").strip():
                    return "hồ sơ chưa có CV — nhập CV ở tab Profile trước"
            finally:
                conn.close()

            def _dung_cv():
                from ..cv import batch
                conn2 = db.connect()
                try:
                    batch.run(conn2)
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.CV,
                                      f"dựng hỏng — {type(exc).__name__}: {exc}")
                finally:
                    journal.log.done(journal.CV)
                    conn2.close()

            threading.Thread(target=_dung_cv, daemon=True, name="cv-build").start()
            return None
        return f"{STAGES.get(stage, stage)} chưa nối nút Chạy"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)

        if path == "/static/app.css":
            return self._send((web_dir() / "app.css").read_bytes(),
                              ctype="text/css; charset=utf-8")
        if path == "/static/live.js":
            return self._send((web_dir() / "live.js").read_bytes(),
                              ctype="text/javascript; charset=utf-8")
        if path == "/events":
            return self._events()
        if path == "/api/state":
            return self._json(_state_payload())

        # --- ĐÃ NỐI DỮ LIỆU THẬT (bước 1) ---
        if path == "/" or path.startswith("/jobs/"):
            conn = db.connect()
            try:
                if path == "/":
                    return self._html(home.render(live.onboarding(conn)))
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
                    tailored = build_cv(answers, explain, found["jd"])
                    return self._html(cvview.render(found, tailored))
                return self._html(jobs.render_detail(found))
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
                return self._html(track.render(
                    rows=board.all(conn), asks=scan.proposals(conn),
                    counts=board.counts(conn),
                    mail_ready=all(mail.account()),
                    mail_address=mail.account()[0],
                    mail_days=prefs.num(conn, prefs.MAIL_DAYS, 1, 365)))
            finally:
                conn.close()

        if path == "/cv/block":
            conn = db.connect()
            try:
                want = (query.get("title") or [""])[0]
                blocks = live.cv_blocks(conn)
                found = next((b for b in blocks if b["title"] == want), None)
                gaps = live.cv_versions(conn)["gaps"]
                return self._html(cvlist.edit(found, gaps))
            finally:
                conn.close()

        if path == "/cv":
            conn = db.connect()
            try:
                # ĐỌC BẢN ĐÃ LƯU, không dựng ở đây. Dựng lúc vẽ trang là bắt
                # người vừa search xong chờ 5,3 giây để xem một thứ họ chưa
                # yêu cầu làm. Bấm thì mới chạy — xem cv/batch.py.
                from ..cv import batch
                luu = batch.saved(conn) or {}
                return self._html(cvlist.render(
                    versions=luu.get("versions") or [],
                    jobs=luu.get("jobs") or 0,
                    gaps=luu.get("gaps") or [],
                    core=luu.get("core") or 0,
                    # KHỐI thì vẽ ngay, không chờ nút: đó là chữ Vin vừa gõ,
                    # và nó chỉ tốn một lần đọc hồ sơ.
                    blocks=live.cv_blocks(conn),
                    stage=batch.stage(conn),
                    q=(query.get("q") or [""])[0].strip()[:80]))
            finally:
                conn.close()

        if path.startswith("/adjust/"):
            # ĐIỀU CHỈNH — khác Cài đặt: Cài đặt đổi thứ APP LÀM (nhịp quét,
            # khung giờ, hộp thư); Điều chỉnh đổi thứ MÀN HÌNH NÀY làm việc
            # trên. Cùng tấm phủ, khác nội dung.
            stage = _segments(path)[-1]
            if stage not in STAGES:
                return self._404()
            conn = db.connect()
            try:
                if stage == "search":
                    return self._html(search.adjust(live.sieve(conn)))
                if stage == "cv":
                    return self._html(cvlist.adjust(live.cv_nut(conn)))
                return self._html(
                    f"<div class=sheethead>Điều chỉnh · {STAGES[stage]}</div>"
                    "<div class=sheetwait>chưa có gì để chỉnh ở khúc này</div>")
            finally:
                conn.close()

        if path == "/onboarding":
            # Chu trình dựng hồ sơ — MẢNH HTML cho tấm phủ. Không phải một tab:
            # việc của nó chỉ có lúc đầu.
            conn = db.connect()
            try:
                return self._html(home.sheet(live.onboarding(conn)))
            finally:
                conn.close()

        if path == "/settings":
            # Trả MẢNH HTML, không phải cả trang: live.js nạp nó vào tấm phủ.
            # Cài đặt là menu bấm ra rồi đóng lại, không phải một tab.
            conn = db.connect()
            try:
                return self._html(settings.render(**live.settings(conn)))
            finally:
                conn.close()

        # --- profile: đã nối backend thật ---
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
                # Chưa đủ chạy thì nút KHÔNG hứa "đi tiếp" — lưu xong vẫn bị
                # giữ lại đây. Nhãn nút phải nói đúng việc nó sắp làm.
                if thieu:
                    label = "Lưu — còn %d câu nữa" % len(thieu)
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

    def do_POST(self):
        path = urlparse(self.path).path
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
                # MỖI FORM CHỈ SỬA PHẦN CỦA NÓ. Tấm Cài đặt có nhiều form gửi
                # về cùng một đường; đọc mù thì form Nguồn (không mang ô nhịp
                # quét) sẽ ghi mặc định 60 phút đè lên con số người dùng đặt.
                phan = form.get("phan", ["chay"])[0]
                if phan == "gmail":
                    prefs.put(conn, prefs.MAIL_DAYS,
                              form.get("mail_days", ["30"])[0])
                    journal.log.emit(journal.SYSTEM, "đổi số ngày đọc lại thư")
                    return self._html(settings.render(**live.settings(conn)))
                if phan == "nguon":
                    bat = set(form.get("ats", []))
                    for ats, key in prefs.SRC_ATS.items():
                        prefs.set_flag(conn, key, ats in bat)
                    prefs.set_flag(conn, prefs.SRC_ALERT, "alert" in bat)
                    journal.log.emit(journal.SYSTEM,
                                     "nguồn API: " + (", ".join(sorted(bat)) or "TẮT HẾT"))
                    return self._html(settings.render(**live.settings(conn)))
                prefs.put(conn, prefs.SCAN_EVERY, form.get("every", ["60"])[0])
                prefs.put(conn, prefs.HOURS_FROM, form.get("from", ["8"])[0])
                prefs.put(conn, prefs.HOURS_TO, form.get("to", ["22"])[0])
                # Chỉ nhận ba giá trị có thật. Gõ bừa vào URL thì về mặc định,
                # không được để một chuỗi lạ chui xuống thành nhịp gọi.
                from ..ingest.web.linkedin import NHIP
                chon = form.get("pace", ["thuong"])[0]
                prefs.put(conn, prefs.PACE, chon if chon in NHIP else "thuong")
                journal.log.emit(journal.SYSTEM, "cài đặt đã đổi")
                return self._html(settings.render(**live.settings(conn)))
            finally:
                conn.close()

        if path == "/api/sieve":
            # Lưới GIỮ/BỎ nằm trong HỒ SƠ. Lưu xong thì mọi tin tự thành cần
            # phán lại (judged_profile lệch phiên bản) — derive lo phần đó.
            # Lưới RỖNG thì KHÔNG lưu. Một POST không mang trường nào — form
            # gửi hụt, hay một yêu cầu lạc — sẽ ghi rỗng đè lên và xoá sạch
            # danh sách chức danh; lúc đó MỌI tin lọt lưới (đo được: 197 -> 4660)
            # và Vin không biết vì sao tab Search đầy rác. Đường phá hoại không
            # được là đường mặc định.
            titles = "\n".join(dict.fromkeys(
                t.strip() for t in form.get("job_titles", []) if t.strip()))
            if not titles:
                return self._json({"ok": False,
                                   "note": "lưới lọc rỗng — cần ít nhất một chức danh"},
                                  status=400)
            conn = db.connect()
            try:
                store.save(conn, {
                    # Ô thẻ gửi lên MỘT DANH SÁCH giá trị, mỗi thẻ một cái.
                    # Bỏ trùng, giữ thứ tự người dùng xếp.
                    "job_titles": titles,
                    "seniority": form.get("seniority", []),
                    "markets": form.get("markets", []),
                }, note="lưới lọc sửa ở tab Search")
            finally:
                conn.close()

            def _rejudge():
                from ..core.derive import derive
                conn = db.connect()
                try:
                    journal.log.emit(journal.SEARCH, "lưới lọc đổi — phán lại tất cả")
                    derive(conn)
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.SEARCH,
                                      f"phán lại hỏng: {type(exc).__name__} — {exc}")
                finally:
                    journal.log.done(journal.SEARCH)
                    journal.log.done(journal.SCORE)
                    conn.close()

            # Chạy nền rồi quay lại ngay: 1,1 giây vẫn là 1,1 giây trình duyệt
            # đứng hình, mà nhật ký hiện tiến độ rồi nên không cần chờ.
            threading.Thread(target=_rejudge, daemon=True, name="rejudge").start()
            return self._redirect("/search")

        if path == "/api/cv/num":
            # BA NÚM của tầng CV. Bấm là lưu ngay, KHÔNG tự dựng lại: dựng mất
            # 5 giây và người vừa xoay thử chưa chắc muốn trả giá đó. Nút Chạy
            # tự đổi thành "Cập nhật" — xem cv/batch.stage.
            from ..core import prefs
            ma, _, gia = form.get("arg", [""])[0].partition(":")
            KHOA = {"giong": (prefs.CV_GIONG, prefs.GIONG),
                    "khoa": (prefs.CV_KHOA, prefs.KHOA),
                    "bo_cuc": (prefs.CV_BO_CUC, prefs.BO_CUC)}
            if ma not in KHOA or gia not in KHOA[ma][1]:
                return self._json({"ok": False, "note": "núm lạ"}, status=400)
            conn = db.connect()
            try:
                prefs.put(conn, KHOA[ma][0], gia)
                live._CV_CACHE.clear()
                journal.log.emit(journal.CV, f"núm {ma} -> {gia}")
            finally:
                conn.close()
            return self._json({"ok": True, "reload": True})

        if path in ("/api/stage/start", "/api/stage/stop"):
            # HAI route cho MỌI khúc, không phải mỗi tab một route. Tên khúc
            # là tham số — thêm một chức năng mới thì không phải thêm đường.
            from ..core import halt

            stage = form.get("arg", [""])[0].strip()
            if stage not in STAGES:
                return self._json({"ok": False, "note": "khúc lạ"}, status=400)
            if path.endswith("/stop"):
                halt.ask(stage)
                journal.log.warn(journal.SEARCH,
                                 f"xin dừng {STAGES[stage]} — sẽ dừng ở "
                                 f"điểm ngắt gần nhất")
                return self._json({"ok": True, "note": "đang dừng…"})
            halt.clear(stage)
            ly_do = self._start_stage(stage)
            if ly_do:
                return self._json({"ok": False, "note": ly_do}, status=400)
            return self._json({"ok": True, "note": "đang chạy…"})

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
                    return self._json({"ok": False, "note": "tin này không có link"},
                                      status=400)
                pdf = live.cv_pdf_for(conn, row["id"])
                from ..track import board
                board.add(conn, row["company"], row["title"], posting_id=row["id"],
                          cv_file=pdf.name if pdf and pdf.exists() else "",
                          origin="apply", stage=board.DRAFT)
            finally:
                conn.close()
            self._start_apply(dict(row), pdf)
            return self._json({"ok": True, "note": "đang mở form…"})

        if path == "/api/source":
            # BẬT/TẮT một nguồn. Nút tự mang trạng thái mới về, nên không phải
            # nạp lại cả trang — tấm phủ Điều chỉnh vẫn mở, bấm tiếp được.
            from ..core import prefs
            which = form.get("arg", [""])[0].strip()
            # Bảng, không phải mấy nhánh if: thêm nguồn thứ tư thì sửa một
            # dòng, và luật "phải còn ít nhất một nguồn" tự đúng theo.
            KHOA = {"board": prefs.SRC_BOARD, "linkedin": prefs.SRC_LINKEDIN,
                    "alert": prefs.SRC_ALERT}
            khoa = KHOA.get(which)
            if khoa is None:
                return self._json({"ok": False, "note": "nguồn lạ"}, status=400)
            conn = db.connect()
            try:
                dang = prefs.flag(conn, khoa)
                # TẮT NỐT CÁI CUỐI = quét mà không lấy ở đâu cả. Đường đó
                # không được là đường bấm nhầm một cái là vào.
                #
                # Đếm mấy nguồn CÒN LẠI chứ không so với đúng một nguồn kia:
                # bản cũ chỉ biết hai nguồn, thêm nguồn thứ ba là nó cho tắt
                # sạch mà vẫn tưởng còn.
                con_lai = [k for k in KHOA.values()
                           if k != khoa and prefs.flag(conn, k)]
                if dang and not con_lai:
                    return self._json({"ok": False, "again": True,
                                       "note": "phải bật ít nhất một nguồn"})
                prefs.set_flag(conn, khoa, not dang)
            finally:
                conn.close()
            bat = not dang
            journal.log.emit(journal.SEARCH,
                             f"nguồn {which}: {'BẬT' if bat else 'TẮT'}")
            # Chữ mới cho nút phải mang cả KÝ HIỆU, không thì bấm một cái là
            # nút rụng mất dấu ◆/⌕ trong khi nút kia vẫn còn. Lấy ký hiệu từ
            # đúng chỗ đang giữ nó, không gõ lại lần thứ ba.
            from .views.jobs import NGUON_DAU
            return self._json({"ok": True, "again": True, "on": bat,
                               "note": f"{NGUON_DAU.get(which, '')} {which}"
                                       f" · {'bật' if bat else 'tắt'}"})

        if path == "/api/keep":
            # GIỮ LẠI một tin máy đã loại — hoặc bỏ giữ. Một nút, hai chiều.
            #
            # KHÔNG sửa thẳng `kept`: đó là cột suy ra, derive() sẽ ghi đè lần
            # sau. Ở đây chỉ ghi Ý MUỐN vào cột riêng rồi đánh dấu tin là cũ,
            # và để derive() — chỗ DUY NHẤT được quyền phán — tự tính lại.
            # Nhờ vậy tin vừa giữ cũng được CHẤM ĐIỂM ngay trong cùng lượt đó,
            # không phải chờ lần quét sau.
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
            journal.log.emit(journal.SEARCH,
                             f"tin #{job}: " + ("bạn GIỮ LẠI dù máy đã loại"
                                                if moi_gia else "bạn bỏ giữ"))
            return self._json({"ok": True, "reload": True})

        if path == "/api/track/state":
            pid, _, stage = form.get("arg", [""])[0].partition(":")
            conn = db.connect()
            try:
                from ..track import board
                board.set_stage(conn, int(pid or 0), stage, "sửa tay")
            except ValueError:
                return self._json({"ok": False}, status=400)
            finally:
                conn.close()
            return self._json({"ok": True, "reload": True})

        if path == "/api/apply/send":
            # BẤM GỬI. Đây là đường DUY NHẤT tới `apply/send.py`, và nó chỉ
            # chạy khi Vin bấm đúng dòng đó. Máy đọc lại form trước khi bấm và
            # từ chối nếu còn ô bắt buộc trống — xem send.submit.
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
                    return self._json({"ok": False, "note": "không có tin gốc"},
                                      status=400)
                # GIÀNH QUYỀN, nguyên tử. So `row["stage"] != DRAFT` rồi mới
                # gửi là đọc-rồi-ghi: hai cú bấm cách nhau hai giây đều đọc
                # thấy 'draft' vì việc đổi chặng xảy ra ở luồng nền, vài giây
                # sau. Một câu UPDATE ... WHERE stage='draft' thì chỉ một cú
                # bấm giành được.
                if not board.claim(conn, int(row["id"])):
                    return self._json({"ok": False,
                                       "note": "đơn này đang gửi hoặc đã gửi rồi"},
                                      status=400)
                row = dict(row)
            finally:
                conn.close()
            self._start_send(row)
            return self._json({"ok": True, "note": "đang kiểm form…"})

        if path == "/api/track/drop":
            # Chỉ xoá được bản nháp — xem board.drop.
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
            # Vin dán app password ở đây thay vì mở tệp bằng tay. Mật khẩu đi
            # THẲNG vào config.toml (chmod 600, đã gitignore) và KHÔNG bao giờ
            # được vẽ ngược ra HTML — trang chỉ hiện địa chỉ và trạng thái.
            from ..core import config as cfg
            from ..track import mail as tmail

            address = form.get("address", [""])[0].strip()
            # Google hiện app password theo nhóm 4 có dấu cách cho dễ chép.
            # Bỏ dấu cách NGAY LÚC LƯU, để thứ đem đi kiểm đúng bằng thứ đem
            # đi đăng nhập — trước đây vòng kiểm bỏ dấu cách còn vòng đăng
            # nhập thì không, hai đường nhìn vào hai chuỗi khác nhau.
            secret = form.get("password", [""])[0].strip().replace(" ", "")
            # CHỐT: hộp thư quét phải ĐÚNG hộp thư khai trong hồ sơ.
            #
            # Địa chỉ trong hồ sơ là địa chỉ in lên CV và điền vào form nộp —
            # tức là chỗ nhà tuyển dụng bấm Trả lời. Nối nhầm một hộp thư
            # khác thì app quét một nơi mà thư về một nơi: bảng Quản lí báo
            # "đang chờ" mãi cho những đơn đã có hồi âm, và không có dấu hiệu
            # nào cho thấy sai — đúng kiểu hỏng im lặng tệ nhất.
            conn_ho_so = db.connect()
            try:
                trong_ho_so = (store.load(conn_ho_so).get("email") or "").strip()
            finally:
                conn_ho_so.close()
            if trong_ho_so and address.lower() != trong_ho_so.lower():
                return self._json(
                    {"ok": False,
                     "note": f"hộp thư này ({address}) khác địa chỉ trong hồ sơ "
                             f"({trong_ho_so}) — thư trả lời sẽ về hồ sơ, không "
                             f"về đây. Sửa một trong hai cho khớp."},
                    status=400)
            if not address:
                return self._json({"ok": False, "note": "thiếu địa chỉ"},
                                  status=400)
            # KIỂM TRƯỚC, GHI SAU. Bản cũ ghi rồi mới kiểm, nên một mật khẩu
            # tài khoản dán nhầm đã kịp nằm trong config.toml dù bị từ chối —
            # mật khẩu thật của Vin nằm trên đĩa mà chẳng dùng được việc gì.
            if secret and not tmail.APP_PASSWORD.fullmatch(secret):
                return self._json({"ok": False, "reload": False, "note":
                                   "đây không phải app password (16 chữ cái thường)"})
            cfg.write_value("mail", "address", address)
            if secret:
                cfg.write_value("mail", "password", secret)
            saved = tmail.account()
            why = tmail.check(*saved) if all(saved) else "chưa có app password"
            if why:
                journal.log.warn(journal.SEARCH, f"hộp thư chưa dùng được — {why}")
                return self._json({"ok": False, "note": why[:70], "reload": False})
            journal.log.ok(journal.SEARCH,
                           f"hộp thư {address} đã nối được — bấm Quét thư")
            return self._json({"ok": True, "reload": True})

        if path == "/api/titles/refresh":
            # Đọc board công ty lấy chức danh THẬT. Không cần hồ sơ (cổng chỉ
            # chặn quét CÓ LỌC), không cần Chrome — thuần HTTP. Đo được: 21
            # board -> 2.226 tin -> 60 cụm nghề, ~13 giây.
            from ..profile import titles as tvocab
            from ..scan_runner import load_boards
            conn = db.connect()
            try:
                tieu_de = tvocab.fetch_boards(
                    load_boards(conn),
                    log=lambda m: journal.log.warn(journal.SEARCH, m))
                cum = tvocab.extract(tieu_de)
                if not cum:
                    # KHÔNG ghi kho rỗng đè lên kho đang có — mạng hỏng một
                    # lần không được làm mất thứ đã lấy được.
                    return self._json({"ok": False,
                                       "note": "không lấy được chức danh nào"},
                                      status=502)
                n = tvocab.save(conn, cum)
            finally:
                conn.close()
            journal.log.ok(journal.SEARCH,
                           f"kho chức danh: {n} cụm từ {len(tieu_de)} tin thật")
            return self._json({"ok": True, "reload": True,
                               "note": f"{n} chức danh"})

        if path == "/api/reset":
            # LÀM LẠI TỪ ĐẦU. Cùng chốt với /api/mail/forget: phải gửi kèm
            # "xoa", một POST rỗng không xoá được gì. Bài thử ném rác vào mọi
            # route từng xoá mất app password thật 12 lần liền — đường phá
            # hoại không được là đường mặc định.
            if form.get("arg", [""])[0].strip() != "xoa":
                return self._json({"ok": False, "note": "cần xác nhận"},
                                  status=400)
            from ..core import reset as reset_mod
            conn = db.connect()
            try:
                ket = reset_mod.run(conn)
                db.migrate(conn)      # dựng lại schema trống, giữ user_version
            except OSError as exc:
                # Sao lưu hỏng thì KHÔNG xoá gì — reset_mod.run() ném ra
                # trước khi đụng tới dòng nào.
                return self._json({"ok": False,
                                   "note": f"không sao lưu được: {exc}"},
                                  status=500)
            finally:
                conn.close()
            journal.log.warn(journal.SYSTEM,
                             f"đã làm lại từ đầu — sao lưu ở {ket['backup']}")
            return self._json({"ok": True, "reload": True, "wipe_local": True,
                               "note": f"đã sao lưu vào {ket['backup']}"})

        # /api/mail/forget ĐÃ BỎ. Nối hộp thư là việc làm MỘT LẦN, và chỉ có
        # MỘT đường xoá: "Làm lại từ đầu". Hai đường phá hoại cho cùng một
        # thứ nghĩa là hai chỗ có thể bấm nhầm — mà app password này đã mất
        # ba lần trong một ngày.
        #
        # Không mất gì: dán mật khẩu mới thì /api/mail/setup ghi đè lên, nên
        # đổi mật khẩu vẫn làm được mà không cần đường xoá riêng.

        if path == "/api/track/mail/scan":
            def _mail():
                from ..track import scan
                conn = db.connect()
                try:
                    scan.run(conn)
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.SEARCH,
                                      f"quét thư hỏng — {type(exc).__name__}: {exc}")
                finally:
                    journal.log.done(journal.SEARCH)
                    conn.close()

            threading.Thread(target=_mail, daemon=True, name="mail").start()
            return self._json({"ok": True, "note": "đang đọc…"})

        if path == "/cv/pdf":
            # In NỀN: mở Chrome headless, tải trang, in, tắt — tính bằng giây.
            # Làm trong lúc vẽ trang là trình duyệt đứng hình.
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
                    # MỘT nguồn tên tệp, dùng chung với máy in hàng loạt và với
                    # phần nộp. Tự ghép tên ở đây là in ra tệp mà phần nộp
                    # không tìm.
                    out = live.cv_pdf_for(conn, int(job))
                    if row is None or out is None:
                        return
                    journal.log.progress(journal.CV, f"in PDF — {row['title'][:40]}")
                    render(f"{base}/jobs/{job}/cv", out)
                    # GIAO TẬN TAY. In xong mà chỉ ghi đường dẫn vào nhật ký
                    # thì người dùng phải đi mò trong data/cv — đó không phải
                    # "tải về". Chép sang Downloads rồi mở Finder trỏ vào nó.
                    from ..cv.pdf import tai_ve
                    ve = tai_ve(out)
                    journal.log.ok(journal.CV,
                                   f"PDF đã tải về: {ve}" if ve
                                   else f"PDF: {out} (không chép được sang Downloads)")
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.CV,
                                      f"in PDF hỏng — {type(exc).__name__}: {exc}")
                finally:
                    journal.log.done(journal.CV)
                    conn.close()

            threading.Thread(target=_print, daemon=True, name=f"pdf-{job}").start()
            return self._json({"ok": True, "note": "đang in… sẽ hiện trong Finder"})

        if path == "/cv/block":
            # Ghi thẳng vào cv_text — MỘT nguồn sự thật. write_block chỉ đụng
            # đúng khối đó, các khối khác giữ nguyên định dạng (có test khứ hồi
            # trong test_cv.py, vì đây là chỗ dễ nuốt mất khối nhất).
            conn = db.connect()
            try:
                from ..cv.blocks import write_block
                title = form.get("title", [""])[0].strip()
                was = form.get("was", [""])[0].strip()
                body = [l.strip() for l in form.get("line", []) if l.strip()]
                if form.get("kill"):
                    body = []                      # thân rỗng = xoá khối
                if title and (body or form.get("kill")):
                    answers = store.load(conn)
                    text = answers.get("cv_text") or ""
                    # ĐỔI TÊN khối: xoá khối tên CŨ trước. write_block tìm theo
                    # tên MỚI, không thấy, nên chỉ thêm khối mới — CV còn CẢ
                    # HAI, và mọi bản in ra có hai mục trùng nội dung.
                    if was and was != title:
                        text = write_block(text, form.get("kind", ["project"])[0],
                                           was, "", [])
                    store.save(conn, {"cv_text": write_block(
                        text, form.get("kind", ["project"])[0],
                        title, form.get("meta", [""])[0].strip(), body)},
                        note=f"soạn khối: {title[:40]}")
                    live._CV_CACHE.clear(); live._BLOCK_CACHE.clear()
                    journal.log.ok(journal.SCORE,
                                   f"CV: khối «{title[:40]}» — "
                                   + (f"{len(body)} câu" if body else "đã xoá"))
            finally:
                conn.close()
            return self._redirect("/cv")

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
                # CHU TRÌNH KHỞI TẠO: chưa đủ để app chạy thì quay lại đúng
                # chỗ còn thiếu, không đi tiếp sang phần sau. Bỏ luật này thì
                # người dùng lướt hết 5 phần, bỏ trống ba câu quan trọng nhất,
                # rồi ngồi thắc mắc vì sao bấm Chạy không ra gì.
                giu_lai = store.next_gate_stop(store.load(conn))
                if giu_lai:
                    return self._redirect(giu_lai)
                nxt = store.next_section(section_id)
                return self._redirect(f"/profile/{nxt.id}" if nxt else "/profile")
            finally:
                conn.close()

        self._404()


    # --- nhập CV ----------------------------------------------------------
    def _import_cv(self, ctype: str, raw: bytes):
        """Đọc file hoặc chữ dán vào rồi hiện ĐỀ XUẤT — chưa ghi gì cả."""
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
        """Chỉ ghi những ô người dùng để tick. Không đè ô đã có sẵn."""
        from ..profile.import_cv import propose
        text = form.get("text", [""])[0]
        wanted = set(form.get("accept", []))
        conn = db.connect()
        try:
            found = {p.field: p.value for p in propose(text, store.load(conn))}
            picked = {k: v for k, v in found.items() if k in wanted}
            if picked:
                store.save(conn, picked, note=f"imported CV ({len(picked)} fields)")
            # Nhập CV xong KHÔNG thả về trang tổng kết: máy không đoán được
            # quyền làm việc, nên gần như chắc chắn vẫn còn câu phải tự trả
            # lời. Đưa thẳng tới đó, đừng bắt người dùng tự đi tìm.
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
    port = port or find_port()
    return ThreadingHTTPServer((HOST, port), Handler), f"http://{HOST}:{port}/"


def _state_payload() -> dict:
    """Trạng thái THẬT của vòng chạy, không phải chuỗi cứng.

    live.run_status() cũ trả 'idle' kể cả lúc đang quét, vì nó chỉ nhìn bảng
    source_run chứ không hỏi scheduler. Đây là chỗ duy nhất biết sự thật.
    """
    runner = sched.current()
    return {"state": runner.state(),
            "next_in": runner.next_in() // 60,      # phút
            "running": journal.log.running()}
