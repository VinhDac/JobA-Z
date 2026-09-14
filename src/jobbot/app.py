"""App macOS thật — cửa sổ riêng, icon Dock, cmd-tab được.

Giống hệt cách Discord/Slack/VS Code làm: nội dung là HTML, nhưng nó nằm trong
cửa sổ native chứ không phải tab trình duyệt. Khác biệt với người dùng là toàn bộ.

    AppKit/Foundation  — PyObjC. KHÔNG có sẵn trên macOS: /usr/bin/python3
                         (3.9.6) không có objc, và bản đó cũng dưới 3.11.
                         Nó đến từ bản Python người dùng thật sự chạy bằng
                         (Anaconda ở máy này). Thiếu nó KHÔNG phải lỗi —
                         shell.has_mac_native() trả False và app lùi về cửa
                         sổ Chrome --app.
    WebKit             — nạp động bằng objc.loadBundle, không cần bindings dựng sẵn

Một tiến trình, ba phần:
    luồng chính  Cocoa event loop + cửa sổ
    luồng nền    web server (nội dung cho cửa sổ)
    luồng nền    scheduler (tự quét theo lịch)

Hành vi kiểu Discord: đóng cửa sổ thì ẨN, app vẫn chạy nền. Bấm icon Dock hoặc
icon thanh menu thì hiện lại. Chỉ Quit mới thật sự thoát.
"""

from __future__ import annotations

import threading

import objc
from AppKit import (NSApplication, NSApplicationActivationPolicyRegular,
                    NSBackingStoreBuffered, NSColor, NSMenu, NSMenuItem,
                    NSModalResponseOK, NSOpenPanel, NSStatusBar, NSWorkspace,
                    NSVariableStatusItemLength, NSViewHeightSizable, NSViewWidthSizable,
                    NSWindow, NSWindowStyleMaskClosable, NSWindowStyleMaskFullSizeContentView,
                    NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
                    NSWindowStyleMaskTitled, NSWindowTitleHidden)
from Foundation import NSMakeRect, NSObject, NSTimer, NSURL, NSURLRequest
from PyObjCTools import AppHelper

from .core import db, dia_chi, postings
from .core import journal
from .core import scheduler as scheduler_mod
from .dashboard.server import serve

# WebKit không có bindings dựng sẵn trong PyObjC của Anaconda -> nạp lúc chạy.
objc.loadBundle("WebKit", globals(),
                bundle_path="/System/Library/Frameworks/WebKit.framework")

# loadBundle chỉ nạp CLASS, không nạp chữ ký method. Hàm mở hộp thoại chọn tệp
# nhận một BLOCK ở tham số cuối; không khai chữ ký thì PyObjC không biết gọi
# block đó thế nào và `handler(...)` chết ngay — mà chết ở đây thì <input
# type=file> treo luôn, bấm mãi không mở. Chỉ số 5 = sau self, _cmd, webView,
# parameters, frame.
objc.registerMetaDataForSelector(
    b"NSObject",
    b"webView:runOpenPanelWithParameters:initiatedByFrame:completionHandler:",
    {"arguments": {5: {"callable": {
        "retval": {"type": b"v"},
        "arguments": {0: {"type": b"^v"}, 1: {"type": b"@"}}}}}},
)

WINDOW_W, WINDOW_H = 1180, 820
IDLE, BUSY = "◆", "◇"


class Delegate(NSObject):
    """Đại diện cho cả app lẫn cửa sổ. Thuộc tính gán từ ngoài vào —
    PyObjC biến mọi method thành selector nên không định nghĩa được setter thường."""

    window = None
    webview = None
    scheduler = None
    status_item = None
    url = ""

    # --- hộp thoại chọn tệp ----------------------------------------------
    # BẮT BUỘC PHẢI CÓ. WKWebView không tự mở được NSOpenPanel: thiếu hàm này
    # thì <input type=file> chết câm — bấm "Choose File" không có gì xảy ra,
    # không lỗi, không log. Trong trình duyệt thường thì cùng trang đó chạy
    # bình thường, nên lỗi này rất dễ bị đổ oan cho HTML.
    def _mo_hop_chon_tep(self, _webview, params, _frame, handler):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(bool(params.allowsMultipleSelection()))
        # Người dùng bấm Cancel -> PHẢI gọi handler(None). Không gọi thì
        # WKWebView treo ô nhập vĩnh viễn, lần sau bấm cũng không mở nữa.
        handler(panel.URLs() if panel.runModal() == NSModalResponseOK else None)

    # Chữ ký phải khai TAY. Để PyObjC tự suy thì tham số cuối thành "@" (một
    # object bình thường) thay vì "@?" (block) — lúc đó `handler(...)` gọi vào
    # hư không và ô chọn tệp treo. Đã kiểm: không có dòng này thì signature ra
    # v@:@@@@, có thì ra v@:@@@@?.
    webView_runOpenPanelWithParameters_initiatedByFrame_completionHandler_ = objc.selector(
        _mo_hop_chon_tep,
        selector=b"webView:runOpenPanelWithParameters:initiatedByFrame:completionHandler:",
        signature=b"v@:@@@@?",
    )

    # --- đường ra ngoài ---------------------------------------------------
    # Tin tuyển dụng nằm ở linkedin.com, greenhouse.io… — tức là NGOÀI app.
    # WKWebView không tự mở cửa sổ mới: thiếu hàm này thì <a target=_blank>
    # bấm vào KHÔNG có gì xảy ra, không lỗi, không log — đúng lớp lỗi mà ô
    # chọn tệp ở trên đã mắc một lần rồi.
    #
    # Và cũng đừng để nó mở NGAY TRONG cửa sổ app: cửa sổ này không có thanh
    # địa chỉ, không có nút Back. Đi sang LinkedIn là mất luôn dashboard, chỉ
    # còn cách tắt app mở lại.
    #
    # Nên: đẩy sang trình duyệt mặc định, rồi trả None để WKWebView khỏi dựng
    # webview mới.
    def _mo_ra_trinh_duyet(self, _webview, _config, action, _features):
        url = action.request().URL()
        if url is not None:
            NSWorkspace.sharedWorkspace().openURL_(url)
        return None                    # None = đừng dựng webview mới

    # Chữ ký khai TAY, y như lý do ở hộp chọn tệp. Để PyObjC tự suy thì nó
    # nhìn `return None` và kết luận hàm trả về void ("v"), trong khi WKWebView
    # gọi hàm này để LẤY VỀ một WKWebView* ("@"). Khai sai kiểu trả về thì nó
    # đọc rác ở thanh ghi trả về — lúc chạy được lúc không, và loại lỗi đó
    # không bao giờ hiện thành thông báo.
    #   @ = trả về object · @: = self, cmd · @@@@ = bốn tham số object
    webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_ = objc.selector(
        _mo_ra_trinh_duyet,
        selector=b"webView:createWebViewWithConfiguration:"
                 b"forNavigationAction:windowFeatures:",
        signature=b"@@:@@@@",
    )

    # --- vòng đời app -----------------------------------------------------
    def applicationShouldTerminateAfterLastWindowClosed_(self, _app) -> bool:
        return False                       # đóng cửa sổ != thoát app

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, has_visible) -> bool:
        if not has_visible:
            self.showWindow_(None)
        return True

    def windowShouldClose_(self, _sender) -> bool:
        self.window.orderOut_(None)        # ẩn, không đóng — app chạy tiếp
        return False

    # --- hành động --------------------------------------------------------
    def showWindow_(self, _sender) -> None:
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def reload_(self, _sender) -> None:
        self.webview.reload_(None)

    def scanNow_(self, _sender) -> None:
        threading.Thread(target=self.scheduler.scan_once, daemon=True).start()

    def goHome_(self, _sender) -> None:
        self.webview.loadRequest_(
            NSURLRequest.requestWithURL_(NSURL.URLWithString_(self.url)))

    def doQuit_(self, _sender) -> None:
        self.scheduler.stop()
        # Chrome chạy bằng profile riêng của app — thoát app mà bỏ nó lại thì
        # nó thành cửa sổ mồ côi, không ai đóng. MỌI cổng, không riêng cổng
        # quét: cửa sổ Nộp cố ý được để mở, nên chỉ có chỗ này đóng nó.
        from .browser import chrome
        chrome.shutdown_all()
        AppHelper.stopEventLoop()

    # --- nhãn trên thanh menu ---------------------------------------------
    def tick_(self, _timer) -> None:
        self.status_item.button().setTitle_(BUSY if self.scheduler.running else IDLE)
        menu = self.status_item.menu()
        menu.itemAtIndex_(0).setTitle_(self._statusLine())
        menu.itemAtIndex_(1).setTitle_(self._jobsLine())

    def _statusLine(self) -> str:
        if self.scheduler.running:
            return "Scanning now…"
        if not self.scheduler.last_scan:
            return "Waiting for first scan"
        return f"Idle · next scan in {self.scheduler.next_in() // 60} min"

    def _jobsLine(self) -> str:
        try:
            conn = db.connect()
            try:
                return f"{postings.count_groups(conn)} jobs · {postings.count(conn):,} pulled"
            finally:
                conn.close()
        except Exception:                                  # noqa: BLE001
            return "—"


def _item(title: str, selector: str | None, key: str, target=None) -> NSMenuItem:
    entry = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, key)
    if target is not None:
        entry.setTarget_(target)
    return entry


def _build_main_menu(delegate: Delegate) -> NSMenu:
    """Menu trên cùng. Thiếu menu Edit thì cmd-C/cmd-V không chạy trong WebView."""
    main = NSMenu.alloc().init()

    app_menu = NSMenu.alloc().init()
    app_menu.addItem_(_item("Hide jobbot", "hide:", "h"))
    app_menu.addItem_(NSMenuItem.separatorItem())
    app_menu.addItem_(_item("Quit jobbot", "doQuit:", "q", delegate))
    holder = NSMenuItem.alloc().init(); holder.setSubmenu_(app_menu)
    main.addItem_(holder)

    edit = NSMenu.alloc().initWithTitle_("Edit")
    for title, selector, key in (("Undo", "undo:", "z"), ("Redo", "redo:", "Z"),
                                 ("Cut", "cut:", "x"), ("Copy", "copy:", "c"),
                                 ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")):
        edit.addItem_(_item(title, selector, key))
    holder = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Edit", None, "")
    holder.setSubmenu_(edit); main.addItem_(holder)

    view = NSMenu.alloc().initWithTitle_("View")
    view.addItem_(_item("Reload", "reload:", "r", delegate))
    view.addItem_(_item("Dashboard", "goHome:", "0", delegate))
    view.addItem_(NSMenuItem.separatorItem())
    view.addItem_(_item("Scan now", "scanNow:", "s", delegate))
    holder = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("View", None, "")
    holder.setSubmenu_(view); main.addItem_(holder)
    return main


def _build_status_item(delegate: Delegate):
    item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    item.button().setTitle_(IDLE)
    menu = NSMenu.alloc().init()
    menu.addItem_(_item("Starting…", None, ""))
    menu.addItem_(_item("—", None, ""))
    menu.addItem_(NSMenuItem.separatorItem())
    menu.addItem_(_item("Open jobbot", "showWindow:", "", delegate))
    menu.addItem_(_item("Scan now", "scanNow:", "", delegate))
    menu.addItem_(NSMenuItem.separatorItem())
    menu.addItem_(_item("Quit jobbot", "doQuit:", "", delegate))
    item.setMenu_(menu)
    return item


def run() -> int:
    httpd, url = serve()
    dia_chi.ghi(url)        # xem core/dia_chi.py — cổng không còn cố định
    threading.Thread(target=httpd.serve_forever, daemon=True, name="web").start()

    # Gắn nhật ký vào DB thật — trước dòng này nó chỉ sống trong bộ nhớ.
    journal.log.open()
    scheduler = scheduler_mod.current()
    scheduler.start()

    # LUỒNG NGHE LỆNH TELEGRAM — riêng một luồng, không dùng chung với
    # scheduler: mỗi lượt long-poll ngủ 25 giây, mà vòng quét thì không được
    # ngủ theo. Tự thoát ngay nếu chưa nối bot hoặc mức điều khiển đang TẮT.
    from . import bao as _bao
    threading.Thread(target=_bao.nghe, args=(scheduler.stop_flag,),
                     daemon=True, name="telegram").start()

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)   # có icon Dock, cmd-tab

    delegate = Delegate.alloc().init()

    rect = NSMakeRect(0, 0, WINDOW_W, WINDOW_H)
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect,
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        | NSWindowStyleMaskFullSizeContentView,      # nội dung chạy lên dưới thanh tiêu đề
        NSBackingStoreBuffered, False)
    window.setTitle_("jobbot")
    # Thanh tiêu đề trong suốt + ẩn chữ -> sidebar chạy lên tận đỉnh, chỉ còn
    # ba nút traffic light nổi trên nền đen. CSS chừa sẵn 38px ở trên.
    window.setTitlebarAppearsTransparent_(True)
    window.setTitleVisibility_(NSWindowTitleHidden)
    # khớp với --side trong app.css (#1A1A1A) — nền KHUNG app, không phải nền
    # vùng làm việc. Sai màu ở đây thì lúc mở cửa sổ nháy một cái khác tông.
    window.setBackgroundColor_(
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.102, 0.102, 0.102, 1.0))
    window.setMinSize_(NSMakeRect(0, 0, 760, 540).size)
    window.center()
    window.setDelegate_(delegate)

    config = WKWebViewConfiguration.alloc().init()                   # noqa: F821
    webview = WKWebView.alloc().initWithFrame_configuration_(rect, config)   # noqa: F821
    webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
    webview.setValue_forKey_(False, "drawsBackground")   # nền webview trong suốt -> đen
    webview.setUIDelegate_(delegate)     # không có dòng này thì <input type=file> chết câm
    window.contentView().addSubview_(webview)
    webview.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))

    delegate.window, delegate.webview = window, webview
    delegate.scheduler, delegate.url = scheduler, url
    delegate.status_item = _build_status_item(delegate)

    app.setMainMenu_(_build_main_menu(delegate))
    app.setDelegate_(delegate)

    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)

    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        2.0, delegate, "tick:", None, True)

    print(f"  jobbot — cửa sổ app · nội dung từ {url}", flush=True)
    AppHelper.runEventLoop()
    httpd.server_close()
    dia_chi.xoa()
    return 0
