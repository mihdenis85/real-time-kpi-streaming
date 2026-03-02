import asyncio
import logging

import asyncpg
from services.alert_service import AlertService
from settings import get_settings

logger = logging.getLogger("alerting")
settings = get_settings()


async def run() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    pool = await asyncpg.create_pool(dsn=settings.DB_DSN, min_size=1, max_size=2)
    monitor_kpis = ["revenue", "view_count"]
    thresholds = {
        "revenue": settings.THRESHOLD_PCT,
        "view_count": settings.VIEW_THRESHOLD_PCT,
    }
    services = [
        AlertService(
            kpi=kpi,
            baseline_days=settings.BASELINE_DAYS,
            threshold_pct=thresholds[kpi],
            min_baseline=settings.MIN_BASELINE,
            lookback_minutes=settings.LOOKBACK_MINUTES,
            current_window_minutes=settings.CURRENT_WINDOW_MINUTES,
            duration_minutes=settings.DURATION_MINUTES,
        )
        for kpi in monitor_kpis
    ]
    try:
        while True:
            async with pool.acquire() as conn:
                try:
                    for service in services:
                        alerted = await service.check_and_alert(conn)
                        if alerted:
                            logger.info("Alert emitted for %s", service.kpi)
                except Exception:
                    logger.exception("Alert check failed")
            await asyncio.sleep(settings.INTERVAL_SECONDS)
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
