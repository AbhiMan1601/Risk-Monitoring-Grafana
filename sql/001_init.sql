CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS vault_health_metrics (
  ts TIMESTAMPTZ NOT NULL,
  vault_id TEXT NOT NULL,
  chain_id INTEGER,
  market_id TEXT,
  health_factor DOUBLE PRECISION NOT NULL,
  collateral_value_usd DOUBLE PRECISION,
  debt_value_usd DOUBLE PRECISION,
  raw_payload JSONB,
  PRIMARY KEY (ts, vault_id)
);

SELECT create_hypertable('vault_health_metrics', 'ts', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');

CREATE INDEX IF NOT EXISTS idx_vault_health_metrics_vault_ts_desc
  ON vault_health_metrics (vault_id, ts DESC);

CREATE TABLE IF NOT EXISTS anomaly_events (
  ts TIMESTAMPTZ NOT NULL,
  vault_id TEXT NOT NULL,
  severity TEXT NOT NULL,
  risk_score DOUBLE PRECISION NOT NULL,
  expected_health_factor DOUBLE PRECISION,
  observed_health_factor DOUBLE PRECISION NOT NULL,
  robust_z_score DOUBLE PRECISION,
  method TEXT NOT NULL,
  details JSONB,
  PRIMARY KEY (ts, vault_id, method)
);

SELECT create_hypertable('anomaly_events', 'ts', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');

CREATE INDEX IF NOT EXISTS idx_anomaly_events_vault_ts_desc
  ON anomaly_events (vault_id, ts DESC);

CREATE TABLE IF NOT EXISTS detector_state (
  vault_id TEXT PRIMARY KEY,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  state JSONB NOT NULL
);

CREATE MATERIALIZED VIEW IF NOT EXISTS hf_5m
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('5 minutes', ts) AS bucket,
  vault_id,
  AVG(health_factor) AS avg_health_factor,
  MIN(health_factor) AS min_health_factor,
  MAX(health_factor) AS max_health_factor
FROM vault_health_metrics
GROUP BY bucket, vault_id
WITH NO DATA;

DO $$
BEGIN
  PERFORM add_continuous_aggregate_policy(
    'hf_5m',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute'
  );
EXCEPTION
  WHEN duplicate_object THEN
    NULL;
END
$$;
