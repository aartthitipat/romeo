"""Level A: a tiny token-protected job queue the iPhone's Shortcuts app polls.

The "Romeo Listener" shortcut on the iPhone loops:
    GET  /next      (header X-Romeo-Token)  -> {"id", "action", "params"} or 204
    ...runs the matching Shortcuts action...
    POST /result    {"id", "ok", "output"}
See shortcuts/README.md for how to build the shortcut.
"""

from __future__ import annotations

import hmac
import json
import queue
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

# Actions the Listener shortcut knows how to perform.
ACTIONS = {
    "open_app": "เปิดแอป (params: app)",
    "send_message": "ส่ง iMessage/SMS (params: to, text)",
    "call": "โทรออก (params: number)",
    "set_alarm": "ตั้งปลุก (params: time HH:MM, label)",
    "play_music": "เล่นเพลง/เพลย์ลิสต์ (params: query)",
    "open_url": "เปิด URL (params: url)",
    "notify": "แสดงแจ้งเตือน (params: text)",
    "run_shortcut": "รัน Shortcut ตามชื่อ (params: name, input)",
    "get_clipboard": "อ่านคลิปบอร์ด iPhone",
    "set_clipboard": "ตั้งคลิปบอร์ด (params: text)",
    "get_battery": "อ่านระดับแบต",
    "get_location": "อ่านตำแหน่งปัจจุบัน",
    "home_scene": "สั่ง HomeKit scene (params: scene)",
}


@dataclass
class Job:
    action: str
    params: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    done: threading.Event = field(default_factory=threading.Event)
    ok: Optional[bool] = None
    output: Any = None


class ShortcutsBridge:
    def __init__(self, token: str, host: str = "0.0.0.0", port: int = 8765) -> None:
        if not token or len(token) < 16:
            raise ValueError("ROMEO_BRIDGE_TOKEN must be at least 16 characters")
        self.token = token
        self.host, self.port = host, port
        self._queue: "queue.Queue[Job]" = queue.Queue()
        self._jobs: dict[str, Job] = {}
        self._server: Optional[ThreadingHTTPServer] = None

    # ------------------------------------------------------------- api ---
    def submit(self, action: str, params: dict[str, Any], wait_s: float = 60.0) -> Job:
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action!r}; known: {sorted(ACTIONS)}")
        job = Job(action, params)
        self._jobs[job.id] = job
        self._queue.put(job)
        job.done.wait(wait_s)
        return job

    def next_job(self) -> Optional[Job]:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def complete(self, job_id: str, ok: bool, output: Any) -> bool:
        job = self._jobs.pop(job_id, None)
        if job is None:
            return False
        job.ok, job.output = ok, output
        job.done.set()
        return True

    # ------------------------------------------------------------ http ---
    def start(self) -> None:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # keep stdio clean for MCP
                pass

            def _authorized(self) -> bool:
                given = self.headers.get("X-Romeo-Token", "")
                return hmac.compare_digest(given, bridge.token)

            def _send(self, code: int, body: Any = None) -> None:
                payload = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if payload:
                    self.wfile.write(payload)

            def do_GET(self) -> None:
                if not self._authorized():
                    return self._send(401, {"error": "bad token"})
                if self.path.rstrip("/") != "/next":
                    return self._send(404)
                job = bridge.next_job()
                if job is None:
                    return self._send(204)
                self._send(200, {"id": job.id, "action": job.action, **job.params})

            def do_POST(self) -> None:
                if not self._authorized():
                    return self._send(401, {"error": "bad token"})
                if self.path.rstrip("/") != "/result":
                    return self._send(404)
                length = int(self.headers.get("Content-Length", "0") or 0)
                try:
                    data = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    return self._send(400, {"error": "invalid json"})
                found = bridge.complete(str(data.get("id", "")),
                                        bool(data.get("ok", True)), data.get("output"))
                self._send(200 if found else 404, {"ok": found})

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
