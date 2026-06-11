# engine/signals/indicators.py
"""Pure technical-indicator helpers. No I/O, fully unit-testable.

Every function takes pandas Series/DataFrames and returns Series (or floats
for point-in-time readings). NaN is used for warm-up windows — callers decide
how to treat missing values.
"""
from typing import Tuple
import numpy as np
import pandas as pd


# --- Moving averages ---------------------------------------------------------

def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, min_periods=span, adjust=False).mean()


# --- Momentum ----------------------------------------------------------------

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing via EMA)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    out = 100.0 - (100.0 / (1.0 + rs))
    # Distinguish flat (neutral) from pure-gain runs; leave warm-up window NaN.
    out = out.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    out = out.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    return out


def macd(series: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram."""
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, min_periods=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stochastic_k(high: pd.Series, low: pd.Series, close: pd.Series,
                 period: int = 14, smooth: int = 3) -> pd.Series:
    """Slow stochastic %K (smoothed)."""
    ll = low.rolling(period, min_periods=period).min()
    hh = high.rolling(period, min_periods=period).max()
    rng = (hh - ll).replace(0.0, float("nan"))
    raw = 100.0 * (close - ll) / rng
    return raw.rolling(smooth, min_periods=smooth).mean()


def roc(series: pd.Series, period: int) -> pd.Series:
    """Rate of change over `period` bars, as a fraction (0.05 == +5%)."""
    return series / series.shift(period) - 1.0


# --- Volatility --------------------------------------------------------------

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True range: max of (H-L, |H-prevC|, |L-prevC|)."""
    prev_close = close.shift(1)
    a = high - low
    b = (high - prev_close).abs()
    c = (low - prev_close).abs()
    return pd.concat([a, b, c], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = 14) -> pd.Series:
    """Average True Range (Wilder's smoothing)."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def bollinger(series: pd.Series, window: int = 20,
              num_std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger bands: (middle, upper, lower)."""
    mid = sma(series, window)
    std = series.rolling(window, min_periods=window).std(ddof=0)
    return mid, mid + num_std * std, mid - num_std * std


def bollinger_bandwidth(series: pd.Series, window: int = 20,
                        num_std: float = 2.0) -> pd.Series:
    """Band width as a fraction of the middle band (volatility squeeze gauge)."""
    mid, upper, lower = bollinger(series, window, num_std)
    return (upper - lower) / mid.replace(0.0, float("nan"))


# --- Trend strength ----------------------------------------------------------

def adx(high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = 14) -> pd.Series:
    """Average Directional Index (Wilder). >25 = trending, <20 = chop."""
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr = true_range(high, low, close)
    alpha = 1.0 / period
    atr_s = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    atr_safe = atr_s.replace(0.0, float("nan"))
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_safe
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_safe
    di_sum = (plus_di + minus_di).replace(0.0, float("nan"))
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    return dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()


def slope(series: pd.Series, window: int) -> float:
    """Normalized linear-regression slope of the last `window` bars.

    Returned as fraction-per-bar of the mean level (0.001 == +0.1%/bar),
    so it is comparable across price scales. NaN-safe: returns 0.0 when
    there is not enough data.
    """
    tail = series.iloc[-window:].dropna()
    if len(tail) < max(3, window // 2):
        return 0.0
    y = tail.to_numpy(dtype="float64")
    x = np.arange(len(y), dtype="float64")
    denom = ((x - x.mean()) ** 2).sum()
    if denom == 0:
        return 0.0
    beta = ((x - x.mean()) * (y - y.mean())).sum() / denom
    level = abs(y.mean())
    return float(beta / level) if level > 0 else 0.0


# --- Volume ------------------------------------------------------------------

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume: cumulative volume signed by the day's direction."""
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()


# --- Structure ---------------------------------------------------------------

def recent_high(series: pd.Series, lookback: int, exclude_last: int = 0) -> float:
    """Highest value within `lookback` bars, optionally excluding the last `exclude_last`."""
    window = series.iloc[-lookback:]
    if exclude_last > 0:
        window = window.iloc[:-exclude_last]
    return float(window.max())


def recent_low(series: pd.Series, lookback: int, exclude_last: int = 0) -> float:
    """Lowest value within `lookback` bars, optionally excluding the last `exclude_last`."""
    window = series.iloc[-lookback:]
    if exclude_last > 0:
        window = window.iloc[:-exclude_last]
    return float(window.min())


def swing_low(low: pd.Series, lookback: int = 20) -> float:
    """The most recent meaningful swing low: lowest low of the last `lookback` bars."""
    return float(low.iloc[-lookback:].min())
