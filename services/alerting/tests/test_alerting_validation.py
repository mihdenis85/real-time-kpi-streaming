from datetime import datetime, timezone

import pytest
from domain.alert_repository import validate_kpi
from services.alert_service import minute_bucket


def test_validate_kpi_allows_known_values() -> None:
    assert validate_kpi("revenue") == "revenue"


def test_validate_kpi_rejects_unknown_values() -> None:
    with pytest.raises(ValueError):
        validate_kpi("revenue; DROP TABLE kpi_minute;")


def test_minute_bucket_rounds_down() -> None:
    ts = datetime(2026, 2, 3, 10, 15, 30, tzinfo=timezone.utc)
    assert minute_bucket(ts) == datetime(2026, 2, 3, 10, 15, tzinfo=timezone.utc)
