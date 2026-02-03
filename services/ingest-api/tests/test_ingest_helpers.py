from datetime import datetime, timezone

from ingest_api.api.schemas import OrderEvent
from ingest_api.services.ingest_service import make_event_id, to_payload


def test_make_event_id_includes_parts() -> None:
    event_time = datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc)
    event_id = make_event_id("order", "o-1", event_time)
    assert event_id.startswith("order:o-1:")
    assert event_time.isoformat() in event_id


def test_to_payload_normalizes_time_fields() -> None:
    event_time = datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc)
    event = OrderEvent(
        order_id="o-1",
        customer_id="c-1",
        amount=120.5,
        currency="USD",
        channel="web",
        event_time=event_time,
    )

    payload = to_payload(event, event_id="o-1")
    assert payload["event_id"] == "o-1"
    assert payload["event_time"] == event_time.isoformat()
    assert "received_at" in payload
    parsed_received = datetime.fromisoformat(payload["received_at"])
    assert parsed_received.tzinfo is not None
