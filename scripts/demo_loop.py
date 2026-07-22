"""End-to-end offline demo — no server, no cloud, no headset.

Runs the whole loop in-process: simulate escalating EEG -> infer affect ->
build a mock asset bank -> let the director emit directives, and watch the
tension curve rise and the stress safety back-off engage.

    python scripts/demo_loop.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.eeg import EEGSimulator, infer_affect  # noqa: E402
from engine.experience.orchestrator import Orchestrator  # noqa: E402
from engine.generative.pipeline import AssetPipeline  # noqa: E402
from engine.schemas import SeedProfile  # noqa: E402


async def main() -> None:
    seed = SeedProfile(theme="abandoned asylum", fears=["darkness", "isolation"], intensity_preference=0.7)
    print(f"Seed: {seed.theme}  fears={seed.fears}\n")

    bank = await AssetPipeline().build_bank("demo", seed)
    print(f"Generated bank: {len(bank.characters)} characters, "
          f"{len(bank.soundscapes)} soundscapes, {len(bank.maps)} maps\n")

    director = Orchestrator(seed)
    sim = EEGSimulator(seed=7)

    print(f"{'step':>4}  {'fear':>5} {'stress':>6} {'arousal':>7}  {'mood':<7} "
          f"{'intensity':>9}  {'bpm':>5}  stalker")
    print("-" * 74)

    # 18 windows: arousal ramps up, plateaus at terror, then a lull.
    for i in range(18):
        if i < 12:
            arousal = min(1.0, 0.15 + i * 0.09)
        else:
            arousal = max(0.1, 1.0 - (i - 11) * 0.18)  # relief phase
        valence = -0.7 if arousal > 0.4 else 0.3
        chunk = sim.window(2.0, arousal=arousal, valence=valence)
        affect = infer_affect(chunk)
        d = director.step(affect, bank)
        chr_name = next((c.name for c in bank.characters if c.id == d.spawn_character_id), "-")
        flag = "  <- SAFETY BACK-OFF" if d.safety_backoff else ""
        print(f"{i:>4}  {affect.fear:>5.2f} {affect.stress:>6.2f} {affect.arousal:>7.2f}  "
              f"{d.mood:<7} {d.intensity:>9.2f}  {d.heartbeat_bpm:>5.0f}  {chr_name}{flag}")

    print("\nLoop complete — affect drove the director end-to-end, offline.")


if __name__ == "__main__":
    asyncio.run(main())
