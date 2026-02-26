import numpy as np


def _clean_series(series):
    arr = np.array([x for x in series if x is not None], dtype=float)
    arr = arr[np.isfinite(arr)]
    arr = arr[arr > 0]
    return arr


def calculate_volatility_and_var(historical_prices_or_tvl, window_days=1):
    arr = _clean_series(historical_prices_or_tvl)
    if arr.size < 3:
        return None, None

    max_points = max(3, int(window_days * 24))
    arr = arr[-max_points:]

    log_returns = np.diff(np.log(arr))
    if log_returns.size < 2:
        return None, None

    volatility = float(np.std(log_returns, ddof=1))
    var_95 = float(abs(np.percentile(log_returns, 5)))
    return volatility, var_95


def calculate_drawdown(series, window_days=1):
    arr = _clean_series(series)
    if arr.size < 2:
        return None

    max_points = max(2, int(window_days * 24))
    arr = arr[-max_points:]

    running_peak = np.maximum.accumulate(arr)
    drawdowns = (arr - running_peak) / running_peak
    return float(abs(np.min(drawdowns)))


def calculate_liquidation_risk(volatility_24h, var_95_24h, drawdown_24h=None, apy=None):
    """
    Liquidation risk proxy in [0, 1].
    Higher downside volatility/var/drawdown => higher liquidation risk.
    A modest APY buffer slightly reduces risk.
    """
    vol = float(volatility_24h) if volatility_24h is not None else 0.0
    var = float(var_95_24h) if var_95_24h is not None else 0.0
    dd = float(drawdown_24h) if drawdown_24h is not None else 0.0
    apy_value = float(apy) if apy is not None else 0.0

    # Weighted stress proxy calibrated for common hourly TVL return scales.
    stress = (var * 8.0) + (vol * 6.0) + (dd * 4.0)
    # APY only provides a small mitigation buffer.
    buffer = min(max(apy_value / 100.0, 0.0), 0.2)
    liquidation_risk = stress - buffer
    return float(min(max(liquidation_risk, 0.0), 1.0))


def estimate_impermanent_loss(price_old, price_new):
    if price_old is None or price_new is None or price_old <= 0 or price_new <= 0:
        return None
    r = price_new / price_old
    il = (2 * np.sqrt(r) / (1 + r)) - 1
    return float(abs(il))
