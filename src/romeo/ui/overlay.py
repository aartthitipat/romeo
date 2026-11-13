"""Siri-style floating bubble in the bottom-right corner of the Windows screen.

Appears when Romeo wakes, shows what it heard and its answer, then hides
itself a couple of seconds after going back to idle. Built with tkinter
(bundled with Python on Windows). `OverlayModel` holds all the logic so it
can be tested without a display.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from typing import Optional

from romeo.ui.events import EventHub

COLORS = {
    "idle": "#9ca3af", "awake": "#2f80ed", "listening": "#2f80ed", "follow_up": "#2f80ed",
    "thinking": "#8b5cf6", "speaking": "#10b981", "stopped": "#e5484d",
}
LABELS = {
    "idle": "", "awake": "ได้ยินแล้ว", "listening": "กำลังฟัง…", "follow_up": "พูดต่อได้เลย",
    "thinking": "กำลังคิด…", "speaking": "กำลังตอบ", "stopped": "หยุดฉุกเฉินแล้ว",
}
ACTIVE = {"awake", "listening", "thinking", "speaking", "follow_up", "stopped"}


def shorten(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class OverlayModel:
    hide_after_s: float = 2.5
    state: str = "idle"
    heard: str = ""
    reply: str = ""
    visible: bool = False
    _hide_at: Optional[float] = field(default=None, repr=False)

    @property
    def color(self) -> str:
        return COLORS.get(self.state, COLORS["idle"])

    @property
    def label(self) -> str:
        return LABELS.get(self.state, self.state)

    def apply(self, event: dict, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        kind = event.get("kind")
        if kind == "state":
            state = event.get("state", "idle")
            if state == "awake" and not self.visible:
                self.heard = self.reply = ""  # a new conversation
            self.state = state
            if state in ACTIVE:
                self.visible, self._hide_at = True, None
            elif self.visible:
                self._hide_at = now + self.hide_after_s
        elif kind == "heard":
            self.heard, self.reply = shorten(event.get("text", "")), ""
            self.visible, self._hide_at = True, None
        elif kind == "reply":
            self.reply = shorten(event.get("text", ""), 220)
            self.visible, self._hide_at = True, None
            if self.state == "idle":  # e.g. a Siri/web request: show, then fade
                self._hide_at = now + self.hide_after_s * 2

    def tick(self, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        if self._hide_at is not None and now >= self._hide_at:
            self.visible, self._hide_at = False, None


class Overlay:
    """tkinter window. Must run on the main thread (call `run()`)."""

    WIDTH, MARGIN, TASKBAR = 380, 24, 48
    BG, INK, MUTED = "#171a21", "#e8eaee", "#9aa1ad"

    def __init__(self, hub: EventHub) -> None:
        import tkinter as tk

        self.tk = tk
        self.model = OverlayModel()
        self.events = hub.subscribe()
        self.hub = hub
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.94)
        except tk.TclError:
            pass
        self.root.configure(bg=self.BG)

        family = "Leelawadee UI"
        wrap = self.WIDTH - 100
        body = tk.Frame(self.root, bg=self.BG, padx=16, pady=14)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, width=56, height=56, bg=self.BG, highlightthickness=0)
        self.canvas.pack(side="left", anchor="n")
        self.dot = self.canvas.create_oval(6, 6, 50, 50, fill=COLORS["idle"], outline="")
        text = tk.Frame(body, bg=self.BG, padx=12)
        text.pack(side="left", fill="both", expand=True)
        self.state_label = tk.Label(text, bg=self.BG, fg=self.MUTED, font=(family, 10), anchor="w")
        self.heard_label = tk.Label(text, bg=self.BG, fg=self.INK, font=(family, 11, "bold"),
                                    anchor="w", justify="left", wraplength=wrap)
        self.reply_label = tk.Label(text, bg=self.BG, fg=self.INK, font=(family, 11),
                                    anchor="w", justify="left", wraplength=wrap)
        for label in (self.state_label, self.heard_label, self.reply_label):
            label.pack(fill="x", anchor="w", pady=(0, 4))
        for widget in (self.root, body, text, self.canvas, self.state_label,
                       self.heard_label, self.reply_label):
            widget.bind("<Button-1>", lambda _e: self._hide())  # click to dismiss
        self._pulse = 0
        self._shown = False
        self._last_height = 0

    def _hide(self) -> None:
        self.model.visible = False
        self._shown = False
        self.root.withdraw()

    def _place(self) -> None:
        """Size to content and pin to the bottom-right corner above the taskbar."""
        self.root.update_idletasks()
        height = max(88, self.root.winfo_reqheight())
        if self._shown and height == self._last_height:
            return
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = sw - self.WIDTH - self.MARGIN
        y = sh - height - self.MARGIN - self.TASKBAR
        self.root.geometry(f"{self.WIDTH}x{height}+{x}+{y}")
        self._last_height = height

    def _render(self) -> None:
        m = self.model
        if not m.visible:
            if self._shown:
                self._hide()
            return
        self._pulse = (self._pulse + 1) % 20
        animated = m.state in ("listening", "follow_up", "thinking", "speaking", "awake")
        inset = 6 + (abs(10 - self._pulse) // 3 if animated else 0)
        self.canvas.coords(self.dot, inset, inset, 56 - inset, 56 - inset)
        self.canvas.itemconfig(self.dot, fill=m.color)
        self.state_label.config(text=m.label)
        self.heard_label.config(text=f"“{m.heard}”" if m.heard else "")
        self.reply_label.config(text=m.reply)
        self._place()
        if not self._shown:
            self.root.deiconify()
            self.root.lift()
            self._place()  # some window managers drop geometry set while hidden
            self._shown = True

    def _poll(self) -> None:
        try:
            while True:
                self.model.apply(self.events.get_nowait())
        except queue.Empty:
            pass
        self.model.tick()
        self._render()
        self.root.after(80, self._poll)

    def run(self) -> None:
        self.root.after(80, self._poll)
        try:
            self.root.mainloop()
        finally:
            self.hub.unsubscribe(self.events)

    def close(self) -> None:
        self.root.after(0, self.root.destroy)
