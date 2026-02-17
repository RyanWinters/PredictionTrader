# Pre-Milestone-1 Foundation Task Layout

This task set creates a production-shaped layout so Milestone 1 implementation can start immediately.

## F0. Repository & architecture scaffolding

- [x] Create monorepo structure:
  - `apps/desktop` (Tauri + React)
  - `apps/engine` (Python sidecar)
  - `packages/contracts` (shared JSON schema / TS types)
  - `docs/adr` (architecture decision records)
- [x] Add root tooling:
  - `.editorconfig`, `.gitignore`, `Makefile`
  - lint/format scripts for TypeScript and Python
- [x] Add ADR-001 documenting process boundaries and trust model.

## F1. Process lifecycle contract (Rust <-> Python)

- [x] Define startup protocol:
  1. Tauri spawns sidecar.
  2. Sidecar binds Port 0.
  3. Sidecar emits `READY <port> <nonce>` on stdout.
  4. Tauri validates and transmits bootstrap payload via stdin.
- [x] Define health protocol:
  - sidecar heartbeat endpoint
  - parent PID watchdog interval and shutdown behavior
- [x] Define graceful shutdown protocol and timeout escalation.
- [x] Write sequence diagram in `docs/process-lifecycle.md`.

## F2. Security baseline

- [x] Define secrets lifecycle doc:
  - keychain read/write policy
  - in-memory retention limits
  - forbidden logging fields
- [x] Implement threat checklist in `docs/security-checklist.md`.
- [x] Define demo/live mode policy and guardrails:
  - default demo on first run
  - explicit warning + confirmation for live
  - sticky visible environment indicator in UI

## F3. Contracts and schema-first design

- [x] Define canonical event schemas:
  - `orderbook_delta`
  - `trade`
  - `order_state`
  - `position_state`
  - `risk_alert`
- [x] Generate TypeScript and Python models from shared contracts.
- [x] Add versioned API contract file for local FastAPI endpoints.

## F4. Database foundation

- [x] Create initial SQLite schema with WAL mode migration.
- [x] Add event-ledger table with source event IDs and ingest timestamps.
- [x] Add write-worker design doc:
  - single `asyncio.Queue`
  - retry policy
  - poison message handling
- [x] Add DB rehydration checklist for boot sequence.

## F5. Observability and reliability baseline

- [x] Standardize structured logging format across Rust/Python.
- [x] Define error code catalog and operator-visible messages.
- [x] Add local diagnostics bundle spec (logs + config metadata, secrets redacted).
- [x] Add reconnect and rate-limit test matrix (spec-only, no implementation yet).
- Reference spec: [Observability and Reliability Baseline Spec](../observability-and-reliability-spec.md).

## F6. Packaging risk spike (do this early)

- [x] Build minimal Python sidecar hello-world binary via Nuitka for target OS.
- [x] Validate Tauri `externalBin` launch and stdout parsing.
- [x] Record platform issues and fallback plan (`PyInstaller` contingency).

## Exit criteria to start Milestone 1

You can begin Milestone 1 only when all criteria are met:

- [x] Process lifecycle contract is documented and agreed.
- [ ] Secret handoff path is defined and tested in a minimal prototype.
- [x] Shared event contracts are versioned.
- [x] SQLite base schema + write queue design is finalized.
- [x] Demo/live safety policy is documented.
- [x] Packaging spike completed for at least one target platform.
