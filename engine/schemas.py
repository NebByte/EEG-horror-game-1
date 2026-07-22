"""Shared pydantic contracts spoken by every layer (API, EEG, generative, director).

Keeping the data model in one place means the whole system speaks the same
language: an `EEGChunk` goes in, an `AffectState` and a `Directive` come out.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# The four "mood buckets" the asset bank is organised around. The director
# always resolves the live affect to exactly one of these.
Mood = Literal["unease", "dread", "panic", "relief"]
MOODS: tuple[Mood, ...] = ("unease", "dread", "panic", "relief")

AssetKind = Literal["soundscape", "character", "map"]


# --------------------------------------------------------------------------- #
# EEG
# --------------------------------------------------------------------------- #
class EEGSample(BaseModel):
    """One multi-channel sample at a point in time (microvolts per channel)."""

    t: float = Field(..., description="Seconds since stream start.")
    channels: list[float] = Field(..., description="One value per EEG channel (uV).")


class EEGChunk(BaseModel):
    """A window of EEG samples pushed to the engine."""

    sample_rate_hz: float = Field(256.0, gt=0)
    channel_names: list[str] = Field(default_factory=lambda: ["AF3", "AF4", "TP9", "TP10"])
    samples: list[EEGSample] = Field(default_factory=list)


class BandPowers(BaseModel):
    """Relative power in each canonical EEG band (sums to ~1.0)."""

    delta: float = 0.0
    theta: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    gamma: float = 0.0
    frontal_alpha_asymmetry: float = 0.0


class AffectState(BaseModel):
    """The engine's estimate of the player's emotional state, all in [0, 1]
    except valence which is in [-1, 1]."""

    fear: float = 0.0
    stress: float = 0.0
    arousal: float = 0.0
    engagement: float = 0.0
    relaxation: float = 0.0
    valence: float = 0.0  # -1 withdrawal ... +1 approach


class CvAffect(BaseModel):
    """Computer-vision (webcam) affect estimate, fused with the EEG affect.

    A second modality: facial expression / motion. `confidence` gates how much
    it's trusted (0 = ignore, e.g. no face detected)."""

    arousal: float = 0.0        # 0..1 (e.g. motion energy / expressiveness)
    valence: float = 0.0        # -1..1 (negative = distress)
    surprise: float = 0.0       # 0..1 (startle spikes)
    fear: float = 0.0           # 0..1 (fear expression)
    confidence: float = 0.0     # 0..1 how much to trust this frame


class SignalQuality(BaseModel):
    """Per-window signal health, from the MindLink poor-signal + artifact checks."""

    poor_signal: int = 0        # 0 good .. 200 off-head (MindLink scale)
    ok: bool = True
    blink: bool = False
    emg: bool = False
    motion: bool = False
    confidence: float = 1.0     # 0..1 usable weight for this window


# --------------------------------------------------------------------------- #
# Generative assets
# --------------------------------------------------------------------------- #
class Asset(BaseModel):
    id: str
    kind: AssetKind
    mood: Mood
    name: str
    tags: list[str] = Field(default_factory=list)
    spec: dict = Field(default_factory=dict, description="Provider design spec.")
    uri: str | None = Field(None, description="Resolved media URI, if any.")


class AssetBank(BaseModel):
    """One character + one soundscape + one map per mood bucket."""

    session_id: str
    characters: list[Asset] = Field(default_factory=list)
    soundscapes: list[Asset] = Field(default_factory=list)
    maps: list[Asset] = Field(default_factory=list)

    def by_mood(self, kind: AssetKind, mood: Mood) -> Asset | None:
        pool = {"character": self.characters, "soundscape": self.soundscapes, "map": self.maps}[kind]
        for a in pool:
            if a.mood == mood:
                return a
        return pool[0] if pool else None


# --------------------------------------------------------------------------- #
# Seed profile & directives
# --------------------------------------------------------------------------- #
class SeedProfile(BaseModel):
    theme: str = "abandoned asylum"
    fears: list[str] = Field(default_factory=lambda: ["darkness", "isolation"])
    intensity_preference: float = Field(0.6, ge=0.0, le=1.0)


class Directive(BaseModel):
    """What the game client should do *right now*."""

    mood: Mood
    intensity: float = Field(..., ge=0.0, le=1.0)
    spawn_character_id: str | None = None
    ambient_sound_id: str | None = None
    stinger_sound_id: str | None = None
    map_id: str | None = None
    safety_backoff: bool = False
    # Convenience fields a thin client can render without resolving the bank.
    fog_density: float = 0.2
    flicker: float = 0.0
    heartbeat_bpm: float = 60.0
