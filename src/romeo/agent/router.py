"""Hybrid routing: decide whether a request goes to the local model or to Claude.

Local (Ollama) handles short, single-step, text-only requests. Anything that
needs to look at a screen, spans several steps, or touches the phone goes to
Claude, which is far more reliable at multi-step GUI control.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

LOCAL_MODEL = os.environ.get("ROMEO_LOCAL_MODEL", "qwen3:8b")
CLOUD_MODEL = os.environ.get("ROMEO_CLOUD_MODEL", "claude-sonnet-5-5")

_VISION = re.compile(
    r"(หน้าจอ|จอ|screen|screenshot|คลิก|click|กด|tap|แตะ|ปัด|swipe|เลื่อน|scroll|"
    r"หน้าต่าง|window|ปุ่ม|button|ไอคอน|icon|ดูให้|เห็น)", re.IGNORECASE)
_PHONE = re.compile(r"(iphone|ไอโฟน|โทรศัพท์|มือถือ|phone|โทรหา|ส่งข้อความ|imessage|sms)",
                    re.IGNORECASE)
_MULTI_STEP = re.compile(r"(แล้ว|จากนั้น|ต่อด้วย|และ|\bthen\b|\band\b|after that|,)",
                         re.IGNORECASE)


@dataclass(frozen=True)
class Route:
    engine: str  # "ollama" | "cloud"
    model: str
    reason: str


def route(request: str) -> Route:
    text = request.strip()
    if _PHONE.search(text):
        return Route("cloud", CLOUD_MODEL, "phone control")
    if _VISION.search(text):
        return Route("cloud", CLOUD_MODEL, "needs to see/operate the screen")
    if len(_MULTI_STEP.findall(text)) >= 2 or len(text) > 240:
        return Route("cloud", CLOUD_MODEL, "multi-step task")
    return Route("ollama", LOCAL_MODEL, "simple request")
