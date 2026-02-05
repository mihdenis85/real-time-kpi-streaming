from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OrderEvent(BaseModel):
    order_id: str = Field(..., min_length=1)
    customer_id: str | None = None
    amount: float = Field(..., gt=0)
    currency: str = "USD"
    channel: str | None = None
    campaign: str | None = None
    event_time: datetime
    event_id: str | None = None


class SessionEvent(BaseModel):
    session_id: str = Field(..., min_length=1)
    event_type: Literal["view", "checkout", "purchase"]
    user_id: str | None = None
    channel: str | None = None
    campaign: str | None = None
    event_time: datetime
    event_id: str | None = None


class IngestResponse(BaseModel):
    status: str
    event_id: str


class KpiPoint(BaseModel):
    bucket: datetime
    revenue: float
    order_count: int
    session_count: int
    checkout_count: int
    purchase_count: int
    conversion_rate: float | None = None


class KpiSeries(BaseModel):
    bucket: str
    from_ts: datetime
    to_ts: datetime
    channel: str | None = None
    campaign: str | None = None
    points: list[KpiPoint]


class KpiLatest(BaseModel):
    bucket: str
    channel: str | None = None
    campaign: str | None = None
    point: KpiPoint | None = None


class AlertItem(BaseModel):
    bucket: datetime
    kpi: str
    current_value: float | None = None
    baseline_value: float | None = None
    delta_pct: float | None = None
    direction: str | None = None
    created_at: datetime


class AlertSeries(BaseModel):
    from_ts: datetime
    to_ts: datetime
    items: list[AlertItem]


class FreshnessResponse(BaseModel):
    now: datetime
    orders_last_event_time: datetime | None = None
    sessions_last_event_time: datetime | None = None
    orders_freshness_seconds: float | None = None
    sessions_freshness_seconds: float | None = None
    channel: str | None = None
    campaign: str | None = None


class TimeToSignalItem(BaseModel):
    avg_seconds: float | None = None
    max_seconds: float | None = None


class TimeToSignalResponse(BaseModel):
    bucket: str
    from_ts: datetime
    to_ts: datetime
    orders: TimeToSignalItem
    sessions: TimeToSignalItem
    channel: str | None = None
    campaign: str | None = None
