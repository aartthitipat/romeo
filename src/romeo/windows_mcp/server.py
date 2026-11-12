"""romeo-windows — MCP server that lets an agent see and control a Windows PC.

Run: ``romeo-windows`` (stdio). OpenJarvis starts it from configs/mcp_servers.json.
"""

from __future__ import annotations

import functools
import sys
import threading
from typing import Callable, Optional

from mcp.server.fastmcp import FastMCP, Image

from romeo.common.guard import ActionBlocked, guard
from romeo.common.safety import Risk, default_gate

DEVICE = "windows"
mcp = FastMCP("romeo-windows")

# Scale of the most recent screenshot; screenshot pixels * scale = screen pixels.
_state = {"scale": 1.0}


def safe(fn: Callable) -> Callable:
    """Turn safety refusals and runtime errors into readable tool results."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ActionBlocked as exc:
            return str(exc)
        except Exception as exc:  # report to the agent instead of crashing
            return f"error: {type(exc).__name__}: {exc}"

    return wrapper


def _active_title() -> str:
    from romeo.windows_mcp import uia

    return uia.focused_window_title()


def _to_screen(x: int, y: int, from_screenshot: bool) -> tuple[int, int]:
    if not from_screenshot:
        return x, y
    s = _state["scale"]
    return round(x * s), round(y * s)


# ---------------------------------------------------------------- observe ---


@mcp.tool()
@safe
def screenshot(monitor: int = 1, grid: bool = True):
    """Capture the screen. A red grid labels coordinates every 100px.
    Coordinates read from this image can be passed to click(..., from_screenshot=True)."""
    from romeo.windows_mcp import screen

    guard(DEVICE, "screenshot", Risk.READ, {"monitor": monitor},
          targets=[_active_title()])
    shot = screen.screenshot(monitor, grid)
    _state["scale"] = shot.scale
    return Image(data=shot.png, format="png")


@mcp.tool()
@safe
def list_windows() -> str:
    """List visible top-level windows with title, handle, pid and rectangle."""
    from romeo.windows_mcp import uia

    guard(DEVICE, "list_windows", Risk.READ, {})
    rows = uia.list_windows()
    return "\n".join(f"{w['title']} | pid={w['process_id']} | rect={w['rect']}" for w in rows)


@mcp.tool()
@safe
def get_ui_tree(window_title: Optional[str] = None, max_depth: int = 4) -> str:
    """Accessibility tree of a window (default: the active one). Each control shows
    its centre in real screen coordinates — click it with from_screenshot=False.
    Prefer this over screenshots: it is faster and more precise."""
    from romeo.windows_mcp import uia

    title = window_title or _active_title()
    guard(DEVICE, "get_ui_tree", Risk.READ, {"window": title}, targets=[title])
    name, tree = uia.ui_tree(window_title, max_depth=max_depth)
    return f"window: {name}\n{tree}"


@mcp.tool()
@safe
def find_element(name: str, control_type: Optional[str] = None,
                 window_title: Optional[str] = None) -> str:
    """Find a control by (partial) name, e.g. name='Save', control_type='Button'."""
    from romeo.windows_mcp import uia

    title = window_title or _active_title()
    guard(DEVICE, "find_element", Risk.READ, {"name": name}, targets=[title])
    return str(uia.find_element(name, control_type, window_title))


# -------------------------------------------------------------------- act ---


@mcp.tool()
@safe
def click(x: int, y: int, button: str = "left", clicks: int = 1,
          from_screenshot: bool = True) -> str:
    """Click at (x, y). from_screenshot=True means the coordinates come from the
    last screenshot image; use False for coordinates from get_ui_tree/find_element."""
    from romeo.windows_mcp import input as inp

    sx, sy = _to_screen(x, y, from_screenshot)
    guard(DEVICE, "click", Risk.ACT, {"x": sx, "y": sy, "button": button},
          targets=[_active_title()])
    inp.click(sx, sy, button=button, clicks=clicks)
    return f"clicked {button} x{clicks} at ({sx},{sy})"


@mcp.tool()
@safe
def double_click(x: int, y: int, from_screenshot: bool = True) -> str:
    """Double-click at (x, y)."""
    return click(x, y, clicks=2, from_screenshot=from_screenshot)


@mcp.tool()
@safe
def type_text(text: str, enter: bool = False) -> str:
    """Type text into the focused control (Thai supported). Never types passwords/OTP."""
    from romeo.windows_mcp import input as inp

    guard(DEVICE, "type_text", Risk.ACT, {"text": text}, text=text,
          targets=[_active_title()])
    inp.type_text(text, enter=enter)
    return f"typed {len(text)} chars" + (" + Enter" if enter else "")


@mcp.tool()
@safe
def hotkey(keys: list[str]) -> str:
    """Press a key combination, e.g. ["ctrl", "s"], ["alt", "tab"], ["win", "d"]."""
    from romeo.windows_mcp import input as inp

    guard(DEVICE, "hotkey", Risk.ACT, {"keys": keys}, targets=[_active_title()])
    inp.hotkey(*keys)
    return "pressed " + "+".join(keys)


@mcp.tool()
@safe
def scroll(amount: int, x: Optional[int] = None, y: Optional[int] = None) -> str:
    """Scroll the mouse wheel; positive = up, negative = down."""
    from romeo.windows_mcp import input as inp

    guard(DEVICE, "scroll", Risk.ACT, {"amount": amount}, targets=[_active_title()])
    inp.scroll(amount, x, y)
    return f"scrolled {amount}"


@mcp.tool()
@safe
def open_app(name_or_path: str) -> str:
    """Open an app, file, folder or URL (e.g. 'notepad', 'chrome', 'https://…')."""
    from romeo.windows_mcp import apps

    guard(DEVICE, "open_app", Risk.ACT, {"app": name_or_path}, targets=[name_or_path])
    apps.open_app(name_or_path)
    return f"opened {name_or_path}"


@mcp.tool()
@safe
def focus_window(title: str) -> str:
    """Bring a window whose title contains `title` to the front."""
    from romeo.windows_mcp import apps

    guard(DEVICE, "focus_window", Risk.ACT, {"title": title}, targets=[title])
    return "focused " + apps.focus_window(title)


@mcp.tool()
@safe
def close_window(title: str) -> str:
    """Close a window (asks the user first — unsaved work may be lost)."""
    from romeo.windows_mcp import apps

    guard(DEVICE, "close_window", Risk.SENSITIVE, {"title": title}, targets=[title])
    return "closed " + apps.close_window(title)


@mcp.tool()
@safe
def run_powershell(command: str, timeout: int = 60) -> str:
    """Run a PowerShell command. ALWAYS asks the user for approval first."""
    from romeo.windows_mcp import system

    guard(DEVICE, "run_powershell", Risk.SENSITIVE, {"command": command},
          command=command, targets=[command])
    return system.run_powershell(command, timeout)


@mcp.tool()
@safe
def system_control(action: str) -> str:
    """lock | sleep | shutdown | restart | cancel_shutdown | mute | volume_up | volume_down"""
    from romeo.windows_mcp import system

    if action not in system.SYSTEM_ACTIONS:
        return f"unknown action; choose one of {sorted(system.SYSTEM_ACTIONS)}"
    risk = Risk.ACT if action in ("mute", "volume_up", "volume_down", "lock",
                                  "cancel_shutdown") else Risk.SENSITIVE
    guard(DEVICE, "system_control", risk, {"action": action})
    return system.run_powershell(system.SYSTEM_ACTIONS[action])


# ------------------------------------------------------------ kill switch ---


def _hotkey_kill_switch() -> None:
    """Ctrl+Alt+Esc engages the kill switch for every Romeo process."""
    import ctypes
    from ctypes import wintypes

    MOD_ALT, MOD_CONTROL, VK_ESCAPE, WM_HOTKEY = 0x1, 0x2, 0x1B, 0x312
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, 1, MOD_ALT | MOD_CONTROL, VK_ESCAPE):
        return
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY:
            default_gate().kill_switch.engage("hotkey Ctrl+Alt+Esc")


def main() -> None:
    if sys.platform == "win32":
        threading.Thread(target=_hotkey_kill_switch, daemon=True).start()
    mcp.run()


if __name__ == "__main__":
    main()
