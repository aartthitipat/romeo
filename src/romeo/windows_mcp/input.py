"""Mouse/keyboard input. Thai and other non-ASCII text is pasted via clipboard."""

from __future__ import annotations

import time


def _pg():
    import pyautogui

    pyautogui.FAILSAFE = True  # slam mouse to a corner to abort
    pyautogui.PAUSE = 0.05
    return pyautogui


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    _pg().click(x=x, y=y, button=button, clicks=clicks, interval=0.08)


def move(x: int, y: int) -> None:
    _pg().moveTo(x, y, duration=0.1)


def scroll(amount: int, x: int | None = None, y: int | None = None) -> None:
    _pg().scroll(amount, x=x, y=y)


def hotkey(*keys: str) -> None:
    _pg().hotkey(*keys)


def type_text(text: str, enter: bool = False) -> None:
    pg = _pg()
    if text.isascii():
        pg.write(text, interval=0.01)
    else:
        import pyperclip

        previous = pyperclip.paste()
        pyperclip.copy(text)
        pg.hotkey("ctrl", "v")
        time.sleep(0.1)
        pyperclip.copy(previous)
    if enter:
        pg.press("enter")
