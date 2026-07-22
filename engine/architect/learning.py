"""The learning layer — the per-player model that makes it better over time.

Every time the game shows the player something (a Beat built from DataPoints) we
record their **reaction** (how their fear/arousal actually moved, from EEG — and
later computer-vision affect). From that we update running scores:

  * `datapoint_scores` — how strongly *this* player reacts to each DataPoint
  * `tag_scores`       — the same at the tag level (generalises to new DataPoints)
  * `fear_weights`     — which of their stated fears actually land

The composer reads these as **conditioning weights**, so across runs the Script
drifts toward what genuinely scares this specific player. Persisted as JSON so it
survives restarts (that's the "learns you over time" loop).
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from engine.architect.datapoints import get_datapoint
from engine.config import get_settings

# How fast scores adapt to new evidence, and where the neutral prior sits.
LEARN_RATE = 0.25
PRIOR = 0.5


class PlayerModel(BaseModel):
    player_id: str
    datapoint_scores: dict[str, float] = Field(default_factory=dict)
    tag_scores: dict[str, float] = Field(default_factory=dict)
    fear_weights: dict[str, float] = Field(default_factory=dict)
    # Learned "these work together" scores, keyed "a|b" (a<b). Drives which
    # DataPoints the Architect *enhances* together, and which to breed.
    pair_scores: dict[str, float] = Field(default_factory=dict)
    reactions_seen: int = 0
    # How many times this player has started/restarted the game. Drives the
    # "scarier and scarier" escalation — each run pushes harder than the last.
    runs: int = 0

    def escalation(self) -> float:
        """A rising dread factor (can exceed 1.0 to push tension ceilings). Grows
        with each run and, more slowly, with how much we've learned about them."""
        return min(1.6, 0.25 + 0.12 * self.runs + 0.008 * self.reactions_seen)

    # -- reads used by the composer ---------------------------------------- #
    def score_datapoint(self, dp_id: str) -> float:
        """Blend the DataPoint's own learned score with its tags' scores so a
        never-seen DataPoint still benefits from what we learned about its tags."""
        direct = self.datapoint_scores.get(dp_id)
        dp = get_datapoint(dp_id)
        tag_vals = [self.tag_scores[t] for t in (dp.tags if dp else []) if t in self.tag_scores]
        tag_mean = sum(tag_vals) / len(tag_vals) if tag_vals else PRIOR
        if direct is None:
            return tag_mean
        return 0.6 * direct + 0.4 * tag_mean

    def fear_weight(self, fear: str) -> float:
        return self.fear_weights.get(fear, PRIOR)

    def learned_enhances(self, dp_id: str, k: int = 2, min_score: float = 0.55) -> list[str]:
        """The DataPoints this player reacts to *best when paired* with `dp_id`."""
        partners: list[tuple[str, float]] = []
        for key, score in self.pair_scores.items():
            a, b = key.split("|", 1)
            if score < min_score:
                continue
            if a == dp_id:
                partners.append((b, score))
            elif b == dp_id:
                partners.append((a, score))
        partners.sort(key=lambda kv: kv[1], reverse=True)
        return [p for p, _ in partners[:k]]

    # -- the update rule --------------------------------------------------- #
    def observe(self, datapoint_ids: list[str], reward: float, fears: list[str] | None = None) -> None:
        """`reward` in [0,1] = how well this moment landed (e.g. fear delta)."""
        reward = max(0.0, min(1.0, reward))
        for dp_id in datapoint_ids:
            prev = self.datapoint_scores.get(dp_id, PRIOR)
            self.datapoint_scores[dp_id] = prev + LEARN_RATE * (reward - prev)
            dp = get_datapoint(dp_id)
            for tag in dp.tags if dp else []:
                p = self.tag_scores.get(tag, PRIOR)
                self.tag_scores[tag] = p + LEARN_RATE * (reward - p)
        # Co-occurrence: every unordered pair present this moment learns the reward.
        uniq = sorted(set(datapoint_ids))
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                key = f"{uniq[i]}|{uniq[j]}"
                p = self.pair_scores.get(key, PRIOR)
                self.pair_scores[key] = p + LEARN_RATE * (reward - p)
        for fear in fears or []:
            p = self.fear_weights.get(fear, PRIOR)
            self.fear_weights[fear] = p + LEARN_RATE * (reward - p)
        self.reactions_seen += 1


class PlayerStore:
    """Loads/saves PlayerModels as JSON under `player_data_dir`."""

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or get_settings().player_data_dir)

    def _path(self, player_id: str) -> Path:
        safe = "".join(c for c in player_id if c.isalnum() or c in "-_")[:64] or "anon"
        return self.root / f"{safe}.json"

    def load(self, player_id: str) -> PlayerModel:
        p = self._path(player_id)
        if p.exists():
            try:
                return PlayerModel.model_validate_json(p.read_text())
            except Exception:
                pass  # corrupt file -> start fresh
        return PlayerModel(player_id=player_id)

    def save(self, model: PlayerModel) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(model.player_id).write_text(model.model_dump_json(indent=2))


player_store = PlayerStore()
