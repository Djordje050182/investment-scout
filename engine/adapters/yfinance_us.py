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


_DESC_MAX = 320   # trim the business summary to a card-friendly length


def _trim_description(text: str) -> str:
    """Trim a long business summary to ~one tidy paragraph, ending on a sentence."""
    text = (text or "").strip()
    if len(text) <= _DESC_MAX:
        return text
    cut = text[:_DESC_MAX]
    # prefer to end at the last sentence boundary inside the window
    dot = cut.rfind(". ")
    if dot >= 120:
        return cut[:dot + 1]
    return cut.rstrip() + "…"


def extract_profile(info: Dict) -> Dict:
    """Map a yfinance .info dict to our normalized company profile.

    Only includes keys that are present; never raises on missing data.
    """
    out: Dict = {}

    def put_str(key: str, src: str):
        v = info.get(src)
        if isinstance(v, str) and v.strip():
            out[key] = v.strip()

    def put_num(key: str, src: str):
        v = info.get(src)
        if isinstance(v, (int, float)):
            out[key] = v

    put_str("name", "longName")
    put_str("sector", "sector")
    put_str("industry", "industry")
    put_str("country", "country")
    put_str("website", "website")
    put_num("employees", "fullTimeEmployees")
    put_num("held_institutions", "heldPercentInstitutions")
    put_num("held_insiders", "heldPercentInsiders")

    summary = info.get("longBusinessSummary")
    if isinstance(summary, str) and summary.strip():
        out["description"] = _trim_description(summary)
    return out


def extract_holders(rows, limit: int = 5):
    """Normalize institutional-holder rows to [{name, pct}], top `limit` by holding.

    Accepts a list of dict-like rows (Holder, pctHeld). Tolerates None/empty.
    """
    if not rows:
        return []
    out = []
    for r in rows:
        name = r.get("Holder")
        pct = r.get("pctHeld")
        if isinstance(name, str) and isinstance(pct, (int, float)):
            out.append({"name": name.strip(), "pct": float(pct)})
    out.sort(key=lambda h: h["pct"], reverse=True)
    return out[:limit]


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
        profile: Dict = {}
        holders: List[Dict] = []
        earnings_date: Optional[str] = None
        if has_fundamentals(market):
            try:
                info = ticker.info or {}
            except Exception:
                info = {}
            fundamentals = extract_fundamentals(info)
            profile = extract_profile(info)
            holders = self._fetch_holders(ticker)
            earnings_date = self._fetch_earnings_date(ticker)
        price = float(prices["Close"].iloc[-1])
        return MarketData(symbol=symbol, market=market, prices=prices,
                          fundamentals=fundamentals, price=price,
                          profile=profile, holders=holders,
                          earnings_date=earnings_date)

    @staticmethod
    def _fetch_earnings_date(ticker) -> Optional[str]:
        """Next scheduled earnings date as ISO YYYY-MM-DD; tolerate any failure."""
        try:
            cal = ticker.calendar
            dates = None
            if isinstance(cal, dict):
                dates = cal.get("Earnings Date")
            elif cal is not None and hasattr(cal, "loc"):
                # older yfinance returned a DataFrame with an 'Earnings Date' row
                try:
                    dates = list(cal.loc["Earnings Date"])
                except Exception:
                    dates = None
            if not dates:
                return None
            first = sorted(dates)[0]
            return first.strftime("%Y-%m-%d") if hasattr(first, "strftime") else str(first)[:10]
        except Exception:
            return None

    @staticmethod
    def _fetch_holders(ticker) -> List[Dict]:
        """Pull top institutional holders as [{name, pct}]; tolerate any failure."""
        try:
            df = ticker.institutional_holders
            if df is None or len(df) == 0:
                return []
            return extract_holders(df.to_dict("records"), limit=5)
        except Exception:
            return []

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

    def fetch_history(self, symbols: List[str]):
        """Price history only (no .info), for benchmarks. {symbol: DataFrame}."""
        out = {}
        for sym in symbols:
            try:
                prices = yf.Ticker(sym).history(period=self.period, auto_adjust=False)
                if prices is not None and len(prices) >= 30:
                    out[sym] = prices
            except Exception as exc:
                print("skip benchmark {}: {}".format(sym, exc))
            time.sleep(self.throttle_sec)
        return out
