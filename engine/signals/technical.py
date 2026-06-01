# engine/signals/technical.py
"""Technical pattern detection. Input: OHLCV DataFrame. Output: {score, patterns}."""
from typing import Dict, List
import pandas as pd
from engine.signals.indicators import sma, rsi, recent_high


def _detect_cup_and_handle(close: pd.Series) -> float:
    """Return 0-1 strength of a cup-and-handle ending near now, else 0.

    Heuristic: over the last ~77 bars find a rounded base whose midpoint is the
    lowest region, with left/right rims at similar levels, followed by a shallow
    handle pullback, with price now near the rim (breakout-ready).
    """
    n = len(close)
    if n < 60:
        return 0.0
    window = close.iloc[-77:] if n >= 77 else close
    vals = window.reset_index(drop=True)
    w = len(vals)
    left_rim = vals.iloc[:5].max()
    cup = vals.iloc[5:w - 12] if w - 12 > 5 else vals.iloc[5:]
    if len(cup) == 0:
        return 0.0
    cup_bottom = cup.min()
    bottom_idx = cup.idxmin()
    handle = vals.iloc[-12:]
    right_rim = handle.max()
    now = vals.iloc[-1]

    depth = (left_rim - cup_bottom) / left_rim if left_rim else 0.0
    if depth < 0.10 or depth > 0.6:
        return 0.0
    # rims roughly level
    rim_balance = 1.0 - min(1.0, abs(left_rim - right_rim) / left_rim)
    if rim_balance < 0.85:
        return 0.0
    # bottom should sit in the middle third (rounded, not a V at the edge)
    pos = (bottom_idx - 5) / max(1, (w - 12 - 5))
    if pos < 0.25 or pos > 0.75:
        return 0.0
    # handle is a shallow dip then recovery toward the rim
    handle_dip = (right_rim - handle.min()) / right_rim if right_rim else 0.0
    if handle_dip > 0.20:
        return 0.0
    # price now near the rim => breakout-ready
    proximity = 1.0 - min(1.0, abs(right_rim - now) / right_rim)
    score = 0.5 * rim_balance + 0.3 * proximity + 0.2 * (1.0 - handle_dip)
    return float(max(0.0, min(1.0, score)))


def _detect_breakout(close: pd.Series, volume: pd.Series) -> float:
    """Price clears recent resistance on above-average volume."""
    if len(close) < 30:
        return 0.0
    resistance = recent_high(close, lookback=60, exclude_last=1)
    now = float(close.iloc[-1])
    if now <= resistance:
        return 0.0
    avg_vol = float(volume.iloc[-21:-1].mean())
    if avg_vol <= 0:
        return 0.0
    vol_ratio = float(volume.iloc[-1]) / avg_vol
    if vol_ratio < 1.5:
        return 0.0
    return float(max(0.0, min(1.0, (vol_ratio - 1.5) / 1.5)))


def _detect_uptrend(close: pd.Series) -> float:
    """Price above rising 50- and 200-day SMAs."""
    if len(close) < 200:
        return 0.0
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    now = float(close.iloc[-1])
    rising50 = sma50.iloc[-1] > sma50.iloc[-10]
    rising200 = sma200.iloc[-1] > sma200.iloc[-20]
    above = now > sma50.iloc[-1] > sma200.iloc[-1]
    if above and rising50 and rising200:
        return 1.0
    if above and rising50:
        return 0.5
    return 0.0


def scan_technical(prices: pd.DataFrame) -> Dict[str, object]:
    """Run all detectors. Returns {'score': float 0-1, 'patterns': List[str], 'detail': dict}."""
    if prices is None or len(prices) == 0:
        return {"score": 0.0, "patterns": [], "detail": {}}
    close = prices["Close"].astype("float64")
    volume = prices["Volume"].astype("float64")

    cup = _detect_cup_and_handle(close)
    breakout = _detect_breakout(close, volume)
    trend = _detect_uptrend(close)
    rsi_val = float(rsi(close, 14).iloc[-1])
    # healthy momentum band 50-70 is good; overbought >80 penalized
    rsi_score = 1.0 if 50 <= rsi_val <= 70 else (0.5 if 40 <= rsi_val < 50 else 0.0)

    patterns: List[str] = []
    if cup > 0:
        patterns.append("cup_and_handle")
    if breakout > 0:
        patterns.append("breakout")
    if trend > 0:
        patterns.append("uptrend")

    # weighted blend; cup & breakout are the headline signals
    score = 0.4 * cup + 0.3 * breakout + 0.2 * trend + 0.1 * rsi_score
    score = float(max(0.0, min(1.0, score)))
    detail = {"cup": cup, "breakout": breakout, "trend": trend, "rsi": rsi_val}
    return {"score": score, "patterns": patterns, "detail": detail}
