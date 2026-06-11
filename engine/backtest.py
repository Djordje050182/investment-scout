# engine/backtest.py
"""Walk-forward backtest of the pattern detectors.

For each symbol in the chosen universe, downloads up to SCOUT_BT_YEARS of
daily history and slides a 260-bar window forward in 5-bar (weekly) steps.
At each step it runs scan_technical on the window — exactly what the daily
scan sees, no look-ahead — records which patterns fired, and measures what
price did 5 / 21 / 63 trading days later.

The BASELINE row is every evaluation point regardless of signals: the
universe's average forward drift. A detector only has edge if it beats it.

Caveats (also shipped in the JSON so the UI can disclose them):
- survivorship bias: today's universe replayed into the past;
- no costs/slippage; close-to-close returns;
- pattern co-occurrence is not disentangled.

Usage:  python -m engine.backtest          (env: SCOUT_BT_UNIVERSE, SCOUT_BT_YEARS)
Writes docs/data/backtest.json and prints a summary table.
"""
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from engine.signals.technical import scan_technical
from engine.universe import get_universe

DEFAULT_OUT = "docs/data/backtest.json"
WINDOW = 260            # bars given to the detectors (what the scan sees)
STEP = 5                # evaluate weekly
HORIZONS = (5, 21, 63)  # forward trading days


def forward_returns(close: pd.Series, t: int) -> Dict[str, float]:
    """Close-to-close forward returns from bar t-1 (the last in-window bar)."""
    entry = float(close.iloc[t - 1])
    out = {}
    for h in HORIZONS:
        if t - 1 + h < len(close):
            out["r{}".format(h)] = float(close.iloc[t - 1 + h]) / entry - 1.0
    return out


def walk_symbol(prices: pd.DataFrame, window: int = WINDOW,
                step: int = STEP) -> List[Dict]:
    """All (patterns fired, forward returns) evaluation points for one symbol."""
    rows: List[Dict] = []
    close = prices["Close"].astype("float64")
    n = len(prices)
    for t in range(window, n - min(HORIZONS) + 1, step):
        win = prices.iloc[t - window:t]
        res = scan_technical(win)
        fwd = forward_returns(close, t)
        if not fwd:
            continue
        rows.append({"patterns": res["patterns"], "returns": fwd,
                     "score": res["score"]})
    return rows


def _stats(returns: List[float]) -> Dict:
    n = len(returns)
    if n == 0:
        return {}
    wins = sum(1 for r in returns if r > 0)
    return {
        "n": n,
        "win_rate": round(wins / n, 3),
        "avg": round(sum(returns) / n, 4),
        "median": round(sorted(returns)[n // 2], 4),
    }


def aggregate(rows: List[Dict]) -> Dict:
    """Per-pattern (and baseline) stats at each horizon."""
    def collect(filter_pattern: Optional[str]) -> Dict:
        out = {}
        for h in HORIZONS:
            key = "r{}".format(h)
            vals = [r["returns"][key] for r in rows
                    if key in r["returns"]
                    and (filter_pattern is None or filter_pattern in r["patterns"])]
            s = _stats(vals)
            if s:
                out[key] = s
        return out

    patterns = sorted({p for r in rows for p in r["patterns"]})
    return {
        "baseline": collect(None),
        "by_pattern": {p: collect(p) for p in patterns},
    }


def main() -> None:
    universe_name = os.environ.get("SCOUT_BT_UNIVERSE", "us")
    years = int(os.environ.get("SCOUT_BT_YEARS", "8"))
    symbols = get_universe(universe_name)
    period = "{}y".format(years)

    all_rows: List[Dict] = []
    evaluated = 0
    for i, sym in enumerate(symbols):
        try:
            prices = yf.Ticker(sym).history(period=period, auto_adjust=False)
            if prices is None or len(prices) < WINDOW + 70:
                print("skip {} (too little history)".format(sym))
                continue
            rows = walk_symbol(prices)
            all_rows.extend(rows)
            evaluated += 1
            print("{}/{} {}: {} eval points".format(i + 1, len(symbols), sym, len(rows)))
        except Exception as exc:
            print("skip {}: {}".format(sym, exc))

    agg = aggregate(all_rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe": universe_name,
        "years": years,
        "symbols_evaluated": evaluated,
        "eval_points": len(all_rows),
        "caveats": ["survivorship bias (today's universe replayed)",
                    "no costs or slippage; close-to-close",
                    "co-occurring patterns not disentangled"],
        "aggregates": agg,
    }
    os.makedirs(os.path.dirname(DEFAULT_OUT), exist_ok=True)
    with open(DEFAULT_OUT, "w") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")))

    base = agg["baseline"].get("r21", {})
    print("\n=== 21-day horizon (baseline win {} avg {}) ===".format(
        base.get("win_rate"), base.get("avg")))
    for p, stats in sorted(agg["by_pattern"].items(),
                           key=lambda kv: -(kv[1].get("r21", {}).get("avg") or -9)):
        s = stats.get("r21", {})
        if s:
            print("{:22s} n={:5d}  win={:.0%}  avg={:+.2%}  med={:+.2%}".format(
                p, s["n"], s["win_rate"], s["avg"], s["median"]))
    print("\nwrote {}".format(DEFAULT_OUT))


if __name__ == "__main__":
    main()
