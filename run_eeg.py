import asyncio, sys
sys.path.insert(0,".")
from engine.eeg.gateway import create_session, generate_assets, run_gateway
from engine.eeg.sources import make_source
import httpx

async def main():
    for _ in range(30):
        try: httpx.get("http://localhost:8000/v1/health",timeout=1.0); break
        except Exception: await asyncio.sleep(0.5)
    sid = await create_session("http://localhost:8000", seed={"theme":"abandoned asylum","fears":["darkness","being watched"]})
    await generate_assets("http://localhost:8000", sid)
    print("session", sid, "- streaming YOUR live EEG (COM7)...\n")
    src = make_source("neurosky", port="COM7", baudrate=57600)
    n=0
    async for frame in run_gateway(src, sid, "ws://localhost:8000", window_seconds=2.0):
        a=frame["affect"]
        print(f"[{n}] poor_sig~ok  fear={a['fear']:.2f} stress={a['stress']:.2f} arousal={a['arousal']:.2f} eng={a['engagement']:.2f} relax={a['relaxation']:.2f} -> intensity={frame['intensity']:.2f} spawn={frame['spawn_character_id']} ambient={frame['ambient_sound_id']} {'BACKOFF' if frame['safety_backoff'] else ''}")
        n+=1
        if n>=8: break
    await src.close()
    print("\nLIVE BRAIN -> HORROR ENGINE: OK")

try:
    asyncio.run(asyncio.wait_for(main(), timeout=45))
except asyncio.TimeoutError:
    print("timed out")
