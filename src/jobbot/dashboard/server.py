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
# `trackcho`, KHÔNG phải `queue`: dòng 9 đã `import queue` của thư viện
# chuẩn, và luồng SSE bắt `queue.Empty`. Một cái tên đè lên nhau ở đây
# là màn hình đứng im, không phải lỗi nổ ra cho ai thấy.
from .views import (cvlist, cvsoan, home, jobs, profile, search,
                    settings, track, trackcho)

HOST = "127.0.0.1"          # chỉ máy này truy cập được. Không mở ra mạng.

# Các KHÚC của dây chuyền. Tên khúc là tham số của /api/stage/*, nên thêm một
# chức năng mới thì không đẻ thêm route. Khúc nào chưa nối nút Chạy thì route
# nói thẳng, không im lặng.
STAGES = {"search": "Search", "cv": "CV", "track": "Quản lí"}
DEFAULT_PORT = 8765


# Đang có một lượt dựng lại chạy nền hay chưa. Sửa năm khối liền tay thì
# không được xếp năm lượt dựng 5 giây chồng lên nhau — lượt cuối mới là lượt
# đúng, bốn lượt kia chỉ đốt CPU rồi bị ghi đè.
_DANG_DUNG = threading.Lock()


def _tu_dung(conn) -> None:
    """Chữ trên CV vừa đổi -> dựng lại mọi bản, NẾU người dùng đã bật.

    Mặc định TẮT. Dựng mất ~5 giây; ép nó lên người vừa sửa một chữ là lấy
    mất của họ quyền quyết định, đúng thứ tấm Điều chỉnh sinh ra để trả lại.
    """
    from ..core import prefs
    if not prefs.flag(conn, prefs.CV_TU_LO):
        return

    def _chay():
        if not _DANG_DUNG.acquire(blocking=False):
            return                      # đã có lượt đang chạy, nó sẽ ăn cả
        try:
            from ..cv import batch
            c = db.connect()
            try:
                batch.run(c)
            finally:
                c.close()
        except Exception as exc:                    # noqa: BLE001
            journal.log.error(journal.CV,
                              f"tự dựng lại hỏng — {type(exc).__name__}: {exc}")
        finally:
            _DANG_DUNG.release()

    threading.Thread(target=_chay, daemon=True, name="cv-tu-dung").start()


def _dap_tron(conn, answers: dict) -> int:
    """Bao nhiêu TIN mà hồ sơ đáp TRỌN — mọi dòng must đều nói được.

    Đơn vị của cả tầng CV. Đếm theo LƯỢT khớp thì một kỹ năng xuất hiện 50 lần
    trông như việc quan trọng nhất trong khi nó chỉ mở khoá thêm 19 tin; đếm
    theo tin hết hụt thì xếp đúng thứ tự việc (xem scoring/gap.py).

    Gọi HAI LẦN quanh mỗi phép ghi vào CV, để nhật ký nói được "129 -> 141"
    bằng số đo thật chứ không phải lời hứa trước khi viết.
    """
    from ..scoring.gap import _tin, tin_tron
    from ..scoring.score import build_index
    from ..scoring.vocab import alias_hits
    co: set = set()
    for e in build_index(answers):
        co |= set(alias_hits(e.normal))
    return tin_tron(_tin(conn), co)


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
                # MÁY BÓ TAY THÌ GIAO LẠI CHO NGƯỜI, đừng để lần nộp đó rơi.
                # Dòng đã dựng sẵn ở /api/apply; đổi nhãn để bảng Quản lí xếp
                # nó vào "phải tự nộp tay", kèm đường nộp và đường tải CV.
                if report.tu_lam:
                    conn.execute(
                        "UPDATE application SET origin = 'tay'"
                        " WHERE posting_id = ? AND stage = ?",
                        (row["id"], "draft"))
                    conn.commit()
                    live.quen()
                    journal.log.warn(
                        journal.SEARCH,
                        f"{who} — máy không nộp được, đã chuyển sang "
                        f"«phải tự nộp tay» ở tab Quản lí")
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

        if stage == "track":
            # Nút Chạy của khúc Quản lí LÀ nút Quét thư — một khúc một nút,
            # đúng như Search và CV.
            def _quet():
                conn2 = db.connect()
                try:
                    from ..track import scan as tscan
                    tscan.run(conn2)
                    tscan.noi_lai(conn2)
                except Exception as exc:            # noqa: BLE001
                    journal.log.error(journal.SEARCH,
                                      f"quét thư hỏng — {type(exc).__name__}: {exc}")
                finally:
                    conn2.close()
                    live.quen()

            threading.Thread(target=_quet, daemon=True, name="mail-scan").start()
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
        if path == "/static/mau.css":
            # KHÔNG CHO CACHE. Đây là tấm chỉ vài trăm byte, mà cache nó thì
            # đổi màu xong phải xoá cache trình duyệt mới thấy — người dùng
            # sẽ kết luận cái nút hỏng.
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
            # DẤU NHẬN DẠNG cho người NGOÀI tiến trình (start.command, vỏ
            # .app). Cổng không còn cố định, và một cổng có ai đó trả lời
            # 200 KHÔNG có nghĩa jobbot đang chạy — sau khi jobbot chết,
            # cổng đó có thể đã thuộc về app khác. Dòng này nói rõ ai
            # đang trả lời, kèm PID để đối chiếu với data/dang-chay.txt.
            import os as _os
            return self._send(f"jobbot {_os.getpid()}\n".encode("utf-8"),
                              ctype="text/plain; charset=utf-8", no_cache=True)

        # --- ĐÃ NỐI DỮ LIỆU THẬT (bước 1) ---
        if path == "/" or path.startswith("/jobs/"):
            conn = db.connect()
            try:
                if path == "/":
                    # MỘT lượt đọc cho cả trang (tongquan.tat_ca) — đo 0,4s
                    # trên kho 5.166 tin. Tách ra gọi từng ô thì mỗi ô lại
                    # quét lại bảng application, và bốn ô có thể nói bốn con
                    # số khác nhau vì đọc ở bốn thời điểm.
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
                                        # LỰA CHỌN CỦA VIN thắng cách máy xếp — xem cv/build.picks
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
            # MÀN CON của Quản lí — mọi thứ máy KHÔNG TỰ CHỐT ĐƯỢC.
            #
            # Trước đây nó là ô thứ hai ngay trên tab Quản lí, và 16 thẻ thư
            # đẩy cái bảng xuống dưới một màn hình. Bảng là thứ đã xong, hàng
            # chờ là thứ chưa xong — hai nhịp khác nhau, nên hai màn.
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
            # MÀN CON của tab CV — chỗ soạn khối. Thay cho tấm phủ /cv/block
            # cũ: tấm phủ rộng 380px và câm, màn này rộng cả cửa sổ và chấm
            # từng câu. Xem views/cvsoan.py.
            #
            # KHÔNG gọi cv_versions ở đây. Tấm phủ cũ gọi nó chỉ để lấy danh
            # sách kỹ năng còn câm — mà đó là lượt dựng 5,3 giây, trả giá mỗi
            # lần mở chỗ soạn. Thang HỤT (0,6 giây, có nhớ) trả lời đúng câu
            # đó và trả lời rõ hơn: viết về cái gì thì thêm bao nhiêu tin.
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
                    q=(query.get("q") or [""])[0].strip()[:80],
                    # ĐỌC TỪ BẢN ĐÃ DỰNG, không tính lại. Cả tab một mốc thời
                    # gian: dựng cùng lúc, cũ cùng lúc, xoá cùng lúc.
                    gap=luu.get("hut") or {},
                    # Bản nháp NẰM TRONG bản dựng, nhưng chỉ HIỆN khi công tắc
                    # đang bật. Tắt xong mà nháp cũ còn nằm đó thì công tắc
                    # không tắt được cái gì.
                    nhap=(luu.get("nhap") or {})
                    if live.cv_nut(conn).get("tu_lo") else {}))
            finally:
                conn.close()

        if path.startswith("/adjust/"):
            # ĐIỀU CHỈNH — khác Cài đặt: Cài đặt đổi thứ APP LÀM (nhịp quét,
            # khung giờ, hộp thư); Điều chỉnh đổi thứ MÀN HÌNH NÀY làm việc
            # trên. Cùng tấm phủ, khác nội dung.
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

    def cung_nha(self) -> bool:
        """Yêu cầu này có ĐẾN TỪ CHÍNH APP không, hay từ một trang web khác.

        NGHE Ở 127.0.0.1 KHÔNG PHẢI LÀ BẢO VỆ. Bất kỳ trang web nào người
        dùng mở cũng gọi được vào đây bằng fetch() — trình duyệt chặn họ ĐỌC
        kết quả, nhưng VIỆC VẪN XẢY RA. Đo thật trên chính app này: một trang
        lạ đổi được màu, bật được trạm trực, và gọi được cả /api/reset lẫn
        /api/apply/send. Cái thứ hai là phá thẳng luật nền số 4 — máy không
        bao giờ được bấm Gửi hộ.

        Luật, theo đúng thứ tự trình duyệt nói thật:
          · `Sec-Fetch-Site` có thì tin nó — trình duyệt tự điền, trang web
            không sửa được.
          · Không có thì xét `Origin`, phải trùng đúng nhà mình.
          · Không có cả hai thì KHÔNG phải trình duyệt (curl, script trên
            chính máy này) — cho qua. Trình duyệt LUÔN gửi `Origin` cho POST
            khác nguồn, nên vắng cả hai không thể là tấn công từ trang web.
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
        # CHỐT ĐẶT Ở ĐÂY, TRƯỚC MỌI ĐƯỜNG. Đặt ở từng route thì thêm một
        # route mới là phải nhớ thêm chốt, và sẽ có lần quên — mà lần quên đó
        # có thể là đường xoá sạch dữ liệu.
        if not self.cung_nha():
            journal.log.warn(journal.SYSTEM,
                             f"CHẶN yêu cầu từ ngoài app tới {path} — "
                             f"origin lạ")
            return self._json({"ok": False, "note": "chỉ nhận yêu cầu từ "
                                                    "chính app"}, status=403)
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
                    return self._html(settings.render(**live.settings(conn),
                                                      mo="gmail"))
                if phan == "telegram":
                    # TOKEN VÀO config.toml, KHÔNG vào DB: cùng chỗ với app
                    # password Gmail (chmod 600, đã gitignore). Kiểm ngay lúc
                    # lưu — xem bao.luu().
                    from .. import bao as _bao
                    kq = _bao.luu(form.get("token", [""])[0].strip())
                    if form.get("test"):
                        # TEST chạy SAU khi lưu: người dùng dán token rồi bấm
                        # thẳng Test là chuyện thường, và test bằng token cũ
                        # thì nó báo sai về cái vừa dán.
                        kq = _bao.thu(conn)
                    return self._html(settings.render(
                        **live.settings(conn), tin_test=kq, mo="bao"))
                if phan == "bao_so":
                    prefs.put(conn, prefs.BAO_NGUONG,
                              form.get("bao_nguong", ["10"])[0])
                    prefs.put(conn, prefs.BAO_GIO, form.get("bao_gio", ["20"])[0])
                    journal.log.emit(journal.SYSTEM, "đổi ngưỡng/giờ thông báo")
                    return self._html(settings.render(**live.settings(conn),
                                                      mo="bao"))
                if phan == "nguon":
                    bat = set(form.get("ats", []))
                    for ats, key in prefs.SRC_ATS.items():
                        prefs.set_flag(conn, key, ats in bat)
                    prefs.set_flag(conn, prefs.SRC_ALERT, "alert" in bat)
                    journal.log.emit(journal.SYSTEM,
                                     "nguồn API: " + (", ".join(sorted(bat)) or "TẮT HẾT"))
                    return self._html(settings.render(**live.settings(conn),
                                                      mo="nguon"))
                prefs.put(conn, prefs.SCAN_EVERY, form.get("every", ["60"])[0])
                prefs.put(conn, prefs.HOURS_FROM, form.get("from", ["8"])[0])
                prefs.put(conn, prefs.HOURS_TO, form.get("to", ["22"])[0])
                # Chỉ nhận ba giá trị có thật. Gõ bừa vào URL thì về mặc định,
                # không được để một chuỗi lạ chui xuống thành nhịp gọi.
                from ..ingest.web.linkedin import NHIP
                chon = form.get("pace", ["thuong"])[0]
                prefs.put(conn, prefs.PACE, chon if chon in NHIP else "thuong")
                journal.log.emit(journal.SYSTEM, "cài đặt đã đổi")
                return self._html(settings.render(**live.settings(conn),
                                                  mo="chay"))
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

        if path == "/api/cv/pick":
            # ĐỔI CÂU cho MỘT tin. Ghim câu mới vào, gạt câu cũ ra — cả hai
            # đều là câu Vin ĐÃ VIẾT, nên đây vẫn là CHỌN, không phải viết.
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
                journal.log.ok(journal.CV, f"tin #{job}: đổi câu trên CV")
            finally:
                conn.close()
            return self._redirect(f"/jobs/{job}/cv")

        if path == "/api/search/xoa":
            # DỌN KHO TIN để quét lại từ đầu. Chốt hai lớp như nút bên CV,
            # nhưng nặng hơn nhiều: bản CV dựng lại mất 15 giây, kho tin dựng
            # lại mất một lượt quét đầy đủ có mở Chrome. Tin đã có đơn thì
            # GIỮ — đó là việc người dùng đã làm, quét lại không lấy lại được.
            if form.get("arg", [""])[0].strip() != "xoa":
                return self._json({"ok": False, "note": "cần xác nhận"},
                                  status=400)
            conn = db.connect()
            try:
                from ..core import postings as _pst
                ket = _pst.xoa_kho(conn)
            finally:
                conn.close()
            live.quen()
            journal.log.ok(journal.SEARCH,
                           f"đã dọn kho: bỏ {ket['tin']:,} tin, "
                           f"giữ {ket['giu']:,} tin đã có đơn · "
                           f"bỏ {ket['ban_cv']} bản CV dựng từ kho đó")
            return self._json({"ok": True, "reload": True,
                               "note": f"đã bỏ {ket['tin']:,} tin"})

        if path == "/api/cv/xoa":
            # XOÁ BẢN ĐÃ DỰNG. Chốt hai lớp: trình duyệt bắt bấm hai nhịp
            # (live.js), máy chủ đòi arg="xoa". Không bao giờ tin mỗi phía
            # trình duyệt — bài thử ném rác vào mọi route từng xoá mất app
            # password thật 12 lần liền.
            if form.get("arg", [""])[0].strip() != "xoa":
                return self._json({"ok": False, "note": "cần xác nhận"},
                                  status=400)
            conn = db.connect()
            try:
                from ..cv import batch
                n = batch.xoa(conn)
            finally:
                conn.close()
            live.quen()
            journal.log.ok(journal.CV,
                           f"đã xoá {n} bản CV đã dựng — bấm Chạy để dựng lại"
                           if n else "chưa có bản nào để xoá")
            return self._json({"ok": True, "reload": True,
                               "note": f"đã xoá {n} bản CV"})

        if path == "/api/cv/num":
            # BA NÚM của tầng CV. Bấm là lưu ngay, KHÔNG tự dựng lại: dựng mất
            # 5 giây và người vừa xoay thử chưa chắc muốn trả giá đó. Nút Chạy
            # tự đổi thành "Cập nhật" — xem cv/batch.stage.
            from ..core import prefs
            ma, _, gia = form.get("arg", [""])[0].partition(":")
            # NÚM nhiều mức và CÔNG TẮC bật/tắt đi chung một đường: cả hai đều
            # là "đổi một quyết định của tầng CV", và đẻ hai route cho cùng một
            # việc là đẻ hai chỗ có thể lệch nhau.
            NHIEU = {"rieng": (prefs.CV_RIENG, prefs.RIENG)}
            TAT_BAT = {"tu_lo": prefs.CV_TU_LO}
            if ma in NHIEU and gia in NHIEU[ma][1]:
                khoa, val = NHIEU[ma][0], gia
            elif ma in TAT_BAT and gia in ("0", "1"):
                khoa, val = TAT_BAT[ma], gia
            else:
                return self._json({"ok": False, "note": "núm lạ"}, status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, val)
                live.quen()
                # MÁY TỰ LO thì lo luôn cả lượt này: xoay núm xong mà màn hình
                # y nguyên cho tới khi tự đi bấm Chạy thì cái tên công tắc là
                # lời nói suông.
                _tu_dung(conn)
                journal.log.emit(journal.CV, f"núm {ma} -> {val}")
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

        if path == "/api/track/nop-tiep":
            # NỘP TIN KẾ TIẾP — cây cầu từ bảng theo dõi sang tab Search.
            # Chọn tin điểm cao nhất CHƯA nộp chỗ nào, và chỉ trong mấy nguồn
            # người dùng đã bật ở ⚟ (xem prefs.NOP).
            from ..core import prefs
            from ..track import board as tboard
            conn = db.connect()
            try:
                bat = [tboard.nguon_cua(n) for n, k in
                       (("board", prefs.NOP_BOARD), ("linkedin", prefs.NOP_LINKEDIN),
                        ("alert", prefs.NOP_ALERT)) if prefs.flag(conn, k)]
                if not bat:
                    return self._json({"ok": False,
                                       "note": "đã tắt cả ba nguồn nộp ở ⚟"},
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
                    return self._json({"ok": False,
                                       "note": "không còn tin đáng nộp nào "
                                               "trong mấy nguồn đang bật"},
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
            return self._json({"ok": True,
                               "note": f"đang mở form — {row['company']}"})

        if path == "/api/bao":
            # Bốn công tắc báo + ba mức điều khiển. Một đường cho cả tab.
            from ..core import prefs, tele as _tele
            khoa, _, gia = form.get("arg", [""])[0].partition(":")
            if khoa in prefs.BAO and gia in ("0", "1"):
                ghi = (f"báo «{prefs.BAO[khoa][0]}» -> "
                       + ("bật" if gia == "1" else "tắt"))
            elif khoa == "muc" and gia in _tele.MUC_DIEU_KHIEN:
                khoa = prefs.BAO_MUC
                ghi = f"điều khiển từ xa -> {_tele.MUC_DIEU_KHIEN[gia][0]}"
            else:
                return self._json({"ok": False, "note": "núm lạ"}, status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, gia)
            finally:
                conn.close()
            journal.log.ok(journal.SYSTEM, ghi)
            return self._json({"ok": True, "reload": True})

        if path == "/api/chung":
            # CÀI ĐẶT CỦA CẢ APP — màu nhấn và tự-trực-khi-mở. Một đường cho
            # cả tab, cùng khuôn với /api/cv/num và /api/track/num.
            from . import mau as _mau
            from ..core import prefs
            khoa, _, gia = form.get("arg", [""])[0].partition(":")
            if khoa == "mau" and gia in _mau.BANG:
                khoa, ghi = prefs.MAU, f"màu nhấn -> {_mau.BANG[gia][0]}"
            elif khoa == "truc" and gia in ("0", "1"):
                khoa, ghi = (prefs.AUTORUN,
                             "tự trực khi mở app -> "
                             + ("bật" if gia == "1" else "tắt"))
            else:
                return self._json({"ok": False, "note": "núm lạ"}, status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, gia)
            finally:
                conn.close()
            # ĐỔI TỰ-TRỰC THÌ BÁO LUÔN CHO VÒNG NỀN, đừng đợi mở lại app: cái
            # công tắc nói "từ giờ", không phải "lần sau".
            if khoa == prefs.AUTORUN:
                runner = sched.current()
                runner.resume() if gia == "1" else runner.pause()
            journal.log.ok(journal.SYSTEM, ghi)
            return self._json({"ok": True, "reload": True})

        if path == "/api/home/num":
            # BA CÔNG TẮC của PHIÊN. Cùng khuôn với /api/cv/num và
            # /api/track/num: một tầng một đường.
            from ..core import prefs
            khoa, _, gia = form.get("arg", [""])[0].partition(":")
            if khoa not in prefs.PHIEN or gia not in ("0", "1"):
                return self._json({"ok": False, "note": "núm lạ"}, status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, gia)
            finally:
                conn.close()
            journal.log.ok(journal.SYSTEM,
                           f"phiên · {prefs.PHIEN[khoa][1]} -> "
                           + ("bật" if gia == "1" else "tắt"))
            return self._json({"ok": True, "reload": True})

        if path in ("/api/session/start", "/api/session/stop"):
            # PHIÊN, không phải khúc. Nút này bật cả TRẠM TRỰC: chạy một vòng
            # ngay, rồi để vòng nền lặp lại 24/7 (scheduler.phien_once).
            #
            # Bật trạm trực mà không chạy ngay là sai: người vừa bấm phải đợi
            # tới nhịp sau — có thể một tiếng — mới thấy gì xảy ra, và họ sẽ
            # tưởng nút hỏng.
            from ..core import halt
            runner = sched.current()
            if path.endswith("/stop"):
                runner.pause()
                for khuc in STAGES:
                    halt.ask(khuc)
                return self._json({"ok": True, "reload": True,
                                   "note": "đã tắt trạm trực"})
            for khuc in STAGES:
                halt.clear(khuc)
            runner.resume()
            threading.Thread(target=runner.phien_once, daemon=True,
                             name="phien").start()
            return self._json({"ok": True, "reload": True,
                               "note": "phiên đang chạy…"})

        if path == "/api/track/num":
            # MỌI NÚM CỦA TẦNG QUẢN LÍ, MỘT ĐƯỜNG — như /api/cv/num bên CV.
            # Ba công tắc nguồn và mốc im lặng đều là "đổi một quyết định của
            # tầng này"; đẻ hai route cho cùng một việc là đẻ hai chỗ có thể
            # lệch nhau.
            #
            # Khác hẳn /api/source bên Search: bên đó bật/tắt việc QUÉT, đây
            # bật/tắt việc NỘP. Hai câu hỏi, hai đường.
            from ..core import prefs
            khoa, _, gia = form.get("arg", [""])[0].partition(":")
            if khoa in prefs.NOP and gia in ("0", "1"):
                ghi = (f"nộp từ {prefs.NOP[khoa][0]} -> "
                       + ("bật" if gia == "1" else "tắt"))
            elif khoa == "im_qua" and gia in prefs.IM_MUC:
                khoa, ghi = prefs.IM_QUA, f"coi như trượt sau {gia} ngày im"
            else:
                return self._json({"ok": False, "note": "núm lạ"}, status=400)
            conn = db.connect()
            try:
                prefs.put(conn, khoa, gia)
            finally:
                conn.close()
            journal.log.ok(journal.SEARCH, ghi)
            return self._json({"ok": True, "reload": True})

        if path == "/api/track/xoa":
            # XOÁ BẢNG — chỉ mấy dòng DỰNG TỪ THƯ. Đơn người dùng tự nộp qua
            # app là việc họ đã làm, quét lại không dựng lại được.
            if form.get("arg", [""])[0].strip() != "xoa":
                return self._json({"ok": False, "note": "cần xác nhận"},
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
                           f"đã xoá {n} lần nộp dựng từ thư — bấm Quét thư "
                           f"để dựng lại")
            return self._json({"ok": True, "reload": True,
                               "note": f"đã xoá {n} dòng"})

        if path == "/api/track/mail/gan":
            # GÁN một lá thư vào đúng lần nộp. Nửa còn thiếu của "không lá nào
            # biến mất": máy đọc được kết cục mà không đoán ra công ty thì
            # người dùng chỉ tay, chứ không phải chỉ được Bỏ qua.
            ma, _, app = form.get("arg", [""])[0].partition(":")
            conn = db.connect()
            try:
                from ..track import scan as tscan
                xong = (ma.isdigit() and app.isdigit()
                        and tscan.gan(conn, int(ma), int(app)))
            finally:
                conn.close()
            if not xong:
                return self._json({"ok": False, "note": "không gán được"},
                                  status=400)
            live.quen()
            return self._json({"ok": True, "reload": True})

        if path == "/api/track/mail/ignore":
            # BỎ QUA một lá máy không hiểu: nó không thuộc lần nộp nào thật,
            # hoặc chỉ là thư quảng cáo. Không xoá thư — chỉ thôi hỏi.
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
            # NGƯỜI DÙNG TỰ XẾP một lá thư máy không hiểu. Đây là nửa còn lại
            # của lời hứa "không lá nào biến mất": máy chỉ ra chỗ nó bó tay,
            # người dùng quyết, và trạng thái đổi ngay.
            ma, _, loai = form.get("arg", [""])[0].partition(":")
            conn = db.connect()
            try:
                from ..track import scan as tscan
                xong = ma.isdigit() and tscan.xep(conn, int(ma), loai)
            finally:
                conn.close()
            if not xong:
                return self._json({"ok": False, "note": "không xếp được"},
                                  status=400)
            live.quen()
            return self._json({"ok": True, "reload": True})

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
            # Bộ lọc "16 chữ cái thường" LÀ CỦA GOOGLE. Áp cho mọi nhà cung
            # cấp thì người dùng Outlook/iCloud/hộp thư công ty bị chặn ngay
            # cửa, bằng một câu chẳng liên quan gì tới lý do thật.
            if (secret and tmail._la_google(tmail.may_chu(address))
                    and not tmail.APP_PASSWORD.fullmatch(secret)):
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
            # CHỈ GHI. Màn đọc là /cv/soan; đường này không còn trả trang nào.
            # Ghi thẳng vào cv_text — MỘT nguồn sự thật. write_block chỉ đụng
            # đúng khối đó, các khối khác giữ nguyên định dạng (có test khứ hồi
            # trong test_cv.py, vì đây là chỗ dễ nuốt mất khối nhất).
            conn = db.connect()
            try:
                from ..cv.blocks import write_block
                title = form.get("title", [""])[0].strip()
                was = form.get("was", [""])[0].strip()
                ky = form.get("ky", [""])[0].strip()[:40]
                nen = form.get("nen", [""])[0].strip()[:400]
                body = [l.strip() for l in form.get("line", []) if l.strip()]
                if form.get("kill"):
                    body = []                      # thân rỗng = xoá khối
                # HAI LỐI GHI, MỘT ĐƯỜNG. Màn SỬA KHỐI gửi cả thân khối; màn
                # VIẾT MỘT CÂU chỉ gửi đúng câu mới, kèm `them=1` — nó không
                # thấy mấy câu cũ nên không được phép thay chúng. Cả hai cùng
                # đi qua `write_block`, cùng chốt chặn, cùng phép đo.
                if form.get("them") and title and body:
                    from ..cv.blocks import parse as parse_cv, sentences
                    cu = next((b for b in parse_cv(
                        store.load(conn).get("cv_text") or "")
                        if b.title == title), None)
                    if cu is not None:
                        body = [x.strip() for x in sentences(cu) if x.strip()] + body
                        form.setdefault("kind", [cu.kind])
                        form.setdefault("meta", [cu.meta])
                # CHỐT CHẶN CỦA CẢ CƠ CHẾ GỢI Ý. Nền bản nháp là chữ nguyên văn
                # của nhà tuyển dụng; để nguyên nó rồi Lưu là hai cái hại cùng
                # lúc — người sàng CV đọc ra chữ trong tin tuyển của chính mình,
                # và người dùng phải đỡ một khẳng định họ chưa từng đưa ra.
                # Không cho lưu, nhưng GIỮ NGUYÊN chữ họ vừa gõ để sửa tiếp.
                if nen and not form.get("kill"):
                    from ..scoring.gap import CHO_TRONG, con_trong, qua_giong
                    xau = vi_sao = ""
                    for l in body:
                        if con_trong(l):
                            xau, vi_sao = l, (
                                f"Câu còn chỗ trống «{CHO_TRONG}» máy chừa lại. "
                                f"Đó là chỗ của BẰNG CHỨNG, và chỉ bạn mới có: "
                                f"bao nhiêu cái, trên bao nhiêu dữ liệu, đổi "
                                f"được mấy phần. Điền vào rồi Lưu lại.")
                            break
                        if qua_giong(l, nen) >= 0.6:
                            xau, vi_sao = l, (
                                "Câu này vẫn gần như nguyên văn dòng của nhà "
                                "tuyển dụng — chưa phải việc BẠN làm. Kể việc "
                                "thật của bạn, kèm con số: bao nhiêu cái, trên "
                                "bao nhiêu dữ liệu, đổi được mấy phần.")
                            break
                    if xau:
                        # MỐC SO SÁNH (`nen`) giữ nguyên là dòng gốc của họ;
                        # chữ người dùng gõ dở đi riêng ở `soan`. Trộn hai thứ
                        # thì mỗi lần bị chặn là mốc trôi theo bản sửa, và lần
                        # sau chép nguyên văn cũng lọt.
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
                    # ĐO TRƯỚC KHI GHI. "Hồ sơ đáp trọn 129 -> 141 tin" là số
                    # thật đo hai lần, không phải lời hứa — và nó là câu trả
                    # lời duy nhất cho "viết câu này có đáng không".
                    truoc = _dap_tron(conn, answers)
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
                    live.quen()
                    _tu_dung(conn)
                    sau = _dap_tron(conn, store.load(conn))
                    viec = (f"{len(body)} câu" if body else "đã xoá")
                    # IN ĐỘ PHỦ CẢ KHI KHÔNG ĐỔI. "Viết xong mà không mở khoá
                    # thêm tin nào" chính là thứ người viết cần biết ngay —
                    # im lặng ở đúng chỗ đó là để họ tưởng câu vừa viết có ăn.
                    doi = (f" — hồ sơ đáp trọn {truoc} -> {sau} tin"
                           if sau != truoc else
                           f" — hồ sơ vẫn đáp trọn {sau} tin")
                    # LUỒNG `CV`, không phải `SCORE`. Ô nhật ký trên chính màn
                    # soạn lọc theo stream="cv"; ghi sang luồng khác thì dòng
                    # báo "đáp trọn 129 -> 141 tin" rơi vào chỗ người vừa bấm
                    # Lưu không nhìn thấy — tức là đo mà không ai đọc.
                    journal.log.ok(journal.CV,
                                   f"khối «{title[:40]}» — {viec}{doi}")
            finally:
                conn.close()
            # VỀ ĐÚNG CHỖ VỪA ĐỨNG. Lưu xong mà bị hất sang danh sách bản CV
            # thì sửa ba khối là ba lần đi tìm lại khối thứ tư — và dải chấm
            # vừa tính lại cho câu vừa sửa không ai nhìn thấy. Giữ cả `ky`:
            # brief đang mở phải còn đó, vì người ta thường viết hai câu về
            # cùng một chỗ hụt.
            if form.get("kill") or not title:
                return self._redirect("/cv/soan")
            # Lưu XONG thì bỏ nền đi: chữ của nhà tuyển dụng đã xong việc của
            # nó, giữ lại là mời người dùng lưu nhầm nó lần nữa.
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
    """Dựng server. `port=0` -> để HỆ ĐIỀU HÀNH cấp một cổng trống.

    Địa chỉ trả về đọc NGƯỢC từ socket đã bind, không dựng từ con số truyền
    vào: với port=0 thì con số truyền vào là 0, mà 0 không phải cổng nào cả.

    Vì sao có port=0: `find_port()` hỏi "cổng này có ai nghe không" rồi mới
    bind — giữa hai bước đó có khe. Hai tiến trình cùng chạy (hai lượt test
    chồng nhau) cùng thấy trống, cùng bind, và một cái chết với "Address
    already in use". Để hệ cấp thì không có khe nào để đua.
    """
    httpd = ThreadingHTTPServer((HOST, find_port() if port is None else port),
                                Handler)
    return httpd, f"http://{HOST}:{httpd.server_address[1]}/"


def _state_payload() -> dict:
    """Trạng thái THẬT của vòng chạy, không phải chuỗi cứng.

    live.run_status() cũ trả 'idle' kể cả lúc đang quét, vì nó chỉ nhìn bảng
    source_run chứ không hỏi scheduler. Đây là chỗ duy nhất biết sự thật.
    """
    runner = sched.current()
    return {"state": runner.state(),
            "next_in": runner.next_in() // 60,      # phút
            "running": journal.log.running()}
