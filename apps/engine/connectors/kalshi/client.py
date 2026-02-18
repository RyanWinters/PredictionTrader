"""Kalshi HTTP and websocket client with shared auth/session plumbing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import random
import time
from datetime import UTC, datetime
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .config import KalshiConfig
from .errors import ConnectorErrorCode, map_kalshi_error
from .interfaces import AccountReadClient, EventPublisher, MarketDataStream, OrderExecutionClient
from .models import (
    CancelOrderResponse,
    OrderDetails,
    PlaceOrderRequest,
    PlaceOrderResponse,
    PortfolioBalance,
    ValidationError,
)
from .rate_limit import RateLimitBucket, SharedRateLimiter, get_shared_rate_limiter

logger = logging.getLogger(__name__)


class StreamHealthState(str, Enum):
    """Operator-facing connectivity state for the market data stream."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"


class StreamCloseType(str, Enum):
    """Classification of stream disconnects."""

    CLEAN = "clean"
    TRANSIENT_FAILURE = "transient_failure"
    AUTH_FAILURE = "auth_failure"


class KalshiAuthSigner:
    """Builds signed Kalshi headers for HTTP and websocket requests."""

    def __init__(self, api_key_id: str, api_key_secret: str):
        self._api_key_id = api_key_id
        self._api_key_secret = api_key_secret.encode("utf-8")

    def signed_headers(self, *, method: str, path: str, body: str = "") -> dict[str, str]:
        timestamp_ms = str(int(time.time() * 1000))
        signature_payload = f"{timestamp_ms}{method.upper()}{path}{body}"
        digest = hmac.new(self._api_key_secret, signature_payload.encode("utf-8"), hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode("utf-8")
        return {
            "KALSHI-ACCESS-KEY": self._api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }


@dataclass
class HttpResponse:
    status_code: int
    body: bytes

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HttpStatusError(self.status_code, self.body.decode("utf-8", errors="ignore"))

    def json(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8"))


class HttpStatusError(Exception):
    def __init__(self, status_code: int, body: str):
        super().__init__(body)
        self.status_code = status_code


class SimpleHttpSession:
    """Minimal urllib-backed HTTP session abstraction."""

    def request(self, *, method: str, url: str, data: str | None, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        payload = data.encode("utf-8") if data is not None else None
        request = Request(url=url, data=payload, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is explicit config
                return HttpResponse(status_code=response.status, body=response.read())
        except HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            raise HttpStatusError(exc.code, body.decode("utf-8", errors="ignore")) from exc
        except URLError as exc:
            raise OSError(str(exc)) from exc


class KalshiSessionFactory:
    """Creates shared HTTP session objects with default timeout/retry behaviors."""

    def __init__(self, config: KalshiConfig):
        self._config = config

    def create_http_session(self) -> SimpleHttpSession:
        return SimpleHttpSession()


class KalshiClient(MarketDataStream, OrderExecutionClient, AccountReadClient):
    """Concrete connector implementation used behind interfaces."""

    SUPPORTED_MARKET_DATA_CHANNELS: tuple[str, ...] = ("orderbook_delta", "trade")

    def __init__(
        self,
        *,
        config: KalshiConfig,
        auth_signer: KalshiAuthSigner,
        session: SimpleHttpSession,
        event_publisher: EventPublisher | None = None,
        rate_limiter: SharedRateLimiter | None = None,
    ) -> None:
        self._config = config
        self._auth_signer = auth_signer
        self._session = session
        self._event_publisher = event_publisher
        self._rate_limiter = rate_limiter or get_shared_rate_limiter(config.rate_limit)

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        url = urljoin(f"{self._config.base_url}/", path.lstrip("/"))
        body = json.dumps(dict(payload or {}), separators=(",", ":")) if payload else ""
        headers = {
            "Content-Type": "application/json",
            **self._auth_signer.signed_headers(method=method, path=path, body=body),
        }
        if extra_headers:
            headers.update(extra_headers)

        attempts = 0
        while True:
            attempts += 1
            try:
                bucket = RateLimitBucket.READ if method.upper() == "GET" else RateLimitBucket.WRITE
                self._rate_limiter.acquire(bucket, operation=f"rest:{method.upper()}:{path}")
                response = self._session.request(
                    method=method,
                    url=url,
                    data=body or None,
                    headers=headers,
                    timeout=self._config.timeout_seconds,
                )
                response.raise_for_status()
                if response.body:
                    return response.json()
                return {}
            except Exception as exc:  # mapped to internal errors for service consumers
                mapped = map_kalshi_error(exc)
                if attempts >= self._config.retry.max_attempts or mapped.code not in {
                    ConnectorErrorCode.NETWORK_ERROR,
                    ConnectorErrorCode.TIMEOUT,
                    ConnectorErrorCode.RATE_LIMITED,
                }:
                    raise mapped from exc
                time.sleep(self._config.retry.backoff_seconds * attempts)

    def place_order(self, order: PlaceOrderRequest | Mapping[str, Any]) -> PlaceOrderResponse:
        try:
            request_model = order if isinstance(order, PlaceOrderRequest) else PlaceOrderRequest.from_mapping(order)
            response = self._request(
                "POST",
                "/portfolio/orders",
                request_model.to_exchange_payload(),
                extra_headers={"Idempotency-Key": request_model.idempotency_key} if request_model.idempotency_key else None,
            )
            return PlaceOrderResponse.from_exchange(response)
        except (ValueError, TypeError) as exc:
            raise map_kalshi_error(ValidationError(str(exc))) from exc

    def cancel_order(self, order_id: str) -> CancelOrderResponse:
        response = self._request("DELETE", f"/portfolio/orders/{order_id}")
        try:
            return CancelOrderResponse.from_exchange(response, fallback_order_id=order_id)
        except (ValueError, TypeError) as exc:
            raise map_kalshi_error(ValidationError(str(exc))) from exc

    def get_order(self, order_id: str) -> OrderDetails:
        response = self._request("GET", f"/portfolio/orders/{order_id}")
        try:
            order_payload = response.get("order") if isinstance(response.get("order"), Mapping) else response
            return OrderDetails.from_exchange(order_payload)
        except (ValueError, TypeError) as exc:
            raise map_kalshi_error(ValidationError(str(exc))) from exc

    def get_balance(self) -> PortfolioBalance:
        response = self._request("GET", "/portfolio/balance")
        try:
            return PortfolioBalance.from_exchange(response)
        except (ValueError, TypeError) as exc:
            raise map_kalshi_error(ValidationError(str(exc))) from exc

    def get_positions(self) -> dict[str, Any]:
        return self._request("GET", "/portfolio/positions")

    async def stream_market_data(self, channels: list[str]) -> AsyncIterator[dict[str, Any]]:
        """Yield websocket control envelopes with reconnect orchestration metadata."""

        ws_path = "/marketdata/stream"
        headers = self._auth_signer.signed_headers(method="GET", path=ws_path)
        subscribed_channels = [channel for channel in channels if self._is_supported_channel(channel)]

        retry_started_at: float | None = None
        consecutive_failures = 0
        health_state = StreamHealthState.HEALTHY

        while True:
            try:
                await self._rate_limiter.acquire_async(RateLimitBucket.READ, operation="ws:connect")
            except Exception as exc:
                raise map_kalshi_error(exc) from exc
            logger.info(
                "kalshi_market_data_connect",
                extra={"event": "connect", "url": self._config.websocket_url, "channels": subscribed_channels},
            )
            yield {
                "type": "connect",
                "url": self._config.websocket_url,
                "headers": headers,
            }

            for channel in subscribed_channels:
                try:
                    await self._rate_limiter.acquire_async(RateLimitBucket.WRITE, operation=f"ws:subscribe:{channel}")
                except Exception as exc:
                    raise map_kalshi_error(exc) from exc
                logger.info(
                    "kalshi_market_data_subscribe",
                    extra={"event": "subscribe", "channel": channel},
                )
                yield {
                    "type": "subscribe",
                    "channel": channel,
                    "headers": headers,
                    "url": self._config.websocket_url,
                    "handler": f"handle_{channel}",
                    "resubscribe": True,
                }

            connect_started_at = time.monotonic()
            disconnect_notice = yield {"type": "await_disconnect"}
            close_type = self._classify_stream_close(disconnect_notice)

            if close_type == StreamCloseType.CLEAN:
                logger.info(
                    "kalshi_market_data_disconnect_clean",
                    extra={"event": "disconnect", "classification": close_type.value},
                )
                return

            if close_type == StreamCloseType.AUTH_FAILURE:
                if health_state != StreamHealthState.DEGRADED:
                    health_state = StreamHealthState.DEGRADED
                    yield self._build_health_event(
                        health_state=health_state,
                        reason="auth_failure",
                        attempt=consecutive_failures + 1,
                    )
                logger.error(
                    "kalshi_market_data_disconnect_auth_failure",
                    extra={"event": "disconnect", "classification": close_type.value},
                )
                return

            now = time.monotonic()
            uptime = now - connect_started_at
            reconnect_config = self._config.stream_reconnect
            if uptime >= reconnect_config.stable_connect_seconds:
                consecutive_failures = 0
                retry_started_at = None

            if retry_started_at is None:
                retry_started_at = now
            consecutive_failures += 1

            if now - retry_started_at > reconnect_config.max_retry_window_seconds:
                logger.error(
                    "kalshi_market_data_retry_window_exhausted",
                    extra={"event": "disconnect", "attempt": consecutive_failures},
                )
                if health_state != StreamHealthState.DEGRADED:
                    health_state = StreamHealthState.DEGRADED
                    yield self._build_health_event(
                        health_state=health_state,
                        reason="max_retry_window_reached",
                        attempt=consecutive_failures,
                    )
                return

            if consecutive_failures >= reconnect_config.degraded_after_attempts and health_state != StreamHealthState.DEGRADED:
                health_state = StreamHealthState.DEGRADED
                yield self._build_health_event(
                    health_state=health_state,
                    reason="repeated_disconnects",
                    attempt=consecutive_failures,
                )

            backoff_seconds = self._compute_stream_backoff_seconds(consecutive_failures)
            logger.warning(
                "kalshi_market_data_reconnect_scheduled",
                extra={
                    "event": "reconnect_scheduled",
                    "attempt": consecutive_failures,
                    "backoff_ms": int(backoff_seconds * 1000),
                    "classification": close_type.value,
                },
            )
            yield {
                "type": "reconnect_scheduled",
                "attempt": consecutive_failures,
                "backoff_seconds": backoff_seconds,
                "close_type": close_type.value,
            }

            recovered = yield {"type": "sleep", "seconds": backoff_seconds}
            if recovered and recovered.get("stable_connect"):
                consecutive_failures = 0
                retry_started_at = None
                if health_state != StreamHealthState.HEALTHY:
                    health_state = StreamHealthState.HEALTHY
                    yield self._build_health_event(
                        health_state=health_state,
                        reason="stable_connection_restored",
                        attempt=0,
                    )


    def _is_supported_channel(self, channel: str) -> bool:
        if channel not in self.SUPPORTED_MARKET_DATA_CHANNELS:
            logger.warning(
                "kalshi_market_data_unsupported_channel",
                extra={"event": "subscribe", "channel": channel},
            )
            return False
        return True

    @staticmethod
    def _classify_stream_close(disconnect_notice: Mapping[str, Any] | None) -> StreamCloseType:
        if not disconnect_notice:
            return StreamCloseType.TRANSIENT_FAILURE

        if disconnect_notice.get("clean") is True:
            return StreamCloseType.CLEAN

        status_code = disconnect_notice.get("status_code")
        if status_code in {401, 403}:
            return StreamCloseType.AUTH_FAILURE

        reason = str(disconnect_notice.get("reason") or "").lower()
        if "auth" in reason or "credential" in reason or "token" in reason:
            return StreamCloseType.AUTH_FAILURE

        return StreamCloseType.TRANSIENT_FAILURE

    def _compute_stream_backoff_seconds(self, attempt: int) -> float:
        reconnect_config = self._config.stream_reconnect
        exponential = reconnect_config.base_backoff_seconds * (2 ** max(0, attempt - 1))
        clamped = min(exponential, reconnect_config.max_backoff_seconds)
        jitter_range = clamped * reconnect_config.jitter_ratio
        return max(0.0, clamped + random.uniform(-jitter_range, jitter_range))

    @staticmethod
    def _build_health_event(*, health_state: StreamHealthState, reason: str, attempt: int) -> dict[str, Any]:
        return {
            "type": "health_state",
            "state": health_state.value,
            "reason": reason,
            "attempt": attempt,
        }

    async def process_market_data_message(self, raw_message: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Normalize channel messages and publish to internal event bus."""

        logger.debug(
            "kalshi_market_data_message_received",
            extra={"event": "message", "raw_type": raw_message.get("type"), "channel": raw_message.get("channel")},
        )

        normalized_events = self._normalize_message(raw_message)
        payload = self._extract_payload(raw_message)
        source_sequence = self._extract_sequence(payload)
        source_timestamp = self._normalize_timestamp(payload.get("timestamp") or payload.get("ts"))
        published: list[dict[str, Any]] = []
        for event in normalized_events:
            envelope = {
                "source": "kalshi",
                "schema": event["schema"],
                "source_sequence": source_sequence,
                "source_timestamp": source_timestamp,
                "ingest_timestamp": self._normalize_timestamp(time.time()),
                "payload": event,
            }
            if self._event_publisher is not None:
                await self._event_publisher.publish(envelope)
            published.append(event)
        return published

    def _normalize_message(self, raw_message: Mapping[str, Any]) -> list[dict[str, Any]]:
        payload = self._extract_payload(raw_message)
        channel = str(raw_message.get("channel") or payload.get("type") or raw_message.get("type") or "")
        try:
            if channel == "orderbook_delta":
                return [self._normalize_orderbook_delta(payload)]
            if channel == "trade":
                return [self._normalize_trade(payload)]
            logger.debug(
                "kalshi_market_data_message_skipped",
                extra={"event": "message", "reason": "unsupported_channel", "channel": channel},
            )
            return []
        except Exception as exc:
            logger.error(
                "kalshi_market_data_parse_failure",
                extra={"event": "parse_failure", "channel": channel, "raw_message": dict(raw_message)},
            )
            raise ValueError(f"Unable to parse market data message for channel '{channel}'") from exc

    @staticmethod
    def _extract_payload(raw_message: Mapping[str, Any]) -> Mapping[str, Any]:
        candidate = raw_message.get("data")
        if isinstance(candidate, Mapping):
            return candidate
        return raw_message

    def _normalize_orderbook_delta(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        side = str(payload.get("side") or "").lower()
        if side not in {"yes", "no"}:
            raise ValueError("orderbook_delta side must be yes/no")

        return {
            "schema": "orderbook_delta",
            "market_id": str(payload["market_id"]),
            "sequence": self._extract_sequence(payload),
            "timestamp": self._normalize_timestamp(payload.get("timestamp") or payload.get("ts")),
            "side": side,
            "price": self._to_int(payload.get("price")),
            "size_delta": self._to_int(payload.get("size_delta") or payload.get("delta") or payload.get("size")),
        }

    def _normalize_trade(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        side = str(payload.get("side") or "").lower()
        allowed_sides = {"buy_yes", "sell_yes", "buy_no", "sell_no"}
        if side not in allowed_sides:
            raise ValueError("trade side must be buy_yes/sell_yes/buy_no/sell_no")

        liquidity = str(payload.get("liquidity") or "").lower()
        if liquidity not in {"maker", "taker"}:
            raise ValueError("trade liquidity must be maker/taker")

        return {
            "schema": "trade",
            "trade_id": str(payload.get("trade_id") or payload.get("id")),
            "market_id": str(payload["market_id"]),
            "timestamp": self._normalize_timestamp(payload.get("timestamp") or payload.get("ts")),
            "side": side,
            "price": self._to_int(payload.get("price")),
            "size": self._to_int(payload.get("size")),
            "liquidity": liquidity,
        }

    @staticmethod
    def _to_int(value: Any) -> int:
        if value is None:
            raise ValueError("Required numeric field missing")
        return int(value)

    @staticmethod
    def _extract_sequence(payload: Mapping[str, Any]) -> int:
        sequence = payload.get("sequence")
        if sequence is None:
            sequence = payload.get("seq")
        if sequence is None:
            sequence = payload.get("sid")
        return int(sequence or 0)

    @staticmethod
    def _normalize_timestamp(value: Any) -> str:
        if value is None:
            raise ValueError("Missing timestamp")

        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")

        numeric = float(value)
        if numeric > 1_000_000_000_000:
            numeric = numeric / 1000.0
        dt = datetime.fromtimestamp(numeric, tz=UTC)
        return dt.isoformat().replace("+00:00", "Z")
