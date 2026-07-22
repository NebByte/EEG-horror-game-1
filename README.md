# EEG Horror Engine

An adaptive horror-experience engine driven by **live EEG affect signals**.

You wear an EEG headset. The engine reads your brain activity, estimates how
**afraid / stressed / aroused** you are in real time, and reshapes the game
around that: which monster stalks you, what you hear, how the level mutates —
all tuned to *your* fear, with a safety rail so it never goes too far.

Generative models (via **Google Cloud Vertex AI**) pre-build a bank of sounds,
characters, and maps from your seed profile; the engine then selects and
modulates those assets at runtime from the measured affect. Everything is
exposed over an **HTTP + WebSocket API** so any game client (Unity, Unreal, web)
can drive it.

> **Status: prototype.** It runs end-to-end today with a built-in EEG simulator
> and an offline mock asset provider — **no hardware and no cloud credentials
> required**. See [`ROADMAP.md`](./ROADMAP.md) for the path to production.

---

## How it works

```
                        ┌──────────────── Phase 1: pre-generation ─────────────────┐
  Seed profile ───────▶ │  AssetPipeline ──▶ Vertex AI (Gemini + Imagen) ──▶ Bank  │
  (theme, fears)        │                     (or offline Mock provider)           │
                        └──────────────────────────────────────────────────────────┘
                                                                          │
                                                                          ▼
  ┌──────────────────────────── Phase 2: live loop ───────────────────────────────┐
  │  EEG headset ─▶ /eeg or WS /stream ─▶ band powers ─▶ affect (fear/stress/...)  │
  │                                                            │                    │
  │                                        Orchestrator (director) ◀── Asset Bank   │
  │                                                            │                    │
  │  game client ◀──────────────── Directive (spawn / sound / map / intensity) ────│
  └────────────────────────────────────────────────────────────────────────────────┘
```

- **EEG → affect** — `engine/eeg`: FFT band powers (delta/theta/alpha/beta/gamma)
  → heuristic affect model (fear, stress, arousal, engagement, valence via
  frontal alpha asymmetry).
- **Generative assets** — `engine/generative`: a pluggable `AssetProvider`
  (`mock` offline, or `vertex` on Google Cloud) builds an `AssetBank`.
- **The director** — `engine/experience`: turns live affect into a `Directive`,
  managing a tension curve and a stress **safety back-off**.
- **API** — `engine/api`: FastAPI HTTP + WebSocket surface.

Full design in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Quickstart (offline, no cloud, no headset)

```bash
pip install -r requirements-dev.txt

# 1) See the whole loop escalate + hit the safety rail, no server needed:
python scripts/demo_loop.py

# 2) Run the API:
uvicorn engine.main:app --reload
#   -> open http://localhost:8000/docs

# 3) Run tests:
pytest -q
```

### Drive the API by hand

```bash
# Create a session from a seed profile
curl -sX POST localhost:8000/v1/sessions \
  -H 'content-type: application/json' \
  -d '{"seed":{"theme":"abandoned asylum","fears":["darkness","isolation"]}}'
# -> {"id":"<SID>", ...}

# Pre-generate the asset bank
curl -sX POST localhost:8000/v1/sessions/<SID>/generate
curl -s  localhost:8000/v1/sessions/<SID>/assets

# Push a window of EEG -> get affect + the next directive
curl -sX POST localhost:8000/v1/sessions/<SID>/eeg \
  -H 'content-type: application/json' \
  -d @sample_eeg_chunk.json
```

The **live path** is the WebSocket `ws://localhost:8000/v1/sessions/<SID>/stream`:
send `EEGChunk` frames, receive `affect + directive` frames per window.

---

## Enabling Google Cloud (Vertex AI)

```bash
pip install -r requirements-vertex.txt
export ASSET_PROVIDER=vertex
export GCP_PROJECT=your-project
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json  # or use ADC
uvicorn engine.main:app
```

If the SDK or credentials are missing, the engine **logs a warning and falls
back to the mock provider** so the prototype never hard-fails.

**Verified live** against Vertex using the current `google-genai` SDK. Two
endpoint details matter: **Gemini** text models are served from the **`global`**
endpoint (`VERTEX_TEXT_LOCATION=global`, the default), while **Imagen** and the
GCS bucket stay **regional** (`GCP_LOCATION=us-central1`). To reproduce a live
generation without any key file, run `scripts/cloudshell_verify.sh` in Google
Cloud Shell (keyless ADC).

---

## API surface

| Method | Path                              | Purpose                                   |
|-------:|-----------------------------------|-------------------------------------------|
| GET    | `/v1/health`                      | Liveness + configured provider            |
| POST   | `/v1/sessions`                    | Create a session from a seed profile      |
| POST   | `/v1/sessions/{id}/generate`      | Pre-generate the asset bank (async)       |
| GET    | `/v1/sessions/{id}`               | Session status + latest affect/directive  |
| GET    | `/v1/sessions/{id}/assets`        | The generated asset bank                  |
| POST   | `/v1/sessions/{id}/eeg`           | Push an EEG batch → affect + directive     |
| WS     | `/v1/sessions/{id}/stream`        | Live EEG in → directives out               |
| GET    | `/v1/sessions/{id}/directive`     | Most recent directive                     |

---

## Repository layout

```
engine/
  main.py            FastAPI app
  config.py          env-driven settings
  schemas.py         shared pydantic contracts
  api/               HTTP + WS routers (health, sessions, eeg)
  eeg/               band powers, affect model, simulator
  generative/        provider interface, mock, vertex, pipeline
  experience/        orchestrator (director) + session store
scripts/demo_loop.py end-to-end offline demo
tests/               affect, pipeline, and API tests
```

---

## Safety & ethics

This system measures physiological signals and deliberately induces fear. The
prototype ships a **stress safety back-off** (`STRESS_SAFETY_CEILING`) that eases
the experience when sustained stress is too high. Before any real-user testing,
read the safety/consent items in [`ROADMAP.md`](./ROADMAP.md#workstream-g--safety-ethics--compliance).
EEG is sensitive personal data — treat it accordingly.
