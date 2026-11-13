"""Append-only JSONL audit log of every action Romeo attempts."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from romeo.common.safety import romeo_home

_lock = threading.Lock()


def log_path() -> Path:
    return romeo_home() / "logs" / "audit.jsonl"


def record(
    device: str,
    action: str,
    params: dict[str, Any],
    verdict: str,
    *,
    ok: Optional[bool] = None,
    note: str = "",
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "device": device,
        "action": action,
        "params": {k: _short(v) for k, v in params.items()},
        "verdict": verdict,
        "ok": ok,
        "note": note,
    }
    path = log_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _short(value: Any, limit: int = 500) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value
