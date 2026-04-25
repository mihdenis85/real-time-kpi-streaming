import logging
import time
import requests
import uuid
from datetime import datetime, timezone
import threading

from tests.testing_helpers import BASE_URL, HEADERS

logger = logging.getLogger(__name__)

PEAK_LOAD_ORDER_COUNT = 1000


def send_many_orders(count):
    for i in range(count):
        payload = {
            "order_id": str(uuid.uuid4()),
            "customer_id": f"cust-bulk-{i}",
            "amount": 5.0,
            "currency": "USD",
            "channel": "web",
            "campaign": "bulk",
            "event_time": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        }
        try:
            requests.post(f"{BASE_URL}/events/order", json=payload, headers=HEADERS, timeout=5)
        except:
            pass  # Ignore errors for this test


def test_latency_during_peak_load():
    """
    Latency test under peak load.
    Measure benchmark event freshness while high traffic is generated.
    """
    # 1) Send a benchmark event
    event_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    # Use random UUID order_id so logic does not reject the test payload
    payload = {
        "order_id": str(uuid.uuid4()),
        "customer_id": "benchmark-cust",
        "amount": 50.0,
        "currency": "USD",
        "channel": "mobile",
        "campaign": "benchmark",
        "event_time": event_time
    }
    r = requests.post(f"{BASE_URL}/events/order", json=payload, headers=HEADERS)
    assert r.status_code == 200

    # 2) Launch load in the background
    thread = threading.Thread(target=send_many_orders, args=(PEAK_LOAD_ORDER_COUNT,))
    thread.start()

    # 3) Ask freshness until the benchmark event appears (wait up to 60 seconds)
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
    # Under peak load we expect a higher latency but within allowed limit (e.g. 10 sec)
    assert latency < 10.0, f"Too high latency under load: {latency} sec."
    logger.info("test_latency_during_peak_load passed: latency=%.2f sec", latency)
