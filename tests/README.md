# Test Suite for Real-Time KPI Streaming

This folder contains integration and load tests.

The tests check whether the system is fast enough, accurate enough, and reliable enough to support real-time small businesses decisions.

## What the tests measure

- **End-to-end latency**: how long it takes for an event to appear in the dashboard or KPI API.
- **Delay under load**: how freshness changes when many events are sent at the same time.
- **Error rate**: how many requests fail during high traffic.
- **KPI accuracy**: whether the calculated metrics match known input values.
- **Input validation**: whether invalid payloads are rejected correctly.
- **Engagement KPIs**: whether session events update non-sales metrics correctly.

## Files

### `test_error_rate.py`
Sends many order events concurrently and checks that the share of failed requests stays low.

### `test_latency.py`
Measures how quickly a benchmark event becomes visible in KPI freshness metrics.

### `test_latency_under_load.py`
Runs the same freshness check while a large number of events is being generated.

### `test_kpi_accuracy_and_validation.py`
Checks:
- correct KPI values for known orders,
- duplicate event handling,
- validation of bad payloads,
- session-event KPI updates,
- delay reporting through `/metrics/time-to-signal`.

## How to install dependencies

From the project root run:

```bash
pip install -r tests/requirements.txt
```

## How to run the tests

Make sure the backend is running locally before starting the tests.
The tests expect the API to be available at:

```text
http://localhost:8000
```

Run all tests from the project root:

```bash
pytest -q tests/
```

To see detailed output:

```bash
pytest -rA tests/
```

To save the result log:

```bash
pytest -q -rA tests/ | tee test_results.log
```
