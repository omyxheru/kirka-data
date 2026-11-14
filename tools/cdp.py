"""A direct Chrome DevTools connection to the kirka.io tab, used by every tool (via kb.kirka_page).

Why: Playwright's connect_over_cdp attaches to every target in the browser, and since Chrome 155
the address-bar popup is a "browser_ui" target that Playwright can't handle: its driver crashes
("Connection closed while reading from the driver"). This talks to the page target alone, over
one websocket, and offers the small part of Playwright's Page the tools use: evaluate,
eval_on_selector, screenshot, mouse.move, wait_for_timeout, on("load"), url, and a CDP session.
"""
import base64
import json
import re
import time
import urllib.request

import websocket

PORT = 9222
FN = re.compile(r"^\s*(async\s+)?(function\b|\([^()]*\)\s*=>|\(\s*\[[^\]]*\]\s*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")


class CDPError(RuntimeError):
    pass


def _browser_call(method, params=None):
    url = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=5))["webSocketDebuggerUrl"]
    ws = websocket.create_connection(url, timeout=10, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                if "error" in m:
                    raise CDPError(m["error"])
                return m["result"]
    finally:
        ws.close()


class _Mouse:
    def __init__(self, page):
        self.page = page

    def move(self, x, y, steps=1):
        self.page.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})

    def click(self, x, y):
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.page.send("Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left", "clickCount": 1})


class Page:
    def __init__(self, target):
        self.target_id = target["targetId"]
        self.url = target["url"]
        self.ws = websocket.create_connection(f"ws://127.0.0.1:{PORT}/devtools/page/{self.target_id}",
                                              timeout=120, suppress_origin=True)
        self._id = 0
        self._handlers = {}
        self.mouse = _Mouse(self)
        self.context = self   # page.context.new_cdp_session(page) -> this page

    # ---- raw protocol
    def _event(self, m):
        if m.get("method") == "Page.loadEventFired":
            for fn in self._handlers.get("load", []):
                fn(self)

    def send(self, method, params=None):
        self._id += 1
        i = self._id
        self.ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == i:
                if "error" in m:
                    raise CDPError(f"{method}: {m['error'].get('message')}")
                return m.get("result", {})
            self._event(m)

    def new_cdp_session(self, _page=None):
        return self

    def on(self, event, fn):
        self._handlers.setdefault(event, []).append(fn)
        if event == "load":
            self.send("Page.enable")

    def wait_for_timeout(self, ms):
        end = time.time() + ms / 1000
        self.ws.settimeout(0.05)
        try:
            while time.time() < end:
                try:
                    self._event(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
        finally:
            self.ws.settimeout(120)

    # ---- the Playwright-like part
    def evaluate(self, js, arg=None):
        expr = f"({js})({json.dumps(arg)})" if FN.match(js) else js
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True,
                                           "userGesture": True})
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise CDPError((d.get("exception") or {}).get("description") or d.get("text"))
        return r.get("result", {}).get("value")

    def eval_on_selector(self, sel, fn):
        return self.evaluate(f"(s => ({fn})(document.querySelector(s)))", sel)

    def screenshot(self, path, **_):
        data = self.send("Page.captureScreenshot", {"format": "png"})["data"]
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))
        return path

    def close(self):
        try:
            self.ws.close()
        except Exception:   # noqa: BLE001
            pass


def kirka_page():
    """The visible kirka.io tab (or the first one, if none reports visible)."""
    tabs = [t for t in _browser_call("Target.getTargets")["targetInfos"]
            if t["type"] == "page" and "kirka.io" in t["url"]]
    if not tabs:
        raise SystemExit("No kirka.io tab found. Is Chrome open on kirka.io? (tools/open-kirka.ps1)")
    for t in tabs:
        p = Page(t)
        try:
            if p.evaluate("document.visibilityState") == "visible":
                return p
        except CDPError:
            pass
        p.close()
    return Page(tabs[0])
