# tests/test_fundamental.py
from engine.signals.fundamental import scan_fundamental


def test_strong_company_scores_high():
    f = {"roe": 0.25, "debt_to_equity": 0.3, "profit_margin": 0.22,
         "free_cash_flow": 5e9, "trailing_pe": 18.0, "shares_change": -0.02}
    result = scan_fundamental(f)
    assert result["score"] > 0.6
    assert result["quality"] > 0.6


def test_weak_company_scores_low():
    f = {"roe": 0.02, "debt_to_equity": 3.0, "profit_margin": -0.05,
         "free_cash_flow": -1e9, "trailing_pe": 90.0, "shares_change": 0.1}
    result = scan_fundamental(f)
    assert result["score"] < 0.4


def test_missing_data_does_not_crash():
    result = scan_fundamental({})
    assert 0.0 <= result["score"] <= 1.0
    assert result["score"] == 0.0


def test_partial_data_scores_partially():
    result = scan_fundamental({"roe": 0.25})
    assert result["score"] > 0.0
