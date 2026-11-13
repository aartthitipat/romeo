"""The always-listening voice assistant — a state machine fed 80 ms frames.

IDLE ──VAD+wake word──► (confirm: STT keyword + speaker) ──► LISTENING
LISTENING ──silence──► THINKING (STT → runner → speak) ──► FOLLOW_UP
FOLLOW_UP ──speech within 6 s──► LISTENING   │   ──timeout──► IDLE
"""

from __future__ import annotations

import enum
import os
import re
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from romeo.common import audit
from romeo.voice.audio import RingBuffer, seconds_to_frames, to_wav
from romeo.voice.runner import CommandRunner
from romeo.voice.speaker import SpeakerVerifier
from romeo.voice.vad import VoiceActivity
from romeo.voice.wakeword import WakeDetector

SttFn = Callable[[bytes, Optional[str]], str]  # (wav, language) -> text


class State(str, enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    FOLLOW_UP = "follow_up"


@dataclass
class Timing:
    pre_roll_s: float = 2.0  # audio kept before the trigger (wake phrase)
    end_silence_s: float = 1.2  # silence that ends a command
    start_timeout_s: float = 4.0  # give up if no command starts
    max_command_s: float = 20.0
    follow_up_s: float = 6.0  # keep listening after a reply, no wake word needed


@dataclass
class Hooks:
    stt: SttFn
    speak: Callable[[str], None]
    chime: Callable[[str], None] = lambda kind: None  # "wake" | "done" | "reject"
    flush: Callable[[], None] = lambda: None  # drop mic audio captured while busy
    log: Callable[[str], None] = print
    event: Callable[[str, dict], None] = lambda kind, data: None  # UI updates


def _norm(text: str) -> str:
    return re.sub(r"[^\w฀-๿ ]+", " ", text.lower())


class VoiceAssistant:
    def __init__(self, detector: WakeDetector, vad: VoiceActivity, runner: CommandRunner,
                 hooks: Hooks, *, speaker: Optional[SpeakerVerifier] = None,
                 keywords: tuple[str, ...] = ("romeo",), verify_with_stt: Optional[bool] = None,
                 language: str = "th", timing: Optional[Timing] = None) -> None:
        self.detector, self.vad, self.runner, self.hooks = detector, vad, runner, hooks
        self.speaker = speaker
        self.keywords = tuple(k.lower() for k in keywords)
        self.verify_with_stt = (verify_with_stt if verify_with_stt is not None
                                else os.environ.get("ROMEO_WAKE_VERIFY_STT", "1") != "0")
        self.language = language
        self.t = timing or Timing()
        self.ring = RingBuffer(self.t.pre_roll_s)
        self._recent_speech: deque[bool] = deque(maxlen=seconds_to_frames(1.0))
        self.state = State.IDLE
        self._command: list[np.ndarray] = []
        self._heard_speech = False
        self._silence = 0
        self._waited = 0
        self.replies: list[str] = []

    # ------------------------------------------------------------ public ---
    def run(self, frames) -> None:
        for frame in frames:
            self.step(frame)

    def step(self, frame: np.ndarray) -> None:
        self.ring.append(frame)
        if self.state is State.IDLE:
            self._idle(frame)
        else:
            self._listening(frame)

    # ------------------------------------------------------------ states ---
    def _idle(self, frame: np.ndarray) -> None:
        # The wake model sees every frame (it keeps a streaming feature window, so
        # gaps would clip the start of "Hey"). Stage 0 VAD then acts as a gate:
        # a trigger only counts if a human voice was present in the last second,
        # which filters music/TV hits that are not speech.
        self._recent_speech.append(self.vad.is_speech(frame))
        event = self.detector.process(frame)
        if event is None:
            return
        if not any(self._recent_speech):
            audit.record("voice", "wake", {"score": round(event.score, 3)}, "reject",
                         note="no voice activity")
            self.hooks.event("wake_rejected", {"reason": "no voice activity"})
            return
        clip = self.ring.last(1.6)
        ok, why = self._confirm(clip)
        audit.record("voice", "wake", {"score": round(event.score, 3)},
                     "accept" if ok else "reject", note=why)
        if not ok:
            self.hooks.log(f"✗ wake rejected ({why})")
            self.hooks.event("wake_rejected", {"reason": why})
            self.hooks.chime("reject")
            return
        self.hooks.log(f"● awake (score {event.score:.2f}{', ' + why if why else ''})")
        self.hooks.event("state", {"state": "awake"})
        self.hooks.chime("wake")
        self._begin(State.LISTENING)

    def _confirm(self, clip: np.ndarray) -> tuple[bool, str]:
        notes = []
        if self.speaker is not None and self.speaker.enrolled:
            ok, score = self.speaker.verify(clip)
            notes.append(f"speaker {score:.2f}")
            if not ok:
                return False, "not the owner's voice: " + ", ".join(notes)
        if self.verify_with_stt:
            heard = _norm(self.hooks.stt(to_wav(clip), None))
            notes.append(f"heard {heard.strip()!r}")
            if not any(k in heard for k in self.keywords):
                return False, "speech-to-text did not hear the wake word: " + ", ".join(notes)
        return True, ", ".join(notes)

    def _begin(self, state: State) -> None:
        if state is not self.state or state is not State.IDLE:
            ui_state = state.value
            if state is State.IDLE and self.runner.kill_switch.engaged():
                ui_state = "stopped"
            self.hooks.event("state", {"state": ui_state})
        self.state = state
        self._command = []
        self._heard_speech = False
        self._silence = 0
        self._waited = 0

    def _listening(self, frame: np.ndarray) -> None:
        speech = self.vad.is_speech(frame)
        if not self._heard_speech:
            self._waited += 1
            limit = self.t.follow_up_s if self.state is State.FOLLOW_UP else self.t.start_timeout_s
            if speech:
                self._heard_speech = True
                self._command = [self.ring.last(0.32)]  # include the onset
                return
            if self._waited >= seconds_to_frames(limit):
                self.hooks.log("○ idle")
                self._begin(State.IDLE)
                self.detector.reset()
            return

        self._command.append(frame)
        self._silence = 0 if speech else self._silence + 1
        too_long = len(self._command) >= seconds_to_frames(self.t.max_command_s)
        if self._silence >= seconds_to_frames(self.t.end_silence_s) or too_long:
            self._think(np.concatenate(self._command))

    def _think(self, audio: np.ndarray) -> None:
        text = self.hooks.stt(to_wav(audio), self.language).strip()
        self.hooks.log(f"🗣  {text}")
        if not text:
            self._begin(State.FOLLOW_UP)
            return
        reply = self.runner.handle(text, source="voice")
        self.replies.append(reply)
        self.hooks.log(f"🤖 {reply}")
        self.hooks.event("state", {"state": "speaking"})
        self.hooks.speak(reply)
        self.hooks.chime("done")
        self.hooks.flush()
        self.ring.clear()
        self.detector.reset()
        stopped = self.runner.kill_switch.engaged()
        self._begin(State.IDLE if stopped else State.FOLLOW_UP)
