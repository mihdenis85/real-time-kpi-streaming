# Real-time KPI Platform

## Agenda

- [1. About the project](#1-about-the-project)
- [2. Tech stack](#2-tech-stack)
- [3. Quick start](#3-quick-start)
- [4. Configuration](#4-configuration)
- [5. Simulator load profiles](#5-simulator-load-profiles)
- [6. Testing](#6-testing)

## 1. About the project

This repository contains a compact real-time KPI platform for collecting events, calculating near real-time business metrics, and detecting anomalies.

The pipeline is built around four application services:

- `ingest-api` accepts order and session events and publishes them to Kafka.
- `stream-processor` consumes events, deduplicates them, and writes facts and aggregates to TimescaleDB.
- `alerting` checks KPI buckets against a baseline and stores generated alerts.
- `simulator` produces synthetic traffic for demos, testing, and load experiments.

The main KPI outputs are based on orders and session events:

- `revenue`
- `order_count`
- `view_count`
- `purchase_count`
- `average_order_value`
- `conversion_rate`

## 2. Tech stack

- Python
- FastAPI
- Kafka (KRaft)
- TimescaleDB / PostgreSQL
- Dynaconf
- Docker Compose
- Pytest

## 3. Quick start

1. Review local `.secrets.toml` files for each service.
1. Start the full stack:

```bash
docker compose up --build
```

1. Send sample events:

```bash
curl -X POST http://localhost:8000/events/order \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"order_id":"o-1","customer_id":"c-1","amount":120.5,"currency":"USD","channel":"web","event_time":"2026-02-03T10:00:00Z"}'

curl -X POST http://localhost:8000/events/session \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s-1","event_type":"view","channel":"web","event_time":"2026-02-03T10:00:05Z"}'
```

1. Check the latest aggregated data in TimescaleDB:

```sql
SELECT * FROM kpi_minute_view ORDER BY bucket DESC LIMIT 10;
```

The simulator is enabled by default. To disable synthetic traffic, set `ENABLED = false` in `services/simulator/settings.toml`.

## 4. Configuration

Each service uses Dynaconf with `settings.toml` for defaults and `.secrets.toml` for local overrides.

Example local overrides:

```toml
# services/ingest-api/.secrets.toml
[default]
KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"
DB_DSN = "postgresql://kpi:kpi@timescaledb:5432/kpi"
ALLOWED_ORIGINS = ["http://localhost:5173"]
API_KEY = "dev-key"

# services/stream-processor/.secrets.toml
[default]
DB_DSN = "postgresql://kpi:kpi@timescaledb:5432/kpi"

# services/alerting/.secrets.toml
[default]
DB_DSN = "postgresql://kpi:kpi@timescaledb:5432/kpi"

# services/simulator/.secrets.toml
[default]
API_KEY = "dev-key"
```

Main simulator settings are stored in `services/simulator/settings.toml`, including:

- traffic intensity
- anomaly probability
- scheduling mode
- channel and campaign pools
- simulator control API host and port

## 5. Simulator load profiles

The simulator sends synthetic order and session traffic to the ingestion API. You can tune load by changing the values in `services/simulator/settings.toml`.

### Normal

```toml
ENABLED = true
SEND_INTERVAL_SECONDS = 20
BASE_ORDERS_PER_TICK = 2
ORDER_COUNT_JITTER = 1.0
BASE_SESSIONS_PER_TICK = 6
SESSION_COUNT_JITTER = 2.0
MIN_VIEWS_PER_ORDER = 25
PRICE_LIST_RUB = [99.0, 129.0, 149.0, 199.0, 249.0]
ORDER_PROB = 0.04
ANOMALY_PROB = 0.02
ANOMALY_LOW_MULTIPLIER = 0.4
ANOMALY_HIGH_MULTIPLIER = 2.0
```

### Peak

```toml
ENABLED = true
SEND_INTERVAL_SECONDS = 10
BASE_ORDERS_PER_TICK = 5
ORDER_COUNT_JITTER = 2.0
BASE_SESSIONS_PER_TICK = 10
SESSION_COUNT_JITTER = 3.0
MIN_VIEWS_PER_ORDER = 20
PRICE_LIST_RUB = [99.0, 129.0, 149.0, 199.0, 249.0]
ORDER_PROB = 0.05
ANOMALY_PROB = 0.03
ANOMALY_LOW_MULTIPLIER = 0.5
ANOMALY_HIGH_MULTIPLIER = 2.5
```

### Quiet

```toml
ENABLED = true
SEND_INTERVAL_SECONDS = 30
BASE_ORDERS_PER_TICK = 1
ORDER_COUNT_JITTER = 0.5
BASE_SESSIONS_PER_TICK = 2
SESSION_COUNT_JITTER = 0.8
MIN_VIEWS_PER_ORDER = 30
PRICE_LIST_RUB = [99.0, 129.0, 149.0, 199.0, 249.0]
ORDER_PROB = 0.03
ANOMALY_PROB = 0.02
ANOMALY_LOW_MULTIPLIER = 0.4
ANOMALY_HIGH_MULTIPLIER = 1.8
```

### Schedule and fixed anomalies

```toml
SCHEDULE_MODE = "day-night"
PEAK_HOURS_UTC = [9, 10, 11, 12, 13]
QUIET_HOURS_UTC = [0, 1, 2, 3, 4, 5]
PEAK_MULTIPLIER = 1.6
QUIET_MULTIPLIER = 0.6
PEAK_ORDER_MULTIPLIER = 1.3
QUIET_ORDER_MULTIPLIER = 0.7

SCHEDULE_MODE = "seasonal"
SEASONAL_PEAK_HOURS_UTC = [10, 11, 12, 13, 14]
SEASONAL_EVENING_HOURS_UTC = [18, 19, 20, 21]
SEASONAL_PEAK_MULTIPLIER = 1.5
SEASONAL_EVENING_MULTIPLIER = 0.8
SEASONAL_PEAK_ORDER_MULTIPLIER = 1.2
SEASONAL_EVENING_ORDER_MULTIPLIER = 0.8

FIXED_ANOMALY_ENABLED = true
FIXED_ANOMALY_INTERVAL_MINUTES = 60
FIXED_ANOMALY_MODE = "alternate"
FIXED_ANOMALY_LOW_MULTIPLIER = 0.4
FIXED_ANOMALY_HIGH_MULTIPLIER = 2.0
```

## 6. Testing

Run unit tests for the backend services:

```bash
cd services/ingest-api
PYTHONPATH=src uv run pytest

cd ../stream-processor
PYTHONPATH=src uv run pytest

cd ../alerting
PYTHONPATH=src uv run pytest
```
