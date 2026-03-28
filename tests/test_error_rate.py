import logging
import threading
import requests
import uuid
from datetime import datetime, timezone

from tests.testing_helpers import BASE_URL, HEADERS


logger = logging.getLogger(__name__)

TOTAL_REQUESTS = 1000


def send_order(i, success_counter, failure_counter):
    payload = {
        # Use random UUID order ID to avoid deduplication collisions in stream processor
        "order_id": str(uuid.uuid4()),
        "customer_id": f"cust-{i}",
        "amount": 10.0 + i,
        "currency": "USD",
        "channel": "web",
        "campaign": "spring",
        "event_time": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    }
    try:
        r = requests.post(f"{BASE_URL}/events/order", json=payload, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            success_counter.append(1)
        else:
            failure_counter.append(1)
    except Exception:
        failure_counter.append(1)


def test_high_load_error_rate():
    """
    Reliability test: with many concurrent events the error rate should be low.
    """
    success_counter = []
    failure_counter = []
    threads = []
    for i in range(TOTAL_REQUESTS):
        t = threading.Thread(target=send_order, args=(i, success_counter, failure_counter))
        threads.append(t)
    # Launch threads
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total = len(success_counter) + len(failure_counter)
    assert total == TOTAL_REQUESTS
    error_rate = len(failure_counter) / TOTAL_REQUESTS * 100
    # Expect a low error rate (e.g. <5%)
    assert error_rate < 5, f"Too high error rate: {error_rate}%"
    logger.info("test_high_load_error_rate passed: error_rate=%.2f%%", error_rate)
