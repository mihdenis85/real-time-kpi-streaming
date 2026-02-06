# Руководство для фронтенда

Ниже описано, как фронтенд может работать с системой: какие ручки дергать, как часто и какие данные отправлять для теста.

## 1) Базовые URL
- API: `http://localhost:8000`
- Grafana (опционально): `http://localhost:3000`

Все даты/время передаются в ISO‑8601 (UTC), например: `2026-02-05T10:39:47Z`.

---

## 2) Отправка тестовых данных (с фронта)

Фронтенд может отправлять события напрямую:

### 2.1 Заказ
`POST /events/order`

Пример тела:
```
{
  "order_id": "o-123",
  "amount": 120.5,
  "currency": "USD",
  "channel": "web",
  "campaign": "spring",
  "event_time": "2026-02-05T10:39:00Z"
}
```

### 2.2 Сессия (шаг воронки)
`POST /events/session`

Пример тела:
```
{
  "session_id": "s-777",
  "event_type": "view",
  "channel": "web",
  "campaign": "spring",
  "event_time": "2026-02-05T10:39:05Z"
}
```

`event_type` может быть: `view`, `checkout`, `purchase`.

---

## 3) Получение KPI (основные ручки)

### 3.1 Последняя точка KPI
`GET /kpi/latest?bucket=minute|hour`

Пример:
```
GET /kpi/latest?bucket=minute
```

### 3.2 KPI по минутам
`GET /kpi/minute?from=...&to=...&limit=...&channel=...&campaign=...`

Пример:
```
GET /kpi/minute?from=2026-02-05T10:00:00Z&to=2026-02-05T11:00:00Z&channel=web&campaign=spring
```

### 3.3 KPI по часам
`GET /kpi/hour?from=...&to=...&limit=...&channel=...&campaign=...`

---

## 4) Фильтры сегментации
В KPI‑запросах доступны:
- `channel` (например: `web`, `ads`, `marketplace`)
- `campaign` (например: `spring`, `email_01`)

Это позволяет строить графики по сегментам.

---

## 5) UX‑метрики (для отображения пользователю)

### 5.1 Freshness (насколько свежие данные)
`GET /metrics/freshness?channel=...&campaign=...`

Ответ содержит:
- `orders_last_event_time`
- `sessions_last_event_time`
- `orders_freshness_seconds`
- `sessions_freshness_seconds`

### 5.2 Time‑to‑signal
`GET /metrics/time-to-signal?bucket=minute|hour&from=...&to=...&channel=...&campaign=...`

Ответ:
- среднее и максимальное время появления сигнала по заказам и сессиям.

---

## 6) Алерты

`GET /alerts?from=...&to=...&limit=...`

Пример:
```
GET /alerts?from=2026-02-05T10:00:00Z&to=2026-02-05T11:00:00Z
```

Ответ включает:
`current_value`, `baseline_value`, `delta_pct`, `direction`.

---

## 7) Рекомендованные интервалы опроса

Почему нужны интервалы:
- KPI пишутся пачками (обычно раз в 10 сек).
- Алерты пересчитываются раз в 60 сек.

### Рекомендации
- KPI минутные: каждые **10–15 сек**
- KPI часовые: каждые **30–60 сек**
- Freshness: каждые **15–30 сек**
- Alerts: каждые **60 сек**

---

## 8) Как строить графики

Ниже минимальный набор графиков:

1) **Выручка по минутам**  
Данные: `GET /kpi/minute`  
Поле для оси Y: `revenue`, ось X: `bucket`.

2) **Количество заказов по минутам**  
Данные: `GET /kpi/minute`  
Поле Y: `order_count`.

3) **Конверсия по минутам**  
Данные: `GET /kpi/minute`  
Поле Y: `conversion_rate`.

4) **Воронка (view → checkout → purchase)**  
Данные: `GET /kpi/minute`  
Поля: `session_count`, `checkout_count`, `purchase_count`.

5) **Алерты**  
Данные: `GET /alerts`  
Отображение: список с `direction`, `delta_pct`, `current_value`, `baseline_value`.

### Сегментированные графики
Любой график выше можно строить с фильтрами:
- `channel`
- `campaign`

Пример:
```
GET /kpi/minute?from=2026-02-05T10:00:00Z&to=2026-02-05T11:00:00Z&channel=web&campaign=spring
```

---

## 9) Пример типичного цикла UI

1. Пользователь открывает дашборд:
   - `GET /kpi/minute?from=...&to=...`
   - `GET /metrics/freshness`

2. Фронтенд запускает таймер:
   - KPI обновление каждые 10–15 сек
   - Alerts каждые 60 сек

3. Пользователь выбирает сегмент:
   - повтор KPI‑запросов с `channel` и `campaign`

---

## 10) Полезная заметка
Если KPI пустые, проверь:
- события действительно отправляются,
- поток обрабатывается (stream‑processor),
- база не пустая.
