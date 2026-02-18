"""Dependency injection entry points for Kalshi connector interfaces."""

from __future__ import annotations

from dataclasses import dataclass

from .bus import InMemoryEventBus
from .client import KalshiAuthSigner, KalshiClient, KalshiSessionFactory
from .config import KalshiConfig
from .interfaces import AccountReadClient, MarketDataStream, OrderExecutionClient


@dataclass(frozen=True)
class KalshiDependencies:
    """Container exposing interface-typed connector dependencies."""

    market_data: MarketDataStream
    orders: OrderExecutionClient
    account: AccountReadClient


def build_kalshi_dependencies(config: KalshiConfig | None = None) -> KalshiDependencies:
    """Build the default dependency graph for Kalshi integrations."""

    resolved_config = config or KalshiConfig.from_env()
    signer = KalshiAuthSigner(
        api_key_id=resolved_config.api_key_id,
        api_key_secret=resolved_config.api_key_secret,
    )
    session = KalshiSessionFactory(resolved_config).create_http_session()
    client = KalshiClient(
        config=resolved_config,
        auth_signer=signer,
        session=session,
        event_publisher=InMemoryEventBus(),
    )

    return KalshiDependencies(market_data=client, orders=client, account=client)
