"""The composer — the Architect that authors a Script from DataPoints.

Two backends behind one interface:

* `MockComposer`  — deterministic, offline. Builds a tension arc and, for each
  beat, selects DataPoints by mood fit, the player's stated fears, and the
  **learned player model**, then *enhances* strong picks by pulling in their
  partner DataPoints. No network, no keys — this is the default and the fallback.

* `AnthropicComposer` — hands the catalog + player model + seed to **Claude** and
  asks it to author the Script as JSON. Falls back to the mock on any error or a
  missing key, so the game always gets a playable script.

`get_composer()` picks the backend from config and degrades to mock.
"""
from __future__ import annotations

import logging
import random

from engine.architect.datapoints import CATALOG, CATEGORIES, DataPoint, catalog_by_category, get_datapoint
from engine.architect.learning import PlayerModel
from engine.architect.script import Beat, Script
from engine.config import get_settings
from engine.schemas import AffectState, Mood, SeedProfile

log = logging.getLogger("engine.architect")

# The tension arc a session moves through, as (mood, target_tension) waypoints.
# The composer interpolates a curve of `length` beats across these.
_ARC: list[tuple[Mood, float]] = [
    ("unease", 0.20), ("unease", 0.35), ("dread", 0.55), ("dread", 0.70),
    ("panic", 0.90), ("relief", 0.30), ("dread", 0.65), ("panic", 0.95),
]


def _seed_int(*parts) -> int:
    return abs(hash("::".join(str(p) for p in parts))) % (2**31)


class MockComposer:
    name = "mock"

    def _rank(self, dp: DataPoint, mood: Mood, target: float, seed: SeedProfile, pm: PlayerModel) -> float:
        # Fit to the beat's intensity.
        fit = 1.0 - abs(dp.base_intensity - target)
        # Does it play on a fear this player stated *and* actually reacts to?
        fear_fit = 0.0
        for fear, aff in dp.fear_affinity.items():
            if fear in seed.fears:
                fear_fit = max(fear_fit, aff * pm.fear_weight(fear))
        # What has this player's history said about this DataPoint / its tags?
        learned = pm.score_datapoint(dp.id)
        return 0.45 * fit + 0.30 * fear_fit + 0.25 * learned

    def _pick_for_beat(self, mood: Mood, target: float, seed: SeedProfile,
                       pm: PlayerModel, rng: random.Random) -> list[str]:
        chosen: list[str] = []
        # One space + one lighting always; encounters/audio/events by tension.
        want = {"space": 1, "lighting": 1, "audio": 1 if target < 0.5 else 2,
                "encounter": 0 if target < 0.3 else 1, "event": 1 if target > 0.55 else 0,
                "prop": 1 if target < 0.5 else 0}
        for cat in CATEGORIES:
            k = want.get(cat, 0)
            if k <= 0:
                continue
            pool = catalog_by_category(cat)
            ranked = sorted(pool, key=lambda d: self._rank(d, mood, target, seed, pm)
                            + rng.uniform(0, 0.08), reverse=True)
            chosen.extend(d.id for d in ranked[:k])
        # Enhance: for each strong pick, pull in a partner DataPoint it amplifies.
        for dp_id in list(chosen):
            dp = get_datapoint(dp_id)
            if not dp or not dp.enhances:
                continue
            if pm.score_datapoint(dp_id) >= 0.5:  # only amplify what's working
                partner = max(dp.enhances, key=lambda p: pm.score_datapoint(p))
                if partner not in chosen and get_datapoint(partner):
                    chosen.append(partner)
        return chosen

    def compose(self, session_id: str, seed: SeedProfile, pm: PlayerModel,
                length: int = 8, recent_affect: AffectState | None = None) -> Script:
        rng = random.Random(_seed_int(session_id, pm.reactions_seen, seed.theme))

        # Build a tension curve of `length` beats sampled across the arc, tilted
        # by the player's intensity preference and (if present) live arousal.
        curve: list[tuple[Mood, float]] = []
        for i in range(length):
            mood, base = _ARC[i % len(_ARC)]
            t = base * (0.6 + 0.8 * seed.intensity_preference)
            if recent_affect is not None:
                t = 0.7 * t + 0.3 * recent_affect.arousal
            curve.append((mood, max(0.05, min(1.0, t))))

        beats: list[Beat] = []
        for i, (mood, target) in enumerate(curve):
            dp_ids = self._pick_for_beat(mood, target, seed, pm, rng)
            names = [get_datapoint(d).name for d in dp_ids if get_datapoint(d)]
            beats.append(Beat(index=i, mood=mood, target_tension=round(target, 3),
                              duration_s=40.0, datapoint_ids=dp_ids,
                              note=" · ".join(names)))

        top = sorted(pm.datapoint_scores.items(), key=lambda kv: kv[1], reverse=True)[:3]
        rationale = (
            f"Composed {length} beats for '{seed.theme}'. "
            f"Conditioned on {pm.reactions_seen} past reactions"
            + (f"; leaning into {', '.join(k for k, _ in top)}." if top else " (no history yet)."))

        return Script(session_id=session_id, player_id=pm.player_id, seed=seed,
                      version=pm.reactions_seen + 1, composer=self.name,
                      beats=beats, tension_curve=[round(t, 3) for _, t in curve],
                      rationale=rationale)


class AnthropicComposer(MockComposer):
    """Claude authors the Script; falls back to the mock arc on any failure."""

    name = "anthropic"

    def __init__(self) -> None:
        self.settings = get_settings()
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Anthropic composer needs the anthropic SDK "
                "(pip install anthropic) and ARCHITECT_PROVIDER=anthropic."
            ) from exc
        key = self.settings.anthropic_api_key
        if not key:
            raise RuntimeError("ARCHITECT_PROVIDER=anthropic but ANTHROPIC_API_KEY is unset.")
        import anthropic

        self._client = anthropic.Anthropic(api_key=key)

    def _catalog_digest(self) -> str:
        return "\n".join(
            f"- {d.id} ({d.category}, intensity {d.base_intensity:.2f}) "
            f"fears={list(d.fear_affinity)} enhances={d.enhances}"
            for d in CATALOG
        )

    def compose(self, session_id: str, seed: SeedProfile, pm: PlayerModel,
                length: int = 8, recent_affect: AffectState | None = None) -> Script:
        import json

        top = sorted(pm.datapoint_scores.items(), key=lambda kv: kv[1], reverse=True)[:6]
        prompt = (
            "You are the Architect of a personalized EEG-driven horror game. Author a "
            f"Script of exactly {length} Beats using ONLY the DataPoint ids below. "
            "Build a tension arc (rise, spikes, brief relief). Personalize using the "
            "player's fears and their learned reaction scores (higher = scares them more).\n\n"
            f"Player fears: {seed.fears}\nTheme: {seed.theme}\n"
            f"Intensity preference: {seed.intensity_preference}\n"
            f"Reactions observed: {pm.reactions_seen}\n"
            f"Top learned scores: {top}\n\n"
            f"DataPoint catalog:\n{self._catalog_digest()}\n\n"
            'Return ONLY minified JSON: {"beats":[{"index":0,"mood":"unease|dread|panic|relief",'
            '"target_tension":0.0-1.0,"datapoint_ids":["..."],"note":"..."}],"rationale":"..."}'
        )
        try:
            msg = self._client.messages.create(
                model=self.settings.architect_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            data = json.loads(text)
            beats = [
                Beat(index=b.get("index", i), mood=b["mood"],
                     target_tension=float(b["target_tension"]),
                     datapoint_ids=[d for d in b.get("datapoint_ids", []) if get_datapoint(d)],
                     note=b.get("note", ""))
                for i, b in enumerate(data["beats"])
            ]
            if not beats:
                raise ValueError("empty script")
            return Script(session_id=session_id, player_id=pm.player_id, seed=seed,
                          version=pm.reactions_seen + 1, composer=self.name, beats=beats,
                          tension_curve=[b.target_tension for b in beats],
                          rationale=data.get("rationale", ""))
        except Exception as exc:  # noqa: BLE001 — always ship a playable script
            log.warning("Anthropic composer failed (%s); using mock composer.", exc)
            script = super().compose(session_id, seed, pm, length, recent_affect)
            script.composer = "mock(fallback)"
            return script


def get_composer():
    provider = get_settings().architect_provider
    if provider == "anthropic":
        try:
            return AnthropicComposer()
        except Exception as exc:  # noqa: BLE001
            log.warning("Architect 'anthropic' unavailable (%s); using mock.", exc)
    return MockComposer()
