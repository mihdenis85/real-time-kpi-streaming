import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader

from simulator.controller import SimulatorController
from simulator.settings import Settings


def build_app(
    controller: SimulatorController, settings: Settings, logger: logging.Logger
) -> FastAPI:
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def require_api_key(api_key: str | None = Depends(api_key_header)) -> None:
        if api_key != settings.API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

    app = FastAPI(
        title="simulator-control",
        version=settings.VERSION,
        dependencies=[Depends(require_api_key)],
    )

    @app.on_event("startup")
    async def on_startup() -> None:
        if settings.ENABLED:
            await controller.start()
            logger.info("Simulator autostart enabled")
        else:
            logger.info("Simulator autostart disabled")

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await controller.stop()

    @app.get("/health")
    async def health() -> dict[str, str | bool]:
        return {"status": "ok", "running": controller.is_running()}

    @app.get("/simulator/status")
    async def simulator_status() -> dict[str, bool]:
        return {"running": controller.is_running()}

    @app.post("/simulator/start")
    async def simulator_start() -> dict[str, str | bool]:
        started = await controller.start()
        return {
            "running": controller.is_running(),
            "status": "started" if started else "already_running",
        }

    @app.post("/simulator/stop")
    async def simulator_stop() -> dict[str, str | bool]:
        stopped = await controller.stop()
        return {
            "running": controller.is_running(),
            "status": "stopped" if stopped else "already_stopped",
        }

    return app
