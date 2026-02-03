import asyncio
from dataclasses import dataclass
from datetime import datetime


@dataclass
class BucketMetrics:
    revenue: float = 0.0
    order_count: int = 0
    session_count: int = 0
    checkout_count: int = 0
    purchase_count: int = 0


def minute_bucket(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def hour_bucket(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


class Aggregates:
    def __init__(self) -> None:
        self._minute: dict[datetime, BucketMetrics] = {}
        self._hour: dict[datetime, BucketMetrics] = {}
        self._lock = asyncio.Lock()

    async def add(self, event_time: datetime, delta: BucketMetrics) -> None:
        async with self._lock:
            for bucket, store in (
                (minute_bucket(event_time), self._minute),
                (hour_bucket(event_time), self._hour),
            ):
                metrics = store.setdefault(bucket, BucketMetrics())
                metrics.revenue += delta.revenue
                metrics.order_count += delta.order_count
                metrics.session_count += delta.session_count
                metrics.checkout_count += delta.checkout_count
                metrics.purchase_count += delta.purchase_count

    async def drain(self) -> tuple[dict[datetime, BucketMetrics], dict[datetime, BucketMetrics]]:
        async with self._lock:
            minute = self._minute
            hour = self._hour
            self._minute = {}
            self._hour = {}
            return minute, hour
