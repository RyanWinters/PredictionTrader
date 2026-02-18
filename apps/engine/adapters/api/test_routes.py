from __future__ import annotations

from dataclasses import dataclass

from adapters.api.auth import AuthNonceGuard
from adapters.api.routes import ApiRouter
from connectors.kalshi.errors import ConnectorError, ConnectorErrorCode


@dataclass
class DummyBalance:
    cash_balance: int
    available_balance: int


@dataclass
class DummyOrder:
    order_id: str = "o-1"
    market_id: str = "KX"
    status: str = "pending"
    side: str = "buy_yes"
    price: int = 45
    quantity: int = 10
    filled_quantity: int = 0
    updated_at: str = "2026-01-01T00:00:00Z"


class StubTradingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.fail_with: Exception | None = None

    def place_order(self, **kwargs: object) -> DummyOrder:
        self.calls.append(("place_order", kwargs))
        if self.fail_with:
            raise self.fail_with
        return DummyOrder()

    def cancel_order(self, *, order_id: str) -> dict[str, str]:
        self.calls.append(("cancel_order", {"order_id": order_id}))
        if self.fail_with:
            raise self.fail_with
        return {"order_id": order_id, "status": "canceled"}

    def get_balance(self) -> DummyBalance:
        self.calls.append(("get_balance", {}))
        if self.fail_with:
            raise self.fail_with
        return DummyBalance(cash_balance=1200, available_balance=1000)

    def control_bot(self, *, action: str) -> str:
        self.calls.append(("control_bot", {"action": action}))
        if self.fail_with:
            raise self.fail_with
        return "running" if action in {"start", "resume"} else "paused"


def _headers(nonce: int) -> dict[str, str]:
    return {"x-pt-auth-token": "trusted", "x-pt-nonce": str(nonce)}


def test_place_order_validates_contract_and_uses_service_layer() -> None:
    service = StubTradingService()
    router = ApiRouter(service=service, guard=AuthNonceGuard(expected_token="trusted"))

    status, payload = router.place_order(
        headers=_headers(1),
        body={
            "account_id": "acc-1",
            "market_id": "KX",
            "side": "buy_yes",
            "price": 45,
            "quantity": 10,
        },
    )

    assert status == 201
    assert payload["contract_version"] == "1.0.0"
    assert payload["data"]["order"]["order_id"] == "o-1"
    assert service.calls == [
        (
            "place_order",
            {
                "market_id": "KX",
                "side": "buy_yes",
                "price": 45,
                "quantity": 10,
                "client_order_id": None,
            },
        )
    ]


def test_auth_nonce_guard_rejects_replayed_nonce() -> None:
    service = StubTradingService()
    router = ApiRouter(service=service, guard=AuthNonceGuard(expected_token="trusted"))

    status1, _ = router.get_balance(headers=_headers(1))
    status2, payload2 = router.get_balance(headers=_headers(1))

    assert status1 == 200
    assert status2 == 401
    assert payload2["error"]["code"] == "PT-AUTH-001"
    assert payload2["error"]["details"]["reason"] == "replayed_nonce"


def test_endpoints_for_cancel_balance_and_bot_control() -> None:
    service = StubTradingService()
    router = ApiRouter(service=service, guard=AuthNonceGuard(expected_token="trusted"))

    cancel_status, cancel_payload = router.cancel_order(headers=_headers(2), body={"order_id": "o-1"})
    balance_status, balance_payload = router.get_balance(headers=_headers(3))
    bot_status, bot_payload = router.bot_control(headers=_headers(4), body={"action": "start"})

    assert cancel_status == 200
    assert cancel_payload["data"]["cancel"]["order_id"] == "o-1"
    assert balance_status == 200
    assert balance_payload["data"]["cash_balance"] == 1200
    assert bot_status == 200
    assert bot_payload["data"]["action"] == "start"
    assert [name for name, _ in service.calls] == ["cancel_order", "get_balance", "control_bot"]


def test_structured_error_payload_aligned_to_catalog() -> None:
    service = StubTradingService()
    service.fail_with = ConnectorError(ConnectorErrorCode.RATE_LIMITED, "too many requests")
    router = ApiRouter(service=service, guard=AuthNonceGuard(expected_token="trusted"))

    status, payload = router.get_balance(headers=_headers(5))

    assert status == 429
    assert payload["error"]["code"] == "PT-HTTP-429"
    assert "Too many requests" in payload["error"]["message"]
