"""The AssetProvider ABC — the seam between the engine and any generative backend.

The rest of the engine depends only on this interface, so swapping mock ->
Vertex -> a self-hosted diffusion model is a config change, not a rewrite.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from engine.schemas import Asset, Mood, SeedProfile


class AssetProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def generate_soundscape(self, seed: SeedProfile, mood: Mood) -> Asset:
        """A looping ambient bed (+ optional stinger spec) for one mood."""

    @abstractmethod
    async def generate_character(self, seed: SeedProfile, mood: Mood) -> Asset:
        """A stalker/monster design for one mood."""

    @abstractmethod
    async def generate_map(self, seed: SeedProfile, mood: Mood) -> Asset:
        """A level/space design for one mood."""
