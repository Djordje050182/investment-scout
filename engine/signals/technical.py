# engine/signals/technical.py
"""Technical pattern detection. Input: OHLCV DataFrame. Output: {score, patterns}."""
from typing import Dict, List
import pandas as pd
from engine.signals.indicators import sma, rsi, recent_high


# --- Cup-and-handle gate thresholds (tuned to reject look-alikes) ------------
_CUP_MIN_BARS = 70          # need a long enough base to be a real cup
_CUP_WINDOW = 77            # bars examined for the pattern
_CUP_HANDLE_BARS = 12       # trailing bars treated as the handle
_CUP_RIM_BARS = 5           # leading bars defining the left rim
_DEPTH_MIN = 0.12           # cup must be a meaningful pullback...
_DEPTH_MAX = 0.50           # ...but not a crash
_RIM_BALANCE_MIN = 0.90     # left and right rims must be close in height
_BOTTOM_POS_LO = 0.30       # the low must sit in the middle of the cup...
_BOTTOM_POS_HI = 0.70       # ...not at an edge (that's a V or a slide)
_ROUNDNESS_MIN = 0.55       # time spent basing near the low (rounded, not a V)
_HANDLE_DIP_MIN = 0.02      # a real handle pulls back at least a little...
_HANDLE_DIP_MAX = 0.15      # ...but stays shallow
_HANDLE_FLOOR = 0.50        # handle low must stay in the upper half of the base
_PROXIMITY_MIN = 0.96       # price must be within ~4% of the rim (breakout-ready)


def _roundness(cup: pd.Series, cup_bottom: float, left_rim: float) -> float:
    """Fraction of cup bars sitting in the lowest third of its depth.

    A rounded cup spends real time near the low; a sharp V touches the low for
    one bar. Returns 0-1 (higher = rounder).
    """
    depth = left_rim - cup_bottom
    if depth <= 0 or len(cup) == 0:
        return 0.0
    low_band = cup_bottom + depth / 3.0
    return float((cup <= low_band).sum()) / float(len(cup))


def _detect_cup_and_handle(close: pd.Series) -> float:
    """Return 0-1 strength of a cup-and-handle ending near now, else 0.

    Every structural requirement is a hard GATE (returns 0 if unmet), so the
    score only reflects how strong a genuine pattern is — not how many loose
    look-alikes slipped through. Gates, in order:
      1. enough bars for a real base;
      2. cup depth in a sane band (meaningful pullback, not a crash);
      3. left and right rims roughly level;
      4. the low sits in the middle of the cup (not at an edge -> a V/slide);
      5. the base is ROUND (time spent near the low), rejecting sharp V-bottoms;
      6. a real but shallow HANDLE pullback that holds the upper half of the base;
      7. price now within ~4% of the rim (breakout-ready).
    """
    n = len(close)
    if n < _CUP_MIN_BARS:
        return 0.0
    vals = close.iloc[-_CUP_WINDOW:].reset_index(drop=True)
    w = len(vals)
    cup_end = w - _CUP_HANDLE_BARS
    if cup_end <= _CUP_RIM_BARS:
        return 0.0

    left_rim = float(vals.iloc[:_CUP_RIM_BARS].max())
    cup = vals.iloc[_CUP_RIM_BARS:cup_end]
    handle = vals.iloc[cup_end:]
    if len(cup) == 0 or left_rim <= 0:
        return 0.0

    cup_bottom = float(cup.min())
    bottom_idx = int(cup.idxmin())
    right_rim = float(handle.max())
    now = float(vals.iloc[-1])

    # Gate 2: depth band
    depth = (left_rim - cup_bottom) / left_rim
    if depth < _DEPTH_MIN or depth > _DEPTH_MAX:
        return 0.0

    # Gate 3: rims roughly level
    rim_balance = 1.0 - min(1.0, abs(left_rim - right_rim) / left_rim)
    if rim_balance < _RIM_BALANCE_MIN:
        return 0.0

    # Gate 4: low in the middle of the cup
    pos = (bottom_idx - _CUP_RIM_BARS) / max(1, (cup_end - _CUP_RIM_BARS))
    if pos < _BOTTOM_POS_LO or pos > _BOTTOM_POS_HI:
        return 0.0

    # Gate 5: roundness — reject sharp V-bottoms
    roundness = _roundness(cup, cup_bottom, left_rim)
    if roundness < _ROUNDNESS_MIN:
        return 0.0

    # Gate 6: a real, shallow handle holding the upper half of the base
    handle_low = float(handle.min())
    handle_dip = (right_rim - handle_low) / right_rim if right_rim else 1.0
    if handle_dip < _HANDLE_DIP_MIN or handle_dip > _HANDLE_DIP_MAX:
        return 0.0
    handle_floor_level = cup_bottom + _HANDLE_FLOOR * (left_rim - cup_bottom)
    if handle_low < handle_floor_level:
        return 0.0

    # Gate 7: breakout-ready proximity to the rim
    proximity = 1.0 - min(1.0, abs(right_rim - now) / right_rim)
    if proximity < _PROXIMITY_MIN:
        return 0.0

    # Strength: reward roundness, level rims, and proximity; penalize a deep handle.
    score = (0.30 * rim_balance + 0.30 * roundness + 0.25 * proximity
             + 0.15 * (1.0 - handle_dip / _HANDLE_DIP_MAX))
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
    if pd.isna(rsi_val):
        # Not enough bars to compute RSI yet: treat as neutral, score 0.5.
        rsi_val = 50.0
        rsi_score = 0.5
    else:
        # rising momentum (above the 50 neutral line, not overbought) is bullish;
        # a dead-neutral RSI of 50 is not a signal on its own.
        rsi_score = 1.0 if 50 < rsi_val <= 70 else (0.5 if 40 <= rsi_val < 50 else 0.0)

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
