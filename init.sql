\set ON_ERROR_STOP on

SELECT 'CREATE DATABASE defi_risk'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'defi_risk') \gexec

\connect defi_risk

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS defi_vault_metrics (
    time TIMESTAMPTZ NOT NULL,
    vault_slug TEXT NOT NULL,
    chain TEXT,
    tvl_usd DOUBLE PRECISION,
    apy REAL,
    price_usd DOUBLE PRECISION,
    volatility_24h REAL,
    var_95_24h REAL,
    drawdown_24h REAL,
    liquidation_risk_24h REAL,
    PRIMARY KEY (time, vault_slug)
);

ALTER TABLE defi_vault_metrics
  ADD COLUMN IF NOT EXISTS liquidation_risk_24h REAL;

SELECT create_hypertable(
    'defi_vault_metrics',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    partitioning_column => 'vault_slug',
    number_partitions => 8,
    migrate_data => true,
    if_not_exists => true
);

CREATE INDEX IF NOT EXISTS idx_defi_metrics_vault_time_desc ON defi_vault_metrics (vault_slug, time DESC);
CREATE INDEX IF NOT EXISTS idx_defi_metrics_time_desc ON defi_vault_metrics (time DESC);
CREATE INDEX IF NOT EXISTS idx_defi_metrics_liquidation_risk_desc ON defi_vault_metrics (liquidation_risk_24h DESC);

ALTER TABLE defi_vault_metrics SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'vault_slug',
  timescaledb.compress_orderby = 'time DESC'
);

DO $$
BEGIN
  PERFORM add_compression_policy('defi_vault_metrics', INTERVAL '7 days');
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;

DO $$
BEGIN
  PERFORM add_retention_policy('defi_vault_metrics', INTERVAL '2 years');
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;

CREATE MATERIALIZED VIEW IF NOT EXISTS defi_vault_metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', time) AS bucket,
  vault_slug,
  chain,
  AVG(tvl_usd) AS avg_tvl_usd,
  MAX(tvl_usd) AS max_tvl_usd,
  MIN(tvl_usd) AS min_tvl_usd,
  AVG(apy) AS avg_apy,
  AVG(volatility_24h) AS avg_volatility_24h,
  AVG(var_95_24h) AS avg_var_95_24h,
  MAX(liquidation_risk_24h) AS max_liquidation_risk_24h
FROM defi_vault_metrics
GROUP BY bucket, vault_slug, chain
WITH NO DATA;

DO $$
BEGIN
  PERFORM add_continuous_aggregate_policy(
    'defi_vault_metrics_hourly',
    start_offset => INTERVAL '90 days',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '15 minutes'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;

CREATE MATERIALIZED VIEW IF NOT EXISTS defi_vault_metrics_daily
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 day', time) AS bucket,
  vault_slug,
  chain,
  AVG(tvl_usd) AS avg_tvl_usd,
  MAX(tvl_usd) AS max_tvl_usd,
  MIN(tvl_usd) AS min_tvl_usd,
  AVG(apy) AS avg_apy,
  AVG(volatility_24h) AS avg_volatility_24h,
  AVG(var_95_24h) AS avg_var_95_24h,
  MAX(liquidation_risk_24h) AS max_liquidation_risk_24h
FROM defi_vault_metrics
GROUP BY bucket, vault_slug, chain
WITH NO DATA;

DO $$
BEGIN
  PERFORM add_continuous_aggregate_policy(
    'defi_vault_metrics_daily',
    start_offset => INTERVAL '5 years',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 hour'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;

DO $$
BEGIN
  PERFORM add_retention_policy('defi_vault_metrics_hourly', INTERVAL '5 years');
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;

DO $$
BEGIN
  PERFORM add_retention_policy('defi_vault_metrics_daily', INTERVAL '5 years');
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;

CREATE OR REPLACE VIEW latest_metrics AS
SELECT DISTINCT ON (vault_slug)
  time,
  vault_slug,
  chain,
  tvl_usd,
  apy,
  price_usd,
  volatility_24h,
  var_95_24h,
  drawdown_24h,
  liquidation_risk_24h
FROM defi_vault_metrics
ORDER BY vault_slug, time DESC;

CREATE OR REPLACE VIEW top_liquidation_risk_vaults AS
SELECT
  vault_slug,
  MAX(time) AS latest_time,
  MAX(liquidation_risk_24h) AS current_liquidation_risk_24h,
  AVG(var_95_24h) AS avg_var_95_24h,
  AVG(volatility_24h) AS avg_volatility_24h
FROM defi_vault_metrics
WHERE time >= NOW() - INTERVAL '24 hours'
GROUP BY vault_slug
ORDER BY current_liquidation_risk_24h DESC;
