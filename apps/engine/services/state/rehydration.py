"""Boot-time state rehydration + reconciliation against Kalshi snapshots."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

from connectors.kalshi.interfaces import AccountReadClient


class RehydrationError(RuntimeError):
    """Raised when boot-time state reconciliation fails."""


class StateReadinessGate:
    """Readiness primitive used by strategy runners and health endpoints."""

    def __init__(self) -> None:
        self._ready_event = threading.Event()
        self._last_error: str | None = None
        self._last_rehydrated_at: str | None = None

    def mark_ready(self, *, rehydrated_at: str) -> None:
        self._last_error = None
        self._last_rehydrated_at = rehydrated_at
        self._ready_event.set()

    def mark_not_ready(self, *, error: str) -> None:
        self._last_error = error
        self._ready_event.clear()

    def wait_until_ready(self, timeout_seconds: float | None = None) -> bool:
        return self._ready_event.wait(timeout=timeout_seconds)

    def assert_ready(self) -> None:
        if not self._ready_event.is_set():
            message = self._last_error or "state is not ready"
            raise RehydrationError(f"strategy execution blocked: {message}")

    def snapshot(self) -> dict[str, Any]:
        return {
            "ready": self._ready_event.is_set(),
            "last_error": self._last_error,
            "last_rehydrated_at": self._last_rehydrated_at,
        }


@dataclass(frozen=True)
class DriftRecord:
    category: str
    entity_key: str
    action: str
    source_event_id: str
    payload: dict[str, Any]


class StateRehydrator:
    """Rehydrates order/position state from Kalshi before strategy execution."""

    def __init__(self, *, db_path: str, kalshi_client: AccountReadClient, readiness_gate: StateReadinessGate) -> None:
        self._db_path = db_path
        self._kalshi_client = kalshi_client
        self._readiness_gate = readiness_gate

    def boot_rehydrate(self) -> None:
        started_at = _now_iso()
        boot_id = started_at
        self._readiness_gate.mark_not_ready(error="rehydration in progress")
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                self._ensure_schema(conn)

                open_orders = self._normalize_orders(self._kalshi_client.get_open_orders())
                positions = self._normalize_positions(self._kalshi_client.get_positions())

                drift = [
                    *self._reconcile_orders(conn, open_orders, boot_id),
                    *self._reconcile_positions(conn, positions, boot_id),
                ]
                self._persist_drift_events(conn, drift)
                self._record_run(conn, boot_id=boot_id, started_at=started_at, status="completed", drift_count=len(drift))

            self._readiness_gate.mark_ready(rehydrated_at=_now_iso())
        except Exception as exc:  # noqa: BLE001 - boot failure must block strategy execution
            with sqlite3.connect(self._db_path) as conn:
                self._ensure_schema(conn)
                self._record_run(
                    conn,
                    boot_id=boot_id,
                    started_at=started_at,
                    status="failed",
                    drift_count=0,
                    error=str(exc),
                )
            self._readiness_gate.mark_not_ready(error=str(exc))
            raise RehydrationError(str(exc)) from exc

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS state_orders (
                order_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                state TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS state_positions (
                position_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS reconciliation_event_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_system TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                category TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                action TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                ingest_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(source_system, source_event_id)
            );

            CREATE TABLE IF NOT EXISTS rehydration_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                boot_id TEXT NOT NULL UNIQUE,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                status TEXT NOT NULL,
                drift_count INTEGER NOT NULL,
                error TEXT
            );
            """
        )

    def _normalize_orders(self, response: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        raw_orders = response.get("orders") if isinstance(response.get("orders"), list) else []
        normalized: dict[str, dict[str, Any]] = {}
        for item in raw_orders:
            if not isinstance(item, Mapping):
                continue
            order_id = str(item.get("order_id") or item.get("id") or "").strip()
            if not order_id:
                continue
            normalized[order_id] = dict(item)
        return normalized

    def _normalize_positions(self, response: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        raw_positions = response.get("positions") if isinstance(response.get("positions"), list) else []
        normalized: dict[str, dict[str, Any]] = {}
        for item in raw_positions:
            if not isinstance(item, Mapping):
                continue
            market_id = str(item.get("market_id") or item.get("ticker") or "").strip()
            side = str(item.get("side") or "").strip().lower()
            if not market_id:
                continue
            key = f"{market_id}:{side}" if side else market_id
            normalized[key] = dict(item)
        return normalized

    def _reconcile_orders(
        self,
        conn: sqlite3.Connection,
        remote_orders: dict[str, dict[str, Any]],
        boot_id: str,
    ) -> list[DriftRecord]:
        existing = {
            str(row["order_id"]): {
                "state": str(row["state"]),
                "payload_sha256": str(row["payload_sha256"]),
            }
            for row in conn.execute("SELECT order_id, state, payload_sha256 FROM state_orders")
        }

        drift: list[DriftRecord] = []
        all_ids = sorted(set(existing) | set(remote_orders))

        for order_id in all_ids:
            remote_payload = remote_orders.get(order_id)
            existing_row = existing.get(order_id)
            event_base = f"boot:{boot_id}:orders:{order_id}"

            if remote_payload and not existing_row:
                payload_json, payload_hash = _serialize_payload(remote_payload)
                conn.execute(
                    """
                    INSERT INTO state_orders(order_id, payload_json, payload_sha256, state, updated_at)
                    VALUES (?, ?, ?, 'open', ?)
                    ON CONFLICT(order_id) DO UPDATE SET
                        payload_json=excluded.payload_json,
                        payload_sha256=excluded.payload_sha256,
                        state='open',
                        updated_at=excluded.updated_at
                    """,
                    (order_id, payload_json, payload_hash, _now_iso()),
                )
                drift.append(
                    DriftRecord(
                        category="orders",
                        entity_key=order_id,
                        action="insert_from_exchange",
                        source_event_id=f"{event_base}:insert",
                        payload=remote_payload,
                    )
                )
                continue

            if not remote_payload and existing_row and existing_row["state"] != "closed":
                conn.execute(
                    "UPDATE state_orders SET state='closed', updated_at=? WHERE order_id=?",
                    (_now_iso(), order_id),
                )
                drift.append(
                    DriftRecord(
                        category="orders",
                        entity_key=order_id,
                        action="mark_closed_missing_exchange",
                        source_event_id=f"{event_base}:close",
                        payload={"order_id": order_id, "state": "closed"},
                    )
                )
                continue

            if remote_payload and existing_row:
                payload_json, payload_hash = _serialize_payload(remote_payload)
                if payload_hash != existing_row["payload_sha256"] or existing_row["state"] != "open":
                    conn.execute(
                        "UPDATE state_orders SET payload_json=?, payload_sha256=?, state='open', updated_at=? WHERE order_id=?",
                        (payload_json, payload_hash, _now_iso(), order_id),
                    )
                    drift.append(
                        DriftRecord(
                            category="orders",
                            entity_key=order_id,
                            action="update_from_exchange",
                            source_event_id=f"{event_base}:update",
                            payload=remote_payload,
                        )
                    )

        return drift

    def _reconcile_positions(
        self,
        conn: sqlite3.Connection,
        remote_positions: dict[str, dict[str, Any]],
        boot_id: str,
    ) -> list[DriftRecord]:
        existing = {
            str(row["position_key"]): str(row["payload_sha256"])
            for row in conn.execute("SELECT position_key, payload_sha256 FROM state_positions")
        }
        drift: list[DriftRecord] = []
        all_keys = sorted(set(existing) | set(remote_positions))

        for key in all_keys:
            remote_payload = remote_positions.get(key)
            event_base = f"boot:{boot_id}:positions:{key}"

            if remote_payload is None:
                conn.execute("DELETE FROM state_positions WHERE position_key=?", (key,))
                drift.append(
                    DriftRecord(
                        category="positions",
                        entity_key=key,
                        action="delete_missing_exchange",
                        source_event_id=f"{event_base}:delete",
                        payload={"position_key": key, "deleted": True},
                    )
                )
                continue

            payload_json, payload_hash = _serialize_payload(remote_payload)
            conn.execute(
                """
                INSERT INTO state_positions(position_key, payload_json, payload_sha256, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(position_key) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    payload_sha256=excluded.payload_sha256,
                    updated_at=excluded.updated_at
                """,
                (key, payload_json, payload_hash, _now_iso()),
            )
            if existing.get(key) != payload_hash:
                drift.append(
                    DriftRecord(
                        category="positions",
                        entity_key=key,
                        action="upsert_from_exchange",
                        source_event_id=f"{event_base}:upsert",
                        payload=remote_payload,
                    )
                )

        return drift

    def _persist_drift_events(self, conn: sqlite3.Connection, drift: list[DriftRecord]) -> None:
        for item in drift:
            payload_json, payload_hash = _serialize_payload(item.payload)
            conn.execute(
                """
                INSERT INTO reconciliation_event_ledger(
                    source_system, source_event_id, category, entity_key, action, payload_json, payload_sha256, ingest_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_system, source_event_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    payload_sha256=excluded.payload_sha256,
                    ingest_at=excluded.ingest_at
                """,
                (
                    "kalshi_rehydration",
                    item.source_event_id,
                    item.category,
                    item.entity_key,
                    item.action,
                    payload_json,
                    payload_hash,
                    _now_iso(),
                ),
            )

    def _record_run(
        self,
        conn: sqlite3.Connection,
        *,
        boot_id: str,
        started_at: str,
        status: str,
        drift_count: int,
        error: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO rehydration_runs(boot_id, started_at, completed_at, status, drift_count, error)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(boot_id) DO UPDATE SET
                completed_at=excluded.completed_at,
                status=excluded.status,
                drift_count=excluded.drift_count,
                error=excluded.error
            """,
            (boot_id, started_at, _now_iso(), status, drift_count, error),
        )


def _serialize_payload(payload: Mapping[str, Any]) -> tuple[str, str]:
    payload_json = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    return payload_json, payload_hash


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
