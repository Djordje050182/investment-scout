# engine/refresh_quotes.py
"""Lightweight intraday quote refresh.

Fetches the latest price + day change for the whole scan universe and the
benchmarks in one batched yfinance call, then writes docs/data/quotes.json.
Runs on a 30-minute GitHub Action during US market hours so the dashboard
shows near-live equity prices between daily scans. (Crypto streams live in
the browser via Binance WebSocket; this file is its fallback.)
"""
import json
import math
import os
from datetime import datetime, timezone
from typing import Dict

import yfinance as yf

from engine.signals.regime import BENCHMARKS
from engine.universe import get_universe

DEFAULT_OUT = "docs/data/quotes.json"


def build_quotes(symbols) -> Dict[str, Dict]:
    """Batched download: last close vs previous close for each symbol."""
    data = yf.download(list(symbols), period="5d", interval="1d",
                       group_by="ticker", threads=True, progress=False,
                       auto_adjust=False)
    quotes: Dict[str, Dict] = {}
    for sym in symbols:
        try:
            df = data[sym] if len(symbols) > 1 else data
            close = df["Close"].dropna()
            if len(close) == 0:
                continue
            price = float(close.iloc[-1])
            chg = None
            if len(close) >= 2 and float(close.iloc[-2]) != 0:
                chg = price / float(close.iloc[-2]) - 1.0
            if math.isnan(price):
                continue
            quotes[sym] = {
                "price": round(price, 6 if price < 1 else 2),
                "chg_1d": None if chg is None or math.isnan(chg) else round(chg, 4),
            }
        except Exception as exc:   # one bad symbol never kills the refresh
            print("skip {}: {}".format(sym, exc))
    return quotes


def main() -> None:
    universe_name = os.environ.get("SCOUT_UNIVERSE", "all")
    symbols = list(dict.fromkeys(get_universe(universe_name) + list(BENCHMARKS.keys())))
    quotes = build_quotes(symbols)
    if not quotes:
        print("no quotes fetched; leaving existing quotes.json untouched")
        return
    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes": quotes,
    }
    os.makedirs(os.path.dirname(DEFAULT_OUT), exist_ok=True)
    with open(DEFAULT_OUT, "w") as fh:
        fh.write(json.dumps(payload, indent=2))
    print("quotes refreshed: {} symbols".format(len(quotes)))


if __name__ == "__main__":
    main()
