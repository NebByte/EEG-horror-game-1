"""DataPoints — the ingredients the Architect builds a Script from.

Each DataPoint is small and **procedural** (kkrieger-style): it stores *parameters*
(seeds, dimensions, palettes), not baked media, so the whole catalog is tiny and
expands to full assets in RAM at load time. This is the deliberate alternative to
heavy generative calls — the Architect only reaches for generation when the
catalog genuinely can't express what it needs.

`fear_affinity` says which player fears a DataPoint plays on; `enhances` names the
DataPoints it combines with well (so the composer can *amplify* a good element by
pulling in its partners).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["space", "encounter", "audio", "event", "lighting", "prop"]
CATEGORIES: tuple[Category, ...] = ("space", "encounter", "audio", "event", "lighting", "prop")


class DataPoint(BaseModel):
    id: str
    category: Category
    name: str
    tags: list[str] = Field(default_factory=list)
    base_intensity: float = Field(0.4, ge=0.0, le=1.0)
    fear_affinity: dict[str, float] = Field(default_factory=dict)
    enhances: list[str] = Field(default_factory=list)
    # Procedural parameters — expanded to real geometry/audio/textures at load.
    params: dict = Field(default_factory=dict)


def _dp(**kw) -> DataPoint:
    return DataPoint(**kw)


# --------------------------------------------------------------------------- #
# The seed catalog. Small on purpose — the composer's job is combination, and
# the learning layer's job is to learn which combinations scare *this* player.
# --------------------------------------------------------------------------- #
CATALOG: list[DataPoint] = [
    # -- spaces -------------------------------------------------------------- #
    _dp(id="space.narrow_corridor", category="space", name="Narrowing corridor",
        tags=["corridor", "claustrophobia", "confined"], base_intensity=0.35,
        fear_affinity={"isolation": 0.6, "confinement": 0.9, "darkness": 0.4},
        enhances=["lighting.failing_fluorescent", "audio.distant_drip"],
        params={"layout": "corridor", "width_taper": 0.6, "length": 26, "seed": 11}),
    _dp(id="space.open_atrium", category="space", name="Derelict atrium",
        tags=["open", "exposed", "vertical"], base_intensity=0.25,
        fear_affinity={"being watched": 0.7, "isolation": 0.4},
        enhances=["encounter.distant_figure", "lighting.moonshaft"],
        params={"layout": "atrium", "radius": 14, "balconies": 3, "seed": 23}),
    _dp(id="space.flooded_basement", category="space", name="Flooded basement",
        tags=["water", "cold", "submerged", "dark"], base_intensity=0.55,
        fear_affinity={"drowning": 0.9, "darkness": 0.7, "confinement": 0.5},
        enhances=["audio.low_drone", "event.lights_die"],
        params={"layout": "maze", "water_level": 0.4, "length": 20, "seed": 31}),
    _dp(id="space.mirror_room", category="space", name="Room of mirrors",
        tags=["mirror", "doppelganger", "disorienting"], base_intensity=0.5,
        fear_affinity={"being watched": 0.8, "loss of self": 0.7},
        enhances=["encounter.reflection_wrong", "event.brief_glimpse"],
        params={"layout": "room", "mirrors": 6, "seed": 42}),

    # -- encounters ---------------------------------------------------------- #
    _dp(id="encounter.distant_figure", category="encounter", name="Distant figure",
        tags=["stalker", "watcher", "slow"], base_intensity=0.4,
        fear_affinity={"being watched": 0.9, "isolation": 0.5},
        enhances=["audio.heartbeat", "lighting.silhouette_backlight"],
        params={"behaviour": "stalk", "speed": 0.5, "silhouette": "tall-thin", "seed": 7}),
    _dp(id="encounter.crawler", category="encounter", name="The crawler",
        tags=["stalker", "fast", "floor"], base_intensity=0.7,
        fear_affinity={"being chased": 0.9, "confinement": 0.6},
        enhances=["audio.scuttle", "event.sudden_dark"],
        params={"behaviour": "hunt", "speed": 1.3, "silhouette": "low-mass", "seed": 13}),
    _dp(id="encounter.reflection_wrong", category="encounter", name="Wrong reflection",
        tags=["mirror", "uncanny", "psychological"], base_intensity=0.55,
        fear_affinity={"loss of self": 0.9, "being watched": 0.5},
        enhances=["space.mirror_room", "audio.whisper"],
        params={"trigger": "look_mirror", "delay_ms": 400, "seed": 19}),
    _dp(id="encounter.render", category="encounter", name="The Render",
        tags=["stalker", "panic", "relentless"], base_intensity=0.95,
        fear_affinity={"being chased": 1.0, "darkness": 0.6},
        enhances=["audio.stinger", "lighting.strobe"],
        params={"behaviour": "hunt", "speed": 1.7, "silhouette": "sprinting-mass", "seed": 5}),

    # -- audio --------------------------------------------------------------- #
    _dp(id="audio.low_drone", category="audio", name="Sub-bass drone",
        tags=["ambient", "dread", "bed"], base_intensity=0.3,
        fear_affinity={"dread": 0.7}, enhances=[],
        params={"type": "drone", "hz": 41.2, "reverb": 0.6}),
    _dp(id="audio.distant_drip", category="audio", name="Distant drip",
        tags=["ambient", "isolation", "sparse"], base_intensity=0.2,
        fear_affinity={"isolation": 0.6}, enhances=["space.narrow_corridor"],
        params={"type": "sfx", "period_s": 3.5, "jitter": 0.4}),
    _dp(id="audio.heartbeat", category="audio", name="Heartbeat",
        tags=["tension", "body", "pulse"], base_intensity=0.45,
        fear_affinity={"being chased": 0.5, "being watched": 0.5},
        enhances=["encounter.distant_figure"], params={"type": "heartbeat", "bpm_from_arousal": True}),
    _dp(id="audio.whisper", category="audio", name="Unintelligible whisper",
        tags=["voice", "psychological", "close"], base_intensity=0.5,
        fear_affinity={"loss of self": 0.7, "being watched": 0.6},
        enhances=["encounter.reflection_wrong"], params={"type": "voice", "pan": "wander"}),
    _dp(id="audio.scuttle", category="audio", name="Scuttling",
        tags=["movement", "close", "panic"], base_intensity=0.6,
        fear_affinity={"being chased": 0.7}, enhances=["encounter.crawler"],
        params={"type": "sfx", "approach": True}),
    _dp(id="audio.stinger", category="audio", name="Stinger",
        tags=["jump", "spike", "brass"], base_intensity=0.8,
        fear_affinity={"being chased": 0.6}, enhances=["event.sudden_dark"],
        params={"type": "stinger", "attack_ms": 20}),

    # -- lighting ------------------------------------------------------------ #
    _dp(id="lighting.failing_fluorescent", category="lighting", name="Failing fluorescent",
        tags=["flicker", "cold", "industrial"], base_intensity=0.4,
        fear_affinity={"darkness": 0.6}, enhances=["space.narrow_corridor"],
        params={"flicker": 0.7, "color": "#9fb0b8", "hz": 3}),
    _dp(id="lighting.moonshaft", category="lighting", name="Single moon shaft",
        tags=["sparse", "high-contrast", "exposed"], base_intensity=0.25,
        fear_affinity={"being watched": 0.5, "isolation": 0.4},
        enhances=["space.open_atrium"], params={"beams": 1, "color": "#c3d0e0"}),
    _dp(id="lighting.silhouette_backlight", category="lighting", name="Backlit silhouette",
        tags=["silhouette", "reveal", "dread"], base_intensity=0.5,
        fear_affinity={"being watched": 0.8}, enhances=["encounter.distant_figure"],
        params={"backlight": True, "color": "#40120f"}),
    _dp(id="lighting.strobe", category="lighting", name="Strobe blackout",
        tags=["panic", "disorienting", "chase"], base_intensity=0.85,
        fear_affinity={"being chased": 0.8, "darkness": 0.7},
        enhances=["encounter.render"], params={"strobe_hz": 8, "black_frames": True}),

    # -- events -------------------------------------------------------------- #
    _dp(id="event.lights_die", category="event", name="The lights die",
        tags=["blackout", "transition", "dread"], base_intensity=0.6,
        fear_affinity={"darkness": 0.9}, enhances=["audio.low_drone"],
        params={"trigger": "enter_room", "fade_ms": 800}),
    _dp(id="event.sudden_dark", category="event", name="Sudden dark",
        tags=["blackout", "spike", "panic"], base_intensity=0.75,
        fear_affinity={"darkness": 0.8, "being chased": 0.6},
        enhances=["audio.stinger", "encounter.crawler"], params={"trigger": "proximity", "fade_ms": 60}),
    _dp(id="event.brief_glimpse", category="event", name="Brief glimpse",
        tags=["peripheral", "uncertainty", "psychological"], base_intensity=0.45,
        fear_affinity={"being watched": 0.7, "loss of self": 0.4},
        enhances=["encounter.reflection_wrong"], params={"trigger": "turn_away", "frames": 3}),

    # -- props --------------------------------------------------------------- #
    _dp(id="prop.wheelchair", category="prop", name="Abandoned wheelchair",
        tags=["clinical", "decay", "stillness"], base_intensity=0.2,
        fear_affinity={"isolation": 0.4}, enhances=[], params={"model": "proc:wheelchair", "seed": 3}),
    _dp(id="prop.hanging_sheets", category="prop", name="Hanging sheets",
        tags=["obscure", "movement", "false-figure"], base_intensity=0.3,
        fear_affinity={"being watched": 0.5}, enhances=["encounter.distant_figure"],
        params={"model": "proc:cloth", "count": 8, "seed": 9}),
]

CATALOG_BY_ID: dict[str, DataPoint] = {d.id: d for d in CATALOG}


def catalog_by_category(category: Category) -> list[DataPoint]:
    return [d for d in CATALOG if d.category == category]


def get_datapoint(dp_id: str) -> DataPoint | None:
    return CATALOG_BY_ID.get(dp_id)
