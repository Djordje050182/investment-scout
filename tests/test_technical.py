# tests/test_technical.py
from tests.fixtures import make_prices, cup_and_handle_closes, uptrend_closes, flat_closes
from engine.signals.technical import scan_technical


def test_cup_and_handle_detected():
    df = make_prices(cup_and_handle_closes())
    result = scan_technical(df)
    assert "cup_and_handle" in result["patterns"]
    assert result["score"] > 0.0


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
