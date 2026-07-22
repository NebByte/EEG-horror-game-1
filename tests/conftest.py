"""Test fixtures: keep the suite offline, deterministic, and free.

The project's `.env` may enable the live Claude architect and remote asset
libraries. Tests must never depend on network or a key (or spend money), so we
force the offline mock composer + procedural assets for the whole test session.
Env vars take precedence over `.env` in pydantic-settings.
"""
import os

os.environ["ARCHITECT_PROVIDER"] = "mock"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ASSET_SOURCE"] = "procedural"

from engine.config import get_settings  # noqa: E402

get_settings.cache_clear()
