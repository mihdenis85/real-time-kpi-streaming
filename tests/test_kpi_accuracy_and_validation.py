from __future__ import annotations

import logging
import uuid
from datetime import timedelta

import pytest

from tests.testing_helpers import (
    iso_zulu,
    make_order_payload,
    make_session_payload,
    post_json,
    utc_now,
    wait_for_json,
)

logger = logging.getLogger(__name__)


def _wait_for_latest_kpi(campaign: str, channel: str = "web", order_count: int | None = None, revenue: float | None = None) -> dict:
    def predicate(payload: dict[str, object]) -> bool:
        point = payload.get("point")
        if point is None:
            return False
        if order_count is not None and point.get("order_count") != order_count:
            return False
        if revenue is not None and point.get("revenue") is not None:
            # allow slight rounding differences
            return abs(point["revenue"] - revenue) < 0.01
        return True

    data, _ = wait_for_json(
        "/kpi/latest",
        params={"bucket": "minute", "campaign": campaign, "channel": channel},
        timeout=30.0,
        predicate=predicate,
    )
    return data


def test_kpi_accuracy_for_known_orders() -> None:
    """
    Verifies accumulated KPI values are correct.

    This directly addresses RQ1 by showing that the lightweight
    streaming architecture is not only fast but also computes metrics correctly.
    Without this validation, latency alone does not prove accuracy.
    """
    campaign = f"accuracy-{uuid.uuid4().hex[:8]}"
    event_time = utc_now()
    amounts = [10.0, 15.5, 24.5]

    for index, amount in enumerate(amounts, start=1):
        payload = make_order_payload(
            order_id=f"{campaign}-order-{index}",
            customer_id=f"cust-{index}",
            amount=amount,
            channel="web",
            campaign=campaign,
            event_time=event_time,
        )
        response = post_json("/events/order", payload)
        assert response.status_code == 200, response.text

    data = _wait_for_latest_kpi(campaign, order_count=len(amounts), revenue=sum(amounts))
    point = data["point"]

    assert point["order_count"] == len(amounts)
    assert point["revenue"] == pytest.approx(sum(amounts), abs=0.01)
    assert point["average_order_value"] == pytest.approx(sum(amounts) / len(amounts), abs=0.01)
    assert point["view_count"] == 0
    assert point["checkout_count"] == 0
    assert point["purchase_count"] == 0
    assert point["conversion_rate"] == 0

    logger.info(
        "test_kpi_accuracy_for_known_orders passed: revenue=%.2f, orders=%s",
        point["revenue"],
        point["order_count"],
    )


def test_duplicate_order_is_not_double_counted() -> None:
    """
    Verifies duplicate event deduplication.

    This is critical for RQ1 because accuracy mistakes break KPI correctness.
    For RQ2 and RQ3 it is also a trust issue: if duplicates inflate sales, the team
    and users cannot trust the dashboard.
    """
    campaign = f"dedupe-{uuid.uuid4().hex[:8]}"
    order_id = f"{campaign}-order-1"
    event_time = utc_now()
    amount = 77.0

    payload = make_order_payload(
        order_id=order_id,
        customer_id="cust-dedupe",
        amount=amount,
        channel="web",
        campaign=campaign,
        event_time=event_time,
    )

    first = post_json("/events/order", payload)
    second = post_json("/events/order", payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    data = _wait_for_latest_kpi(campaign)
    point = data["point"]

    assert point["order_count"] == 1
    assert point["revenue"] == pytest.approx(amount, abs=0.01)
    assert point["average_order_value"] == pytest.approx(amount, abs=0.01)

    logger.info(
        "test_duplicate_order_is_not_double_counted passed: order_count=%s, revenue=%.2f",
        point["order_count"],
        point["revenue"],
    )


@pytest.mark.parametrize(
    "payload,expected_fragment",
    [
        (
            {
                "customer_id": "bad-1",
                "amount": 10.0,
                "currency": "USD",
                "channel": "web",
                "campaign": "invalid-missing-order-id",
                "event_time": iso_zulu(),
            },
            "order_id",
        ),
        (
            {
                "order_id": "bad-2",
                "customer_id": "bad-2",
                "amount": -1.0,
                "currency": "USD",
                "channel": "web",
                "campaign": "invalid-negative-amount",
                "event_time": iso_zulu(),
            },
            "amount",
        ),
        (
            {
                "order_id": "bad-3",
                "customer_id": "bad-3",
                "amount": 10.0,
                "currency": "USD",
                "channel": "web",
                "campaign": "invalid-event-time",
                "event_time": "not-a-date",
            },
            "event_time",
        ),
    ],
)
def test_invalid_order_payloads_are_rejected(payload: dict, expected_fragment: str) -> None:
    """
    Verifies API payload validation.

    This directly supports RQ1: invalid input should not break KPI accuracy,
    and for RQ2/RQ3 it reduces the risk that the team makes decisions based on
    incorrect events.
    """
    response = post_json("/events/order", payload)
    assert response.status_code == 422
    assert expected_fragment in response.text


def test_session_events_update_engagement_kpis() -> None:
    """
    Verifies multi-type event stream processing.

    While the main thesis focus is sales, support for session/view/checkout/purchase
    shows that the platform can provide the team with a broader view of engagement
    and user behavior. This supports RQ2 and RQ3.
    """
    campaign = f"session-{uuid.uuid4().hex[:8]}"
    event_time = utc_now()

    for event_type in ("view", "checkout", "purchase"):
        payload = make_session_payload(
            event_type=event_type,
            session_id=f"{campaign}-{event_type}",
            user_id=f"user-{event_type}",
            channel="mobile",
            campaign=campaign,
            event_time=event_time,
        )
        response = post_json("/events/session", payload)
        assert response.status_code == 200, response.text

    data, _ = wait_for_json(
        "/kpi/latest",
        params={"bucket": "minute", "campaign": campaign, "channel": "mobile"},
        timeout=30.0,
        predicate=lambda payload: payload.get("point") is not None,
    )
    point = data["point"]

    assert point["revenue"] == 0
    assert point["order_count"] == 0
    assert point["view_count"] == 1
    assert point["checkout_count"] == 1
    assert point["purchase_count"] == 1
    assert point["conversion_rate"] == pytest.approx(1.0, abs=0.01)

    logger.info(
        "test_session_events_update_engagement_kpis passed: views=%s, checkout=%s, purchase=%s",
        point["view_count"],
        point["checkout_count"],
        point["purchase_count"],
    )


def test_time_to_signal_reports_delay_for_orders() -> None:
    """
    Verifies /metrics/time-to-signal endpoint.

    This is the most direct test for RQ1: it measures lag between event_time and processing time.
    For RQ2 and RQ3 this is also important, because it determines how quickly the team and product
    will detect changes.
    """
    campaign = f"signal-{uuid.uuid4().hex[:8]}"
    event_time = utc_now()

    payload = make_order_payload(
        order_id=f"{campaign}-signal-order",
        customer_id="cust-signal",
        amount=50.0,
        channel="web",
        campaign=campaign,
        event_time=event_time,
    )
    response = post_json("/events/order", payload)
    assert response.status_code == 200, response.text

    window_start = event_time - timedelta(minutes=1)
    window_end = event_time + timedelta(minutes=5)
    data, _ = wait_for_json(
        "/metrics/time-to-signal",
        params={
            "bucket": "minute",
            "campaign": campaign,
            "channel": "web",
            "from": window_start.isoformat(),
            "to": window_end.isoformat(),
        },
        timeout=30.0,
        predicate=lambda payload: payload["orders"]["avg_seconds"] is not None,
    )

    orders = data["orders"]
    assert orders["avg_seconds"] is not None
    assert orders["max_seconds"] is not None
    assert orders["avg_seconds"] >= 0
    assert orders["max_seconds"] >= orders["avg_seconds"]
    assert orders["max_seconds"] < 15.0

    logger.info(
        "test_time_to_signal_reports_delay_for_orders passed: avg=%.2f sec, max=%.2f sec",
        orders["avg_seconds"],
        orders["max_seconds"],
    )
