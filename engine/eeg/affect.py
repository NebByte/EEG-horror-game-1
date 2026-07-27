"""Map band powers to an AffectState with transparent, tunable heuristics.

This is intentionally a **white-box** model. Each line names its EEG correlate
so the behaviour is explainable and easy to tune; it also pins down the exact
interface (`EEGChunk -> AffectState`) a trained classifier must later satisfy.
"""
from __future__ import annotations

from engine.eeg.bands import band_powers
from engine.schemas import AffectState, BandPowers, CvAffect, EEGChunk


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def affect_from_bands(bp: BandPowers) -> AffectState:
    # No signal (empty/degenerate window) => neutral, never spuriously aroused.
    if (bp.delta + bp.theta + bp.alpha + bp.beta + bp.gamma) <= 1e-9:
        return AffectState()

    # Arousal: beta/gamma up, alpha down (cortical activation).
    arousal = _clamp(1.6 * (bp.beta + bp.gamma) + 0.4 * (0.3 - bp.alpha))

    # Relaxation: high alpha, low beta (the classic "alpha state").
    relaxation = _clamp(2.0 * bp.alpha - 0.8 * bp.beta)

    # Engagement: beta / (alpha + theta) — a well-known engagement index.
    engagement = _clamp((bp.beta) / (bp.alpha + bp.theta + 1e-6) * 0.6)

    # Valence from frontal alpha asymmetry: right-frontal (negative FAA) =>
    # withdrawal/negative affect.
    valence = _clamp(bp.frontal_alpha_asymmetry, -1.0, 1.0)

    # Stress: high beta + high theta (vigilance/tension), penalised by alpha.
    stress = _clamp(1.3 * bp.beta + 0.7 * bp.theta - 0.6 * bp.alpha)

    # Fear: negatively-valenced high arousal. Withdrawal amplifies it.
    withdrawal = _clamp(-valence)  # 0 when approach, up to 1 when withdrawn
    fear = _clamp(0.6 * arousal + 0.5 * withdrawal + 0.2 * stress - 0.3 * relaxation)

    return AffectState(
        fear=round(fear, 4),
        stress=round(stress, 4),
        arousal=round(arousal, 4),
        engagement=round(engagement, 4),
        relaxation=round(relaxation, 4),
        valence=round(valence, 4),
    )


def infer_affect(chunk: EEGChunk) -> AffectState:
    """Public entry point: an EEG window in, an affect estimate out."""
    return affect_from_bands(band_powers(chunk))


def fuse_cv(eeg: AffectState, cv: CvAffect | None) -> AffectState:
    """Fuse a computer-vision (webcam) affect estimate into the EEG affect.

    A second modality that mainly sharpens arousal/fear and catches startles.
    Weighted by the CV confidence (0 => EEG only)."""
    if cv is None or cv.confidence <= 0:
        return eeg
    w = 0.4 * _clamp(cv.confidence)
    startle = _clamp(cv.surprise)
    return AffectState(
        fear=round(_clamp(eeg.fear * (1 - w) + max(cv.fear, 0.7 * startle) * w + 0.15 * startle), 4),
        stress=round(_clamp(eeg.stress * (1 - 0.5 * w) + cv.fear * 0.5 * w), 4),
        arousal=round(_clamp(eeg.arousal * (1 - w) + cv.arousal * w + 0.2 * startle), 4),
        engagement=eeg.engagement,
        relaxation=round(_clamp(eeg.relaxation * (1 - w)), 4),
        valence=round(max(-1.0, min(1.0, eeg.valence * (1 - w) + cv.valence * w)), 4),
    )
