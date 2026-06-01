# tests/test_explain.py
from engine.signals.explain import explain_suggestion


def _sugg(**kw):
    base = {
        "symbol": "AAPL", "market": "US", "price": 195.0,
        "conviction": 87, "tier": "both",
        "reasons": ["ROE 25%", "Cup-and-handle forming"],
        "technical": {"score": 0.82, "patterns": ["cup_and_handle", "breakout"]},
        "fundamental": {"score": 0.79, "quality": 0.9, "value": 0.6, "moat": 0.85},
    }
    base.update(kw)
    return base


def test_explanation_mentions_symbol_and_conviction():
    text = explain_suggestion(_sugg())
    assert "AAPL" in text
    assert "87" in text


def test_both_tier_explains_alignment():
    text = explain_suggestion(_sugg(tier="both")).lower()
    # the headline value prop: a good chart entry AND a high-quality business
    assert "chart" in text and ("quality" in text or "business" in text)


def test_technical_only_explains_chart_basis():
    text = explain_suggestion(_sugg(
        tier="technical",
        reasons=["Cup-and-handle forming"],
        fundamental={"score": 0.1, "quality": 0.1, "value": 0.1, "moat": 0.1},
    )).lower()
    assert "chart" in text or "price" in text or "technical" in text


def test_crypto_explanation_has_no_fundamental_claim():
    text = explain_suggestion(_sugg(
        symbol="BTC-USD", market="Crypto", tier="technical",
        reasons=["Breakout above resistance on volume"],
        fundamental={"score": 0.0, "quality": 0.0, "value": 0.0, "moat": 0.0},
    )).lower()
    # crypto has no company fundamentals — don't claim ROE/moat etc.
    assert "moat" not in text
    assert "roe" not in text


def test_explanation_is_nonempty_prose():
    text = explain_suggestion(_sugg())
    assert isinstance(text, str)
    assert len(text) > 40
    assert text.strip().endswith(".")
