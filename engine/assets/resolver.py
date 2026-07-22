"""Resolve a Script's DataPoints to concrete, per-run media assets.

Each DataPoint category needs certain asset kinds (a space needs a map, an
encounter needs a character + animation, etc.). The resolver seeds every asset
from `(run_seed, datapoint_id, kind)` so a given run is internally consistent but
*different from every other run* — that's "fetch different assets every time".
"""
from __future__ import annotations

from engine.architect.datapoints import get_datapoint
from engine.assets.models import AssetKind, MediaAsset
from engine.assets.sources import AssetSource, get_asset_source

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
    return abs(hash("::".join(str(p) for p in parts))) % (2**31)


class AssetResolver:
    def __init__(self, source: AssetSource | None = None) -> None:
        self.source = source or get_asset_source()

    def resolve_datapoint(self, dp_id: str, run_seed: int, mood: str,
                          fears: list[str], escalation: float) -> list[MediaAsset]:
        dp = get_datapoint(dp_id)
        if dp is None:
            return []
        assets: list[MediaAsset] = []
        for kind in _KINDS_FOR_CATEGORY.get(dp.category, []):
            s = _seed(run_seed, dp_id, kind)
            assets.append(self.source.fetch(kind, s, mood, dp.tags, fears, escalation))
        return assets

    def resolve_script(self, script, run_seed: int, escalation: float) -> dict[str, list[MediaAsset]]:
        """Return {datapoint_id -> [MediaAsset,...]} for every DataPoint in the
        script, resolved fresh for this run."""
        out: dict[str, list[MediaAsset]] = {}
        for beat in script.beats:
            for dp_id in beat.datapoint_ids:
                if dp_id in out:
                    continue
                out[dp_id] = self.resolve_datapoint(dp_id, run_seed, beat.mood, script.seed.fears, escalation)
        return out


def resolve_script_assets(script, run_seed: int, escalation: float,
                          source: AssetSource | None = None) -> dict[str, list[MediaAsset]]:
    return AssetResolver(source).resolve_script(script, run_seed, escalation)
