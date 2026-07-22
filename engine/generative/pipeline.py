"""Build the asset bank by fanning generation across the four moods concurrently.

`get_provider()` selects the backend from config and **degrades to mock on any
error**, so a missing SDK or bad credential never hard-fails the prototype.
"""
from __future__ import annotations

import asyncio
import logging

from engine.config import get_settings
from engine.generative.base import AssetProvider
from engine.generative.mock import MockProvider
from engine.schemas import AssetBank, MOODS, SeedProfile

log = logging.getLogger("engine.generative")


def get_provider() -> AssetProvider:
    settings = get_settings()
    if settings.asset_provider == "vertex":
        try:
            from engine.generative.vertex import VertexProvider  # lazy import

            return VertexProvider()
        except Exception as exc:  # noqa: BLE001 — degrade, never hard-fail
            log.warning("Vertex provider unavailable (%s); falling back to mock.", exc)
    return MockProvider()


class AssetPipeline:
    def __init__(self, provider: AssetProvider | None = None) -> None:
        self.provider = provider or get_provider()

    async def build_bank(self, session_id: str, seed: SeedProfile) -> AssetBank:
        async def gen(kind: str, mood):  # noqa: ANN001
            fn = {
                "character": self.provider.generate_character,
                "soundscape": self.provider.generate_soundscape,
                "map": self.provider.generate_map,
            }[kind]
            return await fn(seed, mood)

        tasks = [gen(k, m) for k in ("character", "soundscape", "map") for m in MOODS]
        assets = await asyncio.gather(*tasks)

        bank = AssetBank(session_id=session_id)
        for a in assets:
            {"character": bank.characters, "soundscape": bank.soundscapes, "map": bank.maps}[a.kind].append(a)
        return bank
