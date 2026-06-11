# engine/ai_scan.py
"""Scan the AI supply chain (engine/ai_chain.py) and write docs/data/ai_chain.json.

Per company:
- momentum: returns, relative strength vs the chain benchmark (SMH),
  distance from the 52-week high, trend state;
- growth: revenue growth, earnings growth, gross margin (yfinance .info);
- value-for-growth: forward P/E against growth (PEG-style) + analyst upside;
- ai_score 0-100 = 0.40 momentum + 0.35 growth + 0.25 value.

Per layer:
- heat 0-100 from median relative strength + breadth (% above the 50-day);
  the chain re-rates layer by layer, so the heat map IS the rotation story.

Radar (the "don't miss the boat" logic):
- catch_up — the Micron pattern: a HOT layer where this name still lags the
  layer median, fundamentals are intact, trend holds, and it's not the most
  expensive of its peers. Demand reached the layer; this name hasn't re-rated.
- leaders — strength leading the whole chain (near highs, top scores).

Usage: python -m engine.ai_scan
"""
import json
import math
import os
import time
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from engine.ai_chain import LAYERS, ETFS, BENCHMARK, all_company_symbols
from engine.adapters.yfinance_us import YFinanceUSAdapter
from engine.signals.indicators import sma, rsi, roc, recent_high

DEFAULT_OUT = "docs/data/ai_chain.json"
SPARK_BARS = 90
HOT_LAYER = 60          # layer heat at/above this = "hot" (rotation has arrived)
EARNINGS_WINDOW = 21


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _band(value: Optional[float], good: float, bad: float) -> Optional[float]:
    """Linear 0-1 score, like the fundamental screen's band helper."""
    if value is None:
        return None
    if good == bad:
        return 0.5
    return _clamp01((value - bad) / (good - bad))


def _avg(parts: List[Optional[float]]) -> Optional[float]:
    present = [p for p in parts if p is not None]
    return sum(present) / len(present) if present else None


# ---------------------------------------------------------------------------
# Pure scoring (unit-tested)
# ---------------------------------------------------------------------------

def score_company(m: Dict) -> Dict[str, Optional[int]]:
    """0-100 momentum / growth / value sub-scores + blended ai_score.

    Input keys (any may be None): rel_3m, high_52w_dist, above_200dma,
    rev_growth, earn_growth, gross_margin, fwd_pe, upside.
    """
    momentum = _avg([
        _band(m.get("rel_3m"), good=0.15, bad=-0.15),
        _band(m.get("high_52w_dist"), good=0.0, bad=-0.30),
        1.0 if m.get("above_200dma") else 0.0,
    ])
    growth = _avg([
        _band(m.get("rev_growth"), good=0.30, bad=0.0),
        _band(m.get("earn_growth"), good=0.50, bad=0.0),
        _band(m.get("gross_margin"), good=0.60, bad=0.20),
    ])
    peg = None
    fwd_pe, rev_g = m.get("fwd_pe"), m.get("rev_growth")
    if fwd_pe and fwd_pe > 0 and rev_g and rev_g > 0:
        peg = fwd_pe / (rev_g * 100.0)
    value = _avg([
        _band(peg, good=0.8, bad=3.0),
        _band(m.get("upside"), good=0.30, bad=-0.10),
    ])

    def to100(x):
        return None if x is None else int(round(100 * x))

    parts = [(momentum, 0.40), (growth, 0.35), (value, 0.25)]
    present = [(v, w) for v, w in parts if v is not None]
    ai = None
    if present:
        wsum = sum(w for _, w in present)
        ai = int(round(100 * sum(v * w for v, w in present) / wsum))
    return {"momentum_score": to100(momentum), "growth_score": to100(growth),
            "value_score": to100(value), "ai_score": ai}


def layer_heat(companies: List[Dict]) -> Dict:
    """Layer heat 0-100: median relative strength blended with breadth."""
    rels = sorted(c["rel_3m"] for c in companies if c.get("rel_3m") is not None)
    above = [c for c in companies if c.get("above_50dma") is not None]
    if not rels:
        return {"score": None, "label": "unknown", "median_rel_3m": None,
                "pct_above_50dma": None, "n": len(companies)}
    median_rel = rels[len(rels) // 2]
    rel_part = _band(median_rel, good=0.10, bad=-0.10)
    breadth = (sum(1 for c in above if c["above_50dma"]) / len(above)) if above else None
    score = _avg([rel_part, breadth])
    score100 = int(round(100 * score)) if score is not None else None
    label = ("hot" if score100 is not None and score100 >= HOT_LAYER
             else "cool" if score100 is not None and score100 <= 40
             else "warm")
    return {"score": score100, "label": label,
            "median_rel_3m": round(median_rel, 4),
            "pct_above_50dma": round(breadth, 3) if breadth is not None else None,
            "n": len(companies)}


def find_catch_up(layer: Dict, heat: Dict) -> List[Dict]:
    """The Micron pattern: hot layer, lagging-but-healthy member.

    Conditions: layer hot; rel_3m below the layer median; growth_score >= 50;
    still above its 200-day (the trend is intact, it just hasn't re-rated);
    and forward P/E not the richest of its peers.
    """
    if heat.get("score") is None or heat["score"] < HOT_LAYER:
        return []
    median_rel = heat.get("median_rel_3m") or 0.0
    pes = sorted(c["fwd_pe"] for c in layer["companies"] if c.get("fwd_pe"))
    median_pe = pes[len(pes) // 2] if pes else None
    out = []
    for c in layer["companies"]:
        if c.get("rel_3m") is None or c["rel_3m"] >= median_rel:
            continue
        if (c.get("growth_score") or 0) < 50:
            continue
        if not c.get("above_200dma"):
            continue
        if median_pe and c.get("fwd_pe") and c["fwd_pe"] > 1.5 * median_pe:
            continue
        out.append({
            "symbol": c["symbol"], "name": c.get("name"), "layer": layer["name"],
            "layer_key": layer["key"], "price": c.get("price"),
            "currency": c.get("currency", "USD"),
            "rel_3m": c["rel_3m"], "gap_to_layer": round(median_rel - c["rel_3m"], 4),
            "growth_score": c.get("growth_score"), "fwd_pe": c.get("fwd_pe"),
            "ai_score": c.get("ai_score"),
            "thesis": ("{} is hot (heat {}) but {} lags the layer median by {:.0f}pp "
                       "with growth intact — the rotation may not have reached it yet."
                       ).format(layer["name"], heat["score"], c["symbol"],
                                100 * (median_rel - c["rel_3m"])),
        })
    out.sort(key=lambda x: -(x["gap_to_layer"] or 0))
    return out


# ---------------------------------------------------------------------------
# Fetch + assemble
# ---------------------------------------------------------------------------

def _series_metrics(prices: pd.DataFrame) -> Dict:
    close = prices["Close"].astype("float64")
    n = len(close)
    price = float(close.iloc[-1])
    out: Dict = {"price": price}
    out["chg_1d"] = round(float(close.iloc[-1] / close.iloc[-2] - 1.0), 4) if n >= 2 else None
    for label, bars in (("ret_1m", 21), ("ret_3m", 63), ("ret_6m", 126)):
        out[label] = round(float(roc(close, bars).iloc[-1]), 4) if n > bars else None
    hi = recent_high(close, lookback=min(n, 252))
    out["high_52w_dist"] = round(price / hi - 1.0, 4) if hi > 0 else None
    s50 = sma(close, 50)
    s200 = sma(close, 200)
    v50 = float(s50.iloc[-1]) if n >= 50 else float("nan")
    v200 = float(s200.iloc[-1]) if n >= 200 else float("nan")
    out["above_50dma"] = bool(price > v50) if not math.isnan(v50) else None
    out["above_200dma"] = bool(price > v200) if not math.isnan(v200) else None
    r = float(rsi(close, 14).iloc[-1])
    out["rsi14"] = round(r, 1) if not math.isnan(r) else None
    step = max(1, len(close.iloc[-SPARK_BARS:]) // SPARK_BARS)
    spark = close.iloc[-SPARK_BARS:][::step]
    out["spark"] = [round(float(v), 4 if price < 10 else 2) for v in spark]
    return out


def _info_metrics(info: Dict, price: float) -> Dict:
    def num(key):
        v = info.get(key)
        return float(v) if isinstance(v, (int, float)) else None

    target = num("targetMeanPrice")
    return {
        "name": (info.get("shortName") or "").strip() or None,
        "currency": info.get("currency") or "USD",
        "market_cap": num("marketCap"),
        "rev_growth": num("revenueGrowth"),
        "earn_growth": num("earningsGrowth"),
        "gross_margin": num("grossMargins"),
        "fwd_pe": num("forwardPE"),
        "upside": round(target / price - 1.0, 4) if (target and price) else None,
    }


def _earnings(ticker) -> Optional[Dict]:
    iso = YFinanceUSAdapter._fetch_earnings_date(ticker)
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return None
    days = (d - date.today()).days
    if 0 <= days <= EARNINGS_WINDOW:
        return {"date": iso[:10], "days": days}
    return None


def fetch_company(symbol: str, throttle: float = 0.35) -> Optional[Dict]:
    try:
        t = yf.Ticker(symbol)
        prices = t.history(period="1y", auto_adjust=False)
        # 40-bar floor: young theme ETFs (e.g. DRAM) list mid-cycle and still
        # deserve a row; returns beyond their life simply come back None.
        if prices is None or len(prices) < 40:
            return None
        row = _series_metrics(prices)
        try:
            info = t.info or {}
        except Exception:
            info = {}
        row.update(_info_metrics(info, row["price"]))
        row["earnings"] = _earnings(t)
        return row
    except Exception as exc:
        print("skip {}: {}".format(symbol, exc))
        return None
    finally:
        time.sleep(throttle)


def _add_relative(row: Dict, bench: Dict) -> None:
    for k, rel in (("ret_1m", "rel_1m"), ("ret_3m", "rel_3m")):
        if row.get(k) is not None and bench.get(k) is not None:
            row[rel] = round(row[k] - bench[k], 4)
        else:
            row[rel] = None


def main() -> None:
    bench_row = fetch_company(BENCHMARK)
    bench = {"symbol": BENCHMARK,
             "ret_1m": bench_row.get("ret_1m") if bench_row else None,
             "ret_3m": bench_row.get("ret_3m") if bench_row else None,
             "ret_6m": bench_row.get("ret_6m") if bench_row else None}

    fetched: Dict[str, Dict] = {}
    for sym in all_company_symbols():
        row = fetch_company(sym)
        if row:
            fetched[sym] = row

    layers_out: List[Dict] = []
    for layer in LAYERS:
        companies = []
        for c in layer["companies"]:
            row = fetched.get(c["symbol"])
            if not row:
                continue
            row = dict(row)
            row["symbol"] = c["symbol"]
            row["note"] = c["note"]
            _add_relative(row, bench)
            row.update(score_company(row))
            companies.append(row)
        companies.sort(key=lambda r: -(r.get("ai_score") or 0))
        heat = layer_heat(companies)
        layers_out.append({"key": layer["key"], "name": layer["name"],
                           "role": layer["role"], "watch": layer["watch"],
                           "heat": heat, "companies": companies})

    etfs_out = []
    for e in ETFS:
        row = fetch_company(e["symbol"])
        if not row:
            continue
        keep = {k: row.get(k) for k in ("price", "chg_1d", "ret_1m", "ret_3m",
                                        "ret_6m", "spark", "name")}
        keep["symbol"] = e["symbol"]
        keep["note"] = e["note"]
        _add_relative(keep, bench)
        etfs_out.append(keep)

    catch_up: List[Dict] = []
    for layer in layers_out:
        catch_up.extend(find_catch_up(layer, layer["heat"]))
    leaders = sorted(
        (c for l in layers_out for c in l["companies"]
         if (c.get("ai_score") or 0) >= 70 and (c.get("high_52w_dist") or -1) > -0.07),
        key=lambda c: -(c["ai_score"] or 0))
    leaders = [{"symbol": c["symbol"], "name": c.get("name"),
                "layer": next(l["name"] for l in layers_out
                              if any(x["symbol"] == c["symbol"] for x in l["companies"])),
                "ai_score": c["ai_score"], "rel_3m": c.get("rel_3m"),
                "price": c.get("price"), "currency": c.get("currency", "USD")}
               for c in leaders[:8]]

    hot = [l["name"] for l in layers_out
           if l["heat"].get("score") is not None and l["heat"]["score"] >= HOT_LAYER]
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark": bench,
        "layers": layers_out,
        "etfs": etfs_out,
        "radar": {"catch_up": catch_up[:10], "leaders": leaders, "hot_layers": hot},
    }
    os.makedirs(os.path.dirname(DEFAULT_OUT), exist_ok=True)
    with open(DEFAULT_OUT, "w") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")))
    print("ai chain scan: {} companies, {} etfs, {} hot layers, {} catch-up candidates".format(
        sum(len(l["companies"]) for l in layers_out), len(etfs_out), len(hot), len(catch_up)))


if __name__ == "__main__":
    main()
