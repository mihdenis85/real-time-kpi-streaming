from typing import Any

import asyncpg


async def insert_order(conn: asyncpg.Connection, payload: dict[str, Any]) -> bool:
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
        ON CONFLICT ON CONSTRAINT orders_pkey DO NOTHING
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


async def insert_session(conn: asyncpg.Connection, payload: dict[str, Any]) -> bool:
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
        ON CONFLICT ON CONSTRAINT sessions_pkey DO NOTHING
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


async def flush_kpis(pool: asyncpg.Pool, minute: dict, hour: dict) -> None:
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
