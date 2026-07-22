"""The evolutionary ML layer: learn enhance-pairs, and breed new DataPoints
(mutate / crossover) from what the player reacts to."""
from __future__ import annotations

from engine.architect.composer import MockComposer
from engine.architect.evolution import evolved_catalog, synthesize_for_player
from engine.architect.datapoints import CATALOG
from engine.architect.learning import PlayerModel
from engine.assets.resolver import resolve_script_assets
from engine.schemas import SeedProfile


def _seed():
    return SeedProfile(theme="asylum", fears=["being chased", "darkness"], intensity_preference=0.7)


def test_pairs_learned_into_enhances():
    pm = PlayerModel(player_id="p")
    for _ in range(5):
        pm.observe(["encounter.crawler", "audio.scuttle"], reward=1.0)
    partners = pm.learned_enhances("encounter.crawler")
    assert "audio.scuttle" in partners


def test_no_breeding_before_enough_data():
    pm = PlayerModel(player_id="p")
    pm.observe(["encounter.crawler"], reward=1.0)  # only 1 reaction
    assert synthesize_for_player(pm) == []


def test_mutation_breeds_similar_datapoints():
    pm = PlayerModel(player_id="p")
    for _ in range(9):
        pm.observe(["encounter.crawler", "audio.scuttle"], reward=1.0)
    bred = synthesize_for_player(pm)
    assert bred, "should breed new DataPoints after enough high-reward reactions"
    # A mutant keeps its parent's category prefix and is a *new* id.
    mutant = next(d for d in bred if "~m" in d.id)
    assert mutant.category in ("encounter", "audio")
    assert mutant.id.split(".", 1)[0] == mutant.category  # prefix preserved
    assert "personalized" in mutant.tags


def test_crossover_after_more_data():
    pm = PlayerModel(player_id="p")
    for _ in range(8):
        pm.observe(["encounter.crawler", "encounter.render"], reward=1.0)
    bred = synthesize_for_player(pm)
    assert any("~x" in d.id for d in bred), "should cross two top encounters into a hybrid"


def test_evolved_catalog_grows_and_feeds_composer():
    pm = PlayerModel(player_id="p")
    base_n = len(CATALOG)
    for _ in range(9):
        pm.observe(["encounter.crawler", "audio.scuttle"], reward=1.0)
    evo = evolved_catalog(pm)
    assert len(evo) > base_n  # bred DataPoints added

    # The composer records the DataPoint defs it used, and bred ones resolve to
    # assets from the script's own definitions.
    script = MockComposer().compose("s", _seed(), pm, length=8)
    assets = resolve_script_assets(script, run_seed=7, escalation=script.escalation)
    for dp_id in script.datapoints:
        if dp_id.startswith("encounter."):
            kinds = {m.kind for m in assets.get(dp_id, [])}
            assert "character" in kinds  # even a bred encounter resolves media
