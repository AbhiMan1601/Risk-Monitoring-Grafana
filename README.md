# Morpho Vault Risk Monitoring Prototype

This repository contains a working prototype for monitoring Morpho vault health using:
- TimescaleDB for time-series storage
- A production-ready robust anomaly detector (median + MAD robust z-score with risk thresholds)
- Grafana dashboard for risk visualization

## Architecture

- `risk-engine` service ingests vault health factor snapshots and writes to TimescaleDB.
- A robust detector scores each vault point and writes anomaly events.
- Grafana reads directly from TimescaleDB with a pre-provisioned dashboard.

## Quick Start

### 1. Start services

```bash
docker compose up --build
```

Services:
- TimescaleDB: `localhost:5432`
- Grafana: `http://localhost:3000` (admin/admin)
- Risk engine: background container logs anomalies each cycle

### 2. View dashboard

Open Grafana and navigate to:
- `Dashboards` -> `Morpho Risk` -> `Morpho Vault Risk Monitoring`

## Data Source Modes

### Synthetic mode (default)

This is enabled by default to provide an immediately working demo.
- `USE_SYNTHETIC_SOURCE=true`
- Generates realistic health-factor movement with occasional stress events.

### Morpho API mode

Set environment variables in `docker-compose.yml`:
- `USE_SYNTHETIC_SOURCE=false`
- `MORPHO_API_URL=<your endpoint returning vault snapshots JSON>`
- `MORPHO_API_KEY=<optional bearer token>`

Expected JSON payload:

```json
[
  {
    "vault_id": "eth-usdc-1",
    "chain_id": 1,
    "market_id": "market-abc",
    "health_factor": 1.42,
    "collateral_value_usd": 1000000,
    "debt_value_usd": 704225,
    "timestamp": "2026-02-26T00:00:00Z"
  }
]
```

## Database Schema

Initialized by `sql/001_init.sql`:
- `vault_health_metrics` hypertable
- `anomaly_events` hypertable
- `detector_state` (state persistence across restarts)
- `hf_5m` continuous aggregate view for dashboarding

## Anomaly Detection Method

Implemented in `src/morpho_risk/anomaly.py`:
- Maintains rolling history per vault
- Computes robust baseline with median and MAD
- Calculates robust z-score
- Applies downside-only risk scoring and health-factor floor thresholds
- Classifies severity (`warning`, `critical`)

This design is resilient to outliers and practical for production monitoring workloads.

## Useful Queries

Recent critical anomalies:

```sql
SELECT *
FROM anomaly_events
WHERE severity = 'critical'
ORDER BY ts DESC
LIMIT 50;
```

Latest health factors per vault:

```sql
SELECT DISTINCT ON (vault_id) vault_id, ts, health_factor
FROM vault_health_metrics
ORDER BY vault_id, ts DESC;
```