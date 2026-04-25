import logging
import threading
import time
import requests
import uuid
import pytest
from datetime import datetime, timedelta, timezone

from tests.testing_helpers import BASE_URL, HEADERS

logger = logging.getLogger(__name__)


def iso_now():
    # Current time in ISO format without microseconds, with 'Z'
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def send_order_event(payload):
    r = requests.post(f"{BASE_URL}/events/order", json=payload, headers=HEADERS, timeout=5)
    assert r.status_code == 200, f"Ingest API error: {r.status_code} {r.text}"


def get_kpi_minute(from_ts, to_ts, channel=None, campaign=None):
    params = {
        "from": from_ts.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "to": to_ts.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    if channel:
        params["channel"] = channel
    if campaign:
        params["campaign"] = campaign

    r = requests.get(f"{BASE_URL}/kpi/minute", params=params, headers=HEADERS, timeout=5)
    r.raise_for_status()
    return r.json().get("points", [])


def wait_for_kpi_bucket(target_event_time, expected_order_count, expected_revenue, channel=None, campaign=None, timeout=60):
    from_ts = target_event_time - timedelta(minutes=2)
    to_ts = target_event_time + timedelta(minutes=2)

    for _ in range(timeout):
        points = get_kpi_minute(from_ts, to_ts, channel, campaign)
        for point in points:
            bucket = datetime.fromisoformat(point["bucket"].replace("Z", "+00:00"))
            if bucket != target_event_time.replace(second=0, microsecond=0):
                continue
            if point["order_count"] >= expected_order_count and point["revenue"] >= expected_revenue:
                return point
        time.sleep(1)
    return None


def test_end_to_end_latency_order():
    """
    End-to-end latency test for order event.
    Send an order with current time and verify when it appears in KPI.
    """
    event_time = iso_now()
    payload = {
        "order_id": str(uuid.uuid4()),
        "customer_id": "cust-1",
        "amount": 100.0,
        "currency": "USD",
        "channel": "web",
        "campaign": "spring",
        "event_time": event_time,
    }
    send_order_event(payload)

    start = time.time()
    latency = None
    for _ in range(60):
        r2 = requests.get(f"{BASE_URL}/metrics/freshness", headers=HEADERS)
        data = r2.json()
        last_time = data.get("orders_last_event_time")
        if last_time is not None and last_time >= event_time:
            latency = time.time() - start
            break
        time.sleep(1)

    assert latency is not None, "Event did not appear in /metrics/freshness in time"
    assert latency < 15.0, f"Latency too high: {latency} sec."
    logger.info("test_end_to_end_latency_order passed: latency=%.2f sec", latency)


def test_latency_during_peak_load():
    """
    Latency test under peak load.
    Measure benchmark event freshness while high traffic is generated.
    """
    event_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "order_id": str(uuid.uuid4()),
        "customer_id": "benchmark-cust",
        "amount": 50.0,
        "currency": "USD",
        "channel": "mobile",
        "campaign": "benchmark",
        "event_time": event_time,
    }
    send_order_event(payload)

    def send_many_orders(count):
        for _ in range(count):
            bulk_payload = {
                "order_id": str(uuid.uuid4()),
                "customer_id": "bulk-cust",
                "amount": 5.0,
                "currency": "USD",
                "channel": "web",
                "campaign": "bulk",
                "event_time": iso_now(),
            }
            requests.post(f"{BASE_URL}/events/order", json=bulk_payload, headers=HEADERS, timeout=5)

    thread = threading.Thread(target=send_many_orders, args=(500,))
    thread.start()

    start = time.time()
    latency = None
    for _ in range(60):
        r2 = requests.get(f"{BASE_URL}/metrics/freshness", headers=HEADERS)
        data = r2.json()
        last_time = data.get("orders_last_event_time")
        if last_time is not None and last_time >= event_time:
            latency = time.time() - start
            break
        time.sleep(1)
    thread.join()

    assert latency is not None, "Benchmark event did not appear in /metrics/freshness"
    assert latency < 30.0, f"Too high latency under load: {latency} sec."
    logger.info("test_latency_during_peak_load passed: latency=%.2f sec", latency)


def test_kpi_aggregation_accuracy():
    """Check accurate KPI values after sending fixed orders."""
    event_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    channel = "test-channel"
    campaign = "test-campaign"

    orders = [
        {"amount": 10.0},
        {"amount": 20.0},
        {"amount": 30.0},
    ]
    for order in orders:
        payload = {
            "order_id": str(uuid.uuid4()),
            "customer_id": "kpi-user",
            "amount": order["amount"],
            "currency": "USD",
            "channel": channel,
            "campaign": campaign,
            "event_time": event_time.isoformat().replace("+00:00", "Z"),
        }
        send_order_event(payload)

    expected_count = len(orders)
    expected_revenue = sum(order["amount"] for order in orders)

    point = wait_for_kpi_bucket(event_time, expected_count, expected_revenue, channel=channel, campaign=campaign, timeout=60)
    assert point is not None, "KPI bucket did not update with expected order_count/revenue"
    assert point["order_count"] == expected_count
    assert point["revenue"] == expected_revenue


def test_order_deduplication():
    """Send same order twice and verify only first is counted."""
    event_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    channel = "dedupe-channel"
    campaign = "dedupe-campaign"
    order_id = str(uuid.uuid4())

    payload = {
        "order_id": order_id,
        "customer_id": "dedupe-user",
        "amount": 123.45,
        "currency": "USD",
        "channel": channel,
        "campaign": campaign,
        "event_time": event_time.isoformat().replace("+00:00", "Z"),
    }

    send_order_event(payload)
    # Duplicate event should be ignored by stream processor
    r2 = requests.post(f"{BASE_URL}/events/order", json=payload, headers=HEADERS, timeout=5)
    assert r2.status_code == 200

    point = wait_for_kpi_bucket(event_time, 1, 123.45, channel=channel, campaign=campaign, timeout=60)
    assert point is not None
    assert point["order_count"] == 1
    assert point["revenue"] == 123.45


def test_negative_order_payload():
    """API should reject invalid order payloads."""
    bad_payloads = [
        {"customer_id": "x", "amount": 1.0, "currency": "USD", "channel": "x", "campaign": "x", "event_time": iso_now()},
        {"order_id": str(uuid.uuid4()), "customer_id": "x", "amount": -5.0, "currency": "USD", "channel": "x", "campaign": "x", "event_time": iso_now()},
    ]

    for payload in bad_payloads:
        r = requests.post(f"{BASE_URL}/events/order", json=payload, headers=HEADERS, timeout=5)
        assert r.status_code in (400, 422)


def test_session_event_processing():
    """Session view events should contribute to KPI view_count."""
    event_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    channel = "session-channel"
    campaign = "session-campaign"

    payload = {
        "session_id": str(uuid.uuid4()),
        "event_type": "view",
        "user_id": "session-user",
        "channel": channel,
        "campaign": campaign,
        "event_time": event_time.isoformat().replace("+00:00", "Z"),
    }

    r = requests.post(f"{BASE_URL}/events/session", json=payload, headers=HEADERS, timeout=5)
    assert r.status_code == 200

    for _ in range(60):
        points = get_kpi_minute(event_time - timedelta(minutes=2), event_time + timedelta(minutes=2), channel=channel, campaign=campaign)
        if any(p.get("view_count", 0) >= 1 for p in points):
            break
        time.sleep(1)
    else:
        pytest.fail("Session event did not appear in KPI view_count")


def test_alerting_endpoint_ethereal():
    """Alerting endpoint should be queryable (basic integration check)."""
    now = datetime.now(timezone.utc)
    from_ts = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    to_ts = now.isoformat().replace("+00:00", "Z")

    r = requests.get(f"{BASE_URL}/alerts", params={"from": from_ts, "to": to_ts}, headers=HEADERS, timeout=5)
    assert r.status_code == 200, f"Alerting endpoint failure: {r.status_code}"
    assert isinstance(r.json().get("items", []), list)
