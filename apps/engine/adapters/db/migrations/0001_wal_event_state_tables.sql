-- 0001_wal_event_state_tables.sql
-- Runtime pragmas + event/state foundation tables.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

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
    CHECK (process_state IN ('pending', 'processed', 'dead_letter')),
    UNIQUE(source_system, source_event_id)
);

CREATE INDEX IF NOT EXISTS ix_event_ledger_state_first_seen
    ON event_ledger (process_state, ingest_first_seen_at);

CREATE TABLE IF NOT EXISTS state_orders (
    order_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    state TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS state_positions (
    position_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_poison_messages (
    poison_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_system TEXT,
    source_event_id TEXT,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
