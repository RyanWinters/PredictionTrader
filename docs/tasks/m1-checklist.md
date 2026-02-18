# Milestone 1 Integration Checklist

Use this checklist to track Milestone 1 completion across implementation, observability, and resilience validation.

## Task Checklist

| Component | Owner | Status | Per-task acceptance criteria | Required observable signals (logs/health flags) | Failure-mode checks |
|---|---|---|---|---|---|
| Streams |  | Not started | Stream consumers connect and subscribe to required channels; message ordering guarantees documented; duplicate/out-of-order handling implemented; reconnect logic resumes from last safe checkpoint; integration tests validate expected event throughput and latency bounds. | Connection lifecycle logs (`connected`, `reconnecting`, `disconnected`); per-stream lag metric; processed events/sec metric; health flag `streams_ready=true` only after active subscription and first successful message processing. | Simulate upstream disconnect and verify auto-reconnect; inject burst traffic to detect dropped events; verify stale stream detection triggers alert when no events received beyond threshold. |
| REST |  | Not started | REST client/server calls succeed for required endpoints; request/response schemas validated; idempotency behavior defined for retries; timeout and retry policy enforced; contract tests pass for success and expected error payloads. | Request summary logs (method, route, status, latency bucket); error logs include upstream/service code; health flag `rest_ready=true` only after dependency probe succeeds; p95 latency metric exposed. | Force dependency timeout and verify retry/backoff; validate graceful degradation on 5xx; verify stale cached response is not served past TTL. |
| Rate limit |  | Not started | Global and per-route/per-key quotas enforced as specified; limiter behavior deterministic under concurrency; reject responses include retry guidance; no quota bypass via alternate route pathing. | Quota consumption metric; throttle event logs with limiter key and reason; health flag `rate_limiter_ready=true`; dashboard panel for reject rate and remaining capacity. | Load test near quota edge to verify soft/hard limits; simulate quota pressure and confirm correct 429 behavior; verify system remains responsive without cascading failures. |
| Rehydration |  | Not started | Startup/backfill restores in-memory state from persistent source to consistent checkpoint; rehydration completion gate blocks dependent processing until ready; checksum/version validation detects mismatches; replay idempotent for duplicate records. | Startup logs with rehydration phase markers (`started`, `progress`, `completed`); duration metric; count of restored entities; health flag `rehydration_ready=true` only at consistency checkpoint. | Simulate partial snapshot/corrupt payload and verify safe fail-fast; verify stale checkpoint triggers replay; inject duplicate replay records and confirm idempotent state. |
| DB worker |  | Not started | Worker queue consumes jobs within SLA; transactional boundaries guarantee atomic writes; retry and dead-letter rules implemented; backpressure handling prevents uncontrolled queue growth; migration compatibility validated. | Job lifecycle logs (`queued`, `started`, `succeeded`, `failed`, `dead-lettered`); queue depth metric; job age metric; health flag `db_worker_ready=true` after connectivity and first successful write cycle. | Kill DB connection mid-job and verify retry semantics; simulate long-running job to test queue starvation protections; induce write conflict to confirm deterministic retry/abort behavior. |
| API routes |  | Not started | All Milestone 1 routes implemented and documented; request validation and auth checks enforced; response codes consistent with API contract; route-level integration tests pass; backward compatibility for existing consumers maintained. | Route-level access logs with correlation IDs; structured validation/auth failure logs; health flag `api_routes_ready=true` when route registry and dependencies are initialized; per-route error-rate metric. | Test unauthorized/invalid requests for correct rejection paths; simulate downstream dependency outage and verify controlled error responses; verify startup with one missing dependency marks affected routes unavailable, not silent success. |

## Cross-component Failure-mode Scenarios

- **Disconnect handling:** Verify streams and dependent REST polling recover automatically and emit reconnection observability without manual intervention.
- **Stale state protection:** Verify stale checkpoints/caches are detected and blocked before serving data.
- **Quota pressure behavior:** Verify rate-limited paths degrade predictably with clear client feedback and no starvation of critical internal work.
- **Startup partial failure:** Verify component-level readiness gates prevent global `healthy` when one required dependency is degraded.

## Milestone 1 → Milestone 2 Exit Criteria

All items below must be satisfied before moving to Milestone 2:

1. Each component row above is marked **Done** with owner assigned.
2. Acceptance criteria for all six components are validated via automated tests or documented runbooks with evidence links.
3. Required logs, metrics, and health flags are wired into dashboards/alerts and reviewed.
4. Failure-mode checks have been executed in a staging-like environment with outcomes documented.
5. No unresolved Sev-1/Sev-2 defects remain for Milestone 1 scope.
6. Integration sign-off is recorded from engineering + operations owners.
