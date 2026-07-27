"""The affect model should be monotonic in the obvious way: more simulated
arousal -> more fear/arousal, less relaxation."""
from __future__ import annotations

from engine.eeg import EEGSimulator, infer_affect


def test_affect_ranges_are_bounded():
    sim = EEGSimulator(seed=1)
    a = infer_affect(sim.window(2.0, arousal=0.5))
    for k in ("fear", "stress", "arousal", "engagement", "relaxation"):
        assert 0.0 <= getattr(a, k) <= 1.0
    assert -1.0 <= a.valence <= 1.0


def test_fear_rises_with_arousal():
    sim = EEGSimulator(seed=2)
    calm = infer_affect(sim.window(2.0, arousal=0.05, valence=0.4))
    terror = infer_affect(sim.window(2.0, arousal=0.98, valence=-0.8))
    assert terror.arousal > calm.arousal
    assert terror.fear > calm.fear
    assert terror.relaxation < calm.relaxation


def test_empty_chunk_is_safe():
    from engine.schemas import EEGChunk

    a = infer_affect(EEGChunk(samples=[]))
    assert a.fear == 0.0 and a.arousal == 0.0
