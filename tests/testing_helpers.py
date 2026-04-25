from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

import requests

BASE_URL = "http://localhost:8000"


def _load_secrets_api_key() -> str:
    try:
        import tomllib
        from pathlib import Path

        settings_path = (
            Path(__file__).resolve().parents[1]
            / "services"
            / "ingest-api"
            / ".secrets.toml"
        )
        if settings_path.exists():
            with settings_path.open("rb") as f:
                data = tomllib.load(f)
            api_key = data.get("default", {}).get("API_KEY")
            if api_key:
                return api_key
    except ImportError:
        pass
    except Exception:
        pass

    return __import__("os").environ.get("INGEST_API_KEY") or "dev-key"


API_KEY = _load_secrets_api_key()
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
DEFAULT_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.5


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_zulu(value: datetime | None = None) -> str:
    dt = value or utc_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def parse_api_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def make_order_payload(
    *,
    order_id: str | None = None,
    customer_id: str | None = None,
    amount: float = 100.0,
    currency: str = "RUB",
    channel: str | None = "web",
    campaign: str | None = None,
    event_time: datetime | None = None,
) -> dict[str, Any]:
    campaign_name = campaign or f"campaign-{uuid.uuid4().hex[:8]}"
    return {
        "order_id": order_id or str(uuid.uuid4()),
        "customer_id": customer_id or f"cust-{uuid.uuid4().hex[:8]}",
        "amount": amount,
        "currency": currency,
        "channel": channel,
        "campaign": campaign_name,
        "event_time": iso_zulu(event_time),
    }


def make_session_payload(
    *,
    event_type: str = "view",
    session_id: str | None = None,
    user_id: str | None = None,
    channel: str | None = "mobile",
    campaign: str | None = None,
    event_time: datetime | None = None,
) -> dict[str, Any]:
    campaign_name = campaign or f"campaign-{uuid.uuid4().hex[:8]}"
    return {
        "session_id": session_id or str(uuid.uuid4()),
        "event_type": event_type,
        "user_id": user_id or f"user-{uuid.uuid4().hex[:8]}",
        "channel": channel,
        "campaign": campaign_name,
        "event_time": iso_zulu(event_time),
    }


def get_json(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    response = requests.get(
        f"{BASE_URL}{path}",
        headers=HEADERS,
        params=params,
        timeout=timeout,
    )
    assert response.status_code == 200, (
        f"GET {path} failed: {response.status_code} {response.text}"
    )
    return response.json()


def post_json(
    path: str, payload: dict[str, Any], *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> requests.Response:
    return requests.post(
        f"{BASE_URL}{path}",
        json=payload,
        headers=HEADERS,
        timeout=timeout,
    )


def wait_for_json(
    path: str,
    *,
    predicate: Callable[[dict[str, Any]], bool],
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
    interval: float = POLL_INTERVAL_SECONDS,
) -> tuple[dict[str, Any], float]:
    start = time.monotonic()
    deadline = start + timeout
    last_payload: dict[str, Any] | None = None
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            payload = get_json(path, params=params)
            last_payload = payload
            if predicate(payload):
                return payload, time.monotonic() - start
        except Exception as exc:
            last_error = exc
        time.sleep(interval)

    if last_error is not None and last_payload is None:
        raise AssertionError(
            f"Timed out waiting for {path}: {last_error}"
        ) from last_error
    raise AssertionError(f"Timed out waiting for {path}. Last payload: {last_payload}")


def minute_window_around(event_time: datetime) -> tuple[datetime, datetime]:
    start = event_time - timedelta(minutes=1)
    end = event_time + timedelta(minutes=5)
    return start, end
