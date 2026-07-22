"""FastAPI application: wires the routers under API_PREFIX and serves the web game.

Run with:  uvicorn engine.main:app --reload
Then open: http://localhost:8000/  (the WebGL horror client)
           http://localhost:8000/docs  (interactive API)
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine.api import architect, eeg, health, sessions
from engine.config import get_settings

logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(
    title="EEG Horror Engine",
    version="0.1.0",
    description="Adaptive horror experience driven by live EEG affect signals.",
)

# Open CORS so any local game client (web, Unity, Unreal) can drive the engine.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

prefix = settings.api_prefix
app.include_router(health.router, prefix=prefix)
app.include_router(sessions.router, prefix=prefix)
app.include_router(eeg.router, prefix=prefix)
app.include_router(architect.router, prefix=prefix)

# Serve the browser/WebGL game client (the engine that replaced DirectX).
# Mounted at root so the client's relative asset paths (js/game.js) resolve.
# The API routers above are registered first, so they always take precedence.
_WEB = Path(__file__).resolve().parent.parent / "web"
if _WEB.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB), html=True), name="game")
