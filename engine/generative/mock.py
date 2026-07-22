"""Deterministic, fully offline asset provider.

Same output *shape* as a real generative backend, but computed from the seed so
the prototype runs with no cloud, no keys, and reproducible results.
"""
from __future__ import annotations

import hashlib

from engine.generative.base import AssetProvider
from engine.schemas import Asset, Mood, SeedProfile

# Per-mood flavour used to shape the deterministic specs.
_MOOD_FLAVOUR: dict[Mood, dict] = {
    "unease": {"tempo": 60, "palette": ["#1a1d22", "#2b2f36"], "aggression": 0.15, "fog": 0.25},
    "dread": {"tempo": 72, "palette": ["#14171c", "#3a2323"], "aggression": 0.45, "fog": 0.45},
    "panic": {"tempo": 120, "palette": ["#0d0d0f", "#5a1414"], "aggression": 0.9, "fog": 0.7},
    "relief": {"tempo": 50, "palette": ["#20242b", "#2f3a44"], "aggression": 0.05, "fog": 0.12},
}

_CREATURES = {
    "unease": "The Watcher",
    "dread": "The Crawler",
    "panic": "The Render",
    "relief": "Distant Echo",
}


def _hid(*parts: str) -> str:
    return hashlib.sha1("::".join(parts).encode()).hexdigest()[:10]


class MockProvider(AssetProvider):
    name = "mock"

    async def generate_soundscape(self, seed: SeedProfile, mood: Mood) -> Asset:
        f = _MOOD_FLAVOUR[mood]
        return Asset(
            id=f"snd_{_hid(seed.theme, mood)}",
            kind="soundscape",
            mood=mood,
            name=f"{mood.title()} ambience — {seed.theme}",
            tags=[mood, "ambient", *seed.fears],
            spec={
                "bpm": f["tempo"],
                "layers": ["drone", "room-tone", "distant-metal"]
                + (["heartbeat", "breathing"] if f["aggression"] > 0.4 else []),
                "stinger": mood in ("dread", "panic"),
                "reverb": 0.6 if mood != "relief" else 0.2,
            },
        )

    async def generate_character(self, seed: SeedProfile, mood: Mood) -> Asset:
        f = _MOOD_FLAVOUR[mood]
        return Asset(
            id=f"chr_{_hid(seed.theme, mood)}",
            kind="character",
            mood=mood,
            name=_CREATURES[mood],
            tags=[mood, "stalker", *seed.fears],
            spec={
                "aggression": f["aggression"],
                "speed": round(0.4 + f["aggression"] * 1.2, 2),
                "silhouette": "tall-thin" if mood != "panic" else "sprinting-mass",
                "palette": f["palette"],
                "behaviour": "stalk" if f["aggression"] < 0.5 else "hunt",
            },
        )

    async def generate_map(self, seed: SeedProfile, mood: Mood) -> Asset:
        f = _MOOD_FLAVOUR[mood]
        return Asset(
            id=f"map_{_hid(seed.theme, mood)}",
            kind="map",
            mood=mood,
            name=f"{seed.theme} — {mood}",
            tags=[mood, "level", *seed.fears],
            spec={
                "layout": "corridor-maze" if mood != "relief" else "open-atrium",
                "fog_density": f["fog"],
                "light_level": round(max(0.05, 0.6 - f["aggression"] * 0.5), 2),
                "flicker": round(f["aggression"], 2),
                "palette": f["palette"],
                "corridor_length": 24,
            },
        )
