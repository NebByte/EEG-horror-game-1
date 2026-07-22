from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from engine.experience.state import store
from engine.generative.pipeline import AssetPipeline
from engine.schemas import AssetBank, SeedProfile

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    seed: SeedProfile = SeedProfile()
    # Stable id so the learning model follows the same player across sessions.
    player_id: str = "anon"


class SessionSummary(BaseModel):
    id: str
    seed: SeedProfile
    has_bank: bool
    generating: bool
    last_affect: dict | None = None
    last_directive: dict | None = None


@router.post("", response_model=SessionSummary)
async def create_session(req: CreateSessionRequest) -> SessionSummary:
    sess = store.create(req.seed, player_id=req.player_id)
    return SessionSummary(id=sess.id, seed=sess.seed, has_bank=False, generating=False)


async def _generate(sid: str) -> None:
    sess = store.get(sid)
    if sess is None:
        return
    sess.generating = True
    try:
        sess.bank = await AssetPipeline().build_bank(sid, sess.seed)
    finally:
        sess.generating = False


@router.post("/{sid}/generate", response_model=SessionSummary)
async def generate_assets(sid: str, background: BackgroundTasks) -> SessionSummary:
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")
    background.add_task(_generate, sid)
    return SessionSummary(id=sid, seed=sess.seed, has_bank=sess.bank is not None, generating=True)


@router.get("/{sid}", response_model=SessionSummary)
async def get_session(sid: str) -> SessionSummary:
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")
    return SessionSummary(
        id=sess.id,
        seed=sess.seed,
        has_bank=sess.bank is not None,
        generating=sess.generating,
        last_affect=sess.last_affect.model_dump() if sess.last_affect else None,
        last_directive=sess.last_directive.model_dump() if sess.last_directive else None,
    )


@router.get("/{sid}/assets", response_model=AssetBank)
async def get_assets(sid: str) -> AssetBank:
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")
    if sess.bank is None:
        raise HTTPException(409, "assets not generated yet; POST /generate first")
    return sess.bank


@router.get("/{sid}/directive")
async def get_directive(sid: str) -> dict:
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")
    if sess.last_directive is None:
        raise HTTPException(409, "no directive yet; push EEG first")
    return sess.last_directive.model_dump()
