"""Director behaviour: mood selection, tension smoothing, and the safety rail."""
from __future__ import annotations

from engine.experience.orchestrator import Orchestrator
from engine.schemas import AffectState, SeedProfile


def _seed() -> SeedProfile:
    return SeedProfile(intensity_preference=0.6)


def test_calm_is_unease_intense_is_panic():
    d1 = Orchestrator(_seed()).step(AffectState(fear=0.05, stress=0.05, arousal=0.1), None)
    assert d1.mood == "unease"

    d2 = Orchestrator(_seed()).step(AffectState(fear=0.95, stress=0.7, arousal=0.9), None)
    assert d2.mood in ("dread", "panic")


def test_intensity_is_smoothed_not_instant():
    o = Orchestrator(_seed())
    terror = AffectState(fear=1.0, stress=0.8, arousal=1.0)
    d = o.step(terror, None)
    # One step must not jump straight to full intensity (tension curve smoothing).
    assert d.intensity < 0.6
    # ...but sustained terror keeps climbing.
    for _ in range(15):
        d = o.step(terror, None)
    assert d.intensity > 0.7


def test_safety_backoff_forces_relief():
    o = Orchestrator(_seed())
    d = None
    # Sustained extreme stress must eventually trip the safety back-off.
    for _ in range(20):
        d = o.step(AffectState(fear=1.0, stress=1.0, arousal=1.0), None)
    assert d.safety_backoff is True
    assert d.mood == "relief"
    assert d.intensity <= 0.25
