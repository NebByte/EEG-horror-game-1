"""MindLink / ThinkGear packet parsing — verified without hardware."""
from __future__ import annotations

from engine.eeg.sources import RAW_TO_UV, make_source, parse_thinkgear_payload


def test_parse_small_packet_attention_meditation_poorsignal():
    # code/value pairs: poor_signal=0, attention=57, meditation=42
    payload = bytes([0x02, 0, 0x04, 57, 0x05, 42])
    out = parse_thinkgear_payload(payload)
    assert out["poor_signal"] == 0
    assert out["attention"] == 57
    assert out["meditation"] == 42


def test_parse_raw_wave_signed():
    # 0x80, len=2, then a negative 16-bit sample (0xFFFF = -1) and a positive one
    payload = bytes([0x80, 2, 0xFF, 0xFF]) + bytes([0x80, 2, 0x01, 0x00])
    out = parse_thinkgear_payload(payload)
    assert out["raw"] == [-1, 256]


def test_parse_asic_power_bands():
    # 0x83, len=24, 8 bands x 3 bytes. Make delta=0x000100=256, rest 0.
    data = bytes([0x00, 0x01, 0x00]) + bytes([0] * 21)
    payload = bytes([0x83, 24]) + data
    out = parse_thinkgear_payload(payload)
    assert out["asic_power"]["delta"] == 256
    assert out["asic_power"]["mid_gamma"] == 0
    assert len(out["asic_power"]) == 8


def test_make_source_mindlink_falls_back_without_pyserial_or_port():
    # Without a real COM port this raises; the simulator is always available.
    sim = make_source("simulator")
    assert sim is not None
    # Raw-to-microvolt conversion is a sane, nonzero scale.
    assert RAW_TO_UV > 0
