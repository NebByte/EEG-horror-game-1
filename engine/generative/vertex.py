"""Google Cloud Vertex AI provider (optional).

Uses the `google-genai` SDK to have **Gemini** author structured design specs
(JSON) for characters, maps and soundscapes. Media generation (Imagen art,
Lyria audio → GCS) is left as a documented extension; specs alone already drive
the engine, and `Asset.uri` stays `None` until media is wired up.

Everything is imported lazily and every call degrades to a deterministic spec on
error, so a missing SDK / credential never hard-fails a session — the pipeline's
`get_provider()` additionally falls back to the mock provider entirely.
"""
from __future__ import annotations

import json
import logging

from engine.config import get_settings
from engine.generative.base import AssetProvider
from engine.generative.mock import MockProvider
from engine.schemas import Asset, Mood, SeedProfile

log = logging.getLogger("engine.generative.vertex")


class VertexProvider(AssetProvider):
    name = "vertex"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._mock = MockProvider()  # spec fallback shape
        try:
            from google import genai  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Vertex provider needs the google-genai SDK "
                "(pip install -r requirements-vertex.txt)."
            ) from exc
        from google import genai

        # Gemini text models are served from the `global` endpoint on Vertex.
        self._client = genai.Client(
            vertexai=True,
            project=self.settings.gcp_project or None,
            location="global",
        )

    async def _spec(self, kind: str, seed: SeedProfile, mood: Mood) -> dict:
        prompt = (
            f"You are designing a horror game asset. Theme: {seed.theme}. "
            f"Player fears: {', '.join(seed.fears)}. Mood bucket: {mood}. "
            f"Return ONLY minified JSON describing a {kind} for this mood."
        )
        try:
            import asyncio

            def _call() -> str:
                resp = self._client.models.generate_content(
                    model=self.settings.vertex_text_model, contents=prompt
                )
                return resp.text or "{}"

            # Hard deadline: the google-genai SDK can hang on silent connections
            # (NAT idle-eviction), so wrap the blocking call in wait_for.
            text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _call), timeout=30.0)
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001 — degrade to a deterministic spec
            log.warning("Vertex %s generation failed (%s); using mock spec.", kind, exc)
            return {}

    async def generate_character(self, seed: SeedProfile, mood: Mood) -> Asset:
        base = await self._mock.generate_character(seed, mood)
        spec = await self._spec("character", seed, mood)
        if spec:
            base.spec = {**base.spec, **spec, "provider": "vertex"}
        return base

    async def generate_soundscape(self, seed: SeedProfile, mood: Mood) -> Asset:
        base = await self._mock.generate_soundscape(seed, mood)
        spec = await self._spec("soundscape", seed, mood)
        if spec:
            base.spec = {**base.spec, **spec, "provider": "vertex"}
        return base

    async def generate_map(self, seed: SeedProfile, mood: Mood) -> Asset:
        base = await self._mock.generate_map(seed, mood)
        spec = await self._spec("map", seed, mood)
        if spec:
            base.spec = {**base.spec, **spec, "provider": "vertex"}
        return base
