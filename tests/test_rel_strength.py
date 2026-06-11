# tests/test_rel_strength.py
from tests.fixtures import make_prices, uptrend_closes
from engine.run_scan import bench_returns, _add_relative_strength, _earnings_block
from engine.adapters.base import MarketData
from datetime import date, timedelta


def test_bench_returns_shape():
    b = bench_returns({"SPY": make_prices(uptrend_closes())})
    assert "SPY" in b
    assert b["SPY"]["ret_1m"] > 0
    assert b["SPY"]["ret_3m"] > 0


def test_relative_strength_added_per_market():
    bench = {"SPY": {"ret_1m": 0.02, "ret_3m": 0.05},
             "^AXJO": {"ret_1m": 0.01, "ret_3m": 0.02}}
    snap = {"ret_1m": 0.06, "ret_3m": 0.10}
    _add_relative_strength(snap, "US", bench)
    assert abs(snap["rel_1m"] - 0.04) < 1e-9
    assert abs(snap["rel_3m"] - 0.05) < 1e-9
    snap2 = {"ret_1m": 0.06, "ret_3m": 0.10}
    _add_relative_strength(snap2, "ASX", bench)
    assert abs(snap2["rel_1m"] - 0.05) < 1e-9


def test_relative_strength_tolerates_missing():
    snap = {"ret_1m": None, "ret_3m": 0.10}
    _add_relative_strength(snap, "US", None)
    assert "rel_1m" not in snap and "rel_3m" not in snap


def _md(earnings_date):
    return MarketData(symbol="X", market="US", prices=None, fundamentals={},
                      earnings_date=earnings_date)


def test_earnings_block_inside_window():
    soon = (date.today() + timedelta(days=5)).isoformat()
    block = _earnings_block(_md(soon))
    assert block == {"date": soon, "days": 5}


def test_earnings_block_outside_window_or_past():
    far = (date.today() + timedelta(days=40)).isoformat()
    past = (date.today() - timedelta(days=3)).isoformat()
    assert _earnings_block(_md(far)) is None
    assert _earnings_block(_md(past)) is None
    assert _earnings_block(_md(None)) is None
    assert _earnings_block(_md("not-a-date")) is None
