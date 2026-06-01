# tests/fixtures.py
"""Synthetic data builders for offline, deterministic signal tests."""
from typing import List, Optional
import pandas as pd
import numpy as np


def make_prices(closes: List[float], volumes: Optional[List[float]] = None) -> pd.DataFrame:
    """Build an OHLCV DataFrame from a list of closing prices.

    High/Low/Open are derived from close so detectors that read them work.
    Index is a daily date range. Volume defaults to a flat 1_000_000.
    """
    n = len(closes)
    if volumes is None:
        volumes = [1_000_000.0] * n
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series(closes, dtype="float64")
    return pd.DataFrame(
        {
            "Open": close.shift(1).fillna(close.iloc[0]).values,
            "High": (close * 1.01).values,
            "Low": (close * 0.99).values,
            "Close": close.values,
            "Volume": pd.Series(volumes, dtype="float64").values,
        },
        index=idx,
    )


def cup_and_handle_closes() -> List[float]:
    """A clean cup-and-handle: rim ~100, rounded cup to ~80, recovery, small handle dip."""
    left_rim = list(np.linspace(100, 100, 5))
    down = list(np.linspace(100, 80, 30))
    up = list(np.linspace(80, 100, 30))
    handle = list(np.linspace(100, 93, 7)) + list(np.linspace(93, 99, 5))
    return left_rim + down + up + handle


def uptrend_closes(days: int = 260, start: float = 50.0, end: float = 100.0) -> List[float]:
    """Steady uptrend long enough for a 200-day moving average."""
    return list(np.linspace(start, end, days))


def flat_closes(days: int = 260, level: float = 50.0) -> List[float]:
    """Flat, featureless series — should produce no technical signal."""
    return [level] * days
