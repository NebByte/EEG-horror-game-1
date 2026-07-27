from __future__ import annotations

import logging

import anyio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

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
    # _step does CPU-bound FFT/artifact work — keep it off the event loop.
    try:
        return await anyio.to_thread.run_sync(_step, sid, chunk)
    except KeyError:
        raise HTTPException(404, "session not found") from None


class CalibrateRequest(BaseModel):
    # Bounded so a single POST can't drive unbounded CPU/memory.
    chunks: list[EEGChunk] = Field(..., min_length=1, max_length=64)


@router.post("/{sid}/calibrate")
async def calibrate(sid: str, req: CalibrateRequest) -> dict:
    """Record a resting baseline so affect is centered on this player."""
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")
    try:
        sess.baseline = compute_baseline(req.chunks)
    except ValueError as exc:  # no usable samples in any chunk
        raise HTTPException(422, str(exc)) from None
    return {"baseline": sess.baseline.model_dump(), "windows": len(req.chunks)}


class EegSourceRequest(BaseModel):
    # "mindlink"/"neurosky" (our serial adapter) or "simulator".
    kind: str = Field("simulator", pattern=r"^(mindlink|neurosky|mindwave|simulator)$")
    port: str = Field("COM7", max_length=64)
    baudrate: int = Field(57600, ge=1200, le=921600)


@router.post("/{sid}/eeg/source")
async def start_eeg_source(sid: str, req: EegSourceRequest) -> dict:
    """Start an engine-run EEG source (our MindLink adapter or the simulator)
    feeding this session. Read the resulting affect via GET /sessions/{id}."""
    sess = store.get(sid)
    if sess is None:
        raise HTTPException(404, "session not found")
    from engine.eeg import runner

    runner.start(sid, req.kind, req.port, req.baudrate)
    return {"ok": True, "kind": req.kind, "port": req.port}


@router.delete("/{sid}/eeg/source")
async def stop_eeg_source(sid: str) -> dict:
    from engine.eeg import runner

    runner.stop(sid)
    sess = store.get(sid)
    if sess is not None:
        sess.eeg_source = None
    return {"ok": True}


@router.websocket("/{sid}/stream")
async def stream(ws: WebSocket, sid: str) -> None:
    await ws.accept()
    if store.get(sid) is None:
        await ws.send_json({"error": "session not found"})
        await ws.close()
        return
    try:
        while True:
            # Everything in the loop is client-controlled — a malformed frame must
            # produce an {"error": ...} reply and keep the stream alive, never crash it.
            try:
                payload = await ws.receive_json()
            except ValueError:
                await ws.send_json({"error": "invalid JSON frame"})
                continue
            if not isinstance(payload, dict):
                await ws.send_json({"error": "frame must be a JSON object"})
                continue
            # A frame may carry an EEGChunk plus optional {cv, poor_signal}.
            cv = None
            try:
                poor_signal = int(payload.pop("poor_signal", 0) or 0)
            except (TypeError, ValueError):
                poor_signal = 0
            cv_raw = payload.pop("cv", None)
            if cv_raw:
                try:
                    cv = CvAffect.model_validate(cv_raw)
                except Exception:  # noqa: BLE001
                    cv = None
            try:
                chunk = EEGChunk.model_validate(payload)
            except Exception as exc:  # noqa: BLE001
                await ws.send_json({"error": f"invalid EEGChunk: {exc}"})
                continue
            try:
                result = await anyio.to_thread.run_sync(_step, sid, chunk, cv, poor_signal)
            except KeyError:  # session evicted mid-stream
                await ws.send_json({"error": "session not found"})
                continue
            await ws.send_json(result)
    except WebSocketDisconnect:
        log.info("stream closed for session %s", sid)
