"""Interfaces for Kalshi connector capabilities."""

from __future__ import annotations

from typing import Any, AsyncIterator, Mapping, Protocol

from .models import (
    CancelOrderResponse,
    OrderDetails,
    PlaceOrderRequest,
    PlaceOrderResponse,
    PortfolioBalance,
)


class MarketDataStream(Protocol):
    """Consumes real-time market data updates."""

    async def stream_market_data(self, channels: list[str]) -> AsyncIterator[dict[str, Any]]:
        """Yield messages for the requested channels."""

    async def process_market_data_message(self, raw_message: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Normalize and publish websocket messages, returning canonical events."""


class EventPublisher(Protocol):
    """Publishes normalized events to internal bus/queue consumers."""

    async def publish(self, event: Mapping[str, Any]) -> None:
        """Publish one normalized event envelope."""


class OrderExecutionClient(Protocol):
    """Places and manages orders."""

    def place_order(self, order: PlaceOrderRequest) -> PlaceOrderResponse:
        """Submit a new order."""

    def cancel_order(self, order_id: str) -> CancelOrderResponse:
        """Cancel an open order."""

    def get_order(self, order_id: str) -> OrderDetails:
        """Fetch an order by id."""


class AccountReadClient(Protocol):
    """Reads account state from Kalshi."""

    def get_balance(self) -> PortfolioBalance:
        """Read account balance snapshot."""

    def get_open_orders(self) -> dict[str, Any]:
        """Read open orders snapshot."""

    def get_positions(self) -> dict[str, Any]:
        """Read open positions snapshot."""
