"""In-process event hub: the voice assistant, runner and UIs talk through it.

Event kinds:
    state          {"state": idle|awake|listening|thinking|speaking|follow_up|stopped}
    heard          {"text", "source"}       what the user said/typed
    reply          {"text", "source"}       Romeo's answer
    wake_rejected  {"reason"}
    error          {"text"}
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
from collections import deque
from typing import Any, Optional

STATES = ("idle", "awake", "listening", "thinking", "speaking", "follow_up", "stopped")


class EventHub:
    def __init__(self, history: int = 200) -> None:
        self._lock = threading.Lock()
        self._subscribers: list["queue.Queue[dict]"] = []
        self._history: deque[dict] = deque(maxlen=history)
        self._ids = itertools.count(1)
        self.state = "idle"

    def publish(self, kind: str, data: Optional[dict[str, Any]] = None) -> dict:
        event = {"id": next(self._ids), "ts": time.time(), "kind": kind, **(data or {})}
        with self._lock:
            if kind == "state":
                self.state = event.get("state", self.state)
            self._history.append(event)
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # a stalled browser tab must not block the assistant
        return event

    # Convenience used as a plain callback: hub.emit("state", {"state": "idle"})
    def emit(self, kind: str, data: Optional[dict[str, Any]] = None) -> None:
        self.publish(kind, data)

    def subscribe(self, maxsize: int = 500) -> "queue.Queue[dict]":
        q: "queue.Queue[dict]" = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[dict]") -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def history(self, after_id: int = 0) -> list[dict]:
        with self._lock:
            return [e for e in self._history if e["id"] > after_id]


_default: Optional[EventHub] = None


def default_hub() -> EventHub:
    global _default
    if _default is None:
        _default = EventHub()
    return _default
