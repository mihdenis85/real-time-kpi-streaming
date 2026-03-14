import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from ingest_api.api.kpi import _ensure_range, _map_alert_kpi, alerts
from ingest_api.api.schemas import AlertType
from ingest_api.services.kpi_service import _alert_type_from_kpi, fetch_alerts


def test_map_alert_kpi_views_to_view_count() -> None:
    assert _map_alert_kpi(AlertType.VIEWS) == "view_count"
    assert _map_alert_kpi(AlertType.REVENUE) == "revenue"
    assert _map_alert_kpi(None) is None


def test_ensure_range_raises_on_invalid_order() -> None:
    start = datetime(2026, 2, 3, 11, 0, tzinfo=timezone.utc)
    end = datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc)
    try:
        _ensure_range(start, end)
        assert False, "expected _ensure_range to raise"
    except Exception as exc:
        assert "from must be <= to" in str(exc)


def test_alert_type_from_kpi_mapping() -> None:
    assert _alert_type_from_kpi("revenue") == AlertType.REVENUE
    assert _alert_type_from_kpi("view_count") == AlertType.VIEWS
    assert _alert_type_from_kpi("unknown") is None


def test_fetch_alerts_enriches_alert_type(monkeypatch) -> None:
    rows = [
        {
            "bucket": datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc),
            "kpi": "revenue",
            "current_value": 200.0,
            "baseline_value": 100.0,
            "delta_pct": 1.0,
            "direction": "up",
            "created_at": datetime(2026, 2, 3, 10, 1, tzinfo=timezone.utc),
        },
        {
            "bucket": datetime(2026, 2, 3, 10, 2, tzinfo=timezone.utc),
            "kpi": "view_count",
            "current_value": 10.0,
            "baseline_value": 30.0,
            "delta_pct": -0.67,
            "direction": "down",
            "created_at": datetime(2026, 2, 3, 10, 3, tzinfo=timezone.utc),
        },
    ]

    async def fake_fetch_alerts_rows(*_args, **_kwargs):
        return rows

    monkeypatch.setattr(
        "ingest_api.services.kpi_service.fetch_alerts_rows", fake_fetch_alerts_rows
    )

    async def run() -> None:
        items = await fetch_alerts(
            pool=None,  # type: ignore[arg-type]
            from_ts=datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc),
            to_ts=datetime(2026, 2, 3, 11, 0, tzinfo=timezone.utc),
            limit=100,
        )
        assert items[0].alert_type == AlertType.REVENUE
        assert items[1].alert_type == AlertType.VIEWS

    asyncio.run(run())


def test_alerts_endpoint_maps_views_filter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_alerts(pool, from_ts, to_ts, limit, kpi):
        captured["pool"] = pool
        captured["from_ts"] = from_ts
        captured["to_ts"] = to_ts
        captured["limit"] = limit
        captured["kpi"] = kpi
        return []

    monkeypatch.setattr("ingest_api.api.kpi.fetch_alerts", fake_fetch_alerts)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_pool="pool"))
    )

    async def run() -> None:
        response = await alerts(
            request=request,  # type: ignore[arg-type]
            from_ts=None,
            to_ts=None,
            limit=123,
            kpi=AlertType.VIEWS,
        )
        assert response.items == []

    asyncio.run(run())
    assert captured["pool"] == "pool"
    assert captured["limit"] == 123
    assert captured["kpi"] == "view_count"
    assert isinstance(captured["from_ts"], datetime)
    assert isinstance(captured["to_ts"], datetime)
