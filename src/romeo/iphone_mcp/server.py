"""romeo-iphone — MCP server for controlling an iPhone from the Windows PC.

Level A (no Mac needed): Shortcuts bridge — messages, calls, apps, alarms, HomeKit…
Level B (WebDriverAgent installed): screenshot / UI tree / tap / swipe / type.
"""

from __future__ import annotations

import functools
import io
import os
from typing import Any, Callable, Optional

from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage

from romeo.common.guard import ActionBlocked, guard
from romeo.common.safety import Risk
from romeo.iphone_mcp.shortcuts_bridge import ACTIONS, ShortcutsBridge

DEVICE = "iphone"
mcp = FastMCP("romeo-iphone")

_bridge: Optional[ShortcutsBridge] = None
_wda = None


def safe(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ActionBlocked as exc:
            return str(exc)
        except Exception as exc:
            return f"error: {type(exc).__name__}: {exc}"

    return wrapper


def wda():
    global _wda
    if _wda is None:
        from romeo.iphone_mcp.wda_client import WDAClient

        _wda = WDAClient()
    return _wda


def bridge() -> ShortcutsBridge:
    if _bridge is None:
        raise RuntimeError("Shortcuts bridge is off — set ROMEO_BRIDGE_TOKEN and restart")
    return _bridge


def _active_bundle() -> Optional[str]:
    try:
        return wda().active_app().get("bundleId")
    except Exception:
        return None


def _via_bridge(action: str, params: dict[str, Any], risk: Risk,
                targets: list[Optional[str]] = (), text: Optional[str] = None) -> str:
    guard(DEVICE, action, risk, params, targets=targets, text=text)
    job = bridge().submit(action, params)
    if job.ok is None:
        return ("timeout: iPhone did not pick up the job. Is the 'Romeo Listener' "
                "shortcut running and on the same network/Tailscale?")
    return f"{'ok' if job.ok else 'failed'}: {job.output}"


# ------------------------------------------------- level B: screen control ---


@mcp.tool()
@safe
def iphone_screenshot():
    """Screenshot of the iPhone, scaled to *points* so the pixel coordinates
    you read from it can be passed straight to iphone_tap / iphone_swipe."""
    bundle = _active_bundle()
    guard(DEVICE, "screenshot", Risk.READ, {"app": bundle}, targets=[bundle])
    png = wda().screenshot_png()
    size = wda().window_size()
    img = PILImage.open(io.BytesIO(png)).convert("RGB")
    img = img.resize((int(size["width"]), int(size["height"])))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Image(data=buf.getvalue(), format="png")


@mcp.tool()
@safe
def iphone_ui_tree() -> str:
    """Accessibility tree of the current iPhone screen (labels + frames in points)."""
    bundle = _active_bundle()
    guard(DEVICE, "ui_tree", Risk.READ, {"app": bundle}, targets=[bundle])
    tree = wda().source()
    return tree if len(tree) < 30_000 else tree[:30_000] + "\n…(truncated)"


@mcp.tool()
@safe
def iphone_tap(x: float, y: float) -> str:
    """Tap at (x, y) in points."""
    bundle = _active_bundle()
    guard(DEVICE, "tap", Risk.ACT, {"x": x, "y": y, "app": bundle}, targets=[bundle])
    wda().tap(x, y)
    return f"tapped ({x},{y})"


@mcp.tool()
@safe
def iphone_swipe(x1: float, y1: float, x2: float, y2: float, duration: float = 0.3) -> str:
    """Swipe/drag from (x1,y1) to (x2,y2) in points."""
    bundle = _active_bundle()
    guard(DEVICE, "swipe", Risk.ACT, {"from": [x1, y1], "to": [x2, y2]}, targets=[bundle])
    wda().swipe(x1, y1, x2, y2, duration)
    return "swiped"


@mcp.tool()
@safe
def iphone_type(text: str) -> str:
    """Type into the focused field (keyboard must be visible). Never types passwords/OTP."""
    bundle = _active_bundle()
    guard(DEVICE, "type", Risk.ACT, {"text": text}, targets=[bundle], text=text)
    wda().type_text(text)
    return f"typed {len(text)} chars"


@mcp.tool()
@safe
def iphone_home() -> str:
    """Go to the home screen."""
    guard(DEVICE, "home", Risk.ACT, {})
    wda().home()
    return "home"


@mcp.tool()
@safe
def iphone_open_app(app: str) -> str:
    """Open an app. Pass a bundle id (com.apple.mobilesafari) for WDA, or an app
    name (Safari, LINE) to open it through the Shortcuts bridge."""
    if "." in app and " " not in app:
        guard(DEVICE, "open_app", Risk.ACT, {"bundle": app}, targets=[app])
        wda().launch(app)
        return f"launched {app}"
    return _via_bridge("open_app", {"app": app}, Risk.ACT, targets=[app])


# ----------------------------------------------- level A: Shortcuts bridge ---


@mcp.tool()
@safe
def iphone_send_message(to: str, text: str) -> str:
    """Send an iMessage/SMS from the iPhone. Always asks the user first."""
    return _via_bridge("send_message", {"to": to, "text": text}, Risk.SENSITIVE, text=text)


@mcp.tool()
@safe
def iphone_call(number: str) -> str:
    """Place a phone call from the iPhone. Always asks the user first."""
    return _via_bridge("call", {"number": number}, Risk.SENSITIVE)


@mcp.tool()
@safe
def iphone_shortcut_run(action: str, params: Optional[dict[str, Any]] = None) -> str:
    """Run a Shortcuts-bridge action. Actions:
    open_app, set_alarm, play_music, open_url, notify, run_shortcut,
    get_clipboard, set_clipboard, get_battery, get_location, home_scene."""
    if action in ("send_message", "call"):
        return "use iphone_send_message / iphone_call for this"
    params = params or {}
    risk = Risk.SENSITIVE if action in ("run_shortcut", "home_scene", "get_location") else Risk.ACT
    return _via_bridge(action, params, risk, targets=[str(v) for v in params.values()],
                       text=params.get("text"))


@mcp.tool()
@safe
def iphone_device_info() -> str:
    """Connection status: USB device info (pymobiledevice3), WDA and bridge state."""
    guard(DEVICE, "device_info", Risk.READ, {})
    parts = []
    try:
        from romeo.iphone_mcp import device

        parts.append(f"usb: {device.device_info()}")
    except Exception as exc:
        parts.append(f"usb: unavailable ({exc})")
    try:
        wda().status()
        parts.append("wda: ready (level B screen control available)")
    except Exception as exc:
        parts.append(f"wda: not reachable ({exc})")
    parts.append("bridge: " + ("listening" if _bridge else "off"))
    parts.append("bridge actions: " + ", ".join(sorted(ACTIONS)))
    return "\n".join(parts)


def main() -> None:
    global _bridge
    token = os.environ.get("ROMEO_BRIDGE_TOKEN")
    if token:
        _bridge = ShortcutsBridge(
            token,
            host=os.environ.get("ROMEO_BRIDGE_HOST", "0.0.0.0"),
            port=int(os.environ.get("ROMEO_BRIDGE_PORT", "8765")),
        )
        _bridge.start()
    mcp.run()


if __name__ == "__main__":
    main()
