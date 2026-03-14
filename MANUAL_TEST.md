# Руководство по ручному тестированию (KPI, сегментация, алерты)

Этот документ нужен, чтобы вручную проверить систему и показать, что:
1) данные проходят сквозь весь конвейер (ingest → Kafka → stream → DB → API),
2) фильтры по `channel` и `campaign` работают,
3) алерты срабатывают только когда нужно (нет лишних).

Все даты и время указываются в UTC.
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
- Конверсия считается как **purchase_count / view_count**.
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
- average_order_value ≈ 93.33
- view_count = 2 (view)
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
- average_order_value = 100
- view_count = 1
- purchase_count = 1
- conversion_rate = 1 / 1 = 1.0

### 3.2 Фильтр `channel=ads`
```
Invoke-RestMethod -Method GET "http://localhost:8000/kpi/minute?from=2026-02-03T09:59:00Z&to=2026-02-03T10:01:00Z&channel=ads&campaign=spring" -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо:
- revenue ≈ 80
- order_count = 1
- average_order_value = 80
- view_count = 1
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

Проверяем на текущих настройках алертинга (как в репозитории сейчас):

В `services/alerting/settings.toml`:
```
BASELINE_DAYS = 1
THRESHOLD_PCT = 1.0
VIEW_THRESHOLD_PCT = 0.5
MIN_BASELINE = 1
LOOKBACK_MINUTES = 10
CURRENT_WINDOW_MINUTES = 5
DURATION_MINUTES = 3
INTERVAL_SECONDS = 60
```

### 6.1 Проверка алерта по `revenue`
Запускай желательно в начале минуты, а не в конце, чтобы не было проблем.

Базовый уровень (вчера, минуты -3/-2/-1), по 100 в каждую минуту:
```
$run = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

for ($m = 3; $m -ge 1; $m--) {
  Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body ("{`"order_id`":`"o-rev-base-" + $run + "-" + $m + "`",`"amount`":100,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddDays(-1).AddMinutes(-$m).ToString("o") + "`"}")
}
```

Аномалия сегодня (минуты -3/-2/-1), по 250 в каждую минуту (рост > 100%):
```
for ($m = 3; $m -ge 1; $m--) {
  Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body ("{`"order_id`":`"o-rev-high-" + $run + "-" + $m + "`",`"amount`":250,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddMinutes(-$m).ToString("o") + "`"}")
}
```

Подожди 3–4 минуты и проверь:
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-20).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o") + "&kpi=revenue") -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо:
- есть алерт с `kpi = "revenue"`
- `alert_type = "revenue"`
- `direction = "up"`
- `delta_pct >= 1.0` (превышение порога 100%)

### 6.2 Проверка алерта по `view_count`
База вчера (минуты -3/-2/-1): по 40 view-событий в минуту
```
$run = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

for ($m = 3; $m -ge 1; $m--) {
  for ($i = 1; $i -le 40; $i++) {
    Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body ("{`"session_id`":`"s-view-base-" + $run + "-" + $m + "-" + $i + "`",`"event_type`":`"view`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddDays(-1).AddMinutes(-$m).ToString("o") + "`"}")
  }
}
```

Аномалия сегодня (минуты -3/-2/-1): по 10 view-событий в минуту
```
for ($m = 3; $m -ge 1; $m--) {
  for ($i = 1; $i -le 10; $i++) {
    Invoke-RestMethod -Method POST "http://localhost:8000/events/session" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body ("{`"session_id`":`"s-view-low-" + $run + "-" + $m + "-" + $i + "`",`"event_type`":`"view`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddMinutes(-$m).ToString("o") + "`"}")
  }
}
```

Подожди 3–4 минуты и проверь:
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-20).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o") + "&kpi=views") -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо:
- есть алерт с `kpi = "view_count"`
- `alert_type = "views"`
- `direction = "down"`
- `delta_pct <= -0.5` (так как порог 50%)

---

## 7) Проверка фильтрации алертов
### 7.1 Общий список
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-20).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o")) -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо: в `items` могут быть алерты обоих типов (`revenue` и `view_count`).

### 7.2 Фильтр по выручке
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-20).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o") + "&kpi=revenue") -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо: только записи с `kpi = "revenue"` и `alert_type = "revenue"`.

### 7.3 Фильтр по просмотрам
```
Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-20).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o") + "&kpi=views") -Headers @{ "X-API-Key" = "dev-key" }
```

Ожидаемо: только записи с `kpi = "view_count"` и `alert_type = "views"`.

---

## 8) Проверка “без ложных алертов”

Сохрани количество алертов до отправки:
```
$before = (Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-20).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o")) -Headers @{ "X-API-Key" = "dev-key" }).items.Count
```

Отправь нормальные данные (без аномалии):
```
$run = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
Invoke-RestMethod -Method POST "http://localhost:8000/events/order" -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body ("{`"order_id`":`"o-rev-normal-" + $run + "`",`"amount`":100,`"currency`":`"USD`",`"channel`":`"web`",`"campaign`":`"spring`",`"event_time`":`"" + (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("o") + "`"}")
```

Подожди 3–4 минуты, затем проверь:
```
$after = (Invoke-RestMethod -Method GET ("http://localhost:8000/alerts?from=" + (Get-Date).ToUniversalTime().AddMinutes(-20).ToString("o") + "&to=" + (Get-Date).ToUniversalTime().ToString("o")) -Headers @{ "X-API-Key" = "dev-key" }).items.Count
"before=$before after=$after"
```

Ожидаемо: `after` не больше `before` из-за этого шага (новый алерт не добавился).

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
