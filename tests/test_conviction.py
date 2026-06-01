# tests/test_conviction.py
from engine.signals.conviction import score_conviction, THRESHOLD


def _tech(score, patterns=None, detail=None):
    return {"score": score, "patterns": patterns or [], "detail": detail or {}}


def _fund(score, reasons=None):
    return {"score": score, "quality": score, "value": score, "moat": score,
            "management": score, "reasons": reasons or []}


def test_alignment_gets_both_tier_and_bonus():
    aligned = score_conviction(_tech(0.7, ["cup_and_handle"]), _fund(0.7))
    tech_only = score_conviction(_tech(0.7, ["cup_and_handle"]), _fund(0.0))
    assert aligned["tier"] == "both"
    # alignment should score strictly higher than either leg alone at same tech level
    assert aligned["conviction"] > tech_only["conviction"]


def test_tier_technical_when_only_technical():
    r = score_conviction(_tech(0.8, ["breakout"]), _fund(0.1))
    assert r["tier"] == "technical"


def test_tier_fundamental_when_only_fundamental():
    r = score_conviction(_tech(0.1), _fund(0.8))
    assert r["tier"] == "fundamental"


def test_conviction_is_0_to_100():
    r = score_conviction(_tech(1.0, ["cup_and_handle", "breakout"]), _fund(1.0))
    assert 0 <= r["conviction"] <= 100


def test_reasons_merged():
    r = score_conviction(_tech(0.7, ["cup_and_handle"]),
                         _fund(0.7, ["ROE 25%"]))
    assert any("ROE" in x for x in r["reasons"])
    assert any("cup" in x.lower() for x in r["reasons"])


def test_threshold_is_reasonable():
    assert 0 < THRESHOLD < 100
