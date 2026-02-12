# Руководство по ручному тестированию (KPI, сегментация, алерты)

Этот документ нужен, чтобы вручную проверить систему и показать, что:
1) данные проходят сквозь весь конвейер (ingest → Kafka → stream → DB → API),
2) фильтры по `channel` и `campaign` работают,
3) алерты срабатывают только когда нужно (нет лишних).

Все даты и время указываются в ISO‑8601 UTC.
Все запросы требуют `X-API-Key`.

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

Сессии:
- `web + spring`: 1 `view` + 1 `purchase`
- `ads + spring`: 1 `view`

PowerShell (одна строка на запрос):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body '{"order_id":"o-1","amount":120.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:00Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body '{"order_id":"o-2","amount":80.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:10Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body '{"order_id":"o-3","amount":80.0,"currency":"USD","channel":"ads","campaign":"spring","event_time":"2026-02-03T10:00:20Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body '{"session_id":"s-1","event_type":"view","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:05Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body '{"session_id":"s-1","event_type":"purchase","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:25Z"}'
Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body '{"session_id":"s-2","event_type":"view","channel":"ads","campaign":"spring","event_time":"2026-02-03T10:00:30Z"}'
```

Подожди 10–15 секунд, чтобы stream‑processor сбросил агрегаты.

### 2.2 Проверяем KPI (без фильтров)
```
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z" -Headers @{ "X-API-Key" = "dev-key" }
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
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=web&campaign=spring" -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо:
- revenue ≈ 200
- order_count = 2
- session_count = 1
- purchase_count = 1
- conversion_rate = 1 / 1 = 1.0

### 3.2 Фильтр `channel=ads`
```
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=ads&campaign=spring" -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо:
- revenue ≈ 80
- order_count = 1
- session_count = 1
- purchase_count = 0
- conversion_rate = 0 / 1 = 0.0

---

## 4) Freshness (UX‑индикатор свежести)
```
Invoke-RestMethod -Method GET "http://localhost:8000/metrics/freshness?channel=web&campaign=spring" -Headers @{ "X-API-Key" = "dev-key" }
```

---

## 5) Time‑to‑Signal
```
Invoke-RestMethod -Method GET "http://localhost:8000/metrics/time-to-signal?bucket=minute&from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=web&campaign=spring" -Headers @{ "X-API-Key" = "dev-key" }
```

---

## 6) Алерты

Для быстрого теста уменьшаем пороги и задаём окно:

В `services/alerting/settings.toml`:
```
BASELINE_DAYS = 1
THRESHOLD_PCT = 0.1
MIN_BASELINE = 1
LOOKBACK_MINUTES = 10
CURRENT_WINDOW_MINUTES = 5
DURATION_MINUTES = 3
```

Перезапусти только alerting:
```
docker compose up -d --build alerting
```

### 6.1 Базовый уровень (вчера, та же минута)
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body '{"order_id":"o-baseline","amount":100.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-02T10:00:00Z"}'
```

### 6.2 Аномалия сегодня (сильное падение)
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body '{"order_id":"o-drop","amount":10.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:00:00Z"}'
```

Подожди минуту. Алертинг берёт самый свежий KPI‑бакет в окне lookback.

### 6.3 Проверяем алерт
```
Invoke-RestMethod -Method GET "http://localhost:8000/alerts?from=2026-02-03T09:55:00Z&to=2026-02-03T10:05:00Z" -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо:
- один алерт с `direction = "down"` и `delta_pct ≈ -0.9`

---

## 7) Полный тест (гарантированно)
Шаг A — baseline (вчера, минута‑1):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body ("{`"order_id`":`"o-baseline3`",`"amount`":100,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddDays(-1).AddMinutes(-1).ToString("o") + "`"}")
```

Шаг B — аномалия (сегодня, минута‑1):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body ("{`"order_id`":`"o-drop3`",`"amount`":10,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("o") + "`"}")
```

Шаг C — подожди минуту и проверь:
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-10).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o")) -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо: появился новый алерт.

Шаг D — нормальные данные (не должны дать новый алерт):
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body ("{`"order_id`":`"o-normal3`",`"amount`":100,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("o") + "`"}")
```

Шаг E — подожди минуту и проверь:
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-10).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o")) -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо: **новый алерт не появился**.

---

## 8) Проверка “без ложных алертов”

### 8.1 Нормальные данные (как baseline)
```
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body '{"order_id":"o-normal","amount":100.0,"currency":"USD","channel":"web","campaign":"spring","event_time":"2026-02-03T10:01:00Z"}'
```

### 8.2 Проверяем алерты
```
Invoke-RestMethod -Method GET "http://localhost:8000/alerts?from=2026-02-03T10:00:00Z&to=2026-02-03T10:02:00Z" -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо:
- новых алертов нет

---

## 9) Дополнительная SQL‑проверка
```
SELECT * FROM kpi_minute_view ORDER BY bucket DESC LIMIT 10;
SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10;
```

---

## 10) Примечания
- Если таблиц нет, скорее всего переиспользован volume. Выполни:
  ```
  docker compose down -v
  docker compose up --build
  ```
- Алерты считаются по самому свежему KPI‑бакету за последние `LOOKBACK_MINUTES`.
