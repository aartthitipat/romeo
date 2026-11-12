"""Web dashboard: live status, chat, emergency stop, action history, devices.

Served by the standard library (no extra dependencies). By default it only
listens on 127.0.0.1. To open it from the iPhone, bind 0.0.0.0 — then every
request must carry ROMEO_BRIDGE_TOKEN (header X-Romeo-Token or ?token=).
"""

from __future__ import annotations

import hmac
import json
import os
import queue
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

from romeo.common.audit import log_path
from romeo.ui.events import EventHub
from romeo.voice.runner import CommandRunner

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MAX_BODY = 16_384


def default_devices() -> dict[str, Any]:
    windows: dict[str, Any] = {"ok": sys.platform == "win32", "detail": sys.platform}
    if sys.platform == "win32":
        try:
            import pywinauto  # noqa: F401

            windows["detail"] = "พร้อมควบคุม"
        except ImportError:
            windows = {"ok": False, "detail": "ยังไม่ได้ติดตั้ง pywinauto"}

    iphone: dict[str, Any] = {"ok": False, "detail": "ไม่ได้เชื่อมต่อ"}
    try:
        import httpx

        url = os.environ.get("ROMEO_WDA_URL", "http://127.0.0.1:8100").rstrip("/")
        httpx.get(url + "/status", timeout=1.5).raise_for_status()
        iphone = {"ok": True, "detail": "WebDriverAgent พร้อม (คุมหน้าจอได้)"}
    except Exception:
        if os.environ.get("ROMEO_BRIDGE_TOKEN"):
            iphone = {"ok": True, "detail": "Shortcuts bridge (ระดับ A)"}
    return {"windows": windows, "iphone": iphone}


def read_audit(n: int = 50) -> list[dict]:
    path = log_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text("utf-8").splitlines()[-n:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))


class DashboardServer:
    def __init__(self, hub: EventHub, runner: CommandRunner, *, host: str = "127.0.0.1",
                 port: int = 8767, token: Optional[str] = None, wake_model: str = "",
                 devices: Callable[[], dict] = default_devices) -> None:
        self.hub, self.runner = hub, runner
        self.host, self.port = host, port
        self.remote = host not in LOOPBACK
        self.token = token or ""
        if self.remote and len(self.token) < 16:
            raise ValueError("opening the dashboard to the network needs ROMEO_BRIDGE_TOKEN "
                             "(at least 16 characters)")
        self.wake_model = wake_model
        self.devices = devices
        self._server: Optional[ThreadingHTTPServer] = None
        self._html = resources.files("romeo.ui").joinpath("static/index.html").read_bytes()

    @property
    def url(self) -> str:
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{host}:{self.port}/"

    def state(self) -> dict[str, Any]:
        stopped = self.runner.kill_switch.engaged()
        return {
            "state": "stopped" if stopped else self.hub.state,
            "stopped": stopped,
            "wake_model": self.wake_model,
            "events": self.hub.history()[-60:],
        }

    def start(self) -> None:
        srv = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            # ---------------------------------------------------- helpers --
            def _query(self) -> dict[str, list[str]]:
                return parse_qs(urlparse(self.path).query)

            def _route(self) -> str:
                return urlparse(self.path).path.rstrip("/") or "/"

            def _is_local(self) -> bool:
                return self.client_address[0] in LOOPBACK

            def _authorized(self) -> bool:
                if not srv.remote:
                    return True
                given = self.headers.get("X-Romeo-Token") or self._query().get("token", [""])[0]
                return hmac.compare_digest(given, srv.token)

            def _json(self, code: int, body: Any) -> None:
                payload = json.dumps(body, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def _body(self) -> dict:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length > MAX_BODY:
                    raise ValueError("too large")
                data = json.loads(self.rfile.read(length) or b"{}")
                return data if isinstance(data, dict) else {}

            # ------------------------------------------------------- GET ---
            def do_GET(self) -> None:
                route = self._route()
                if route == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(srv._html)))
                    self.end_headers()
                    self.wfile.write(srv._html)
                    return
                if not self._authorized():
                    return self._json(401, {"error": "bad token"})
                if route == "/api/state":
                    return self._json(200, {**srv.state(), "local": self._is_local()})
                if route == "/api/audit":
                    n = int(self._query().get("n", ["50"])[0] or 50)
                    return self._json(200, read_audit(min(max(n, 1), 500)))
                if route == "/api/devices":
                    return self._json(200, srv.devices())
                if route == "/api/events":
                    return self._stream()
                self._json(404, {"error": "not found"})

            def _stream(self) -> None:
                after = int(self.headers.get("Last-Event-ID")
                            or self._query().get("after", ["0"])[0] or 0)
                q = srv.hub.subscribe()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    for event in srv.hub.history(after):
                        self._send_event(event)
                    while True:
                        try:
                            self._send_event(q.get(timeout=15))
                        except queue.Empty:
                            self.wfile.write(b": keep-alive\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    srv.hub.unsubscribe(q)

            def _send_event(self, event: dict) -> None:
                data = json.dumps(event, ensure_ascii=False)
                self.wfile.write(f"id: {event['id']}\ndata: {data}\n\n".encode())
                self.wfile.flush()

            # ------------------------------------------------------ POST ---
            def do_POST(self) -> None:
                if not self._authorized():
                    return self._json(401, {"error": "bad token"})
                route = self._route()
                try:
                    body = self._body()
                except (ValueError, json.JSONDecodeError):
                    return self._json(400, {"error": "invalid body"})
                if route == "/api/ask":
                    text = str(body.get("text", "")).strip()
                    if not text:
                        return self._json(400, {"error": "empty"})
                    return self._json(200, {"reply": srv.runner.handle(text, source="web")})
                if route == "/api/stop":
                    srv.runner.kill_switch.engage("dashboard stop button")
                    srv.hub.publish("state", {"state": "stopped"})
                    return self._json(200, {"stopped": True})
                if route == "/api/resume":
                    if not self._is_local():
                        return self._json(403, {"error": "resume only from this computer"})
                    srv.runner.kill_switch.release()
                    srv.hub.publish("state", {"state": "idle"})
                    return self._json(200, {"stopped": False})
                self._json(404, {"error": "not found"})

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
