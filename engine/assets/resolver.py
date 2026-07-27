"""Resolve a Script's DataPoints to concrete, per-run media assets.

Each DataPoint category needs certain asset kinds (a space needs a map, an
encounter needs a character + animation, etc.). The resolver seeds every asset
from `(run_seed, datapoint_id, kind)` so a given run is internally consistent but
*different from every other run* — that's "fetch different assets every time".
"""
from __future__ import annotations

import logging

from engine.architect.datapoints import DataPoint, get_datapoint
from engine.assets.models import AssetKind, MediaAsset
from engine.assets.sources import AssetSource, get_asset_source

log = logging.getLogger("engine.assets.resolver")

# Which asset kinds each DataPoint category resolves to.
_KINDS_FOR_CATEGORY: dict[str, list[AssetKind]] = {
    "space": ["map"],
    "encounter": ["character", "animation"],
    "audio": ["sound"],
    "prop": ["model", "image"],
    "lighting": [],
    "event": [],
}


def _seed(*parts) -> int:
    from engine.util import stable_seed

    return stable_seed(*parts)


class AssetResolver:
    def __init__(self, source: AssetSource | None = None) -> None:
        self.source = source or get_asset_source()

    def resolve_datapoint(self, dp_id: str, run_seed: int, mood: str, fears: list[str],
                          escalation: float, lookup: dict[str, DataPoint] | None = None) -> list[MediaAsset]:
        dp = (lookup or {}).get(dp_id) or get_datapoint(dp_id)
        if dp is None:
            return []
        assets: list[MediaAsset] = []
        for kind in _KINDS_FOR_CATEGORY.get(dp.category, []):
            s = _seed(run_seed, dp_id, kind)
            assets.append(self.source.fetch(kind, s, mood, dp.tags, fears, escalation))
        return assets

    def resolve_script(self, script, run_seed: int, escalation: float,
                       catalog: list[DataPoint] | None = None) -> dict[str, list[MediaAsset]]:
        """Return {datapoint_id -> [MediaAsset,...]} for every DataPoint in the
        script, resolved fresh for this run. Bred/synthesized DataPoints are
        resolved from the script's own `datapoints` (or an explicit catalog)."""
        lookup: dict[str, DataPoint] = {d.id: d for d in (catalog or [])}
        for dp_id, raw in (getattr(script, "datapoints", None) or {}).items():
            if dp_id not in lookup:
                try:
                    lookup[dp_id] = DataPoint.model_validate(raw)
                except Exception as exc:  # noqa: BLE001
                    log.warning("failed to validate bred datapoint %s: %s", dp_id, exc)
        out: dict[str, list[MediaAsset]] = {}
        for beat in script.beats:
            for dp_id in beat.datapoint_ids:
                if dp_id in out:
                    continue
                out[dp_id] = self.resolve_datapoint(dp_id, run_seed, beat.mood, script.seed.fears, escalation, lookup)
        return out


def resolve_script_assets(script, run_seed: int, escalation: float,
                          source: AssetSource | None = None,
                          catalog: list[DataPoint] | None = None) -> dict[str, list[MediaAsset]]:
    return AssetResolver(source).resolve_script(script, run_seed, escalation, catalog)


def license_manifest(assets: dict[str, list]) -> list[dict]:
    """A dedup'd attribution/licensing manifest for a run's resolved assets.

    Accepts either MediaAsset objects or their dumped dicts (as stored on a
    Script). Only non-procedural, real-media assets need attribution."""
    seen: dict[str, dict] = {}
    for media in assets.values():
        for a in media:
            d = a if isinstance(a, dict) else a.model_dump()
            if d.get("source") == "procedural":
                continue
            key = d.get("source_url") or d.get("id")
            if key and key not in seen:
                seen[key] = {"name": d.get("name"), "kind": d.get("kind"),
                             "source": d.get("source"), "license": d.get("license"),
                             "attribution": d.get("attribution"), "source_url": d.get("source_url")}
    return list(seen.values())
