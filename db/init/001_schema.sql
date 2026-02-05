CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT NOT NULL,
    customer_id TEXT,
    amount NUMERIC(14, 2) NOT NULL,
    currency TEXT NOT NULL,
    channel TEXT,
    campaign TEXT,
    event_time TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (order_id, event_time)
);

SELECT create_hypertable('orders', 'event_time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS orders_event_time_idx ON orders (event_time DESC);
CREATE INDEX IF NOT EXISTS orders_event_time_channel_campaign_idx
    ON orders (event_time DESC, channel, campaign);

CREATE TABLE IF NOT EXISTS sessions (
    event_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    user_id TEXT,
    channel TEXT,
    campaign TEXT,
    event_time TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (event_id, event_time)
);

SELECT create_hypertable('sessions', 'event_time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS sessions_event_time_idx ON sessions (event_time DESC);
CREATE INDEX IF NOT EXISTS sessions_event_time_channel_campaign_idx
    ON sessions (event_time DESC, channel, campaign);
