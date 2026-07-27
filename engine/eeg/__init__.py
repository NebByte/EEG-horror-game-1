"""EEG signal → affect: band powers, a white-box affect model, and a simulator."""

from engine.eeg.affect import infer_affect
from engine.eeg.bands import band_powers
from engine.eeg.simulator import EEGSimulator

__all__ = ["band_powers", "infer_affect", "EEGSimulator"]
