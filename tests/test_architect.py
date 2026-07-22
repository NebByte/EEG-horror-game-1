"""The Architect: composes a valid Script, and the learning layer makes the
composer favour what scared this player last time."""
from __future__ import annotations

from engine.architect.composer import MockComposer
from engine.architect.datapoints import get_datapoint
from engine.architect.learning import PlayerModel
from engine.schemas import SeedProfile


def _seed() -> SeedProfile:
    return SeedProfile(theme="asylum", fears=["darkness", "being chased"], intensity_preference=0.7)


def test_script_is_valid_and_arced():
    pm = PlayerModel(player_id="p1")
    script = MockComposer().compose("s1", _seed(), pm, length=8)
    assert len(script.beats) == 8
    # Every referenced DataPoint exists in the catalog.
    for beat in script.beats:
        assert beat.datapoint_ids
        for dp in beat.datapoint_ids:
            assert get_datapoint(dp) is not None
    # The arc should reach a real spike.
    assert max(script.tension_curve) >= 0.6


def test_learning_shifts_selection():
    seed = _seed()
    pm = PlayerModel(player_id="p2")
    composer = MockComposer()

    # Teach the model that "the crawler" reliably terrifies this player.
    for _ in range(6):
        pm.observe(["encounter.crawler", "audio.scuttle"], reward=1.0, fears=seed.fears)
    # ...and that the distant figure does nothing for them.
    for _ in range(6):
        pm.observe(["encounter.distant_figure"], reward=0.0, fears=seed.fears)

    assert pm.score_datapoint("encounter.crawler") > pm.score_datapoint("encounter.distant_figure")

    # Across several composed scripts, the crawler should now appear more than
    # the distant figure for this player.
    crawler = figure = 0
    for i in range(6):
        script = composer.compose(f"s{i}", seed, pm, length=8)
        ids = [d for b in script.beats for d in b.datapoint_ids]
        crawler += ids.count("encounter.crawler")
        figure += ids.count("encounter.distant_figure")
    assert crawler > figure


def test_version_increments_with_reactions():
    pm = PlayerModel(player_id="p3")
    s1 = MockComposer().compose("s", _seed(), pm, length=6)
    pm.observe(["encounter.render"], reward=0.9)
    s2 = MockComposer().compose("s", _seed(), pm, length=6)
    assert s2.version > s1.version
