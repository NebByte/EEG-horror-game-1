"""Engine-run EEG source loops.

Runs *our* MindLink adapter (or the simulator) server-side, feeding a session's
affect/directive continuously. The engine process has the serial-port access to
the headset (it runs on the player's machine), so the browser can just ask the
engine to "use MindLink on COM7" and then read the resulting affect — no browser
Bluetooth, our signal pipeline throughout.
"""
from __future__ import annotations

import asyncio
import logging
import time

from engine.eeg.affect import infer_affect
from engine.eeg.artifacts import assess_quality
from engine.eeg.calibration import apply_baseline
from engine.eeg.sources import make_source
from engine.experience.state import store

log = logging.getLogger("engine.eeg.runner")

_tasks: dict[str, asyncio.Task] = {}


async def _loop(sid: str, kind: str, port: str, baudrate: int, window: float) -> None:
    sess = store.get(sid)
    if sess is None:
        return
    # Build our source; on hardware failure, degrade to the simulator so the
    # game keeps running (and record why).
    try:
        src = make_source(kind, port=port, baudrate=baudrate)
        sess.eeg_source = kind
        sess.eeg_source_error = None
    except Exception as exc:  # noqa: BLE001
        log.warning("EEG source %s unavailable (%s); using simulator.", kind, exc)
        src = make_source("simulator")
        sess.eeg_source = "simulator"
        sess.eeg_source_error = f"{kind} unavailable: {exc}"

    try:
        while store.get(sid) is not None:
            t0 = time.monotonic()
            try:
                chunk = await src.read(window)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — a headset disconnect mid-stream
                if sess.eeg_source == "simulator":
                    raise  # simulator failing is unexpected; let it bubble
                log.warning("EEG source read failed (%s); switching to simulator.", exc)
                try:
                    await src.close()
                except Exception:  # noqa: BLE001
                    pass
                src = make_source("simulator")
                sess.eeg_source = "simulator"
                sess.eeg_source_error = f"hardware read failed: {exc}"
                continue
            poor = int(getattr(src, "poor_signal", 0) or 0)
            affect = apply_baseline(infer_affect(chunk), sess.baseline)
            quality = assess_quality(chunk, poor)
            # Honor the central SignalQuality gating contract (ok = strictly usable).
            if quality.ok or sess.last_directive is None:
                directive = sess.orchestrator.step(affect, sess.bank)
            else:
                directive = sess.last_directive  # too noisy — hold
            store.record(sid, affect, directive)
            sess.last_quality = quality.model_dump()
            # Pace to real time: a real headset's read() already blocks ~`window`
            # seconds; the offline simulator returns instantly, so sleep the
            # remainder — this also yields the event loop so requests stay served.
            elapsed = time.monotonic() - t0
            if elapsed < window:
                await asyncio.sleep(window - elapsed)
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001
        log.exception("EEG source loop crashed for session %s", sid)
    finally:
        try:
            await src.close()
        except Exception:  # noqa: BLE001
            pass


def start(sid: str, kind: str, port: str = "COM7", baudrate: int = 57600, window: float = 1.0) -> None:
    stop(sid)
    _tasks[sid] = asyncio.create_task(_loop(sid, kind, port, baudrate, window))


def stop(sid: str) -> None:
    task = _tasks.pop(sid, None)
    if task is not None:
        task.cancel()


def is_running(sid: str) -> bool:
    task = _tasks.get(sid)
    return task is not None and not task.done()
