# engine/universe.py
"""Symbol lists to scan. Keep modest to respect free-API rate limits."""
from typing import List

# A starter set of liquid US large-caps across sectors. Expand or add new
# named universes (e.g. 'sp500', 'asx', 'crypto') here later.
_STARTER = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B",
    "JPM", "V", "MA", "UNH", "HD", "PG", "JNJ", "KO", "PEP", "COST",
    "WMT", "DIS", "ADBE", "CRM", "NFLX", "AMD", "INTC", "CSCO", "ORCL",
    "TXN", "QCOM", "NKE",
]

_UNIVERSES = {
    "starter": _STARTER,
}


def get_universe(name: str = "starter") -> List[str]:
    """Return the symbol list for a named universe. Raises KeyError if unknown."""
    return list(_UNIVERSES[name])
