# tests/test_technical.py
from tests.fixtures import (
    make_prices, cup_and_handle_closes, uptrend_closes, flat_closes,
    v_bottom_closes, cup_no_handle_closes, cup_far_from_rim_closes,
    downtrend_closes,
)
from engine.signals.technical import scan_technical, _detect_cup_and_handle
import pandas as pd


def test_cup_and_handle_detected():
    df = make_prices(cup_and_handle_closes())
    result = scan_technical(df)
    assert "cup_and_handle" in result["patterns"]
    assert result["score"] > 0.0


def _cup(closes):
    return _detect_cup_and_handle(pd.Series(closes, dtype="float64"))


def test_cup_rejects_v_bottom():
    # A sharp V (no time spent basing) is not a cup-and-handle.
    assert _cup(v_bottom_closes()) == 0.0


def test_cup_rejects_no_handle():
    # A cup that recovers and flatlines at the rim has no handle pullback.
    assert _cup(cup_no_handle_closes()) == 0.0


def test_cup_rejects_far_from_rim():
    # Price well below the rim is not breakout-ready; proximity is now a gate.
    assert _cup(cup_far_from_rim_closes()) == 0.0


def test_cup_rejects_downtrend():
    assert _cup(downtrend_closes()) == 0.0


def test_cup_rejects_flat():
    assert _cup(flat_closes()) == 0.0


def test_genuine_cup_scores_strongly():
    # The real rounded cup should score clearly, not marginally.
    assert _cup(cup_and_handle_closes()) >= 0.5


def test_uptrend_detects_trend():
    df = make_prices(uptrend_closes())
    result = scan_technical(df)
    assert "uptrend" in result["patterns"]


def test_flat_series_no_signal():
    df = make_prices(flat_closes())
    result = scan_technical(df)
    assert result["score"] == 0.0
    assert result["patterns"] == []


def test_breakout_on_volume():
    # long base at 100, then a jump to 110 on 3x volume
    closes = [100.0] * 60 + [110.0]
    volumes = [1_000_000.0] * 60 + [3_000_000.0]
    df = make_prices(closes, volumes)
    result = scan_technical(df)
    assert "breakout" in result["patterns"]


def test_score_capped_at_one():
    df = make_prices(cup_and_handle_closes())
    result = scan_technical(df)
    assert 0.0 <= result["score"] <= 1.0
