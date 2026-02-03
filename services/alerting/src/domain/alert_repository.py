from datetime import datetime, timedelta

import asyncpg


ALLOWED_KPIS = {
    "revenue",
    "order_count",
    "session_count",
    "checkout_count",
    "purchase_count",
}


def validate_kpi(kpi: str) -> str:
    if kpi not in ALLOWED_KPIS:
        raise ValueError(f"Unsupported KPI: {kpi}")
    return kpi


async def fetch_current(
    conn: asyncpg.Connection, bucket: datetime, kpi: str
) -> float | None:
    safe_kpi = validate_kpi(kpi)
    row = await conn.fetchrow(
        f"SELECT {safe_kpi} FROM kpi_minute WHERE bucket = $1", bucket
    )
    if row is None:
        return None
    return float(row[kpi])


async def fetch_baseline(
    conn: asyncpg.Connection, bucket: datetime, kpi: str, baseline_days: int
) -> float | None:
    safe_kpi = validate_kpi(kpi)
    start = bucket - timedelta(days=baseline_days)
    row = await conn.fetchrow(
        f"""
        SELECT AVG({safe_kpi}) AS value
        FROM kpi_minute
        WHERE bucket >= $1
          AND bucket < $2
          AND EXTRACT(DOW FROM bucket) = EXTRACT(DOW FROM $2::timestamptz)
          AND EXTRACT(HOUR FROM bucket) = EXTRACT(HOUR FROM $2::timestamptz)
          AND EXTRACT(MINUTE FROM bucket) = EXTRACT(MINUTE FROM $2::timestamptz)
        """,
        start,
        bucket,
    )
    if row is None or row["value"] is None:
        return None
    return float(row["value"])


async def insert_alert(
    conn: asyncpg.Connection,
    bucket: datetime,
    kpi: str,
    current: float,
    baseline: float,
    delta_pct: float,
    direction: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO alerts (
            bucket,
            kpi,
            current_value,
            baseline_value,
            delta_pct,
            direction
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (bucket, kpi) DO NOTHING
        """,
        bucket,
        kpi,
        current,
        baseline,
        delta_pct,
        direction,
    )
