"""Typed request/response models and schema validation for Kalshi trading endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class ValidationError(ValueError):
    """Raised when a request or response fails schema validation."""


class OrderSide(str, Enum):
    YES = "yes"
    NO = "no"


class OrderAction(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


class OrderLifecycleStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


_STATUS_MAP: dict[str, OrderLifecycleStatus] = {
    "pending": OrderLifecycleStatus.PENDING,
    "queued": OrderLifecycleStatus.PENDING,
    "resting": OrderLifecycleStatus.OPEN,
    "open": OrderLifecycleStatus.OPEN,
    "active": OrderLifecycleStatus.OPEN,
    "partially_filled": OrderLifecycleStatus.PARTIALLY_FILLED,
    "partial_fill": OrderLifecycleStatus.PARTIALLY_FILLED,
    "filled": OrderLifecycleStatus.FILLED,
    "executed": OrderLifecycleStatus.FILLED,
    "canceled": OrderLifecycleStatus.CANCELED,
    "cancelled": OrderLifecycleStatus.CANCELED,
    "void": OrderLifecycleStatus.CANCELED,
    "rejected": OrderLifecycleStatus.REJECTED,
    "declined": OrderLifecycleStatus.REJECTED,
    "expired": OrderLifecycleStatus.EXPIRED,
}


def normalize_exchange_status(status: str) -> OrderLifecycleStatus:
    """Normalize Kalshi status values to internal order lifecycle enums."""

    return _STATUS_MAP.get(status.strip().lower(), OrderLifecycleStatus.UNKNOWN)


@dataclass(frozen=True)
class PlaceOrderRequest:
    market_id: str
    side: OrderSide
    action: OrderAction
    count: int
    order_type: OrderType = OrderType.LIMIT
    yes_price: int | None = None
    no_price: int | None = None
    client_order_id: str | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "side", self.side if isinstance(self.side, OrderSide) else OrderSide(str(self.side).lower()))
        object.__setattr__(
            self,
            "action",
            self.action if isinstance(self.action, OrderAction) else OrderAction(str(self.action).lower()),
        )
        object.__setattr__(
            self,
            "order_type",
            self.order_type if isinstance(self.order_type, OrderType) else OrderType(str(self.order_type).lower()),
        )
        if not self.market_id:
            raise ValidationError("market_id is required")
        if self.count <= 0:
            raise ValidationError("count must be positive")
        if self.order_type == OrderType.LIMIT and self.yes_price is None and self.no_price is None:
            raise ValidationError("limit orders require yes_price or no_price")
        if self.yes_price is not None and not 1 <= self.yes_price <= 99:
            raise ValidationError("yes_price must be in [1, 99]")
        if self.no_price is not None and not 1 <= self.no_price <= 99:
            raise ValidationError("no_price must be in [1, 99]")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PlaceOrderRequest":
        return cls(
            market_id=str(payload.get("market_id") or payload.get("ticker") or ""),
            side=OrderSide(str(payload.get("side", "")).lower()),
            action=OrderAction(str(payload.get("action", "buy")).lower()),
            count=int(payload.get("count", 0)),
            order_type=OrderType(str(payload.get("type", "limit")).lower()),
            yes_price=int(payload["yes_price"]) if payload.get("yes_price") is not None else None,
            no_price=int(payload["no_price"]) if payload.get("no_price") is not None else None,
            client_order_id=str(payload["client_order_id"]) if payload.get("client_order_id") is not None else None,
            idempotency_key=str(payload["idempotency_key"]) if payload.get("idempotency_key") is not None else None,
        )

    def to_exchange_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ticker": self.market_id,
            "side": self.side.value,
            "action": self.action.value,
            "count": self.count,
            "type": self.order_type.value,
        }
        if self.yes_price is not None:
            payload["yes_price"] = self.yes_price
        if self.no_price is not None:
            payload["no_price"] = self.no_price
        if self.client_order_id:
            payload["client_order_id"] = self.client_order_id
        return payload


@dataclass(frozen=True)
class OrderDetails:
    order_id: str
    market_id: str
    side: OrderSide
    action: OrderAction
    quantity: int
    filled_quantity: int
    lifecycle_status: OrderLifecycleStatus
    raw_status: str

    @classmethod
    def from_exchange(cls, payload: Mapping[str, Any]) -> "OrderDetails":
        order_id = str(payload.get("order_id") or payload.get("id") or "")
        if not order_id:
            raise ValidationError("order response missing order_id")

        raw_status = str(payload.get("status") or payload.get("order_status") or "")

        return cls(
            order_id=order_id,
            market_id=str(payload.get("ticker") or payload.get("market_id") or ""),
            side=OrderSide(str(payload.get("side", "")).lower()),
            action=OrderAction(str(payload.get("action", "buy")).lower()),
            quantity=int(payload.get("count") or payload.get("quantity") or 0),
            filled_quantity=int(payload.get("filled_count") or payload.get("filled_quantity") or 0),
            lifecycle_status=normalize_exchange_status(raw_status),
            raw_status=raw_status,
        )


@dataclass(frozen=True)
class PlaceOrderResponse:
    order: OrderDetails

    @classmethod
    def from_exchange(cls, payload: Mapping[str, Any]) -> "PlaceOrderResponse":
        order_payload = payload.get("order") if isinstance(payload.get("order"), Mapping) else payload
        return cls(order=OrderDetails.from_exchange(order_payload))


@dataclass(frozen=True)
class CancelOrderResponse:
    order_id: str
    lifecycle_status: OrderLifecycleStatus
    raw_status: str

    @classmethod
    def from_exchange(cls, payload: Mapping[str, Any], *, fallback_order_id: str = "") -> "CancelOrderResponse":
        order_id = str(payload.get("order_id") or payload.get("id") or fallback_order_id)
        if not order_id:
            raise ValidationError("cancel response missing order_id")
        raw_status = str(payload.get("status") or payload.get("order_status") or "canceled")
        return cls(
            order_id=order_id,
            lifecycle_status=normalize_exchange_status(raw_status),
            raw_status=raw_status,
        )


@dataclass(frozen=True)
class PortfolioBalance:
    cash_balance: int
    available_balance: int

    @classmethod
    def from_exchange(cls, payload: Mapping[str, Any]) -> "PortfolioBalance":
        if payload.get("balance") is not None:
            raw_balance = payload.get("balance")
            if isinstance(raw_balance, Mapping):
                payload = raw_balance

        cash = payload.get("cash")
        if cash is None:
            cash = payload.get("cash_balance")
        available = payload.get("available")
        if available is None:
            available = payload.get("available_balance")

        if cash is None or available is None:
            raise ValidationError("balance response missing cash/available fields")

        return cls(cash_balance=int(cash), available_balance=int(available))
