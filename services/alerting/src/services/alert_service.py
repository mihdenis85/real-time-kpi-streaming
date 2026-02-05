from datetime import datetime

import asyncpg
from domain.alert_repository import (
    fetch_baseline,
    fetch_current,
    fetch_recent_bucket,
    insert_alert,
    validate_kpi,
)


def minute_bucket(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


class AlertService:
    def __init__(
        self,
        kpi: str,
        baseline_days: int,
        threshold_pct: float,
        min_baseline: float,
        lookback_minutes: int,
    ) -> None:
        self.kpi = validate_kpi(kpi)
        self.baseline_days = baseline_days
        self.threshold_pct = threshold_pct
        self.min_baseline = min_baseline
        self.lookback_minutes = lookback_minutes

    async def check_and_alert(self, conn: asyncpg.Connection) -> bool:
        bucket = await fetch_recent_bucket(conn, self.lookback_minutes)
        if bucket is None:
            return False

        current = await fetch_current(conn, bucket, self.kpi)
        if current is None:
            return False

        baseline = await fetch_baseline(conn, bucket, self.kpi, self.baseline_days)
        if baseline is None or baseline < self.min_baseline:
            return False

        delta_pct = (current - baseline) / baseline
        if abs(delta_pct) < self.threshold_pct:
            return False

        direction = "up" if delta_pct > 0 else "down"
        inserted = await insert_alert(
            conn, bucket, self.kpi, current, baseline, delta_pct, direction
        )
        return inserted
