"""Stage 0 — is anyone speaking? (plays the role of Siri's low-power always-on chip)

Uses the Silero VAD model bundled with openWakeWord; falls back to a simple
energy threshold if it is unavailable.
"""

from __future__ import annotations

import os

import numpy as np

from romeo.voice.audio import rms


class VoiceActivity:
    def __init__(self, threshold: float | None = None, energy_threshold: float = 500.0) -> None:
        self.threshold = float(threshold if threshold is not None
                               else os.environ.get("ROMEO_VAD_THRESHOLD", 0.5))
        self.energy_threshold = energy_threshold
        self._vad = None
        try:
            from openwakeword.vad import VAD

            self._vad = VAD()
        except Exception:
            self._vad = None

    @property
    def backend(self) -> str:
        return "silero" if self._vad is not None else "energy"

    def probability(self, frame: np.ndarray) -> float:
        if self._vad is not None:
            try:
                return float(self._vad.predict(frame, frame_size=480))
            except Exception:
                self._vad = None
        return min(1.0, rms(frame) / (2 * self.energy_threshold))

    def is_speech(self, frame: np.ndarray) -> bool:
        return self.probability(frame) >= self.threshold
