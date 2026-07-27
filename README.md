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

The flagship client is **THE BACKROOMS** (`web/index.html`) — a first-person
WebGL horror game (Three.js, vendored locally in `web/vendor/` so it runs fully
offline): an **infinite procedural maze**, four distinct stalkers (some freeze
while you watch them, some charge on sight), sanity/stamina, a flashlight, a
compass, synthesized audio, full post-processing, and a real **win/lose** loop —
find 3 Almond Waters, then reach the Exit. It is wired to the engine's brain: the
**Architect composes the run** and its **escalation** ramps the monsters, your
**reactions train** the learning/evolution layer, and a real **MindLink headset
is read by the engine** (over its serial/COM port — *our* adapter, not browser
Bluetooth) so your brain drives the fear. It plays standalone (simulated fear)
when no headset is connected. Because it uses ES modules, run it **via the
engine** (`python run.py`), not by double-clicking.

A dependency-free **classic raycaster** client is also included at
`web/classic.html` (pure canvas, opens by double-clicking) for the zero-install
path and the Architect HUD.

> **Why not DirectX?** The old plan was a native DirectX 12 runtime. It was
> Windows-only, needed a heavy C++/CMake/vcpkg toolchain, and never built
> cleanly. It's been **replaced by the browser client** above — same directives,
> zero install, runs everywhere.
>
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
- **The Architect** — `engine/architect`: composes a personalized **Script** (the
  game) from **DataPoints**, and **learns the player over time** from their
  reactions. *The script is the game.*
- **API** — `engine/api`: FastAPI HTTP + WebSocket surface.

### The Architect: the script is the game

The Architect (Claude, or an offline mock) authors a **Script** — an ordered set
of **Beats** — out of **DataPoints**: small, procedural ingredients (spaces,
encounters, audio, lighting, events, props) that store *parameters*, not heavy
media. It selects and *combines* them by the player's fears and a **learned
model** of what actually scared them before, so every run is a fresh combination
that adapts to *you*. Generation is only used when the catalog can't express
something. See it learn:

```bash
python scripts/demo_architect.py      # compose -> react -> re-author, offline
python scripts/demo_evolution.py      # the model breeds new DataPoints for you
```

Beyond scoring, the learning layer (`engine/architect/evolution.py`) **breeds**:
it links the DataPoints you react to best *together* (enhance), reuses your top
scarers (copy), and **mutates/crosses them into brand-new personalized
DataPoints** (e.g. a `crawler × render` hybrid) that join your catalog and feed
the next script — so the game literally invents new horrors tuned to you.

```text
POST /v1/sessions/{id}/script       compose the personalized game
GET  /v1/sessions/{id}/script       the current Script
POST /v1/sessions/{id}/reactions    feed a reaction -> the model learns you
GET  /v1/players/{player_id}        inspect what it has learned
```

Full design in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Quickstart (offline, no cloud, no headset)

```bash
pip install -r requirements-dev.txt

# Play it — starts the engine and opens the WebGL horror game in your browser:
python run.py          # Windows / macOS / Linux
#   ./run.sh           # macOS / Linux
#   run.bat            # Windows (double-click)
```

Then move with **WASD / arrows**, look with the **mouse**, and drag the **fear
slider** (or tick *Auto-escalate*) to watch the world turn from *unease* to
*panic*. Switch the dock to **Live engine** to drive it from real streamed EEG,
and optionally tick **Webcam affect** to fuse a webcam motion/startle signal with
the EEG (processed locally — only the derived affect numbers are sent). The
Director HUD shows live **signal quality** (blink / EMG / motion / poor-signal).

Prefer the pieces on their own:

```bash
# 1) See the whole loop escalate in your terminal, no server needed:
python scripts/demo_loop.py

# 2) Run the API + game server:
uvicorn engine.main:app --reload
#   -> game:  http://localhost:8000/
#   -> docs:  http://localhost:8000/docs

# 3) Watch it get scarier and scarier, with fresh assets each run:
python scripts/demo_escalation.py

# 4) Stream (simulated) live EEG into a running engine:
python run_eeg.py                 # offline simulator
python run_eeg.py mindlink COM7   # a real NeuroSky MindLink headset

# 5) Run tests:
pytest -q
```

### Hardware: the NeuroSky MindLink

The target headset is the **NeuroSky MindLink** — a single-channel (FP1) dry
electrode sampling raw EEG at 512 Hz over the ThinkGear serial protocol, also
reporting eSense Attention/Meditation and a signal-quality value. The
`mindlink` source (`engine/eeg/sources.py`) parses that stream; because it's a
*single* channel it can't measure frontal alpha asymmetry, so valence falls back
to neutral and fear is driven by arousal + stress + band powers. Install the
serial deps with `pip install -r requirements-eeg.txt`, then either:

```bash
# In THE BACKROOMS: click "Connect Mind Link" and enter the COM port — the engine
# reads the headset server-side (POST /v1/sessions/{id}/eeg/source) and your
# brain drives the fear. No browser Bluetooth; our signal pipeline throughout.

# …or stream it to a session from the terminal:
python run_eeg.py mindlink COM7   # COM port the headset pairs on (57600 baud)
```

### Every run is different, and scarier

Each time you compose a Script it's a new **run**: the Architect's **escalation**
rises (higher tension ceiling, faster beats, more intense elements), and every
DataPoint resolves to **fresh media** (a different map layout, stalker, palette,
sound, animation) seeded per run. Nothing heavy ships — variants are procedural
by default (`engine/assets/`).

**Live Claude architect.** Set `ARCHITECT_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`
and Claude authors the Script itself (with a rationale); it degrades to the mock
composer on any error, so the game never hard-fails. `GET /v1/health` reports the
active `architect`.

**Multiple asset libraries.** Set `ASSET_SOURCE=libraries` to resolve real media
from open libraries — **Poly Haven** (CC0 textures/HDRIs/models, keyless),
**Freesound** (sounds, needs `FREESOUND_API_KEY`), **Sketchfab** (models/
animations, needs `SKETCHFAB_API_KEY`), and **CC0 packs** (Kenney / OpenGameArt).
Each asset kind is routed to the best-configured library and **falls back to
procedural** per asset, so a missing key or blocked network never breaks a run.
`GET /v1/sessions/{id}/assets/manifest` returns the attribution/licensing manifest.

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
  main.py            FastAPI app (also serves the web game at /)
  config.py          env-driven settings
  schemas.py         shared pydantic contracts
  api/               HTTP + WS routers (health, sessions, eeg)
  eeg/               band powers, affect, simulator, sources, gateway, runner
  generative/        provider interface, mock, pipeline
  architect/         DataPoints + Script composer (Claude/mock) + learning
  experience/        orchestrator (director) + session store
web/                 browser game clients (replaces the DirectX runtime)
  index.html         THE BACKROOMS — flagship Three.js game, wired to the engine
  vendor/three/      vendored Three.js (offline, no CDN)
  classic.html       dependency-free raycaster client + Architect HUD
  js/game.js         raycasting renderer, affect sim, engine client, audio
scripts/demo_loop.py end-to-end offline demo
run.py / run.sh      one-command launchers (start engine + open the game)
tests/               affect, orchestrator, and API tests
```

---

## Safety & ethics

This system measures physiological signals and deliberately induces fear. The
prototype ships a **stress safety back-off** (`STRESS_SAFETY_CEILING`) that eases
the experience when sustained stress is too high. Before any real-user testing,
read the safety/consent items in [`ROADMAP.md`](./ROADMAP.md#workstream-g--safety-ethics--compliance).
EEG is sensitive personal data — treat it accordingly.
