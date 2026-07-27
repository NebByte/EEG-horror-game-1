"""Demo: every run fetches fresh assets and gets scarier and scarier.

Composes the Script three times for the same player (three "runs"). Each run
bumps the escalation (higher tension ceiling, faster pacing, more intense
elements) and resolves a *different* set of media assets.

    python scripts/demo_escalation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.architect.composer import MockComposer  # noqa: E402
from engine.architect.learning import PlayerModel  # noqa: E402
from engine.assets.resolver import resolve_script_assets  # noqa: E402
from engine.schemas import SeedProfile  # noqa: E402


def main() -> None:
    seed = SeedProfile(theme="abandoned asylum", fears=["darkness", "being chased"], intensity_preference=0.7)
    pm = PlayerModel(player_id="demo")
    composer = MockComposer()

    for _ in range(3):
        pm.runs += 1  # a run = opening/restarting the game
        script = composer.compose("sess", seed, pm, length=8)
        run_seed = abs(hash(f"sess:{pm.runs}")) % (2**31)
        assets = resolve_script_assets(script, run_seed, script.escalation)

        print(f"=== RUN {pm.runs} ===")
        print(f"  escalation={script.escalation:.2f}  peak_tension={max(script.tension_curve):.2f}  "
              f"beat_len={script.beats[0].duration_s:.0f}s")
        # Show the resolved assets for the first encounter this run.
        enc = next((dp for b in script.beats for dp in b.datapoint_ids if dp.startswith("encounter.")), None)
        if enc and enc in assets:
            for a in assets[enc]:
                p = a.params
                detail = p.get("silhouette") or p.get("clip") or p.get("synth") or ""
                print(f"    {enc:<26} -> {a.kind:<10} {a.id}  ({detail})")
        # Show one fresh map + sound.
        space = next((dp for b in script.beats for dp in b.datapoint_ids if dp.startswith("space.")), None)
        if space and space in assets and assets[space]:
            m = assets[space][0]
            print(f"    {space:<26} -> map        {m.id}  (layout={m.params.get('layout')}, fog={m.params.get('fog')})")
        print()

    print("Each run: higher escalation, faster beats, and different resolved assets.")


if __name__ == "__main__":
    main()
