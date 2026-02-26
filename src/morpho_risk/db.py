from __future__ import annotations

from typing import Iterable

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .types import AnomalyEvent, VaultSnapshot


class DbClient:
    def __init__(self, conn: Connection):
        self.conn = conn

    def insert_snapshots(self, snapshots: Iterable[VaultSnapshot]) -> None:
        rows = [
            (
                s.ts,
                s.vault_id,
                s.chain_id,
                s.market_id,
                s.health_factor,
                s.collateral_value_usd,
                s.debt_value_usd,
                Jsonb(s.raw_payload),
            )
            for s in snapshots
        ]
        if not rows:
            return

        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO vault_health_metrics (
                    ts, vault_id, chain_id, market_id, health_factor,
                    collateral_value_usd, debt_value_usd, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ts, vault_id) DO NOTHING
                """,
                rows,
            )
        self.conn.commit()

    def insert_anomalies(self, events: Iterable[AnomalyEvent]) -> None:
        rows = [
            (
                e.ts,
                e.vault_id,
                e.severity,
                e.risk_score,
                e.expected_health_factor,
                e.observed_health_factor,
                e.robust_z_score,
                e.method,
                Jsonb(e.details),
            )
            for e in events
        ]
        if not rows:
            return

        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO anomaly_events (
                    ts, vault_id, severity, risk_score, expected_health_factor,
                    observed_health_factor, robust_z_score, method, details
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ts, vault_id, method) DO NOTHING
                """,
                rows,
            )
        self.conn.commit()

    def load_detector_states(self) -> dict[str, list[float]]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT vault_id, state FROM detector_state")
            rows = cur.fetchall()
        return {row["vault_id"]: row["state"].get("history", []) for row in rows}

    def upsert_detector_state(self, state_map: dict[str, list[float]]) -> None:
        rows = [(vault_id, Jsonb({"history": history})) for vault_id, history in state_map.items()]
        if not rows:
            return

        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO detector_state (vault_id, state)
                VALUES (%s, %s)
                ON CONFLICT (vault_id)
                DO UPDATE SET state = EXCLUDED.state, updated_at = NOW()
                """,
                rows,
            )
        self.conn.commit()
