import asyncio
from datetime import datetime, timezone

from services.alert_service import AlertService


def _service(
    up_threshold_pct: float = 0.5,
    down_threshold_pct: float = 0.5,
) -> AlertService:
    return AlertService(
        kpi="revenue",
        baseline_days=1,
        up_threshold_pct=up_threshold_pct,
        down_threshold_pct=down_threshold_pct,
        min_baseline=1.0,
        lookback_minutes=10,
        current_window_minutes=5,
        duration_minutes=3,
    )


def test_check_and_alert_returns_false_when_not_enough_buckets(monkeypatch) -> None:
    service = _service()
    buckets = [datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc)]

    async def fake_recent(*_args, **_kwargs):
        return buckets

    monkeypatch.setattr("services.alert_service.fetch_recent_buckets", fake_recent)

    async def run() -> None:
        result = await service.check_and_alert(conn=None)  # type: ignore[arg-type]
        assert result is False

    asyncio.run(run())


def test_check_and_alert_inserts_up_alert(monkeypatch) -> None:
    service = _service()
    buckets = [
        datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 2, tzinfo=timezone.utc),
    ]
    inserted_calls: list[dict] = []

    async def fake_recent(*_args, **_kwargs):
        return buckets

    async def fake_current(*_args, **_kwargs):
        return 200.0

    async def fake_baseline(*_args, **_kwargs):
        return 100.0

    async def fake_insert(
        _conn, bucket, kpi, current, baseline, delta_pct, direction
    ) -> bool:
        inserted_calls.append(
            {
                "bucket": bucket,
                "kpi": kpi,
                "current": current,
                "baseline": baseline,
                "delta_pct": delta_pct,
                "direction": direction,
            }
        )
        return True

    monkeypatch.setattr("services.alert_service.fetch_recent_buckets", fake_recent)
    monkeypatch.setattr("services.alert_service.fetch_smoothed_current", fake_current)
    monkeypatch.setattr("services.alert_service.fetch_baseline", fake_baseline)
    monkeypatch.setattr("services.alert_service.insert_alert", fake_insert)

    async def run() -> None:
        result = await service.check_and_alert(conn=None)  # type: ignore[arg-type]
        assert result is True

    asyncio.run(run())
    assert len(inserted_calls) == 1
    assert inserted_calls[0]["bucket"] == buckets[-1]
    assert inserted_calls[0]["direction"] == "up"
    assert inserted_calls[0]["delta_pct"] == 1.0


def test_check_and_alert_inserts_down_alert(monkeypatch) -> None:
    service = _service(down_threshold_pct=0.5)
    buckets = [
        datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 2, tzinfo=timezone.utc),
    ]
    inserted_calls: list[dict] = []

    async def fake_recent(*_args, **_kwargs):
        return buckets

    async def fake_current(*_args, **_kwargs):
        return 40.0

    async def fake_baseline(*_args, **_kwargs):
        return 100.0

    async def fake_insert(
        _conn, bucket, kpi, current, baseline, delta_pct, direction
    ) -> bool:
        inserted_calls.append(
            {
                "bucket": bucket,
                "kpi": kpi,
                "current": current,
                "baseline": baseline,
                "delta_pct": delta_pct,
                "direction": direction,
            }
        )
        return True

    monkeypatch.setattr("services.alert_service.fetch_recent_buckets", fake_recent)
    monkeypatch.setattr("services.alert_service.fetch_smoothed_current", fake_current)
    monkeypatch.setattr("services.alert_service.fetch_baseline", fake_baseline)
    monkeypatch.setattr("services.alert_service.insert_alert", fake_insert)

    async def run() -> None:
        result = await service.check_and_alert(conn=None)  # type: ignore[arg-type]
        assert result is True

    asyncio.run(run())
    assert len(inserted_calls) == 1
    assert inserted_calls[0]["bucket"] == buckets[-1]
    assert inserted_calls[0]["direction"] == "down"
    assert inserted_calls[0]["delta_pct"] == -0.6


def test_check_and_alert_returns_false_when_baseline_too_low(monkeypatch) -> None:
    service = _service()
    buckets = [
        datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 2, tzinfo=timezone.utc),
    ]

    async def fake_recent(*_args, **_kwargs):
        return buckets

    async def fake_current(*_args, **_kwargs):
        return 200.0

    async def fake_baseline(*_args, **_kwargs):
        return 0.5

    async def fail_insert(*_args, **_kwargs):
        assert False, "insert_alert should not be called"

    monkeypatch.setattr("services.alert_service.fetch_recent_buckets", fake_recent)
    monkeypatch.setattr("services.alert_service.fetch_smoothed_current", fake_current)
    monkeypatch.setattr("services.alert_service.fetch_baseline", fake_baseline)
    monkeypatch.setattr("services.alert_service.insert_alert", fail_insert)

    async def run() -> None:
        result = await service.check_and_alert(conn=None)  # type: ignore[arg-type]
        assert result is False

    asyncio.run(run())


def test_check_and_alert_returns_false_when_any_bucket_below_threshold(
    monkeypatch,
) -> None:
    service = _service(up_threshold_pct=0.5, down_threshold_pct=0.5)
    buckets = [
        datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 2, tzinfo=timezone.utc),
    ]
    current_by_bucket = {
        buckets[0]: 200.0,
        buckets[1]: 120.0,
        buckets[2]: 200.0,
    }

    async def fake_recent(*_args, **_kwargs):
        return buckets

    async def fake_current(_conn, bucket, *_args):
        return current_by_bucket[bucket]

    async def fake_baseline(*_args, **_kwargs):
        return 100.0

    async def fail_insert(*_args, **_kwargs):
        assert False, "insert_alert should not be called"

    monkeypatch.setattr("services.alert_service.fetch_recent_buckets", fake_recent)
    monkeypatch.setattr("services.alert_service.fetch_smoothed_current", fake_current)
    monkeypatch.setattr("services.alert_service.fetch_baseline", fake_baseline)
    monkeypatch.setattr("services.alert_service.insert_alert", fail_insert)

    async def run() -> None:
        result = await service.check_and_alert(conn=None)  # type: ignore[arg-type]
        assert result is False

    asyncio.run(run())


def test_check_and_alert_returns_false_when_current_missing(monkeypatch) -> None:
    service = _service()
    buckets = [
        datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 10, 2, tzinfo=timezone.utc),
    ]

    async def fake_recent(*_args, **_kwargs):
        return buckets

    async def fake_current(*_args, **_kwargs):
        return None

    async def fake_baseline(*_args, **_kwargs):
        return 100.0

    async def fail_insert(*_args, **_kwargs):
        assert False, "insert_alert should not be called"

    monkeypatch.setattr("services.alert_service.fetch_recent_buckets", fake_recent)
    monkeypatch.setattr("services.alert_service.fetch_smoothed_current", fake_current)
    monkeypatch.setattr("services.alert_service.fetch_baseline", fake_baseline)
    monkeypatch.setattr("services.alert_service.insert_alert", fail_insert)

    async def run() -> None:
        result = await service.check_and_alert(conn=None)  # type: ignore[arg-type]
        assert result is False

    asyncio.run(run())
