"""The concrete media asset contract."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AssetKind = Literal["map", "model", "character", "image", "sound", "animation"]


class MediaAsset(BaseModel):
    id: str
    kind: AssetKind
    name: str
    # "procedural" | "remote:<library>" | "pack"
    source: str = "procedural"
    # A resolvable URI when the asset is real media; None for pure-procedural
    # assets the client synthesises from `params`.
    uri: str | None = None
    params: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    license: str | None = None
    # Attribution + provenance for a licensing manifest (required by CC-BY etc.).
    attribution: str | None = None
    source_url: str | None = None
    seed: int = 0
