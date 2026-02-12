from datetime import datetime

import asyncpg
from domain.alert_repository import (
    fetch_baseline,
    fetch_recent_buckets,
    fetch_smoothed_current,
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
        current_window_minutes: int,
        duration_minutes: int,
    ) -> None:
        self.kpi = validate_kpi(kpi)
        self.baseline_days = baseline_days
        self.threshold_pct = threshold_pct
        self.min_baseline = min_baseline
        self.lookback_minutes = lookback_minutes
        self.current_window_minutes = current_window_minutes
        self.duration_minutes = duration_minutes

    async def check_and_alert(self, conn: asyncpg.Connection) -> bool:
        buckets = await fetch_recent_buckets(
            conn, self.lookback_minutes, self.duration_minutes
        )
        if len(buckets) < self.duration_minutes:
            return False

        latest_bucket = buckets[-1]
        latest_current = None
        latest_baseline = None
        latest_delta_pct = None

        for bucket in buckets:
            current = await fetch_smoothed_current(
                conn, bucket, self.kpi, self.current_window_minutes
            )
            if current is None:
                return False

            baseline = await fetch_baseline(conn, bucket, self.kpi, self.baseline_days)
            if baseline is None or baseline < self.min_baseline:
                return False

            delta_pct = (current - baseline) / baseline
            if abs(delta_pct) < self.threshold_pct:
                return False

            if bucket == latest_bucket:
                latest_current = current
                latest_baseline = baseline
                latest_delta_pct = delta_pct

        if (
            latest_current is None
            or latest_baseline is None
            or latest_delta_pct is None
        ):
            return False

        direction = "up" if latest_delta_pct > 0 else "down"
        inserted = await insert_alert(
            conn,
            latest_bucket,
            self.kpi,
            latest_current,
            latest_baseline,
            latest_delta_pct,
            direction,
        )
        return inserted
