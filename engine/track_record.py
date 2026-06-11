# engine/track_record.py
"""Score past leads against what actually happened.

Reads the dated snapshots in docs/data/history/, extracts lead EPISODES
(a symbol newly appearing in the suggestion list starts an episode; daily
re-appearances of the same lead don't double-count), fetches price history
since each episode's signal date, and computes:

- forward returns at +5, +21, +63 trading days (where enough time has passed)
- trade-plan resolution: did price touch target1 before the stop?
  (same-day touch of both counts as a stop — conservative)

Aggregates hit rates by pattern, tier, and market, and writes
docs/data/track_record.json for the dashboard's performance panel.

Run after the daily scan:  python -m engine.track_record
"""
import glob
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

HISTORY_DIR = "docs/data/history"
DEFAULT_OUT = "docs/data/track_record.json"
HORIZONS = (5, 21, 63)          # trading days
MAX_EPISODES_LISTED = 60        # newest episodes shipped to the UI


# --------------------------------------------------------------------------
# Episode extraction (pure)
# --------------------------------------------------------------------------

def _patterns_of(suggestion: Dict) -> List[str]:
    tech = suggestion.get("technical") or {}
    pats = tech.get("patterns")
    return list(pats) if isinstance(pats, list) else []


def extract_episodes(snapshots: List[Dict]) -> List[Dict]:
    """One episode per (symbol, first day it newly appears as a suggestion).

    `snapshots` must be sorted by scanned_at ascending. A symbol re-appearing
    on consecutive scan days extends the same episode; appearing again after
    dropping off starts a new one.
    """
    episodes: List[Dict] = []
    prev_symbols: set = set()
    for snap in snapshots:
        suggestions = snap.get("suggestions") or []
        today = {s["symbol"] for s in suggestions}
        for s in suggestions:
            if s["symbol"] in prev_symbols:
                continue
            episodes.append({
                "symbol": s["symbol"],
                "market": s.get("market", "US"),
                "date": (snap.get("scanned_at") or "")[:10],
                "price": s.get("price"),
                "conviction": s.get("conviction"),
                "tier": s.get("tier"),
                "patterns": _patterns_of(s),
                "trade_plan": s.get("trade_plan"),
            })
        prev_symbols = today
    return episodes


# --------------------------------------------------------------------------
# Outcome evaluation (pure given a price frame)
# --------------------------------------------------------------------------

def evaluate_episode(ep: Dict, prices: Optional[pd.DataFrame]) -> Dict:
    """Attach forward returns and trade-plan resolution to an episode."""
    out = dict(ep)
    out["returns"] = {}
    out["plan_outcome"] = None
    entry = ep.get("price")
    if prices is None or len(prices) == 0 or not entry:
        out["status"] = "unpriced"
        return out

    after = prices[prices.index.strftime("%Y-%m-%d") > ep["date"]]
    if len(after) == 0:
        out["status"] = "open"
        return out

    close = after["Close"].astype("float64")
    for h in HORIZONS:
        if len(close) >= h:
            out["returns"]["r{}".format(h)] = round(float(close.iloc[h - 1]) / entry - 1.0, 4)

    plan = ep.get("trade_plan") or {}
    stop, target = plan.get("stop"), plan.get("target1")
    if stop and target:
        high = after["High"].astype("float64") if "High" in after else close
        low = after["Low"].astype("float64") if "Low" in after else close
        for i in range(len(after)):
            hit_stop = float(low.iloc[i]) <= stop
            hit_target = float(high.iloc[i]) >= target
            if hit_stop:                      # conservative on same-day double touch
                out["plan_outcome"] = "stopped"
                break
            if hit_target:
                out["plan_outcome"] = "target1"
                break

    resolved = ("r63" in out["returns"]) or out["plan_outcome"] is not None
    out["status"] = "closed" if resolved else "open"
    return out


def _agg(rows: List[Dict]) -> Dict:
    """Aggregate a set of evaluated episodes: counts, win rate, avg returns."""
    n = len(rows)
    r5 = [r["returns"].get("r5") for r in rows]
    r5 = [x for x in r5 if x is not None]
    r21 = [r["returns"].get("r21") for r in rows]
    r21 = [x for x in r21 if x is not None]
    r63 = [r["returns"].get("r63") for r in rows]
    r63 = [x for x in r63 if x is not None]
    plans = [r["plan_outcome"] for r in rows if r["plan_outcome"] is not None]
    out: Dict = {"episodes": n}
    if r5:
        out["n_1w"] = len(r5)
        out["win_rate_1w"] = round(sum(1 for x in r5 if x > 0) / len(r5), 3)
        out["avg_1w"] = round(sum(r5) / len(r5), 4)
    if r21:
        out["n_1m"] = len(r21)
        out["win_rate_1m"] = round(sum(1 for x in r21 if x > 0) / len(r21), 3)
        out["avg_1m"] = round(sum(r21) / len(r21), 4)
    if r63:
        out["n_3m"] = len(r63)
        out["win_rate_3m"] = round(sum(1 for x in r63 if x > 0) / len(r63), 3)
        out["avg_3m"] = round(sum(r63) / len(r63), 4)
    if plans:
        out["plans_resolved"] = len(plans)
        out["target_rate"] = round(sum(1 for p in plans if p == "target1") / len(plans), 3)
    return out


def aggregate(evaluated: List[Dict]) -> Dict:
    """Aggregates overall and by pattern / tier / market."""
    by_pattern: Dict[str, List[Dict]] = {}
    by_tier: Dict[str, List[Dict]] = {}
    by_market: Dict[str, List[Dict]] = {}
    for ep in evaluated:
        for p in ep.get("patterns") or []:
            by_pattern.setdefault(p, []).append(ep)
        if ep.get("tier"):
            by_tier.setdefault(ep["tier"], []).append(ep)
        if ep.get("market"):
            by_market.setdefault(ep["market"], []).append(ep)
    return {
        "overall": _agg(evaluated),
        "by_pattern": {k: _agg(v) for k, v in sorted(by_pattern.items())},
        "by_tier": {k: _agg(v) for k, v in sorted(by_tier.items())},
        "by_market": {k: _agg(v) for k, v in sorted(by_market.items())},
    }


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------

def load_snapshots(history_dir: str = HISTORY_DIR) -> List[Dict]:
    snaps = []
    for path in sorted(glob.glob(os.path.join(history_dir, "*.json"))):
        try:
            with open(path) as fh:
                snaps.append(json.load(fh))
        except (json.JSONDecodeError, OSError) as exc:
            print("skip snapshot {}: {}".format(path, exc))
    snaps.sort(key=lambda s: s.get("scanned_at") or "")
    return snaps


def fetch_prices(symbols: List[str], start: str) -> Dict[str, pd.DataFrame]:
    """Batched daily history from the earliest signal date to now."""
    if not symbols:
        return {}
    data = yf.download(symbols, start=start, interval="1d", group_by="ticker",
                       threads=True, progress=False, auto_adjust=False)
    out: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            df = data[sym] if len(symbols) > 1 else data
            df = df.dropna(subset=["Close"])
            if len(df):
                out[sym] = df
        except (KeyError, TypeError):
            continue
    return out


def main() -> None:
    snapshots = load_snapshots()
    episodes = extract_episodes(snapshots)
    if not episodes:
        print("no episodes in history; nothing to do")
        return
    symbols = sorted({e["symbol"] for e in episodes})
    earliest = min(e["date"] for e in episodes if e["date"])
    prices = fetch_prices(symbols, start=earliest)
    evaluated = [evaluate_episode(e, prices.get(e["symbol"])) for e in episodes]
    evaluated = [e for e in evaluated if e["status"] != "unpriced"]

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "episodes_total": len(evaluated),
        "aggregates": aggregate(evaluated),
        "episodes": sorted(evaluated, key=lambda e: e["date"], reverse=True)[:MAX_EPISODES_LISTED],
    }
    os.makedirs(os.path.dirname(DEFAULT_OUT), exist_ok=True)
    with open(DEFAULT_OUT, "w") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")))
    closed = sum(1 for e in evaluated if e["status"] == "closed")
    print("track record: {} episodes ({} closed) -> {}".format(
        len(evaluated), closed, DEFAULT_OUT))


if __name__ == "__main__":
    main()
