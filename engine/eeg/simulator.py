"""A synthetic EEG source biased toward a target arousal.

Lets the whole system be demoed and tested with no hardware: crank the target
arousal up and the affect model should report rising fear/stress.
"""
from __future__ import annotations

import math

import numpy as np

from engine.schemas import EEGChunk, EEGSample

# Representative center frequency (Hz) and baseline amplitude per band.
_BAND_CENTERS = {"delta": 2.0, "theta": 6.0, "alpha": 10.0, "beta": 20.0, "gamma": 38.0}


class EEGSimulator:
    def __init__(
        self,
        sample_rate_hz: float = 256.0,
        channel_names: list[str] | None = None,
        seed: int | None = None,
    ) -> None:
        self.fs = sample_rate_hz
        self.channel_names = channel_names or ["AF3", "AF4", "TP9", "TP10"]
        self._t = 0.0
        self._rng = np.random.default_rng(seed)

    def _band_amplitudes(self, arousal: float) -> dict[str, float]:
        """Higher arousal -> more beta/gamma, less alpha."""
        a = float(np.clip(arousal, 0.0, 1.0))
        return {
            "delta": 1.0 - 0.3 * a,
            "theta": 0.8 + 0.3 * a,
            "alpha": 1.2 * (1.0 - 0.8 * a),
            "beta": 0.4 + 1.6 * a,
            "gamma": 0.2 + 1.0 * a,
        }

    def window(self, seconds: float, arousal: float = 0.5, valence: float = 0.0) -> EEGChunk:
        """Generate `seconds` of synthetic multi-channel EEG.

        `valence` in [-1, 1] tilts the frontal alpha asymmetry (negative =>
        right-frontal dominance => the affect model reads withdrawal/fear).
        """
        n = max(2, int(self.fs * seconds))
        amps = self._band_amplitudes(arousal)
        t = self._t + np.arange(n) / self.fs
        samples: list[EEGSample] = []

        for i in range(n):
            channels: list[float] = []
            for ch_idx, name in enumerate(self.channel_names):
                val = 0.0
                for band, center in _BAND_CENTERS.items():
                    amp = amps[band]
                    # Skew frontal alpha left/right per valence.
                    if band == "alpha" and name.upper() in ("AF3", "AF4", "F3", "F4"):
                        is_left = name.upper() in ("AF3", "F3")
                        tilt = 1.0 - 0.5 * valence if is_left else 1.0 + 0.5 * valence
                        amp *= tilt
                    phase = self._rng.uniform(0, 2 * math.pi) if i == 0 else 0.0
                    val += amp * math.sin(2 * math.pi * center * t[i] + ch_idx * 0.3 + phase)
                val += self._rng.normal(0, 0.15)  # sensor noise
                channels.append(round(float(val), 4))
            samples.append(EEGSample(t=round(float(t[i]), 5), channels=channels))

        self._t = float(t[-1] + 1.0 / self.fs)
        return EEGChunk(sample_rate_hz=self.fs, channel_names=self.channel_names, samples=samples)
