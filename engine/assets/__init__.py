"""Asset resolution & variation — fresh assets every run, plus escalation.

This layer sits between the Architect's abstract DataPoints and concrete media
(maps, models, characters, pictures, sounds, animations). For every run it
resolves each DataPoint to a *different* asset variant, seeded by a per-run seed,
so no two playthroughs look or sound the same. Variants are **procedural** by
default (infinite, offline, kkrieger-style), with hooks for remote open-asset
libraries when configured. Generation stays the rare fallback.
"""

from engine.assets.models import MediaAsset
from engine.assets.resolver import AssetResolver, resolve_script_assets
from engine.assets.sources import ProceduralAssetSource, get_asset_source

__all__ = [
    "MediaAsset",
    "AssetResolver",
    "resolve_script_assets",
    "ProceduralAssetSource",
    "get_asset_source",
]
