# Architecture

This document explains the moving parts of the EEG Horror Engine and the design
decisions behind them. The guiding principle for the prototype: **run end-to-end
with zero external dependencies**, but keep every seam pluggable so production
pieces (real headset, Vertex AI, distributed state) drop in without a rewrite.

## The two phases

The experience has a clear split:

1. **Pre-generation (offline-ish).** From a player's *seed profile* (theme +
   self-reported fears + intensity preference), the engine generates an
   **asset bank**: sounds, characters, and maps, one variant per *mood bucket*
   (`unease`, `dread`, `panic`, `relief`). This is where the heavy generative
   calls happen — done once, up front.

2. **Live loop (real time).** During play, EEG windows stream in continuously.
   Each window is turned into an **affect estimate**, and the **orchestrator**
   ("the director") emits a **directive** telling the game what to do *now*,
   drawing from the pre-generated bank. This path must be fast and cheap — no
   model calls in the hot loop.

Separating the two keeps latency-sensitive gameplay decoupled from slow,
expensive generation.

## Components

### `engine/schemas.py` — contracts
Pydantic models shared everywhere: `EEGChunk`/`EEGSample`, `BandPowers`,
`AffectState`, `SeedProfile`, `Asset`/`AssetBank`, and `Directive`. Keeping the
contracts in one place means the API, EEG, generative, and experience layers all
speak the same language.

### `engine/eeg/` — signal → affect
- `bands.py` — converts an `EEGChunk` into relative band powers via an FFT
  periodogram, plus `frontal_alpha_asymmetry()` (the approach/withdrawal proxy
  used for valence).
- `affect.py` — maps band powers to an `AffectState` using transparent,
  tunable heuristics (documented inline with their EEG correlates). This is
  intentionally a **white-box model** for the prototype so behaviour is
  explainable; it's the natural place to later swap in a trained classifier.
- `simulator.py` — a synthetic EEG source biased toward a target arousal, so the
  entire system is demoable and testable without hardware.

**Why heuristics first?** A supervised affect model needs labelled EEG, which we
don't have yet. The heuristics give a plausible, monotonic signal to build the
rest of the system against, and define the exact interface (`EEGChunk →
AffectState`) a model must later satisfy.

### `engine/generative/` — asset generation
- `base.py` — the `AssetProvider` ABC. Three async methods:
  `generate_soundscape`, `generate_character`, `generate_map`.
- `mock.py` — deterministic, offline provider. Same output shape as a real one.
- `vertex.py` — Google Cloud provider: Gemini for structured design (JSON specs
  for characters/maps/soundscapes), Imagen for concept art (media upload to GCS
  is a documented TODO). SDK imported lazily; auth via ADC.
- `pipeline.py` — `AssetPipeline.build_bank()` fans out generation across the
  four moods **concurrently** with `asyncio.gather`, and `get_provider()`
  selects the backend from config and **degrades to mock on any error**.

**Why a provider interface?** The choice of generative backend is a business/ops
decision that will change (Vertex today, maybe a self-hosted diffusion model or
ElevenLabs for audio tomorrow). The rest of the engine depends only on the ABC.

### `engine/architect/` — the Architect (the script is the game)
The Architect authors a personalized **Script** and learns the player over time.

- `datapoints.py` — the **DataPoint** catalog: small, **procedural** ingredients
  (spaces, encounters, audio, lighting, events, props). Each stores *parameters*
  (seeds, dims, palettes) not baked media, plus `fear_affinity` (which fears it
  plays on) and `enhances` (which DataPoints it combines with well). The catalog
  is tiny on purpose — the value is in *combination*, not asset count.
- `script.py` — a **Script** is an ordered list of **Beats**; each Beat is a mood
  + target tension + the DataPoints active during it. The Architect authors the
  arc; the live EEG director modulates *within* the current beat.
- `composer.py` — the composer. `MockComposer` selects DataPoints per beat by
  intensity fit, the player's stated fears, and their learned scores, then
  *enhances* strong picks by pulling in partner DataPoints. `AnthropicComposer`
  lets **Claude** author the Script from the catalog + player model, degrading to
  the mock on any error. `get_composer()` chooses from config.
- `learning.py` — the **PlayerModel**: per-DataPoint / per-tag / per-fear scores
  updated from reactions (EEG affect deltas now; computer-vision affect later),
  persisted as JSON so it improves across restarts. This is the "re-author a
  fresh combination that has learned you" loop: compose reads the model, play
  posts reactions, the model updates for next time.

**Why not just generate everything?** Generation is slow, costly, and
non-deterministic. Composing from a curated procedural catalog is fast, cheap,
explainable, and personalizable — so generation is reserved for the rare case
the catalog genuinely can't express what the Architect wants.

### `engine/assets/` — fresh assets every run + escalation
Turns the Architect's abstract DataPoints into concrete media (maps, models,
characters, pictures, sounds, animations), resolved **fresh for every run**.

- `models.py` — the `MediaAsset` contract (kind, source, uri/params, license, seed).
- `sources.py` — `ProceduralAssetSource` synthesises an infinite space of asset
  variants from a seed (palettes, geometry/texture seeds, synth params, animation
  clips) — offline, kkrieger-style, nothing heavy on disk. `RemoteAssetSource` is
  the seam for open-asset libraries (Poly Haven, Freesound, Mixamo-style rigs)
  and degrades to procedural until wired.
- `resolver.py` — seeds each asset from `(run_seed, datapoint_id, kind)`, so a run
  is internally consistent but different from every other run.

**Escalation ("scarier and scarier").** The `PlayerModel` counts `runs`; each
compose bumps it and raises `escalation`, which the composer uses to lift the
tension ceiling, shorten beats (faster pacing), and bias selection toward more
intense DataPoints. The per-run asset seed changes with it, so every restart is a
hotter, different game.

### `engine/eeg/` — hardware: the NeuroSky MindLink
`sources.py` includes a `MindLinkSource` (alias `NeuroSkySource`) that speaks the
ThinkGear serial protocol: a single-channel (FP1) dry-electrode headset sampling
raw EEG at 512 Hz, plus the eSense Attention/Meditation meters and a Poor-Signal
quality value used for contact gating. `parse_thinkgear_payload()` is a pure,
unit-tested parser (raw wave, poor-signal, attention/meditation, ASIC band
powers). Being single-channel, it can't compute frontal alpha asymmetry, so
valence falls back to neutral and fear is driven by arousal + stress + bands.

Around the raw signal: `bands.py` uses **Welch PSD** (Hann windows + overlap) for
lower-variance band powers; `artifacts.py` flags blink / EMG / motion and turns
poor-signal into a per-window **confidence** (the director holds on low-confidence
windows instead of reacting to noise); `calibration.py` records a resting baseline
so affect is centered on *this* player. `affect.fuse_cv()` fuses an optional
**computer-vision (webcam) affect** as a second modality — the browser computes a
motion/startle proxy locally (only the derived numbers are sent), ready to swap
for a real facial-expression model.

### `engine/experience/` — the director
- `orchestrator.py` — the core creative logic. Given `AffectState` + the
  `AssetBank`, it:
  - maintains a **smoothed intensity** (a tension curve) so directives don't
    jitter frame to frame;
  - picks a **target mood** from fear/stress/arousal;
  - selects matching assets (character, ambient, stinger, map) by tag;
  - enforces a **safety back-off**: if a rolling stress EMA exceeds
    `STRESS_SAFETY_CEILING`, it forces the `relief` mood and lowers intensity.
- `state.py` — an in-memory `SessionStore` holding each session, its bank, its
  orchestrator, and bounded affect history. A module-level singleton for the
  prototype.

### `engine/api/` — the surface
FastAPI. `sessions.py` covers lifecycle + (background) generation; `eeg.py`
covers the REST batch endpoint and the WebSocket live loop; `health.py` for
readiness. `main.py` wires routers under `API_PREFIX` (default `/v1`), opens
CORS for local game clients, and mounts the `web/` client at `/`.

### `web/` — the game client (replaces the DirectX runtime)
A first-person **raycasting** renderer in pure HTML5 canvas + WebAudio — no
game engine, no libraries, no build step, no DirectX. `index.html` is the HUD
and controls; `js/game.js` is the renderer + audio + two input modes:

- **Local sim** — a compact JS mirror of the Python affect + director so the
  game plays standalone (open the file, no server, no headset).
- **Live engine** — creates a session, streams synthetic `EEGChunk`s to the
  WebSocket `/stream`, and renders the `Directive`s the engine returns.

The renderer maps a `Directive` straight onto what you see and hear: `mood`
tints the walls, `intensity` drives fog/darkness and the stalker's aggression,
`heartbeat_bpm` sets the WebAudio pulse, `flicker` darkens the lights, and
`safety_backoff` forces the calm `relief` palette.

**Why a browser client?** The original plan was a native **DirectX 12** runtime
(`runtime/`, C++/CMake/vcpkg). It was Windows-only, heavy to build, and never
ran. Because the engine already exposes everything over HTTP + WebSocket, the
client is just a consumer of `Directive`s — so a zero-install web renderer gives
the same experience on every platform. Unity/Unreal remain drop-in alternatives
against the identical API.

## Data flow (live loop)

```
game client ──EEGChunk──▶ POST /eeg  (or WS /stream)
                              │
                    infer_affect(chunk)          # engine/eeg
                              │  AffectState
                    store.update_affect(sid, a)  # engine/experience
                              │
                    orchestrator.step(a, bank)   # tension + safety + selection
                              │  Directive
game client ◀──affect+directive──┘
```

## Key design decisions & trade-offs

| Decision | Why | Trade-off / when to revisit |
|---|---|---|
| White-box heuristic affect model | Explainable, no training data needed | Lower accuracy; replace with trained model once labelled EEG exists |
| In-memory session store | Zero infra for the prototype | Single-process only; move to Redis/Firestore for horizontal scale |
| Provider ABC + mock fallback | Runs with no cloud; swappable backends | Mock isn't representative of real latency/cost |
| Pre-generate an asset bank | Keeps the live loop model-free & fast | Less "infinite" variety than per-moment generation; add streaming gen later |
| FFT periodogram (not Welch) | Minimal deps, easy to read | Noisier estimates; add proper windowing + artifact rejection for real signals |
| Directive = named IDs, not media | Engine stays media-agnostic; client resolves assets | Client must know how to fetch/resolve URIs |

## Scaling path (summary)

1. **Stateful → stateless workers:** move `SessionStore` to Redis/Firestore;
   the orchestrator becomes a pure function of `(affect_history, bank)`.
2. **Async generation at scale:** push asset-generation jobs onto a queue
   (Cloud Tasks / Pub/Sub) with a worker pool; store media in GCS.
3. **Live loop scale:** the WS handler is CPU-light (one FFT per window); scale
   horizontally behind a sticky-session load balancer, or move affect inference
   to the edge/client and send only `AffectState` up.
4. **Model serving:** replace the heuristic with a served classifier (Vertex
   Endpoint) behind the same `EEGChunk → AffectState` interface.

Detailed, ticket-sized tasks are in [`ROADMAP.md`](./ROADMAP.md).
