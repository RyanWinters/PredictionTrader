# PredictionTrader: Unified Tech Stack and Milestone Roadmap

This document is the canonical, up-to-date plan that integrates the original milestone definitions with subsequent architectural updates already documented in the repository.

## Planning principles

- Keep the app desktop-first and low-cost for solo development.
- Keep secrets and privileged operations in Rust/Tauri boundaries.
- Treat reliability and safety as first-class requirements (not polish work).
- Sequence milestones so architecture and guardrails are in place before aggressive feature expansion.

---

## Canonical tech stack

### 1) Desktop wrapper (Tauri + Rust)

**Role:** app shell, OS integration, keychain, process orchestration, and trust boundary enforcement.

- Tauri owns the application window and System Tray behavior.
- Tauri is the only process allowed to access OS keychain material.
- Tauri spawns the Python sidecar without passing secrets via command line args.
- Sidecar boot uses Port 0 binding and readiness signaling so Tauri can discover the ephemeral port.
- Secret handoff path is one-time and in-memory, with stdin handoff as preferred path and localhost authenticated POST as a controlled fallback when needed by platform/runtime constraints.

### 2) UI command center (React + TypeScript)

**Role:** operator-facing dashboard and controls.

- State management: Zustand.
- Charting: Lightweight Charts (TradingView).
- Heavy JSON parsing/normalization runs in a Web Worker.
- Rendering strategy uses frame-coalescing via `requestAnimationFrame` to maintain responsiveness near 60fps while avoiding unnecessary CPU load.
- The prior "16ms debounce" concept is interpreted as frame-budgeted updates, with critical risk alerts bypassing chart-throttle paths.

### 3) Core engine sidecar (Python + FastAPI)

**Role:** trading engine, exchange connectivity, strategy/risk orchestration, and local API.

- Spawned and supervised by Tauri.
- Binds to ephemeral port (Port 0), then announces readiness.
- Implements a PPID watchdog so orphaned sidecars self-terminate safely.
- Process lifecycle includes startup handshake, heartbeat health checks, and graceful shutdown escalation.
- Recommended internal layering:
  - `connectors/` (Kalshi + cloud sentiment)
  - `services/` (strategy, risk, state sync)
  - `adapters/` (db, api, ws)

### 4) Local database (SQLite WAL)

**Role:** local event/state persistence and rehydration source.

- SQLite in WAL mode for read/write concurrency.
- All writes are serialized through a dedicated `asyncio.Queue` worker.
- Event-ledger tables store source event IDs + ingest timestamps for idempotent replay/recovery.
- Boot-time state rehydration reconciles exchange truth with local state before trading resumes.

### 5) Machine learning and inference

**Role:** local inference for strategy augmentation.

- Primary target: TensorFlow Lite (`.tflite`) models for lightweight desktop inference.
- Mandatory stale-data protection: sentiment decay protocol that neutralizes or blocks sentiment-driven inference when upstream data quality degrades.
- Practical fallback: evaluate ONNX Runtime if packaging/portability constraints materially threaten release reliability.

### 6) Packaging and distribution

**Role:** produce a double-clickable desktop product.

- Primary package path: Nuitka-compiled Python sidecar as Tauri `externalBin`.
- Keep PyInstaller contingency documented for schedule-risk mitigation if Nuitka blocks target-platform release.

### 7) Data pipeline

**Role:** cloud sentiment aggregation with controlled local consumption.

- Cloud scraping proxy (e.g., DigitalOcean droplet) handles Reddit/Discord/RSS collection.
- Local engine consumes aggregated sentiment via constrained API contract.
- Contract includes freshness metadata (`generated_at`, `ttl_s`, source health/confidence) to enforce decay/failsafe behavior.

---

## Milestone sequence

Milestones are sequenced to preserve safety and implementation realism.

## Milestone 0: Foundation and guardrails (precondition milestone)

Goal: lock process boundaries, trust model, and reliability baselines before exchange-grade runtime work.

- Process contract: spawn, handshake, health, shutdown.
- Secret lifecycle policy and secure handoff prototype.
- Canonical event contracts and DB migration baseline.
- Observability baseline: structured logs, error taxonomy, diagnostics bundle.
- Demo/live safety gates and mode semantics.
- Packaging spike completed on at least one target platform.

Reference: `docs/tasks/pre-m1-foundation.md` and linked specs.

## Milestone 1: Core trading engine and local API

Goal: build execution/data plumbing, connect to Kalshi, and establish a robust local sidecar API.

### Epic 1.1: Exchange execution and streaming data

- **Task 1.1.1:** Implement Kalshi async WebSockets for `orderbook_delta` and `trade` streams.
- **Task 1.1.2:** Build Python REST wrappers for order execution and portfolio balance checks.
- **Task 1.1.3:** Implement resilient WebSocket reconnect with exponential backoff.
- **Task 1.1.4:** Add token-bucket limiter aligned to Kalshi tier constraints (20 reads/s, 10 writes/s).
- **Task 1.1.5:** Implement startup state rehydration of open orders/positions to sync SQLite before trading resumes.

### Epic 1.2: Local data vault and server

- **Task 1.2.1 (updated):** Finalize SQLite WAL schema + single `asyncio.Queue` write worker to prevent lock contention.
- **Task 1.2.2:** Build FastAPI local endpoints for execution plus local WebSocket routes for frontend streaming.

## Milestone 2: Intelligence and strategy layer

Goal: implement strategies and attach them to safe, external sentiment signals.

### Epic 2.1: Cloud data pipelines ("Omni-Vibe" API)

- **Task 2.1.1:** Build centralized cloud scraper service (RSS/Reddit/Discord) producing bullish/bearish scores.
- **Task 2.1.2:** Implement local Python client consuming aggregated sentiment API.
- **Task 2.1.3 (new):** Enforce sentiment decay protocol; neutralize sentiment or trigger kill-switch behavior on stale/unavailable feed.

### Epic 2.2: Playbook and ML inference

- **Task 2.2.1:** Implement "Volatility Rider" and "Hype-Fade" logic.
- **Task 2.2.2:** Train in cloud, export `.tflite`, bundle for local inference.

Implementation note: we are currently executing Milestone 2 with a **local-first training path** and optional later cloud migration. See `docs/milestone-2-local-first-guide.md`.

## Milestone 3: End-user experience and security

Goal: make operation safer, clearer, and self-contained for end users.

### Epic 3.1: Onboarding wizard and Rust security

- **Task 3.1.1:** Build React 3-step onboarding for Kalshi API key setup.
- **Task 3.1.2 (updated):** Implement Rust keyring + no-CLI-secret spawn model; perform one-time in-memory secret handoff after sidecar readiness (stdin preferred, authenticated local HTTP fallback).

### Epic 3.2: Paper-trade sandbox

- **Task 3.2.1:** Default first run to Kalshi demo endpoint.
- **Task 3.2.2:** Add prominent demo/live toggle requiring explicit liability acknowledgement for live mode.

## Milestone 4: Command center UI

Goal: provide full visual control and transparency without UI lag.

### Epic 4.1: Dashboard and state

- **Task 4.1.1 (updated):** Implement Zustand stores fed by local streams; use Web Worker for heavy rehydration parsing; use frame-coalesced rendering (`requestAnimationFrame`) for stable 60fps-class updates.
- **Task 4.1.2:** Build event-contract-focused step-line charts with sentiment overlays.
- **Task 4.1.3:** Implement real-time activity feed explaining bot decisions.

### Epic 4.2: User controls and panic buttons

- **Task 4.2.1:** Add risk management controls posting updates to FastAPI.
- **Task 4.2.2:** Build global "Flatten All" kill switch to flatten exposure and halt trading workflows.

## Milestone 5: Packaging and distribution

Goal: ship a commercial-quality desktop app with robust sidecar lifecycle management.

### Epic 5.1: Tauri bundling and process management

- **Task 5.1.1:** Compile Python backend into standalone executable via Nuitka.
- **Task 5.1.2:** Configure `tauri.conf.json` `externalBin` integration.
- **Task 5.1.3:** Implement Rust startup flow reading sidecar ephemeral port from stdout and exposing connection info to UI.
- **Task 5.1.4:** Implement System Tray lifecycle (minimize-to-tray, explicit Quit, graceful sidecar termination).
- **Task 5.1.5 (new):** Enforce Python PPID watchdog: if parent disappears/reparents, cancel open orders, close SQLite, and self-terminate.

---

## Cross-milestone cohesion checks

To keep milestones coherent with the chosen stack:

- **Security boundary:** only Tauri handles secrets and privileged OS integration.
- **Runtime resilience:** reconnect/idempotency/rehydration are mandatory before strategy complexity grows.
- **Data freshness safety:** sentiment-driven logic must degrade safely when upstream data is stale.
- **UI truthfulness:** throttling optimizes rendering only, never suppresses safety-critical signals.
- **Packaging realism:** Nuitka-first with explicit fallback path protects delivery timelines.
