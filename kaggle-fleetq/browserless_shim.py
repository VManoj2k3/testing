"""Minimal browserless-compatible HTTP service for FleetQ's browser skill, on Playwright's headless Chromium.

FleetQ (app/Domain/Skill/Actions/ExecuteBrowserSkillAction.php) only calls three browserless v1 endpoints,
all POST with an `Authorization: Token <token>` header:
  /screenshot {url, options{type, fullPage}, waitFor, viewport{width, height}} -> image bytes
  /content    {url, waitFor}                                                 -> rendered HTML
  /pdf        {url, options{printBackground, format}, waitFor}               -> PDF bytes
Usage: BROWSERLESS_TOKEN=... python browserless_shim.py [port]   (binds 127.0.0.1)
"""
import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright

TOKEN = os.environ.get("BROWSERLESS_TOKEN", "")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
lock = threading.Lock()
pw = sync_playwright().start()
browser = pw.chromium.launch(args=["--no-sandbox"], executable_path=os.environ.get("CHROME_PATH") or None)


def render(path, body):
    url = body.get("url")
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError("url must be http(s)")
    vp = body.get("viewport") or {}
    opts = body.get("options") or {}
    with lock:
        page = browser.new_page(viewport={"width": int(vp.get("width", 1280)), "height": int(vp.get("height", 720))})
        try:
            page.goto(url, wait_until="load", timeout=60000)
            page.wait_for_timeout(min(int(body.get("waitFor") or 0), 30000))
            if path == "/screenshot":
                kind = "jpeg" if opts.get("type") == "jpeg" else "png"
                return page.screenshot(type=kind, full_page=bool(opts.get("fullPage"))), f"image/{kind}"
            if path == "/content":
                return page.content().encode(), "text/html; charset=utf-8"
            if path == "/pdf":
                return page.pdf(format=opts.get("format", "A4"),
                                print_background=bool(opts.get("printBackground", True))), "application/pdf"
        finally:
            page.close()
    raise KeyError(path)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, data, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        self._send(200, b'{"status":"ok"}') if self.path.startswith("/health") else self._send(404, b"{}")

    def do_POST(self):
        if TOKEN and self.headers.get("Authorization") != f"Token {TOKEN}" and f"token={TOKEN}" not in self.path:
            return self._send(401, b'{"error":"bad token"}')
        path = self.path.split("?")[0]
        if path not in ("/screenshot", "/content", "/pdf"):
            return self._send(404, b'{"error":"unsupported endpoint"}')
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            data, ctype = render(path, body)
            self._send(200, data, ctype)
        except Exception as e:
            self._send(400, json.dumps({"error": str(e)[:500]}).encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"browserless shim on 127.0.0.1:{PORT}", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()   # single thread: Playwright sync API is thread-bound
