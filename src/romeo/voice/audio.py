"""Microphone streaming, a rolling pre-roll buffer and small audio helpers.

Audio is 16 kHz mono int16 in 80 ms frames (1280 samples) — the frame size
openWakeWord expects.
"""

from __future__ import annotations

import io
import queue
import wave
from collections import deque
from typing import Iterator, Optional

import numpy as np

SAMPLE_RATE = 16_000
FRAME = 1280  # 80 ms
FRAME_SECONDS = FRAME / SAMPLE_RATE


def seconds_to_frames(seconds: float) -> int:
    return max(1, round(seconds / FRAME_SECONDS))


class RingBuffer:
    """Keeps the last `seconds` of audio so speech before a trigger is not lost."""

    def __init__(self, seconds: float = 2.0) -> None:
        self._frames: deque[np.ndarray] = deque(maxlen=seconds_to_frames(seconds))

    def append(self, frame: np.ndarray) -> None:
        self._frames.append(frame)

    def last(self, seconds: Optional[float] = None) -> np.ndarray:
        frames = list(self._frames)
        if seconds is not None:
            frames = frames[-seconds_to_frames(seconds):]
        if not frames:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(frames)

    def clear(self) -> None:
        self._frames.clear()


def to_wav(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(np.asarray(samples, dtype=np.int16).tobytes())
    return buf.getvalue()


def rms(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))


def beep(freq: float = 880.0, seconds: float = 0.12, volume: float = 0.3) -> np.ndarray:
    t = np.linspace(0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    fade = np.minimum(1.0, np.minimum(t, seconds - t) / 0.01)
    return (np.sin(2 * np.pi * freq * t) * fade * volume * 32767).astype(np.int16)


def play(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    try:
        import sounddevice as sd

        sd.play(samples, sample_rate)
        sd.wait()
    except Exception:
        pass  # sound is a nicety; never break the assistant over it


class MicStream:
    """Default microphone as an iterator of 80 ms int16 frames."""

    def __init__(self, device: Optional[int | str] = None) -> None:
        self.device = device
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=500)
        self._stream = None

    def __enter__(self) -> "MicStream":
        import sounddevice as sd

        def callback(indata, _frames, _time, _status) -> None:
            try:
                self._q.put_nowait(indata[:, 0].copy())
            except queue.Full:
                pass

        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                      blocksize=FRAME, device=self.device, callback=callback)
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()

    def flush(self) -> None:
        """Drop audio captured while Romeo was thinking/speaking (avoids self-trigger)."""
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def __iter__(self) -> Iterator[np.ndarray]:
        while True:
            yield self._q.get()

    def record(self, seconds: float) -> np.ndarray:
        frames = [self._q.get() for _ in range(seconds_to_frames(seconds))]
        return np.concatenate(frames)
