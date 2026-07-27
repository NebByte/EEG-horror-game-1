"""Demo: the Architect composes a Script, learns from reactions, and adapts.

Shows the core idea — "the script is the game, and it learns you":
  1. compose a personalized Script from DataPoints (no generation, offline);
  2. simulate the player being terrified by the chase elements and bored by the
     slow watcher, feeding those reactions back into the learning model;
  3. recompose — the new Script leans into what actually scared this player.

    python scripts/demo_architect.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.architect.composer import MockComposer  # noqa: E402
from engine.architect.learning import PlayerModel  # noqa: E402
from engine.schemas import SeedProfile  # noqa: E402


def counts(script) -> dict[str, int]:
    ids = [d for b in script.beats for d in b.datapoint_ids]
    return {k: ids.count(k) for k in ("encounter.crawler", "encounter.render",
                                      "encounter.distant_figure")}


def main() -> None:
    seed = SeedProfile(theme="abandoned asylum", fears=["being chased", "darkness"],
                       intensity_preference=0.7)
    pm = PlayerModel(player_id="demo-player")
    composer = MockComposer()

    print("=== Run 1: first ever session (no history) ===")
    s1 = composer.compose("sess1", seed, pm, length=8)
    print(s1.rationale)
    for b in s1.beats:
        print(f"  beat {b.index} [{b.mood:<6} t={b.target_tension:.2f}]  {b.note}")
    print("  encounter usage:", counts(s1), "\n")

    print("=== Player reacts: the chase TERRIFIES them, the watcher bores them ===")
    for _ in range(8):
        pm.observe(["encounter.crawler", "encounter.render", "audio.scuttle"],
                   reward=1.0, fears=seed.fears)
        pm.observe(["encounter.distant_figure"], reward=0.05, fears=seed.fears)
    print(f"  observed {pm.reactions_seen} reactions")
    print(f"  learned score  crawler={pm.score_datapoint('encounter.crawler'):.2f}  "
          f"render={pm.score_datapoint('encounter.render'):.2f}  "
          f"distant_figure={pm.score_datapoint('encounter.distant_figure'):.2f}\n")

    print("=== Run 2: same player, next time (Claude/Architect re-authors) ===")
    s2 = composer.compose("sess2", seed, pm, length=8)
    print(s2.rationale)
    for b in s2.beats:
        print(f"  beat {b.index} [{b.mood:<6} t={b.target_tension:.2f}]  {b.note}")
    print("  encounter usage:", counts(s2))
    print("\nThe script personalized itself: the chase elements crowd out the "
          "watcher the player didn't fear.")


if __name__ == "__main__":
    main()
