# DeFi Vault Risk Monitoring (TimescaleDB + Grafana)

Production-ready vault risk monitor for:
- yearn-finance
- beefy
- morpho-blue
- pendle
- aave

## Features
- TimescaleDB hypertable storage
- Continuous aggregates (hourly and daily)
- Compression and retention policies
- Scheduled ingestion every 15 minutes
- Risk metrics: volatility, VaR(95%), drawdown, risk score
- Grafana dashboard provisioning and alert provisioning

## Quick Start

1. Create your own `.env` file from the template:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

2. Edit `.env` with your own values.

Example `.env`:

```env
POSTGRES_USER=defi_admin
POSTGRES_PASSWORD=change_me_strong
DB_HOST=localhost
DB_PORT=5432
DB_NAME=defi_risk
DB_USER=defi_admin
DB_PASSWORD=change_me_strong

GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=change_me_grafana
GRAFANA_ROOT_URL=http://localhost:3000

VAULT_SLUGS=yearn-finance,beefy,morpho-blue,pendle,aave
POLL_INTERVAL_MINUTES=15
BACKFILL_DAYS=30
RATE_LIMIT_SLEEP_SECONDS=0.5
LOG_LEVEL=INFO
RUN_ONCE=false

GENERATE_SAMPLE_DATA=false
SAMPLE_DAYS=14
```

3. Start infrastructure + ingest worker:

```bash
docker compose up --build -d
```

4. Open Grafana:
- URL: `http://localhost:3000`
- Credentials from `.env`
- Dashboard: `DeFi Risk / DeFi Vault Risk Monitoring`

## Run Ingest Locally

```bash
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python ingest_vaults.py
```

## Backfill

Run one cycle with custom backfill:

```bash
set RUN_ONCE=true
set BACKFILL_DAYS=60
.\.venv\Scripts\python ingest_vaults.py
```

## Add New Vaults

Edit `VAULT_SLUGS` in `.env`:

```env
VAULT_SLUGS=yearn-finance,beefy,morpho-blue,pendle,aave,new-slug
```

## Generate Sample Data

```bash
set GENERATE_SAMPLE_DATA=true
set SAMPLE_DAYS=30
.\.venv\Scripts\python ingest_vaults.py
```

## Production Notes
- `.env` is gitignored; keep all secrets there and never commit it.
- Keep `POSTGRES_PASSWORD` and `GRAFANA_ADMIN_PASSWORD` in a secret manager for production.
- Enable backups/WAL archiving on your database host.
- Pin image versions in production release tags.
- Restrict DB and Grafana network access at firewall/VPC level.

## Cloud Deployment

### Timescale Cloud + Grafana Cloud
1. Create Timescale service and run `init.sql`.
2. Point ingestion env vars to cloud DB endpoint.
3. Import dashboard JSON into Grafana Cloud or provision it.
4. Configure alert contact points in Grafana.

### Render/Fly.io/VM
1. Deploy TimescaleDB (managed or self-hosted).
2. Deploy Grafana container with mounted provisioning.
3. Deploy ingestion worker as an always-on process.
4. Add monitoring for ingestion success and DB storage growth.