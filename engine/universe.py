# engine/universe.py
"""Symbol lists to scan, and market classification.

Symbols use yfinance conventions: plain tickers for US (AAPL), a ".AX" suffix
for the ASX (BHP.AX), and a "-USD" suffix for crypto (BTC-USD). Keep lists
modest to respect free-API rate limits.
"""
from typing import List

# Liquid US large-caps across sectors.
_US = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B",
    "JPM", "V", "MA", "UNH", "HD", "PG", "JNJ", "KO", "PEP", "COST",
    "WMT", "DIS", "ADBE", "CRM", "NFLX", "AMD", "INTC", "CSCO", "ORCL",
    "TXN", "QCOM", "NKE",
]

# Large-cap ASX names (.AX suffix).
_ASX = [
    "BHP.AX", "CBA.AX", "CSL.AX", "NAB.AX", "WBC.AX", "ANZ.AX", "WES.AX",
    "MQG.AX", "GMG.AX", "WOW.AX", "TLS.AX", "RIO.AX", "FMG.AX", "WDS.AX",
    "TCL.AX",
]

# Major cryptocurrencies (priced in USD). No fundamentals — technical only.
_CRYPTO = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD",
    "DOGE-USD", "AVAX-USD",
]


def _dedupe(seq: List[str]) -> List[str]:
    """Order-preserving de-duplication."""
    seen = set()
    out = []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


_UNIVERSES = {
    "starter": _US,            # back-compat: the original US-only universe
    "us": _US,
    "asx": _ASX,
    "crypto": _CRYPTO,
    "all": _dedupe(_US + _ASX + _CRYPTO),
}


def get_universe(name: str = "starter") -> List[str]:
    """Return the symbol list for a named universe. Raises KeyError if unknown."""
    return list(_UNIVERSES[name])


def market_of(symbol: str) -> str:
    """Classify a symbol into a market label from its suffix."""
    if symbol.endswith("-USD"):
        return "Crypto"
    if symbol.endswith(".AX"):
        return "ASX"
    return "US"
