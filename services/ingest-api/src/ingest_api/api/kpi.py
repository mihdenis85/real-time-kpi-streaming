from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from ingest_api.api.schemas import (
    AlertSeries,
    FreshnessResponse,
    KpiLatest,
    KpiSeries,
    TimeToSignalResponse,
)
from ingest_api.services.kpi_service import (
    fetch_alerts,
    fetch_freshness_info,
    fetch_latest_kpi,
    fetch_series,
    fetch_time_to_signal_info,
)

router = APIRouter(tags=["kpi"])


def _ensure_range(start: datetime, end: datetime) -> None:
    if start > end:
        raise HTTPException(status_code=400, detail="from must be <= to")


@router.get(
    "/kpi/latest",
    response_model=KpiLatest,
    summary="Get latest KPI point",
    description=(
        "Returns the latest aggregated KPI point for the selected bucket "
        "(minute or hour), with optional segmentation by channel/campaign."
    ),
    response_description="Latest KPI point and applied filters.",
)
async def kpi_latest(
    request: Request,
    bucket: Literal["minute", "hour"] = Query(
        "minute", description="Aggregation bucket: minute or hour."
    ),
    channel: str | None = Query(None, description="Optional channel filter."),
    campaign: str | None = Query(None, description="Optional campaign filter."),
) -> KpiLatest:
    pool = request.app.state.db_pool
    try:
        point = await fetch_latest_kpi(pool, bucket, channel, campaign)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KpiLatest(bucket=bucket, channel=channel, campaign=campaign, point=point)


@router.get(
    "/kpi/minute",
    response_model=KpiSeries,
    summary="Get minute KPI series",
    description=(
        "Returns KPI time series with minute granularity. "
        "If from/to are omitted, default range is the last 2 hours."
    ),
    response_description="Minute KPI series for the selected period.",
)
async def kpi_minute(
    request: Request,
    from_ts: datetime | None = Query(
        None, alias="from", description="Range start (UTC)."
    ),
    to_ts: datetime | None = Query(None, alias="to", description="Range end (UTC)."),
    limit: int = Query(2000, ge=1, le=5000, description="Maximum points to return."),
    channel: str | None = Query(None, description="Optional channel filter."),
    campaign: str | None = Query(None, description="Optional campaign filter."),
) -> KpiSeries:
    now = datetime.now(timezone.utc)
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(hours=2))
    _ensure_range(from_ts, to_ts)
    pool = request.app.state.db_pool
    try:
        points = await fetch_series(
            pool, "minute", from_ts, to_ts, limit, channel, campaign
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KpiSeries(
        bucket="minute",
        from_ts=from_ts,
        to_ts=to_ts,
        channel=channel,
        campaign=campaign,
        points=points,
    )


@router.get(
    "/kpi/hour",
    response_model=KpiSeries,
    summary="Get hour KPI series",
    description=(
        "Returns KPI time series with hour granularity. "
        "If from/to are omitted, default range is the last 3 days."
    ),
    response_description="Hour KPI series for the selected period.",
)
async def kpi_hour(
    request: Request,
    from_ts: datetime | None = Query(
        None, alias="from", description="Range start (UTC)."
    ),
    to_ts: datetime | None = Query(None, alias="to", description="Range end (UTC)."),
    limit: int = Query(2000, ge=1, le=5000, description="Maximum points to return."),
    channel: str | None = Query(None, description="Optional channel filter."),
    campaign: str | None = Query(None, description="Optional campaign filter."),
) -> KpiSeries:
    now = datetime.now(timezone.utc)
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(days=3))
    _ensure_range(from_ts, to_ts)
    pool = request.app.state.db_pool
    try:
        points = await fetch_series(
            pool, "hour", from_ts, to_ts, limit, channel, campaign
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KpiSeries(
        bucket="hour",
        from_ts=from_ts,
        to_ts=to_ts,
        channel=channel,
        campaign=campaign,
        points=points,
    )


@router.get(
    "/alerts",
    response_model=AlertSeries,
    summary="Get alerts list",
    description=(
        "Returns alerts in the requested time range. "
        "If from/to are omitted, default range is the last 24 hours."
    ),
    response_description="Alerts list for the selected period.",
)
async def alerts(
    request: Request,
    from_ts: datetime | None = Query(
        None, alias="from", description="Range start (UTC)."
    ),
    to_ts: datetime | None = Query(None, alias="to", description="Range end (UTC)."),
    limit: int = Query(500, ge=1, le=2000, description="Maximum alerts to return."),
) -> AlertSeries:
    now = datetime.now(timezone.utc)
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(days=1))
    _ensure_range(from_ts, to_ts)
    pool = request.app.state.db_pool
    items = await fetch_alerts(pool, from_ts, to_ts, limit)
    return AlertSeries(from_ts=from_ts, to_ts=to_ts, items=items)


@router.get(
    "/metrics/freshness",
    response_model=FreshnessResponse,
    summary="Get freshness metrics",
    description=(
        "Returns latest event timestamps and freshness (seconds) "
        "for orders and sessions, optionally filtered by segment."
    ),
    response_description="Freshness metrics for orders and sessions.",
)
async def metrics_freshness(
    request: Request,
    channel: str | None = Query(None, description="Optional channel filter."),
    campaign: str | None = Query(None, description="Optional campaign filter."),
) -> FreshnessResponse:
    pool = request.app.state.db_pool
    return await fetch_freshness_info(pool, channel, campaign)


@router.get(
    "/metrics/time-to-signal",
    response_model=TimeToSignalResponse,
    summary="Get time-to-signal metrics",
    description=(
        "Returns average and max delay between event_time and processed_time "
        "for orders and sessions in the selected interval."
    ),
    response_description="Time-to-signal metrics for orders and sessions.",
)
async def metrics_time_to_signal(
    request: Request,
    bucket: Literal["minute", "hour"] = Query(
        "minute", description="Aggregation bucket: minute or hour."
    ),
    from_ts: datetime | None = Query(
        None, alias="from", description="Range start (UTC)."
    ),
    to_ts: datetime | None = Query(None, alias="to", description="Range end (UTC)."),
    channel: str | None = Query(None, description="Optional channel filter."),
    campaign: str | None = Query(None, description="Optional campaign filter."),
) -> TimeToSignalResponse:
    now = datetime.now(timezone.utc)
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(hours=2))
    _ensure_range(from_ts, to_ts)
    pool = request.app.state.db_pool
    data = await fetch_time_to_signal_info(
        pool, bucket, from_ts, to_ts, channel, campaign
    )
    return TimeToSignalResponse(
        bucket=bucket,
        from_ts=from_ts,
        to_ts=to_ts,
        orders=data["orders"],
        sessions=data["sessions"],
        channel=channel,
        campaign=campaign,
    )
