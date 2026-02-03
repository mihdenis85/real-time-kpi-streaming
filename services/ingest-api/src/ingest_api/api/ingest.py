import json
import logging

from aiokafka import AIOKafkaProducer
from fastapi import APIRouter, HTTPException, Request

from ingest_api.api.schemas import IngestResponse, OrderEvent, SessionEvent
from ingest_api.services.ingest_service import make_event_id, to_payload
from ingest_api.settings import get_settings

router = APIRouter(tags=["ingest"])
settings = get_settings()
logger = logging.getLogger("ingest-api")


async def _publish(
    producer: AIOKafkaProducer, topic: str, event_id: str, payload: dict[str, object]
) -> None:
    await producer.send_and_wait(
        topic,
        json.dumps(payload).encode("utf-8"),
        key=event_id.encode("utf-8"),
    )


@router.post("/events/order", response_model=IngestResponse)
async def ingest_order(event: OrderEvent, request: Request) -> IngestResponse:
    producer: AIOKafkaProducer = request.app.state.producer
    event_id = event.event_id or event.order_id
    payload = to_payload(event, event_id)
    try:
        await _publish(producer, settings.KAFKA_ORDERS_TOPIC, event_id, payload)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Kafka publish failed") from exc
    request.app.state.ingest_counter += 1
    if request.app.state.ingest_counter % settings.LOG_EVERY_N == 0:
        logger.info("Accepted %s events", request.app.state.ingest_counter)
    return IngestResponse(status="accepted", event_id=event_id)


@router.post("/events/session", response_model=IngestResponse)
async def ingest_session(event: SessionEvent, request: Request) -> IngestResponse:
    producer: AIOKafkaProducer = request.app.state.producer
    event_id = event.event_id or make_event_id(
        "session", f"{event.session_id}:{event.event_type}", event.event_time
    )
    payload = to_payload(event, event_id)
    try:
        await _publish(producer, settings.KAFKA_SESSIONS_TOPIC, event_id, payload)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Kafka publish failed") from exc
    request.app.state.ingest_counter += 1
    if request.app.state.ingest_counter % settings.LOG_EVERY_N == 0:
        logger.info("Accepted %s events", request.app.state.ingest_counter)
    return IngestResponse(status="accepted", event_id=event_id)
