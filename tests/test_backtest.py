# tests/test_backtest.py
from tests.fixtures import make_prices, uptrend_closes
from engine.backtest import walk_symbol, forward_returns, aggregate


def test_forward_returns_from_window_end():
    prices = make_prices([100.0] * 100 + [110.0] * 100)
    close = prices["Close"].astype("float64")
    fwd = forward_returns(close, 100)   # last in-window bar = index 99 (100.0)
    assert abs(fwd["r5"] - 0.10) < 1e-9
    assert abs(fwd["r21"] - 0.10) < 1e-9


def test_walk_symbol_emits_rows_without_lookahead():
    closes = uptrend_closes(days=400)
    rows = walk_symbol(make_prices(closes), window=260, step=5)
    assert len(rows) > 10
    for r in rows:
        assert "returns" in r and "patterns" in r
        assert all(k in ("r5", "r21", "r63") for k in r["returns"])


def test_aggregate_baseline_and_patterns():
    rows = [
        {"patterns": ["breakout"], "returns": {"r21": 0.05}, "score": 0.5},
        {"patterns": [], "returns": {"r21": -0.01}, "score": 0.0},
        {"patterns": ["breakout"], "returns": {"r21": 0.03}, "score": 0.6},
    ]
    agg = aggregate(rows)
    assert agg["baseline"]["r21"]["n"] == 3
    assert agg["by_pattern"]["breakout"]["r21"]["n"] == 2
    assert agg["by_pattern"]["breakout"]["r21"]["win_rate"] == 1.0
