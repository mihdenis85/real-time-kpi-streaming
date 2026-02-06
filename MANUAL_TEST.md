# Руководство по ручному тестированию (KPI, сегментация, алерты)

Этот документ нужен, чтобы вручную проверить систему и показать, что:
1) данные проходят сквозь весь конвейер (ingest → Kafka → stream → DB → API),
2) фильтры по `channel` и `campaign` работают,
3) алерты срабатывают только когда нужно (нет лишних).

Все даты и время указываются в ISO‑8601 UTC.

## 0) Чистый старт
TimescaleDB выполняет init‑скрипты только при первом создании volume.
Чтобы применить схему:

```
docker compose down -v
docker compose up --build
```

Дождись, пока все контейнеры будут healthy.

---

## 1) Модель данных и зачем она такая

Мы отправляем **два типа событий**:
- **Order** — влияет на выручку и количество заказов.
- **Session** — влияет на конверсию и шаги воронки.

Оба события содержат:
- `event_time` (время, к которому относится KPI),
- опциональные `channel` и `campaign` (для сегментации).

### Почему этих полей достаточно
- Выручка и количество заказов считаются по **orders**.
- Конверсия считается как **purchase_count / session_count**.
- Сегментация работает, потому что **и orders, и sessions** несут одинаковые измерения (`channel`, `campaign`).

---

## 2) Базовая проверка end‑to‑end

### 2.1 Отправляем небольшой, понятный набор данных
Это даст один “чистый” минутный бакет:

Orders:
- 2 заказа в `web + spring` на сумму 200
- 1 заказ в `ads + spring` на сумму 80

Заказ — это факт покупки, он увеличивает выручку и количество заказов.

Sessions:
- `web + spring`: 1 `view` + 1 `purchase`
- `ads + spring`: 1 `view`

Сессии — это шаги воронки, они влияют на конверсию.

PowerShell (одна строка на запрос):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-1","amount":120.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:00Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-2","amount":80.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:10Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-3","amount":80.0,"currency":"USD","channel":"ads","campaign":"spring","event_time":"2026-02-03T10:00:20Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -ContentType "application/json" -Body '{"session_id":"s-1","event_type":"view","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:05Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -ContentType "application/json" -Body '{"session_id":"s-1","event_type":"purchase","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:25Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -ContentType "application/json" -Body '{"session_id":"s-2","event_type":"view","channel":"ads","campaign":"spring","event_time":"2026-02-03T10:00:30Z"}'
```

Подожди 10–15 секунд, чтобы stream‑processor сбросил агрегаты.

### 2.2 Проверяем KPI (без фильтров)
```
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z"
```

Ожидаемо для бакета `10:00`:
- revenue ≈ 280
- order_count = 3
- session_count = 2 (view)
- purchase_count = 1
- conversion_rate = 1 / 2 = 0.5

---

## 3) Проверка сегментации

### 3.1 Фильтр `channel=web`
```
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=web&campaign=spring"
```

Ожидаемо:
- revenue ≈ 200
- order_count = 2
- session_count = 1
- purchase_count = 1
- conversion_rate = 1 / 1 = 1.0

### 3.2 Фильтр `channel=ads`
```
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=ads&campaign=spring"
```

Ожидаемо:
- revenue ≈ 80
- order_count = 1
- session_count = 1
- purchase_count = 0
- conversion_rate = 0 / 1 = 0.0

Это подтверждает сегментацию по `channel` и `campaign`.

---

## 4) Freshness (UX‑индикатор свежести)
```
Invoke-RestMethod -Method GET "http://localhost:8000/metrics/freshness?channel=web&campaign=spring"
```

Ожидаемо:
- `orders_last_event_time` и `sessions_last_event_time` близки к отправленным
- `orders_freshness_seconds` и `sessions_freshness_seconds` маленькие

---

## 5) Time‑to‑Signal
```
Invoke-RestMethod -Method GET "http://localhost:8000/metrics/time-to-signal?bucket=minute&from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=web&campaign=spring"
```

Ожидаемо:
- `orders.avg_seconds` > 0
- `sessions.avg_seconds` > 0
- значения обычно в пределах нескольких секунд

---

## 6) Алерты

По умолчанию алертинг использует 7‑дневную сезонность.  
Для быстрого теста уменьшаем пороги и даём короткое окно lookback.

В `services/alerting/settings.toml`:
```
BASELINE_DAYS = 1
THRESHOLD_PCT = 0.1
MIN_BASELINE = 1
LOOKBACK_MINUTES = 10
```

Перезапусти только alerting:
```
docker compose up -d --build alerting
```

### 6.1 Базовый уровень (вчера, та же минута)
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-baseline","amount":100.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-02T10:00:00Z"}'
```

Подожди 10–15 секунд.

### 6.2 Аномалия сегодня (сильное падение)
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-drop","amount":10.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:00Z"}'
```

Подожди минуту. Алертинг берёт самый свежий KPI‑бакет в окне lookback.

### 6.3 Проверяем алерт
```
Invoke-RestMethod -Method GET "http://localhost:8000/alerts?from=2026-02-03T09:55:00Z&to=2026-02-03T10:05:00Z"
```

Ожидаемо:
- один алерт с `direction = "down"` и `delta_pct ≈ -0.9`

### 6.4 Полный тест (гарантированно)
Шаг A — baseline (вчера, минута‑1):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body ("{`"order_id`":`"o-baseline3`",`"amount`":100,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddDays(-1).AddMinutes(-1).ToString("o") + "`"}")
```

Шаг B — аномалия (сегодня, минута‑1):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body ("{`"order_id`":`"o-drop3`",`"amount`":10,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("o") + "`"}")
```

Шаг C — подожди минуту и проверь:
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-10).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o"))
```

Ожидаемо: появился новый алерт.

Шаг D — нормальные данные (не должны дать новый алерт):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body ("{`"order_id`":`"o-normal3`",`"amount`":100,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("o") + "`"}")
```

Шаг E — подожди минуту и проверь:
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-10).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o"))
```

Ожидаемо: **новый алерт не появился**.

---

## 7) Проверка “без ложных алертов”

Цель: убедиться, что при нормальных данных алерты не появляются.

### 7.1 Нормальные данные (как baseline)
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-normal","amount":100.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:01:00Z"}'
```

Подожди минуту.

### 7.2 Проверяем алерты
```
Invoke-RestMethod -Method GET "http://localhost:8000/alerts?from=2026-02-03T10:00:00Z&to=2026-02-03T10:02:00Z"
```

Ожидаемо:
- новых алертов нет

---

## 8) Дополнительная SQL‑проверка
```
SELECT * FROM kpi_minute_view ORDER BY bucket DESC LIMIT 10;
SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10;
```

---

## Примечания
- Если таблиц нет, скорее всего переиспользован volume. Выполни:
  ```
  docker compose down -v
  docker compose up --build
  ```
- Алерты считаются по самому свежему KPI‑бакету за последние `LOOKBACK_MINUTES`.
# Manual Test Guide (KPI, Segmentation, Alerts)

This guide is designed to validate the system manually and demonstrate that:
1) data flows end‑to‑end (ingest → Kafka → stream → DB → API),
2) segmentation by `channel` and `campaign` works,
3) alerts trigger only when they should (no false positives).

All timestamps use ISO‑8601 UTC.

## 0) Clean Start
TimescaleDB runs init scripts only on first volume creation.
To ensure schema changes are applied:

```
docker compose down -v
docker compose up --build
```

Wait until all containers are healthy.

---

## 1) Data Model and Why It Works

We send **two types of events**:
- **Order event**: drives revenue and order count.
- **Session event**: drives session, checkout, and purchase counts.

Both carry:
- `event_time` (the time KPI should be attributed to),
- optional `channel` and `campaign` (segmentation dimensions).

### Why these fields are enough
- Revenue and order count come from **orders**.
- Conversion is computed as **purchase_count / session_count**.
- Segmentation works because **both orders and sessions store the same dimensions** (`channel`, `campaign`).

---

## 2) Base End‑to‑End Check

### 2.1 Send a small, consistent dataset
This creates a clean minute bucket with clear values:

Orders:
- 2 orders in `web + spring` for total revenue 200
- 1 order in `ads + spring` for revenue 80

Orders are purchase transactions. Each order represents a completed sale
and contributes to revenue and order count.

Sessions:
- `web + spring`: 1 view + 1 purchase
- `ads + spring`: 1 view only

Sessions are user journeys (steps in the funnel). A single session can
include multiple steps like `view`, `checkout`, and `purchase`, and these
steps drive session count and conversion rate.

PowerShell (one line each):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-1","amount":120.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:00Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-2","amount":80.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:10Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-3","amount":80.0,"currency":"USD","channel":"ads","campaign":"spring","event_time":"2026-02-03T10:00:20Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -ContentType "application/json" -Body '{"session_id":"s-1","event_type":"view","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:05Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -ContentType "application/json" -Body '{"session_id":"s-1","event_type":"purchase","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:25Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -ContentType "application/json" -Body '{"session_id":"s-2","event_type":"view","channel":"ads","campaign":"spring","event_time":"2026-02-03T10:00:30Z"}'
```

Wait ~10–15 seconds for the stream processor flush.

### 2.2 Check KPI (no filters)
```
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z"
```
Expected for the bucket `10:00`:
- revenue ≈ 280
- order_count = 3
- session_count = 2 (views only)
- purchase_count = 1
- conversion_rate = 1 / 2 = 0.5

---

## 3) Segmentation Check

### 3.1 Filter by `channel=web`
```
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=web&campaign=spring"
```
Expected:
- revenue ≈ 200 (only web orders)
- order_count = 2
- session_count = 1 (web view)
- purchase_count = 1
- conversion_rate = 1 / 1 = 1.0

### 3.2 Filter by `channel=ads`
```
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=ads&campaign=spring"
```
Expected:
- revenue ≈ 80 (ads order)
- order_count = 1
- session_count = 1 (ads view)
- purchase_count = 0
- conversion_rate = 0 / 1 = 0.0

This proves segmentation by both `channel` and `campaign`.

---

## 4) Freshness (UX Indicator)

```
Invoke-RestMethod -Method GET "http://localhost:8000/metrics/freshness?channel=web&campaign=spring"
```

Expected:
- `orders_last_event_time` and `sessions_last_event_time` close to the times you sent
- `orders_freshness_seconds` and `sessions_freshness_seconds` are small (if you test immediately)

---

## 5) Time‑to‑Signal

```
Invoke-RestMethod -Method GET "http://localhost:8000/metrics/time-to-signal?bucket=minute&from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=web&campaign=spring"
```

Expected:
- `orders.avg_seconds` > 0
- `sessions.avg_seconds` > 0
- values are typically seconds to tens of seconds (depends on processing delay)

---

## 6) Alerts

By default, alerts use a 7‑day seasonal baseline. For fast manual testing, reduce thresholds and allow a short lookback window:

In `services/alerting/settings.toml`:
```
BASELINE_DAYS = 1
THRESHOLD_PCT = 0.1
MIN_BASELINE = 1
LOOKBACK_MINUTES = 10
```

Restart only alerting:
```
docker compose up -d --build alerting
```

### 6.1 Create a baseline (yesterday at same minute)
Send a “normal” revenue:
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-baseline","amount":100.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-02T10:00:00Z"}'
```

Wait ~10–15 seconds for processing.

### 6.2 Create an anomaly today (big drop)
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-drop","amount":10.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:00Z"}'
```

Wait one minute. Alerting checks the most recent KPI bucket within the lookback window.

### 6.3 Verify alert exists
```
Invoke-RestMethod -Method GET "http://localhost:8000/alerts?from=2026-02-03T09:55:00Z&to=2026-02-03T10:05:00Z"
```

Expected:
- One alert with `direction = "down"` and `delta_pct` roughly ‑0.9

### 6.4 Full alerting test (guaranteed)
Use these steps to force one alert and then confirm no new alerts.

Step A — Baseline (yesterday, same minute):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body ("{`"order_id`":`"o-baseline3`",`"amount`":100,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddDays(-1).AddMinutes(-1).ToString("o") + "`"}")
```

Step B — Anomaly (today, same minute with large drop):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body ("{`"order_id`":`"o-drop3`",`"amount`":10,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("o") + "`"}")
```

Step C — Wait one minute, then check alerts:
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-10).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o"))
```

Expected: a new alert with `direction = "down"`.

Step D — Normal data (should NOT trigger):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body ("{`"order_id`":`"o-normal3`",`"amount`":100,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("o") + "`"}")
```

Step E — Wait one minute, then check alerts again:
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-10).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o"))
```

Expected: no new alert should appear.

---

## 7) No‑False‑Alerts Check

Goal: prove the system **does not raise alerts** during normal conditions.

### 7.1 Send “normal” data (same as baseline)
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -ContentType "application/json" -Body '{"order_id":"o-normal","amount":100.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:01:00Z"}'
```

Wait one minute.

### 7.2 Check alerts
```
Invoke-RestMethod -Method GET "http://localhost:8000/alerts?from=2026-02-03T10:00:00Z&to=2026-02-03T10:02:00Z"
```

Expected:
- **No new alert** for the normal bucket.

This validates **low false positive rate** for stable conditions.

---

## 8) Optional SQL Verification

```
SELECT * FROM kpi_minute_view ORDER BY bucket DESC LIMIT 10;
SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10;
```

---

## Notes
- If tables are missing, you likely reused the DB volume. Run:
  ```
  docker compose down -v
  docker compose up --build
  ```
- Alerts are evaluated on the last closed minute (current minute minus one).
