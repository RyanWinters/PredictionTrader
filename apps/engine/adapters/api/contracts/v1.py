"""Versioned API contract models for local engine endpoints (v1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping


class ContractValidationError(ValueError):
    """Raised when an API payload does not satisfy the versioned contract."""


class ContractVersion(str, Enum):
    V1 = "1.0.0"


class BotAction(str, Enum):
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"


@dataclass(frozen=True)
class PlaceOrderRequestV1:
    account_id: str
    market_id: str
    side: str
    price: int
    quantity: int
    client_order_id: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PlaceOrderRequestV1":
        request = cls(
            account_id=str(payload.get("account_id", "")),
            market_id=str(payload.get("market_id", "")),
            side=str(payload.get("side", "")),
            price=int(payload.get("price", 0)),
            quantity=int(payload.get("quantity", 0)),
            client_order_id=str(payload["client_order_id"]) if payload.get("client_order_id") else None,
        )
        request.validate()
        return request

    def validate(self) -> None:
        if not self.account_id:
            raise ContractValidationError("account_id is required")
        if not self.market_id:
            raise ContractValidationError("market_id is required")
        if self.side not in {"buy_yes", "sell_yes", "buy_no", "sell_no"}:
            raise ContractValidationError("side must be one of: buy_yes, sell_yes, buy_no, sell_no")
        if not 1 <= self.price <= 99:
            raise ContractValidationError("price must be in [1, 99]")
        if self.quantity <= 0:
            raise ContractValidationError("quantity must be positive")


@dataclass(frozen=True)
class CancelOrderRequestV1:
    order_id: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CancelOrderRequestV1":
        request = cls(order_id=str(payload.get("order_id", "")))
        if not request.order_id:
            raise ContractValidationError("order_id is required")
        return request


@dataclass(frozen=True)
class BalanceResponseV1:
    contract_version: str
    cash_balance: int
    available_balance: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "cash_balance": self.cash_balance,
            "available_balance": self.available_balance,
        }


@dataclass(frozen=True)
class BotControlRequestV1:
    action: BotAction

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "BotControlRequestV1":
        raw_action = str(payload.get("action", "")).lower()
        if not raw_action:
            raise ContractValidationError("action is required")
        try:
            action = BotAction(raw_action)
        except ValueError as exc:
            raise ContractValidationError("unsupported bot action") from exc
        return cls(action=action)


@dataclass(frozen=True)
class BotControlResponseV1:
    contract_version: str
    status: str
    action: str
    updated_at: str

    @classmethod
    def from_state(cls, *, status: str, action: BotAction) -> "BotControlResponseV1":
        return cls(
            contract_version=ContractVersion.V1.value,
            status=status,
            action=action.value,
            updated_at=datetime.now(UTC).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "status": self.status,
            "action": self.action,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ApiEnvelopeV1:
    contract_version: str
    data: Mapping[str, Any]

    @classmethod
    def ok(cls, data: Mapping[str, Any]) -> "ApiEnvelopeV1":
        return cls(contract_version=ContractVersion.V1.value, data=data)

    def to_dict(self) -> dict[str, Any]:
        return {"contract_version": self.contract_version, "data": dict(self.data)}
