# tests/test_scores.py
from engine.signals.scores import backing_score, strength_score


def test_backing_score_high_for_well_held():
    # heavily institution-owned with some insider alignment -> high backing
    p = {"held_institutions": 0.80, "held_insiders": 0.05}
    assert backing_score(p) >= 75


def test_backing_score_low_for_barely_held():
    p = {"held_institutions": 0.05, "held_insiders": 0.0}
    assert backing_score(p) <= 30


def test_backing_score_none_when_no_data():
    # crypto / missing ownership data -> no score (None), not a fake zero
    assert backing_score({}) is None
    assert backing_score(None) is None


def test_strength_score_high_for_quality_business():
    fund = {"score": 0.8, "quality": 0.9, "moat": 0.85, "value": 0.6}
    assert strength_score(fund) >= 70


def test_strength_score_low_for_weak_business():
    fund = {"score": 0.1, "quality": 0.1, "moat": 0.1, "value": 0.1}
    assert strength_score(fund) <= 25


def test_strength_score_none_when_no_fundamentals():
    # crypto has no fundamentals -> no strength score
    assert strength_score({"score": 0.0, "quality": 0.0, "value": 0.0, "moat": 0.0},
                          has_fundamentals=False) is None


def test_scores_are_ints_in_range():
    b = backing_score({"held_institutions": 0.5, "held_insiders": 0.02})
    s = strength_score({"score": 0.5, "quality": 0.5, "moat": 0.5, "value": 0.5})
    assert isinstance(b, int) and 0 <= b <= 100
    assert isinstance(s, int) and 0 <= s <= 100
