# Roadmap & Task Breakdown

This is the plan to take the engine from **prototype** (what's in this repo) to a
scalable product. Tasks are grouped into workstreams and sized to be ticketable.
Check items off as you go.

**Legend:** 🟢 done in prototype · 🟡 partial/stubbed · ⬜ not started

---

## Where we are (prototype — this repo)

- 🟢 End-to-end loop runs offline (EEG simulator + mock asset provider)
- 🟢 EEG → band powers → affect (fear / stress / arousal / engagement / valence)
- 🟢 Asset pipeline with pluggable providers (`mock`, `vertex`)
- 🟢 Orchestrator with tension curve + stress safety back-off
- 🟢 HTTP + WebSocket API (sessions, generate, assets, eeg, stream)
- 🟢 Tests (affect monotonicity, pipeline, API lifecycle) + demo script
- 🟢 Vertex AI provider **verified live** (Gemini specs + Imagen concept art →
  GCS), via the current `google-genai` SDK; Gemini on the `global` endpoint,
  Imagen regional
- 🟡 In-memory single-process state (not yet horizontally scalable)
- 🟢 **AI architect layer** (`engine/architect/`): a DataPoint catalog + a
  Claude/mock composer that authors a personalized **Script** (the level+event
  graph), plus a learning layer that updates a persisted per-player model from
  reactions. API: `GET /sessions/{id}/script`, `POST /sessions/{id}/reactions`
- 🟢 **Browser/WebGL game client** (`web/`): a first-person raycasting horror
  renderer in pure HTML5 canvas + WebAudio — no engine, no build, cross-platform.
  Consumes directives live over WebSocket (or runs standalone on a JS affect sim).
  **This replaces the abandoned DirectX 12 native runtime** (`runtime/`), which
  was Windows-only, required a C++/CMake/vcpkg toolchain, and never built cleanly.

---

## Workstream A — EEG hardware & ingestion
Turn real headset data into clean `EEGChunk`s.

- 🟡 **A1** Real headset adapter — **NeuroSky MindLink** (ThinkGear) implemented:
  single-channel FP1 @ 512 Hz, pure unit-tested packet parser, eSense +
  poor-signal surfaced (`engine/eeg/sources.py`). Verify against real hardware;
  add LSL / Muse / OpenBCI / Emotiv adapters behind the same interface
- 🟢 **A2** Client-side device gateway streams to the WS `/stream` (`engine/eeg/gateway.py`)
- 🟡 **A3** Signal quality: MindLink poor-signal gating + per-window confidence in
  place (`engine/eeg/artifacts.py`), surfaced in the game HUD; add impedance +
  dropout detection
- 🟢 **A4** Artifact rejection (blink / EMG / motion) with confidence gating — the
  director holds on low-confidence windows instead of reacting to noise
- 🟢 **A5** Welch PSD with Hann windowing + overlap (`engine/eeg/bands.py`)
- ⬜ **A6** Timestamp sync & jitter handling across channels

## Workstream B — Affect model
Move from heuristics to a validated model behind the same `EEGChunk → AffectState` interface.

- 🟡 **B1** Calibration: resting-baseline capture + affect re-centering
  (`engine/eeg/calibration.py`, `POST /sessions/{id}/calibrate`); add the guided
  eyes-open/closed protocol UI
- ⬜ **B2** Data collection protocol + labelling (self-report + stimulus tags) with consent
- ⬜ **B3** Train a classifier/regressor (arousal/valence → fear/stress), validate against heuristics
- ⬜ **B4** Serve it on a Vertex AI Endpoint; wire behind `infer_affect` as a strategy
- ⬜ **B5** Online personalization / drift correction during a session
- 🟢 **B6** Confidence-aware fusion — low-confidence (artifact/poor-signal)
  windows don't move the director
- 🟡 **B7** Multimodal fusion: computer-vision (webcam) affect fused with EEG
  (`fuse_cv`, `CvAffect`); browser sends a motion/startle proxy now — swap in a
  real facial-expression model next

## Workstream C — Generative assets
Make the asset bank real, richer, and cheaper.

- 🟢 **C1** `VertexProvider`: Imagen concept art uploaded to GCS, `Asset.uri` set
  (verified live against project `eeg-horror`, bucket `dduhwycdgcdg`)
- 🟡 **C2** Audio generation via **Lyria** (`lyria-002`): Gemini sound spec →
  Lyria music prompt → WAV uploaded to GCS, `Asset.uri` set. Enabled with
  `AUDIO_PROVIDER=lyria`. **Remaining to fully close C2:**
  - ⬜ Verify live (run `cloudshell_verify.sh`; confirm `gs://…/sounds/*.wav`)
  - ⬜ Seamless looping: Lyria clips are ~30s and not loop-safe — add
    crossfade/loop-point processing (e.g. ffmpeg) for gapless ambience
  - ⬜ Stems/SFX: Lyria is instrumental music only; add discrete SFX + stingers
    (separate model/library) and layer them per the spec's `layers`
  - ⬜ Cost/perf: cache by (theme, mood) and generate audio lazily (it's the
    slowest asset), plus a length/parameter budget
- ⬜ **C3** Map generation → an engine-consumable format (tilemap/graph the client can build)
- ⬜ **C4** Prompt templating + guardrails (avoid disallowed/triggering content per player opt-outs)
- ⬜ **C5** Asset caching & dedup keyed on seed (don't regenerate identical banks)
- ⬜ **C6** Streaming / just-in-time generation for long sessions (beyond the 4-mood bank)
- ⬜ **C7** Cost controls: budgets, model tiering, batch generation
- 🟢 **C8** **Per-run asset resolution** (`engine/assets/`): every DataPoint
  resolves to fresh, procedurally-varied media (map/model/character/image/sound/
  animation) seeded per run — different every playthrough, offline, no bloat
- ⬜ **C9** Wire `RemoteAssetSource` to real open libraries (Poly Haven, Freesound,
  Mixamo-style rigs) with a license/attribution manifest; cache to a local pack

## Workstream D — Experience / director
Deeper, smarter real-time adaptation.

- 🟢 **D1** Tension curve + mood selection + safety back-off (prototype)
- ⬜ **D2** Richer director policy (pacing beats, jump-scare cooldowns, habituation modelling)
- 🟢 **D3** Per-player fear model: learns what *this* player reacts to (DataPoint
  / tag / fear / co-occurrence scores) and **breeds new personalized DataPoints**
  (mutation + crossover) from the top performers (`engine/architect/evolution.py`)
- ⬜ **D4** Difficulty/comfort modes (intensity caps, opt-out categories)
- ⬜ **D5** Deterministic replay of a session from recorded affect (for tuning/QA)
- ⬜ **D6** A/B experiment hooks for director policies
- 🟢 **D7** **Escalation across runs** ("scarier and scarier"): a persisted per-
  player run counter raises the tension ceiling, shortens beats, and biases
  toward more intense DataPoints each restart (`PlayerModel.escalation()`)

## Workstream E — Platform, API & scale
Production-grade service.

- ⬜ **E1** Move `SessionStore` to Redis/Firestore; make orchestrator state externalized
- ⬜ **E2** AuthN/AuthZ (API keys / OAuth) + per-session ownership
- ⬜ **E3** Async generation via Cloud Tasks/Pub-Sub + worker pool; job status API
- ⬜ **E4** Deploy on Cloud Run/GKE; sticky-session LB for WebSockets; autoscaling
- ⬜ **E5** Rate limiting, quotas, and backpressure on the stream endpoint
- ⬜ **E6** Versioned API + OpenAPI client generation for the game engine
- ⬜ **E7** Structured logging, metrics, tracing (affect/directive telemetry dashboards)

## Workstream F — Game client integration
Close the loop with an actual game.

- 🟢 **F1** Reference **web/WebGL client**: consumes `Directive` live over the
  WebSocket `/stream` (replaces the DirectX runtime; Unity/Unreal still optional)
- 🟡 **F2** Asset resolver: the web client maps directives to walls/fog/stalker/
  heartbeat now; downloading real generated media (Imagen art, Lyria audio) by
  `Asset.uri` is the remaining piece
- 🟢 **F3** In-game debug overlay (live affect + directive + safety state HUD)
- 🟡 **F4** Latency budget & smoothing (director already smooths intensity;
  client-side interpolation/prediction still to add)

## Workstream I — High-fidelity runtime (WASM + WebGPU) & procedural assets
Take the browser client from the raycasting prototype to a real 3D horror engine
that still runs everywhere — and keep the footprint tiny.

> **On "DirectX in the browser":** browsers can't call DirectX directly. The
> browser's **WebGPU** implementation runs on **Direct3D 12** under the hood on
> Windows (Metal on macOS, Vulkan on Linux). So a **WASM + WebGPU** game *is*
> DirectX-backed GPU rendering on Windows while still running cross-platform in
> the browser — that's how we honour "DirectX" and "runs in the browser" at once.
> A separate native DirectX desktop build is possible but can't run in a browser.

- ⬜ **I1** WebGPU renderer (WebGL2 fallback) driven by the same `Directive` +
  `Script`; port the raycaster's role to real 3D corridors/rooms
- ⬜ **I2** Compile the runtime to **WebAssembly** (Rust `wgpu`, or C++ via
  Emscripten) for near-native performance in the browser
- ⬜ **I3** **Procedural asset compiler** (kkrieger-style, the 96 KB demoscene
  approach): DataPoint `params` (seeds/dims/palettes) → meshes, textures and
  audio generated **into RAM at load** — tiny on disk, full-fidelity in memory
- ⬜ **I4** Lossless asset packer: a build script that scans authored/imported
  assets and packs them 1:1 (dedup + lossless compression), so nothing bloats
- ⬜ **I5** Open model/animation import (e.g. Mixamo, other openly-licensed
  sources) with a license/attribution manifest; retarget onto encounter rigs
- ⬜ **I6** Script-driven runtime: walk the Beats, instantiate each Beat's
  DataPoints, hand off to the live EEG director for second-to-second modulation
- ⬜ **I7** Computer-vision affect: fuse webcam facial-affect into the reaction
  signal alongside EEG (the `cv_affect` field already exists on reactions)

## Workstream G — Safety, ethics & compliance
Non-negotiable before real users.

- 🟡 **G1** Stress safety back-off (prototype implemented; needs clinical review + tuning)
- ⬜ **G2** Informed consent flow; clear stop/pause; photosensitivity & health screening
- ⬜ **G3** EEG data governance: encryption at rest/in transit, retention limits, deletion
- ⬜ **G4** Privacy/regulatory review (EEG is sensitive personal data; GDPR/health-data rules)
- ⬜ **G5** Content safety: honor per-player fear opt-outs end to end (generation + director)
- ⬜ **G6** Red-team the safety rail (can the director get "stuck" escalating?)

## Workstream H — Quality & DevEx
- 🟢 **H1** Unit/integration tests + offline demo (prototype)
- ⬜ **H2** CI (lint + type-check + tests) on PRs
- ⬜ **H3** Load tests for the WS stream (concurrent sessions)
- ⬜ **H4** Contract tests against a real Vertex sandbox
- ⬜ **H5** Recorded-EEG fixtures for regression testing the affect model

---

## Suggested next 5 tasks (highest leverage)

1. **C1** — finish the Vertex media path (Imagen → GCS) so generated assets are real.
2. **F1/F2** — a minimal Unity client that consumes directives (proves the whole product).
3. **E1** — externalize session state (unblocks scaling and multi-worker deploys).
4. **A1** — one real headset adapter (proves the ingestion contract with hardware).
5. **G2** — consent + stop flow (gate for any real-user test).
