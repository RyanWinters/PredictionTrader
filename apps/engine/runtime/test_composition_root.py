from __future__ import annotations

import asyncio

from runtime.composition_root import SidecarCompositionRoot


class FakeHealthCheck:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy

    async def healthcheck(self) -> bool:
        return self.healthy


class FakeService:
    def __init__(self, events: list[str], name: str) -> None:
        self._events = events
        self._name = name

    async def start(self) -> None:
        self._events.append(f"{self._name}.start")

    async def stop(self) -> None:
        self._events.append(f"{self._name}.stop")


class FakeDb:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def flush_queue(self) -> None:
        self._events.append("db.flush_queue")

    def close(self) -> None:
        self._events.append("db.close")


class FakeConnectors:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def stop_intake(self) -> None:
        self._events.append("connectors.stop_intake")

    def close(self) -> None:
        self._events.append("connectors.close")


class FakeRehydrator:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def boot_rehydrate(self) -> None:
        self._events.append("rehydrator.boot_rehydrate")


def test_sidecar_startup_orders_rehydration_before_consumers_and_routes() -> None:
    events: list[str] = []
    published: list[dict[str, object]] = []

    async def start_consumers(_: object) -> None:
        events.append("consumers.start")

    async def start_routes(_: object) -> None:
        events.append("routes.start")

    root = SidecarCompositionRoot(
        config_loader=lambda: {"env": "test"},
        db_factory=lambda _: FakeDb(events),
        connector_factory=lambda _: FakeConnectors(events),
        rate_limiter_factory=lambda _: object(),
        rest_service_factory=lambda _: FakeService(events, "rest"),
        websocket_service_factory=lambda _: FakeService(events, "websocket"),
        rehydrator_factory=lambda _: FakeRehydrator(events),
        consumer_starter=start_consumers,
        route_starter=start_routes,
        health_publisher=lambda state: published.append(state.to_payload()),
        dependency_health_checks=[FakeHealthCheck(True)],
    )

    asyncio.run(root.start())

    assert events.index("rehydrator.boot_rehydrate") < events.index("consumers.start")
    assert events.index("consumers.start") < events.index("routes.start")
    assert root.state.strategy_enabled is True
    assert root.state.execution_enabled is True
    assert root.state.tauri_ready is True
    assert root.state.ui_ready is True
    assert published[-1]["readiness"] == {
        "tauri": True,
        "ui": True,
        "strategy": True,
        "execution": True,
    }


def test_sidecar_shutdown_orders_intake_flush_connectors_then_db() -> None:
    events: list[str] = []

    async def noop(_: object) -> None:
        return None

    root = SidecarCompositionRoot(
        config_loader=lambda: {"env": "test"},
        db_factory=lambda _: FakeDb(events),
        connector_factory=lambda _: FakeConnectors(events),
        rate_limiter_factory=lambda _: object(),
        rest_service_factory=lambda _: FakeService(events, "rest"),
        websocket_service_factory=lambda _: FakeService(events, "websocket"),
        rehydrator_factory=lambda _: FakeRehydrator(events),
        consumer_starter=noop,
        route_starter=noop,
        health_publisher=lambda _: None,
        dependency_health_checks=[FakeHealthCheck(True)],
    )

    asyncio.run(root.start())
    asyncio.run(root.shutdown())

    ordered = [
        "connectors.stop_intake",
        "db.flush_queue",
        "connectors.close",
        "db.close",
    ]
    last_idx = -1
    for item in ordered:
        idx = events.index(item)
        assert idx > last_idx
        last_idx = idx


def test_sidecar_does_not_start_routes_if_dependency_health_fails() -> None:
    events: list[str] = []

    async def start_consumers(_: object) -> None:
        events.append("consumers.start")

    async def start_routes(_: object) -> None:
        events.append("routes.start")

    root = SidecarCompositionRoot(
        config_loader=lambda: {"env": "test"},
        db_factory=lambda _: FakeDb(events),
        connector_factory=lambda _: FakeConnectors(events),
        rate_limiter_factory=lambda _: object(),
        rest_service_factory=lambda _: FakeService(events, "rest"),
        websocket_service_factory=lambda _: FakeService(events, "websocket"),
        rehydrator_factory=lambda _: FakeRehydrator(events),
        consumer_starter=start_consumers,
        route_starter=start_routes,
        health_publisher=lambda _: None,
        dependency_health_checks=[FakeHealthCheck(False)],
    )

    try:
        asyncio.run(root.start())
    except RuntimeError as exc:
        assert "healthcheck failed" in str(exc)
    else:
        raise AssertionError("expected healthcheck failure")

    assert "consumers.start" not in events
    assert "routes.start" not in events
