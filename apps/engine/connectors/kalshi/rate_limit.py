"""Shared process-level rate limiter for Kalshi control paths."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .config import RateLimitConfig

logger = logging.getLogger(__name__)


class RateLimitBucket(str, Enum):
    READ = "read"
    WRITE = "write"


class RateLimitExceededError(Exception):
    """Raised when queued waiting exceeds configured timeout."""

    def __init__(self, *, bucket: RateLimitBucket, timeout_seconds: float):
        message = f"Rate limit exceeded for {bucket.value} bucket after waiting {timeout_seconds:.3f}s"
        super().__init__(message)
        self.bucket = bucket
        self.timeout_seconds = timeout_seconds
        self.status_code = 429


@dataclass
class RateLimitMetrics:
    throttled_requests: int = 0
    dropped_requests: int = 0


class _SlidingWindowBucket:
    def __init__(self, name: RateLimitBucket, *, requests_per_second: float):
        self._name = name
        self._requests_per_second = requests_per_second
        self._events: deque[float] = deque()

    def configure(self, requests_per_second: float) -> None:
        self._requests_per_second = requests_per_second

    def reserve_delay(self, now: float) -> float:
        self._evict_old(now)
        if self._requests_per_second <= 0:
            return float("inf")

        capacity = max(1, int(self._requests_per_second))
        if len(self._events) < capacity:
            self._events.append(now)
            return 0.0

        oldest = self._events[0]
        wait_for = max(0.0, (oldest + 1.0) - now)
        if wait_for <= 0:
            self._events.popleft()
            self._events.append(now)
            return 0.0
        return wait_for

    def commit_after_wait(self, now: float) -> None:
        self._evict_old(now)
        self._events.append(now)

    def _evict_old(self, now: float) -> None:
        while self._events and now - self._events[0] >= 1.0:
            self._events.popleft()


class SharedRateLimiter:
    """Thread-safe limiter shared by all connector clients in-process."""

    def __init__(self, config: RateLimitConfig):
        self._lock = threading.Lock()
        self._config = config
        self._metrics = RateLimitMetrics()
        self._buckets = {
            RateLimitBucket.READ: _SlidingWindowBucket(
                RateLimitBucket.READ,
                requests_per_second=config.read_requests_per_second,
            ),
            RateLimitBucket.WRITE: _SlidingWindowBucket(
                RateLimitBucket.WRITE,
                requests_per_second=config.write_requests_per_second,
            ),
        }

    def configure(self, config: RateLimitConfig) -> None:
        with self._lock:
            self._config = config
            self._buckets[RateLimitBucket.READ].configure(config.read_requests_per_second)
            self._buckets[RateLimitBucket.WRITE].configure(config.write_requests_per_second)

    def acquire(self, bucket: RateLimitBucket, *, operation: str) -> None:
        self._acquire_with_sleep(bucket, operation=operation, sleeper=time.sleep)

    async def acquire_async(self, bucket: RateLimitBucket, *, operation: str) -> None:
        await self._acquire_with_async_sleep(bucket, operation=operation)

    def metrics_snapshot(self) -> RateLimitMetrics:
        with self._lock:
            return RateLimitMetrics(
                throttled_requests=self._metrics.throttled_requests,
                dropped_requests=self._metrics.dropped_requests,
            )

    def _acquire_with_sleep(self, bucket: RateLimitBucket, *, operation: str, sleeper: Callable[[float], None]) -> None:
        timeout = self._config.wait_timeout_seconds
        while True:
            with self._lock:
                now = time.monotonic()
                wait_for = self._buckets[bucket].reserve_delay(now)
                if wait_for == 0:
                    return

                if wait_for > timeout:
                    self._metrics.dropped_requests += 1
                    logger.warning(
                        "kalshi_rate_limit_dropped",
                        extra={"event": "rate_limit_dropped", "bucket": bucket.value, "operation": operation, "wait_seconds": wait_for},
                    )
                    raise RateLimitExceededError(bucket=bucket, timeout_seconds=timeout)

                self._metrics.throttled_requests += 1
                logger.info(
                    "kalshi_rate_limit_throttled",
                    extra={"event": "rate_limit_throttled", "bucket": bucket.value, "operation": operation, "wait_seconds": wait_for},
                )
            sleeper(wait_for)
            with self._lock:
                self._buckets[bucket].commit_after_wait(time.monotonic())
                return

    async def _acquire_with_async_sleep(self, bucket: RateLimitBucket, *, operation: str) -> None:
        timeout = self._config.wait_timeout_seconds
        while True:
            with self._lock:
                now = time.monotonic()
                wait_for = self._buckets[bucket].reserve_delay(now)
                if wait_for == 0:
                    return

                if wait_for > timeout:
                    self._metrics.dropped_requests += 1
                    logger.warning(
                        "kalshi_rate_limit_dropped",
                        extra={"event": "rate_limit_dropped", "bucket": bucket.value, "operation": operation, "wait_seconds": wait_for},
                    )
                    raise RateLimitExceededError(bucket=bucket, timeout_seconds=timeout)

                self._metrics.throttled_requests += 1
                logger.info(
                    "kalshi_rate_limit_throttled",
                    extra={"event": "rate_limit_throttled", "bucket": bucket.value, "operation": operation, "wait_seconds": wait_for},
                )
            await asyncio.sleep(wait_for)
            with self._lock:
                self._buckets[bucket].commit_after_wait(time.monotonic())
                return


_SHARED_LIMITER: SharedRateLimiter | None = None
_SHARED_LIMITER_LOCK = threading.Lock()


def get_shared_rate_limiter(config: RateLimitConfig) -> SharedRateLimiter:
    global _SHARED_LIMITER
    with _SHARED_LIMITER_LOCK:
        if _SHARED_LIMITER is None:
            _SHARED_LIMITER = SharedRateLimiter(config)
        else:
            _SHARED_LIMITER.configure(config)
        return _SHARED_LIMITER
