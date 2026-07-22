"""The Script — the composed game.

A Script is an ordered list of **Beats**. Each beat is a moment of play: a mood,
a target tension, and the **DataPoints** active during it (a space + encounters +
audio + lighting + events). The runtime walks the beats, and the live EEG loop
modulates *within* the current beat (via the existing director/Directive). So the
Architect authors the arc; the director handles the second-to-second reaction.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from engine.schemas import Mood, SeedProfile


class Beat(BaseModel):
    index: int
    mood: Mood
    target_tension: float = Field(..., ge=0.0, le=1.0)
    duration_s: float = 45.0
    datapoint_ids: list[str] = Field(default_factory=list)
    # A one-line, human-readable summary of what happens (for logs/debug/HUD).
    note: str = ""


class Script(BaseModel):
    session_id: str
    player_id: str
    seed: SeedProfile
    version: int = 1
    composer: str = "mock"
    # Which run this is for the player, and the escalation ("scarier and scarier").
    run: int = 1
    escalation: float = 0.25
    beats: list[Beat] = Field(default_factory=list)
    tension_curve: list[float] = Field(default_factory=list)
    # Per-run resolved media, keyed by DataPoint id: {dp_id -> [MediaAsset,...]}.
    assets: dict[str, list] = Field(default_factory=dict)
    # Why the Architect made these choices (conditioning summary / Claude rationale).
    rationale: str = ""

    def beat(self, index: int) -> Beat | None:
        return self.beats[index] if 0 <= index < len(self.beats) else None
