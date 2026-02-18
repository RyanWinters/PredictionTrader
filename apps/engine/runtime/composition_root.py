"""Sidecar startup composition root and lifecycle orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol


class SupportsClose(Protocol):
    def close(self) -> Any: ...


class SupportsAsyncClose(Protocol):
    async def close(self) -> Any: ...


class SupportsStartStop(Protocol):
    async def start(self) -> Any: ...

    async def stop(self) -> Any: ...


class SupportsIntakeStop(Protocol):
    async def stop_intake(self) -> Any: ...


class SupportsFlushQueue(Protocol):
    async def flush_queue(self) -> Any: ...


class SupportsRehydration(Protocol):
    def boot_rehydrate(self) -> Any: ...


class SupportsHealth(Protocol):
    async def healthcheck(self) -> bool: ...


HealthPublisher = Callable[["LifecycleState"], None]


@dataclass(slots=True)
class LifecycleState:
    config_ready: bool = False
    db_ready: bool = False
    connectors_ready: bool = False
    rate_limiter_ready: bool = False
    rest_ready: bool = False
    websocket_ready: bool = False
    rehydrated: bool = False
    consumers_ready: bool = False
    routes_ready: bool = False
    strategy_enabled: bool = False
    execution_enabled: bool = False
    tauri_ready: bool = False
    ui_ready: bool = False
    shutdown_phase: str = "running"
    last_error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "readiness": {
                "tauri": self.tauri_ready,
                "ui": self.ui_ready,
                "strategy": self.strategy_enabled,
                "execution": self.execution_enabled,
            },
            "startup": {
                "config": self.config_ready,
                "db": self.db_ready,
                "connectors": self.connectors_ready,
                "rate_limiter": self.rate_limiter_ready,
                "rest": self.rest_ready,
                "websocket": self.websocket_ready,
                "rehydrated": self.rehydrated,
                "consumers": self.consumers_ready,
                "routes": self.routes_ready,
            },
            "shutdown_phase": self.shutdown_phase,
            "last_error": self.last_error,
        }


@dataclass(slots=True)
class SidecarCompositionRoot:
    """Builds and orchestrates sidecar startup/shutdown dependencies."""

    config_loader: Callable[[], Any]
    db_factory: Callable[[Any], Any]
    connector_factory: Callable[[Any], Any]
    rate_limiter_factory: Callable[[Any], Any]
    rest_service_factory: Callable[[Any], SupportsStartStop]
    websocket_service_factory: Callable[[Any], SupportsStartStop]
    rehydrator_factory: Callable[[Any], SupportsRehydration]
    consumer_starter: Callable[[Any], Awaitable[Any]]
    route_starter: Callable[[Any], Awaitable[Any]]
    health_publisher: HealthPublisher
    dependency_health_checks: list[SupportsHealth] = field(default_factory=list)

    _state: LifecycleState = field(default_factory=LifecycleState, init=False)
    _resolved: dict[str, Any] = field(default_factory=dict, init=False)

    @property
    def state(self) -> LifecycleState:
        return self._state

    async def start(self) -> dict[str, Any]:
        try:
            self._resolved["config"] = self.config_loader()
            self._state.config_ready = True
            self._publish()

            self._resolved["db"] = self.db_factory(self._resolved["config"])
            self._state.db_ready = True
            self._publish()

            self._resolved["connectors"] = self.connector_factory(self._resolved["config"])
            self._state.connectors_ready = True
            self._publish()

            self._resolved["rate_limiter"] = self.rate_limiter_factory(self._resolved["config"])
            self._state.rate_limiter_ready = True
            self._publish()

            self._resolved["rest_service"] = self.rest_service_factory(self._resolved)
            self._state.rest_ready = True
            self._publish()

            self._resolved["websocket_service"] = self.websocket_service_factory(self._resolved)
            self._state.websocket_ready = True
            self._publish()

            rehydrator = self.rehydrator_factory(self._resolved)
            rehydrator.boot_rehydrate()
            self._state.rehydrated = True
            self._state.strategy_enabled = True
            self._state.execution_enabled = True
            self._publish()

            await self._wait_for_dependencies_healthy()

            await self._resolved["rest_service"].start()
            await self._resolved["websocket_service"].start()

            await self.consumer_starter(self._resolved)
            self._state.consumers_ready = True
            self._publish()

            await self.route_starter(self._resolved)
            self._state.routes_ready = True
            self._state.tauri_ready = True
            self._state.ui_ready = True
            self._publish()
            return self._resolved
        except Exception as exc:  # noqa: BLE001
            self._state.last_error = str(exc)
            self._state.tauri_ready = False
            self._state.ui_ready = False
            self._publish()
            raise

    async def shutdown(self) -> None:
        self._state.shutdown_phase = "stop_intake"
        self._publish()
        await self._stop_intake()

        self._state.shutdown_phase = "flush_queue"
        self._publish()
        await self._flush_queue()

        self._state.shutdown_phase = "close_connectors"
        self._publish()
        await self._close_resource(self._resolved.get("connectors"))

        self._state.shutdown_phase = "close_db"
        self._publish()
        await self._close_resource(self._resolved.get("db"))

        await self._stop_service(self._resolved.get("websocket_service"))
        await self._stop_service(self._resolved.get("rest_service"))

        self._state.shutdown_phase = "stopped"
        self._state.tauri_ready = False
        self._state.ui_ready = False
        self._publish()

    async def _wait_for_dependencies_healthy(self) -> None:
        for check in self.dependency_health_checks:
            healthy = await check.healthcheck()
            if not healthy:
                raise RuntimeError("required dependency healthcheck failed")

    async def _stop_intake(self) -> None:
        target = self._resolved.get("connectors")
        stop_intake = getattr(target, "stop_intake", None)
        if callable(stop_intake):
            result = stop_intake()
            if asyncio.iscoroutine(result):
                await result

    async def _flush_queue(self) -> None:
        db = self._resolved.get("db")
        flush_queue = getattr(db, "flush_queue", None)
        if callable(flush_queue):
            result = flush_queue()
            if asyncio.iscoroutine(result):
                await result

    async def _stop_service(self, service: Any) -> None:
        if service is None:
            return
        stop = getattr(service, "stop", None)
        if callable(stop):
            result = stop()
            if asyncio.iscoroutine(result):
                await result

    async def _close_resource(self, resource: Any) -> None:
        if resource is None:
            return
        close = getattr(resource, "close", None)
        if close is None:
            return
        result = close()
        if asyncio.iscoroutine(result):
            await result

    def _publish(self) -> None:
        self.health_publisher(self._state)
