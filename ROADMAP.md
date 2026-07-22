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
- 🟡 **DX12 runtime scaffold** (`runtime/`): CMake+vcpkg project; a client that
  composes a Script and prints the authored level (protocol proven). Renderer
  (DirectX 12 + glTF/Draco + ozz + XAudio2) is the next build-out

---

## Workstream A — EEG hardware & ingestion
Turn real headset data into clean `EEGChunk`s.

- ⬜ **A1** Integrate a real headset SDK (LSL / Muse / OpenBCI / Emotiv) → adapter that emits `EEGChunk`
- ⬜ **A2** Build a device gateway (client-side) that streams to the WS `/stream` endpoint
- ⬜ **A3** Signal quality: contact/impedance check, dropout detection, per-channel gating
- ⬜ **A4** Artifact rejection (eye blinks / EMG / motion) before band-power extraction
- ⬜ **A5** Replace FFT periodogram with Welch + proper windowing/overlap
- ⬜ **A6** Timestamp sync & jitter handling across channels

## Workstream B — Affect model
Move from heuristics to a validated model behind the same `EEGChunk → AffectState` interface.

- ⬜ **B1** Calibration routine per player (baseline eyes-open/closed, resting FAA)
- ⬜ **B2** Data collection protocol + labelling (self-report + stimulus tags) with consent
- ⬜ **B3** Train a classifier/regressor (arousal/valence → fear/stress), validate against heuristics
- ⬜ **B4** Serve it on a Vertex AI Endpoint; wire behind `infer_affect` as a strategy
- ⬜ **B5** Online personalization / drift correction during a session
- ⬜ **B6** Confidence-aware fusion (ignore low-SNR windows in the director)

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

## Workstream D — Experience / director
Deeper, smarter real-time adaptation.

- 🟢 **D1** Tension curve + mood selection + safety back-off (prototype)
- ⬜ **D2** Richer director policy (pacing beats, jump-scare cooldowns, habituation modelling)
- ⬜ **D3** Per-player fear model: learn what *this* player reacts to, weight assets accordingly
- ⬜ **D4** Difficulty/comfort modes (intensity caps, opt-out categories)
- ⬜ **D5** Deterministic replay of a session from recorded affect (for tuning/QA)
- ⬜ **D6** A/B experiment hooks for director policies

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

- ⬜ **F1** Reference Unity (or Unreal) client: consume `Directive`, resolve assets by URI/id
- ⬜ **F2** Asset resolver: download/stream sounds, spawn characters, apply map mutations
- ⬜ **F3** In-game debug overlay (live affect + directive + safety state)
- ⬜ **F4** Latency budget & smoothing on the client side

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
