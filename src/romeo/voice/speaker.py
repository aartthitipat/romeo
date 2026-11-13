"""Stage 3 — is this the owner's voice? (like "Personalized Hey Siri")

`romeo voice enroll` records the owner saying the wake phrase a few times and
stores the average speaker embedding. Each wake event is compared to it with
cosine similarity. Embeddings come from SpeechBrain's ECAPA-TDNN model.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from romeo.common.safety import romeo_home
from romeo.voice.audio import SAMPLE_RATE

Embedder = Callable[[np.ndarray], np.ndarray]


def ecapa_embedder() -> Embedder:
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    model = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(romeo_home() / "voice" / "ecapa"),
    )

    def embed(samples: np.ndarray) -> np.ndarray:
        wav = torch.from_numpy(samples.astype(np.float32) / 32768.0).unsqueeze(0)
        return model.encode_batch(wav).squeeze().detach().cpu().numpy()

    return embed


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n else v


class SpeakerVerifier:
    def __init__(self, embedder: Optional[Embedder] = None, path: Optional[Path] = None,
                 threshold: float | None = None) -> None:
        self._embedder = embedder
        self.path = path or romeo_home() / "voice" / "owner.npy"
        self.threshold = float(threshold if threshold is not None
                               else os.environ.get("ROMEO_SPEAKER_THRESHOLD", 0.55))
        self._owner: Optional[np.ndarray] = np.load(self.path) if self.path.exists() else None

    @property
    def enrolled(self) -> bool:
        return self._owner is not None

    def _embed(self, samples: np.ndarray) -> np.ndarray:
        if self._embedder is None:
            self._embedder = ecapa_embedder()
        return _unit(np.asarray(self._embedder(samples), dtype=np.float32))

    def enroll(self, clips: Sequence[np.ndarray]) -> None:
        if len(clips) < 3:
            raise ValueError("record at least 3 clips of the wake phrase")
        for clip in clips:
            if clip.size < SAMPLE_RATE // 2:
                raise ValueError("each clip must be at least 0.5 s long")
        owner = _unit(np.mean([self._embed(c) for c in clips], axis=0))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.save(self.path, owner)
        self._owner = owner

    def score(self, samples: np.ndarray) -> float:
        if self._owner is None:
            raise RuntimeError("no owner enrolled — run `romeo voice enroll`")
        return float(np.dot(self._embed(samples), self._owner))

    def verify(self, samples: np.ndarray) -> tuple[bool, Optional[float]]:
        """(accepted, score). Not enrolled → accepted with score None."""
        if self._owner is None:
            return True, None
        s = self.score(samples)
        return s >= self.threshold, s
