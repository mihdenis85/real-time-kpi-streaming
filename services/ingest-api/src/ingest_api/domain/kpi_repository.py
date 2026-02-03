from datetime import datetime

import asyncpg


_KPI_TABLES = {
    "minute": "kpi_minute_view",
    "hour": "kpi_hour_view",
}


def _get_table(bucket: str) -> str:
    table = _KPI_TABLES.get(bucket)
    if table is None:
        raise ValueError(f"Unsupported bucket: {bucket}")
    return table


async def fetch_range_rows(
    pool: asyncpg.Pool,
    bucket: str,
    from_ts: datetime,
    to_ts: datetime,
    limit: int,
) -> list[dict]:
    table = _get_table(bucket)
    query = f"""
        SELECT bucket, revenue, order_count, session_count,
               checkout_count, purchase_count, conversion_rate
        FROM {table}
        WHERE bucket >= $1 AND bucket <= $2
        ORDER BY bucket ASC
        LIMIT $3
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, from_ts, to_ts, limit)
    return [dict(row) for row in rows]


async def fetch_latest_row(pool: asyncpg.Pool, bucket: str) -> dict | None:
    table = _get_table(bucket)
    query = f"""
        SELECT bucket, revenue, order_count, session_count,
               checkout_count, purchase_count, conversion_rate
        FROM {table}
        ORDER BY bucket DESC
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query)
    return dict(row) if row else None


async def fetch_alerts_rows(
    pool: asyncpg.Pool,
    from_ts: datetime,
    to_ts: datetime,
    limit: int,
) -> list[dict]:
    query = """
        SELECT bucket, kpi, current_value, baseline_value, delta_pct,
               direction, created_at
        FROM alerts
        WHERE created_at >= $1 AND created_at <= $2
        ORDER BY created_at DESC
        LIMIT $3
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, from_ts, to_ts, limit)
    return [dict(row) for row in rows]
