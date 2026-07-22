"""Environment-driven settings for the engine.

All values have sensible defaults so the prototype runs offline with no cloud
credentials and no headset. Override via environment variables or a `.env` file.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- API ---
    environment: str = "development"
    api_prefix: str = "/v1"

    # --- Generative asset provider ---
    # "mock"  -> fully offline, deterministic (default)
    # "vertex" -> Google Cloud Vertex AI (optional, requires extra deps + creds)
    asset_provider: str = "mock"

    # --- Google Cloud (only used when asset_provider == "vertex") ---
    gcp_project: str = ""
    gcp_location: str = "us-central1"
    vertex_text_model: str = "gemini-2.5-flash"
    vertex_image_model: str = "gemini-2.5-flash-image"
    vertex_music_model: str = "lyria-002"
    audio_provider: str = "none"
    google_application_credentials: str = ""
    gcs_bucket: str = ""

    # --- Architect (the "script" composer) ---
    # "mock"     -> deterministic offline composer weighted by the player model
    # "anthropic"-> Claude composes the script (needs anthropic SDK + API key)
    architect_provider: str = "mock"
    architect_model: str = "claude-opus-4-8"
    anthropic_api_key: str = ""
    # Where per-player learning models are persisted (JSON).
    player_data_dir: str = "data/players"

    # --- EEG signal processing ---
    eeg_sample_rate_hz: int = 256
    eeg_window_seconds: float = 2.0

    # --- Safety ---
    # Sustained stress above this ceiling triggers the experience back-off.
    stress_safety_ceiling: float = 0.9


@lru_cache
def get_settings() -> Settings:
    return Settings()
