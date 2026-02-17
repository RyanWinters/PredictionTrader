# Security & Live-Readiness Checklist

Use this checklist as a **release gate** before any build is promoted beyond internal testing.

**How to use**
- Mark each item `Yes` or `No`.
- Any `No` in a **Blocker** section fails the gate.
- Capture evidence links (PRs, screenshots, runbooks, ticket IDs) for auditability.

---

## 1) Keychain & Secret Storage Boundaries (Blocker)

| Item | Yes/No | Evidence / Notes |
|---|---|---|
| Secrets are read only through approved keychain/secret-manager APIs (no plain env-file fallbacks in production). |  |  |
| Write operations to keychain are restricted to provisioning/rotation workflows (not runtime business logic). |  |  |
| Access controls enforce least privilege (service identity can read only required keys). |  |  |
| Separate namespaces/paths exist for demo and live credentials; cross-environment reads are blocked. |  |  |
| Keychain writes are immutable/audited (actor, timestamp, key identifier, operation). |  |  |
| Emergency “break glass” access path exists, is time-bounded, and is fully audited. |  |  |

### Boundary rules
- **Allowed reads**: runtime process may read only secrets required for its function (scoped API keys, signing keys, DB creds).
- **Allowed writes**: provisioning tooling and rotation jobs only.
- **Disallowed**: application endpoints, user-initiated actions, or debug tooling writing credentials into keychain.
- **Isolation**: demo and live credentials must never share the same key path, cache bucket, or token scope.

---

## 2) In-Memory Retention, Expiry, and Zeroization (Blocker)

| Item | Yes/No | Evidence / Notes |
|---|---|---|
| Secrets are not persisted in process-wide global state beyond active use. |  |  |
| Secret-bearing objects define explicit TTL/expiry and are invalidated at or before TTL. |  |  |
| Buffers/objects containing secrets are zeroized or overwritten on disposal/rotation. |  |  |
| Retry queues, caches, and message payloads exclude raw secrets. |  |  |
| Crash handlers and memory dumps are configured to avoid including raw secret payloads where possible. |  |  |
| Unit/integration tests validate expiry and cleanup behavior for secret-handling code paths. |  |  |

### Retention policy
- Keep secrets in memory only for the minimum operation window.
- Prefer short-lived session tokens over long-lived static credentials.
- On token refresh/rotation, invalidate previous secret material immediately.
- Zeroization expectation: clear mutable buffers and clear references to allow prompt GC/collection.

---

## 3) Forbidden Logging Fields (Blocker)

| Item | Yes/No | Evidence / Notes |
|---|---|---|
| Logging middleware/redaction filters block forbidden fields in app logs. |  |  |
| Structured logs are reviewed for sensitive key names and nested payload leakage. |  |  |
| Error telemetry, traces, and analytics events follow the same redaction policy. |  |  |
| A CI check or log contract test enforces forbidden-field protections. |  |  |

### Never log the following
- API keys, private keys, seed phrases, wallet mnemonics, passwords, OTPs, refresh tokens, bearer tokens.
- Full authorization headers, cookie values, session IDs, CSRF secrets.
- Raw keychain values, secret-manager payloads, decrypted credential material.
- Payment instrument PAN/CVV, bank account numbers, tax IDs, government IDs.
- Full PII where not required (email, phone, address, legal name) unless explicitly approved and minimized.

### Logging-safe alternatives
- Log only key IDs/fingerprints (`key_id`, last 4 chars, hash fingerprint).
- Replace values with fixed placeholders (`[REDACTED]`).
- Truncate and hash where correlation is needed.

---

## 4) Demo vs Live Controls (Blocker)

| Item | Yes/No | Evidence / Notes |
|---|---|---|
| New installs/sessions default to **Demo Mode**. |  |  |
| Enabling live mode requires explicit user confirmation with risk disclosure. |  |  |
| Live confirmation uses a deliberate friction step (typed phrase, checkbox + confirm, or equivalent). |  |  |
| A persistent, high-visibility live-mode indicator is present across all relevant screens. |  |  |
| Live-mode state persists correctly across app restarts and re-auth flows. |  |  |
| Reverting from live to demo is always available and clearly labeled. |  |  |
| Live mode cannot activate when required pre-live checks fail. |  |  |

### Required UX behavior
- **Default**: Demo mode on first run and after account reset.
- **Explicit confirmation flow**: risk notice + user acknowledgment + final confirmation action.
- **Persistent indicator**: non-dismissable badge/banner (e.g., `LIVE`) shown in header/status area while live mode is active.

---

## 5) Operator Pre-Live Validation Checklist (Blocker)

> Complete immediately before enabling live trading/operations.

| Item | Yes/No | Evidence / Notes |
|---|---|---|
| Deployment artifact checksum/signature matches approved build. |  |  |
| Live credentials are present, valid, and least-privileged. |  |  |
| Demo credentials are still isolated and untouched by live deployment. |  |  |
| Risk limits (size, exposure, loss caps, rate limits) are configured and verified. |  |  |
| Circuit breakers / kill switch are tested and reachable by on-call operator. |  |  |
| Alerting is healthy for auth failures, order failures, and abnormal loss patterns. |  |  |
| Time sync and market data feed health checks pass. |  |  |
| Rollback plan is documented, tested, and owner-confirmed. |  |  |
| Incident contacts and escalation path are current. |  |  |
| Live-mode UI indicator and explicit confirmation flow validated in production-like environment. |  |  |

---

## 6) Gate Decision

- **Release decision**: Pass / Fail
- **Approver**:
- **Date/Time (UTC)**:
- **Exceptions granted** (must include owner + expiry):

A release is approved only when all Blocker items are `Yes`, or an exception is formally approved with a time-bounded remediation plan.
