"""Welch PSD, artifact rejection, calibration, and CV/EEG fusion."""
from __future__ import annotations

from engine.eeg import EEGSimulator, infer_affect
from engine.eeg.affect import fuse_cv
from engine.eeg.artifacts import assess_quality
from engine.eeg.bands import band_powers
from engine.eeg.calibration import apply_baseline, compute_baseline
from engine.schemas import CvAffect, EEGChunk, EEGSample


def test_welch_bandpowers_sum_to_one():
    sim = EEGSimulator(seed=3)
    bp = band_powers(sim.window(2.0, arousal=0.6))
    total = bp.delta + bp.theta + bp.alpha + bp.beta + bp.gamma
    assert 0.98 <= total <= 1.02  # relative powers normalise


def test_clean_window_is_high_quality():
    sim = EEGSimulator(seed=4)
    q = assess_quality(sim.window(2.0, arousal=0.5), poor_signal=0)
    assert q.ok and q.confidence > 0.5 and not q.motion


def test_motion_spike_flagged_as_artifact():
    # A window with a giant deflection = motion/clipping -> rejected.
    samples = [EEGSample(t=i / 256, channels=[0.0]) for i in range(256)]
    samples[128].channels = [500.0]  # 500 uV spike
    chunk = EEGChunk(sample_rate_hz=256, channel_names=["FP1"], samples=samples)
    q = assess_quality(chunk)
    assert q.motion  # a 500 uV spike is unambiguous motion/clipping
    assert not q.ok


def test_poor_signal_lowers_confidence():
    sim = EEGSimulator(seed=5)
    good = assess_quality(sim.window(1.0, arousal=0.5), poor_signal=0)
    bad = assess_quality(sim.window(1.0, arousal=0.5), poor_signal=180)
    assert bad.confidence < good.confidence


def test_calibration_recenters_resting_player():
    sim = EEGSimulator(seed=6)
    # A player whose "resting" state is already fairly aroused.
    resting = [sim.window(1.0, arousal=0.6) for _ in range(4)]
    baseline = compute_baseline(resting)
    raw = infer_affect(sim.window(1.0, arousal=0.6))
    cal = apply_baseline(raw, baseline)
    # Calibrated arousal at the resting level should be near neutral, below raw.
    assert cal.arousal < raw.arousal


def test_cv_fusion_boosts_fear_on_startle():
    base = infer_affect(EEGSimulator(seed=7).window(1.0, arousal=0.3))
    fused = fuse_cv(base, CvAffect(surprise=1.0, fear=0.9, arousal=0.9, confidence=1.0))
    assert fused.fear > base.fear
    assert fuse_cv(base, CvAffect(confidence=0.0)).fear == base.fear
