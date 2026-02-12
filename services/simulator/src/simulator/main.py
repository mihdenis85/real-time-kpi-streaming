import asyncio
import logging
import random
import string
from datetime import datetime, timezone

import httpx

from simulator.settings import get_settings

settings = get_settings()
logger = logging.getLogger("simulator")


def isoformat_z(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def random_id(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}-{int(datetime.now(timezone.utc).timestamp())}-{suffix}"


def clamp_count(value: float) -> int:
    return max(0, int(round(value)))


def sample_count(base: float, jitter: float) -> int:
    return clamp_count(random.gauss(base, jitter))


def anomaly_factor() -> float:
    if random.random() >= settings.ANOMALY_PROB:
        return 1.0
    return random.choice(
        [settings.ANOMALY_LOW_MULTIPLIER, settings.ANOMALY_HIGH_MULTIPLIER]
    )


def schedule_factor(now: datetime) -> float:
    if settings.SCHEDULE_MODE == "day-night":
        if now.hour in settings.PEAK_HOURS_UTC:
            return settings.PEAK_MULTIPLIER
        if now.hour in settings.QUIET_HOURS_UTC:
            return settings.QUIET_MULTIPLIER
        return 1.0
    if settings.SCHEDULE_MODE == "seasonal":
        if now.hour in settings.SEASONAL_PEAK_HOURS_UTC:
            return settings.SEASONAL_PEAK_MULTIPLIER
        if now.hour in settings.SEASONAL_EVENING_HOURS_UTC:
            return settings.SEASONAL_EVENING_MULTIPLIER
        return 1.0
    return 1.0


def schedule_order_factor(now: datetime) -> float:
    if settings.SCHEDULE_MODE == "day-night":
        if now.hour in settings.PEAK_HOURS_UTC:
            return settings.PEAK_ORDER_MULTIPLIER
        if now.hour in settings.QUIET_HOURS_UTC:
            return settings.QUIET_ORDER_MULTIPLIER
        return 1.0
    if settings.SCHEDULE_MODE == "seasonal":
        if now.hour in settings.SEASONAL_PEAK_HOURS_UTC:
            return settings.SEASONAL_PEAK_ORDER_MULTIPLIER
        if now.hour in settings.SEASONAL_EVENING_HOURS_UTC:
            return settings.SEASONAL_EVENING_ORDER_MULTIPLIER
        return 1.0
    return 1.0


def fixed_anomaly_factor(now: datetime) -> float | None:
    if not settings.FIXED_ANOMALY_ENABLED:
        return None
    if settings.FIXED_ANOMALY_INTERVAL_MINUTES <= 0:
        return None
    slot = int(now.timestamp() // 60) // settings.FIXED_ANOMALY_INTERVAL_MINUTES
    if settings.FIXED_ANOMALY_MODE == "low":
        return settings.FIXED_ANOMALY_LOW_MULTIPLIER
    if settings.FIXED_ANOMALY_MODE == "high":
        return settings.FIXED_ANOMALY_HIGH_MULTIPLIER
    if slot % 2 == 0:
        return settings.FIXED_ANOMALY_LOW_MULTIPLIER
    return settings.FIXED_ANOMALY_HIGH_MULTIPLIER


def pick_segment() -> tuple[str, str]:
    return random.choice(settings.CHANNELS), random.choice(settings.CAMPAIGNS)


async def post_event(
    client: httpx.AsyncClient, path: str, payload: dict[str, object]
) -> None:
    try:
        response = await client.post(path, json=payload)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to send event to %s", path)


async def run_once(client: httpx.AsyncClient) -> None:
    now = datetime.now(timezone.utc)
    event_time = isoformat_z(now)
    schedule = schedule_factor(now)
    order_schedule = schedule_order_factor(now)
    fixed = fixed_anomaly_factor(now)
    factor = schedule * (fixed if fixed is not None else anomaly_factor())

    orders_count = sample_count(
        settings.BASE_ORDERS_PER_TICK * factor, settings.ORDER_COUNT_JITTER
    )
    sessions_count = sample_count(
        settings.BASE_SESSIONS_PER_TICK * factor, settings.SESSION_COUNT_JITTER
    )
    sessions_count = max(sessions_count, orders_count * settings.MIN_VIEWS_PER_ORDER)

    for _ in range(sessions_count):
        channel, campaign = pick_segment()
        session_id = random_id("s")
        await post_event(
            client,
            "/events/session",
            {
                "session_id": session_id,
                "event_type": "view",
                "channel": channel,
                "campaign": campaign,
                "event_time": event_time,
            },
        )

        if random.random() < settings.CHECKOUT_RATE:
            await post_event(
                client,
                "/events/session",
                {
                    "session_id": session_id,
                    "event_type": "checkout",
                    "channel": channel,
                    "campaign": campaign,
                    "event_time": event_time,
                },
            )

        order_prob = min(1.0, settings.ORDER_PROB * order_schedule)
        if random.random() < order_prob:
            order_id = random_id("o")
            amount = random.choice(settings.PRICE_LIST_RUB)
            await post_event(
                client,
                "/events/order",
                {
                    "order_id": order_id,
                    "amount": amount,
                    "currency": "RUB",
                    "channel": channel,
                    "campaign": campaign,
                    "event_time": event_time,
                },
            )

            await post_event(
                client,
                "/events/session",
                {
                    "session_id": f"s-{order_id}",
                    "event_type": "purchase",
                    "channel": channel,
                    "campaign": campaign,
                    "event_time": event_time,
                },
            )


async def run() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    if settings.SEED is not None:
        random.seed(settings.SEED)

    if not settings.ENABLED:
        logger.info("Simulator disabled (ENABLED=false)")
        return

    headers = {"X-API-Key": settings.API_KEY}
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(
        base_url=settings.API_BASE_URL, headers=headers, timeout=timeout
    ) as client:
        logger.info("Simulator started")
        while True:
            await run_once(client)
            await asyncio.sleep(settings.SEND_INTERVAL_SECONDS)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
