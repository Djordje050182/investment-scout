# engine/signals/scores.py
"""Two headline company scores shown alongside (not instead of) Conviction.

- backing_score:  how strongly institutions ("smart money") back the company.
- strength_score: how solid the underlying business is (the fundamental blend).

Both are 0-100 and return None when the inputs don't exist (e.g. crypto), so the
UI can omit them rather than show a misleading zero.
"""
from typing import Dict, Optional


def _to_100(x: float) -> int:
    return int(round(max(0.0, min(1.0, x)) * 100))


def backing_score(profile: Optional[Dict]) -> Optional[int]:
    """0-100 institutional-backing score from ownership data.

    Mostly driven by the share held by institutions (broad professional
    conviction), with a small lift for insider ownership (skin in the game).
    Returns None when no ownership data is available.
    """
    if not profile:
        return None
    inst = profile.get("held_institutions")
    insiders = profile.get("held_insiders")
    if inst is None and insiders is None:
        return None
    inst = inst if isinstance(inst, (int, float)) else 0.0
    insiders = insiders if isinstance(insiders, (int, float)) else 0.0
    # ~70% institutional ownership is already very strong -> scale to 1.0 there.
    inst_part = min(1.0, inst / 0.70)
    # insider alignment caps its contribution; ~10% insider held is notable.
    insider_part = min(1.0, insiders / 0.10)
    return _to_100(0.85 * inst_part + 0.15 * insider_part)


def strength_score(fundamental: Dict, has_fundamentals: bool = True) -> Optional[int]:
    """0-100 business-strength score blending quality, moat, and value.

    Returns None when the asset has no fundamentals (crypto).
    """
    if not has_fundamentals:
        return None
    quality = float(fundamental.get("quality", 0.0))
    moat = float(fundamental.get("moat", 0.0))
    value = float(fundamental.get("value", 0.0))
    return _to_100(0.5 * quality + 0.3 * moat + 0.2 * value)
