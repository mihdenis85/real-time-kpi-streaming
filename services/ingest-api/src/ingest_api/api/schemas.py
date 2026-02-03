from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class OrderEvent(BaseModel):
    order_id: str = Field(..., min_length=1)
    customer_id: Optional[str] = None
    amount: float = Field(..., gt=0)
    currency: str = "USD"
    channel: Optional[str] = None
    event_time: datetime
    event_id: Optional[str] = None


class SessionEvent(BaseModel):
    session_id: str = Field(..., min_length=1)
    event_type: Literal["view", "checkout", "purchase"]
    user_id: Optional[str] = None
    channel: Optional[str] = None
    event_time: datetime
    event_id: Optional[str] = None


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
    conversion_rate: Optional[float] = None


class KpiSeries(BaseModel):
    bucket: str
    from_ts: datetime
    to_ts: datetime
    points: list[KpiPoint]


class KpiLatest(BaseModel):
    bucket: str
    point: Optional[KpiPoint] = None


class AlertItem(BaseModel):
    bucket: datetime
    kpi: str
    current_value: Optional[float] = None
    baseline_value: Optional[float] = None
    delta_pct: Optional[float] = None
    direction: Optional[str] = None
    created_at: datetime


class AlertSeries(BaseModel):
    from_ts: datetime
    to_ts: datetime
    items: list[AlertItem]
