from dataclasses import dataclass
import os


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://risk_user:risk_pass@localhost:5432/risk_monitor")
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

    history_window: int = int(os.getenv("HISTORY_WINDOW", "180"))
    min_history: int = int(os.getenv("MIN_HISTORY", "30"))
    mad_epsilon: float = float(os.getenv("MAD_EPSILON", "0.000001"))
    alert_z_threshold: float = float(os.getenv("ALERT_Z_THRESHOLD", "3.0"))
    warning_z_threshold: float = float(os.getenv("WARNING_Z_THRESHOLD", "2.0"))
    health_factor_warning: float = float(os.getenv("HEALTH_FACTOR_WARNING", "1.20"))
    health_factor_critical: float = float(os.getenv("HEALTH_FACTOR_CRITICAL", "1.05"))

    morpho_api_url: str = os.getenv("MORPHO_API_URL", "")
    morpho_api_key: str = os.getenv("MORPHO_API_KEY", "")
    use_synthetic_source: bool = _get_bool("USE_SYNTHETIC_SOURCE", True)
    synthetic_vaults: int = int(os.getenv("SYNTHETIC_VAULTS", "6"))

    log_level: str = os.getenv("LOG_LEVEL", "INFO")