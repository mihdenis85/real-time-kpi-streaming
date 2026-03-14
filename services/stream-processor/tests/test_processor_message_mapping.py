import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

from stream_processor.services import processor


class _DummyAcquire:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyPool:
    def acquire(self):
        return _DummyAcquire()


class _CaptureAggregates:
    def __init__(self) -> None:
        self.items: list[tuple[datetime, object]] = []

    async def add(self, event_time, delta):
        self.items.append((event_time, delta))


class _DedupeNeverSeen:
    def seen(self, _key, _now):
        return False


def _message(topic: str, payload: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(topic=topic, value=json.dumps(payload).encode("utf-8"))


def test_process_message_maps_view_event_to_view_count(monkeypatch) -> None:
    monkeypatch.setattr(processor.settings, "KAFKA_ORDERS_TOPIC", "orders")

    async def fake_insert_session(_conn, _payload):
        return True

    monkeypatch.setattr(processor, "insert_session", fake_insert_session)

    aggregates = _CaptureAggregates()
    msg = _message(
        "sessions",
        {
            "event_id": "e-1",
            "session_id": "s-1",
            "event_type": "view",
            "event_time": "2026-02-03T10:00:00Z",
            "received_at": "2026-02-03T10:00:01Z",
        },
    )

    async def run() -> None:
        result = await processor.process_message(
            msg=msg,
            pool=_DummyPool(),
            aggregates=aggregates,  # type: ignore[arg-type]
            dedupe=_DedupeNeverSeen(),  # type: ignore[arg-type]
        )
        assert result is not None

    asyncio.run(run())
    assert len(aggregates.items) == 1
    _, delta = aggregates.items[0]
    assert delta.view_count == 1
    assert delta.checkout_count == 0
    assert delta.purchase_count == 0


def test_process_message_maps_checkout_event_to_checkout_count(monkeypatch) -> None:
    monkeypatch.setattr(processor.settings, "KAFKA_ORDERS_TOPIC", "orders")

    async def fake_insert_session(_conn, _payload):
        return True

    monkeypatch.setattr(processor, "insert_session", fake_insert_session)

    aggregates = _CaptureAggregates()
    msg = _message(
        "sessions",
        {
            "event_id": "e-2",
            "session_id": "s-2",
            "event_type": "checkout",
            "event_time": "2026-02-03T10:01:00Z",
            "received_at": "2026-02-03T10:01:01Z",
        },
    )

    async def run() -> None:
        result = await processor.process_message(
            msg=msg,
            pool=_DummyPool(),
            aggregates=aggregates,  # type: ignore[arg-type]
            dedupe=_DedupeNeverSeen(),  # type: ignore[arg-type]
        )
        assert result is not None

    asyncio.run(run())
    assert len(aggregates.items) == 1
    _, delta = aggregates.items[0]
    assert delta.view_count == 0
    assert delta.checkout_count == 1
    assert delta.purchase_count == 0
