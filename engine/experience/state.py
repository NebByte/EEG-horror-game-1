"""In-memory session store — zero infra for the prototype.

Holds each session's seed, orchestrator, asset bank, and a bounded history of
recent affect/directive pairs. A module-level singleton; swap for Redis/
Firestore to go multi-worker (see ROADMAP workstream E).
"""
from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field

from engine.experience.orchestrator import Orchestrator
from engine.schemas import AffectState, AssetBank, Directive, SeedProfile

_HISTORY = 128


@dataclass
class Session:
    id: str
    seed: SeedProfile
    orchestrator: Orchestrator
    bank: AssetBank | None = None
    generating: bool = False
    history: deque = field(default_factory=lambda: deque(maxlen=_HISTORY))
    last_affect: AffectState | None = None
    last_directive: Directive | None = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, seed: SeedProfile) -> Session:
        sid = uuid.uuid4().hex[:12]
        sess = Session(id=sid, seed=seed, orchestrator=Orchestrator(seed))
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
