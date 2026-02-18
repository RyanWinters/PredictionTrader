"""Websocket routing primitives for streaming UI-facing normalized events."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

_EVENT_TOPICS = {"market", "order", "position", "risk_alert"}


class WebSocketClient(Protocol):
    """Framework adapter contract for websocket clients."""

    def send_json(self, payload: Mapping[str, Any]) -> None:
        """Send a JSON frame to the connected client."""

    def send_ping(self) -> None:
        """Send a websocket ping frame."""

    def close(self, *, code: int, reason: str) -> None:
        """Close the websocket connection."""


@dataclass
class UiEvent:
    """Normalized event contract streamed to UI subscribers."""

    topic: str
    payload: Mapping[str, Any]
    timestamp: str
    critical: bool = False

    @classmethod
    def from_mapping(cls, raw_event: Mapping[str, Any]) -> "UiEvent":
        topic = cls._normalize_topic(raw_event)
        payload = raw_event.get("payload")
        if not isinstance(payload, Mapping):
            payload = raw_event
        timestamp = cls._normalize_timestamp(raw_event)
        critical = topic == "risk_alert" and bool(raw_event.get("critical") or payload.get("critical"))
        return cls(topic=topic, payload=dict(payload), timestamp=timestamp, critical=critical)

    def to_frame(self) -> dict[str, Any]:
        return {
            "type": "event",
            "topic": self.topic,
            "timestamp": self.timestamp,
            "critical": self.critical,
            "payload": dict(self.payload),
        }

    @staticmethod
    def _normalize_topic(raw_event: Mapping[str, Any]) -> str:
        topic = str(raw_event.get("topic") or raw_event.get("category") or raw_event.get("stream") or "").lower()
        if topic in _EVENT_TOPICS:
            return topic

        schema = str(raw_event.get("schema") or "").lower()
        if schema in {"orderbook_delta", "trade", "market"}:
            return "market"
        if schema in {"order", "order_update", "orders"}:
            return "order"
        if schema in {"position", "positions"}:
            return "position"
        if schema in {"risk_alert", "risk"}:
            return "risk_alert"

        raise ValueError("Unable to determine websocket event topic")

    @staticmethod
    def _normalize_timestamp(raw_event: Mapping[str, Any]) -> str:
        candidate = raw_event.get("timestamp") or raw_event.get("updated_at")
        if candidate is None and isinstance(raw_event.get("payload"), Mapping):
            candidate = raw_event["payload"].get("timestamp")
        if candidate is None:
            return datetime.now(UTC).isoformat().replace("+00:00", "Z")

        if isinstance(candidate, str):
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")

        epoch_seconds = float(candidate)
        if epoch_seconds > 1_000_000_000_000:
            epoch_seconds = epoch_seconds / 1000.0
        return datetime.fromtimestamp(epoch_seconds, tz=UTC).isoformat().replace("+00:00", "Z")


@dataclass
class _ClientState:
    client: WebSocketClient
    subscriptions: set[str]
    queue: deque[UiEvent] = field(default_factory=deque)
    dropped_non_critical: int = 0
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_ping_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ApiWebSocketConnectionManager:
    """Manages websocket clients with subscriptions, fanout, and liveness controls."""

    def __init__(
        self,
        *,
        max_queue_size: int = 128,
        heartbeat_interval: timedelta = timedelta(seconds=15),
        stale_timeout: timedelta = timedelta(seconds=45),
    ):
        self._max_queue_size = max_queue_size
        self._heartbeat_interval = heartbeat_interval
        self._stale_timeout = stale_timeout
        self._clients: dict[str, _ClientState] = {}

    def connect(self, *, client_id: str, client: WebSocketClient, subscriptions: Iterable[str] | None = None) -> None:
        requested = set(subscriptions or _EVENT_TOPICS)
        self._clients[client_id] = _ClientState(client=client, subscriptions=self._sanitize_topics(requested))

    def disconnect(self, *, client_id: str, code: int = 1000, reason: str = "client_disconnect") -> None:
        state = self._clients.pop(client_id, None)
        if state is not None:
            state.client.close(code=code, reason=reason)

    def subscribe(self, *, client_id: str, topics: Iterable[str]) -> set[str]:
        state = self._clients[client_id]
        state.subscriptions.update(self._sanitize_topics(topics))
        state.last_seen_at = datetime.now(UTC)
        return set(state.subscriptions)

    def unsubscribe(self, *, client_id: str, topics: Iterable[str]) -> set[str]:
        state = self._clients[client_id]
        state.subscriptions.difference_update(self._sanitize_topics(topics))
        state.last_seen_at = datetime.now(UTC)
        return set(state.subscriptions)

    def mark_client_alive(self, *, client_id: str, at: datetime | None = None) -> None:
        state = self._clients.get(client_id)
        if state is not None:
            state.last_seen_at = at or datetime.now(UTC)

    def stream_event(self, raw_event: Mapping[str, Any]) -> None:
        event = UiEvent.from_mapping(raw_event)
        for state in self._clients.values():
            if event.topic not in state.subscriptions:
                continue
            self._enqueue_event(state=state, event=event)

    def flush(self, *, client_id: str, max_messages: int | None = None) -> int:
        state = self._clients[client_id]
        sent = 0
        limit = max_messages if max_messages is not None else len(state.queue)
        while sent < limit and state.queue:
            event = state.queue.popleft()
            state.client.send_json(event.to_frame())
            sent += 1
        state.last_seen_at = datetime.now(UTC)
        return sent

    def flush_all(self, *, max_messages_per_client: int | None = None) -> dict[str, int]:
        sent_counts: dict[str, int] = {}
        for client_id in list(self._clients.keys()):
            sent_counts[client_id] = self.flush(client_id=client_id, max_messages=max_messages_per_client)
        return sent_counts

    def heartbeat(self, *, at: datetime | None = None) -> list[str]:
        now = at or datetime.now(UTC)
        pinged: list[str] = []
        for client_id, state in self._clients.items():
            if now - state.last_ping_at >= self._heartbeat_interval:
                state.client.send_ping()
                state.last_ping_at = now
                pinged.append(client_id)
        return pinged

    def disconnect_stale_clients(self, *, at: datetime | None = None) -> list[str]:
        now = at or datetime.now(UTC)
        disconnected: list[str] = []
        for client_id, state in list(self._clients.items()):
            if now - state.last_seen_at > self._stale_timeout:
                disconnected.append(client_id)
                self.disconnect(client_id=client_id, code=1001, reason="stale_client")
        return disconnected

    def get_client_stats(self, *, client_id: str) -> dict[str, Any]:
        state = self._clients[client_id]
        return {
            "subscriptions": sorted(state.subscriptions),
            "queued": len(state.queue),
            "dropped_non_critical": state.dropped_non_critical,
            "last_seen_at": state.last_seen_at.isoformat(),
            "last_ping_at": state.last_ping_at.isoformat(),
        }

    @staticmethod
    def _sanitize_topics(topics: Iterable[str]) -> set[str]:
        normalized = {str(topic).lower() for topic in topics}
        invalid = normalized - _EVENT_TOPICS
        if invalid:
            raise ValueError(f"Unsupported websocket topics: {sorted(invalid)}")
        return normalized

    def _enqueue_event(self, *, state: _ClientState, event: UiEvent) -> None:
        if len(state.queue) < self._max_queue_size:
            state.queue.append(event)
            return

        if event.critical:
            for queued in list(state.queue):
                if not queued.critical:
                    state.queue.remove(queued)
                    state.dropped_non_critical += 1
                    state.queue.append(event)
                    return
            state.queue.popleft()
            state.queue.append(event)
            return

        state.dropped_non_critical += 1
