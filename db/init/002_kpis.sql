CREATE TABLE IF NOT EXISTS kpi_minute (
    bucket TIMESTAMPTZ PRIMARY KEY,
    revenue NUMERIC(14, 2) NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 0,
    checkout_count INTEGER NOT NULL DEFAULT 0,
    purchase_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('kpi_minute', 'bucket', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS kpi_hour (
    bucket TIMESTAMPTZ PRIMARY KEY,
    revenue NUMERIC(14, 2) NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 0,
    checkout_count INTEGER NOT NULL DEFAULT 0,
    purchase_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('kpi_hour', 'bucket', if_not_exists => TRUE);

CREATE OR REPLACE VIEW kpi_minute_view AS
SELECT
    bucket,
    revenue,
    order_count,
    session_count,
    checkout_count,
    purchase_count,
    CASE
        WHEN session_count > 0 THEN purchase_count::DOUBLE PRECISION / session_count
        ELSE NULL
    END AS conversion_rate
FROM kpi_minute;

CREATE OR REPLACE VIEW kpi_hour_view AS
SELECT
    bucket,
    revenue,
    order_count,
    session_count,
    checkout_count,
    purchase_count,
    CASE
        WHEN session_count > 0 THEN purchase_count::DOUBLE PRECISION / session_count
        ELSE NULL
    END AS conversion_rate
FROM kpi_hour;

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    bucket TIMESTAMPTZ NOT NULL,
    kpi TEXT NOT NULL,
    current_value NUMERIC(14, 2),
    baseline_value NUMERIC(14, 2),
    delta_pct DOUBLE PRECISION,
    direction TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (bucket, kpi)
);
