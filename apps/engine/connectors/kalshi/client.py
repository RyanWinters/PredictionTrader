"""Kalshi HTTP and websocket client with shared auth/session plumbing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .config import KalshiConfig
from .errors import ConnectorErrorCode, map_kalshi_error
from .interfaces import AccountReadClient, MarketDataStream, OrderExecutionClient


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

    def __init__(
        self,
        *,
        config: KalshiConfig,
        auth_signer: KalshiAuthSigner,
        session: SimpleHttpSession,
    ) -> None:
        self._config = config
        self._auth_signer = auth_signer
        self._session = session

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(f"{self._config.base_url}/", path.lstrip("/"))
        body = json.dumps(dict(payload or {}), separators=(",", ":")) if payload else ""
        headers = {
            "Content-Type": "application/json",
            **self._auth_signer.signed_headers(method=method, path=path, body=body),
        }

        attempts = 0
        while True:
            attempts += 1
            try:
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

    def place_order(self, order_payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/portfolio/orders", order_payload)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/portfolio/orders/{order_id}")

    def get_balance(self) -> dict[str, Any]:
        return self._request("GET", "/portfolio/balance")

    def get_positions(self) -> dict[str, Any]:
        return self._request("GET", "/portfolio/positions")

    async def stream_market_data(self, channels: list[str]) -> AsyncIterator[dict[str, Any]]:
        """Yield websocket envelopes.

        This method intentionally returns no messages by default; runtime applications can
        wrap this client and connect their websocket implementation while still relying on
        shared signing/auth setup.
        """

        ws_path = "/marketdata/stream"
        subscribe_message = {
            "type": "subscribe",
            "channels": channels,
            "headers": self._auth_signer.signed_headers(method="GET", path=ws_path),
            "url": self._config.websocket_url,
        }
        yield subscribe_message
