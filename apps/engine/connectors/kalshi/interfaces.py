"""Interfaces for Kalshi connector capabilities."""

from __future__ import annotations

from typing import Any, AsyncIterator, Mapping, Protocol


class MarketDataStream(Protocol):
    """Consumes real-time market data updates."""

    async def stream_market_data(self, channels: list[str]) -> AsyncIterator[dict[str, Any]]:
        """Yield messages for the requested channels."""


class OrderExecutionClient(Protocol):
    """Places and manages orders."""

    def place_order(self, order_payload: Mapping[str, Any]) -> dict[str, Any]:
        """Submit a new order."""

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an open order."""


class AccountReadClient(Protocol):
    """Reads account state from Kalshi."""

    def get_balance(self) -> dict[str, Any]:
        """Read account balance snapshot."""

    def get_positions(self) -> dict[str, Any]:
        """Read open positions snapshot."""
