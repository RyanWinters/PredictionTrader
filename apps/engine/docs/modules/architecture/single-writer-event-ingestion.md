# Single-Writer Event Ingestion Architecture

## Goals
- Guarantee **idempotent ingestion** of upstream events, even across reconnects and duplicate deliveries.
- Keep SQLite writes safe and performant via a **single writer task** and WAL mode.
- Preserve enough ledger metadata to recover from crashes, retries, and out-of-order upstream delivery.

## Core Data Flow
1. Transport adapters (WebSocket, REST poller, replay feed) normalize incoming messages into `InboundEvent`.
2. Adapters push `InboundEvent` into a bounded `asyncio.Queue`.
3. A dedicated writer coroutine drains the queue and executes DB upserts in order of dequeue.
4. Downstream workers consume `pending` ledger rows and mark them `processed` or `dead_letter`.

This separation means reconnect storms can increase queue depth, but cannot create concurrent SQLite writers.

## `asyncio.Queue` Ingestion Plan

### Queue shape
- `maxsize`: finite (for example 5k) to apply backpressure when producers outrun processing.
- Payload fields:
  - `source_system`
  - `source_event_id`
  - `source_sequence` (nullable monotonic number from source, if available)
  - `source_emitted_at` (nullable source timestamp)
  - `received_at`
  - `payload_json`
  - `payload_sha256`

### Producer behavior
- On reconnect, producers should request/replay from last acknowledged cursor when source supports it.
- Producers enqueue every received event without pre-deduping; dedupe authority remains DB unique constraints.
- If queue is full, producers should:
  1. pause socket reads or polling pulls,
  2. emit a saturation metric,
  3. retry enqueue with short jittered delay.

### Single writer behavior
- Use one long-lived DB connection configured with WAL mode.
- Wrap each ingest in short transaction and execute the canonical upsert against `(source_system, source_event_id)`.
- Track processing lag via `now - ingest_first_seen_at` for pending rows.

## Idempotency + Out-of-Order Strategy

### Duplicate/reconnect handling
- Reconnects may replay already-seen source IDs.
- Unique key `(source_system, source_event_id)` forces one canonical row per source event.
- Upsert increments `ingest_attempt_count` and refreshes `ingest_last_seen_at` for observability.

### Out-of-order handling
- `source_sequence` and `source_emitted_at` are stored but not used as primary uniqueness.
- Consumers must not assume dequeue order equals business-time order.
- Business logic requiring ordering should query by:
  1. `source_sequence` when available,
  2. fallback to `source_emitted_at`, then
  3. fallback to `ledger_id` as arrival order.

### Poisoned payload containment
- Rows repeatedly failing validation or apply steps move to `process_state='dead_letter'` with `process_error`.
- Upsert logic should preserve `dead_letter` state unless operator/manual replay explicitly resets it.

## Retry and Backoff Policy

### Ingest retry (queue -> DB)
- Retry only for transient DB errors (`database is locked`, I/O hiccups).
- Recommended schedule: exponential backoff with full jitter.
  - attempt 1: immediate
  - attempts 2-5: base 100ms, multiplier 2, cap 5s
  - attempts >5: fixed 5s + jitter, alert after threshold window
- If transient failures exceed budget, keep process running but raise critical health signal.

### Apply retry (pending -> processed)
- Use `ingest_attempt_count` for ingest observations and a separate in-memory/apply counter for domain handling.
- After `N` apply failures (for example 10), mark `dead_letter`.
- Record terminal error details in `process_error` for triage.

## Poison Message Workflow
1. Event lands in ledger as `pending`.
2. Consumer fails domain validation or side-effect apply.
3. Retry according to policy; each failure emits structured error with event identifiers.
4. On terminal failure, update row:
   - `process_state='dead_letter'`
   - `process_error='<last error + code>'`
5. Operator workflow:
   - inspect dead-letter rows,
   - patch parser/business logic if needed,
   - manually reset selected rows to `pending` for replay.

## Boot-Time Rehydration Checklist
1. Open DB connection and reassert runtime pragmas (WAL, `foreign_keys=ON`, `synchronous=NORMAL`).
2. Verify migration level includes initial ledger schema.
3. Load high-water checkpoint per source (if external cursor table exists).
4. Scan ledger for unfinished work:
   - `pending` rows (must be resumed),
   - stale in-flight markers if introduced later.
5. Start writer coroutine before starting transport adapters.
6. Start adapters with reconnect cursor from checkpoint/high-water logic.
7. Emit startup metrics:
   - pending row count,
   - dead-letter row count,
   - oldest pending age.

## Operational Notes
- WAL mode enables concurrent readers during writes, which is essential for diagnostics and replay scans.
- Single-writer architecture keeps lock contention predictable and simplifies correctness under reconnect bursts.
- Ledger-first durability means events are persisted before domain apply, enabling deterministic crash recovery.
