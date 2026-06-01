# engine/signals/fundamental.py
"""Buffett-style fundamental screen. Input: dict of metrics (may be partial)."""
from typing import Dict, Optional


def _band(value: Optional[float], good: float, bad: float) -> Optional[float]:
    """Map a value to 0-1 where `good`->1 and `bad`->0 (linear, clamped).

    Handles both directions: if good > bad, higher is better; else lower is better.
    Returns None when value is missing so callers can ignore absent metrics.
    """
    if value is None:
        return None
    if good == bad:
        return 0.5
    frac = (value - bad) / (good - bad)
    return float(max(0.0, min(1.0, frac)))


def _avg(parts):
    """Average of the non-None sub-scores; 0.0 if none present."""
    present = [p for p in parts if p is not None]
    if not present:
        return 0.0
    return float(sum(present) / len(present))


def scan_fundamental(f: Dict[str, float]) -> Dict[str, object]:
    """Return {'score', 'quality', 'value', 'moat', 'management', 'reasons'}."""
    roe = f.get("roe")
    dte = f.get("debt_to_equity")
    margin = f.get("profit_margin")
    fcf = f.get("free_cash_flow")
    pe = f.get("trailing_pe")
    shares_change = f.get("shares_change")  # negative = buybacks (good)

    fcf_score = None if fcf is None else (1.0 if fcf > 0 else 0.0)
    quality = _avg([
        _band(roe, good=0.20, bad=0.05),
        _band(dte, good=0.3, bad=2.0),
        _band(margin, good=0.20, bad=0.0),
        fcf_score,
    ])
    moat = _avg([
        _band(roe, good=0.20, bad=0.08),
        _band(margin, good=0.18, bad=0.05),
    ])
    value = _avg([
        _band(pe, good=12.0, bad=40.0),
    ])
    management = _avg([
        _band(shares_change, good=-0.03, bad=0.05),
    ])

    score = 0.4 * quality + 0.25 * moat + 0.2 * value + 0.15 * management
    score = float(max(0.0, min(1.0, score)))

    reasons = []
    if roe is not None and roe >= 0.20:
        reasons.append("ROE {:.0%}".format(roe))
    if dte is not None and dte <= 0.5:
        reasons.append("low debt/equity {:.1f}".format(dte))
    if margin is not None and margin >= 0.18:
        reasons.append("strong margin {:.0%}".format(margin))
    if pe is not None and pe <= 20:
        reasons.append("reasonable P/E {:.0f}".format(pe))
    if shares_change is not None and shares_change < 0:
        reasons.append("share buybacks")

    return {"score": score, "quality": quality, "value": value, "moat": moat,
            "management": management, "reasons": reasons}
