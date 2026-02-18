from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from connectors.kalshi.bus import InMemoryEventBus
from connectors.kalshi.client import HttpResponse, KalshiAuthSigner, KalshiClient, SimpleHttpSession
from connectors.kalshi.config import KalshiConfig, RateLimitConfig, RetryConfig, StreamReconnectConfig
from connectors.kalshi.errors import ConnectorErrorCode
from connectors.kalshi.models import (
    OrderLifecycleStatus,
    PlaceOrderRequest,
)
from connectors.kalshi.rate_limit import RateLimitBucket, SharedRateLimiter, get_shared_rate_limiter


class DummySession(SimpleHttpSession):
    def __init__(self, responses: list[dict[str, Any]] | None = None):
        self.responses = responses or []
        self.requests: list[dict[str, Any]] = []

    def request(self, *, method: str, url: str, data: str | None, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "data": data, "headers": dict(headers), "timeout": timeout})
        if not self.responses:
            return HttpResponse(200, b"{}")
        response = self.responses.pop(0)
        status = int(response.get("status_code", 200))
        payload = response.get("payload", {})
        return HttpResponse(status_code=status, body=json.dumps(payload).encode("utf-8"))


def _build_client(
    bus: InMemoryEventBus | None = None,
    reconnect_config: StreamReconnectConfig | None = None,
    session: DummySession | None = None,
    rate_limit_config: RateLimitConfig | None = None,
    retry_config: RetryConfig | None = None,
    rate_limiter: SharedRateLimiter | None = None,
) -> KalshiClient:
    return KalshiClient(
        config=KalshiConfig(
            api_key_id="k",
            api_key_secret="s",
            retry=retry_config or RetryConfig(),
            stream_reconnect=reconnect_config or StreamReconnectConfig(),
            rate_limit=rate_limit_config or RateLimitConfig(),
        ),
        auth_signer=KalshiAuthSigner(api_key_id="k", api_key_secret="s"),
        session=session or DummySession(),
        event_publisher=bus,
        rate_limiter=rate_limiter,
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


def test_place_order_validates_and_adds_idempotency_header() -> None:
    session = DummySession(
        responses=[
            {
                "payload": {
                    "order": {
                        "order_id": "o-123",
                        "ticker": "KXTEST",
                        "side": "yes",
                        "action": "buy",
                        "count": 10,
                        "filled_count": 0,
                        "status": "queued",
                    }
                }
            }
        ]
    )
    client = _build_client(session=session)
    response = client.place_order(
        PlaceOrderRequest(
            market_id="KXTEST",
            side="yes",
            action="buy",
            count=10,
            yes_price=45,
            idempotency_key="idem-1",
        )
    )

    assert response.order.order_id == "o-123"
    assert response.order.lifecycle_status == OrderLifecycleStatus.PENDING
    assert session.requests[0]["headers"]["Idempotency-Key"] == "idem-1"


def test_order_query_cancel_and_balance_models() -> None:
    session = DummySession(
        responses=[
            {
                "payload": {
                    "order": {
                        "id": "o-456",
                        "market_id": "KXTEST",
                        "side": "no",
                        "action": "sell",
                        "quantity": 4,
                        "filled_quantity": 2,
                        "status": "partially_filled",
                    }
                }
            },
            {"payload": {"status": "cancelled"}},
            {"payload": {"balance": {"cash": 1200, "available": 900}}},
        ]
    )
    client = _build_client(session=session)

    order = client.get_order("o-456")
    canceled = client.cancel_order("o-456")
    balance = client.get_balance()

    assert order.lifecycle_status == OrderLifecycleStatus.PARTIALLY_FILLED
    assert canceled.lifecycle_status == OrderLifecycleStatus.CANCELED
    assert canceled.order_id == "o-456"
    assert balance.cash_balance == 1200
    assert balance.available_balance == 900


def test_schema_validation_errors_are_mapped() -> None:
    client = _build_client()
    try:
        client.place_order({"market_id": "KXTEST", "side": "yes", "action": "buy", "count": 1})
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", None) == ConnectorErrorCode.SCHEMA_VALIDATION
    else:
        raise AssertionError("expected schema validation error")


def test_rest_write_requests_can_be_dropped_by_rate_limiter() -> None:
    session = DummySession(responses=[{"payload": {}}, {"payload": {}}])
    client = _build_client(
        session=session,
        rate_limiter=SharedRateLimiter(
            RateLimitConfig(read_requests_per_second=50, write_requests_per_second=1, wait_timeout_seconds=0.0)
        ),
        retry_config=RetryConfig(max_attempts=1, backoff_seconds=0.0),
    )

    client.cancel_order("o-1")

    try:
        client.cancel_order("o-2")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", None) == ConnectorErrorCode.RATE_LIMITED
    else:
        raise AssertionError("expected rate limited error")


def test_shared_rate_limiter_instance_is_reused() -> None:
    first = get_shared_rate_limiter(
        RateLimitConfig(
            read_requests_per_second=1,
            write_requests_per_second=1,
            wait_timeout_seconds=1.1,
        )
    )
    second = get_shared_rate_limiter(RateLimitConfig(read_requests_per_second=20, write_requests_per_second=10))

    assert first is second


def test_rate_limiter_tracks_throttled_and_dropped_metrics() -> None:
    limiter = SharedRateLimiter(
        RateLimitConfig(read_requests_per_second=1, write_requests_per_second=1, wait_timeout_seconds=1.1)
    )
    limiter.acquire(bucket=RateLimitBucket.READ, operation="test-prime")
    limiter.acquire(bucket=RateLimitBucket.READ, operation="test-throttle")
    limiter.configure(RateLimitConfig(read_requests_per_second=1, write_requests_per_second=1, wait_timeout_seconds=0.0))
    try:
        limiter.acquire(bucket=RateLimitBucket.READ, operation="test-drop")
    except Exception:
        pass

    metrics = limiter.metrics_snapshot()
    assert metrics.throttled_requests >= 1
    assert metrics.dropped_requests >= 1
