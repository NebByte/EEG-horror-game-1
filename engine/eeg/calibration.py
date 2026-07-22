"""Per-player calibration — center affect on *this* player's resting baseline.

Two people have different resting EEG; without calibration a naturally high-beta
person reads as permanently "aroused". We record a short resting baseline (eyes
open/closed) and express live affect *relative* to it, so neutral means neutral
for that player. This is the front half of ROADMAP B1.
"""
from __future__ import annotations

from engine.eeg.affect import affect_from_bands
from engine.eeg.bands import band_powers
from engine.schemas import AffectState, EEGChunk


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_baseline(chunks: list[EEGChunk]) -> AffectState:
    """Average the resting windows into a baseline AffectState."""
    if not chunks:
        return AffectState(arousal=0.2, relaxation=0.6)
    affects = [affect_from_bands(band_powers(c)) for c in chunks]
    n = len(affects)
    avg = {k: sum(getattr(a, k) for a in affects) / n
           for k in ("fear", "stress", "arousal", "engagement", "relaxation", "valence")}
    return AffectState(**{k: round(v, 4) for k, v in avg.items()})


def apply_baseline(raw: AffectState, baseline: AffectState | None) -> AffectState:
    """Re-center a live affect estimate against the player's resting baseline."""
    if baseline is None:
        return raw
    return AffectState(
        fear=round(_clamp(raw.fear - baseline.fear), 4),
        stress=round(_clamp(raw.stress - baseline.stress + 0.1), 4),
        arousal=round(_clamp(raw.arousal - baseline.arousal + 0.2), 4),
        engagement=round(_clamp(raw.engagement - baseline.engagement + 0.3), 4),
        relaxation=round(_clamp(raw.relaxation - baseline.relaxation + 0.5), 4),
        valence=round(max(-1.0, min(1.0, raw.valence - baseline.valence)), 4),
    )
