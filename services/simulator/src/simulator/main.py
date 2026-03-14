import asyncio
import logging
import random

import uvicorn

from simulator.api import build_app
from simulator.controller import SimulatorController
from simulator.settings import get_settings

settings = get_settings()
logger = logging.getLogger("simulator")


logging.basicConfig(level=settings.LOG_LEVEL)
if settings.SEED is not None:
    random.seed(settings.SEED)

controller = SimulatorController(settings, logger)
app = build_app(controller, settings, logger)


async def run() -> None:
    config = uvicorn.Config(
        app=app,
        host=settings.CONTROL_API_HOST,
        port=settings.CONTROL_API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
