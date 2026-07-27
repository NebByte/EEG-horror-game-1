"""The engine-run EEG source (our MindLink adapter / simulator), driven via the
API — the path the Backrooms client uses to read a headset through the engine."""
from __future__ import annotations

import asyncio

import httpx
from engine.main import app


async def test_engine_eeg_source_feeds_affect_and_stops():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        sid = (await c.post("/v1/sessions", json={"seed": {"fears": ["being chased"]},
                                                  "player_id": "runnertest"})).json()["id"]
        assert (await c.post(f"/v1/sessions/{sid}/eeg/source", json={"kind": "simulator"})).status_code == 200

        # The background source should populate affect within a couple of windows.
        affect = None
        for _ in range(6):
            await asyncio.sleep(0.6)
            s = (await c.get(f"/v1/sessions/{sid}")).json()
            if s.get("last_affect"):
                affect = s["last_affect"]
                assert s["eeg_source"] == "simulator"
                break
        assert affect is not None, "engine-run source should feed affect"

        # A GET stays responsive while the source runs (event loop not starved).
        assert (await c.get(f"/v1/sessions/{sid}")).status_code == 200

        assert (await c.request("DELETE", f"/v1/sessions/{sid}/eeg/source")).json()["ok"] is True


async def test_mindlink_kind_degrades_without_hardware(monkeypatch):
    # Deterministic regardless of whether a COM7 device is attached: force the
    # mindlink branch to fail, delegate everything else to the real factory.
    from engine.eeg import runner

    real_make_source = runner.make_source

    def unavailable_mindlink(kind, *args, **kwargs):
        if kind == "mindlink":
            raise OSError("test device unavailable")
        return real_make_source(kind, *args, **kwargs)

    monkeypatch.setattr(runner, "make_source", unavailable_mindlink)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        sid = (await c.post("/v1/sessions", json={"player_id": "runnertest2"})).json()["id"]
        await c.post(f"/v1/sessions/{sid}/eeg/source", json={"kind": "mindlink", "port": "COM7"})
        await asyncio.sleep(1.0)
        s = (await c.get(f"/v1/sessions/{sid}")).json()
        # Falls back to the simulator, records why, keeps running.
        assert s["eeg_source"] == "simulator"
        assert s["eeg_source_error"]
        await c.request("DELETE", f"/v1/sessions/{sid}/eeg/source")
