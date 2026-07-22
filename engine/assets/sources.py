"""Asset sources — where a variant for a DataPoint comes from.

`ProceduralAssetSource` is the default: it synthesises an infinite space of asset
*variants* from a seed (palettes, geometry/texture seeds, synth params, animation
clips), so every run differs and nothing heavy ships on disk. `RemoteAssetSource`
is the seam for open-asset libraries (Poly Haven textures/models, Freesound audio,
Mixamo-style animations); it activates when configured and otherwise degrades to
procedural. `get_asset_source()` picks from config.
"""
from __future__ import annotations

import logging
import random

from engine.assets.models import AssetKind, MediaAsset
from engine.config import get_settings

log = logging.getLogger("engine.assets")

# Procedural variant vocabularies. Combined with a per-run seed these give a
# large space of distinct-but-coherent assets without any media files.
_PALETTES = [
    ["#12151a", "#2a2f38"], ["#1a1210", "#3a2320"], ["#0d0f0d", "#243024"],
    ["#141019", "#33223a"], ["#0e1416", "#20343a"], ["#1a1414", "#402020"],
]
_MAP_LAYOUTS = ["corridor", "maze", "atrium", "room", "catacomb", "ward"]
_SILHOUETTES = ["tall-thin", "low-mass", "sprinting-mass", "hunched", "elongated", "swarm"]
_ANIM_CLIPS = ["stalk", "lurch", "crawl", "sprint", "twitch", "sway", "convulse", "drag"]
_IMG_MOTIFS = ["static", "face", "corridor", "symbol", "stain", "figure", "eye"]
_SOUND_SYNTHS = ["drone", "stinger", "whisper", "scuttle", "heartbeat", "wind", "choir", "metal"]
_MODEL_KINDS = ["wheelchair", "gurney", "locker", "statue", "cross", "chair", "cage", "pipe"]


class AssetSource:
    name = "base"

    def fetch(self, kind: AssetKind, seed: int, mood: str, tags: list[str],
              fears: list[str], escalation: float) -> MediaAsset:
        raise NotImplementedError


class ProceduralAssetSource(AssetSource):
    name = "procedural"

    def fetch(self, kind: AssetKind, seed: int, mood: str, tags: list[str],
              fears: list[str], escalation: float) -> MediaAsset:
        rng = random.Random(seed)
        pick = lambda xs: xs[rng.randrange(len(xs))]  # noqa: E731
        pal = pick(_PALETTES)
        # Escalation nudges variants toward more intense choices.
        intensity = min(1.0, 0.3 + 0.5 * escalation + 0.2 * rng.random())

        base = dict(id=f"{kind}_{seed & 0xffffff:06x}", kind=kind, source="procedural",
                    tags=list(tags), license="generated (CC0-equivalent)", seed=seed)

        if kind == "map":
            params = {"layout": pick(_MAP_LAYOUTS), "palette": pal, "geometry_seed": rng.randrange(1 << 30),
                      "decay": round(rng.random(), 2), "fog": round(0.2 + 0.6 * intensity, 2),
                      "light_level": round(max(0.05, 0.6 - 0.4 * intensity), 2)}
            name = f"{params['layout']} ({seed & 0xfff:03x})"
        elif kind == "character":
            params = {"silhouette": pick(_SILHOUETTES), "palette": pal, "height": round(1.4 + 1.4 * rng.random(), 2),
                      "texture_seed": rng.randrange(1 << 30), "aggression": round(intensity, 2),
                      "speed": round(0.4 + 1.4 * intensity, 2)}
            name = f"{params['silhouette']} stalker"
        elif kind == "animation":
            params = {"clip": pick(_ANIM_CLIPS), "speed": round(0.6 + 1.2 * intensity, 2),
                      "jitter": round(0.1 + 0.6 * rng.random(), 2), "loop": True, "rig_seed": rng.randrange(1 << 30)}
            name = f"anim:{params['clip']}"
        elif kind == "image":
            params = {"motif": pick(_IMG_MOTIFS), "palette": pal, "noise_seed": rng.randrange(1 << 30),
                      "grain": round(0.3 + 0.5 * intensity, 2)}
            name = f"img:{params['motif']}"
        elif kind == "sound":
            synth = pick(_SOUND_SYNTHS)
            params = {"synth": synth, "hz": round(35 + rng.random() * 180, 1), "reverb": round(0.3 + 0.5 * rng.random(), 2),
                      "mod": round(rng.random(), 2), "gain": round(0.3 + 0.5 * intensity, 2)}
            name = f"snd:{synth}"
        else:  # model / prop
            params = {"mesh": f"proc:{pick(_MODEL_KINDS)}", "palette": pal, "scale": round(0.7 + rng.random(), 2),
                      "mesh_seed": rng.randrange(1 << 30)}
            name = params["mesh"]

        return MediaAsset(name=name, params=params, **base)


class RemoteAssetSource(AssetSource):
    """Fetch from configured open-asset libraries (Poly Haven, Freesound, etc.).

    Falls back to procedural per asset until a library integration is wired.
    Structured so a real integration is a drop-in: implement `_query(...)`.
    """

    name = "remote"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._fallback = ProceduralAssetSource()

    def _query(self, kind: AssetKind, mood: str, tags: list[str], fears: list[str]) -> MediaAsset | None:
        # No library configured yet -> signal "use fallback".
        return None

    def fetch(self, kind, seed, mood, tags, fears, escalation) -> MediaAsset:
        try:
            got = self._query(kind, mood, tags, fears)
            if got is not None:
                return got
        except Exception as exc:  # noqa: BLE001 — never break a run on a fetch error
            log.warning("Remote asset fetch failed (%s); using procedural.", exc)
        return self._fallback.fetch(kind, seed, mood, tags, fears, escalation)


def get_asset_source() -> AssetSource:
    if get_settings().asset_source == "remote":
        try:
            return RemoteAssetSource()
        except Exception as exc:  # noqa: BLE001
            log.warning("Remote asset source unavailable (%s); using procedural.", exc)
    return ProceduralAssetSource()
