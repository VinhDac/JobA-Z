"""Khởi động jobbot. Chạy được trên macOS, Windows, Linux.

    python run.py            cửa sổ app (macOS: NSWindow · còn lại: Chrome --app)
    python run.py --window   chạy trong terminal, mở trình duyệt, Ctrl+C dừng
    python run.py --scan     quét một lần rồi thoát

Trên Windows dùng `python`, trên macOS/Linux thường là `python3`. Cần Python
3.11 trở lên (tomllib).
"""

from __future__ import annotations

import sys
import threading
import webbrowser

from . import shell
from .core import db, journal
from .core import dia_chi, scheduler
from .core.paths import db_path
from .dashboard.server import serve


def run_window(app_window: bool = False) -> int:
    """Server + scheduler chạy ở tiến trình này, log ra terminal.

    app_window=True  mở cửa sổ Chrome --app (vỏ app trên Windows/Linux)
    app_window=False mở trình duyệt mặc định
    """
    ran = db.migrate(db.connect())
    journal.log.open()                      # trước dòng này nhật ký chỉ ở bộ nhớ
    httpd, url = serve()
    # Nói cho NGOÀI biết đang chạy ở đâu. Cổng do hệ cấp nên nó đổi theo
    # từng lượt; không ghi ra thì `start.command` bấm đúp sẽ gõ nhầm cửa.
    dia_chi.ghi(url)
    runner = scheduler.current()
    runner.start()

    # LUỒNG NGHE LỆNH TELEGRAM — bật ở ĐÂY, không chỉ ở đường macOS/PyObjC.
    #
    # Trước đây nó chỉ nằm trong app.py (vỏ PyObjC). Chạy bằng
    # `run.py --window`, chạy trên Windows/Linux, hay chạy khi máy thiếu
    # PyObjC thì điều khiển từ xa chết CÂM: màn hình vẫn nói mức điều khiển
    # đang bật, mà nhắn cho bot thì không ai trả lời.
    from . import bao as _bao
    threading.Thread(target=_bao.nghe, args=(runner.stop_flag,),
                     daemon=True, name="telegram").start()

    print(f"  jobbot  ->  {url}", flush=True)
    print(f"  DB      ->  {db_path()}", flush=True)
    print(f"  vỏ      ->  {shell.describe()}", flush=True)
    if ran:
        print(f"  ran {ran} migration(s)", flush=True)
    print(f"  tự quét: {'BẬT' if not runner.paused else 'TẮT'}"
          "  ·  Ctrl+C để dừng\n", flush=True)

    window = None
    if app_window:
        window = shell.open_window(url)
        if window is None:
            print("  (không mở được cửa sổ Chrome — mở trình duyệt thay)")
    if window is None:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        runner.stop()
        httpd.server_close()
        if window is not None:
            window.terminate()
        from .browser import chrome
        chrome.shutdown_all()               # đừng bỏ lại cửa sổ cào mồ côi
        dia_chi.xoa()
    return 0


def main() -> int:
    db.migrate(db.connect())

    if "--scan" in sys.argv:
        from .scan_runner import run_scan
        result = run_scan(log=print)
        print(f"\n  {result['summary']}\n")
        return 0 if result["ok"] else 1

    if "--window" in sys.argv:
        return run_window()

    # macOS có PyObjC -> cửa sổ thật. Windows/Linux -> cửa sổ Chrome --app.
    if shell.has_mac_native():
        try:
            from .app import run
            return run()
        except (ImportError, AttributeError) as exc:
            print(f"  (không dựng được cửa sổ macOS: {exc})")
    return run_window(app_window=True)


if __name__ == "__main__":
    sys.exit(main())
