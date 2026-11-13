"""HTTP endpoint for the iPhone "Hey Siri, Romeo" shortcut.

    POST /ask   header X-Romeo-Token   body {"text": "..."}   ->   {"reply": "..."}

Siri is the wake word on the phone (iOS does not let other apps listen in the
background); the shortcut dictates the command and sends it here.
"""

from __future__ import annotations

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from romeo.voice.runner import CommandRunner

MAX_BODY = 16_384


class AskServer:
    def __init__(self, token: str, runner: CommandRunner, host: str = "0.0.0.0",
                 port: int = 8766) -> None:
        if not token or len(token) < 16:
            raise ValueError("ROMEO_BRIDGE_TOKEN must be at least 16 characters")
        self.token, self.runner = token, runner
        self.host, self.port = host, port
        self._server: Optional[ThreadingHTTPServer] = None

    def start(self) -> None:
        srv = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _send(self, code: int, body: dict) -> None:
                payload = json.dumps(body, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:
                if not hmac.compare_digest(self.headers.get("X-Romeo-Token", ""), srv.token):
                    return self._send(401, {"error": "bad token"})
                if self.path.rstrip("/") != "/ask":
                    return self._send(404, {"error": "not found"})
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length > MAX_BODY:
                    return self._send(413, {"error": "too large"})
                try:
                    text = str(json.loads(self.rfile.read(length) or b"{}").get("text", ""))
                except (json.JSONDecodeError, AttributeError):
                    return self._send(400, {"error": "invalid json"})
                self._send(200, {"reply": srv.runner.handle(text, source="siri")})

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        if self.port == 0:
            self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
