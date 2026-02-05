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
    channel: str | None = None,
    campaign: str | None = None,
) -> list[dict]:
    if channel is None and campaign is None:
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

    query = """
        WITH orders_agg AS (
            SELECT date_trunc($1, event_time) AS bucket,
                   SUM(amount) AS revenue,
                   COUNT(*) AS order_count
            FROM orders
            WHERE event_time >= $2 AND event_time <= $3
              AND ($4::text IS NULL OR channel = $4)
              AND ($5::text IS NULL OR campaign = $5)
            GROUP BY 1
        ),
        sessions_agg AS (
            SELECT date_trunc($1, event_time) AS bucket,
                   COUNT(*) FILTER (WHERE event_type = 'view') AS session_count,
                   COUNT(*) FILTER (WHERE event_type = 'checkout') AS checkout_count,
                   COUNT(*) FILTER (WHERE event_type = 'purchase') AS purchase_count
            FROM sessions
            WHERE event_time >= $2 AND event_time <= $3
              AND ($4::text IS NULL OR channel = $4)
              AND ($5::text IS NULL OR campaign = $5)
            GROUP BY 1
        )
        SELECT
            COALESCE(o.bucket, s.bucket) AS bucket,
            COALESCE(o.revenue, 0) AS revenue,
            COALESCE(o.order_count, 0) AS order_count,
            COALESCE(s.session_count, 0) AS session_count,
            COALESCE(s.checkout_count, 0) AS checkout_count,
            COALESCE(s.purchase_count, 0) AS purchase_count,
            CASE
                WHEN COALESCE(s.session_count, 0) > 0
                THEN COALESCE(s.purchase_count, 0)::DOUBLE PRECISION
                     / NULLIF(COALESCE(s.session_count, 0), 0)
                ELSE NULL
            END AS conversion_rate
        FROM orders_agg o
        FULL OUTER JOIN sessions_agg s ON o.bucket = s.bucket
        ORDER BY bucket ASC
        LIMIT $6
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, bucket, from_ts, to_ts, channel, campaign, limit)
    return [dict(row) for row in rows]


async def fetch_latest_row(
    pool: asyncpg.Pool,
    bucket: str,
    channel: str | None = None,
    campaign: str | None = None,
) -> dict | None:
    if channel is None and campaign is None:
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

    query = """
        WITH orders_agg AS (
            SELECT date_trunc($1, event_time) AS bucket,
                   SUM(amount) AS revenue,
                   COUNT(*) AS order_count
            FROM orders
            WHERE ($2::text IS NULL OR channel = $2)
              AND ($3::text IS NULL OR campaign = $3)
            GROUP BY 1
        ),
        sessions_agg AS (
            SELECT date_trunc($1, event_time) AS bucket,
                   COUNT(*) FILTER (WHERE event_type = 'view') AS session_count,
                   COUNT(*) FILTER (WHERE event_type = 'checkout') AS checkout_count,
                   COUNT(*) FILTER (WHERE event_type = 'purchase') AS purchase_count
            FROM sessions
            WHERE ($2::text IS NULL OR channel = $2)
              AND ($3::text IS NULL OR campaign = $3)
            GROUP BY 1
        )
        SELECT
            COALESCE(o.bucket, s.bucket) AS bucket,
            COALESCE(o.revenue, 0) AS revenue,
            COALESCE(o.order_count, 0) AS order_count,
            COALESCE(s.session_count, 0) AS session_count,
            COALESCE(s.checkout_count, 0) AS checkout_count,
            COALESCE(s.purchase_count, 0) AS purchase_count,
            CASE
                WHEN COALESCE(s.session_count, 0) > 0
                THEN COALESCE(s.purchase_count, 0)::DOUBLE PRECISION
                     / NULLIF(COALESCE(s.session_count, 0), 0)
                ELSE NULL
            END AS conversion_rate
        FROM orders_agg o
        FULL OUTER JOIN sessions_agg s ON o.bucket = s.bucket
        ORDER BY bucket DESC
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, bucket, channel, campaign)
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


async def fetch_freshness(
    pool: asyncpg.Pool,
    channel: str | None = None,
    campaign: str | None = None,
) -> dict:
    query = """
        SELECT
            (SELECT MAX(event_time) FROM orders
             WHERE ($1::text IS NULL OR channel = $1)
               AND ($2::text IS NULL OR campaign = $2)) AS orders_last_event_time,
            (SELECT MAX(event_time) FROM sessions
             WHERE ($1::text IS NULL OR channel = $1)
               AND ($2::text IS NULL OR campaign = $2)) AS sessions_last_event_time
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, channel, campaign)
    return dict(row) if row else {}


async def fetch_time_to_signal(
    pool: asyncpg.Pool,
    bucket: str,
    from_ts: datetime,
    to_ts: datetime,
    channel: str | None = None,
    campaign: str | None = None,
) -> dict:
    query = """
        WITH order_lags AS (
            SELECT date_trunc($1, event_time) AS bucket,
                   MAX(processed_at) - MAX(event_time) AS lag
            FROM orders
            WHERE event_time >= $2 AND event_time <= $3
              AND ($4::text IS NULL OR channel = $4)
              AND ($5::text IS NULL OR campaign = $5)
            GROUP BY 1
        ),
        session_lags AS (
            SELECT date_trunc($1, event_time) AS bucket,
                   MAX(processed_at) - MAX(event_time) AS lag
            FROM sessions
            WHERE event_time >= $2 AND event_time <= $3
              AND ($4::text IS NULL OR channel = $4)
              AND ($5::text IS NULL OR campaign = $5)
            GROUP BY 1
        )
        SELECT
            (SELECT AVG(EXTRACT(EPOCH FROM lag)) FROM order_lags) AS orders_avg_seconds,
            (SELECT MAX(EXTRACT(EPOCH FROM lag)) FROM order_lags) AS orders_max_seconds,
            (SELECT AVG(EXTRACT(EPOCH FROM lag)) FROM session_lags) AS sessions_avg_seconds,
            (SELECT MAX(EXTRACT(EPOCH FROM lag)) FROM session_lags) AS sessions_max_seconds
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, bucket, from_ts, to_ts, channel, campaign)
    return dict(row) if row else {}
