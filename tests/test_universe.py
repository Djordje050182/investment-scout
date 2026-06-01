# tests/test_universe.py
from engine.universe import get_universe


def test_default_universe_nonempty():
    syms = get_universe("starter")
    assert len(syms) >= 20
    assert "AAPL" in syms


def test_unknown_universe_raises():
    import pytest
    with pytest.raises(KeyError):
        get_universe("does_not_exist")
