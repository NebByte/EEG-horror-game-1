"""The director — the core creative logic.

Given an AffectState and the AssetBank it:
  * maintains a **smoothed intensity** (tension curve) so directives don't jitter;
  * picks a **target mood** from fear / stress / arousal;
  * selects matching assets (character, ambient, stinger, map) by mood;
  * enforces a **safety back-off**: when a rolling stress EMA exceeds the
    configured ceiling it forces `relief` and eases the intensity.
"""
from __future__ import annotations

from engine.config import get_settings
from engine.schemas import AffectState, AssetBank, Directive, Mood, SeedProfile


def _ema(prev: float, new: float, alpha: float) -> float:
    return alpha * new + (1.0 - alpha) * prev


class Orchestrator:
    def __init__(self, seed: SeedProfile) -> None:
        self.seed = seed
        self.settings = get_settings()
        self._intensity = 0.15  # smoothed tension curve
        self._stress_ema = 0.0  # rolling stress for the safety rail
        self._steps = 0

    # -- mood selection ----------------------------------------------------- #
    def _target_mood(self, affect: AffectState) -> Mood:
        drive = 0.5 * affect.fear + 0.3 * affect.stress + 0.2 * affect.arousal
        if drive < 0.30:
            return "unease"
        if drive < 0.60:
            return "dread"
        return "panic"

    # -- the step ----------------------------------------------------------- #
    def step(self, affect: AffectState, bank: AssetBank | None) -> Directive:
        self._steps += 1
        self._stress_ema = _ema(self._stress_ema, affect.stress, alpha=0.25)

        # Target intensity tracks the fear/arousal drive, biased by the player's
        # stated intensity preference; smoothed into the tension curve.
        drive = 0.55 * affect.fear + 0.25 * affect.arousal + 0.20 * affect.stress
        target = min(1.0, drive * (0.6 + 0.8 * self.seed.intensity_preference))
        self._intensity = _ema(self._intensity, target, alpha=0.2)

        mood = self._target_mood(affect)
        backoff = self._stress_ema > self.settings.stress_safety_ceiling
        if backoff:
            mood = "relief"
            self._intensity = min(self._intensity, 0.25)

        intensity = round(max(0.0, min(1.0, self._intensity)), 4)

        # Resolve concrete asset ids from the bank (if a bank exists).
        character = ambient = stinger = level = None
        if bank is not None:
            c = bank.by_mood("character", mood)
            s = bank.by_mood("soundscape", mood)
            m = bank.by_mood("map", mood)
            character = c.id if c else None
            ambient = s.id if s else None
            level = m.id if m else None
            # A stinger only fires on tense moods and only occasionally.
            if s and mood in ("dread", "panic") and self._steps % 3 == 0:
                stinger = s.id

        return Directive(
            mood=mood,
            intensity=intensity,
            spawn_character_id=character,
            ambient_sound_id=ambient,
            stinger_sound_id=stinger,
            map_id=level,
            safety_backoff=backoff,
            fog_density=round(0.15 + 0.6 * intensity, 3),
            flicker=round(intensity * (0.0 if mood == "relief" else 1.0), 3),
            heartbeat_bpm=round(60 + 70 * affect.arousal, 1),
        )
