# engine/run_scan.py
"""Daily scan orchestrator: fetch -> score -> write signals.json -> email.

signals.json now carries everything the dashboard needs:
- suggestions: leads that cleared the conviction bar, each with an embedded
  chart (last ~130 OHLCV bars + SMA overlays), an indicator snapshot, and a
  trade plan (entry / stop / targets / R:R);
- radar: near-misses (conviction 35..threshold) worth watching;
- movers: the day's biggest gainers and losers across the scanned universe;
- market: benchmark trend reads + breadth + a one-word regime label.
"""
import json
import math
import os
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

from engine.adapters.base import DataAdapter, MarketData
from engine.adapters.yfinance_us import YFinanceUSAdapter, has_fundamentals
from engine.signals.technical import scan_technical
from engine.signals.fundamental import scan_fundamental
from engine.signals.conviction import score_conviction, passes, THRESHOLD
from engine.signals.explain import explain_suggestion
from engine.signals.scores import backing_score, strength_score
from engine.signals.trade_plan import build_trade_plan
from engine.signals.regime import build_market_block, BENCHMARKS
from engine.universe import get_universe
from engine.notify.email import build_digest, send_email

DEFAULT_OUT = "docs/data/signals.json"
DEFAULT_HISTORY = "docs/data/history"

RADAR_MIN = 50          # conviction floor for the near-miss radar list
CHART_BARS = 130        # OHLCV bars embedded per suggestion
EARNINGS_WINDOW = 21    # flag earnings this many days out (binary-event warning)

# Benchmark used for each market's relative-strength read.
BENCH_FOR = {"US": "SPY", "ASX": "^AXJO", "Crypto": "BTC-USD"}


def bench_returns(benchmark_prices: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, float]]:
    """1m/3m returns per benchmark symbol, for relative-strength comparison."""
    out: Dict[str, Dict[str, float]] = {}
    for sym, prices in benchmark_prices.items():
        if prices is None or len(prices) < 64:
            continue
        close = prices["Close"].astype("float64")
        r1m = float(close.iloc[-1] / close.iloc[-22] - 1.0)
        r3m = float(close.iloc[-1] / close.iloc[-64] - 1.0)
        out[sym] = {"ret_1m": r1m, "ret_3m": r3m}
    return out


def _add_relative_strength(snapshot: Dict, market: str,
                           bench: Optional[Dict[str, Dict[str, float]]]) -> None:
    """Attach rel_1m / rel_3m (symbol return minus benchmark return) in place."""
    if not bench:
        return
    b = bench.get(BENCH_FOR.get(market, "SPY"))
    if not b:
        return
    for key, rel_key in (("ret_1m", "rel_1m"), ("ret_3m", "rel_3m")):
        r = snapshot.get(key)
        if r is not None and b.get(key) is not None:
            snapshot[rel_key] = round(r - b[key], 4)


def _build_company(md: MarketData, fundamental: Dict) -> Dict:
    """Assemble the company block: profile fields, named backers, and the two scores."""
    profile = md.profile or {}
    fund_present = has_fundamentals(md.market)
    company = dict(profile)
    company["holders"] = md.holders or []
    company["backing_score"] = backing_score(profile)
    company["strength_score"] = strength_score(fundamental, has_fundamentals=fund_present)
    return company


def _round_sig(x: float) -> Optional[float]:
    """Compact price rounding for chart payloads."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if abs(x) >= 100:
        return round(x, 2)
    if abs(x) >= 1:
        return round(x, 3)
    return round(x, 6)


def build_chart(prices: pd.DataFrame, bars: int = CHART_BARS) -> Dict:
    """Compact OHLCV + SMA overlays for the dashboard's candlestick chart.

    SMAs are computed on the FULL history, then trimmed to the chart window,
    so the 200-day line is correct from the first visible bar.
    """
    close_full = prices["Close"].astype("float64")
    sma50_full = close_full.rolling(50, min_periods=50).mean()
    sma200_full = close_full.rolling(200, min_periods=200).mean()
    tail = prices.iloc[-bars:]
    idx = tail.index

    def col(name: str) -> List[Optional[float]]:
        if name not in tail:
            return [None] * len(tail)
        return [_round_sig(float(v)) for v in tail[name]]

    dates = [d.strftime("%Y-%m-%d") for d in idx]
    return {
        "dates": dates,
        "open": col("Open"),
        "high": col("High"),
        "low": col("Low"),
        "close": col("Close"),
        "volume": [int(v) if not math.isnan(float(v)) else 0
                   for v in tail.get("Volume", pd.Series([0.0] * len(tail), index=idx))],
        "sma50": [_round_sig(float(v)) for v in sma50_full.loc[idx]],
        "sma200": [_round_sig(float(v)) for v in sma200_full.loc[idx]],
    }


def _chg_1d(prices: pd.DataFrame) -> Optional[float]:
    close = prices["Close"].astype("float64")
    if len(close) < 2 or float(close.iloc[-2]) == 0:
        return None
    return round(float(close.iloc[-1]) / float(close.iloc[-2]) - 1.0, 4)


def _score_one(md: MarketData) -> Dict:
    """Score a single symbol; returns the scored bundle (pass/fail decided later)."""
    technical = scan_technical(md.prices)
    fundamental = scan_fundamental(md.fundamentals)
    scored = score_conviction(technical, fundamental)
    return {"md": md, "technical": technical, "fundamental": fundamental,
            "scored": scored}


def _earnings_block(md: MarketData) -> Optional[Dict]:
    """{date, days} when the next earnings report is inside the warning window."""
    if not md.earnings_date:
        return None
    try:
        d = date.fromisoformat(md.earnings_date[:10])
    except ValueError:
        return None
    days = (d - date.today()).days
    if 0 <= days <= EARNINGS_WINDOW:
        return {"date": md.earnings_date[:10], "days": days}
    return None


def _to_suggestion(bundle: Dict, bench: Optional[Dict] = None) -> Dict:
    md, technical, fundamental, scored = (bundle["md"], bundle["technical"],
                                          bundle["fundamental"], bundle["scored"])
    suggestion = {
        "symbol": md.symbol,
        "market": md.market,
        "price": md.price,
        "chg_1d": _chg_1d(md.prices),
        "conviction": scored["conviction"],
        "tier": scored["tier"],
        "reasons": scored["reasons"],
        "technical": {
            "score": technical["score"],
            "patterns": technical["patterns"],
            "strengths": technical.get("strengths", {}),
            "detail": technical.get("detail", {}),
        },
        "fundamental": {"score": fundamental["score"],
                        "quality": fundamental["quality"],
                        "value": fundamental["value"],
                        "moat": fundamental["moat"],
                        "management": fundamental.get("management", 0.0)},
        "snapshot": dict(technical.get("snapshot", {})),
        "trade_plan": build_trade_plan(md.prices, technical["patterns"]),
        "chart": build_chart(md.prices),
    }
    _add_relative_strength(suggestion["snapshot"], md.market, bench)
    earnings = _earnings_block(md)
    if earnings:
        suggestion["earnings"] = earnings
    suggestion["summary"] = explain_suggestion(suggestion)
    suggestion["company"] = _build_company(md, fundamental)
    return suggestion


def _to_radar(bundle: Dict, bench: Optional[Dict] = None) -> Dict:
    """Compact near-miss entry: enough to show a row, no chart payload."""
    md, technical, scored = bundle["md"], bundle["technical"], bundle["scored"]
    snap = {k: technical.get("snapshot", {}).get(k)
            for k in ("rsi14", "adx14", "high_52w_dist", "ret_1m", "ret_3m")}
    _add_relative_strength(snap, md.market, bench)
    return {
        "symbol": md.symbol,
        "market": md.market,
        "price": md.price,
        "chg_1d": _chg_1d(md.prices),
        "conviction": scored["conviction"],
        "tier": scored["tier"],
        "patterns": technical["patterns"][:3],
        "snapshot": snap,
    }


def build_movers(bundles: List[Dict], top: int = 5) -> Dict[str, List[Dict]]:
    """Biggest 1-day gainers and losers across everything fetched."""
    rows = []
    for b in bundles:
        chg = _chg_1d(b["md"].prices)
        if chg is None:
            continue
        rows.append({"symbol": b["md"].symbol, "market": b["md"].market,
                     "price": b["md"].price, "chg_1d": chg})
    rows.sort(key=lambda r: r["chg_1d"], reverse=True)
    return {"gainers": rows[:top],
            "losers": sorted(rows[-top:], key=lambda r: r["chg_1d"])}


def build_scan(adapter: DataAdapter, symbols: List[str],
               bench: Optional[Dict] = None) -> Dict:
    """Fetch + score the universe; return suggestions, radar, movers, breadth input."""
    bundles = [_score_one(md) for md in adapter.fetch(symbols)]

    suggestions = [_to_suggestion(b, bench) for b in bundles if passes(b["scored"])]
    suggestions.sort(key=lambda s: s["conviction"], reverse=True)

    radar = [_to_radar(b, bench) for b in bundles
             if not passes(b["scored"])
             and b["scored"]["conviction"] >= RADAR_MIN
             and b["scored"]["tier"] != "none"]
    radar.sort(key=lambda r: r["conviction"], reverse=True)

    return {
        "suggestions": suggestions,
        "radar": radar,
        "movers": build_movers(bundles),
        "universe_prices": [b["md"].prices for b in bundles],
    }


# Back-compat wrapper used by tests and any external callers.
def build_suggestions(adapter: DataAdapter, symbols: List[str]) -> List[Dict]:
    """Fetch each symbol, score it, return suggestions that pass the threshold."""
    return build_scan(adapter, symbols)["suggestions"]


def write_output(payload: Dict, out_file: str, history_dir: str) -> None:
    """Write signals.json and a dated history snapshot. Only called on success.

    History snapshots drop the heavy per-suggestion chart payloads to keep the
    repo small; the latest signals.json keeps them for the dashboard.
    """
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    os.makedirs(history_dir, exist_ok=True)
    # compact JSON: chart arrays make indented output ~10x larger in git
    with open(out_file, "w") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")))

    slim = dict(payload)
    slim["suggestions"] = [
        {k: v for k, v in s.items() if k != "chart"} for s in payload["suggestions"]
    ]
    stamp = payload["scanned_at"].replace(":", "").replace("-", "")[:15]
    with open(os.path.join(history_dir, "{}.json".format(stamp)), "w") as fh:
        fh.write(json.dumps(slim, separators=(",", ":")))


def main() -> None:
    universe_name = os.environ.get("SCOUT_UNIVERSE", "starter")
    symbols = get_universe(universe_name)
    scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    adapter = YFinanceUSAdapter()

    benchmark_prices = adapter.fetch_history(list(BENCHMARKS.keys()))
    scan = build_scan(adapter, symbols, bench=bench_returns(benchmark_prices))
    market = build_market_block(benchmark_prices, scan["universe_prices"])

    payload = {
        "scanned_at": scanned_at,
        "universe": universe_name,
        "threshold": THRESHOLD,
        "count": len(scan["suggestions"]),
        "market": market,
        "suggestions": scan["suggestions"],
        "radar": scan["radar"],
        "movers": scan["movers"],
    }
    write_output(payload, DEFAULT_OUT, DEFAULT_HISTORY)

    digest = build_digest(scan["suggestions"], scanned_at)
    if digest is not None:
        send_email(digest[0], digest[1])
    print("scan complete: {} suggestions, {} on radar, from {} symbols".format(
        len(scan["suggestions"]), len(scan["radar"]), len(symbols)))


if __name__ == "__main__":
    main()
