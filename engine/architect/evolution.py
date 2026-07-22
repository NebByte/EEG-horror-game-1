"""Evolutionary personalization — the model doesn't just score DataPoints, it
*breeds* new ones from what scares this player.

From the learned per-player model it decides, every run:
  * **enhance** — link DataPoints the player reacts to best *together* (learned
    co-occurrence) so the composer amplifies those pairs;
  * **copy/reuse** — high-scoring DataPoints simply rank higher (handled by the
    composer via `datapoint_scores`);
  * **breed similar** — *mutate* a high scorer into a near-variant, and *cross*
    two high scorers into a hybrid, producing brand-new DataPoints tailored to
    this player. Those synthesized DataPoints join the player's catalog and feed
    back into the next script.

Deterministic per player (seeded by id + reactions + runs) so a run is
reproducible, but it grows and personalizes as more reactions arrive.
"""
from __future__ import annotations

import random

from engine.architect.datapoints import CATALOG, DataPoint
from engine.architect.learning import PlayerModel

MIN_REACTIONS_TO_BREED = 3


def _seed(pm: PlayerModel) -> int:
    return abs(hash((pm.player_id, pm.reactions_seen, pm.runs))) % (2**31)


def _short(dp_id: str) -> str:
    return dp_id.split(".", 1)[1] if "." in dp_id else dp_id


def _mutate_params(params: dict, rng: random.Random) -> dict:
    """A near-variant: jitter numbers, keep structure — a *similar* DataPoint."""
    out: dict = {}
    for k, v in params.items():
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = round(v * rng.uniform(0.8, 1.25), 3) if isinstance(v, float) else max(1, int(v * rng.uniform(0.8, 1.3)))
        elif isinstance(v, list):
            out[k] = list(v)
        else:
            out[k] = v
    out["mutation_seed"] = rng.randrange(1 << 30)
    return out


def mutate(dp: DataPoint, pm: PlayerModel, rng: random.Random, escalation: float) -> DataPoint:
    n = 1 + (rng.randrange(999))
    return DataPoint(
        id=f"{dp.id}~m{n % 97}",
        category=dp.category,
        name=f"{dp.name} (variant)",
        tags=sorted(set(dp.tags) | {"personalized"}),
        base_intensity=max(0.05, min(1.0, dp.base_intensity + rng.uniform(-0.1, 0.15) + 0.1 * escalation)),
        fear_affinity={f: min(1.0, a * rng.uniform(0.9, 1.15)) for f, a in dp.fear_affinity.items()},
        enhances=pm.learned_enhances(dp.id) or list(dp.enhances),
        params=_mutate_params(dp.params, rng),
    )


def crossover(a: DataPoint, b: DataPoint, rng: random.Random) -> DataPoint:
    fear = dict(a.fear_affinity)
    for f, v in b.fear_affinity.items():
        fear[f] = max(fear.get(f, 0.0), v)
    params: dict = {}
    for k in set(a.params) | set(b.params):
        if k in a.params and k in b.params:
            params[k] = a.params[k] if rng.random() < 0.5 else b.params[k]
        else:
            params[k] = a.params.get(k, b.params.get(k))
    params["crossover_seed"] = rng.randrange(1 << 30)
    return DataPoint(
        id=f"{a.id}+{_short(b.id)}~x",
        category=a.category,
        name=f"{a.name} x {b.name}",
        tags=sorted(set(a.tags) | set(b.tags)),
        base_intensity=round((a.base_intensity + b.base_intensity) / 2, 3),
        fear_affinity=fear,
        enhances=sorted(set(a.enhances) | set(b.enhances)),
        params=params,
    )


def synthesize_for_player(pm: PlayerModel, base: list[DataPoint] | None = None) -> list[DataPoint]:
    """Breed new, personalized DataPoints from the player's top performers."""
    base = base or CATALOG
    if pm.reactions_seen < MIN_REACTIONS_TO_BREED:
        return []
    rng = random.Random(_seed(pm))
    escalation = pm.escalation()

    ranked = sorted(base, key=lambda d: pm.score_datapoint(d.id), reverse=True)
    top = [d for d in ranked if pm.score_datapoint(d.id) > 0.5]
    if not top:
        return []

    new: list[DataPoint] = []
    n_mutants = min(len(top), pm.reactions_seen // 3, 5)
    for dp in top[:n_mutants]:
        new.append(mutate(dp, pm, rng, escalation))

    # Cross the two best within the same category into a hybrid.
    if pm.reactions_seen >= 6:
        for cat in ("encounter", "space", "audio"):
            cands = [d for d in top if d.category == cat]
            if len(cands) >= 2:
                new.append(crossover(cands[0], cands[1], rng))
                break
    return new


def _with_learned_enhances(dp: DataPoint, pm: PlayerModel) -> DataPoint:
    learned = pm.learned_enhances(dp.id)
    if not learned:
        return dp
    merged = sorted(set(dp.enhances) | set(learned))
    return dp.model_copy(update={"enhances": merged})


def evolved_catalog(pm: PlayerModel, base: list[DataPoint] | None = None) -> list[DataPoint]:
    """The player's personalized catalog: base DataPoints (with learned enhance
    links merged in) plus the synthesized ones."""
    base = base or CATALOG
    merged_base = [_with_learned_enhances(d, pm) for d in base]
    return merged_base + synthesize_for_player(pm, base)


def catalog_index(catalog: list[DataPoint]) -> dict[str, DataPoint]:
    return {d.id: d for d in catalog}
