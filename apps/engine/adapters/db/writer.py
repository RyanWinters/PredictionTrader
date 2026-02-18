from __future__ import annotations

import asyncio
import hashlib
import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .migrations import MigrationError, apply_migrations, verify_runtime_pragmas, verify_schema


class StartupSchemaMismatch(MigrationError):
    """Raised when startup checks detect an incompatible DB schema."""


@dataclass(slots=True)
class InboundEvent:
    source_system: str
    source_event_id: str
    payload: dict[str, Any]
    source_sequence: int | None = None
    source_emitted_at: str | None = None


@dataclass(slots=True)
class LedgerWriteResult:
    status: str
    attempts: int
    message: str | None = None


class SQLiteWriteWorker:
    """Single queue writer that serializes all SQLite transactions."""

    _STOP = object()

    def __init__(
        self,
        *,
        db_path: str,
        queue_maxsize: int = 5_000,
        lock_retry_limit: int = 5,
        backoff_base_seconds: float = 0.1,
        backoff_cap_seconds: float = 5.0,
    ) -> None:
        self._db_path = Path(db_path)
        self._queue: asyncio.Queue[InboundEvent | object] = asyncio.Queue(maxsize=queue_maxsize)
        self._lock_retry_limit = lock_retry_limit
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_cap_seconds = backoff_cap_seconds
        self._worker_task: asyncio.Task[None] | None = None
        self._conn: sqlite3.Connection | None = None

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._conn = sqlite3.connect(self._db_path, timeout=0.0, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        apply_migrations(self._conn)
        try:
            verify_runtime_pragmas(self._conn)
            verify_schema(self._conn)
        except MigrationError as exc:
            raise StartupSchemaMismatch(str(exc)) from exc
        self._worker_task = asyncio.create_task(self._run(), name="sqlite-single-writer")

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        await self._queue.put(self._STOP)
        await self._worker_task
        self._worker_task = None
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    async def submit(self, event: InboundEvent) -> None:
        await self._queue.put(event)

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item is self._STOP:
                    return
                assert isinstance(item, InboundEvent)
                await self._write_with_retries(item)
            finally:
                self._queue.task_done()

    async def _write_with_retries(self, event: InboundEvent) -> LedgerWriteResult:
        if self._conn is None:
            raise RuntimeError("writer not started")
        if not event.source_system or not event.source_event_id:
            self._record_poison(event, "missing source_system/source_event_id")
            return LedgerWriteResult(status="poison", attempts=0, message="missing id")

        for attempt in range(1, self._lock_retry_limit + 2):
            try:
                self._upsert_event(self._conn, event)
                return LedgerWriteResult(status="ok", attempts=attempt)
            except sqlite3.OperationalError as exc:
                if not _is_transient_lock_error(exc):
                    raise
                if attempt > self._lock_retry_limit:
                    self._record_poison(event, f"db lock retries exhausted: {exc}")
                    return LedgerWriteResult(status="poison", attempts=attempt, message=str(exc))
                await asyncio.sleep(self._backoff_delay(attempt))

        raise AssertionError("unreachable")

    def _backoff_delay(self, attempt: int) -> float:
        cap = min(self._backoff_cap_seconds, self._backoff_base_seconds * (2 ** max(attempt - 1, 0)))
        return random.uniform(0.0, cap)

    def _record_poison(self, event: InboundEvent, reason: str) -> None:
        if self._conn is None:
            return
        payload_json = _to_json(event.payload)
        self._conn.execute(
            """
            INSERT INTO ingest_poison_messages(source_system, source_event_id, reason, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (event.source_system or None, event.source_event_id or None, reason, payload_json),
        )

    @staticmethod
    def _upsert_event(conn: sqlite3.Connection, event: InboundEvent) -> None:
        payload_json = _to_json(event.payload)
        payload_sha = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        now = _utc_now_iso()

        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                INSERT INTO event_ledger(
                    source_system,
                    source_event_id,
                    source_sequence,
                    source_emitted_at,
                    payload_json,
                    payload_sha256,
                    ingest_first_seen_at,
                    ingest_last_seen_at,
                    ingest_attempt_count,
                    process_state,
                    process_error,
                    processed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'pending', NULL, NULL)
                ON CONFLICT(source_system, source_event_id) DO UPDATE SET
                    source_sequence = COALESCE(excluded.source_sequence, event_ledger.source_sequence),
                    source_emitted_at = COALESCE(excluded.source_emitted_at, event_ledger.source_emitted_at),
                    payload_json = excluded.payload_json,
                    payload_sha256 = excluded.payload_sha256,
                    ingest_last_seen_at = excluded.ingest_last_seen_at,
                    ingest_attempt_count = event_ledger.ingest_attempt_count + 1,
                    process_state = CASE
                        WHEN event_ledger.process_state = 'dead_letter' THEN event_ledger.process_state
                        ELSE 'pending'
                    END,
                    process_error = CASE
                        WHEN event_ledger.process_state = 'dead_letter' THEN event_ledger.process_error
                        ELSE NULL
                    END,
                    processed_at = CASE
                        WHEN event_ledger.process_state = 'dead_letter' THEN event_ledger.processed_at
                        ELSE NULL
                    END
                """,
                (
                    event.source_system,
                    event.source_event_id,
                    event.source_sequence,
                    event.source_emitted_at,
                    payload_json,
                    payload_sha,
                    now,
                    now,
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    async def startup_checks(self) -> None:
        if self._conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA foreign_keys = ON;")
            try:
                verify_runtime_pragmas(conn)
                verify_schema(conn)
            except MigrationError as exc:
                raise StartupSchemaMismatch(str(exc)) from exc
            finally:
                conn.close()
            return

        try:
            verify_runtime_pragmas(self._conn)
            verify_schema(self._conn)
        except MigrationError as exc:
            raise StartupSchemaMismatch(str(exc)) from exc


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _is_transient_lock_error(exc: sqlite3.OperationalError) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg
