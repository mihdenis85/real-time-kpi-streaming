import asyncio
import logging
import random
import string
from contextlib import suppress
from datetime import datetime, timezone

import httpx

from simulator.settings import Settings


def _isoformat_z(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _random_id(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}-{int(datetime.now(timezone.utc).timestamp())}-{suffix}"


def _clamp_count(value: float) -> int:
    return max(0, int(round(value)))


def _sample_count(base: float, jitter: float) -> int:
    return _clamp_count(random.gauss(base, jitter))


def _anomaly_factor(settings: Settings) -> float:
    if random.random() >= settings.ANOMALY_PROB:
        return 1.0
    return random.choice(
        [settings.ANOMALY_LOW_MULTIPLIER, settings.ANOMALY_HIGH_MULTIPLIER]
    )


def _schedule_factor(settings: Settings, now: datetime) -> float:
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


def _schedule_order_factor(settings: Settings, now: datetime) -> float:
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


def _fixed_anomaly_factor(settings: Settings, now: datetime) -> float | None:
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


def _pick_segment(settings: Settings) -> tuple[str, str]:
    return random.choice(settings.CHANNELS), random.choice(settings.CAMPAIGNS)


class SimulatorController:
    def __init__(self, settings: Settings, logger: logging.Logger) -> None:
        self._settings = settings
        self._logger = logger
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> bool:
        async with self._lock:
            if self.is_running():
                return False
            self._task = asyncio.create_task(self._run_loop())
            return True

    async def stop(self) -> bool:
        async with self._lock:
            if not self.is_running():
                self._task = None
                return False
            task = self._task
            self._task = None
            assert task is not None
            task.cancel()

        with suppress(asyncio.CancelledError):
            await task
        return True

    async def _post_event(
        self, client: httpx.AsyncClient, path: str, payload: dict[str, object]
    ) -> None:
        try:
            response = await client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError:
            self._logger.exception("Failed to send event to %s", path)

    async def _run_once(self, client: httpx.AsyncClient) -> None:
        now = datetime.now(timezone.utc)
        event_time = _isoformat_z(now)
        schedule = _schedule_factor(self._settings, now)
        order_schedule = _schedule_order_factor(self._settings, now)
        fixed = _fixed_anomaly_factor(self._settings, now)
        factor = schedule * (
            fixed if fixed is not None else _anomaly_factor(self._settings)
        )

        orders_count = _sample_count(
            self._settings.BASE_ORDERS_PER_TICK * factor,
            self._settings.ORDER_COUNT_JITTER,
        )
        sessions_count = _sample_count(
            self._settings.BASE_SESSIONS_PER_TICK * factor,
            self._settings.SESSION_COUNT_JITTER,
        )
        sessions_count = max(
            sessions_count, orders_count * self._settings.MIN_VIEWS_PER_ORDER
        )

        for _ in range(sessions_count):
            channel, campaign = _pick_segment(self._settings)
            session_id = _random_id("s")
            await self._post_event(
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

            if random.random() < self._settings.CHECKOUT_RATE:
                await self._post_event(
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

            order_prob = min(1.0, self._settings.ORDER_PROB * order_schedule)
            if random.random() < order_prob:
                order_id = _random_id("o")
                amount = random.choice(self._settings.PRICE_LIST_RUB)
                await self._post_event(
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

                await self._post_event(
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

    async def _run_loop(self) -> None:
        headers = {"X-API-Key": self._settings.API_KEY}
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(
            base_url=self._settings.API_BASE_URL, headers=headers, timeout=timeout
        ) as client:
            self._logger.info("Simulator loop started")
            while True:
                await self._run_once(client)
                await asyncio.sleep(self._settings.SEND_INTERVAL_SECONDS)
