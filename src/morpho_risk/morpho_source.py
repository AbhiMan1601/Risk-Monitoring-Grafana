from __future__ import annotations

import random
from datetime import datetime
from typing import Any

import requests
from dateutil import parser

from .types import VaultSnapshot, utc_now


class MorphoSource:
    def fetch_snapshots(self) -> list[VaultSnapshot]:
        raise NotImplementedError


class SyntheticMorphoSource(MorphoSource):
    def __init__(self, vault_count: int = 6):
        self._vault_count = vault_count
        self._state = {f"vault-{idx + 1}": random.uniform(1.35, 2.0) for idx in range(vault_count)}

    def fetch_snapshots(self) -> list[VaultSnapshot]:
        now = utc_now()
        snapshots: list[VaultSnapshot] = []

        for vault_id, base_hf in self._state.items():
            drift = random.uniform(-0.02, 0.015)
            next_hf = max(0.8, min(2.5, base_hf + drift))
            if random.random() < 0.05:
                next_hf -= random.uniform(0.15, 0.4)
            next_hf = max(0.7, next_hf)
            self._state[vault_id] = next_hf

            collateral = random.uniform(500_000, 2_000_000)
            debt = collateral / max(next_hf, 0.7)
            snapshots.append(
                VaultSnapshot(
                    ts=now,
                    vault_id=vault_id,
                    chain_id=1,
                    market_id="synthetic",
                    health_factor=round(next_hf, 6),
                    collateral_value_usd=round(collateral, 2),
                    debt_value_usd=round(debt, 2),
                    raw_payload={"source": "synthetic"},
                )
            )

        return snapshots


class MorphoApiSource(MorphoSource):
    """
    Expected payload format from MORPHO_API_URL:
    [
      {
        "vault_id": "...",
        "chain_id": 1,
        "market_id": "...",
        "health_factor": 1.42,
        "collateral_value_usd": 1000000,
        "debt_value_usd": 704225,
        "timestamp": "2026-02-26T00:00:00Z"
      }
    ]
    """

    def __init__(self, url: str, api_key: str | None = None, timeout_seconds: int = 15):
        self._url = url
        self._timeout = timeout_seconds
        self._session = requests.Session()
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"

    def fetch_snapshots(self) -> list[VaultSnapshot]:
        response = self._session.get(self._url, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, list):
            raise ValueError("Morpho API payload must be a list of vault snapshots")

        snapshots: list[VaultSnapshot] = []
        for item in payload:
            snapshots.append(self._to_snapshot(item))
        return snapshots

    def _to_snapshot(self, item: dict[str, Any]) -> VaultSnapshot:
        ts_raw = item.get("timestamp")
        ts = parser.isoparse(ts_raw) if ts_raw else utc_now()

        return VaultSnapshot(
            ts=ts,
            vault_id=str(item["vault_id"]),
            chain_id=int(item["chain_id"]) if item.get("chain_id") is not None else None,
            market_id=str(item["market_id"]) if item.get("market_id") is not None else None,
            health_factor=float(item["health_factor"]),
            collateral_value_usd=float(item["collateral_value_usd"]) if item.get("collateral_value_usd") is not None else None,
            debt_value_usd=float(item["debt_value_usd"]) if item.get("debt_value_usd") is not None else None,
            raw_payload=item,
        )