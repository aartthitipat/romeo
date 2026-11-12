"""Safety gate for every action Romeo performs on a device.

Every MCP tool calls :func:`check` before doing anything. The gate:

* stops everything while the kill switch is engaged,
* hard-denies actions that touch banking/payment apps or secrets,
* tells the caller whether user approval is required (``SENSITIVE``).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional


class Risk(str, Enum):
    READ = "read"  # observe only: screenshot, UI tree, list windows
    ACT = "act"  # ordinary input: click, type, open app (logged)
    SENSITIVE = "sensitive"  # needs explicit approval every time


class Verdict(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW


# Apps/windows Romeo must never operate (matched case-insensitively against
# window titles, process names, app names and iOS bundle ids).
DEFAULT_DENY_PATTERNS: tuple[str, ...] = (
    r"k ?plus", r"kplus", r"com\.kasikornbank",
    r"scb ?easy", r"com\.scb",
    r"krungthai ?next", r"com\.ktb",
    r"bualuang", r"com\.bbl",
    r"krungsri", r"\bkma\b", r"com\.krungsri",
    r"ttb ?touch", r"\bmymo\b", r"com\.gsb",
    r"truemoney", r"paotang", r"เป๋าตัง",
    r"paypal", r"binance", r"bitkub",
    r"keychain", r"1password", r"bitwarden", r"lastpass", r"credential manager",
    r"ธนาคาร", r"mobile banking",
)

# Text Romeo must never type (passwords/OTP are entered by the human only).
_SECRET_HINTS = re.compile(
    r"(password|passcode|รหัสผ่าน|\botp\b|pin ?code|cvv|รหัส ?otp)", re.IGNORECASE
)

# Keyword hints that turn an otherwise ordinary command into a sensitive one.
_SENSITIVE_COMMAND_HINTS = re.compile(
    r"\b(remove-item|del|erase|rmdir|rd|format|shutdown|restart-computer|stop-computer|"
    r"reg(\.exe)?\s+(add|delete)|set-executionpolicy|invoke-webrequest|iwr|curl|wget|"
    r"start-process\s+.*-verb\s+runas|msiexec|winget|choco|diskpart|bcdedit|cipher)\b",
    re.IGNORECASE,
)


def romeo_home() -> Path:
    return Path(os.environ.get("ROMEO_HOME", Path.home() / ".romeo"))


class KillSwitch:
    """File-based kill switch shared by every Romeo process.

    Engaged by the Windows hotkey, ``romeo stop`` or a "หยุด" command from any
    channel. Released only by ``romeo resume``.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or romeo_home() / "STOP"

    def engaged(self) -> bool:
        return self.path.exists()

    def engage(self, reason: str = "manual") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(reason, encoding="utf-8")

    def release(self) -> None:
        self.path.unlink(missing_ok=True)


class SafetyGate:
    def __init__(
        self,
        deny_patterns: Iterable[str] = DEFAULT_DENY_PATTERNS,
        kill_switch: Optional[KillSwitch] = None,
    ) -> None:
        self._deny = [re.compile(p, re.IGNORECASE) for p in deny_patterns]
        self.kill_switch = kill_switch or KillSwitch()

    def is_denied_target(self, *targets: Optional[str]) -> Optional[str]:
        for target in targets:
            if not target:
                continue
            for pattern in self._deny:
                if pattern.search(target):
                    return target
        return None

    def check(
        self,
        action: str,
        risk: Risk,
        *,
        targets: Iterable[Optional[str]] = (),
        text: Optional[str] = None,
        command: Optional[str] = None,
    ) -> Decision:
        if self.kill_switch.engaged():
            return Decision(Verdict.DENY, "kill switch engaged — run `romeo resume`")

        hit = self.is_denied_target(*targets)
        if hit:
            return Decision(Verdict.DENY, f"target '{hit}' is on the deny list")

        if text and _SECRET_HINTS.search(text):
            return Decision(
                Verdict.DENY, "typing passwords/OTP is reserved for the human user"
            )

        if command and _SENSITIVE_COMMAND_HINTS.search(command):
            risk = Risk.SENSITIVE

        if risk is Risk.SENSITIVE:
            return Decision(Verdict.ASK, f"'{action}' requires user approval")
        return Decision(Verdict.ALLOW)


_default_gate: Optional[SafetyGate] = None


def default_gate() -> SafetyGate:
    global _default_gate
    if _default_gate is None:
        _default_gate = SafetyGate()
    return _default_gate
