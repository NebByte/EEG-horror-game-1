from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from engine.eeg.affect import fuse_cv, infer_affect
from engine.eeg.artifacts import assess_quality
from engine.eeg.calibration import apply_baseline, compute_baseline
from engine.experience.state import store
from engine.schemas import CvAffect, EEGChunk

log = logging.getLogger("engine.api.eeg")
router = APIRouter(prefix="/sessions", tags=["eeg"])


def _step(sid: str, chunk: EEGChunk, cv: CvAffect | None = None, poor_signal: int = 0) -> dict:
    """Hot path: EEG (+optional CV) -> affect -> directive, with calibration and
    signal-quality gating. Low-confidence windows don't move the director."""
    sess = store.get(sid)
    if sess is None:
        raise KeyError(sid)

    quality = assess_quality(chunk, poor_signal)
    affect = apply_baseline(infer_affect(chunk), sess.baseline)
    affect = fuse_cv(affect, cv)

    if quality.confidence < 0.3 and sess.last_directive is not None:
        # Too noisy to trust — hold the last directive rather than react to junk.
        directive = sess.last_directive
    else:
        directive = sess.orchestrator.step(affect, sess.bank)
    store.record(sid, affect, directive)
    return {"affect": affect.model_dump(), "directive": directive.model_dump(),
            "quality": quality.model_dump()}


@router.post("/{sid}/eeg")
async def push_eeg(sid: str, chunk: EEGChunk) -> dict:
    try:
        return _step(sid, chunk)
    except KeyError:
        raise HTTPException(404, "session not found")


class CalibrateRequest(BaseModel):
    chunks: list[EEGChunk]


@router.post("/{sid}/calibrate")
async def calibrate(sid: str, req: CalibrateRequest) -> dict:
    """Record a resting baseline so affect is centered on this player."""
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")
    if not req.chunks:
        raise HTTPException(422, "provide at least one resting EEG chunk")
    sess.baseline = compute_baseline(req.chunks)
    return {"baseline": sess.baseline.model_dump(), "windows": len(req.chunks)}


@router.websocket("/{sid}/stream")
async def stream(ws: WebSocket, sid: str) -> None:
    await ws.accept()
    if store.get(sid) is None:
        await ws.send_json({"error": "session not found"})
        await ws.close()
        return
    try:
        while True:
            payload = await ws.receive_json()
            # A frame may carry an EEGChunk plus optional {cv, poor_signal}.
            cv = None
            poor_signal = int(payload.pop("poor_signal", 0) or 0)
            cv_raw = payload.pop("cv", None)
            if cv_raw:
                try:
                    cv = CvAffect.model_validate(cv_raw)
                except Exception:
                    cv = None
            try:
                chunk = EEGChunk.model_validate(payload)
            except Exception as exc:  # noqa: BLE001
                await ws.send_json({"error": f"invalid EEGChunk: {exc}"})
                continue
            await ws.send_json(_step(sid, chunk, cv=cv, poor_signal=poor_signal))
    except WebSocketDisconnect:
        log.info("stream closed for session %s", sid)
