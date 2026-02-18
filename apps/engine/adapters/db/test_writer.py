from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from adapters.db.migrations import apply_migrations
from adapters.db.writer import InboundEvent, SQLiteWriteWorker, StartupSchemaMismatch


def test_apply_migrations_creates_wal_and_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    with sqlite3.connect(db_path) as conn:
        apply_migrations(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "event_ledger" in tables
        assert "state_orders" in tables
        assert "state_positions" in tables
        assert "ingest_poison_messages" in tables

        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(journal_mode).lower() == "wal"


def test_single_worker_idempotent_upsert(tmp_path: Path) -> None:
    async def _scenario() -> None:
        worker = SQLiteWriteWorker(db_path=str(tmp_path / "ingest.db"))
        await worker.start()
        await worker.submit(InboundEvent(source_system="kalshi", source_event_id="evt-1", payload={"x": 1}))
        await worker.submit(InboundEvent(source_system="kalshi", source_event_id="evt-1", payload={"x": 2}))
        await worker.stop()

        with sqlite3.connect(tmp_path / "ingest.db") as conn:
            row = conn.execute(
                "SELECT payload_json, ingest_attempt_count FROM event_ledger WHERE source_system='kalshi' AND source_event_id='evt-1'"
            ).fetchone()
            assert row is not None
            assert row[0] == '{"x":2}'
            assert row[1] == 2

    asyncio.run(_scenario())


def test_retry_and_poison_on_lock_exhaustion(tmp_path: Path) -> None:
    async def _scenario() -> None:
        worker = SQLiteWriteWorker(db_path=str(tmp_path / "retry.db"), lock_retry_limit=2, backoff_base_seconds=0.0)
        await worker.start()

        calls = {"n": 0}
        original = SQLiteWriteWorker._upsert_event

        def _always_locked(conn: sqlite3.Connection, event: InboundEvent) -> None:
            calls["n"] += 1
            raise sqlite3.OperationalError("database is locked")

        SQLiteWriteWorker._upsert_event = staticmethod(_always_locked)
        try:
            await worker.submit(InboundEvent(source_system="kalshi", source_event_id="evt-locked", payload={"a": 1}))
            await worker.stop()
        finally:
            SQLiteWriteWorker._upsert_event = original

        assert calls["n"] == 3
        with sqlite3.connect(tmp_path / "retry.db") as conn:
            poison = conn.execute(
                "SELECT reason FROM ingest_poison_messages WHERE source_event_id='evt-locked'"
            ).fetchone()
            assert poison is not None
            assert "retries exhausted" in poison[0]

    asyncio.run(_scenario())


def test_poison_invalid_event_ids(tmp_path: Path) -> None:
    async def _scenario() -> None:
        worker = SQLiteWriteWorker(db_path=str(tmp_path / "poison.db"))
        await worker.start()
        await worker.submit(InboundEvent(source_system="", source_event_id="", payload={"bad": True}))
        await worker.stop()

        with sqlite3.connect(tmp_path / "poison.db") as conn:
            count = conn.execute("SELECT COUNT(*) FROM ingest_poison_messages").fetchone()[0]
            assert count == 1

    asyncio.run(_scenario())


def test_startup_checks_fail_fast_on_schema_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "broken.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("CREATE TABLE event_ledger (ledger_id INTEGER PRIMARY KEY)")

    worker = SQLiteWriteWorker(db_path=str(db_path))
    try:
        asyncio.run(worker.startup_checks())
    except StartupSchemaMismatch as exc:
        assert "schema mismatch" in str(exc) or "missing required table" in str(exc)
    else:
        raise AssertionError("expected startup schema mismatch")
