# ADR-001: Process Boundaries and Trust Model

- **Status:** Accepted
- **Date:** 2026-02-17
- **Deciders:** Milestone 1 architecture owners
- **Technical Story:** Define host/sidecar trust boundaries before implementation

## Context

PredictionTrader uses a desktop runtime with a **Tauri host process** and a **Python sidecar process**. Before Milestone 1 coding, we must establish explicit trust boundaries so we do not accidentally leak secrets, over-privilege sidecar capabilities, or create unauthenticated control channels.

Without a written decision, process interaction patterns tend to grow ad hoc and become hard to secure retroactively.

## Decision

### 1) Process trust responsibilities

#### Tauri host (primary trusted boundary)
The Tauri host is trusted to:
- Own user-facing security posture and local OS capability access.
- Gate all privileged operations exposed to the UI or sidecar.
- Validate sidecar identity during startup handshake.
- Enforce policy for IPC allowlists and command routing.
- Decide when sidecar restarts are permitted after failures.

The Tauri host is **not** trusted to persist plaintext long-lived secrets to disk unless explicitly approved by a separate ADR.

#### Python sidecar (constrained trusted component)
The Python sidecar is trusted to:
- Execute domain/business logic delegated by host policy.
- Hold only the minimum in-memory credentials needed for active tasks.
- Return structured results and machine-readable errors.

The Python sidecar is **not** trusted to:
- Access secrets directly from OS keychain or secure stores.
- Open arbitrary inbound network listeners.
- Accept unauthenticated commands from any local process.
- Persist host-transferred secrets in plaintext files.

### 2) Secret ownership and transfer rules

- **Root ownership:** Secrets are logically owned by the host trust boundary.
- **Acquisition:** The host obtains secrets via approved UX and storage policy (future ADR for storage details).
- **Transfer to sidecar:**
  - Allowed only when required for a specific active workflow.
  - Must occur after successful startup authentication.
  - Must be scoped (least privilege, minimal fields, shortest feasible lifetime).
- **Lifetime:**
  - Sidecar keeps secrets in memory only.
  - Sidecar clears in-memory secret material on task completion, shutdown, or auth/session invalidation.
- **Prohibited flows:**
  - Sidecar writing secrets to logs, crash dumps, local files, or telemetry.
  - UI directly sending secrets to sidecar without host mediation.

### 3) Allowed communication channels

Only the following inter-process channels are allowed:

1. **Host ↔ Sidecar authenticated IPC channel** (primary command and event channel).
2. **Host-mediated UI command path** where UI calls host commands; host may then call sidecar.

Disallowed channels:
- UI ↔ sidecar direct socket/pipe communication.
- Any sidecar-exposed unauthenticated local TCP/UDP/WebSocket endpoint.
- File-drop polling directories as a control plane.

If a new channel is needed, it requires a new ADR before implementation.

### 4) Startup authentication expectations

Each sidecar launch must complete a host-driven challenge before privileged traffic is accepted:

1. Host generates a cryptographically strong one-time nonce/token challenge.
2. Host delivers challenge over launch-scoped bootstrap path.
3. Sidecar proves possession/echo/signature per agreed protocol in first message.
4. Host validates challenge response and binds an authenticated session ID.
5. Only after success does host enable privileged commands or secret transfer.

Rules:
- Challenge tokens are single-use and expire quickly.
- Failed or expired challenges cannot be retried on the same session.
- Restart requires a new challenge.

### 5) Failure behavior when trust checks fail

If any trust check fails (handshake failure, token mismatch, replay suspicion, channel policy violation):

- Host immediately rejects privileged requests.
- Host terminates sidecar session and revokes session context.
- Host redacts sensitive diagnostics and records security event metadata.
- Host presents a safe, generic error state to the UI.
- Automatic retries are limited and backoff-controlled; repeated failures require explicit user action or app restart per policy.

Fail-closed principle applies: no degraded mode that bypasses authentication or policy gates.

## Consequences

### Positive
- Locks a clear security boundary before Milestone 1 implementation.
- Reduces accidental secret sprawl and ambiguous ownership.
- Provides a stable contract for IPC and handshake implementation.
- Enables targeted testing for fail-closed behavior.

### Negative / trade-offs
- Adds startup complexity due to mandatory authentication handshake.
- Introduces implementation overhead for scoped secret lifecycle handling.
- May slow early prototyping when adding new IPC paths (ADR required).

### Follow-up required
- Define concrete handshake protocol details (message schema, timeout values, cryptographic primitives).
- Define secure storage ADR for host-owned secrets.
- Add security test cases for replay, mismatch, and unauthorized-channel attempts before Milestone 1 exit.
