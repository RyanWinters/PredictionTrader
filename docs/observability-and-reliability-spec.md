# Observability and Reliability Baseline Spec

This document defines the **Milestone 0 / F5** baseline specs that both the Rust desktop process and Python engine process must follow.

## Scope

This spec covers:

1. Structured logging format shared by Rust and Python.
2. Error code catalog with user-visible and operator-visible messages.
3. Local diagnostics bundle contents and redaction requirements.
4. Reconnect and rate-limit test matrix (spec only).

---

## 1) Structured logging format (Rust + Python)

### 1.1 Log format and encoding

- **Format:** JSON Lines (one JSON object per line).
- **Encoding:** UTF-8.
- **Timestamp:** RFC3339/ISO-8601 in UTC (`Z` suffix).
- **Required behavior:** Never emit plaintext-only logs in production paths; framework default logs must be adapted into this schema.

### 1.2 Canonical log fields

The following fields are required unless marked optional.

| Field | Type | Required | Description |
|---|---|---:|---|
| `ts` | string | Yes | Event timestamp in UTC RFC3339 format. |
| `level` | string | Yes | Severity (`TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`). |
| `service` | string | Yes | Logical service name (`desktop`, `engine`). |
| `component` | string | Yes | Subsystem (`process_manager`, `ws_client`, `risk`, `db_writer`, etc.). |
| `event` | string | Yes | Stable event name in `snake_case`. |
| `message` | string | Yes | Human-readable summary for operators. |
| `correlation_id` | string | Yes | Cross-process/request correlation ID. |
| `session_id` | string | Yes | App session/run identifier generated at startup. |
| `span_id` | string | Optional | Fine-grained operation span ID for nested operations. |
| `error_code` | string | Optional | Stable error code from the catalog section below. |
| `attempt` | integer | Optional | Attempt count for retries/reconnect loops. |
| `backoff_ms` | integer | Optional | Backoff duration before next retry. |
| `rate_limit_scope` | string | Optional | Scope key for rate-limit handling (`rest.orders`, `ws.market_data`). |
| `details` | object | Optional | Additional structured details (must be non-secret). |

### 1.3 Correlation ID rules

- `correlation_id` is mandatory for every log event.
- The desktop process creates a root `session_id` at startup.
- For each user action or autonomous workflow trigger, create a new `correlation_id`.
- When desktop invokes engine operations (stdin bootstrap, HTTP, websocket control), propagate the same `correlation_id`.
- Child operations may add `span_id` but must not replace `correlation_id`.
- Correlation IDs must be opaque random IDs (UUIDv4 or equivalent 128-bit randomness).

### 1.4 Security constraints for logs

Logs must never include raw secrets. At minimum, redact/omit:

- API keys, access tokens, refresh tokens, session cookies.
- Full auth headers.
- Full account identifiers if they are considered sensitive.
- Local filesystem paths containing user identity data when avoidable.

If a sensitive value is necessary for debugging, emit a one-way fingerprint (e.g., hash prefix) under a clearly named field such as `credential_fingerprint`.

### 1.5 Example log records

```json
{"ts":"2026-01-09T18:07:23.412Z","level":"INFO","service":"desktop","component":"process_manager","event":"engine_ready_received","message":"Engine READY handshake received","correlation_id":"4e18bf6a-94c8-4ce7-a4e9-151f5f573263","session_id":"fefea8d9-0a09-422d-baf6-4f69970fa9ea","details":{"port":43125}}
{"ts":"2026-01-09T18:07:25.019Z","level":"WARN","service":"engine","component":"ws_client","event":"reconnect_scheduled","message":"WebSocket disconnected; scheduling reconnect","correlation_id":"4e18bf6a-94c8-4ce7-a4e9-151f5f573263","session_id":"fefea8d9-0a09-422d-baf6-4f69970fa9ea","attempt":3,"backoff_ms":5000}
{"ts":"2026-01-09T18:07:27.200Z","level":"ERROR","service":"engine","component":"rest_client","event":"request_failed","message":"Order placement failed due to rate limit","correlation_id":"4e18bf6a-94c8-4ce7-a4e9-151f5f573263","session_id":"fefea8d9-0a09-422d-baf6-4f69970fa9ea","error_code":"PT-HTTP-429","rate_limit_scope":"rest.orders"}
```

---

## 2) Error code catalog (user + operator messaging)

### 2.1 Error code format

- Format: `PT-<DOMAIN>-<ID>`
  - `PT` = PredictionTrader prefix
  - `DOMAIN` = category (`PROC`, `AUTH`, `NET`, `HTTP`, `DB`, `RISK`, `DATA`, `INT`)
  - `ID` = zero-padded numeric code segment
- Codes are stable once published.
- A single incident may emit multiple logs, but primary user-facing failures should map to one canonical error code.

### 2.2 Catalog (initial)

| Code | Category | User-visible message | Operator-visible message / action |
|---|---|---|---|
| `PT-PROC-001` | Process lifecycle | "Engine failed to start. Please restart the app." | Sidecar process did not reach READY handshake; inspect bootstrap logs and binary launch path. |
| `PT-PROC-002` | Process lifecycle | "Engine connection was interrupted." | Parent/child heartbeat failed; verify PID watchdog and shutdown sequence timing. |
| `PT-AUTH-001` | Authentication | "API credentials are missing or invalid." | Credential retrieval or exchange auth rejected; check keychain read and auth responses. |
| `PT-AUTH-002` | Authentication | "Session expired. Please reconnect your account." | Refresh/re-auth flow failed; inspect token expiry, refresh path, and clock skew. |
| `PT-NET-001` | Network | "Cannot reach exchange services right now." | Upstream network/connectivity error; verify DNS, TLS, and upstream status. |
| `PT-HTTP-429` | Rate limit | "Too many requests sent. Retrying automatically." | HTTP 429 received; inspect throttle policy and backoff behavior for scope. |
| `PT-DB-001` | Database | "Local database is temporarily unavailable." | SQLite open/lock/write failure; inspect WAL mode, permissions, and write queue saturation. |
| `PT-RISK-001` | Risk controls | "Order blocked by configured risk limits." | Risk guardrail rejection (position/notional/loss threshold). Review configured limits and latest state. |
| `PT-DATA-001` | Market data | "Market data feed interrupted. Reconnecting." | Websocket/data stream interruption; inspect reconnect loop and stale-feed detection. |
| `PT-INT-001` | Internal | "Unexpected internal error occurred." | Unhandled exception/path; capture diagnostics bundle and stack traces for triage. |

### 2.3 Message usage rules

- User-visible messages must be short, action-oriented, and non-sensitive.
- Operator-visible messages should include likely subsystem and next diagnostic action.
- UI surfaces should show: `user_message + error_code`.
- Logs should include full operator context with `error_code`, `component`, and structured `details`.

---

## 3) Local diagnostics bundle spec

### 3.1 Purpose

A diagnostics bundle is a local, user-triggered export for support and debugging that captures recent operational context without exposing secrets.

### 3.2 Bundle packaging

- Format: `.zip`
- Naming: `predictiontrader-diagnostics-<utc_timestamp>-<short_session_id>.zip`
- Output location: user-selected path (default to local Downloads).

### 3.3 Required contents

```
/manifest.json
/logs/desktop.log.jsonl
/logs/engine.log.jsonl
/config/runtime-config.json
/config/environment-metadata.json
/state/process-lifecycle.json
/state/reconnect-rate-limit-counters.json
/errors/recent-errors.json
```

#### File details

- `manifest.json`
  - bundle version
  - generated timestamp
  - app version/build
  - OS/platform info
  - included files + byte sizes + checksums
- `logs/*.jsonl`
  - last N MB (or time window) of structured logs for desktop + engine
- `config/runtime-config.json`
  - active non-secret config values (feature flags, mode, endpoints with sensitive query params stripped)
- `config/environment-metadata.json`
  - runtime versions (Rust app build, Python runtime, SQLite version), platform metadata
- `state/process-lifecycle.json`
  - sidecar launch status, last heartbeat timestamps, last graceful shutdown result
- `state/reconnect-rate-limit-counters.json`
  - reconnect attempts, latest backoff values, 429 counters by scope
- `errors/recent-errors.json`
  - recent unique error codes and frequencies

### 3.4 Redaction policy (mandatory)

Before writing bundle artifacts, remove or mask:

- Credentials/tokens of all forms.
- Authorization headers/cookies.
- Personally identifying account data beyond minimal support-necessary identifiers.
- Secrets embedded in environment variables or local config.

Redaction rules:

- Prefer omission to masking when possible.
- If masking is needed, preserve only minimal suffix/prefix (e.g., `****abcd`).
- Include `manifest.json.redaction_summary` with counts by redaction rule.

---

## 4) Reconnect and rate-limit test matrix (spec-only)

The following test matrix defines expected behavior only; implementation and automated tests are tracked separately.

| ID | Scenario | Preconditions | Expected behavior | Evidence |
|---|---|---|---|---|
| `RR-01` | Transient websocket disconnect | Active market data stream | Reconnect with exponential backoff + jitter; no crash; logs include attempt/backoff/correlation_id | Structured logs + reconnect counter state |
| `RR-02` | Repeated disconnects beyond threshold | Multiple disconnects within rolling window | Enter degraded mode indicator and raise operator warning event | UI status + `PT-DATA-001` log/event |
| `RR-03` | HTTP 429 on order endpoint | Burst order requests | Respect `Retry-After` when present; otherwise scoped backoff; avoid tight retry loop | Request logs showing throttled cadence |
| `RR-04` | HTTP 429 on market-data REST backfill | Recovery/backfill active | Apply independent scope limiter (`rest.market_data`) separate from order limiter | Per-scope counters + logs |
| `RR-05` | Network outage then recovery | Exchange unreachable for N minutes then restored | Surface `PT-NET-001`, continue retries, auto-recover without restart once network returns | Error transitions and recovery logs |
| `RR-06` | Sidecar restart during reconnect | Engine process restarted while retries pending | Parent re-establishes lifecycle session; stale retry state discarded safely | Process lifecycle + reconnect logs |
| `RR-07` | Mixed 429 + disconnect | Concurrent rate limit and websocket flaps | Maintain independent state machines; no starvation/deadlock in order pipeline | Timeline logs and queue health metrics |
| `RR-08` | Max retry budget reached | Configured retry cap exceeded for critical path | Emit terminal operator event with actionable error code; user sees safe degraded status | `PT-NET-001`/`PT-DATA-001` terminal record |

### 4.1 Acceptance notes for future implementation

- Every matrix scenario should map to at least one deterministic automated test and one manual runbook step.
- All resulting logs must satisfy the structured schema defined in this document.
- Final implementation should reference these IDs (`RR-01`..`RR-08`) in test names for traceability.
