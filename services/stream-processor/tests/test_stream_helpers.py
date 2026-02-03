import asyncio
from datetime import datetime, timezone

from stream_processor.services.aggregation import (
    Aggregates,
    BucketMetrics,
    hour_bucket,
    minute_bucket,
)
from stream_processor.services.dedupe import DedupeCache


def test_dedupe_cache() -> None:
    cache = DedupeCache(ttl_seconds=60)
    now = datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc)

    assert cache.seen("id-1", now) is False
    assert cache.seen("id-1", now) is True

    cache.cleanup(now)
    assert cache.seen("id-2", now) is False


def test_bucket_functions() -> None:
    ts = datetime(2026, 2, 3, 10, 15, 45, 123456, tzinfo=timezone.utc)
    assert minute_bucket(ts) == datetime(2026, 2, 3, 10, 15, tzinfo=timezone.utc)
    assert hour_bucket(ts) == datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc)


def test_aggregates_add_and_drain() -> None:
    aggregates = Aggregates()
    ts = datetime(2026, 2, 3, 10, 0, 5, tzinfo=timezone.utc)

    async def run() -> None:
        await aggregates.add(ts, BucketMetrics(revenue=10.0, order_count=1))
        minute, hour = await aggregates.drain()
        assert len(minute) == 1
        assert len(hour) == 1
        minute_metrics = list(minute.values())[0]
        assert minute_metrics.revenue == 10.0
        assert minute_metrics.order_count == 1

    asyncio.run(run())
