# engine/signals/conviction.py
"""Combine technical + fundamental results into a ranked, explainable suggestion."""
from typing import Dict, List

THRESHOLD = 65          # minimum conviction (0-100) to become a suggestion
_ALIGN_MIN = 0.45       # each leg must clear this for the alignment bonus
_ALIGN_BONUS = 15       # max points added when both legs are strong
_ALIGN_FULL = 0.75      # min-leg level at which the full bonus is earned

_PATTERN_LABELS = {
    "cup_and_handle": "Cup-and-handle forming",
    "breakout": "Breakout above resistance on volume",
    "uptrend": "Uptrend (above rising 50/200-day MAs)",
    "golden_cross": "Fresh golden cross (50-day over 200-day)",
    "pullback_to_trend": "Pullback to the 50-day in an uptrend",
    "bull_flag": "Bull flag after a sharp advance",
    "double_bottom": "Double bottom recovering",
    "bollinger_squeeze": "Volatility squeeze (Bollinger bands coiled)",
    "obv_accumulation": "Volume accumulation (OBV rising ahead of price)",
    "high_52w_momentum": "Holding near 52-week highs",
    "macd_bull_cross": "Fresh MACD bullish cross",
    "oversold_reversal": "Oversold bounce in a long-term uptrend",
}

def pattern_label(name: str) -> str:
    """Human-readable label for a detector name."""
    return _PATTERN_LABELS.get(name, name.replace("_", " "))


def _tier(tech_score: float, fund_score: float) -> str:
    tech_on = tech_score >= _ALIGN_MIN
    fund_on = fund_score >= _ALIGN_MIN
    if tech_on and fund_on:
        return "both"
    if tech_on:
        return "technical"
    if fund_on:
        return "fundamental"
    return "none"


def score_conviction(technical: Dict, fundamental: Dict) -> Dict[str, object]:
    """Return {'conviction' 0-100, 'tier', 'reasons', 'technical', 'fundamental'}."""
    t = float(technical.get("score", 0.0))
    f = float(fundamental.get("score", 0.0))
    tier = _tier(t, f)

    # A strong single leg should clear the bar; aligned both-leg signals
    # still rank highest. Use max-with-blend so one strong leg isn't diluted
    # to ~half by a zero other leg.
    blend = 0.5 * t + 0.5 * f
    strongest = max(t, f)
    base = 100.0 * max(blend, 0.80 * strongest)   # a strong single leg reaches ~80
    # Alignment bonus scales with the WEAKER leg: a 0.46/0.9 pair is barely
    # aligned and earns ~nothing; 0.75+/0.75+ earns the full bonus.
    bonus = 0.0
    if tier == "both":
        frac = (min(t, f) - _ALIGN_MIN) / (_ALIGN_FULL - _ALIGN_MIN)
        bonus = _ALIGN_BONUS * max(0.0, min(1.0, frac))
    conviction = int(round(max(0.0, min(100.0, base + bonus))))

    reasons: List[str] = []
    for p in technical.get("patterns", []):
        reasons.append(_PATTERN_LABELS.get(p, p))
    reasons.extend(fundamental.get("reasons", []))

    return {
        "conviction": conviction,
        "tier": tier,
        "reasons": reasons,
        "technical": technical,
        "fundamental": fundamental,
    }


def passes(result: Dict) -> bool:
    """True if a scored result clears the suggestion threshold and is not 'none' tier."""
    return result["conviction"] >= THRESHOLD and result["tier"] != "none"
