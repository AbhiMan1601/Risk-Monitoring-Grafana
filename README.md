# DeFi Vault Risk Monitoring (TimescaleDB + Grafana)

Monitoring stack for DeFi vault protocols:
- yearn-finance
- beefy
- morpho-blue
- pendle
- aave

## Current Status
- This repo is currently running with sample-seeded data in local TimescaleDB.
- Primary risk metric is `liquidation_risk_24h` (not `risk_score`).

## How The System Works
- `ingest_vaults.py` fetches protocol TVL data (DefiLlama), computes:
  - `volatility_24h`
  - `var_95_24h`
  - `drawdown_24h`
  - `liquidation_risk_24h` (bounded 0..1 stress proxy)
- Data is upserted into `defi_vault_metrics` hypertable.
- Timescale views surface latest and top liquidation-risk vaults.
- Grafana reads PostgreSQL/Timescale directly and displays:
  - TVL time series
  - current liquidation risk stat
  - top liquidation-risk vaults table
  - alert rule on liquidation risk threshold

## Architecture Wireframe
```text
                +--------------------------+
                |  DefiLlama API           |
                |  /protocol/{vault_slug}  |
                +------------+-------------+
                             |
                             | pull every 15m
                             v
                +--------------------------+
                |  ingest_vaults.py        |
                |  - parse chart/tvl/apy   |
                |  - calc liquidation risk  |
                |  - upsert metrics         |
                +------------+-------------+
                             |
                             | SQL upsert
                             v
                +--------------------------+
                | TimescaleDB (Postgres16) |
                | hypertable:              |
                |   defi_vault_metrics     |
                | views: latest/top-risk   |
                +------------+-------------+
                             |
                             | datasource query
                             v
                +--------------------------+
                | Grafana                  |
                | Dashboard + Alerting     |
                +--------------------------+
```

## Quick Start
1. Create `.env` from template:
```bash
cp .env.example .env
```
PowerShell:
```powershell
Copy-Item .env.example .env
```

2. Edit `.env` values.

3. Start stack:
```bash
docker compose up --build -d
```

4. Open Grafana:
- URL: `http://localhost:3000`
- Login from `.env`
- Dashboard: `DeFi Risk / DeFi Vault Risk Monitoring`

## Sample Data Mode (Current)
Seed sample data manually:
```powershell
docker compose run --rm -e GENERATE_SAMPLE_DATA=true -e SAMPLE_DAYS=30 ingest
```

## Switch To Real Data Ingestion
The same ingest service already supports real DefiLlama ingestion by default.

1. Ensure `.env` has:
```env
GENERATE_SAMPLE_DATA=false
RUN_ONCE=false
POLL_INTERVAL_MINUTES=15
VAULT_SLUGS=yearn-finance,beefy,morpho-blue,pendle,aave
```

2. Start/Restart ingest service:
```powershell
docker compose up -d ingest
```

3. (Optional) run one immediate real-data cycle:
```powershell
docker compose run --rm -e RUN_ONCE=true -e GENERATE_SAMPLE_DATA=false ingest
```

4. If you want to clear sample rows first:
```powershell
docker compose exec timescaledb psql -U $env:POSTGRES_USER -d defi_risk -c "TRUNCATE TABLE defi_vault_metrics;"
```

## Add New Vaults
Update in `.env`:
```env
VAULT_SLUGS=yearn-finance,beefy,morpho-blue,pendle,aave,new-slug
```

## Local Python Run (Without Docker Ingest)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python ingest_vaults.py
```

## Production Notes
- `.env` is gitignored; never commit secrets.
- Use managed secret storage for passwords/tokens.
- Enable DB backups/WAL archiving.
- Restrict DB and Grafana network exposure.
