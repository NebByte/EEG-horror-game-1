"""Artifact rejection & signal-quality gating for EEG windows.

Real EEG (especially a single forehead electrode like the MindLink) is full of
non-brain artifacts: eye blinks (large slow deflections), EMG/muscle tension
(excess high-frequency power), and motion (clipping / huge amplitude). We flag
these so the director can down-weight or skip bad windows (confidence-aware
fusion) rather than treating noise as fear.
"""
from __future__ import annotations

import numpy as np

from engine.eeg.bands import BANDS, _relative_band_powers
from engine.schemas import EEGChunk, SignalQuality

# Thresholds in microvolts / relative power. Tuned for a forehead dry electrode.
BLINK_UV = 100.0     # a big slow deflection above this looks like a blink
MOTION_UV = 250.0    # clipping / gross movement
EMG_HIGH_FREQ = 0.72  # beta+gamma fraction above this suggests muscle tension
                      # (genuine high arousal is high-freq too — keep this strict)


def _matrix(chunk: EEGChunk) -> np.ndarray:
    if not chunk.samples:
        return np.empty((0, 0))
    return np.asarray([s.channels for s in chunk.samples], dtype=float).T


def assess_quality(chunk: EEGChunk, poor_signal: int = 0) -> SignalQuality:
    mat = _matrix(chunk)
    if mat.size == 0:
        return SignalQuality(poor_signal=poor_signal, ok=False, confidence=0.0)

    centered = mat - mat.mean(axis=-1, keepdims=True)
    peak = float(np.abs(centered).max())

    motion = peak > MOTION_UV
    blink = (not motion) and peak > BLINK_UV

    bp = _relative_band_powers(mat, chunk.sample_rate_hz)
    high_freq = bp["beta"] + bp["gamma"]
    emg = high_freq > EMG_HIGH_FREQ

    # MindLink poor_signal: 0 good .. 200 off-head. Clamp first so an out-of-range
    # caller value can't push confidence above 1.0 (violating the contract).
    poor_signal = max(0, min(200, poor_signal))
    ps_conf = 1.0 - poor_signal / 200.0
    conf = ps_conf
    if motion:
        conf *= 0.0
    elif blink:
        conf *= 0.4
    elif emg:
        conf *= 0.6

    ok = conf > 0.3 and not motion
    return SignalQuality(poor_signal=poor_signal, ok=ok, blink=blink,
                         emg=emg, motion=motion, confidence=round(conf, 3))


def is_artifact(chunk: EEGChunk, poor_signal: int = 0) -> bool:
    return not assess_quality(chunk, poor_signal).ok
