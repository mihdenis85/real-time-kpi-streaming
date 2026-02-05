from datetime import datetime, timezone

import asyncpg

from ingest_api.api.schemas import (
    AlertItem,
    FreshnessResponse,
    KpiPoint,
    TimeToSignalItem,
)
from ingest_api.domain.kpi_repository import (
    fetch_alerts_rows,
    fetch_freshness,
    fetch_latest_row,
    fetch_range_rows,
    fetch_time_to_signal,
)


async def fetch_series(
    pool: asyncpg.Pool,
    bucket: str,
    from_ts: datetime,
    to_ts: datetime,
    limit: int,
    channel: str | None = None,
    campaign: str | None = None,
) -> list[KpiPoint]:
    rows = await fetch_range_rows(
        pool, bucket, from_ts, to_ts, limit, channel, campaign
    )
    return [KpiPoint(**row) for row in rows]


async def fetch_latest_kpi(
    pool: asyncpg.Pool,
    bucket: str,
    channel: str | None = None,
    campaign: str | None = None,
) -> KpiPoint | None:
    row = await fetch_latest_row(pool, bucket, channel, campaign)
    if row is None:
        return None
    return KpiPoint(**row)


async def fetch_alerts(
    pool: asyncpg.Pool, from_ts: datetime, to_ts: datetime, limit: int
) -> list[AlertItem]:
    rows = await fetch_alerts_rows(pool, from_ts, to_ts, limit)
    return [AlertItem(**row) for row in rows]


async def fetch_freshness_info(
    pool: asyncpg.Pool, channel: str | None = None, campaign: str | None = None
) -> FreshnessResponse:
    row = await fetch_freshness(pool, channel, campaign)
    now = datetime.now(timezone.utc)
    orders_last = row.get("orders_last_event_time")
    sessions_last = row.get("sessions_last_event_time")
    return FreshnessResponse(
        now=now,
        orders_last_event_time=orders_last,
        sessions_last_event_time=sessions_last,
        orders_freshness_seconds=(
            (now - orders_last).total_seconds() if orders_last else None
        ),
        sessions_freshness_seconds=(
            (now - sessions_last).total_seconds() if sessions_last else None
        ),
        channel=channel,
        campaign=campaign,
    )


async def fetch_time_to_signal_info(
    pool: asyncpg.Pool,
    bucket: str,
    from_ts: datetime,
    to_ts: datetime,
    channel: str | None = None,
    campaign: str | None = None,
) -> dict:
    row = await fetch_time_to_signal(pool, bucket, from_ts, to_ts, channel, campaign)
    return {
        "orders": TimeToSignalItem(
            avg_seconds=row.get("orders_avg_seconds"),
            max_seconds=row.get("orders_max_seconds"),
        ),
        "sessions": TimeToSignalItem(
            avg_seconds=row.get("sessions_avg_seconds"),
            max_seconds=row.get("sessions_max_seconds"),
        ),
    }
