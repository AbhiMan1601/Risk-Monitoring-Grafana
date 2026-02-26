from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median

from .config import Settings
from .types import AnomalyEvent, VaultSnapshot


@dataclass
class DetectorState:
    history: deque[float]


class RobustHealthFactorDetector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._state: dict[str, DetectorState] = {}

    def load_state(self, state_map: dict[str, list[float]]) -> None:
        for vault_id, history in state_map.items():
            trimmed = history[-self.settings.history_window :]
            self._state[vault_id] = DetectorState(deque(trimmed, maxlen=self.settings.history_window))

    def export_state(self) -> dict[str, list[float]]:
        return {vault_id: list(state.history) for vault_id, state in self._state.items()}

    def score_snapshot(self, snapshot: VaultSnapshot) -> AnomalyEvent | None:
        state = self._state.setdefault(
            snapshot.vault_id,
            DetectorState(deque(maxlen=self.settings.history_window)),
        )

        if len(state.history) < self.settings.min_history:
            state.history.append(snapshot.health_factor)
            return None

        history = list(state.history)
        baseline = median(history)
        mad = median([abs(x - baseline) for x in history])
        robust_z = 0.6745 * ((snapshot.health_factor - baseline) / (mad + self.settings.mad_epsilon))

        # Convert into downside-only risk score because lower health factors are risky.
        downside_z = max(0.0, -robust_z)
        threshold_component = 0.0
        if snapshot.health_factor < self.settings.health_factor_warning:
            threshold_component = (self.settings.health_factor_warning - snapshot.health_factor) / max(
                self.settings.health_factor_warning - self.settings.health_factor_critical,
                1e-6,
            )

        risk_score = max(downside_z, threshold_component)
        severity = self._severity(risk_score, snapshot.health_factor)

        event = None
        if severity != "none":
            event = AnomalyEvent(
                ts=snapshot.ts,
                vault_id=snapshot.vault_id,
                severity=severity,
                risk_score=round(risk_score, 4),
                expected_health_factor=round(baseline, 6),
                observed_health_factor=round(snapshot.health_factor, 6),
                robust_z_score=round(robust_z, 6),
                method="robust_zscore_mad",
                details={
                    "mad": mad,
                    "history_size": len(history),
                    "warning_hf": self.settings.health_factor_warning,
                    "critical_hf": self.settings.health_factor_critical,
                },
            )
        state.history.append(snapshot.health_factor)
        return event

    def _severity(self, risk_score: float, health_factor: float) -> str:
        if health_factor <= self.settings.health_factor_critical or risk_score >= self.settings.alert_z_threshold:
            return "critical"
        if health_factor <= self.settings.health_factor_warning or risk_score >= self.settings.warning_z_threshold:
            return "warning"
        return "none"
