"""Talk to a Chrome tab over the DevTools Protocol.

Only what a job board needs: open a page, wait, run JS, take the HTML,
scroll, click. Not a complete automation library — deliberately not.
"""

from __future__ import annotations

import json
import random
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .chrome import PORT
from .ws import WebSocket

# A human-shaped pace: a short pause between actions, and unevenly spaced.
# Not to dodge detection — but because a page needs time to render, and
# firing back to back reads a DOM that is not finished.
PAUSE = (0.6, 1.8)


class CDPError(RuntimeError):
    pass


def _targets(port: int) -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
        return json.load(r)


@dataclass
class Tab:
    ws: WebSocket
    target_id: str
    port: int = PORT
    _next: int = 1

    # --- nền ---------------------------------------------------------------
    def call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        self._next += 1
        message_id = self._next
        self.ws.send(json.dumps({"id": message_id, "method": method,
                                 "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = json.loads(self.ws.recv())
            if data.get("id") != message_id:
                continue                            # an event, not a response
            if "error" in data:
                raise CDPError(f"{method}: {data['error'].get('message')}")
            return data.get("result", {})
        raise CDPError(f"{method}: timed out after {timeout:g}s")

    def eval(self, expression: str, timeout: float = 30.0):
        result = self.call("Runtime.evaluate",
                           {"expression": expression, "returnByValue": True,
                            "awaitPromise": True}, timeout)
        if result.get("exceptionDetails"):
            raise CDPError(result["exceptionDetails"].get("text", "lỗi JS"))
        return result.get("result", {}).get("value")

    # --- actions -----------------------------------------------------------
    def go(self, url: str, wait_for: str = "", timeout: float = 30.0) -> None:
        self.call("Page.navigate", {"url": url}, timeout)
        self.settle(wait_for, timeout)

    def settle(self, wait_for: str = "", timeout: float = 30.0) -> None:
        """Wait for the page to settle. With a selector, wait for that."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.35)
            try:
                ready = self.eval("document.readyState", timeout=8)
                if ready not in ("interactive", "complete"):
                    continue
                if not wait_for:
                    break
                found = self.eval(
                    f"!!document.querySelector({json.dumps(wait_for)})", timeout=8)
                if found:
                    break
            except CDPError:
                continue
        self.pause()

    def html(self) -> str:
        return self.eval("document.documentElement.outerHTML") or ""

    def text(self) -> str:
        return self.eval("document.body ? document.body.innerText : ''") or ""

    def click(self, selector: str) -> bool:
        done = self.eval(
            f"(()=>{{const e=document.querySelector({json.dumps(selector)});"
            "if(!e)return false;e.click();return true;})()")
        self.pause()
        return bool(done)

    def scroll_to_end(self, rounds: int = 6) -> None:
        """Infinite scroll: scroll until the height stops growing."""
        last = 0
        for _ in range(rounds):
            self.eval("window.scrollTo(0, document.body.scrollHeight)")
            self.pause()
            height = self.eval("document.body.scrollHeight") or 0
            if height == last:
                break
            last = height

    @staticmethod
    def pause() -> None:
        time.sleep(random.uniform(*PAUSE))

    def close(self) -> None:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json/close/{self.target_id}", timeout=5)
        except Exception:                           # noqa: BLE001
            pass
        finally:
            self.ws.close()


def pages(port: int = PORT) -> list[dict]:
    """The open tabs. Used to find a page opened earlier, rather than keeping
    a handle in server memory — a handle is lost on restart, the tab is
    still sitting there."""
    try:
        return [t for t in _targets(port) if t.get("type") == "page"]
    except (OSError, ValueError):
        return []


def attach(target_id: str, port: int = PORT) -> Tab:
    """Attach to an EXISTING tab. Opens nothing, navigates nowhere."""
    tab = Tab(WebSocket(f"ws://127.0.0.1:{port}/devtools/page/{target_id}"),
              target_id, port)
    tab.call("Runtime.enable")
    return tab


def open_tab(url: str = "about:blank", port: int = PORT) -> Tab:
    """Mở tab mới qua Target.createTarget.

    Does NOT use the /json/new HTTP endpoint: newer Chrome requires PUT
    instead of GET and returns 405, so that route breaks per version. The CDP
    command is stable.
    """
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as r:
        browser_ws = json.load(r)["webSocketDebuggerUrl"]

    control = WebSocket(browser_ws)
    try:
        control.send(json.dumps({"id": 1, "method": "Target.createTarget",
                                 "params": {"url": url}}))
        while True:
            reply = json.loads(control.recv())
            if reply.get("id") == 1:
                break
        if "error" in reply:
            raise CDPError(f"Target.createTarget: {reply['error'].get('message')}")
        target_id = reply["result"]["targetId"]
    finally:
        control.close()

    tab = Tab(WebSocket(f"ws://127.0.0.1:{port}/devtools/page/{target_id}"),
              target_id, port)
    tab.call("Page.enable")
    tab.call("Runtime.enable")
    return tab
