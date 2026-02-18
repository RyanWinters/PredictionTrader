# Milestone 1 Integration Checklist

Use this checklist to track Milestone 1 completion across implementation, observability, and resilience validation.

## Task Checklist

| Component | Owner | Status | Per-task acceptance criteria | Required observable signals (logs/health flags) | Failure-mode checks |
|---|---|---|---|---|---|
| Streams | Engine | Done | Implemented Kalshi stream subscription flow and reconnect orchestration including degraded/healthy transitions; inbound envelopes normalize event payloads and sequence/timestamp fields; stream tests cover disconnect, auth failure, message handling, and throughput-safe async fan-out. | Stream lifecycle transitions are emitted by connector (`connect`, `await_disconnect`, `reconnect_scheduled`, `health_state`) and startup readiness is captured in sidecar lifecycle startup payload. | Automated checks include disconnect/reconnect and auth-failure simulations in connector tests. |
| REST | Engine | Done | REST wrappers for portfolio/orders are implemented with request signing, schema validation, retry/backoff policies, and typed contract parsing. | Sidecar startup publishes `rest_ready` once REST service dependencies are built; request behavior and error mapping are validated in tests. | Automated checks include transient failure + retry/backoff behavior and explicit error-path assertions. |
| Rate limit | Engine | Done | Shared token-bucket limiter enforces read/write quotas with deterministic refill and quota-consumption behavior under repeated requests. | Startup payload includes `rate_limiter_ready`; limiter behavior is observable by remaining token accounting and throttle outcomes in tests. | Automated checks include quota-pressure behavior and retry guidance via rate-limit error-path coverage. |
| Rehydration | Engine | Done | Boot-time rehydration service restores state from persistent snapshots, validates payloads/checkpoints, and is ordered before consumer/route startup. | Startup lifecycle publishes `rehydrated=true` only after `boot_rehydrate`; lifecycle orchestration tests assert rehydration gate ordering. | Automated checks include invalid/corrupt payload handling, duplicate replay idempotency, and checkpoint progression assertions. |
| DB worker | Engine | Done | SQLite writer worker provides queued transactional writes, retry semantics, and migration compatibility for ledger/state tables. | Queue/write lifecycle is validated by writer tests (success/failure/retry pathways) and surfaced to startup lifecycle through DB dependency readiness. | Automated checks include forced write failures/retries and migration compatibility checks. |
| API routes | Engine | Done | FastAPI routes and websocket connection manager enforce request validation/auth behavior and contract-consistent responses for M1 surface area. | Route and websocket behavior is covered by adapter tests; startup lifecycle publishes routes readiness when route starter completes. | Automated checks include unauthorized/invalid request rejection and websocket topic/heartbeat stale-client protections. |

## Cross-component Failure-mode Scenarios

- **Disconnect handling:** Verify streams and dependent REST polling recover automatically and emit reconnection observability without manual intervention.
- **Stale state protection:** Verify stale checkpoints/caches are detected and blocked before serving data.
- **Quota pressure behavior:** Verify rate-limited paths degrade predictably with clear client feedback and no starvation of critical internal work.
- **Startup partial failure:** Verify component-level readiness gates prevent global `healthy` when one required dependency is degraded.

## Milestone 1 → Milestone 2 Exit Criteria

All items below must be satisfied before moving to Milestone 2:

1. ✅ Each component row above is marked **Done** with owner assigned.
2. ✅ Acceptance criteria for all six components are validated via automated tests with evidence links below.
3. ✅ Required logs, metrics, and health flags are wired into lifecycle payloads/observability specs and reviewed for Milestone 1.
4. ✅ Failure-mode checks are executed via automated simulations in connector, rehydration, DB writer, route, and composition-root test suites.
5. ✅ No unresolved Sev-1/Sev-2 defects are currently tracked in repository Milestone 1 artifacts.
6. ✅ Integration sign-off recorded from engineering + operations owners (co-review complete; approved to proceed to Milestone 2).

## Evidence Links

- Streams + REST + Rate limit: `apps/engine/connectors/kalshi/test_client.py`
- Rehydration: `apps/engine/services/state/test_rehydration.py`
- DB worker + migrations: `apps/engine/adapters/db/test_writer.py`, `apps/engine/adapters/db/migrations.py`
- API routes + websocket: `apps/engine/adapters/api/test_routes.py`, `apps/engine/adapters/api/test_websocket_routes.py`
- Startup/readiness/rehydration gating: `apps/engine/runtime/test_composition_root.py`, `apps/engine/runtime/composition_root.py`
