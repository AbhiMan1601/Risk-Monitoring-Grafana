import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg2
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from psycopg2.extras import execute_values

from risk_calculations import calculate_drawdown, calculate_liquidation_risk, calculate_volatility_and_var

LLAMA_URL = "https://api.llama.fi/protocol/{}"
DEFAULT_VAULTS = ["yearn-finance", "beefy", "morpho-blue", "pendle", "aave"]

UPSERT_SQL = """
INSERT INTO defi_vault_metrics (
    time, vault_slug, chain, tvl_usd, apy, price_usd,
    volatility_24h, var_95_24h, drawdown_24h, liquidation_risk_24h
) VALUES %s
ON CONFLICT (time, vault_slug) DO UPDATE SET
    chain = EXCLUDED.chain,
    tvl_usd = EXCLUDED.tvl_usd,
    apy = EXCLUDED.apy,
    price_usd = EXCLUDED.price_usd,
    volatility_24h = EXCLUDED.volatility_24h,
    var_95_24h = EXCLUDED.var_95_24h,
    drawdown_24h = EXCLUDED.drawdown_24h,
    liquidation_risk_24h = EXCLUDED.liquidation_risk_24h;
"""


SCHEMA_PATCH_SQL = """
ALTER TABLE IF EXISTS defi_vault_metrics
  ADD COLUMN IF NOT EXISTS liquidation_risk_24h REAL;

CREATE INDEX IF NOT EXISTS idx_defi_metrics_liquidation_risk_desc
  ON defi_vault_metrics (liquidation_risk_24h DESC);

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
"""


def utc_now():
    return datetime.now(timezone.utc)


def parse_env_list(name, default_list):
    raw = os.getenv(name, "")
    if not raw.strip():
        return default_list
    return [x.strip() for x in raw.split(",") if x.strip()]


def db_connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "defi_risk"),
        user=os.getenv("DB_USER", "defi_admin"),
        password=os.getenv("DB_PASSWORD", ""),
        connect_timeout=10,
    )


def ensure_db_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA_PATCH_SQL)
    conn.commit()


def fetch_defillama(protocol_slug, session, timeout=20, retries=3):
    url = LLAMA_URL.format(protocol_slug)
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 429:
                sleep_s = min(10, attempt * 2)
                logging.warning("Rate limited for %s, sleeping %ss", protocol_slug, sleep_s)
                time.sleep(sleep_s)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            if attempt == retries:
                raise
            sleep_s = attempt * 2
            logging.warning("Fetch failed for %s (%s), retrying in %ss", protocol_slug, exc, sleep_s)
            time.sleep(sleep_s)
    return None


def parse_chart_points(payload):
    points = []
    chart = payload.get("chart") or []
    for item in chart:
        ts = None
        tvl = None

        if isinstance(item, dict):
            ts = item.get("date") or item.get("timestamp") or item.get("time")
            tvl = item.get("totalLiquidityUSD")
            if tvl is None:
                tvl = item.get("tvl")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            ts, tvl = item[0], item[1]

        if ts is None or tvl is None:
            continue

        try:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            points.append((dt, float(tvl)))
        except Exception:
            continue

    points.sort(key=lambda x: x[0])
    return points


def parse_latest_tvl(payload, chart_points):
    candidates = [payload.get("tvl"), payload.get("currentChainTvlsTotal"), payload.get("currentTvl")]
    for c in candidates:
        if c is not None:
            try:
                return float(c)
            except Exception:
                pass
    if chart_points:
        return float(chart_points[-1][1])
    return None


def parse_chain(payload):
    current_chain_tvls = payload.get("currentChainTvls")
    if isinstance(current_chain_tvls, dict) and current_chain_tvls:
        try:
            return max(current_chain_tvls.items(), key=lambda kv: float(kv[1]))[0]
        except Exception:
            pass

    chain_tvls = payload.get("chainTvls")
    if isinstance(chain_tvls, dict) and chain_tvls:
        return next(iter(chain_tvls.keys()))

    return "all"


def parse_apy(payload):
    apy = payload.get("apy")
    if apy is None:
        return None
    try:
        return float(apy)
    except Exception:
        return None


def parse_price(payload):
    for key in ("price", "priceUsd", "price_usd"):
        value = payload.get(key)
        if value is not None:
            try:
                return float(value)
            except Exception:
                continue
    return None


def get_latest_db_time(conn, vault_slug):
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(time) FROM defi_vault_metrics WHERE vault_slug = %s", (vault_slug,))
        row = cur.fetchone()
    return row[0] if row and row[0] is not None else None


def build_rows(vault_slug, chain, apy, price, chart_points, latest_tvl, latest_time, backfill_days):
    now = utc_now().replace(second=0, microsecond=0)
    cutoff = now - timedelta(days=backfill_days)

    filtered = [(t, v) for (t, v) in chart_points if t >= cutoff]
    if latest_time is not None:
        filtered = [(t, v) for (t, v) in filtered if t > latest_time]

    if latest_tvl is not None:
        filtered.append((now, latest_tvl))

    dedup = {}
    for t, v in filtered:
        dedup[t] = v
    ordered = sorted(dedup.items(), key=lambda x: x[0])

    rows = []

    for ts, tvl in ordered:
        series = [x for (t, x) in chart_points if t <= ts and x is not None]
        if tvl is not None:
            series.append(tvl)

        volatility, var_95 = calculate_volatility_and_var(series, window_days=1)
        drawdown = calculate_drawdown(series, window_days=1)
        liquidation_risk = calculate_liquidation_risk(volatility, var_95, drawdown, apy)

        rows.append(
            (
                ts,
                vault_slug,
                chain,
                float(tvl) if tvl is not None else None,
                apy,
                price,
                volatility,
                var_95,
                drawdown,
                liquidation_risk,
            )
        )

    return rows


def upsert_rows(conn, rows):
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_values(cur, UPSERT_SQL, rows, page_size=500)
    conn.commit()
    return len(rows)


def process_vault(conn, session, vault_slug, backfill_days=30):
    payload = fetch_defillama(vault_slug, session=session)
    chart_points = parse_chart_points(payload)
    latest_tvl = parse_latest_tvl(payload, chart_points)
    chain = parse_chain(payload)
    apy = parse_apy(payload)
    price = parse_price(payload)
    latest_time = get_latest_db_time(conn, vault_slug)

    rows = build_rows(vault_slug, chain, apy, price, chart_points, latest_tvl, latest_time, backfill_days)
    written = upsert_rows(conn, rows)
    logging.info("vault=%s chart_points=%d upserted=%d", vault_slug, len(chart_points), written)


def run_cycle(vaults, backfill_days, rate_limit_sleep):
    logging.info("Starting ingest cycle for %d vaults", len(vaults))

    session = requests.Session()
    session.headers.update({"User-Agent": "defi-risk-monitor/1.0"})

    with db_connect() as conn:
        ensure_db_schema(conn)
        for slug in vaults:
            try:
                process_vault(conn, session, slug, backfill_days=backfill_days)
            except Exception:
                logging.exception("Failed processing vault=%s", slug)
            time.sleep(rate_limit_sleep)

    logging.info("Ingest cycle complete")


def seed_sample_data(days=14):
    import random

    now = utc_now().replace(minute=0, second=0, microsecond=0)
    rows = []

    for vault in DEFAULT_VAULTS:
        base = random.uniform(5e7, 8e8)
        for i in range(days * 24):
            ts = now - timedelta(hours=(days * 24 - i))
            shock = random.uniform(-0.03, 0.03)
            base = max(1e6, base * (1 + shock))
            apy = random.uniform(1.0, 12.0)
            vol = abs(shock)
            var95 = vol * 1.5
            dd = max(0.0, vol * 0.8)
            liquidation_risk = calculate_liquidation_risk(vol, var95, dd, apy)
            rows.append(
                (
                    ts,
                    vault,
                    "all",
                    float(base),
                    float(apy),
                    random.uniform(0.5, 3500.0),
                    float(vol),
                    float(var95),
                    float(dd),
                    float(liquidation_risk),
                )
            )

    with db_connect() as conn:
        ensure_db_schema(conn)
        count = upsert_rows(conn, rows)
    logging.info("Seeded sample rows=%d", count)


def main():
    load_dotenv()

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(message)s")

    vaults = parse_env_list("VAULT_SLUGS", DEFAULT_VAULTS)
    interval_minutes = int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
    backfill_days = int(os.getenv("BACKFILL_DAYS", "30"))
    rate_limit_sleep = float(os.getenv("RATE_LIMIT_SLEEP_SECONDS", "0.5"))
    run_once = os.getenv("RUN_ONCE", "false").lower() in {"1", "true", "yes"}
    generate_sample = os.getenv("GENERATE_SAMPLE_DATA", "false").lower() in {"1", "true", "yes"}

    if generate_sample:
        days = int(os.getenv("SAMPLE_DAYS", "14"))
        seed_sample_data(days=days)
        return

    if run_once:
        run_cycle(vaults, backfill_days, rate_limit_sleep)
        return

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_cycle,
        trigger="interval",
        minutes=interval_minutes,
        args=[vaults, backfill_days, rate_limit_sleep],
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
        id="defi_vault_ingest_job",
        replace_existing=True,
    )

    logging.info("Scheduler started: every %d minutes", interval_minutes)
    run_cycle(vaults, backfill_days, rate_limit_sleep)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Shutting down")
        sys.exit(0)


if __name__ == "__main__":
    main()
