import asyncio
import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient
from simulator.api import build_app
from simulator.controller import SimulatorController


def test_controller_start_stop_idempotent(monkeypatch) -> None:
    settings = SimpleNamespace()
    logger = logging.getLogger("test-simulator")
    controller = SimulatorController(settings=settings, logger=logger)

    async def fake_run_loop(self) -> None:
        while True:
            await asyncio.sleep(1)

    monkeypatch.setattr(SimulatorController, "_run_loop", fake_run_loop)

    async def run() -> None:
        assert await controller.start() is True
        assert controller.is_running() is True
        assert await controller.start() is False
        assert await controller.stop() is True
        assert controller.is_running() is False
        assert await controller.stop() is False

    asyncio.run(run())


class _FakeController:
    def __init__(self) -> None:
        self.running = False
        self.start_calls = 0
        self.stop_calls = 0

    def is_running(self) -> bool:
        return self.running

    async def start(self) -> bool:
        self.start_calls += 1
        if self.running:
            return False
        self.running = True
        return True

    async def stop(self) -> bool:
        self.stop_calls += 1
        if not self.running:
            return False
        self.running = False
        return True


def test_simulator_api_requires_api_key() -> None:
    controller = _FakeController()
    settings = SimpleNamespace(VERSION="0.1.0", API_KEY="dev-key", ENABLED=False)
    app = build_app(
        controller=controller, settings=settings, logger=logging.getLogger("test")
    )

    with TestClient(app) as client:
        response = client.get("/simulator/status")
        assert response.status_code == 401

        response = client.get("/simulator/status", headers={"X-API-Key": "dev-key"})
        assert response.status_code == 200
        assert response.json() == {"running": False}


def test_simulator_api_start_stop_flow() -> None:
    controller = _FakeController()
    settings = SimpleNamespace(VERSION="0.1.0", API_KEY="dev-key", ENABLED=False)
    app = build_app(
        controller=controller, settings=settings, logger=logging.getLogger("test")
    )
    headers = {"X-API-Key": "dev-key"}

    with TestClient(app) as client:
        start_resp = client.post("/simulator/start", headers=headers)
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "started"

        start_again = client.post("/simulator/start", headers=headers)
        assert start_again.status_code == 200
        assert start_again.json()["status"] == "already_running"

        stop_resp = client.post("/simulator/stop", headers=headers)
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "stopped"


def test_simulator_api_autostarts_when_enabled_and_stops_on_shutdown() -> None:
    controller = _FakeController()
    settings = SimpleNamespace(VERSION="0.1.0", API_KEY="dev-key", ENABLED=True)
    app = build_app(
        controller=controller, settings=settings, logger=logging.getLogger("test")
    )

    with TestClient(app):
        assert controller.start_calls == 1
        assert controller.running is True

    assert controller.stop_calls >= 1
