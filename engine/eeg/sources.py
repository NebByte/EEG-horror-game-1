"""EEG sources: an offline simulator, and the NeuroSky **MindLink** adapter.

`make_source(kind, ...)` returns something with an async `read(seconds)` that
yields an `EEGChunk`, plus `close()`. This is the seam a real headset SDK
(Muse / OpenBCI / Emotiv / LSL) plugs into — implement the same interface.

The MindLink is a NeuroSky ThinkGear single-channel (FP1) headset sampling raw
EEG at 512 Hz and streaming the ThinkGear serial protocol. It also reports the
eSense Attention/Meditation meters and a Poor-Signal quality value, which we
surface for signal-quality gating. Because it is single-channel, frontal alpha
asymmetry (our valence proxy) isn't available — valence falls back to neutral.
"""
from __future__ import annotations

from typing import Protocol

from engine.eeg.simulator import EEGSimulator
from engine.schemas import EEGChunk, EEGSample

# --------------------------------------------------------------------------- #
# ThinkGear protocol (MindLink / MindWave family)
# --------------------------------------------------------------------------- #
SYNC = 0xAA
# Single-byte value codes.
CODE_POOR_SIGNAL = 0x02
CODE_ATTENTION = 0x04
CODE_MEDITATION = 0x05
CODE_BLINK = 0x16
# Multi-byte value codes (preceded by a length byte).
CODE_RAW_WAVE = 0x80        # 2 bytes, big-endian signed
CODE_ASIC_EEG_POWER = 0x83  # 24 bytes = 8 bands x 3 bytes big-endian
# 12-bit ADC over ~1.8V, MindLink gain — convert raw counts to microvolts.
RAW_TO_UV = (1.8 / 4096.0) / 2000.0 * 1e6

ASIC_BANDS = ("delta", "theta", "low_alpha", "high_alpha",
              "low_beta", "high_beta", "low_gamma", "mid_gamma")


def parse_thinkgear_payload(payload: bytes) -> dict:
    """Parse one ThinkGear packet payload into a dict of values.

    Pure and dependency-free so it is unit-testable without hardware. Returns any
    of: poor_signal, attention, meditation, blink, raw (list[int]),
    asic_power (dict[band->int]).
    """
    out: dict = {"raw": []}
    i = 0
    n = len(payload)
    while i < n:
        code = payload[i]
        if code == CODE_POOR_SIGNAL and i + 1 < n:
            out["poor_signal"] = payload[i + 1]; i += 2
        elif code == CODE_ATTENTION and i + 1 < n:
            out["attention"] = payload[i + 1]; i += 2
        elif code == CODE_MEDITATION and i + 1 < n:
            out["meditation"] = payload[i + 1]; i += 2
        elif code == CODE_BLINK and i + 1 < n:
            out["blink"] = payload[i + 1]; i += 2
        elif code == CODE_RAW_WAVE and i + 3 < n:
            length = payload[i + 1]  # always 2 for raw wave
            val = (payload[i + 2] << 8) | payload[i + 3]
            if val >= 32768:
                val -= 65536
            out["raw"].append(val)
            i += 2 + length
        elif code == CODE_ASIC_EEG_POWER and i + 1 < n:
            length = payload[i + 1]  # 24
            data = payload[i + 2 : i + 2 + length]
            bands = {}
            # Iterate against the *actual* slice length so a truncated packet
            # can't index past `data`.
            for b in range(min(8, length // 3, len(data) // 3)):
                o = b * 3
                bands[ASIC_BANDS[b]] = (data[o] << 16) | (data[o + 1] << 8) | data[o + 2]
            out["asic_power"] = bands
            i += 2 + length
        else:
            # Unknown/most-single-byte codes: skip a byte and resync.
            i += 1
    return out


class EEGSource(Protocol):
    async def read(self, seconds: float) -> EEGChunk: ...
    async def close(self) -> None: ...


class SimulatorSource:
    """Offline source — biases the simulated signal on a slow arousal wave so a
    demo without hardware still rises and falls."""

    def __init__(self, sample_rate_hz: float = 256.0, seed: int | None = None) -> None:
        self._sim = EEGSimulator(sample_rate_hz=sample_rate_hz, seed=seed)
        self._phase = 0.0

    async def read(self, seconds: float) -> EEGChunk:
        import math

        self._phase += seconds
        arousal = 0.5 + 0.45 * math.sin(self._phase * 0.15)
        valence = -0.6 if arousal > 0.45 else 0.3
        return self._sim.window(seconds, arousal=arousal, valence=valence)

    async def close(self) -> None:  # nothing to release
        return None


class MindLinkSource:
    """NeuroSky MindLink (ThinkGear) adapter over a serial COM port.

    Single channel (FP1), 512 Hz raw. Requires `pyserial`. Tracks the latest
    Poor-Signal / Attention / Meditation values (see `signal_ok`). If the port or
    dependency is missing it raises a clear error so the caller can fall back to
    the simulator.
    """

    def __init__(self, port: str, baudrate: int = 57600, sample_rate_hz: float = 512.0) -> None:
        try:
            import serial  # noqa: F401
        except ImportError as exc:  # pragma: no cover - hardware path
            raise RuntimeError(
                "MindLink source needs pyserial. Install requirements-eeg.txt, "
                "or use make_source('simulator')."
            ) from exc
        import serial

        self.fs = sample_rate_hz
        self._ser = serial.Serial(port, baudrate, timeout=1.0)
        # Latest device telemetry (updated as packets arrive).
        self.poor_signal = 200  # 0 good .. 200 no contact
        self.attention = 0
        self.meditation = 0

    def signal_ok(self) -> bool:
        """MindLink contact quality gate: poor_signal well below the off-head 200."""
        return self.poor_signal < 60

    def _read_packet(self):  # pragma: no cover - hardware path
        # Sync on 0xAA 0xAA, then read length, payload, checksum.
        if self._ser.read(1) != bytes([SYNC]):
            return None
        if self._ser.read(1) != bytes([SYNC]):
            return None
        plen = self._ser.read(1)
        if not plen:
            return None
        length = plen[0]
        payload = self._ser.read(length)
        self._ser.read(1)  # checksum (unverified in the prototype)
        return parse_thinkgear_payload(payload)

    async def read(self, seconds: float) -> EEGChunk:  # pragma: no cover - hardware path
        import asyncio

        n = int(self.fs * seconds)
        samples: list[EEGSample] = []
        t = 0.0
        loop = asyncio.get_event_loop()
        while len(samples) < n:
            parsed = await loop.run_in_executor(None, self._read_packet)
            if not parsed:
                continue
            if "poor_signal" in parsed:
                self.poor_signal = parsed["poor_signal"]
            if "attention" in parsed:
                self.attention = parsed["attention"]
            if "meditation" in parsed:
                self.meditation = parsed["meditation"]
            for raw in parsed.get("raw", []):
                t += 1.0 / self.fs
                samples.append(EEGSample(t=round(t, 5), channels=[float(raw) * RAW_TO_UV]))
                if len(samples) >= n:
                    break
        return EEGChunk(sample_rate_hz=self.fs, channel_names=["FP1"], samples=samples[:n])

    async def close(self) -> None:  # pragma: no cover - hardware path
        try:
            self._ser.close()
        except Exception:
            pass


# Backwards-compatible alias.
NeuroSkySource = MindLinkSource


def make_source(kind: str = "simulator", **kwargs):
    kind = (kind or "simulator").lower()
    if kind in ("mindlink", "neurosky", "mindwave"):
        return MindLinkSource(port=kwargs.get("port", "COM7"),
                              baudrate=int(kwargs.get("baudrate", 57600)),
                              sample_rate_hz=float(kwargs.get("sample_rate_hz", 512.0)))
    return SimulatorSource(seed=kwargs.get("seed"))
