"""Vòng chạy nền — cái làm cho nó thành APP thay vì trang web phải tự bấm.

Nhịp (design.md §3):
  - Nguồn có API công khai: chạy 24/7, không có lý do gì phải nhịn.
  - Nguồn qua Chrome: chỉ trong cửa sổ giờ người. Không ai lướt web 3 giờ sáng
    mỗi đêm — chính nhịp đó tố cáo, chứ không phải tốc độ click.

Mọi vòng chạy đều ghi audit. Hỏng một nguồn không được làm chết cả vòng.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

from . import notify, postings
from . import prefs
from .journal import SEARCH, SYSTEM, log as jlog
from .db import connect

# Mặc định. Người dùng đổi được ở menu Cài đặt; hai hằng số này chỉ còn là
# giá trị khởi điểm khi bảng pref chưa có gì.
SCAN_EVERY_MIN = 60
HUMAN_WINDOW = (8, 22)          # giờ địa phương, cho nguồn qua Chrome

MIN_EVERY, MAX_EVERY = 5, 1440  # 5 phút tới 24 giờ


def _pref(key: str, low: int, high: int) -> int:
    """Đọc LÚC CHẠY, không phải lúc nạp module.

    Import theo giá trị thì con số đóng băng: đổi 60 -> 15 phút phải khởi động
    lại app mới ăn. Đọc hỏng thì trả mặc định — người dùng gõ gì vào ô cũng
    không được làm chết vòng quét nền.
    """
    try:
        conn = connect()
        try:
            return prefs.num(conn, key, low, high)
        finally:
            conn.close()
    except Exception:                       # noqa: BLE001
        return int(prefs.DEFAULTS.get(key, low))


def scan_every_min() -> int:
    return _pref(prefs.SCAN_EVERY, MIN_EVERY, MAX_EVERY)


def human_window() -> tuple[int, int]:
    return (_pref(prefs.HOURS_FROM, 0, 23), _pref(prefs.HOURS_TO, 1, 24))


def in_human_window(now: datetime | None = None) -> bool:
    """Giờ này có nằm trong khung được phép quét không.

    Khung QUA ĐÊM là khung hợp lệ: 22:00–08:00 nghĩa là quét ban đêm, đúng lúc
    máy rảnh. Công thức cũ `low <= hour < high` cho ra RỖNG với khung đó — vòng
    quét im lặng không chạy giờ nào, và không có cảnh báo nào cả.

    low == high thì coi là CẢ NGÀY: người đặt hai đầu bằng nhau có ý "lúc nào
    cũng được", không phải "không bao giờ".
    """
    hour = (now or datetime.now()).hour
    low, high = human_window()
    if low == high:
        return True
    if low < high:
        return low <= hour < high
    return hour >= low or hour < high


class Scheduler:
    """Chạy trong luồng nền. Không bao giờ ném lỗi ra ngoài — app phải sống tiếp."""

    def __init__(self, scan_every_min: int = SCAN_EVERY_MIN):
        self.scan_every = scan_every_min * 60
        self.stop_flag = threading.Event()
        self.last_scan: float = 0.0
        self.last_result: str = "chưa chạy lần nào"
        # `running` KHÔNG lưu riêng — nó là khoá đang bị giữ hay không. Giữ
        # cả cờ lẫn khoá là hai nguồn sự thật, và chúng sẽ lệch nhau.
        self._gate = threading.Lock()
        # Mặc định DỪNG. Mở app lên mà nó tự đi quét trong lúc người dùng còn
        # đang cấu hình là sai — cấu hình chưa xong thì quét về cũng là rác.
        # Đọc lại lựa chọn lần trước, chưa có thì tắt.
        self.paused = True
        self._thread: threading.Thread | None = None

    # --- điều khiển -------------------------------------------------------
    def start(self) -> None:
        self.paused = not self._autorun()
        # Mốc đếm bắt đầu TỪ LÚC MỞ APP, không phải từ 0. Để 0 thì
        # "now - 0 >= 3600" luôn đúng và vòng quét nổ ngay sau 5 giây —
        # Chrome bật lên trong khi cửa sổ còn chưa vẽ xong.
        self.last_scan = time.time()
        jlog.emit(SYSTEM,
                  "app mở — trạm trực đang TẮT, bấm Start session trên tab Tổng quan"
                  if self.paused else
                  f"app mở — trạm trực ĐANG BẬT, vòng đầu sau {self.scan_every // 60} phút")
        self._thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self._thread.start()

    @staticmethod
    def _autorun() -> bool:
        try:
            conn = connect()
            try:
                return prefs.flag(conn, prefs.AUTORUN)
            finally:
                conn.close()
        except Exception:                       # noqa: BLE001
            return False                        # đọc hỏng -> KHÔNG tự chạy

    def stop(self) -> None:
        self.stop_flag.set()

    def pause(self) -> None:
        """Ngưng quét tự động, và NHỚ lựa chọn đó cho lần mở app sau.

        KHÁC stop(): luồng vẫn sống, bấm tiếp là chạy lại.
        Không cắt ngang lần quét đang chạy dở — cắt giữa chừng thì Chrome
        treo tab và giao dịch trong derive() cuộn lại nửa vời.
        """
        self.paused = True
        self._remember(False)
        jlog.warn(SYSTEM, "TRẠM TRỰC ĐÃ TẮT — không tự chạy vòng nào nữa")

    def resume(self) -> None:
        self.paused = False
        self._remember(True)
        jlog.ok(SYSTEM, f"trạm trực ĐÃ BẬT — vòng sau trong {self.next_in() // 60} phút")

    @staticmethod
    def _remember(on: bool) -> None:
        """Nhớ lựa chọn. Không nhớ thì lần mở app sau lại tự chạy, đúng cái
        vừa tắt đi."""
        try:
            conn = connect()
            try:
                prefs.set_flag(conn, prefs.AUTORUN, on)
            finally:
                conn.close()
        except Exception:                       # noqa: BLE001
            pass

    def state(self) -> str:
        """Một chữ cho giao diện: đang chạy / tạm dừng / chờ."""
        if self.running:
            return "running"
        return "paused" if self.paused else "idle"

    def next_in(self) -> int:
        """Còn bao nhiêu giây tới lần quét sau."""
        if not self.last_scan:
            return 0
        return max(0, int(self.scan_every - (time.time() - self.last_scan)))

    # --- vòng lặp ---------------------------------------------------------
    def _loop(self) -> None:
        time.sleep(5)                       # để server lên trước
        while not self.stop_flag.is_set():
            # Đọc lại nhịp MỖI vòng, không phải lúc khởi tạo: đổi 60 -> 15
            # phút ở menu Cài đặt là ăn ngay, không phải mở lại app.
            self.scan_every = scan_every_min() * 60
            if not self.paused and time.time() - self.last_scan >= self.scan_every:
                self.phien_once()
            self.stop_flag.wait(30)

    @property
    def running(self) -> bool:
        """Đang quét dở? Suy từ khoá, không lưu riêng."""
        return self._gate.locked()

    def scan_once(self) -> str:
        """Một lần quét. Nuốt mọi lỗi — một nguồn chết không được giết app."""
        # Khoá, KHÔNG phải kiểm-rồi-gán. `if self.running: ... self.running =
        # True` là hai bước: bấm RUN đúng lúc lịch trình cũng kích hoạt thì cả
        # hai luồng đều thấy False và cùng đặt True — hai vòng quét cùng ghi
        # một DB và cùng mở Chrome.
        if not self._gate.acquire(blocking=False):
            jlog.warn(SYSTEM, "đang quét dở — bỏ qua yêu cầu chạy chồng")
            return self.last_result
        self.last_scan = time.time()
        try:
            from ..scan_runner import run_scan          # nạp muộn, tránh vòng import
            result = run_scan()
            self.last_result = result["summary"]
            self._maybe_notify(result)
        except Exception as exc:                        # noqa: BLE001
            self.last_result = f"lỗi: {type(exc).__name__}: {exc}"
            jlog.error(SYSTEM, f"lần quét hỏng: {type(exc).__name__} — {str(exc)[:70]}")
            try:
                conn = connect()
                postings.log(conn, "scan_error", str(exc)[:300])
                conn.close()
            except Exception:                           # noqa: BLE001
                pass
        finally:
            self._gate.release()
            jlog.done(SEARCH)
            jlog.done(SYSTEM)
        return self.last_result

    def phien_once(self) -> str:
        """MỘT PHIÊN: chạy lần lượt mọi khúc đang bật (xem jobbot/phien.py).

        Khác `scan_once` ở chỗ nó chạy CẢ dây chuyền chứ không riêng lượt
        tìm việc. Vòng 24/7 gọi hàm này, và nút «Start session» trên Home
        cũng vậy — hai lối vào, MỘT việc. Hai định nghĩa "một vòng" là có
        ngày bấm tay ra một đằng, để tự chạy ra một nẻo.

        DÙNG CHUNG KHOÁ với scan_once: hai phiên chồng nhau thì hai chỗ cùng
        ghi một file SQLite và cùng mở Chrome.
        """
        if not self._gate.acquire(blocking=False):
            jlog.warn(SYSTEM, "đang chạy dở — bỏ qua yêu cầu chạy chồng")
            return self.last_result
        self.last_scan = time.time()
        try:
            from ..phien import chay
            ra = chay()
            self.last_result = ("cả ba khúc đang tắt" if ra.get("tat") else
                                f"{len(ra['xong'])} khúc xong"
                                + (f", {len(ra['hong'])} hỏng" if ra["hong"] else ""))
        except Exception as exc:                        # noqa: BLE001
            self.last_result = f"lỗi: {type(exc).__name__}: {exc}"
            jlog.error(SYSTEM, f"phiên hỏng: {type(exc).__name__} — {str(exc)[:70]}")
        finally:
            self._gate.release()
            jlog.done(SEARCH)
            jlog.done(SYSTEM)
        return self.last_result

    @staticmethod
    def _maybe_notify(result: dict) -> None:
        """Chỉ báo khi có việc MỚI đáng xem. Không báo mỗi lần quét.

        Nuốt giá trị trả về là lý do lỗi rào chuỗi AppleScript sống sót qua
        cả quá trình: mọi thông báo đều hỏng mà không ai biết. Hỏng thì GHI
        VÀO NHẬT KÝ, để nó hiện ở màn hình Settings.
        """
        fresh = result.get("new_matches", 0)
        if fresh <= 0:
            return
        sent = notify.send("jobbot",
                           f"{fresh} việc mới khớp hồ sơ của bạn",
                           subtitle="Mở dashboard để xem")
        try:
            conn = connect()
            postings.log(conn, "notify" if sent else "notify_failed",
                         f"{fresh} việc mới" if sent
                         else f"{fresh} việc mới — thông báo KHÔNG hiện được")
            conn.close()
        except Exception:                               # noqa: BLE001
            pass


# Một bản dùng chung: app.py dựng vòng chạy, server.py cần nó cho nút RUN/PAUSE.
# Luồn qua tham số thì phải xuyên qua serve() -> Handler -> từng route, mà
# Handler thì do http.server dựng, không truyền gì vào được.
_current: Scheduler | None = None


def current() -> Scheduler:
    global _current
    if _current is None:
        _current = Scheduler()
    return _current
