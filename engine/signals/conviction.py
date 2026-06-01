# engine/signals/conviction.py
"""Combine technical + fundamental results into a ranked, explainable suggestion."""
from typing import Dict, List

THRESHOLD = 55          # minimum conviction (0-100) to become a suggestion
_ALIGN_MIN = 0.4        # each leg must clear this for the alignment bonus
_ALIGN_BONUS = 15       # points added when both legs are strong

_PATTERN_LABELS = {
    "cup_and_handle": "Cup-and-handle forming",
    "breakout": "Breakout above resistance on volume",
    "uptrend": "Uptrend (above rising 50/200-day MAs)",
}


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
    base = 100.0 * max(blend, 0.85 * strongest)   # a strong single leg reaches ~85
    bonus = _ALIGN_BONUS if tier == "both" else 0
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
