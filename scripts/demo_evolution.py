"""Demo: the model breeds new DataPoints from what scares the player.

The player is repeatedly terrified by the crawler + its scuttle sound. The
learning layer (a) links them as an enhance-pair, and (b) breeds brand-new,
personalized DataPoints (mutants + a hybrid) that feed back into the script.

    python scripts/demo_evolution.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.architect.composer import MockComposer  # noqa: E402
from engine.architect.datapoints import CATALOG  # noqa: E402
from engine.architect.evolution import synthesize_for_player  # noqa: E402
from engine.architect.learning import PlayerModel  # noqa: E402
from engine.schemas import SeedProfile  # noqa: E402


def main() -> None:
    seed = SeedProfile(theme="abandoned asylum", fears=["being chased", "darkness"], intensity_preference=0.7)
    pm = PlayerModel(player_id="demo")

    print(f"Base catalog: {len(CATALOG)} DataPoints\n")
    print("Player keeps getting terrified by: the crawler + its scuttle, and the render...")
    for _ in range(9):
        pm.observe(["encounter.crawler", "audio.scuttle"], reward=1.0, fears=seed.fears)
        pm.observe(["encounter.render"], reward=0.95, fears=seed.fears)
        pm.observe(["encounter.distant_figure"], reward=0.1, fears=seed.fears)
    pm.runs = 3

    print(f"\nLearned enhance-pairs for the crawler: {pm.learned_enhances('encounter.crawler')}")

    bred = synthesize_for_player(pm)
    print(f"\nBred {len(bred)} new personalized DataPoints:")
    for d in bred:
        kind = "hybrid (crossover)" if "~x" in d.id else "variant (mutation)"
        print(f"  [{kind}] {d.id}")
        print(f"      name='{d.name}'  intensity={d.base_intensity:.2f}  enhances={d.enhances}")

    print("\nThese feed straight back into the next script:")
    script = MockComposer().compose("sess", seed, pm, length=8)
    bred_used = [d for d in script.datapoints if "~" in d]
    print(f"  script references {len(script.datapoints)} DataPoints, "
          f"{len(bred_used)} of them bred: {bred_used}")
    print(f"  rationale: {script.rationale}")


if __name__ == "__main__":
    main()
