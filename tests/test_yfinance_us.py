# tests/test_yfinance_us.py
from engine.adapters.yfinance_us import extract_fundamentals, has_fundamentals
from engine.universe import market_of


def test_crypto_has_no_fundamentals():
    # Crypto isn't a company — we never screen it on Buffett-style metrics.
    assert has_fundamentals(market_of("BTC-USD")) is False
    assert has_fundamentals(market_of("AAPL")) is True
    assert has_fundamentals(market_of("BHP.AX")) is True


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
