"""Client-side device gateway: stream an EEG source to the engine WebSocket.

This is the glue that turns a headset (or the simulator) into a live session:
create a session, generate its asset bank, then pump EEG windows into
`/stream` and yield the affect + directive frames the engine sends back.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx
import websockets


async def create_session(base_url: str, seed: dict) -> str:
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as c:
        r = await c.post("/v1/sessions", json={"seed": seed})
        r.raise_for_status()
        return r.json()["id"]


async def generate_assets(base_url: str, sid: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as c:
        r = await c.post(f"/v1/sessions/{sid}/generate")
        r.raise_for_status()


async def run_gateway(source, sid: str, ws_base: str, window_seconds: float = 2.0) -> AsyncIterator[dict]:
    """Yield one flattened `{affect, intensity, mood, ...}` frame per window."""
    url = f"{ws_base}/v1/sessions/{sid}/stream"
    async with websockets.connect(url) as ws:
        while True:
            chunk = await source.read(window_seconds)
            await ws.send(chunk.model_dump_json())
            msg = json.loads(await ws.recv())
            if "error" in msg:
                raise RuntimeError(msg["error"])
            a, d = msg["affect"], msg["directive"]
            yield {
                "affect": a,
                "mood": d["mood"],
                "intensity": d["intensity"],
                "spawn_character_id": d.get("spawn_character_id"),
                "ambient_sound_id": d.get("ambient_sound_id"),
                "safety_backoff": d.get("safety_backoff", False),
            }
