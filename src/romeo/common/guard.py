"""One call that every MCP tool runs before acting: safety → approval → audit."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from romeo.common import audit
from romeo.common.approval import default_approver
from romeo.common.safety import Risk, Verdict, default_gate


class ActionBlocked(Exception):
    """Raised when the safety gate or the user refuses an action."""


def guard(
    device: str,
    action: str,
    risk: Risk,
    params: dict[str, Any],
    *,
    targets: Iterable[Optional[str]] = (),
    text: Optional[str] = None,
    command: Optional[str] = None,
) -> None:
    decision = default_gate().check(
        action, risk, targets=targets, text=text, command=command
    )
    if decision.verdict is Verdict.DENY:
        audit.record(device, action, params, "deny", note=decision.reason)
        raise ActionBlocked(f"ปฏิเสธ: {decision.reason}")
    if decision.verdict is Verdict.ASK:
        detail = ", ".join(f"{k}={v!r}" for k, v in params.items())
        if not default_approver().request(f"[{device}] {action}", detail):
            audit.record(device, action, params, "user_denied")
            raise ActionBlocked("ผู้ใช้ไม่อนุญาต (หรือไม่ตอบภายในเวลา)")
        audit.record(device, action, params, "user_approved")
        return
    audit.record(device, action, params, "allow")
