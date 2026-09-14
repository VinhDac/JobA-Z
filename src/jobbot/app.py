"""A real macOS app — its own window, a Dock icon, cmd-tab.

Exactly how Discord/Slack/VS Code do it: the content is HTML, but it lives in
a native window rather than a browser tab. For the user the difference is
everything.

    AppKit/Foundation  — PyObjC. NOT preinstalled on macOS: /usr/bin/python3
                         (3.9.6) has no objc, and that build is also below
                         3.11. It comes from whichever Python the user
                         actually runs (Anaconda on this machine). Its
                         absence is NOT an error — shell.has_mac_native()
                         returns False and the app falls back to a Chrome
                         --app window.
    WebKit             — loaded at runtime with objc.loadBundle, no prebuilt
                         bindings needed

One process, three parts:
    main thread        Cocoa event loop + the window
    background thread  the web server (the window's content)
    background thread  the scheduler (scanning on a schedule)

Discord-style behaviour: closing the window HIDES it, the app keeps running.
Click the Dock icon or the menu-bar icon and it comes back. Only Quit really
exits.
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

# WebKit has no prebuilt bindings in Anaconda's PyObjC -> load it at runtime.
objc.loadBundle("WebKit", globals(),
                bundle_path="/System/Library/Frameworks/WebKit.framework")

# loadBundle loads CLASSES only, not method signatures. The file-picker
# callback takes a BLOCK as its last argument; without a declared signature
# PyObjC does not know how to call that block and `handler(...)` dies on the
# spot — and dying here means <input type=file> hangs forever, clicking it
# does nothing. Index 5 = after self, _cmd, webView, parameters, frame.
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
    """Stands in for both the app and the window. Attributes are assigned
    from outside — PyObjC turns every method into a selector, so an ordinary
    setter cannot be defined."""

    window = None
    webview = None
    scheduler = None
    status_item = None
    url = ""

    # --- the file picker --------------------------------------------------
    # THIS IS MANDATORY. WKWebView cannot open an NSOpenPanel by itself:
    # without this method <input type=file> dies silently — clicking "Choose
    # File" does nothing, no error, no log. In an ordinary browser that same
    # page works fine, so this bug is very easy to blame on the HTML.
    def _mo_hop_chon_tep(self, _webview, params, _frame, handler):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(bool(params.allowsMultipleSelection()))
        # The user pressed Cancel -> handler(None) MUST still be called.
        # Skip it and WKWebView leaves the input wedged forever; clicking it
        # again never opens anything.
        handler(panel.URLs() if panel.runModal() == NSModalResponseOK else None)

    # The signature has to be declared BY HAND. Let PyObjC infer it and the
    # last argument becomes "@" (an ordinary object) instead of "@?" (a
    # block) — at which point `handler(...)` calls into nothing and the
    # picker hangs. Measured: without this line the signature is v@:@@@@,
    # with it, v@:@@@@?.
    webView_runOpenPanelWithParameters_initiatedByFrame_completionHandler_ = objc.selector(
        _mo_hop_chon_tep,
        selector=b"webView:runOpenPanelWithParameters:initiatedByFrame:completionHandler:",
        signature=b"v@:@@@@?",
    )

    # --- the way out ------------------------------------------------------
    # Job postings live on linkedin.com, greenhouse.io… — that is, OUTSIDE
    # the app. WKWebView does not open a new window by itself: without this
    # method clicking <a target=_blank> does NOTHING, no error, no log — the
    # very same class of bug the file picker above already hit once.
    #
    # And do not let it open INSIDE the app window either: this window has no
    # address bar and no Back button. Navigating to LinkedIn loses the
    # dashboard, and the only way back is to quit and reopen.
    #
    # So: hand it to the default browser, then return None so WKWebView does
    # not build a new webview.
    def _mo_ra_trinh_duyet(self, _webview, _config, action, _features):
        url = action.request().URL()
        if url is not None:
            NSWorkspace.sharedWorkspace().openURL_(url)
        return None                    # None = do not build a new webview

    # The signature is declared BY HAND for the same reason as the file
    # picker. Let PyObjC infer it and it sees `return None` and concludes the
    # method returns void ("v"), while WKWebView calls it to GET BACK a
    # WKWebView* ("@"). Declare the return type wrong and it reads garbage
    # out of the return register — works sometimes, not others, and that kind
    # of bug never surfaces as a message.
    #   @ = returns an object · @: = self, cmd · @@@@ = four object arguments
    webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_ = objc.selector(
        _mo_ra_trinh_duyet,
        selector=b"webView:createWebViewWithConfiguration:"
                 b"forNavigationAction:windowFeatures:",
        signature=b"@@:@@@@",
    )

    # --- the app lifecycle ------------------------------------------------
    def applicationShouldTerminateAfterLastWindowClosed_(self, _app) -> bool:
        return False                       # closing the window != quitting

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, has_visible) -> bool:
        if not has_visible:
            self.showWindow_(None)
        return True

    def windowShouldClose_(self, _sender) -> bool:
        self.window.orderOut_(None)        # hide, do not close — the app runs on
        return False

    # --- actions ------------------------------------------------------------
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
        # Chrome runs under the app's own profile — quitting and leaving it
        # behind makes it an orphaned window nobody closes. EVERY port, not
        # just the scan port: the Apply window is deliberately left open, so
        # this is the only place that closes it.
        from .browser import chrome
        chrome.shutdown_all()
        AppHelper.stopEventLoop()

    # --- the menu-bar labels ----------------------------------------------
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
    """The top menu. Without an Edit menu, cmd-C/cmd-V do not work in the
    WebView."""
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
    dia_chi.ghi(url)        # see core/dia_chi.py — the port is no longer fixed
    threading.Thread(target=httpd.serve_forever, daemon=True, name="web").start()

    # Attach the journal to the real DB — before this line it is memory only.
    journal.log.open()
    scheduler = scheduler_mod.current()
    scheduler.start()

    # THE TELEGRAM LISTENER — its own thread, not shared with the scheduler:
    # each long-poll sleeps 25 seconds and the scan must not sleep with it.
    # It exits immediately if no bot is connected or the control level is OFF.
    from . import bao as _bao
    threading.Thread(target=_bao.nghe, args=(scheduler.stop_flag,),
                     daemon=True, name="telegram").start()

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)   # Dock icon, cmd-tab

    delegate = Delegate.alloc().init()

    rect = NSMakeRect(0, 0, WINDOW_W, WINDOW_H)
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect,
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        | NSWindowStyleMaskFullSizeContentView,      # content runs under the title bar
        NSBackingStoreBuffered, False)
    window.setTitle_("jobbot")
    # A transparent title bar with hidden text -> the sidebar reaches the top
    # and only the three traffic lights float over the dark background. The
    # CSS already reserves 38px up there.
    window.setTitlebarAppearsTransparent_(True)
    window.setTitleVisibility_(NSWindowTitleHidden)
    # matches --side in app.css (#1A1A1A) — the app FRAME background, not the
    # workspace background. Get it wrong and the window flashes off-tone as
    # it opens.
    window.setBackgroundColor_(
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.102, 0.102, 0.102, 1.0))
    window.setMinSize_(NSMakeRect(0, 0, 760, 540).size)
    window.center()
    window.setDelegate_(delegate)

    config = WKWebViewConfiguration.alloc().init()                   # noqa: F821
    webview = WKWebView.alloc().initWithFrame_configuration_(rect, config)   # noqa: F821
    webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
    webview.setValue_forKey_(False, "drawsBackground")   # transparent webview -> dark
    webview.setUIDelegate_(delegate)     # without this line <input type=file> dies silently
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

    print(f"  jobbot — app window · content from {url}", flush=True)
    AppHelper.runEventLoop()
    httpd.server_close()
    dia_chi.xoa()
    return 0
