# engine/signals/regime.py
"""Market regime: benchmark health + scan-universe breadth.

The same setup is worth more in a rising tide. This module produces the
"market" block of signals.json: per-benchmark trend reads plus breadth
statistics computed across everything the scan fetched (not just what passed).
"""
import math
from typing import Dict, List, Optional
import pandas as pd

from engine.signals.indicators import sma, rsi, roc

# Benchmarks fetched alongside the universe. Keys are display labels.
BENCHMARKS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "^AXJO": "ASX 200",
    "BTC-USD": "Bitcoin",
}


def _nan_none(x: float, nd: int = 4) -> Optional[float]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


def benchmark_read(prices: pd.DataFrame) -> Optional[Dict]:
    """Trend read for one benchmark: price, changes, trend state."""
    if prices is None or len(prices) < 30:
        return None
    # drop NaN closes (exchange holidays leave gaps) — a NaN last price would
    # serialise as literal NaN, which is invalid JSON and breaks the dashboard
    close = prices["Close"].astype("float64").dropna()
    if len(close) < 30:
        return None
    price = float(close.iloc[-1])
    s50 = sma(close, 50)
    s200 = sma(close, 200)
    s50_last = float(s50.iloc[-1]) if not math.isnan(float(s50.iloc[-1])) else None
    s200_last = None
    if len(close) >= 200:
        v = float(s200.iloc[-1])
        s200_last = v if not math.isnan(v) else None

    if s50_last and s200_last:
        if price > s50_last and s50_last > s200_last:
            trend = "uptrend"
        elif price < s50_last and s50_last < s200_last:
            trend = "downtrend"
        else:
            trend = "mixed"
    elif s50_last:
        trend = "uptrend" if price > s50_last else "mixed"
    else:
        trend = "unknown"

    return {
        "price": round(price, 2),
        "chg_1d": _nan_none(float(roc(close, 1).iloc[-1])),
        "chg_5d": _nan_none(float(roc(close, 5).iloc[-1])),
        "chg_1m": _nan_none(float(roc(close, 21).iloc[-1]) if len(close) > 21 else float("nan")),
        "trend": trend,
        "rsi14": _nan_none(float(rsi(close, 14).iloc[-1]), 1),
    }


def breadth(all_prices: List[pd.DataFrame]) -> Optional[Dict]:
    """Breadth across every symbol the scan fetched.

    pct_above_50dma / pct_above_200dma / pct_rsi_bullish are 0-1 fractions of
    the symbols with enough history for each measure.
    """
    above50 = above200 = rsi_bull = 0
    n50 = n200 = nrsi = 0
    for prices in all_prices:
        if prices is None or len(prices) < 60:
            continue
        close = prices["Close"].astype("float64")
        price = float(close.iloc[-1])
        s50 = float(sma(close, 50).iloc[-1])
        if not math.isnan(s50):
            n50 += 1
            if price > s50:
                above50 += 1
        if len(close) >= 200:
            s200 = float(sma(close, 200).iloc[-1])
            if not math.isnan(s200):
                n200 += 1
                if price > s200:
                    above200 += 1
        r = float(rsi(close, 14).iloc[-1])
        if not math.isnan(r):
            nrsi += 1
            if r > 50.0:
                rsi_bull += 1
    if n50 == 0:
        return None
    out = {
        "pct_above_50dma": round(above50 / n50, 3),
        "symbols": n50,
    }
    if n200:
        out["pct_above_200dma"] = round(above200 / n200, 3)
    if nrsi:
        out["pct_rsi_bullish"] = round(rsi_bull / nrsi, 3)
    return out


def regime_label(benchmarks: Dict[str, Dict], breadth_stats: Optional[Dict]) -> str:
    """One-word market read: risk_on / neutral / risk_off."""
    score = 0.0
    weight = 0.0
    for key in ("SPY", "QQQ"):
        b = benchmarks.get(key)
        if not b:
            continue
        weight += 1.0
        if b["trend"] == "uptrend":
            score += 1.0
        elif b["trend"] == "mixed":
            score += 0.5
    if breadth_stats and "pct_above_50dma" in breadth_stats:
        weight += 1.0
        score += float(breadth_stats["pct_above_50dma"])
    if weight == 0:
        return "neutral"
    frac = score / weight
    if frac >= 0.65:
        return "risk_on"
    if frac <= 0.35:
        return "risk_off"
    return "neutral"


def build_market_block(benchmark_prices: Dict[str, pd.DataFrame],
                       universe_prices: List[pd.DataFrame]) -> Dict:
    """Assemble the full market block for signals.json."""
    benchmarks: Dict[str, Dict] = {}
    for symbol, label in BENCHMARKS.items():
        read = benchmark_read(benchmark_prices.get(symbol))
        if read is not None:
            read["label"] = label
            benchmarks[symbol] = read
    breadth_stats = breadth(universe_prices)
    return {
        "regime": regime_label(benchmarks, breadth_stats),
        "benchmarks": benchmarks,
        "breadth": breadth_stats,
    }
