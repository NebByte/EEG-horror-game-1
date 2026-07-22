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


def _periodogram(signal: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    n = signal.shape[-1]
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    psd = np.abs(np.fft.rfft(signal, axis=-1)) ** 2
    psd = psd.mean(axis=0) if psd.ndim > 1 else psd
    return freqs, psd


def _welch_psd(signal: np.ndarray, fs: float, seg: int | None = None,
               overlap: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """Welch's method: average periodograms over overlapping Hann-windowed
    segments. Lower variance than a single periodogram — better for real signals.
    Falls back to a plain periodogram when the window is too short to segment."""
    n = signal.shape[-1]
    seg = seg or int(fs)  # ~1s segments by default
    if n < 2 * seg:
        return _periodogram(signal, fs)
    step = max(1, int(seg * (1.0 - overlap)))
    win = np.hanning(seg)
    win_norm = (win ** 2).sum()
    starts = range(0, n - seg + 1, step)
    acc = None
    count = 0
    for s in starts:
        segw = signal[..., s : s + seg] * win
        spec = np.abs(np.fft.rfft(segw, axis=-1)) ** 2 / win_norm
        spec = spec.mean(axis=0) if spec.ndim > 1 else spec
        acc = spec if acc is None else acc + spec
        count += 1
    freqs = np.fft.rfftfreq(seg, d=1.0 / fs)
    return freqs, (acc / max(1, count))


def _relative_band_powers(signal: np.ndarray, fs: float, method: str = "welch") -> dict[str, float]:
    n = signal.shape[-1]
    if n < 2:
        return {b: 0.0 for b in BANDS}
    signal = signal - signal.mean(axis=-1, keepdims=True)
    freqs, psd = (_welch_psd if method == "welch" else _periodogram)(signal, fs)

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
