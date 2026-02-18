from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


class MigrationError(RuntimeError):
    """Raised when DB migration or runtime pragma verification fails."""



def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply SQL migrations in lexical order and stamp schema_migrations."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if migration.name in applied:
            continue
        conn.executescript(migration.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (migration.name,))
    conn.commit()



def verify_runtime_pragmas(conn: sqlite3.Connection) -> None:
    journal_mode = str(conn.execute("PRAGMA journal_mode;").fetchone()[0]).lower()
    if journal_mode != "wal":
        raise MigrationError(f"journal_mode mismatch: expected wal, got {journal_mode}")

    foreign_keys = int(conn.execute("PRAGMA foreign_keys;").fetchone()[0])
    if foreign_keys != 1:
        raise MigrationError("foreign_keys must be ON")



def list_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}


REQUIRED_TABLE_COLUMNS: dict[str, set[str]] = {
    "event_ledger": {
        "ledger_id",
        "source_system",
        "source_event_id",
        "source_sequence",
        "source_emitted_at",
        "payload_json",
        "payload_sha256",
        "ingest_first_seen_at",
        "ingest_last_seen_at",
        "ingest_attempt_count",
        "process_state",
        "process_error",
        "processed_at",
    },
    "state_orders": {"order_id", "payload_json", "payload_sha256", "state", "updated_at"},
    "state_positions": {"position_key", "payload_json", "payload_sha256", "updated_at"},
    "ingest_poison_messages": {
        "poison_id",
        "source_system",
        "source_event_id",
        "reason",
        "payload_json",
        "created_at",
    },
}



def verify_schema(conn: sqlite3.Connection) -> None:
    """Fail fast when required tables or columns are missing."""
    for table_name, expected_columns in REQUIRED_TABLE_COLUMNS.items():
        columns = list_table_columns(conn, table_name)
        if not columns:
            raise MigrationError(f"missing required table: {table_name}")
        missing = expected_columns - columns
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise MigrationError(f"schema mismatch for {table_name}; missing columns: {missing_list}")
