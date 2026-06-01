# engine/adapters/yfinance_us.py
"""Multi-market adapter backed by yfinance (free). Skips per-symbol failures.

Handles US equities, ASX equities (.AX), and crypto (-USD). The market is
inferred from the symbol. Crypto has no company fundamentals, so for crypto we
skip the (slow, often-empty) .info call and screen on technicals only.
"""
import time
from typing import Dict, List, Optional
import yfinance as yf
from engine.adapters.base import DataAdapter, MarketData
from engine.universe import market_of


def has_fundamentals(market: str) -> bool:
    """Whether a market has company fundamentals worth screening (crypto does not)."""
    return market != "Crypto"


def extract_fundamentals(info: Dict) -> Dict[str, float]:
    """Map a yfinance .info dict to our normalized fundamentals dict.

    Only includes keys that are present and numeric. debtToEquity is reported
    by yfinance as a percentage (e.g. 30.0 == 0.30), so we divide by 100.
    """
    out: Dict[str, float] = {}

    def put(key: str, src: str, scale: float = 1.0):
        v = info.get(src)
        if isinstance(v, (int, float)):
            out[key] = float(v) * scale

    put("roe", "returnOnEquity")
    put("debt_to_equity", "debtToEquity", scale=0.01)
    put("profit_margin", "profitMargins")
    put("free_cash_flow", "freeCashflow")
    put("trailing_pe", "trailingPE")
    return out


class YFinanceUSAdapter(DataAdapter):
    """Fetches daily price history + fundamentals for US symbols."""

    def __init__(self, period: str = "1y", throttle_sec: float = 0.4):
        self.period = period
        self.throttle_sec = throttle_sec

    def _fetch_one(self, symbol: str) -> Optional[MarketData]:
        market = market_of(symbol)
        ticker = yf.Ticker(symbol)
        prices = ticker.history(period=self.period, auto_adjust=False)
        if prices is None or len(prices) < 60:
            return None
        fundamentals: Dict[str, float] = {}
        if has_fundamentals(market):
            try:
                info = ticker.info or {}
            except Exception:
                info = {}
            fundamentals = extract_fundamentals(info)
        price = float(prices["Close"].iloc[-1])
        return MarketData(symbol=symbol, market=market, prices=prices,
                          fundamentals=fundamentals, price=price)

    def fetch(self, symbols: List[str]) -> List[MarketData]:
        out: List[MarketData] = []
        for sym in symbols:
            try:
                md = self._fetch_one(sym)
                if md is not None:
                    out.append(md)
            except Exception as exc:  # never let one symbol kill the run
                print("skip {}: {}".format(sym, exc))
            time.sleep(self.throttle_sec)
        return out
