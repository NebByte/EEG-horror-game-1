"""Architect API: compose the Script, read it back, and learn from reactions.

    POST /sessions/{id}/script      -> compose (or recompose) the personalized game
    GET  /sessions/{id}/script      -> the current Script
    POST /sessions/{id}/reactions   -> feed a reaction; update the player model
    GET  /players/{player_id}       -> the learned model (inspect what it knows)

Recomposing on every open/restart is the "Claude re-authors a fresh combination
that has learned you" loop: the composer reads the persisted player model, and
reactions posted during play update that model for next time.
"""
from __future__ import annotations

import anyio
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from engine.architect.composer import get_composer
from engine.architect.learning import PlayerModel, player_store
from engine.architect.script import Script
from engine.assets.resolver import resolve_script_assets
from engine.experience.state import store
from engine.schemas import AffectState
from engine.util import stable_seed

# Stable, injection-safe player id (also the persistence key).
PLAYER_ID = r"^[A-Za-z0-9_-]{1,64}$"

router = APIRouter(tags=["architect"])


class ComposeRequest(BaseModel):
    length: int = Field(8, ge=1, le=32)
    use_recent_affect: bool = True
    # Resolve a fresh set of media assets for this run (different every time).
    fresh_assets: bool = True


@router.post("/sessions/{sid}/script", response_model=Script)
async def compose_script(sid: str, req: ComposeRequest) -> Script:
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")

    # Each compose is a "run": bump the counter so the game gets scarier and
    # scarier and the asset seed changes, then persist so it survives restarts.
    pm = sess.player_model
    pm.runs += 1
    player_store.save(pm)

    recent = sess.last_affect if req.use_recent_affect else None
    # Composition can be a multi-second Claude round trip (or CPU work) — run it
    # off the event loop so one compose doesn't stall other requests/streams.
    script = await anyio.to_thread.run_sync(get_composer().compose, sid, sess.seed, pm, req.length, recent)

    if req.fresh_assets:
        run_seed = stable_seed(sid, pm.runs)
        resolved = resolve_script_assets(script, run_seed, script.escalation)
        script.assets = {k: [a.model_dump() for a in v] for k, v in resolved.items()}

    sess.script = script
    sess.beat_index = 0
    return script


@router.get("/sessions/{sid}/script", response_model=Script)
async def get_script(sid: str) -> Script:
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")
    if sess.script is None:
        raise HTTPException(409, "no script yet; POST /script to compose one")
    return sess.script


class ReactionRequest(BaseModel):
    """How the player reacted to a moment (a Beat, or an explicit DataPoint set)."""

    beat_index: int | None = None
    datapoint_ids: list[str] = Field(default_factory=list)
    affect_before: AffectState | None = None
    affect_peak: AffectState | None = None
    # Optional explicit reward in [0,1]; else derived from the affect delta.
    reward: float | None = None
    # Optional computer-vision affect (webcam) to fuse later; accepted now.
    cv_affect: dict | None = None


class LearnSummary(BaseModel):
    player_id: str
    reactions_seen: int
    reward: float
    updated_datapoints: list[str]
    top_datapoints: list[tuple[str, float]]


@router.post("/sessions/{sid}/reactions", response_model=LearnSummary)
async def post_reaction(sid: str, r: ReactionRequest) -> LearnSummary:
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")

    # Which DataPoints was the player reacting to?
    dp_ids = r.datapoint_ids
    if not dp_ids and r.beat_index is not None and sess.script:
        beat = sess.script.beat(r.beat_index)
        dp_ids = beat.datapoint_ids if beat else []
    if not dp_ids:
        raise HTTPException(422, "provide datapoint_ids or a valid beat_index with a composed script")

    # Reward: explicit, else the rise in fear/arousal this moment produced.
    if r.reward is not None:
        reward = max(0.0, min(1.0, r.reward))
    elif r.affect_before and r.affect_peak:
        fear_delta = r.affect_peak.fear - r.affect_before.fear
        arousal_delta = r.affect_peak.arousal - r.affect_before.arousal
        reward = max(0.0, min(1.0, 0.5 + 0.6 * fear_delta + 0.4 * arousal_delta))
    else:
        reward = 0.6  # a neutral-positive default if no affect provided

    pm: PlayerModel = sess.player_model
    pm.observe(dp_ids, reward, fears=sess.seed.fears)
    player_store.save(pm)  # persist -> improves across restarts

    top = sorted(pm.datapoint_scores.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return LearnSummary(player_id=pm.player_id, reactions_seen=pm.reactions_seen,
                        reward=round(reward, 3), updated_datapoints=dp_ids,
                        top_datapoints=[(k, round(v, 3)) for k, v in top])


@router.get("/players/{player_id}", response_model=PlayerModel)
async def get_player(player_id: str = Path(..., pattern=PLAYER_ID)) -> PlayerModel:
    return player_store.load(player_id)


@router.get("/sessions/{sid}/assets/manifest")
async def get_asset_manifest(sid: str) -> dict:
    """The licensing/attribution manifest for the current script's assets."""
    from engine.assets.resolver import license_manifest

    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")
    if sess.script is None:
        raise HTTPException(409, "no script yet; POST /script first")
    return {"manifest": license_manifest(sess.script.assets)}
