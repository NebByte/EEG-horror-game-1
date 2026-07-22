from __future__ import annotations

from fastapi import APIRouter

from engine import __version__
from engine.config import get_settings
from engine.generative.pipeline import get_provider

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
        "asset_provider": get_provider().name,
    }
