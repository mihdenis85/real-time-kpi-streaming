import asyncio

from stream_processor.services.processor import run_processor


def main() -> None:
    asyncio.run(run_processor())


if __name__ == "__main__":
    main()
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from aiokafka import AIOKafkaConsumer

from stream_processor.settings import get_settings

logger = logging.getLogger("stream-processor")
settings = get_settings()


def _parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _minute_bucket(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _hour_bucket(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


class DedupeCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._items: dict[str, datetime] = {}

    def seen(self, key: str, now: datetime) -> bool:
        expiry = self._items.get(key)
        if expiry and expiry > now:
            return True
        self._items[key] = now + self.ttl
        return False

    def cleanup(self, now: datetime) -> None:
        expired = [key for key, expiry in self._items.items() if expiry <= now]
        for key in expired:
            self._items.pop(key, None)


@dataclass
class BucketMetrics:
    revenue: float = 0.0
    order_count: int = 0
    session_count: int = 0
    checkout_count: int = 0
    purchase_count: int = 0


class Aggregates:
    def __init__(self) -> None:
        self._minute: dict[datetime, BucketMetrics] = {}
        self._hour: dict[datetime, BucketMetrics] = {}
        self._lock = asyncio.Lock()

    async def add(self, event_time: datetime, delta: BucketMetrics) -> None:
        async with self._lock:
            for bucket, store in (
                (_minute_bucket(event_time), self._minute),
                (_hour_bucket(event_time), self._hour),
            ):
                metrics = store.setdefault(bucket, BucketMetrics())
                metrics.revenue += delta.revenue
                metrics.order_count += delta.order_count
                metrics.session_count += delta.session_count
                metrics.checkout_count += delta.checkout_count
                metrics.purchase_count += delta.purchase_count

    async def drain(
        self,
    ) -> tuple[dict[datetime, BucketMetrics], dict[datetime, BucketMetrics]]:
        async with self._lock:
            minute = self._minute
            hour = self._hour
            self._minute = {}
            self._hour = {}
            return minute, hour


async def _insert_order(conn: asyncpg.Connection, payload: dict[str, Any]) -> bool:
    row = await conn.fetchrow(
        """
        INSERT INTO orders (
            order_id,
            customer_id,
            amount,
            currency,
            channel,
            event_time,
            received_at,
            processed_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (order_id) DO NOTHING
        RETURNING order_id
        """,
        payload["order_id"],
        payload.get("customer_id"),
        float(payload["amount"]),
        payload.get("currency", "USD"),
        payload.get("channel"),
        payload["event_time"],
        payload["received_at"],
        payload["processed_at"],
    )
    return row is not None


async def _insert_session(conn: asyncpg.Connection, payload: dict[str, Any]) -> bool:
    row = await conn.fetchrow(
        """
        INSERT INTO sessions (
            event_id,
            session_id,
            event_type,
            user_id,
            channel,
            event_time,
            received_at,
            processed_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (event_id) DO NOTHING
        RETURNING event_id
        """,
        payload["event_id"],
        payload["session_id"],
        payload["event_type"],
        payload.get("user_id"),
        payload.get("channel"),
        payload["event_time"],
        payload["received_at"],
        payload["processed_at"],
    )
    return row is not None


async def _flush_kpis(
    pool: asyncpg.Pool,
    minute: dict[datetime, BucketMetrics],
    hour: dict[datetime, BucketMetrics],
) -> None:
    if not minute and not hour:
        return

    async with pool.acquire() as conn:
        if minute:
            rows = [
                (
                    bucket,
                    metrics.revenue,
                    metrics.order_count,
                    metrics.session_count,
                    metrics.checkout_count,
                    metrics.purchase_count,
                )
                for bucket, metrics in minute.items()
            ]
            await conn.executemany(
                """
                INSERT INTO kpi_minute (
                    bucket,
                    revenue,
                    order_count,
                    session_count,
                    checkout_count,
                    purchase_count
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (bucket) DO UPDATE SET
                    revenue = kpi_minute.revenue + EXCLUDED.revenue,
                    order_count = kpi_minute.order_count + EXCLUDED.order_count,
                    session_count = kpi_minute.session_count + EXCLUDED.session_count,
                    checkout_count = kpi_minute.checkout_count + EXCLUDED.checkout_count,
                    purchase_count = kpi_minute.purchase_count + EXCLUDED.purchase_count,
                    updated_at = NOW()
                """,
                rows,
            )
        if hour:
            rows = [
                (
                    bucket,
                    metrics.revenue,
                    metrics.order_count,
                    metrics.session_count,
                    metrics.checkout_count,
                    metrics.purchase_count,
                )
                for bucket, metrics in hour.items()
            ]
            await conn.executemany(
                """
                INSERT INTO kpi_hour (
                    bucket,
                    revenue,
                    order_count,
                    session_count,
                    checkout_count,
                    purchase_count
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (bucket) DO UPDATE SET
                    revenue = kpi_hour.revenue + EXCLUDED.revenue,
                    order_count = kpi_hour.order_count + EXCLUDED.order_count,
                    session_count = kpi_hour.session_count + EXCLUDED.session_count,
                    checkout_count = kpi_hour.checkout_count + EXCLUDED.checkout_count,
                    purchase_count = kpi_hour.purchase_count + EXCLUDED.purchase_count,
                    updated_at = NOW()
                """,
                rows,
            )


async def _process_message(
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

    payload["event_time"] = _parse_dt(payload["event_time"])
    payload["received_at"] = _parse_dt(payload["received_at"])
    payload["processed_at"] = now

    async with pool.acquire() as conn:
        if msg.topic == settings.KAFKA_ORDERS_TOPIC:
            inserted = await _insert_order(conn, payload)
            if inserted:
                await aggregates.add(
                    payload["event_time"],
                    BucketMetrics(revenue=float(payload["amount"]), order_count=1),
                )
        else:
            inserted = await _insert_session(conn, payload)
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


async def _flush_loop(
    pool: asyncpg.Pool, aggregates: Aggregates, interval: int
) -> None:
    while True:
        await asyncio.sleep(interval)
        minute, hour = await aggregates.drain()
        await _flush_kpis(pool, minute, hour)


async def run() -> None:
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
        _flush_loop(pool, aggregates, settings.FLUSH_INTERVAL_SECONDS)
    )

    processed = 0
    try:
        async for msg in consumer:
            event_info = await _process_message(msg, pool, aggregates, dedupe)
            if event_info:
                processed += 1
                if processed % settings.LOG_EVERY_N == 0:
                    processing_ms = int(
                        (
                            event_info["processed_at"] - event_info["received_at"]
                        ).total_seconds()
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


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
