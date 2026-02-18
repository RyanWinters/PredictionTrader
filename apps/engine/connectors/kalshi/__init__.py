"""Kalshi connector package."""

from .bus import InMemoryEventBus
from .client import KalshiAuthSigner, KalshiClient, KalshiSessionFactory
from .config import KalshiConfig, RetryConfig
from .dependencies import KalshiDependencies, build_kalshi_dependencies
from .errors import ConnectorError, ConnectorErrorCode, map_kalshi_error
from .models import (
    CancelOrderResponse,
    OrderAction,
    OrderDetails,
    OrderLifecycleStatus,
    OrderSide,
    OrderType,
    PlaceOrderRequest,
    PlaceOrderResponse,
    PortfolioBalance,
)

__all__ = [
    "ConnectorError",
    "ConnectorErrorCode",
    "CancelOrderResponse",
    "InMemoryEventBus",
    "KalshiAuthSigner",
    "KalshiClient",
    "KalshiConfig",
    "KalshiDependencies",
    "KalshiSessionFactory",
    "OrderAction",
    "OrderDetails",
    "OrderLifecycleStatus",
    "OrderSide",
    "OrderType",
    "PlaceOrderRequest",
    "PlaceOrderResponse",
    "PortfolioBalance",
    "RetryConfig",
    "build_kalshi_dependencies",
    "map_kalshi_error",
]
