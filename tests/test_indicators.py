# tests/test_indicators.py
import pandas as pd
from engine.signals.indicators import sma, rsi, recent_high


def test_sma_last_value():
    s = pd.Series([1, 2, 3, 4, 5], dtype="float64")
    assert sma(s, 5).iloc[-1] == 3.0


def test_rsi_all_gains_is_high():
    s = pd.Series(list(range(1, 40)), dtype="float64")
    val = rsi(s, 14).iloc[-1]
    assert val > 90


def test_rsi_all_losses_is_low():
    s = pd.Series(list(range(40, 1, -1)), dtype="float64")
    val = rsi(s, 14).iloc[-1]
    assert val < 10


def test_rsi_flat_series_is_neutral():
    s = pd.Series([42.0] * 260, dtype="float64")
    val = rsi(s, 14).iloc[-1]
    assert 45 <= val <= 55


def test_recent_high_excludes_last_n():
    # last 3 values are small; the prior window peaks at 100
    s = pd.Series([10, 100, 20, 5, 5, 5], dtype="float64")
    assert recent_high(s, lookback=6, exclude_last=3) == 100.0
