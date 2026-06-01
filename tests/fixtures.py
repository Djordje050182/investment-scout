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


def _eased(start: float, end: float, n: int) -> List[float]:
    """A cosine-eased ramp from start to end over n points (rounded shoulders)."""
    ease = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))   # 0 -> 1, smooth
    return list(start + (end - start) * ease)


def cup_and_handle_closes() -> List[float]:
    """A clean, ROUNDED cup-and-handle.

    Rim ~100, a cosine-eased decline to a basing period near 78, an eased
    recovery back to the rim, then a shallow handle pullback (~6%) that stays
    in the upper third of the base, ending just below the rim (breakout-ready).
    77 bars total (5 + 22 + 16 + 22 + 12).
    """
    rim = [100.0] * 5
    down = _eased(100, 78, 22)
    base = list(np.linspace(78, 79, 16))            # rounded, time spent at the low
    up = _eased(78, 100, 22)
    handle = list(np.linspace(100, 94, 7)) + list(np.linspace(94, 98, 5))
    return rim + down + base + up + handle


def v_bottom_closes() -> List[float]:
    """A sharp V-bottom (no rounded base) with a handle — NOT a real cup."""
    rim = [100.0] * 5
    down = list(np.linspace(100, 78, 30))
    up = list(np.linspace(78, 100, 30))
    handle = list(np.linspace(100, 94, 7)) + list(np.linspace(94, 98, 5))
    return rim + down + up + handle


def cup_no_handle_closes() -> List[float]:
    """A rounded cup that recovers to the rim and flatlines — no handle pullback."""
    rim = [100.0] * 5
    down = _eased(100, 78, 22)
    base = list(np.linspace(78, 79, 16))
    up = _eased(78, 100, 22)
    flat = [100.0] * 12
    return rim + down + base + up + flat


def cup_far_from_rim_closes() -> List[float]:
    """A rounded cup whose price is still well below the rim — not breakout-ready."""
    rim = [100.0] * 5
    down = _eased(100, 78, 22)
    base = list(np.linspace(78, 79, 16))
    up = _eased(78, 100, 22)
    handle = list(np.linspace(100, 90, 12))   # ends at 90, ~10% below the rim
    return rim + down + base + up + handle


def downtrend_closes(days: int = 260) -> List[float]:
    """A steady decline — should never read as a cup."""
    return list(np.linspace(100, 50, days))


def uptrend_closes(days: int = 260, start: float = 50.0, end: float = 100.0) -> List[float]:
    """Steady uptrend long enough for a 200-day moving average."""
    return list(np.linspace(start, end, days))


def flat_closes(days: int = 260, level: float = 50.0) -> List[float]:
    """Flat, featureless series — should produce no technical signal."""
    return [level] * days
