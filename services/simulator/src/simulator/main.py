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
    factor = anomaly_factor()

    orders_count = sample_count(
        settings.BASE_ORDERS_PER_TICK * factor, settings.ORDER_COUNT_JITTER
    )
    sessions_count = sample_count(
        settings.BASE_SESSIONS_PER_TICK * factor, settings.SESSION_COUNT_JITTER
    )

    for _ in range(orders_count):
        channel, campaign = pick_segment()
        amount = random.gauss(
            settings.ORDER_BASE_AMOUNT_RUB * factor, settings.ORDER_AMOUNT_STDDEV
        )
        order_id = random_id("o")
        await post_event(
            client,
            "/events/order",
            {
                "order_id": order_id,
                "amount": round(max(1.0, amount), 2),
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

        if random.random() < settings.PURCHASE_RATE:
            await post_event(
                client,
                "/events/session",
                {
                    "session_id": session_id,
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
