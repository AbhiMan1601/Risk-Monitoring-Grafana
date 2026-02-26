from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class VaultSnapshot:
    ts: datetime
    vault_id: str
    chain_id: int | None
    market_id: str | None
    health_factor: float
    collateral_value_usd: float | None
    debt_value_usd: float | None
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class AnomalyEvent:
    ts: datetime
    vault_id: str
    severity: str
    risk_score: float
    expected_health_factor: float | None
    observed_health_factor: float
    robust_z_score: float | None
    method: str
    details: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)