# engine/signals/indicators.py
"""Pure technical-indicator helpers. No I/O, fully unit-testable."""
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing via EMA)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(100.0)


def recent_high(series: pd.Series, lookback: int, exclude_last: int = 0) -> float:
    """Highest value within `lookback` bars, optionally excluding the last `exclude_last`."""
    window = series.iloc[-lookback:]
    if exclude_last > 0:
        window = window.iloc[:-exclude_last]
    return float(window.max())
