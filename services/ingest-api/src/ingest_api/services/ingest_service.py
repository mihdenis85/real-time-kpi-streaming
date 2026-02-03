from datetime import datetime, timezone

from pydantic import BaseModel


def to_payload(event: BaseModel, event_id: str) -> dict[str, object]:
    received_at = datetime.now(timezone.utc)
    payload = event.model_dump()
    payload["event_id"] = event_id
    payload["received_at"] = received_at.isoformat()
    payload["event_time"] = payload["event_time"].isoformat()
    return payload


def make_event_id(prefix: str, key: str, event_time: datetime) -> str:
    return f"{prefix}:{key}:{event_time.isoformat()}"
