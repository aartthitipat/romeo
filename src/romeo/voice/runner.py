"""Turn a spoken/typed request into an answer: stop-word → router → OpenJarvis.

Shared by the microphone assistant and the Siri `/ask` endpoint.
"""

from __future__ import annotations

import re
import threading
from typing import Any, Callable, Optional

from romeo.agent.router import LOCAL_MODEL, route
from romeo.common import audit
from romeo.common.safety import KillSwitch

AskFn = Callable[[str, str, str], str]  # (text, engine, model) -> reply

_WAKE_PREFIX = re.compile(
    r"^\s*(hey|เฮ้?|เฮ)?\s*(romeo|jarvis|โรมิโอ|โรเมโอ|จาร์วิส|จาวิส)[\s,.!?]*", re.IGNORECASE)
_STOP = re.compile(
    r"^(หยุด|หยุดเลย|หยุดเดี๋ยวนี้|หยุดทุกอย่าง|หยุดทำงาน|stop|stop it|stop now|stop everything)$",
    re.IGNORECASE)


def clean_command(text: str) -> str:
    """Strip a leading wake phrase ("Hey Romeo, …") and surrounding punctuation."""
    text = _WAKE_PREFIX.sub("", text.strip())
    return text.strip(" \t\n.,!?。")


def is_stop(text: str) -> bool:
    return bool(_STOP.match(clean_command(text)))


def jarvis_ask(text: str, engine: str, model: str) -> str:
    from openjarvis.sdk import Jarvis

    return Jarvis(engine_key=engine, model=model).ask(text, agent="native_react")


class CommandRunner:
    def __init__(self, ask: Optional[AskFn] = None, kill_switch: Optional[KillSwitch] = None) -> None:
        self._ask = ask or jarvis_ask
        self.kill_switch = kill_switch or KillSwitch()
        self._lock = threading.Lock()  # mic and Siri requests run one at a time

    def handle(self, text: str, *, source: str = "voice") -> str:
        command = clean_command(text)
        if not command:
            return "ว่าไงครับ"
        if is_stop(command):
            self.kill_switch.engage(f"voice stop via {source}")
            audit.record(source, "stop", {"text": text}, "kill_switch")
            return "หยุดทุกอย่างแล้วครับ พิมพ์ romeo resume เพื่อให้ทำงานต่อ"
        if self.kill_switch.engaged():
            return "ตอนนี้ Romeo ถูกสั่งหยุดอยู่ครับ พิมพ์ romeo resume ที่คอมก่อน"

        r = route(command)
        params: dict[str, Any] = {"text": command, "engine": r.engine, "model": r.model}
        with self._lock:
            try:
                reply = self._ask(command, r.engine, r.model)
            except Exception as exc:
                if r.engine == "ollama":
                    audit.record(source, "ask", params, "error", ok=False, note=str(exc))
                    return f"ขอโทษครับ เกิดข้อผิดพลาด: {exc}"
                # Cloud unavailable (no key / offline): fall back to the local model.
                audit.record(source, "ask", params, "cloud_failed", ok=False, note=str(exc))
                try:
                    reply = self._ask(command, "ollama", LOCAL_MODEL)
                except Exception as exc2:
                    return f"ขอโทษครับ เกิดข้อผิดพลาด: {exc2}"
        audit.record(source, "ask", params, "allow", ok=True)
        return reply
