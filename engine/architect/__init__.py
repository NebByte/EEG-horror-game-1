"""The Architect: composes a personalized **Script** (the game) from **DataPoints**.

The script is the game. DataPoints are the ingredients — small, procedural,
media-light building blocks (rooms, encounters, audio beds, events, lighting).
The composer (Claude or an offline mock) selects, combines and *enhances* them
into an ordered set of Beats, conditioned on the player's seed profile, their
live EEG affect, and a **learned per-player model** that gets better every run.
"""

from engine.architect.composer import get_composer
from engine.architect.datapoints import CATALOG, DataPoint, catalog_by_category
from engine.architect.learning import PlayerModel, PlayerStore, player_store
from engine.architect.script import Beat, Script

__all__ = [
    "get_composer",
    "CATALOG",
    "DataPoint",
    "catalog_by_category",
    "PlayerModel",
    "PlayerStore",
    "player_store",
    "Beat",
    "Script",
]
