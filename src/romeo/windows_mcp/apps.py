"""Launch, focus and close applications."""

from __future__ import annotations

import subprocess
import time


def open_app(name_or_path: str) -> None:
    """Open by path/URL/registered name (e.g. 'notepad', 'chrome', 'ms-settings:')."""
    # `start` resolves App Paths, URLs and protocol handlers like the Run box.
    subprocess.Popen(["cmd", "/c", "start", "", name_or_path], shell=False)
    time.sleep(1.0)


def focus_window(title: str) -> str:
    from pywinauto import Desktop

    win = Desktop(backend="uia").window(title_re=f".*{title}.*", visible_only=True)
    w = win.wrapper_object()
    if w.is_minimized():
        w.restore()
    w.set_focus()
    return w.window_text()


def close_window(title: str) -> str:
    from pywinauto import Desktop

    w = Desktop(backend="uia").window(title_re=f".*{title}.*").wrapper_object()
    text = w.window_text()
    w.close()
    return text
