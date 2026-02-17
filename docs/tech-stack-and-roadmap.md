# PredictionTrader: Tech Stack Review, Recommendations, and Milestones

## Executive take

Your plan is strong and realistic for a solo builder. The architecture (Tauri shell + Python sidecar + local SQLite + local inference) is a pragmatic way to keep operating costs near zero while still supporting real-time workflows.

Biggest likely struggles:

1. **Cross-language process lifecycle complexity** (Rust <-> Python bootstrapping, health checks, graceful shutdown).
2. **Data consistency under high-frequency streams** (reconnects, out-of-order events, idempotency).
3. **Packaging and distribution reliability** across platforms (Nuitka + Tauri sidecar mechanics).
4. **Compliance/safety UX** for live trading (kill switch guarantees, clear mode separation).

---

## Revised tech stack (recommended changes)

## 1) Desktop wrapper
- **Keep:** Tauri (Rust).
- **Add:** Explicit command boundary: only Tauri can access OS keychain and only Tauri can initiate secret handoff.
- **Change:** Prefer **stdin one-time secret handoff** over localhost HTTP POST where possible (smaller attack surface).

## 2) UI command center
- **Keep:** React + TypeScript + Zustand + Lightweight Charts.
- **Refine:** Use one unidirectional data flow pipeline:
  - WS/event stream -> worker normalize -> Zustand store slices -> derived selectors.
- **Change:** Replace “16ms debounce” wording with **frame-coalescing** via `requestAnimationFrame` (debounce can drop critical transitions).

## 3) Core engine sidecar
- **Keep:** Python + FastAPI.
- **Add:** Internal domain layering now to avoid rewrite:
  - `connectors/` (Kalshi, cloud sentiment)
  - `services/` (strategy, risk, state sync)
  - `adapters/` (db, api, ws)
- **Change:** Use **startup token challenge** between Tauri and sidecar to ensure only parent process can initialize secrets.

## 4) Local DB
- **Keep:** SQLite WAL + single write queue.
- **Add:** Strict event ledger tables with monotonic ingest IDs for idempotent replay.
- **Change:** Reserve separate read models/materialized views for UI query speed.

## 5) ML inference
- **Keep goal:** lightweight local inference.
- **Change:** For Python runtime simplicity, evaluate **ONNX Runtime** first, TFLite second.
  - TFLite in Python desktop apps can be friction-heavy depending on platform builds.
  - ONNX often has smoother packaging story with Nuitka.

## 6) Packaging
- **Keep:** Nuitka for sidecar binary attempt.
- **Risk mitigation:** Maintain fallback packaging path (`PyInstaller onefile`) behind CI flag in case Nuitka edge cases block release.

## 7) Sentiment pipeline
- **Keep:** cloud aggregation API.
- **Add:** cache invalidation contract (`generated_at`, `ttl_s`, `source_health`) and a local “confidence” scalar.

---

## Milestones (re-sequenced for lower risk)

## Milestone 0 (new): Foundation & guardrails
Goal: stabilize architecture boundaries and safety semantics before exchange integration.

- Process contract (spawn, handshake, health, shutdown)
- Secrets lifecycle policy
- Event schema and DB migration baseline
- Observability baseline (structured logs, error codes)
- Demo/live mode safety gates

## Milestone 1: Core trading engine & local API
(Your current Milestone 1, but after M0 artifacts are in place)

## Milestone 2: Intelligence & strategy layer
(keep with sentiment-decay safeguards)

## Milestone 3: UX & security hardening
(keep, but pull keyring + mode safety pieces earlier into M0)

## Milestone 4: Command center UI
(keep; build against stable event contracts)

## Milestone 5: Packaging & distribution
(keep; begin packaging spike in M0 to de-risk)

---

## Obvious conflicts / pitfalls and better options

1. **Port-0 sidecar + one-time secret POST** can race on startup.
   - Better: sidecar writes readiness line with nonce; Tauri sends secret over stdin with nonce confirmation.
2. **WebSocket reconnect + DB writer queue** without event idempotency can duplicate state.
   - Better: persist source event IDs and enforce upsert-on-id semantics.
3. **“Flatten all” guarantee** conflicts with connectivity outages.
   - Better: explicit state machine with degraded mode and user-facing “flatten requested, pending exchange confirm”.
4. **TFLite + Nuitka + cross-platform** may cause packaging drag for solo dev.
   - Better: run packaging spike early on all target OSes before ML lock-in.
5. **Realtime UI throttling** can hide critical risk events.
   - Better: throttle chart rendering, not risk alerts/activity feed.

---

## Cost-control guidance (solo-friendly)

- Start with one cloud VM for sentiment aggregation (small fixed-cost droplet).
- Keep market data and execution local through Kalshi APIs.
- Avoid managed streaming infrastructure until user count justifies it.
- Implement robust local logging + optional compressed diagnostic export instead of costly cloud observability.
- Delay model complexity: begin with deterministic strategies + simple sentiment-weighted score before ML rollout.
