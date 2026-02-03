import logging

import uvicorn
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ingest_api.api.ingest import router as ingest_router
from ingest_api.api.kpi import router as kpi_router
from ingest_api.domain.db import create_pool
from ingest_api.settings import get_settings


settings = get_settings()
logger = logging.getLogger("ingest-api")

app = FastAPI(title="KPI Ingestion API", root_path=settings.ROOT_PATH)
allow_credentials = "*" not in settings.ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ingest_router)
app.include_router(kpi_router)


@app.on_event("startup")
async def startup() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    app.state.producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        client_id=settings.KAFKA_CLIENT_ID,
    )
    app.state.db_pool = await create_pool()
    app.state.ingest_counter = 0
    await app.state.producer.start()
    logger.info("Ingest API started")


@app.on_event("shutdown")
async def shutdown() -> None:
    producer: AIOKafkaProducer = app.state.producer
    await producer.stop()
    await app.state.db_pool.close()
    logger.info("Ingest API stopped")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    uvicorn.run(
        "ingest_api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
