# engine/adapters/base.py
"""Data-source contract. Signals depend on MarketData, never on a concrete source."""
from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd


@dataclass
class MarketData:
    """Everything the signal engine needs about one symbol."""
    symbol: str
    market: str
    prices: pd.DataFrame              # OHLCV, daily, chronological
    fundamentals: Dict[str, float]    # may be partial; missing keys absent
    price: Optional[float] = None     # latest close convenience
    profile: Optional[Dict] = None    # company info (name, sector, description, ...)
    holders: Optional[List[Dict]] = None  # top institutional backers [{name, pct}]
    earnings_date: Optional[str] = None   # next earnings date, ISO (equities only)


class DataAdapter:
    """Interface every data source implements."""

    def fetch(self, symbols: List[str]) -> List[MarketData]:
        """Return MarketData for each symbol that could be fetched.

        Implementations MUST skip (not raise on) individual symbol failures.
        """
        raise NotImplementedError
