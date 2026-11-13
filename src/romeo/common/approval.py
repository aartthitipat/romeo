"""User approval for SENSITIVE actions.

MCP servers run as stdio subprocesses of OpenJarvis, so they cannot prompt in
the chat themselves. On Windows we show a native, always-on-top Yes/No dialog
on the user's desktop; with no answer before the timeout the action is denied.
Elsewhere (tests, headless) approval is denied unless a callback is injected.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Callable, Optional

ApproveFn = Callable[[str, str], bool]

_MB_YESNO = 0x04
_MB_ICONWARNING = 0x30
_MB_TOPMOST = 0x40000
_MB_SETFOREGROUND = 0x10000
_IDYES = 6


def _windows_dialog(action: str, detail: str, timeout_s: float) -> bool:
    import ctypes

    result: dict[str, int] = {}

    def show() -> None:
        result["answer"] = ctypes.windll.user32.MessageBoxW(
            0,
            f"Romeo ต้องการทำสิ่งนี้:\n\n{action}\n\n{detail}\n\nอนุญาตหรือไม่?",
            "Romeo — ขออนุญาต",
            _MB_YESNO | _MB_ICONWARNING | _MB_TOPMOST | _MB_SETFOREGROUND,
        )

    worker = threading.Thread(target=show, daemon=True)
    worker.start()
    worker.join(timeout_s)
    return result.get("answer") == _IDYES


class Approver:
    def __init__(
        self, callback: Optional[ApproveFn] = None, timeout_s: float = 60.0
    ) -> None:
        self._callback = callback
        self.timeout_s = float(os.environ.get("ROMEO_APPROVAL_TIMEOUT", timeout_s))

    def request(self, action: str, detail: str = "") -> bool:
        if self._callback is not None:
            return bool(self._callback(action, detail))
        if sys.platform == "win32":
            return _windows_dialog(action, detail, self.timeout_s)
        return False


_default: Optional[Approver] = None


def default_approver() -> Approver:
    global _default
    if _default is None:
        _default = Approver()
    return _default


def set_default_approver(approver: Approver) -> None:
    global _default
    _default = approver
