"""EEG sources: an offline simulator, and a real-headset (NeuroSky) adapter.

`make_source(kind, ...)` returns something with an async `read(seconds)` that
yields an `EEGChunk`, plus `close()`. This is the seam a real headset SDK
(Muse / OpenBCI / Emotiv / LSL) plugs into — implement the same interface.
"""
from __future__ import annotations

from typing import Protocol

from engine.eeg.simulator import EEGSimulator
from engine.schemas import EEGChunk


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


class NeuroSkySource:
    """Real NeuroSky MindWave/MindLink adapter over a serial COM port.

    Requires `pyserial`. Kept minimal: it parses the ThinkGear raw-wave stream.
    If the port or dependency is missing it raises a clear error so the caller
    can fall back to the simulator.
    """

    def __init__(self, port: str, baudrate: int = 57600, sample_rate_hz: float = 512.0) -> None:
        try:
            import serial  # noqa: F401
        except ImportError as exc:  # pragma: no cover - hardware path
            raise RuntimeError(
                "NeuroSky source needs pyserial. Install requirements-eeg.txt, "
                "or use make_source('simulator')."
            ) from exc
        import serial

        self.fs = sample_rate_hz
        self._ser = serial.Serial(port, baudrate, timeout=1.0)

    async def read(self, seconds: float) -> EEGChunk:  # pragma: no cover - hardware path
        import asyncio

        from engine.schemas import EEGSample

        n = int(self.fs * seconds)
        samples: list[EEGSample] = []
        # ThinkGear raw wave: 0xAA 0xAA 0x04 0x80 0x02 <hi> <lo> <chk>.
        t0 = 0.0
        while len(samples) < n:
            b = await asyncio.get_event_loop().run_in_executor(None, self._ser.read, 1)
            if b != b"\xaa":
                continue
            if self._ser.read(1) != b"\xaa":
                continue
            plen = self._ser.read(1)[0]
            payload = self._ser.read(plen)
            self._ser.read(1)  # checksum (unchecked in the prototype)
            i = 0
            while i < len(payload) - 1:
                if payload[i] == 0x80 and payload[i + 1] == 0x02:
                    raw = (payload[i + 2] << 8) | payload[i + 3]
                    if raw >= 32768:
                        raw -= 65536
                    uv = raw * (1.8 / 4096.0) / 2000.0 * 1e6
                    t0 += 1.0 / self.fs
                    samples.append(EEGSample(t=round(t0, 5), channels=[float(uv)]))
                    i += 4
                else:
                    i += 1
        return EEGChunk(sample_rate_hz=self.fs, channel_names=["FP1"], samples=samples[:n])

    async def close(self) -> None:  # pragma: no cover - hardware path
        try:
            self._ser.close()
        except Exception:
            pass


def make_source(kind: str = "simulator", **kwargs):
    kind = (kind or "simulator").lower()
    if kind in ("neurosky", "mindwave", "mindlink"):
        return NeuroSkySource(port=kwargs.get("port", "COM7"),
                              baudrate=int(kwargs.get("baudrate", 57600)))
    return SimulatorSource(seed=kwargs.get("seed"))
