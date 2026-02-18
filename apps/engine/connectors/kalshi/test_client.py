from __future__ import annotations

import asyncio

from connectors.kalshi.bus import InMemoryEventBus
from connectors.kalshi.client import KalshiAuthSigner, KalshiClient, SimpleHttpSession
from connectors.kalshi.config import KalshiConfig, StreamReconnectConfig


class DummySession(SimpleHttpSession):
    pass


def _build_client(
    bus: InMemoryEventBus | None = None,
    reconnect_config: StreamReconnectConfig | None = None,
) -> KalshiClient:
    return KalshiClient(
        config=KalshiConfig(
            api_key_id="k",
            api_key_secret="s",
            stream_reconnect=reconnect_config or StreamReconnectConfig(),
        ),
        auth_signer=KalshiAuthSigner(api_key_id="k", api_key_secret="s"),
        session=DummySession(),
        event_publisher=bus,
    )


def test_stream_market_data_reconnect_orchestration() -> None:
    client = _build_client(
        reconnect_config=StreamReconnectConfig(
            base_backoff_seconds=0.5,
            max_backoff_seconds=1.0,
            jitter_ratio=0.0,
            degraded_after_attempts=1,
            stable_connect_seconds=0.0,
            max_retry_window_seconds=10.0,
        )
    )

    async def _collect() -> list[dict[str, object]]:
        stream = client.stream_market_data(["orderbook_delta", "trade", "foo"])
        emitted: list[dict[str, object]] = []
        emitted.append(await anext(stream))
        emitted.append(await anext(stream))
        emitted.append(await anext(stream))
        emitted.append(await anext(stream))
        emitted.append(await stream.asend({"clean": False, "reason": "connection reset"}))
        emitted.append(await anext(stream))
        emitted.append(await anext(stream))
        emitted.append(await stream.asend({"stable_connect": True}))
        await stream.aclose()
        return emitted

    messages = asyncio.run(_collect())

    assert messages[0]["type"] == "connect"
    assert [messages[1]["channel"], messages[2]["channel"]] == ["orderbook_delta", "trade"]
    assert messages[3] == {"type": "await_disconnect"}
    assert messages[4] == {
        "type": "health_state",
        "state": "degraded",
        "reason": "repeated_disconnects",
        "attempt": 1,
    }
    assert messages[5]["type"] == "reconnect_scheduled"
    assert messages[5]["attempt"] == 1
    assert messages[5]["backoff_seconds"] == 0.5
    assert messages[6] == {"type": "sleep", "seconds": 0.5}
    assert messages[7] == {
        "type": "health_state",
        "state": "healthy",
        "reason": "stable_connection_restored",
        "attempt": 0,
    }


def test_stream_market_data_auth_failure_enters_degraded_and_stops() -> None:
    client = _build_client()

    async def _collect() -> list[dict[str, object]]:
        stream = client.stream_market_data(["trade"])
        emitted: list[dict[str, object]] = []
        emitted.append(await anext(stream))
        emitted.append(await anext(stream))
        emitted.append(await anext(stream))
        emitted.append(await stream.asend({"status_code": 401, "reason": "auth expired"}))
        try:
            await anext(stream)
        except StopAsyncIteration:
            pass
        return emitted

    messages = asyncio.run(_collect())

    assert messages[3] == {
        "type": "health_state",
        "state": "degraded",
        "reason": "auth_failure",
        "attempt": 1,
    }


def test_process_orderbook_delta_publishes_envelope() -> None:
    bus = InMemoryEventBus()
    client = _build_client(bus)

    async def _process() -> tuple[list[dict[str, object]], dict[str, object]]:
        events = await client.process_market_data_message(
            {
                "channel": "orderbook_delta",
                "data": {
                    "market_id": "KXTEST",
                    "sequence": 42,
                    "timestamp": "2026-01-01T12:00:00Z",
                    "side": "YES",
                    "price": "44",
                    "size_delta": "12",
                },
            }
        )
        published = await bus.queue.get()
        return events, published

    events, published = asyncio.run(_process())

    assert events == [
        {
            "schema": "orderbook_delta",
            "market_id": "KXTEST",
            "sequence": 42,
            "timestamp": "2026-01-01T12:00:00Z",
            "side": "yes",
            "price": 44,
            "size_delta": 12,
        }
    ]

    assert published["schema"] == "orderbook_delta"
    assert published["source_sequence"] == 42
    assert published["payload"]["schema"] == "orderbook_delta"


def test_process_trade_normalizes_and_publishes() -> None:
    bus = InMemoryEventBus()
    client = _build_client(bus)

    async def _process() -> tuple[list[dict[str, object]], dict[str, object]]:
        events = await client.process_market_data_message(
            {
                "type": "trade",
                "market_id": "KXTEST",
                "trade_id": "t-1",
                "seq": 99,
                "timestamp": 1767225600,
                "side": "buy_yes",
                "price": 51,
                "size": 7,
                "liquidity": "maker",
            }
        )
        published = await bus.queue.get()
        return events, published

    events, published = asyncio.run(_process())

    assert events == [
        {
            "schema": "trade",
            "trade_id": "t-1",
            "market_id": "KXTEST",
            "timestamp": "2026-01-01T00:00:00Z",
            "side": "buy_yes",
            "price": 51,
            "size": 7,
            "liquidity": "maker",
        }
    ]

    assert published["schema"] == "trade"
    assert published["source_sequence"] == 99
    assert published["payload"]["trade_id"] == "t-1"
