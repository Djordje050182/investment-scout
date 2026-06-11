# tests/test_trade_plan.py
from tests.fixtures import make_prices, cup_and_handle_closes, uptrend_closes
from engine.signals.trade_plan import build_trade_plan


def test_plan_levels_are_coherent():
    plan = build_trade_plan(make_prices(uptrend_closes()))
    assert plan is not None
    assert plan["stop"] < plan["entry"] < plan["target1"] <= plan["target2"]
    assert plan["rr"] > 0
    assert 0 < plan["atr_pct"] < 0.5


def test_cup_uses_measured_move():
    plan = build_trade_plan(make_prices(cup_and_handle_closes()),
                            patterns=["cup_and_handle"])
    assert plan is not None
    assert plan["method"] == "cup measured move"
    # the cup is ~22 points deep; target2 must reflect a real projection
    assert plan["target2"] - plan["entry"] >= plan["target1"] - plan["entry"]


def test_too_little_data_returns_none():
    assert build_trade_plan(make_prices([100.0] * 10)) is None


def test_stop_respects_noise_band():
    # stop must sit at least ~1 ATR below entry, never inside daily noise
    plan = build_trade_plan(make_prices(uptrend_closes()))
    atr_abs = plan["atr_pct"] * plan["entry"]
    assert plan["entry"] - plan["stop"] >= 0.95 * atr_abs
