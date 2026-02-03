from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from ingest_api.api.schemas import AlertSeries, KpiLatest, KpiSeries
from ingest_api.services.kpi_service import (
    fetch_alerts,
    fetch_latest_kpi,
    fetch_series,
)

router = APIRouter(tags=["kpi"])


def _ensure_range(start: datetime, end: datetime) -> None:
    if start > end:
        raise HTTPException(status_code=400, detail="from must be <= to")


@router.get("/kpi/latest", response_model=KpiLatest)
async def kpi_latest(
    request: Request,
    bucket: Literal["minute", "hour"] = Query("minute"),
) -> KpiLatest:
    pool = request.app.state.db_pool
    try:
        point = await fetch_latest_kpi(pool, bucket)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KpiLatest(bucket=bucket, point=point)


@router.get("/kpi/minute", response_model=KpiSeries)
async def kpi_minute(
    request: Request,
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(2000, ge=1, le=5000),
) -> KpiSeries:
    now = datetime.now(timezone.utc)
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(hours=2))
    _ensure_range(from_ts, to_ts)
    pool = request.app.state.db_pool
    try:
        points = await fetch_series(pool, "minute", from_ts, to_ts, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KpiSeries(bucket="minute", from_ts=from_ts, to_ts=to_ts, points=points)


@router.get("/kpi/hour", response_model=KpiSeries)
async def kpi_hour(
    request: Request,
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(2000, ge=1, le=5000),
) -> KpiSeries:
    now = datetime.now(timezone.utc)
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(days=3))
    _ensure_range(from_ts, to_ts)
    pool = request.app.state.db_pool
    try:
        points = await fetch_series(pool, "hour", from_ts, to_ts, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KpiSeries(bucket="hour", from_ts=from_ts, to_ts=to_ts, points=points)


@router.get("/alerts", response_model=AlertSeries)
async def alerts(
    request: Request,
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(500, ge=1, le=2000),
) -> AlertSeries:
    now = datetime.now(timezone.utc)
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(days=1))
    _ensure_range(from_ts, to_ts)
    pool = request.app.state.db_pool
    items = await fetch_alerts(pool, from_ts, to_ts, limit)
    return AlertSeries(from_ts=from_ts, to_ts=to_ts, items=items)
