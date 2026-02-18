from __future__ import annotations

import asyncio

from connectors.kalshi.bus import InMemoryEventBus
from connectors.kalshi.client import KalshiAuthSigner, KalshiClient, SimpleHttpSession
from connectors.kalshi.config import KalshiConfig


class DummySession(SimpleHttpSession):
    pass


def _build_client(bus: InMemoryEventBus | None = None) -> KalshiClient:
    return KalshiClient(
        config=KalshiConfig(api_key_id="k", api_key_secret="s"),
        auth_signer=KalshiAuthSigner(api_key_id="k", api_key_secret="s"),
        session=DummySession(),
        event_publisher=bus,
    )


def test_stream_market_data_subscriptions() -> None:
    client = _build_client()

    async def _collect() -> list[dict[str, str]]:
        return [message async for message in client.stream_market_data(["orderbook_delta", "trade", "foo"])]

    messages = asyncio.run(_collect())

    assert [m["channel"] for m in messages] == ["orderbook_delta", "trade"]
    assert all("handler" in m for m in messages)


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
