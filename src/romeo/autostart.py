"""Start Romeo automatically when the user signs in to Windows.

Uses the per-user Run key (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run):
no administrator rights needed, runs in the user's desktop session (so the
microphone, the dashboard and the floating overlay all work), and shows in
Task Manager ▸ Startup apps where it can also be switched off.

The entry runs `pythonw.exe -m romeo listen --background`: no console window,
output goes to ~/.romeo/logs/romeo.log, and a second copy exits immediately.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from romeo.common.safety import romeo_home

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Romeo"


class Registry(Protocol):
    def get(self, key: str, name: str) -> Optional[str]: ...
    def set(self, key: str, name: str, value: str) -> None: ...
    def delete(self, key: str, name: str) -> None: ...


class WinRegistry:
    """HKEY_CURRENT_USER string values."""

    def __init__(self) -> None:
        import winreg

        self.w = winreg

    def get(self, key: str, name: str) -> Optional[str]:
        try:
            with self.w.OpenKey(self.w.HKEY_CURRENT_USER, key) as k:
                return self.w.QueryValueEx(k, name)[0]
        except FileNotFoundError:
            return None

    def set(self, key: str, name: str, value: str) -> None:
        with self.w.CreateKeyEx(self.w.HKEY_CURRENT_USER, key, 0, self.w.KEY_SET_VALUE) as k:
            self.w.SetValueEx(k, name, 0, self.w.REG_SZ, value)

    def delete(self, key: str, name: str) -> None:
        try:
            with self.w.OpenKey(self.w.HKEY_CURRENT_USER, key, 0, self.w.KEY_SET_VALUE) as k:
                self.w.DeleteValue(k, name)
        except FileNotFoundError:
            pass


def gui_python(executable: Optional[str] = None) -> str:
    """pythonw.exe next to the current interpreter (no console window), if present."""
    exe = Path(executable or sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return str(pyw if pyw.exists() else exe)


def build_command(extra_args: tuple[str, ...] = (), executable: Optional[str] = None) -> str:
    args = ["-m", "romeo", "listen", "--background", *extra_args]
    return " ".join([f'"{gui_python(executable)}"', *args])


@dataclass
class Status:
    enabled: bool
    command: Optional[str]
    current: bool  # points at this Python installation


class Autostart:
    def __init__(self, registry: Optional[Registry] = None, key: str = RUN_KEY,
                 name: str = VALUE_NAME) -> None:
        if registry is None:
            if sys.platform != "win32":
                raise RuntimeError("autostart is only supported on Windows")
            registry = WinRegistry()
        self.reg, self.key, self.name = registry, key, name

    def enable(self, extra_args: tuple[str, ...] = (), executable: Optional[str] = None) -> str:
        command = build_command(extra_args, executable)
        self.reg.set(self.key, self.name, command)
        return command

    def disable(self) -> bool:
        existed = self.reg.get(self.key, self.name) is not None
        self.reg.delete(self.key, self.name)
        return existed

    def status(self, executable: Optional[str] = None) -> Status:
        command = self.reg.get(self.key, self.name)
        current = command is not None and command.startswith(build_command((), executable))
        return Status(command is not None, command, current)


# --------------------------------------------------------- background mode ---


def log_file() -> Path:
    return romeo_home() / "logs" / "romeo.log"


def redirect_output(max_bytes: int = 2_000_000) -> Path:
    """Send stdout/stderr to the log file (pythonw has no console)."""
    path = log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > max_bytes:
        path.replace(path.with_suffix(".log.1"))
    stream = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives for the process
    sys.stdout = sys.stderr = stream
    return path


class SingleInstance:
    """Holds a machine-wide lock so autostart + a manual start don't both run."""

    def __init__(self, name: str = "romeo-listen") -> None:
        self.name = name
        self._handle = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            self._handle = kernel32.CreateMutexW(None, False, f"Local\\{self.name}")
            return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
        import fcntl

        path = romeo_home() / f"{self.name}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(path, "w")  # noqa: SIM115 - held until release
        try:
            fcntl.flock(self._handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._handle.close()
            self._handle = None
            return False
        self._handle.write(str(os.getpid()))
        self._handle.flush()
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self._handle)
        else:
            self._handle.close()
        self._handle = None
