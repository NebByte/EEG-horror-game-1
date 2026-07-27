from __future__ import annotations

from fastapi import APIRouter

from engine import __version__
from engine.config import get_settings
from engine.generative.pipeline import get_provider

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    from engine.architect.composer import get_composer
    from engine.assets.sources import get_asset_source

    src = get_asset_source()
    libs = [getattr(lib, "name", "?") for lib in getattr(src, "libraries", [])]
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
        "asset_provider": get_provider().name,
        "architect": get_composer().name,        # "anthropic" when Claude is live
        "asset_source": src.name,
        "asset_libraries": libs,
    }
