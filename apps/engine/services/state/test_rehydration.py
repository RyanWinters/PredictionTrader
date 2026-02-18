from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from services.state.rehydration import RehydrationError, StateReadinessGate, StateRehydrator


class FakeKalshiClient:
    def __init__(self, *, open_orders: dict[str, Any], positions: dict[str, Any], fail: bool = False):
        self._open_orders = open_orders
        self._positions = positions
        self._fail = fail

    def get_open_orders(self) -> dict[str, Any]:
        if self._fail:
            raise RuntimeError("kalshi unavailable")
        return self._open_orders

    def get_positions(self) -> dict[str, Any]:
        if self._fail:
            raise RuntimeError("kalshi unavailable")
        return self._positions


def _seed_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
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
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO state_orders(order_id, payload_json, payload_sha256, state, updated_at) VALUES(?, ?, ?, ?, ?)",
            ("stale-local", "{}", "oldhash", "open", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO state_orders(order_id, payload_json, payload_sha256, state, updated_at) VALUES(?, ?, ?, ?, ?)",
            ("o-1", "{}", "different-hash", "closed", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO state_positions(position_key, payload_json, payload_sha256, updated_at) VALUES(?, ?, ?, ?)",
            ("MKT1:yes", "{}", "oldhash", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO state_positions(position_key, payload_json, payload_sha256, updated_at) VALUES(?, ?, ?, ?)",
            ("MKT2:no", "{}", "removehash", "2026-01-01T00:00:00Z"),
        )


def test_boot_rehydrate_reconciles_and_sets_readiness(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _seed_db(db_path)

    gate = StateReadinessGate()
    client = FakeKalshiClient(
        open_orders={"orders": [{"order_id": "o-1", "market_id": "MKT1", "status": "open"}, {"id": "o-2", "status": "open"}]},
        positions={"positions": [{"market_id": "MKT1", "side": "yes", "contracts": 10}]},
    )
    rehydrator = StateRehydrator(db_path=str(db_path), kalshi_client=client, readiness_gate=gate)
    rehydrator.boot_rehydrate()

    assert gate.wait_until_ready(0.1)
    health = gate.snapshot()
    assert health["ready"] is True
    assert health["last_error"] is None

    with sqlite3.connect(db_path) as conn:
        order_states = {row[0]: row[1] for row in conn.execute("SELECT order_id, state FROM state_orders")}
        assert order_states["stale-local"] == "closed"
        assert order_states["o-1"] == "open"
        assert order_states["o-2"] == "open"

        position_keys = [row[0] for row in conn.execute("SELECT position_key FROM state_positions ORDER BY position_key")]
        assert position_keys == ["MKT1:yes"]

        event_rows = list(conn.execute("SELECT category, action, source_event_id, ingest_at FROM reconciliation_event_ledger"))
        assert len(event_rows) >= 4
        assert all(row[2].startswith("boot:") for row in event_rows)
        assert all(row[3].endswith("Z") for row in event_rows)

        run = conn.execute("SELECT status, drift_count, error FROM rehydration_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        assert run == ("completed", len(event_rows), None)


def test_boot_rehydrate_failure_keeps_strategy_blocked(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    gate = StateReadinessGate()
    client = FakeKalshiClient(open_orders={"orders": []}, positions={"positions": []}, fail=True)
    rehydrator = StateRehydrator(db_path=str(db_path), kalshi_client=client, readiness_gate=gate)

    try:
        rehydrator.boot_rehydrate()
    except RehydrationError:
        pass
    else:
        raise AssertionError("expected rehydration error")

    assert not gate.wait_until_ready(0.01)
    try:
        gate.assert_ready()
    except RehydrationError as exc:
        assert "blocked" in str(exc)
    else:
        raise AssertionError("expected strategy execution block")

    with sqlite3.connect(db_path) as conn:
        run = conn.execute("SELECT status, error FROM rehydration_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        assert run is not None
        assert run[0] == "failed"
        assert "kalshi unavailable" in run[1]
