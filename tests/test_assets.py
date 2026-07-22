"""Fresh-assets-every-run + escalation."""
from __future__ import annotations

from engine.architect.composer import MockComposer
from engine.architect.learning import PlayerModel
from engine.assets.resolver import resolve_script_assets
from engine.assets.sources import ProceduralAssetSource
from engine.schemas import SeedProfile


def _seed():
    return SeedProfile(theme="asylum", fears=["darkness", "being chased"], intensity_preference=0.7)


def test_procedural_source_covers_all_kinds():
    src = ProceduralAssetSource()
    for kind in ("map", "model", "character", "image", "sound", "animation"):
        a = src.fetch(kind, seed=123, mood="dread", tags=["x"], fears=["darkness"], escalation=0.5)
        assert a.kind == kind
        assert a.params and a.license and a.source == "procedural"


def test_resolver_covers_datapoints_with_expected_kinds():
    pm = PlayerModel(player_id="a")
    script = MockComposer().compose("s", _seed(), pm, length=6)
    assets = resolve_script_assets(script, run_seed=1, escalation=0.4)
    # every space -> map, encounter -> character+animation, audio -> sound
    for dp_id, media in assets.items():
        kinds = {m.kind for m in media}
        if dp_id.startswith("space."):
            assert "map" in kinds
        if dp_id.startswith("encounter."):
            assert {"character", "animation"} <= kinds
        if dp_id.startswith("audio."):
            assert "sound" in kinds


def test_assets_differ_every_run():
    pm = PlayerModel(player_id="b")
    script = MockComposer().compose("s", _seed(), pm, length=6)
    a1 = resolve_script_assets(script, run_seed=111, escalation=0.4)
    a2 = resolve_script_assets(script, run_seed=222, escalation=0.4)
    # For a shared DataPoint, the resolved asset ids should change run to run.
    shared = set(a1) & set(a2)
    assert shared
    changed = any(a1[k][0].id != a2[k][0].id for k in shared if a1[k] and a2[k])
    assert changed, "assets should vary between runs"


def test_escalation_rises_with_runs():
    pm = PlayerModel(player_id="c")
    e0 = pm.escalation()
    pm.runs = 5
    e5 = pm.escalation()
    assert e5 > e0
    # A later run produces a hotter tension ceiling than the first.
    s_early = MockComposer().compose("s", _seed(), PlayerModel(player_id="c", runs=1), length=8)
    s_late = MockComposer().compose("s", _seed(), PlayerModel(player_id="c", runs=8), length=8)
    assert s_late.escalation > s_early.escalation
    assert max(s_late.tension_curve) >= max(s_early.tension_curve)
