"""Stages 1–2 — wake-word detection modelled on Siri's two-pass design.

Stage 1: a small openWakeWord model scores every 80 ms frame; a loose
threshold flags *candidates* so real wake words are rarely missed.
Stage 2: a candidate only fires when several recent frames clear a stricter
threshold. (Speech-to-text confirmation and speaker verification happen in
assistant.py, because they need the buffered audio and other models.)
"""

from __future__ import annotations

import os
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from romeo.common.safety import romeo_home
from romeo.voice.audio import seconds_to_frames

Scorer = Callable[[np.ndarray], float]

FALLBACK_MODEL = "hey_jarvis"  # ships with openWakeWord; used until hey_romeo is trained


def default_model() -> str:
    env = os.environ.get("ROMEO_WAKE_MODEL")
    if env:
        return env
    custom = romeo_home() / "voice" / "hey_romeo.onnx"
    return str(custom) if custom.exists() else FALLBACK_MODEL


def keywords_for(model: str) -> tuple[str, ...]:
    """Words speech-to-text must hear for stage-2 confirmation, e.g. 'romeo'."""
    stem = Path(model).stem.lower()
    stem = re.sub(r"_v?\d+(\.\d+)*$", "", stem)
    word = stem.removeprefix("hey_").replace("_", " ")
    thai = {"romeo": ("โรมิโอ", "โรเมโอ"), "jarvis": ("จาร์วิส", "จาวิส")}
    return (word, *thai.get(word, ()))


def resolve_model_path(name_or_path: str) -> str:
    if Path(name_or_path).exists():
        return str(Path(name_or_path).resolve())
    import openwakeword

    def find() -> Optional[str]:
        # openWakeWord 0.6 lists .tflite paths by default; Romeo always runs ONNX.
        try:
            paths = openwakeword.get_pretrained_model_paths("onnx")
        except TypeError:  # 0.4 takes no argument
            paths = openwakeword.get_pretrained_model_paths()
        for p in paths:
            onnx = str(Path(p).with_suffix(".onnx"))
            if Path(p).stem.startswith(name_or_path):
                return onnx
        return None

    found = find()
    if found is None or not Path(found).exists():
        try:  # openWakeWord >= 0.5 downloads its models on demand
            from openwakeword.utils import download_models

            download_models([name_or_path])
        except Exception:
            pass
        found = find()
    if found is None:
        raise FileNotFoundError(f"wake-word model not found: {name_or_path}")
    return found


def openwakeword_scorer(model: str) -> Scorer:
    """Load an openWakeWord model (works with both the 0.4 and 0.6 APIs)."""
    from openwakeword.model import Model

    path = resolve_model_path(model)
    try:
        oww = Model(wakeword_models=[path], inference_framework="onnx")
    except TypeError:
        oww = Model(wakeword_model_paths=[path])

    def score(frame: np.ndarray) -> float:
        prediction = oww.predict(frame)
        return float(max(prediction.values())) if prediction else 0.0

    score.reset = getattr(oww, "reset", lambda: None)  # type: ignore[attr-defined]
    return score


@dataclass
class WakeEvent:
    score: float
    frame_index: int


class WakeDetector:
    def __init__(
        self,
        scorer: Scorer,
        *,
        candidate_threshold: float | None = None,
        confirm_threshold: float | None = None,
        confirm_frames: int = 2,
        window_seconds: float = 0.5,
        cooldown_seconds: float = 2.0,
    ) -> None:
        self.scorer = scorer
        self.candidate_threshold = float(candidate_threshold if candidate_threshold is not None
                                         else os.environ.get("ROMEO_WAKE_CANDIDATE", 0.5))
        self.confirm_threshold = float(confirm_threshold if confirm_threshold is not None
                                       else os.environ.get("ROMEO_WAKE_THRESHOLD", 0.7))
        self.confirm_frames = confirm_frames
        self._recent: deque[float] = deque(maxlen=seconds_to_frames(window_seconds))
        self._cooldown = seconds_to_frames(cooldown_seconds)
        self._cooldown_left = 0
        self._index = 0
        self.last_score = 0.0

    def reset(self) -> None:
        self._recent.clear()
        reset = getattr(self.scorer, "reset", None)
        if callable(reset):
            reset()

    def process(self, frame: np.ndarray) -> Optional[WakeEvent]:
        self._index += 1
        score = self.scorer(frame)
        self.last_score = score
        if self._cooldown_left > 0:
            self._cooldown_left -= 1
            return None
        self._recent.append(score)
        if score < self.candidate_threshold:  # stage 1: not even a candidate
            return None
        strong = sum(1 for s in self._recent if s >= self.confirm_threshold)
        if strong >= self.confirm_frames:  # stage 2: confirmed by several frames
            self._cooldown_left = self._cooldown
            peak = max(self._recent)
            self.reset()
            return WakeEvent(peak, self._index)
        return None
