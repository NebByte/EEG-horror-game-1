"""API lifecycle: create a session, generate a bank, push EEG, get a directive."""
from __future__ import annotations

import math

from fastapi.testclient import TestClient

from engine.main import app

client = TestClient(app)


def _eeg_window(arousal: float) -> dict:
    fs, n = 128, 128
    centers = {"delta": 2, "theta": 6, "alpha": 10, "beta": 20, "gamma": 38}
    amp = {"delta": 1 - 0.3 * arousal, "theta": 0.8 + 0.3 * arousal,
           "alpha": 1.2 * (1 - 0.8 * arousal), "beta": 0.4 + 1.6 * arousal, "gamma": 0.2 + arousal}
    samples = []
    for i in range(n):
        t = i / fs
        ch = [sum(amp[b] * math.sin(2 * math.pi * centers[b] * t + c * 0.3) for b in centers) for c in range(4)]
        samples.append({"t": t, "channels": ch})
    return {"sample_rate_hz": fs, "channel_names": ["AF3", "AF4", "TP9", "TP10"], "samples": samples}


def test_health():
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_full_lifecycle():
    r = client.post("/v1/sessions", json={"seed": {"theme": "asylum", "fears": ["dark"]}})
    assert r.status_code == 200
    sid = r.json()["id"]

    assert client.post(f"/v1/sessions/{sid}/generate").status_code == 200
    bank = client.get(f"/v1/sessions/{sid}/assets").json()
    assert len(bank["characters"]) == 4

    out = client.post(f"/v1/sessions/{sid}/eeg", json=_eeg_window(0.9)).json()
    assert "affect" in out and "directive" in out
    assert out["directive"]["mood"] in ("unease", "dread", "panic", "relief")

    d = client.get(f"/v1/sessions/{sid}/directive").json()
    assert d["mood"] == out["directive"]["mood"]


def test_missing_session_404():
    assert client.get("/v1/sessions/nope").status_code == 404
    assert client.post("/v1/sessions/nope/eeg", json=_eeg_window(0.5)).status_code == 404


def test_websocket_stream():
    sid = client.post("/v1/sessions", json={"seed": {}}).json()["id"]
    client.post(f"/v1/sessions/{sid}/generate")
    with client.websocket_connect(f"/v1/sessions/{sid}/stream") as ws:
        ws.send_json(_eeg_window(0.8))
        msg = ws.receive_json()
        assert "affect" in msg and "directive" in msg


def test_architect_script_and_reaction(tmp_path, monkeypatch):
    # Isolate the persisted player model to a temp dir.
    from engine.architect import learning

    monkeypatch.setattr(learning, "player_store", learning.PlayerStore(str(tmp_path)))
    monkeypatch.setattr("engine.experience.state.player_store", learning.player_store, raising=False)

    sid = client.post("/v1/sessions", json={
        "seed": {"theme": "asylum", "fears": ["being chased"]}, "player_id": "tester"
    }).json()["id"]

    script = client.post(f"/v1/sessions/{sid}/script", json={"length": 6}).json()
    assert len(script["beats"]) == 6
    beat0 = script["beats"][0]

    r = client.post(f"/v1/sessions/{sid}/reactions", json={
        "beat_index": 0,
        "affect_before": {"fear": 0.1}, "affect_peak": {"fear": 0.9, "arousal": 0.8},
    }).json()
    assert r["reactions_seen"] == 1
    assert r["reward"] > 0.6
    assert set(r["updated_datapoints"]) == set(beat0["datapoint_ids"])

    got = client.get(f"/v1/sessions/{sid}/script").json()
    assert got["session_id"] == sid
