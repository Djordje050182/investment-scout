# tests/test_universe.py
from engine.universe import get_universe, market_of


def test_default_universe_nonempty():
    syms = get_universe("starter")
    assert len(syms) >= 20
    assert "AAPL" in syms


def test_unknown_universe_raises():
    import pytest
    with pytest.raises(KeyError):
        get_universe("does_not_exist")


def test_asx_universe():
    syms = get_universe("asx")
    assert len(syms) >= 10
    assert all(s.endswith(".AX") for s in syms)


def test_crypto_universe():
    syms = get_universe("crypto")
    assert len(syms) >= 5
    assert "BTC-USD" in syms
    assert all(s.endswith("-USD") for s in syms)


def test_all_universe_combines_and_dedupes():
    syms = get_universe("all")
    assert "AAPL" in syms and "BTC-USD" in syms
    assert any(s.endswith(".AX") for s in syms)
    assert len(syms) == len(set(syms))   # no duplicates


def test_market_of_classifies_symbols():
    assert market_of("AAPL") == "US"
    assert market_of("BHP.AX") == "ASX"
    assert market_of("BTC-USD") == "Crypto"
