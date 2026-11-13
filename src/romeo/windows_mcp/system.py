"""PowerShell execution and system controls (always SENSITIVE)."""

from __future__ import annotations

import subprocess

MAX_OUTPUT = 20_000

SYSTEM_ACTIONS = {
    "lock": "rundll32.exe user32.dll,LockWorkStation",
    "sleep": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
    "shutdown": "shutdown /s /t 30",
    "restart": "shutdown /r /t 30",
    "cancel_shutdown": "shutdown /a",
    "mute": "(New-Object -ComObject WScript.Shell).SendKeys([char]173)",
    "volume_up": "(New-Object -ComObject WScript.Shell).SendKeys([char]175)",
    "volume_down": "(New-Object -ComObject WScript.Shell).SendKeys([char]174)",
}


def run_powershell(command: str, timeout: int = 60) -> str:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=min(max(timeout, 1), 300),
    )
    out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    return f"exit={proc.returncode}\n{out[:MAX_OUTPUT]}"
