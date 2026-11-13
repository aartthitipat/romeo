"""iPhone connection helpers built on the pymobiledevice3 CLI (works on Windows).

Windows prerequisites: Apple Mobile Device Support (install iTunes or Apple
Devices from the Microsoft Store), iPhone trusted this PC, Developer Mode on.
iOS 17+: also run `pymobiledevice3 remote tunneld` as Administrator.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from typing import Any

WDA_BUNDLE = os.environ.get(
    "ROMEO_WDA_BUNDLE", "com.facebook.WebDriverAgentRunner.xctrunner"
)


def _cli() -> list[str]:
    exe = shutil.which("pymobiledevice3")
    return [exe] if exe else [sys.executable, "-m", "pymobiledevice3"]


def _run(*args: str, timeout: int = 30) -> str:
    proc = subprocess.run(_cli() + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout


def list_devices() -> list[dict[str, Any]]:
    return json.loads(_run("usbmux", "list") or "[]")


def device_info() -> dict[str, Any]:
    info = json.loads(_run("lockdown", "info"))
    keep = ("DeviceName", "ProductType", "ProductVersion", "BatteryCurrentCapacity",
            "BatteryIsCharging", "WiFiAddress")
    return {k: info.get(k) for k in keep if k in info}


def start_wda() -> subprocess.Popen:
    """Launch WebDriverAgent as an XCTest and keep it running in the background.

    Override with ROMEO_WDA_START_CMD if your setup differs (e.g. `go-ios runwda`).
    """
    custom = os.environ.get("ROMEO_WDA_START_CMD")
    cmd = shlex.split(custom) if custom else _cli() + ["developer", "dvt", "xcuitest", WDA_BUNDLE]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def forward_port(local: int = 8100, remote: int = 8100) -> subprocess.Popen:
    return subprocess.Popen(_cli() + ["usbmux", "forward", str(local), str(remote)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
