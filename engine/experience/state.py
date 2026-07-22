"""In-memory session store — zero infra for the prototype.

Holds each session's seed, orchestrator, asset bank, and a bounded history of
recent affect/directive pairs. A module-level singleton; swap for Redis/
Firestore to go multi-worker (see ROADMAP workstream E).
"""
from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from engine.experience.orchestrator import Orchestrator
from engine.schemas import AffectState, AssetBank, Directive, SeedProfile

if TYPE_CHECKING:
    from engine.architect.learning import PlayerModel
    from engine.architect.script import Script

_HISTORY = 128


@dataclass
class Session:
    id: str
    seed: SeedProfile
    orchestrator: Orchestrator
    player_id: str = "anon"
    player_model: "PlayerModel | None" = None
    script: "Script | None" = None
    beat_index: int = 0
    bank: AssetBank | None = None
    generating: bool = False
    baseline: AffectState | None = None  # per-player resting calibration
    history: deque = field(default_factory=lambda: deque(maxlen=_HISTORY))
    last_affect: AffectState | None = None
    last_directive: Directive | None = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, seed: SeedProfile, player_id: str = "anon") -> Session:
        # Load the persisted per-player learning model so it improves across runs.
        from engine.architect.learning import player_store

        sid = uuid.uuid4().hex[:12]
        sess = Session(id=sid, seed=seed, orchestrator=Orchestrator(seed),
                       player_id=player_id, player_model=player_store.load(player_id))
        self._sessions[sid] = sess
        return sess

    def get(self, sid: str) -> Session | None:
        return self._sessions.get(sid)

    def require(self, sid: str) -> Session:
        sess = self._sessions.get(sid)
        if sess is None:
            raise KeyError(sid)
        return sess

    def record(self, sid: str, affect: AffectState, directive: Directive) -> None:
        sess = self.require(sid)
        sess.last_affect = affect
        sess.last_directive = directive
        sess.history.append({"affect": affect.model_dump(), "directive": directive.model_dump()})


# Module-level singleton for the prototype.
store = SessionStore()
