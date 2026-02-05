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
    service = AlertService(
        kpi=settings.KPI,
        baseline_days=settings.BASELINE_DAYS,
        threshold_pct=settings.THRESHOLD_PCT,
        min_baseline=settings.MIN_BASELINE,
        lookback_minutes=settings.LOOKBACK_MINUTES,
    )
    try:
        while True:
            async with pool.acquire() as conn:
                try:
                    alerted = await service.check_and_alert(conn)
                    if alerted:
                        logger.info("Alert emitted for %s", settings.KPI)
                except Exception:
                    logger.exception("Alert check failed")
            await asyncio.sleep(settings.INTERVAL_SECONDS)
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
