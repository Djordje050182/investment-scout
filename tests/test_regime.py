# tests/test_regime.py
from tests.fixtures import make_prices, uptrend_closes, downtrend_closes, flat_closes
from engine.signals.regime import benchmark_read, breadth, regime_label, build_market_block


def test_benchmark_read_uptrend():
    read = benchmark_read(make_prices(uptrend_closes()))
    assert read["trend"] == "uptrend"
    assert read["price"] > 0
    assert read["chg_1d"] is not None


def test_benchmark_read_downtrend():
    read = benchmark_read(make_prices(downtrend_closes()))
    assert read["trend"] in ("downtrend", "mixed")


def test_benchmark_read_too_short_is_none():
    assert benchmark_read(make_prices([100.0] * 10)) is None


def test_breadth_counts_uptrends():
    frames = [make_prices(uptrend_closes()), make_prices(downtrend_closes())]
    b = breadth(frames)
    assert b["symbols"] == 2
    assert 0.0 <= b["pct_above_50dma"] <= 1.0


def test_regime_label_risk_on():
    benchmarks = {"SPY": {"trend": "uptrend"}, "QQQ": {"trend": "uptrend"}}
    assert regime_label(benchmarks, {"pct_above_50dma": 0.8}) == "risk_on"


def test_regime_label_risk_off():
    benchmarks = {"SPY": {"trend": "downtrend"}, "QQQ": {"trend": "downtrend"}}
    assert regime_label(benchmarks, {"pct_above_50dma": 0.1}) == "risk_off"


def test_build_market_block_shape():
    block = build_market_block(
        {"SPY": make_prices(uptrend_closes())},
        [make_prices(uptrend_closes()), make_prices(flat_closes())],
    )
    assert block["regime"] in ("risk_on", "neutral", "risk_off")
    assert "SPY" in block["benchmarks"]
    assert block["benchmarks"]["SPY"]["label"] == "S&P 500"
    assert block["breadth"]["symbols"] >= 1
