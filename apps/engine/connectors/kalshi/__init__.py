"""Kalshi connector package."""

from .bus import InMemoryEventBus
from .client import KalshiAuthSigner, KalshiClient, KalshiSessionFactory
from .config import KalshiConfig, RetryConfig
from .dependencies import KalshiDependencies, build_kalshi_dependencies
from .errors import ConnectorError, ConnectorErrorCode, map_kalshi_error

__all__ = [
    "ConnectorError",
    "ConnectorErrorCode",
    "InMemoryEventBus",
    "KalshiAuthSigner",
    "KalshiClient",
    "KalshiConfig",
    "KalshiDependencies",
    "KalshiSessionFactory",
    "RetryConfig",
    "build_kalshi_dependencies",
    "map_kalshi_error",
]
