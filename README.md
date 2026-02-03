# Real-time KPI Platform (Kafka + TimescaleDB + FastAPI)

This repository provides a compact, production‑leaning real‑time KPI platform for SMB teams: ingestion API, Kafka (KRaft), a stream processor, TimescaleDB, Grafana, and alerting.

## Quick Start
1. Review each service `.secrets.toml` (local only, ignored by git).
2. Start the stack:
   ```bash
   docker compose up --build
   ```
3. Send sample events:
   ```bash
   curl -X POST http://localhost:8000/events/order \
     -H "Content-Type: application/json" \
     -d '{"order_id":"o-1","customer_id":"c-1","amount":120.5,"currency":"USD","channel":"web","event_time":"2026-02-03T10:00:00Z"}'

   curl -X POST http://localhost:8000/events/session \
     -H "Content-Type: application/json" \
     -d '{"session_id":"s-1","event_type":"view","channel":"web","event_time":"2026-02-03T10:00:05Z"}'
   ```
4. Inspect KPIs:
   - Grafana: http://localhost:3000 (admin/admin)
   - TimescaleDB: `SELECT * FROM kpi_minute_view ORDER BY bucket DESC LIMIT 10;`

## Architecture
- `ingest-api`: FastAPI service for accepting events and publishing to Kafka.
- `stream-processor`: Kafka consumer with dedupe, aggregation, and TimescaleDB writes.
- `alerting`: periodic SQL checks writing alerts into `alerts`.
- `timescaledb`: event facts + KPI aggregates.
- `grafana`: KPI visualization.

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

6. **Grafana queries aggregates directly**  
   Dashboards stay fast because aggregates are precomputed in the database.

7. **Alerting compares against a seasonal baseline**  
   Every minute it compares the latest closed bucket to past data from the same weekday/time.  
   Threshold breaches create a row in `alerts`.

8. **Key technical metrics**  
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

# services/stream-processor/.secrets.toml
[default]
DB_DSN = "postgresql://kpi:kpi@timescaledb:5432/kpi"

# services/alerting/.secrets.toml
[default]
DB_DSN = "postgresql://kpi:kpi@timescaledb:5432/kpi"
```

## Endpoints
- `POST /events/order` — order event
- `POST /events/session` — session step (`view`, `checkout`, `purchase`)
- `GET /health` — healthcheck
- `GET /kpi/latest?bucket=minute|hour` — latest KPI point
- `GET /kpi/minute?from=...&to=...&limit=...` — minute series
- `GET /kpi/hour?from=...&to=...&limit=...` — hour series
- `GET /alerts?from=...&to=...&limit=...` — alerts list

## Frontend API Details
All timestamps are ISO‑8601 strings in UTC.

### `GET /kpi/latest`
- Query: `bucket` (`minute` | `hour`, default `minute`)
- Response: latest KPI point with conversion rate.

### `GET /kpi/minute`
- Query:
  - `from` (optional, ISO datetime)
  - `to` (optional, ISO datetime)
  - `limit` (optional, default 2000, max 5000)
- Default window: last 2 hours.

### `GET /kpi/hour`
- Query:
  - `from` (optional, ISO datetime)
  - `to` (optional, ISO datetime)
  - `limit` (optional, default 2000, max 5000)
- Default window: last 3 days.

### `GET /alerts`
- Query:
  - `from` (optional, ISO datetime)
  - `to` (optional, ISO datetime)
  - `limit` (optional, default 500, max 2000)
- Default window: last 24 hours.

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
