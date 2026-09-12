"""Nhật ký chạy — thứ quan trọng nhất trong một app chạy 24/7.

Máy chạy suốt còn người thì không ngồi nhìn. Nên lúc mở app ra, câu hỏi đầu
tiên luôn là "nó VỪA làm gì, và ĐANG làm gì". Không trả lời được câu đó thì
mọi con số khác trên màn hình đều là số chết.

Hai thứ KHÁC NHAU, đừng trộn:

    SỰ KIỆN   ghi thêm, không bao giờ sửa. "linkedin bị chặn ở tin 47".
              Còn lại sau khi tắt app -> lưu xuống SQLite.

    TIẾN ĐỘ   ghi đè, chỉ có giá trị lúc này. "đọc kỹ 47/192".
              Tắt app là hết nghĩa -> CHỈ giữ trong bộ nhớ, không ghi đĩa.
              Ghi 192 dòng tiến độ xuống đĩa mỗi lần quét là tự bóp mình.

Mỗi sự kiện thuộc về một LUỒNG (stream). Nhờ nó mà tab Search chỉ hiện việc
của Search, không lẫn việc của Score — mà Home vẫn gộp được tất cả.
"""

from __future__ import annotations

import queue
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .paths import db_path

# Luồng = một hệ con có thời gian chạy thật. Thêm luồng thì thêm vào đây,
# đừng gõ chuỗi tự do ở chỗ gọi — sai một chữ là mất hút trong giao diện.
SYSTEM = "system"
SEARCH = "search"
SCORE = "score"
STREAMS = (SYSTEM, SEARCH, SCORE)

INFO, OK, WARN, ERROR = "info", "ok", "warn", "error"

RING = 400              # số dòng giữ trong bộ nhớ để vẽ ngay, không phải hỏi đĩa
LOAD_ON_START = 120     # nạp lại bấy nhiêu dòng cũ khi mở app, để journal không trống


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Event:
    at: str
    stream: str
    level: str
    text: str

    def as_dict(self) -> dict:
        return asdict(self)


def remain_text(seconds: int) -> str:
    """Giây -> câu người đọc được. MỘT chỗ định dạng cho cả app.

    Dòng nhật ký viết bằng Python, thanh tiến độ vẽ bằng JavaScript. Để mỗi
    bên tự định dạng thì cùng một con số hiện ra hai kiểu chữ khác nhau trên
    cùng một màn hình — nên chỗ này tính sẵn thành chữ rồi đẩy xuống.

    Luôn kèm dấu ~: đây là ước lượng theo nhịp hiện tại, không phải lời hứa.
    """
    if seconds <= 0:
        return ""
    if seconds < 90:
        return f"~{seconds} giây"
    phut = round(seconds / 60)
    if phut < 60:
        return f"~{phut} phút"
    gio, le = divmod(phut, 60)
    return f"~{gio} giờ {le} phút" if le else f"~{gio} giờ"


@dataclass
class Progress:
    """Đang làm gì, tới đâu, còn bao lâu nữa xong."""
    what: str
    done: int = 0
    total: int = 0
    started: float = 0.0

    @property
    def percent(self) -> int:
        return int(self.done * 100 / self.total) if self.total else 0

    @property
    def eta(self) -> int:
        """Còn bao nhiêu GIÂY nữa xong. Chưa đoán được thì 0.

        Đo bằng nhịp THẬT của vòng đang chạy, không dùng hằng số đoán sẵn:
        vòng đọc kỹ LinkedIn nhanh chậm theo mạng, theo nhịp nghỉ, và theo
        số tin đã đọc từ trước — một con số cứng trong mã nguồn sai ngay
        hôm sau.

        Chờ đủ 3 nhịp mới dám nói. Nhịp đầu còn lẫn thời gian mở Chrome và
        mở trang; chia ra thì phút đầu báo "còn 9 tiếng" rồi tụt dần, mà một
        con số nhảy loạn còn tệ hơn không có con số nào.
        """
        if not self.total or self.done < 3 or not self.started:
            return 0
        troi = _monotonic() - self.started
        return max(0, int(troi / self.done * (self.total - self.done)))

    def as_dict(self) -> dict:
        out = asdict(self)
        out["percent"] = self.percent
        out["eta"] = self.eta
        out["eta_text"] = remain_text(self.eta)
        return out


class Journal:
    """Một bản duy nhất cho cả tiến trình. Nhiều luồng cùng ghi nên có khoá."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ring: list[Event] = []
        self._progress: dict[str, Progress] = {}
        self._subs: list[queue.Queue] = []
        self._conn: sqlite3.Connection | None = None
        self._path = None          # None = CHƯA gắn vào file nào -> chỉ ghi bộ nhớ
        self._loaded = False

    # --- lưu xuống đĩa ----------------------------------------------------
    def _db(self) -> sqlite3.Connection | None:
        """Kết nối riêng của nhật ký, mở một lần rồi giữ.

        Chưa open() thì trả None -> chỉ ghi bộ nhớ, không đụng file nào.

        check_same_thread=False vì luồng nền ghi còn luồng web đọc. An toàn
        vì mọi lối vào đều đi qua self._lock.
        """
        if self._path is None:
            return None
        if self._conn is None:
            try:
                self._conn = sqlite3.connect(self._path, check_same_thread=False)
                self._conn.execute("PRAGMA busy_timeout = 3000")
            except Exception:                   # noqa: BLE001
                return None
        return self._conn

    def _persist(self, event: Event) -> None:
        conn = self._db()
        if conn is None:
            return
        try:
            conn.execute(
                "INSERT INTO audit (at, kind, detail, stream, level) VALUES (?,?,?,?,?)",
                (event.at, event.text[:60], event.text, event.stream, event.level))
            conn.commit()
        except Exception:       # noqa: BLE001
            # Bắt RỘNG là cố ý. Nhật ký mất một dòng là chuyện nhỏ; nhật ký
            # ném lỗi ra và giết vòng quét đang chạy dở mới là hỏng thật.
            # sqlite3.Error thôi thì chưa đủ: đĩa đầy, kết nối chết, DB bị
            # khoá quá lâu đều ra lỗi kiểu khác.
            pass

    def open(self, path=None) -> int:
        """Gắn nhật ký vào một file DB và nạp lại lịch sử. Gọi một lần lúc mở app.

        CHƯA gọi thì nhật ký chỉ sống trong bộ nhớ. Cố ý: nếu mặc định là ghi
        thẳng vào db_path(), thì mọi bài test gọi derive() đều đổ dòng của nó
        vào nhật ký THẬT của người dùng — đã xảy ra, 24 dòng "đang giữ 1 tin".
        Bắt từng file test phải nhớ đặt biến môi trường là cách chờ hỏng lần
        sau; để mặc định câm thì không ai phải nhớ gì.
        """
        with self._lock:
            if self._loaded:
                return 0
            self._loaded = True
            self._path = str(path or db_path())
            conn = self._db()
            if conn is None:
                return 0
            try:
                rows = conn.execute(
                    "SELECT at, stream, level, detail, kind FROM audit"
                    " ORDER BY id DESC LIMIT ?", (LOAD_ON_START,)).fetchall()
            except Exception:                   # noqa: BLE001
                return 0
            # detail rỗng thì lấy kind: dòng ghi bằng postings.log() đời trước
            # chỉ có kind ('scan_started'), và hiện ra sẽ là một dòng trống trơn.
            self._ring = [Event(at=r[0], stream=r[1] or SYSTEM,
                                level=r[2] or INFO,
                                text=r[3] or (r[4] or "").replace("_", " "))
                          for r in reversed(rows)]
            return len(self._ring)

    # --- ghi ---------------------------------------------------------------
    def emit(self, stream: str, text: str, level: str = INFO,
             persist: bool = True) -> Event:
        event = Event(at=_now(), stream=stream, level=level, text=text)
        with self._lock:
            self._ring.append(event)
            if len(self._ring) > RING:
                del self._ring[:-RING]
            subs = list(self._subs)
        if persist:
            self._persist(event)
        self._push(subs, {"type": "event", **event.as_dict()})
        return event

    def ok(self, stream: str, text: str) -> Event:
        return self.emit(stream, text, OK)

    def warn(self, stream: str, text: str) -> Event:
        return self.emit(stream, text, WARN)

    def error(self, stream: str, text: str) -> Event:
        return self.emit(stream, text, ERROR)

    def progress(self, stream: str, what: str, done: int = 0, total: int = 0) -> None:
        """Đang làm tới đâu. KHÔNG ghi đĩa — gọi bao nhiêu lần cũng được."""
        with self._lock:
            found = self._progress.get(stream)
            # Mốc thời gian đặt lại khi sang VIỆC KHÁC — nhận ra bằng TỔNG đổi
            # hoặc số đếm tụt về, KHÔNG bằng dòng chữ đổi. Vòng tìm LinkedIn
            # viết tên chức danh đang tìm vào `what`, nên mỗi nhịp là một chữ
            # khác nhau; lấy chữ làm mốc thì đồng hồ reset mỗi nhịp và câu
            # "còn bao lâu" không bao giờ tính ra được.
            if found is None or found.total != total or done < found.done:
                found = Progress(what=what, started=_monotonic())
                self._progress[stream] = found
            found.what, found.done, found.total = what, done, total
            payload = {"type": "progress", "stream": stream, **found.as_dict()}
            subs = list(self._subs)
        self._push(subs, payload)

    def done(self, stream: str) -> None:
        """Xong việc — xoá thanh tiến độ, để giao diện không đứng hình ở 47/192."""
        with self._lock:
            self._progress.pop(stream, None)
            subs = list(self._subs)
        self._push(subs, {"type": "progress", "stream": stream, "what": ""})

    # --- đọc ---------------------------------------------------------------
    def tail(self, stream: str | None = None, limit: int = 60) -> list[Event]:
        with self._lock:
            rows = [e for e in self._ring if stream is None or e.stream == stream]
        return rows[-limit:][::-1]          # mới nhất lên đầu

    def running(self) -> dict[str, dict]:
        with self._lock:
            return {k: v.as_dict() for k, v in self._progress.items()}

    def remaining(self, stream: str) -> str:
        """Còn bao lâu nữa xong, đã thành chữ. Không đoán được thì rỗng.

        Để dòng NHẬT KÝ nói đúng cùng con số với THANH TIẾN ĐỘ. Hai chỗ tự
        tính là hai con số, và có ngày chúng lệch nhau ngay trên một màn hình.
        """
        with self._lock:
            found = self._progress.get(stream)
        return remain_text(found.eta) if found else ""

    def busy(self) -> bool:
        with self._lock:
            return bool(self._progress)

    # --- đẩy cho giao diện -------------------------------------------------
    def subscribe(self) -> queue.Queue:
        chan: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._subs.append(chan)
        return chan

    def unsubscribe(self, chan: queue.Queue) -> None:
        with self._lock:
            if chan in self._subs:
                self._subs.remove(chan)

    @staticmethod
    def _push(subs: list[queue.Queue], payload: dict) -> None:
        """Người xem chậm thì BỎ tin, không được chặn việc đang chạy.

        Giao diện đứng hình một nhịp là chuyện nhỏ; vòng quét đứng lại vì
        chờ một cái hàng đợi đầy mới là hỏng thật.
        """
        for chan in subs:
            try:
                chan.put_nowait(payload)
            except queue.Full:
                pass


def _monotonic() -> float:
    import time
    return time.monotonic()


# Một bản dùng chung cho cả tiến trình.
log = Journal()
