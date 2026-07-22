"""Turn an EEGChunk into relative band powers via an FFT periodogram.

Deliberately minimal (numpy only, no scipy): a plain periodogram, not Welch.
Good enough for a monotonic prototype signal; the ROADMAP tracks the upgrade to
Welch + windowing + artifact rejection for real hardware.
"""
from __future__ import annotations

import numpy as np

from engine.schemas import BandPowers, EEGChunk

# Canonical EEG band edges in Hz.
BANDS: dict[str, tuple[float, float]] = {
    "delta": (0.5, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 45.0),
}


def _chunk_to_matrix(chunk: EEGChunk) -> np.ndarray:
    """(n_channels, n_samples) matrix from a chunk, or empty if no samples."""
    if not chunk.samples:
        return np.empty((0, 0))
    rows = [s.channels for s in chunk.samples]
    return np.asarray(rows, dtype=float).T  # channels on axis 0


def _relative_band_powers(signal: np.ndarray, fs: float) -> dict[str, float]:
    n = signal.shape[-1]
    if n < 2:
        return {b: 0.0 for b in BANDS}
    signal = signal - signal.mean(axis=-1, keepdims=True)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    psd = np.abs(np.fft.rfft(signal, axis=-1)) ** 2  # (channels, freqs)
    psd = psd.mean(axis=0) if psd.ndim > 1 else psd    # average across channels

    total = psd[(freqs >= 0.5) & (freqs <= 45.0)].sum()
    if total <= 0:
        return {b: 0.0 for b in BANDS}

    out: dict[str, float] = {}
    for band, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        out[band] = float(psd[mask].sum() / total)
    return out


def frontal_alpha_asymmetry(chunk: EEGChunk) -> float:
    """ln(alpha_right) - ln(alpha_left) on the two frontal channels.

    Positive => relatively more left-frontal activity (approach/positive
    valence); negative => right-frontal (withdrawal). Falls back to 0 when the
    frontal channels can't be identified.
    """
    names = [n.upper() for n in chunk.channel_names]
    mat = _chunk_to_matrix(chunk)
    if mat.size == 0:
        return 0.0

    def alpha_of(idx: int) -> float:
        bp = _relative_band_powers(mat[idx : idx + 1], chunk.sample_rate_hz)
        return bp["alpha"]

    left = next((i for i, n in enumerate(names) if n in ("AF3", "F3", "FP1")), 0)
    right = next((i for i, n in enumerate(names) if n in ("AF4", "F4", "FP2")), min(1, mat.shape[0] - 1))
    al, ar = alpha_of(left), alpha_of(right)
    eps = 1e-6
    return float(np.log(ar + eps) - np.log(al + eps))


def band_powers(chunk: EEGChunk) -> BandPowers:
    mat = _chunk_to_matrix(chunk)
    rel = _relative_band_powers(mat, chunk.sample_rate_hz) if mat.size else {b: 0.0 for b in BANDS}
    return BandPowers(**rel, frontal_alpha_asymmetry=frontal_alpha_asymmetry(chunk))
