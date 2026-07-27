"""Stream live EEG into a running engine and print the directives it returns.

    python run_eeg.py                 # offline simulator (no hardware)
    python run_eeg.py neurosky COM7   # real NeuroSky headset on COM7

Start the engine first:  uvicorn engine.main:app  (or  python run.py).
"""
import asyncio
import sys

import httpx

from engine.eeg.gateway import create_session, generate_assets, run_gateway
from engine.eeg.sources import make_source

BASE = "http://localhost:8000"
WS = "ws://localhost:8000"


async def main() -> None:
    # Wait for the engine to be up (require a real 200, not just a response).
    for _ in range(30):
        try:
            if httpx.get(f"{BASE}/v1/health", timeout=1.0).status_code == 200:
                break
        except Exception:
            pass
        await asyncio.sleep(0.5)
    else:
        raise RuntimeError(f"engine health check never succeeded at {BASE} — is it running?")

    sid = await create_session(BASE, seed={"theme": "abandoned asylum",
                                           "fears": ["darkness", "being watched"]})
    await generate_assets(BASE, sid)

    # Choose a source: CLI arg, else simulator. Fall back to sim on hardware error.
    kind = sys.argv[1] if len(sys.argv) > 1 else "simulator"
    port = sys.argv[2] if len(sys.argv) > 2 else "COM7"
    try:
        src = make_source(kind, port=port, baudrate=57600)
    except Exception as exc:
        print(f"[!] {kind} unavailable ({exc}); using the offline simulator.")
        src = make_source("simulator")

    print(f"session {sid} — streaming EEG ({kind})...\n")
    n = 0
    try:
        async for frame in run_gateway(src, sid, WS, window_seconds=2.0):
            a = frame["affect"]
            print(f"[{n}] fear={a['fear']:.2f} stress={a['stress']:.2f} "
                  f"arousal={a['arousal']:.2f} relax={a['relaxation']:.2f} "
                  f"-> {frame['mood']} intensity={frame['intensity']:.2f} "
                  f"spawn={frame['spawn_character_id']} "
                  f"{'BACKOFF' if frame['safety_backoff'] else ''}")
            n += 1
            if n >= 8:
                break
    finally:
        await src.close()  # always release the serial connection
    print("\nLIVE BRAIN -> HORROR ENGINE: OK")


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=60))
    except asyncio.TimeoutError:
        print("timed out (is the engine running?)")
