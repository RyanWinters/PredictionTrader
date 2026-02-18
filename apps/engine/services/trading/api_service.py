"""Service-layer boundary for local API routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from connectors.kalshi.client import KalshiClient
from connectors.kalshi.models import CancelOrderResponse, PlaceOrderRequest, PlaceOrderResponse, PortfolioBalance


class BotController(Protocol):
    def apply(self, action: str) -> str:
        """Apply bot action and return the latest bot status."""


@dataclass
class InMemoryBotController:
    _status: str = "stopped"

    def apply(self, action: str) -> str:
        if action == "start":
            self._status = "running"
        elif action == "stop":
            self._status = "stopped"
        elif action == "pause":
            self._status = "paused"
        elif action == "resume":
            self._status = "running"
        return self._status


@dataclass(frozen=True)
class OrderView:
    order_id: str
    market_id: str
    status: str
    side: str
    price: int
    quantity: int
    filled_quantity: int
    updated_at: str


class TradingApiService:
    """Service that mediates API requests from adapters to connectors/controllers."""

    def __init__(self, client: KalshiClient, bot_controller: BotController | None = None):
        self._client = client
        self._bot_controller = bot_controller or InMemoryBotController()

    def place_order(self, *, market_id: str, side: str, price: int, quantity: int, client_order_id: str | None) -> OrderView:
        action = "buy" if side.startswith("buy_") else "sell"
        polarity = "yes" if side.endswith("_yes") else "no"
        request = PlaceOrderRequest(
            market_id=market_id,
            side=polarity,
            action=action,
            count=quantity,
            yes_price=price if polarity == "yes" else None,
            no_price=price if polarity == "no" else None,
            client_order_id=client_order_id,
        )
        response: PlaceOrderResponse = self._client.place_order(request)
        return OrderView(
            order_id=response.order.order_id,
            market_id=response.order.market_id,
            status=response.order.lifecycle_status.value,
            side=side,
            price=price,
            quantity=response.order.quantity,
            filled_quantity=response.order.filled_quantity,
            updated_at=datetime.now(UTC).isoformat(),
        )

    def cancel_order(self, *, order_id: str) -> dict[str, str]:
        response: CancelOrderResponse = self._client.cancel_order(order_id)
        return {"order_id": response.order_id, "status": response.lifecycle_status.value}

    def get_balance(self) -> PortfolioBalance:
        return self._client.get_balance()

    def control_bot(self, *, action: str) -> str:
        return self._bot_controller.apply(action)
