"""Internal event bus primitives for connector fan-out."""

from __future__ import annotations

from asyncio import Queue
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .interfaces import EventPublisher


@dataclass
class InMemoryEventBus(EventPublisher):
    """Simple async queue-backed publisher used by the engine runtime."""

    queue: Queue[dict[str, Any]] = field(default_factory=Queue)

    async def publish(self, event: Mapping[str, Any]) -> None:
        await self.queue.put(dict(event))

