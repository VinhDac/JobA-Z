"""Start jobbot. Runs on macOS, Windows, Linux.

    python run.py            app window (macOS: NSWindow · else: Chrome --app)
    python run.py --window   run in the terminal, open a browser, Ctrl+C stops
    python run.py --scan     scan once, then exit

On Windows use `python`, on macOS/Linux usually `python3`. Needs Python 3.11
or newer (tomllib).
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
    """Server + scheduler run in this process, logging to the terminal.

    app_window=True  open a Chrome --app window (the app shell on Windows/Linux)
    app_window=False open the default browser
    """
    ran = db.migrate(db.connect())
    journal.log.open()                      # before this line the journal is memory-only
    httpd, url = serve()
    # Tell the OUTSIDE where we are listening. The OS hands out the port, so
    # it changes every run; without this file a double-click on start.command
    # knocks on the wrong door.
    dia_chi.ghi(url)
    runner = scheduler.current()
    runner.start()

    # THE TELEGRAM COMMAND LISTENER — started HERE, not only on the
    # macOS/PyObjC path.
    #
    # It used to live only in app.py (the PyObjC shell). Run with
    # `run.py --window`, run on Windows/Linux, or run on a machine without
    # PyObjC, and remote control died SILENTLY: the screen still said which
    # control level was on, but messaging the bot got no answer.
    from . import bao as _bao
    threading.Thread(target=_bao.nghe, args=(runner.stop_flag,),
                     daemon=True, name="telegram").start()

    print(f"  jobbot  ->  {url}", flush=True)
    print(f"  DB      ->  {db_path()}", flush=True)
    print(f"  shell   ->  {shell.describe()}", flush=True)
    if ran:
        print(f"  ran {ran} migration(s)", flush=True)
    print(f"  auto-scan: {'ON' if not runner.paused else 'OFF'}"
          "  ·  Ctrl+C to stop\n", flush=True)

    window = None
    if app_window:
        window = shell.open_window(url)
        if window is None:
            print("  (could not open a Chrome window — opening your browser instead)")
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
        chrome.shutdown_all()               # never leave an orphaned scraping window
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

    # macOS with PyObjC -> a real window. Windows/Linux -> a Chrome --app window.
    if shell.has_mac_native():
        try:
            from .app import run
            return run()
        except (ImportError, AttributeError) as exc:
            print(f"  (could not build the macOS window: {exc})")
    return run_window(app_window=True)


if __name__ == "__main__":
    sys.exit(main())
