import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg
from aiokafka import AIOKafkaConsumer

from stream_processor.domain.repository import flush_kpis, insert_order, insert_session
from stream_processor.services.aggregation import Aggregates, BucketMetrics
from stream_processor.services.dedupe import DedupeCache
from stream_processor.settings import get_settings


logger = logging.getLogger("stream-processor")
settings = get_settings()


def parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


async def process_message(
    msg: Any,
    pool: asyncpg.Pool,
    aggregates: Aggregates,
    dedupe: DedupeCache,
) -> dict[str, Any] | None:
    payload = json.loads(msg.value.decode("utf-8"))
    now = datetime.now(timezone.utc)
    event_id = payload["event_id"]
    if dedupe.seen(event_id, now):
        return None

    payload["event_time"] = parse_dt(payload["event_time"])
    payload["received_at"] = parse_dt(payload["received_at"])
    payload["processed_at"] = now

    async with pool.acquire() as conn:
        if msg.topic == settings.KAFKA_ORDERS_TOPIC:
            inserted = await insert_order(conn, payload)
            if inserted:
                await aggregates.add(
                    payload["event_time"],
                    BucketMetrics(revenue=float(payload["amount"]), order_count=1),
                )
        else:
            inserted = await insert_session(conn, payload)
            if inserted:
                delta = BucketMetrics()
                if payload["event_type"] == "view":
                    delta.session_count = 1
                elif payload["event_type"] == "checkout":
                    delta.checkout_count = 1
                elif payload["event_type"] == "purchase":
                    delta.purchase_count = 1
                await aggregates.add(payload["event_time"], delta)
    if inserted:
        return {
            "event_id": event_id,
            "event_time": payload["event_time"],
            "received_at": payload["received_at"],
            "processed_at": payload["processed_at"],
        }
    return None


async def flush_loop(pool: asyncpg.Pool, aggregates: Aggregates, interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        minute, hour = await aggregates.drain()
        await flush_kpis(pool, minute, hour)


async def run_processor() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    pool = await asyncpg.create_pool(dsn=settings.DB_DSN, min_size=1, max_size=5)
    consumer = AIOKafkaConsumer(
        settings.KAFKA_ORDERS_TOPIC,
        settings.KAFKA_SESSIONS_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_GROUP_ID,
        auto_offset_reset=settings.KAFKA_AUTO_OFFSET_RESET,
        enable_auto_commit=True,
    )
    await consumer.start()

    aggregates = Aggregates()
    dedupe = DedupeCache(settings.DEDUPE_TTL_SECONDS)
    flush_task = asyncio.create_task(
        flush_loop(pool, aggregates, settings.FLUSH_INTERVAL_SECONDS)
    )

    processed = 0
    try:
        async for msg in consumer:
            event_info = await process_message(msg, pool, aggregates, dedupe)
            if event_info:
                processed += 1
                if processed % settings.LOG_EVERY_N == 0:
                    processing_ms = int(
                        (event_info["processed_at"] - event_info["received_at"]).total_seconds()
                        * 1000
                    )
                    logger.info(
                        "Processed %s events (last id=%s, event_time=%s, processing_ms=%s)",
                        processed,
                        event_info["event_id"],
                        event_info["event_time"].isoformat(),
                        processing_ms,
                    )
                if processed % (settings.LOG_EVERY_N * 5) == 0:
                    dedupe.cleanup(datetime.now(timezone.utc))
    finally:
        flush_task.cancel()
        await consumer.stop()
        await pool.close()
