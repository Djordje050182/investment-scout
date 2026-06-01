# tests/test_yfinance_us.py
from engine.adapters.yfinance_us import (
    extract_fundamentals, has_fundamentals, extract_profile, extract_holders,
)
from engine.universe import market_of


def test_crypto_has_no_fundamentals():
    # Crypto isn't a company — we never screen it on Buffett-style metrics.
    assert has_fundamentals(market_of("BTC-USD")) is False
    assert has_fundamentals(market_of("AAPL")) is True
    assert has_fundamentals(market_of("BHP.AX")) is True


def test_extract_profile_maps_fields():
    info = {
        "longName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "country": "United States",
        "fullTimeEmployees": 166000,
        "website": "https://www.apple.com",
        "longBusinessSummary": "Apple designs and sells phones. " * 30,
        "heldPercentInstitutions": 0.658,
        "heldPercentInsiders": 0.016,
    }
    p = extract_profile(info)
    assert p["name"] == "Apple Inc."
    assert p["sector"] == "Technology"
    assert p["industry"] == "Consumer Electronics"
    assert p["country"] == "United States"
    assert p["employees"] == 166000
    assert p["website"] == "https://www.apple.com"
    assert abs(p["held_institutions"] - 0.658) < 1e-9
    assert abs(p["held_insiders"] - 0.016) < 1e-9
    # the long summary is trimmed to a sane card length
    assert 0 < len(p["description"]) <= 360


def test_extract_profile_handles_missing():
    p = extract_profile({})
    # absent keys simply don't appear; never raises
    assert isinstance(p, dict)
    assert "name" not in p


def test_extract_holders_returns_named_backers():
    rows = [
        {"Holder": "Blackrock Inc.", "pctHeld": 0.0779},
        {"Holder": "Vanguard Capital Management LLC", "pctHeld": 0.0649},
        {"Holder": "State Street Corporation", "pctHeld": 0.0410},
    ]
    holders = extract_holders(rows, limit=2)
    assert len(holders) == 2
    assert holders[0]["name"] == "Blackrock Inc."
    assert abs(holders[0]["pct"] - 0.0779) < 1e-9


def test_extract_holders_handles_empty():
    assert extract_holders([], limit=5) == []
    assert extract_holders(None, limit=5) == []


def test_extract_fundamentals_maps_keys():
    info = {
        "returnOnEquity": 0.25,
        "debtToEquity": 30.0,           # yfinance reports as percent
        "profitMargins": 0.22,
        "freeCashflow": 5e9,
        "trailingPE": 18.0,
    }
    f = extract_fundamentals(info)
    assert abs(f["roe"] - 0.25) < 1e-9
    assert abs(f["debt_to_equity"] - 0.30) < 1e-9   # converted from percent
    assert abs(f["profit_margin"] - 0.22) < 1e-9
    assert f["free_cash_flow"] == 5e9
    assert f["trailing_pe"] == 18.0


def test_extract_fundamentals_handles_missing():
    f = extract_fundamentals({})
    assert f == {}
