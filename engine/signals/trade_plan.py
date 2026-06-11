# engine/signals/trade_plan.py
"""ATR- and structure-based trade plan for a surfaced lead.

Produces entry / stop / two targets / risk-reward so every suggestion comes
with concrete levels instead of just a score. This frames the research lead —
it is not an order ticket and nothing here is advice.

Method:
- entry:   last close (leads are surfaced at, or just before, actionable levels)
- stop:    the tighter of (recent 20-bar swing low, entry - 2*ATR), never
           closer than 1*ATR (a stop inside the daily noise band is just churn)
- target1: entry + 2*ATR  (a "take some off" level)
- target2: measured move when a structural pattern fired (cup depth / flag
           pole projected from entry), else entry + 4*ATR
- rr:      (target1 - entry) / (entry - stop)
"""
import math
from typing import Dict, List, Optional
import pandas as pd

from engine.signals.indicators import atr, swing_low, recent_high


def _round_price(x: float) -> float:
    """Round to a sensible number of decimals for the price's magnitude."""
    if x >= 1000:
        return round(x, 0)
    if x >= 10:
        return round(x, 2)
    if x >= 0.1:
        return round(x, 4)
    return round(x, 6)


def build_trade_plan(prices: pd.DataFrame,
                     patterns: Optional[List[str]] = None) -> Optional[Dict]:
    """Return {entry, stop, target1, target2, rr, atr_pct, method} or None."""
    if prices is None or len(prices) < 30:
        return None
    close = prices["Close"].astype("float64")
    high = prices["High"].astype("float64") if "High" in prices else close
    low = prices["Low"].astype("float64") if "Low" in prices else close

    entry = float(close.iloc[-1])
    if entry <= 0:
        return None
    atr_series = atr(high, low, close, 14).dropna()
    if len(atr_series) == 0:
        return None
    a = float(atr_series.iloc[-1])
    if a <= 0 or math.isnan(a):
        return None

    # Stop: structure first (swing low), volatility as the backstop.
    structural = swing_low(low, lookback=20)
    volatility = entry - 2.0 * a
    stop = max(structural, volatility)          # the tighter (higher) of the two
    stop = min(stop, entry - 1.0 * a)           # but never inside the noise band
    if stop <= 0 or stop >= entry:
        stop = entry - 2.0 * a
    if stop <= 0:
        return None

    target1 = entry + 2.0 * a
    target2 = entry + 4.0 * a
    method = "2x/4x ATR"

    patterns = patterns or []
    if "cup_and_handle" in patterns and len(close) >= 77:
        # measured move: project the cup depth above the rim
        window = close.iloc[-77:]
        rim = recent_high(window, lookback=len(window))
        depth = rim - float(window.min())
        if depth > 0:
            target2 = max(target2, entry + depth)
            method = "cup measured move"
    elif "bull_flag" in patterns and len(close) >= 30:
        # project the pole height from the flag
        pole = close.iloc[-30:-10]
        pole_height = float(pole.max()) - float(pole.iloc[0])
        if pole_height > 0:
            target2 = max(target2, entry + pole_height)
            method = "flag pole projection"

    risk = entry - stop
    reward = target1 - entry
    rr = reward / risk if risk > 0 else 0.0

    return {
        "entry": _round_price(entry),
        "stop": _round_price(stop),
        "target1": _round_price(target1),
        "target2": _round_price(target2),
        "rr": round(rr, 2),
        "atr_pct": round(a / entry, 4),
        "method": method,
    }
