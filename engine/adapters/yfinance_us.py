# engine/adapters/yfinance_us.py
"""US-equity adapter backed by yfinance (free). Skips per-symbol failures."""
import time
from typing import Dict, List, Optional
import yfinance as yf
from engine.adapters.base import DataAdapter, MarketData


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
        ticker = yf.Ticker(symbol)
        prices = ticker.history(period=self.period, auto_adjust=False)
        if prices is None or len(prices) < 60:
            return None
        try:
            info = ticker.info or {}
        except Exception:
            info = {}
        fundamentals = extract_fundamentals(info)
        price = float(prices["Close"].iloc[-1])
        return MarketData(symbol=symbol, market="US", prices=prices,
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
