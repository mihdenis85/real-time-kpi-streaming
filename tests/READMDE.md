# Test Suite for Real-Time KPI Streaming

This folder contains integration and load tests..

The tests check whether the system is fast enough, accurate enough, and reliable enough to support real-time small businesses decisions.

## What the tests measure

- **End-to-end latency**: how long it takes for an event to appear in the dashboard or KPI API.
- **Delay under load**: how freshness changes when many events are sent at the same time.
- **Error rate**: how many requests fail during high traffic.
- **KPI accuracy**: whether the calculated metrics match known input values.
- **Input validation**: whether invalid payloads are rejected correctly.
- **Engagement KPIs**: whether session events update non-sales metrics correctly.

## Research Questions

Research Questions:

- **Research Question 1**: Can a lightweight, streaming analytics architecture for SMBs deliver continuously updating sales KPIs and alerts in near real time at significantly lower cost and operational burden that enterprise BI, without sacrificing accuracy?
- **Research Question 2**: How can a lightweight and stream oriented platform help to increase productivity and engagement within a distributed team?
- **Research Question 3**: How can a platform designed to update data in real time help startups develop their product and attract new customers?

## Files

### `test_error_rate.py`
Sends many order events concurrently and checks that the share of failed requests stays low.

- Supports **RQ1** by showing the lightweight architecture remains reliable under load.
- Supports **RQ2** and **RQ3** because teams and customers need trustworthy data.

### `test_latency.py`
Measures how quickly a benchmark event becomes visible in KPI freshness metrics.

- Supports **RQ1** because real-time analytics must update quickly.
- Supports **RQ2** and **RQ3** because faster updates help teams react sooner.

### `test_latency_under_load.py`
Runs the same freshness check while a large number of events is being generated.

- Supports **RQ1** by testing real-time behavior during peak traffic.
- Helps show whether the system can keep latency acceptable when load increases.

### `test_kpi_accuracy_and_validation.py`
Checks:
- correct KPI values for known orders,
- duplicate event handling,
- validation of bad payloads,
- session-event KPI updates,
- delay reporting through `/metrics/time-to-signal`.

- Supports **RQ1** because fast results are not useful if the numbers are wrong.
- Supports **RQ2** because reliable metrics improve trust and productivity.
- Supports **RQ3** because accurate real-time data helps product and marketing decisions.

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

## How these tests answer the research questions

### RQ1
**Can a lightweight, streaming analytics architecture for SMBs deliver continuously updating sales KPIs and alerts in near real time at significantly lower cost and operational burden than enterprise BI, without sacrificing accuracy?**

The tests help answer this by checking:
- latency and freshness,
- behavior under load,
- error rate,
- KPI correctness,
- validation of bad inputs.

Together, these tests show whether the system is fast, accurate, and reliable enough to be practical for SMBs.

### RQ2
**How can a lightweight and stream-oriented platform help increase productivity and engagement within a distributed team?**

The tests support this question indirectly by showing that the dashboard data is:
- timely,
- trustworthy,
- stable during traffic spikes.

If the team can rely on the data and see changes quickly, it becomes easier to react, coordinate, and make decisions.

### RQ3
**How can a platform designed to update data in real time help startups develop their product and attract new customers?**

The tests support this question by proving that:
- product and sales signals appear quickly,
- engagement events are processed correctly,
- the system can keep working during bursts of activity.

This matters because startups need fast feedback to improve the product and respond to market behavior.
