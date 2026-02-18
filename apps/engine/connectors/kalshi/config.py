"""Configuration model for Kalshi connectors."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class RetryConfig:
    """Retry controls for HTTP and websocket calls."""

    max_attempts: int = 3
    backoff_seconds: float = 0.5


@dataclass(frozen=True)
class StreamReconnectConfig:
    """Reconnect controls for websocket market data streaming."""

    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 10.0
    jitter_ratio: float = 0.2
    max_retry_window_seconds: float = 120.0
    stable_connect_seconds: float = 30.0
    degraded_after_attempts: int = 2


@dataclass(frozen=True)
class KalshiConfig:
    """Centralized connector configuration."""

    base_url: str = "https://trading-api.kalshi.com/trade-api/v2"
    websocket_url: str = "wss://trading-api.kalshi.com/trade-api/ws/v2"
    api_key_id: str = ""
    api_key_secret: str = ""
    timeout_seconds: float = 10.0
    retry: RetryConfig = RetryConfig()
    stream_reconnect: StreamReconnectConfig = StreamReconnectConfig()

    @classmethod
    def from_env(cls) -> "KalshiConfig":
        """Build config from environment variables."""

        return cls(
            base_url=getenv("KALSHI_BASE_URL", cls.base_url),
            websocket_url=getenv("KALSHI_WEBSOCKET_URL", cls.websocket_url),
            api_key_id=getenv("KALSHI_API_KEY_ID", ""),
            api_key_secret=getenv("KALSHI_API_KEY_SECRET", ""),
            timeout_seconds=float(getenv("KALSHI_TIMEOUT_SECONDS", "10.0")),
            retry=RetryConfig(
                max_attempts=int(getenv("KALSHI_RETRY_MAX_ATTEMPTS", "3")),
                backoff_seconds=float(getenv("KALSHI_RETRY_BACKOFF_SECONDS", "0.5")),
            ),
            stream_reconnect=StreamReconnectConfig(
                base_backoff_seconds=float(getenv("KALSHI_STREAM_RETRY_BASE_BACKOFF_SECONDS", "0.5")),
                max_backoff_seconds=float(getenv("KALSHI_STREAM_RETRY_MAX_BACKOFF_SECONDS", "10.0")),
                jitter_ratio=float(getenv("KALSHI_STREAM_RETRY_JITTER_RATIO", "0.2")),
                max_retry_window_seconds=float(getenv("KALSHI_STREAM_RETRY_MAX_WINDOW_SECONDS", "120.0")),
                stable_connect_seconds=float(getenv("KALSHI_STREAM_RETRY_STABLE_CONNECT_SECONDS", "30.0")),
                degraded_after_attempts=int(getenv("KALSHI_STREAM_RETRY_DEGRADED_AFTER_ATTEMPTS", "2")),
            ),
        )
