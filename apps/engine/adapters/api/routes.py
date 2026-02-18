"""Route handlers for engine local API adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from connectors.kalshi.errors import ConnectorError, ConnectorErrorCode, map_kalshi_error

from services.trading.api_service import TradingApiService

from .auth import AuthNonceGuard
from .contracts.v1 import (
    ApiEnvelopeV1,
    BalanceResponseV1,
    BotControlRequestV1,
    BotControlResponseV1,
    CancelOrderRequestV1,
    ContractValidationError,
    PlaceOrderRequestV1,
)
from .errors import ApiError


class ApiRouter:
    """Framework-agnostic route layer so web frameworks can adapt it."""

    def __init__(self, service: TradingApiService, guard: AuthNonceGuard):
        self._service = service
        self._guard = guard

    def place_order(self, *, headers: Mapping[str, str], body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            self._guard.validate(headers)
            request = PlaceOrderRequestV1.from_mapping(body)
            order = self._service.place_order(
                market_id=request.market_id,
                side=request.side,
                price=request.price,
                quantity=request.quantity,
                client_order_id=request.client_order_id,
            )
            payload = ApiEnvelopeV1.ok(
                {
                    "order": {
                        "order_id": order.order_id,
                        "market_id": order.market_id,
                        "status": order.status,
                        "side": order.side,
                        "price": order.price,
                        "quantity": order.quantity,
                        "filled_quantity": order.filled_quantity,
                        "updated_at": order.updated_at,
                    }
                }
            )
            return 201, payload.to_dict()
        except ContractValidationError as exc:
            return self._error_response(ApiError("validation", details={"reason": str(exc)}), 400)
        except Exception as exc:
            return self._map_unexpected_error(exc)

    def cancel_order(self, *, headers: Mapping[str, str], body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            self._guard.validate(headers)
            request = CancelOrderRequestV1.from_mapping(body)
            result = self._service.cancel_order(order_id=request.order_id)
            return 200, ApiEnvelopeV1.ok({"cancel": result}).to_dict()
        except ContractValidationError as exc:
            return self._error_response(ApiError("validation", details={"reason": str(exc)}), 400)
        except Exception as exc:
            return self._map_unexpected_error(exc)

    def get_balance(self, *, headers: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
        try:
            self._guard.validate(headers)
            balance = self._service.get_balance()
            response = BalanceResponseV1(
                contract_version="1.0.0",
                cash_balance=balance.cash_balance,
                available_balance=balance.available_balance,
            )
            return 200, ApiEnvelopeV1.ok(response.to_dict()).to_dict()
        except Exception as exc:
            return self._map_unexpected_error(exc)

    def bot_control(self, *, headers: Mapping[str, str], body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            self._guard.validate(headers)
            request = BotControlRequestV1.from_mapping(body)
            bot_status = self._service.control_bot(action=request.action.value)
            response = BotControlResponseV1.from_state(status=bot_status, action=request.action)
            return 200, ApiEnvelopeV1.ok(response.to_dict()).to_dict()
        except ContractValidationError as exc:
            return self._error_response(ApiError("validation", details={"reason": str(exc)}), 400)
        except Exception as exc:
            return self._map_unexpected_error(exc)

    def _map_unexpected_error(self, exc: Exception) -> tuple[int, dict[str, Any]]:
        if isinstance(exc, ApiError):
            return self._error_response(exc, 401)
        connector_error = exc if isinstance(exc, ConnectorError) else map_kalshi_error(exc)
        status = 500
        kind = "internal"
        if connector_error.code == ConnectorErrorCode.RATE_LIMITED:
            status, kind = 429, "rate_limit"
        elif connector_error.code in {ConnectorErrorCode.NETWORK_ERROR, ConnectorErrorCode.TIMEOUT}:
            status, kind = 503, "network"
        elif connector_error.code in {ConnectorErrorCode.AUTHENTICATION_FAILED, ConnectorErrorCode.AUTHORIZATION_FAILED}:
            status, kind = 401, "auth"
        elif connector_error.code == ConnectorErrorCode.BAD_REQUEST:
            status, kind = 400, "validation"
        return self._error_response(ApiError(kind, details={"reason": str(connector_error)}), status)

    @staticmethod
    def _error_response(error: ApiError, status: int) -> tuple[int, dict[str, Any]]:
        return status, error.payload.to_dict()
