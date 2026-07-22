from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from engine.eeg.affect import infer_affect
from engine.experience.state import store
from engine.schemas import EEGChunk

log = logging.getLogger("engine.api.eeg")
router = APIRouter(prefix="/sessions", tags=["eeg"])


def _step(sid: str, chunk: EEGChunk) -> dict:
    """Shared hot path: EEG chunk -> affect -> directive, recorded on the session."""
    sess = store.get(sid)
    if sess is None:
        raise KeyError(sid)
    affect = infer_affect(chunk)
    directive = sess.orchestrator.step(affect, sess.bank)
    store.record(sid, affect, directive)
    return {"affect": affect.model_dump(), "directive": directive.model_dump()}


@router.post("/{sid}/eeg")
async def push_eeg(sid: str, chunk: EEGChunk) -> dict:
    try:
        return _step(sid, chunk)
    except KeyError:
        raise HTTPException(404, "session not found")


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
            try:
                chunk = EEGChunk.model_validate(payload)
            except Exception as exc:  # noqa: BLE001
                await ws.send_json({"error": f"invalid EEGChunk: {exc}"})
                continue
            await ws.send_json(_step(sid, chunk))
    except WebSocketDisconnect:
        log.info("stream closed for session %s", sid)
