# Real-time KPI Platform (Kafka + TimescaleDB + FastAPI)

This repository provides a compact, production‑leaning real‑time KPI platform for SMB teams: ingestion API, Kafka (KRaft), a stream processor, TimescaleDB, and alerting.

## Quick Start
1. Review each service `.secrets.toml` (local only, ignored by git).
2. Start the stack:
   ```bash
   docker compose up --build
   ```
3. Send sample events (API key required):
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
4. Inspect KPIs:
   - TimescaleDB: `SELECT * FROM kpi_minute_view ORDER BY bucket DESC LIMIT 10;`

Simulator is enabled by default. To stop synthetic traffic, set `ENABLED = false` in `services/simulator/settings.toml`.

## Simulator Load Profiles
Below are sample profiles for `services/simulator/settings.toml`. Copy one block and tune as needed.

### Normal
```
ENABLED = true
SEND_INTERVAL_SECONDS = 20
BASE_ORDERS_PER_TICK = 2
ORDER_COUNT_JITTER = 1.0
BASE_SESSIONS_PER_TICK = 4
SESSION_COUNT_JITTER = 1.5
ORDER_BASE_AMOUNT_RUB = 1200.0
ORDER_AMOUNT_STDDEV = 150.0
ANOMALY_PROB = 0.02
ANOMALY_LOW_MULTIPLIER = 0.4
ANOMALY_HIGH_MULTIPLIER = 2.0
```

### Peak
```
ENABLED = true
SEND_INTERVAL_SECONDS = 10
BASE_ORDERS_PER_TICK = 5
ORDER_COUNT_JITTER = 2.0
BASE_SESSIONS_PER_TICK = 10
SESSION_COUNT_JITTER = 3.0
ORDER_BASE_AMOUNT_RUB = 1300.0
ORDER_AMOUNT_STDDEV = 200.0
ANOMALY_PROB = 0.03
ANOMALY_LOW_MULTIPLIER = 0.5
ANOMALY_HIGH_MULTIPLIER = 2.5
```

### Quiet
```
ENABLED = true
SEND_INTERVAL_SECONDS = 30
BASE_ORDERS_PER_TICK = 1
ORDER_COUNT_JITTER = 0.5
BASE_SESSIONS_PER_TICK = 2
SESSION_COUNT_JITTER = 0.8
ORDER_BASE_AMOUNT_RUB = 900.0
ORDER_AMOUNT_STDDEV = 120.0
ANOMALY_PROB = 0.02
ANOMALY_LOW_MULTIPLIER = 0.4
ANOMALY_HIGH_MULTIPLIER = 1.8
```

### Schedule and Fixed Anomalies
```
SCHEDULE_MODE = "day-night"
PEAK_HOURS_UTC = [9, 10, 11, 12, 13]
QUIET_HOURS_UTC = [0, 1, 2, 3, 4, 5]
PEAK_MULTIPLIER = 1.6
QUIET_MULTIPLIER = 0.6

SCHEDULE_MODE = "seasonal"
SEASONAL_PEAK_HOURS_UTC = [10, 11, 12, 13, 14]
SEASONAL_EVENING_HOURS_UTC = [18, 19, 20, 21]
SEASONAL_PEAK_MULTIPLIER = 1.5
SEASONAL_EVENING_MULTIPLIER = 0.8

FIXED_ANOMALY_ENABLED = true
FIXED_ANOMALY_INTERVAL_MINUTES = 60
FIXED_ANOMALY_MODE = "alternate"
FIXED_ANOMALY_LOW_MULTIPLIER = 0.4
FIXED_ANOMALY_HIGH_MULTIPLIER = 2.0
```

## Architecture
- `ingest-api`: FastAPI service for accepting events and publishing to Kafka.
- `stream-processor`: Kafka consumer with dedupe, aggregation, and TimescaleDB writes.
- `alerting`: periodic SQL checks writing alerts into `alerts`.
- `simulator`: optional synthetic traffic generator for demo/testing.
- `timescaledb`: event facts + KPI aggregates.

## How it Works (Detailed)
1. **Events hit the ingestion API**  
   Clients send JSON payloads with `event_time` and domain fields.  
   FastAPI validates the schema and stamps `received_at`, then publishes to Kafka.

2. **Kafka (KRaft) stores events by topic**  
   `orders` and `sessions` are separate topics for clarity and parallelism.

3. **Stream processor normalizes and deduplicates**  
   It stamps `processed_at`, normalizes timestamps to UTC, and applies a short TTL‑based dedupe window.

4. **Facts are persisted in TimescaleDB**  
   Orders go to `orders`, session events to `sessions`.  
   Fact tables include `event_time`, `received_at`, `processed_at` for latency/freshness analysis.

5. **Minute/hour KPI aggregates**  
   Aggregates are stored in `kpi_minute` and `kpi_hour` (revenue, counts, etc.).  
   Views (`kpi_minute_view`, `kpi_hour_view`) add derived metrics like conversion.

6. **Alerting compares against a seasonal baseline**  
   Every minute it compares the latest closed bucket to past data from the same weekday/time.  
   Threshold breaches create a row in `alerts`.

7. **Key technical metrics**  
   - **Latency**: `processed_at - event_time`  
   - **Freshness**: `now - max(event_time)`  
   - **Deduplication**: ratio of unique IDs vs total events  
   These are computed from the database plus lightweight logs.

## Configuration
Each service uses Dynaconf with `settings.toml` (defaults) and `.secrets.toml` (local overrides).

Examples:
```
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

## Endpoints
All endpoints require `X-API-Key` header.
- `POST /events/order` — order event
- `POST /events/session` — session step (`view`, `checkout`, `purchase`)
- `GET /health` — healthcheck
- `GET /kpi/latest?bucket=minute|hour` — latest KPI point
- `GET /kpi/minute?from=...&to=...&limit=...&channel=...&campaign=...` — minute series
- `GET /kpi/hour?from=...&to=...&limit=...&channel=...&campaign=...` — hour series
- `GET /alerts?from=...&to=...&limit=...` — alerts list
- `GET /metrics/freshness?channel=...&campaign=...` — freshness indicator
- `GET /metrics/time-to-signal?bucket=minute|hour&from=...&to=...&channel=...&campaign=...` — time-to-signal

## Frontend API Details
All timestamps are ISO‑8601 strings in UTC.

### `GET /kpi/latest`
- Query: `bucket` (`minute` | `hour`, default `minute`)
- Optional filters: `channel`, `campaign`
- Response: latest KPI point with conversion rate.

### `GET /kpi/minute`
- Query:
  - `from` (optional, ISO datetime)
  - `to` (optional, ISO datetime)
  - `limit` (optional, default 2000, max 5000)
  - `channel` (optional)
  - `campaign` (optional)
- Default window: last 2 hours.

### `GET /kpi/hour`
- Query:
  - `from` (optional, ISO datetime)
  - `to` (optional, ISO datetime)
  - `limit` (optional, default 2000, max 5000)
  - `channel` (optional)
  - `campaign` (optional)
- Default window: last 3 days.

### `GET /alerts`
- Query:
  - `from` (optional, ISO datetime)
  - `to` (optional, ISO datetime)
  - `limit` (optional, default 500, max 2000)
- Default window: last 24 hours.

### `GET /metrics/freshness`
- Optional filters: `channel`, `campaign`
- Returns latest event timestamps and freshness in seconds for orders and sessions.

### `GET /metrics/time-to-signal`
- Query:
  - `bucket` (`minute` | `hour`, default `minute`)
  - `from` / `to` (optional)
  - `channel` (optional)
  - `campaign` (optional)
- Returns average and max time‑to‑signal for orders and sessions.

## SQL Safety
All queries are parameterized. The only dynamic column name (KPI in alerting) is strictly validated against a whitelist to prevent injection.

## Repository Layout
```
db/init/
services/
  ingest-api/
    settings.toml
  stream-processor/
    settings.toml
  alerting/
    settings.toml
docker-compose.yml
```

## Local Development (uv)
Each service is a separate Python project:
```
cd services/ingest-api
uv sync
PYTHONPATH=src uv run python -m ingest_api.main
```

## Tests
```
cd services/ingest-api
PYTHONPATH=src uv run pytest

cd ../stream-processor
PYTHONPATH=src uv run pytest

cd ../alerting
PYTHONPATH=src uv run pytest
```
