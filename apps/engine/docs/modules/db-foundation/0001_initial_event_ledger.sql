-- 0001_initial_event_ledger.sql
-- DB foundation migration for the engine's single-writer ledger.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS event_ledger (
    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_system TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    source_sequence INTEGER,
    source_emitted_at TEXT,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    ingest_first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ingest_last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ingest_attempt_count INTEGER NOT NULL DEFAULT 1,
    process_state TEXT NOT NULL DEFAULT 'pending',
    process_error TEXT,
    processed_at TEXT,
    CHECK (process_state IN ('pending', 'processed', 'dead_letter'))
);

-- Hard idempotency key: same source system + event ID must map to one ledger row.
CREATE UNIQUE INDEX IF NOT EXISTS ux_event_ledger_source_event
    ON event_ledger (source_system, source_event_id);

-- Optional secondary idempotency hint for producers that may accidentally rotate IDs.
CREATE UNIQUE INDEX IF NOT EXISTS ux_event_ledger_source_sequence
    ON event_ledger (source_system, source_sequence)
    WHERE source_sequence IS NOT NULL;

-- Read helpers for retry loops and boot-time rehydration scans.
CREATE INDEX IF NOT EXISTS ix_event_ledger_state_first_seen
    ON event_ledger (process_state, ingest_first_seen_at);

CREATE INDEX IF NOT EXISTS ix_event_ledger_source_emitted_at
    ON event_ledger (source_system, source_emitted_at);

-- Canonical ingest/upsert statement:
-- INSERT INTO event_ledger (...)
-- VALUES (...)
-- ON CONFLICT(source_system, source_event_id) DO UPDATE SET
--   ingest_last_seen_at = excluded.ingest_last_seen_at,
--   ingest_attempt_count = event_ledger.ingest_attempt_count + 1,
--   payload_json = excluded.payload_json,
--   payload_sha256 = excluded.payload_sha256,
--   process_state = CASE
--     WHEN event_ledger.process_state = 'dead_letter' THEN event_ledger.process_state
--     ELSE 'pending'
--   END,
--   process_error = CASE
--     WHEN event_ledger.process_state = 'dead_letter' THEN event_ledger.process_error
--     ELSE NULL
--   END;
