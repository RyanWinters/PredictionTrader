# Secrets Lifecycle Policy

## 1) Purpose

This policy defines how secrets are created, stored, accessed, rotated, used in memory, and destroyed across demo and live environments.

## 2) Scope

Applies to:
- Application services, background workers, CI/CD pipelines, and operator tooling.
- All credentials and sensitive security material: API keys, private/signing keys, tokens, DB credentials, webhook secrets, and encryption keys.

## 3) Secret Classes

- **Static secrets**: manually provisioned credentials with explicit rotation windows.
- **Dynamic secrets**: short-lived credentials issued by a broker/secret manager.
- **Session secrets**: in-memory tokens derived from an auth flow.

Policy preference: dynamic > static, shortest feasible TTL, least privilege by default.

## 4) Lifecycle Requirements

### 4.1 Creation & Provisioning
- Generate secrets with approved cryptographic RNGs.
- Assign owner, purpose, environment (`demo` or `live`), rotation cadence, and expiry metadata.
- Never reuse the same secret value across environments.

### 4.2 Storage (Keychain/Secret Manager)
- Store secrets only in approved keychain/secret-manager backends.
- Disallow plaintext storage in source control, local config files, screenshots, tickets, or chat transcripts.
- Enforce separate key namespaces for demo and live.

### 4.3 Read/Write Boundary Policy
- **Read allowed**: runtime identities may read only secrets required for current operation.
- **Write allowed**: provisioning and rotation workflows only.
- **Write denied**: request handlers, UI-triggered runtime paths, and debug endpoints.
- **Audit required**: every read/write action must be attributable to an identity and timestamp.

### 4.4 Distribution & Use
- Deliver secrets over authenticated, encrypted channels only.
- Avoid fan-out distribution; fetch on demand where possible.
- Cache only when operationally necessary and for bounded TTL.

### 4.5 Rotation & Revocation
- Define rotation SLOs per secret class.
- Support immediate revocation for compromise events.
- Rotate on role change, personnel departure, suspected exposure, and incident closure.
- Ensure dependent services can reload secrets without downtime where feasible.

### 4.6 Retirement & Destruction
- Disable and remove unused secrets promptly.
- Revoke secrets before decommissioning dependent infrastructure.
- Maintain tamper-evident audit logs of destruction events.

## 5) In-Memory Handling Standard

### 5.1 Retention Limits
- Hold plaintext secrets in memory only for active operation windows.
- Avoid storing secrets in long-lived globals/singletons.
- Use short cache TTLs; default to no caching unless justified.

### 5.2 Expiry Expectations
- All in-memory secret containers must have explicit expiry semantics.
- Expired secrets must be invalidated before next use attempt.
- Token refresh must invalidate prior tokens immediately.

### 5.3 Zeroization Expectations
- Zeroize mutable buffers on completion, rotation, and error paths.
- Remove references after use to accelerate garbage collection.
- Do not serialize secret-bearing objects into crash dumps or diagnostics.

## 6) Logging and Telemetry Policy

### 6.1 Forbidden Log Fields
Never emit to logs, traces, analytics, metrics tags, or error payloads:
- `password`, `passphrase`, `secret`, `api_key`, `private_key`, `mnemonic`, `seed`
- `authorization`, `cookie`, `session_id`, `refresh_token`, `access_token`
- Raw keychain payloads, decrypted credentials, signing material
- Full payment or government ID values

### 6.2 Required Controls
- Centralized redaction middleware for structured and unstructured logs.
- Contract tests/CI checks that fail builds on forbidden field leakage.
- Use identifiers/fingerprints instead of values for correlation.

## 7) Demo vs Live Safety Policy

### 7.1 Default Mode
- Product defaults to **Demo Mode** for first-time use and after reset.

### 7.2 Live Enablement Flow
- Live mode requires explicit user acknowledgment of risk.
- Confirmation must include deliberate friction (typed confirmation phrase or equivalent).
- Live activation is blocked unless pre-live checks pass.

### 7.3 Persistent Live Indicator
- Display a non-dismissable, persistent live-state indicator on all trading/operation-critical views.
- Indicator must survive navigation, refresh, and re-auth flows.

## 8) Operator Pre-Live Validation

Before enabling live mode/operators switching to live credentials, verify:
- Correct build/version and artifact integrity.
- Credential scope and environment separation.
- Risk guardrails, limits, and kill-switch readiness.
- Alerting, monitoring, and incident response coverage.
- Successful dry-run of live confirmation UX and persistent live indicator.

## 9) Exceptions

Any policy exception requires:
- Named owner and business justification.
- Risk assessment and compensating controls.
- Explicit expiry date and remediation plan.

## 10) Compliance & Review

- Review this policy at least quarterly and after any security incident.
- Track conformance via release gates and audit checks.
- Non-compliance can block production/live releases.
