"""The Anthropic (Claude) composer: parses a script from a Claude-style response,
and falls back to the mock composer on a bad response — verified with a fake
client, no API key or network."""
from __future__ import annotations

from engine.architect.composer import AnthropicComposer
from engine.architect.learning import PlayerModel
from engine.schemas import SeedProfile


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Msg:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeClient:
    def __init__(self, text):
        self._text = text
        self.messages = self

    def create(self, **kwargs):
        return _Msg(self._text)


def _seed():
    return SeedProfile(theme="asylum", fears=["darkness"], intensity_preference=0.6)


def test_parses_claude_script():
    payload = (
        '{"beats":[{"index":0,"mood":"unease","target_tension":0.2,'
        '"datapoint_ids":["space.narrow_corridor","encounter.distant_figure"],"note":"open"},'
        '{"index":1,"mood":"panic","target_tension":0.95,'
        '"datapoint_ids":["encounter.render"],"note":"chase"}],"rationale":"test"}'
    )
    comp = AnthropicComposer(client=_FakeClient(payload))
    script = comp.compose("s", _seed(), PlayerModel(player_id="p"), length=2)
    assert script.composer == "anthropic"
    assert len(script.beats) == 2
    assert script.beats[1].mood == "panic"
    assert "encounter.render" in script.beats[1].datapoint_ids


def test_falls_back_on_garbage():
    comp = AnthropicComposer(client=_FakeClient("not json at all"))
    script = comp.compose("s", _seed(), PlayerModel(player_id="p"), length=4)
    assert script.composer == "mock(fallback)"
    assert len(script.beats) == 4  # still a playable script
