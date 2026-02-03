from datetime import datetime

import asyncpg

from ingest_api.api.schemas import AlertItem, KpiPoint
from ingest_api.domain.kpi_repository import (
    fetch_alerts_rows,
    fetch_latest_row,
    fetch_range_rows,
)


async def fetch_series(
    pool: asyncpg.Pool,
    bucket: str,
    from_ts: datetime,
    to_ts: datetime,
    limit: int,
) -> list[KpiPoint]:
    rows = await fetch_range_rows(pool, bucket, from_ts, to_ts, limit)
    return [KpiPoint(**row) for row in rows]


async def fetch_latest_kpi(pool: asyncpg.Pool, bucket: str) -> KpiPoint | None:
    row = await fetch_latest_row(pool, bucket)
    if row is None:
        return None
    return KpiPoint(**row)


async def fetch_alerts(
    pool: asyncpg.Pool, from_ts: datetime, to_ts: datetime, limit: int
) -> list[AlertItem]:
    rows = await fetch_alerts_rows(pool, from_ts, to_ts, limit)
    return [AlertItem(**row) for row in rows]
