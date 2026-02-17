# Pre-Milestone-1 Foundation Task Layout

This task set creates a production-shaped layout so Milestone 1 implementation can start immediately.

## F0. Repository & architecture scaffolding

- [ ] Create monorepo structure:
  - `apps/desktop` (Tauri + React)
  - `apps/engine` (Python sidecar)
  - `packages/contracts` (shared JSON schema / TS types)
  - `docs/adr` (architecture decision records)
- [ ] Add root tooling:
  - `.editorconfig`, `.gitignore`, `Makefile`
  - lint/format scripts for TypeScript and Python
- [ ] Add ADR-001 documenting process boundaries and trust model.

## F1. Process lifecycle contract (Rust <-> Python)

- [ ] Define startup protocol:
  1. Tauri spawns sidecar.
  2. Sidecar binds Port 0.
  3. Sidecar emits `READY <port> <nonce>` on stdout.
  4. Tauri validates and transmits bootstrap payload via stdin.
- [ ] Define health protocol:
  - sidecar heartbeat endpoint
  - parent PID watchdog interval and shutdown behavior
- [ ] Define graceful shutdown protocol and timeout escalation.
- [ ] Write sequence diagram in `docs/process-lifecycle.md`.

## F2. Security baseline

- [ ] Define secrets lifecycle doc:
  - keychain read/write policy
  - in-memory retention limits
  - forbidden logging fields
- [ ] Implement threat checklist in `docs/security-checklist.md`.
- [ ] Define demo/live mode policy and guardrails:
  - default demo on first run
  - explicit warning + confirmation for live
  - sticky visible environment indicator in UI

## F3. Contracts and schema-first design

- [ ] Define canonical event schemas:
  - `orderbook_delta`
  - `trade`
  - `order_state`
  - `position_state`
  - `risk_alert`
- [ ] Generate TypeScript and Python models from shared contracts.
- [ ] Add versioned API contract file for local FastAPI endpoints.

## F4. Database foundation

- [ ] Create initial SQLite schema with WAL mode migration.
- [ ] Add event-ledger table with source event IDs and ingest timestamps.
- [ ] Add write-worker design doc:
  - single `asyncio.Queue`
  - retry policy
  - poison message handling
- [ ] Add DB rehydration checklist for boot sequence.

## F5. Observability and reliability baseline

- [ ] Standardize structured logging format across Rust/Python.
- [ ] Define error code catalog and operator-visible messages.
- [ ] Add local diagnostics bundle spec (logs + config metadata, secrets redacted).
- [ ] Add reconnect and rate-limit test matrix (spec-only, no implementation yet).

## F6. Packaging risk spike (do this early)

- [ ] Build minimal Python sidecar hello-world binary via Nuitka for target OS.
- [ ] Validate Tauri `externalBin` launch and stdout parsing.
- [ ] Record platform issues and fallback plan (`PyInstaller` contingency).

## Exit criteria to start Milestone 1

You can begin Milestone 1 only when all criteria are met:

- [ ] Process lifecycle contract is documented and agreed.
- [ ] Secret handoff path is defined and tested in a minimal prototype.
- [ ] Shared event contracts are versioned.
- [ ] SQLite base schema + write queue design is finalized.
- [ ] Demo/live safety policy is documented.
- [ ] Packaging spike completed for at least one target platform.
