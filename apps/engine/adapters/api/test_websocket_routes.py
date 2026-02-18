from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from adapters.api.websocket_routes import ApiWebSocketConnectionManager


@dataclass
class StubWebSocketClient:
    frames: list[dict[str, Any]] = field(default_factory=list)
    ping_count: int = 0
    close_calls: list[tuple[int, str]] = field(default_factory=list)

    def send_json(self, payload: dict[str, Any]) -> None:
        self.frames.append(payload)

    def send_ping(self) -> None:
        self.ping_count += 1

    def close(self, *, code: int, reason: str) -> None:
        self.close_calls.append((code, reason))


def test_subscribe_and_unsubscribe_semantics() -> None:
    manager = ApiWebSocketConnectionManager()
    client = StubWebSocketClient()
    manager.connect(client_id="c1", client=client, subscriptions=["market"])

    subscriptions = manager.subscribe(client_id="c1", topics=["order", "position"])
    assert subscriptions == {"market", "order", "position"}

    subscriptions = manager.unsubscribe(client_id="c1", topics=["market"])
    assert subscriptions == {"order", "position"}


def test_streams_normalized_market_order_position_and_risk_events() -> None:
    manager = ApiWebSocketConnectionManager()
    client = StubWebSocketClient()
    manager.connect(client_id="c1", client=client)

    manager.stream_event({"schema": "trade", "payload": {"market_id": "M1"}, "timestamp": "2026-01-01T00:00:00Z"})
    manager.stream_event({"topic": "order", "payload": {"order_id": "o1"}, "timestamp": 1_735_689_600})
    manager.stream_event({"schema": "position", "payload": {"market_id": "M1", "size": 2}})
    manager.stream_event({"schema": "risk_alert", "payload": {"level": "high"}, "critical": True})

    sent = manager.flush(client_id="c1")

    assert sent == 4
    assert [frame["topic"] for frame in client.frames] == ["market", "order", "position", "risk_alert"]
    assert all("timestamp" in frame for frame in client.frames)


def test_non_critical_events_drop_under_backpressure() -> None:
    manager = ApiWebSocketConnectionManager(max_queue_size=2)
    client = StubWebSocketClient()
    manager.connect(client_id="c1", client=client)

    manager.stream_event({"topic": "market", "payload": {"i": 1}})
    manager.stream_event({"topic": "order", "payload": {"i": 2}})
    manager.stream_event({"topic": "position", "payload": {"i": 3}})

    stats = manager.get_client_stats(client_id="c1")
    sent = manager.flush(client_id="c1")

    assert stats["dropped_non_critical"] == 1
    assert sent == 2
    assert [frame["payload"]["i"] for frame in client.frames] == [1, 2]


def test_critical_risk_alert_bypasses_non_critical_throttling() -> None:
    manager = ApiWebSocketConnectionManager(max_queue_size=2)
    client = StubWebSocketClient()
    manager.connect(client_id="c1", client=client)

    manager.stream_event({"topic": "market", "payload": {"i": 1}})
    manager.stream_event({"topic": "order", "payload": {"i": 2}})
    manager.stream_event({"topic": "risk_alert", "payload": {"i": 9, "critical": True}})

    sent = manager.flush(client_id="c1")

    assert sent == 2
    assert [frame["topic"] for frame in client.frames] == ["order", "risk_alert"]
    assert client.frames[-1]["critical"] is True


def test_heartbeat_pings_and_disconnects_stale_clients() -> None:
    manager = ApiWebSocketConnectionManager(
        heartbeat_interval=timedelta(seconds=10),
        stale_timeout=timedelta(seconds=30),
    )
    client = StubWebSocketClient()
    manager.connect(client_id="c1", client=client)

    now = datetime.now(UTC)
    pinged = manager.heartbeat(at=now + timedelta(seconds=11))
    assert pinged == ["c1"]
    assert client.ping_count == 1

    manager.mark_client_alive(client_id="c1", at=now + timedelta(seconds=20))
    disconnected = manager.disconnect_stale_clients(at=now + timedelta(seconds=60))
    assert disconnected == ["c1"]
    assert client.close_calls == [(1001, "stale_client")]


def test_invalid_topic_rejected() -> None:
    manager = ApiWebSocketConnectionManager()
    client = StubWebSocketClient()

    with pytest.raises(ValueError):
        manager.connect(client_id="c1", client=client, subscriptions=["unknown"])
