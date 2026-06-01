# engine/signals/explain.py
"""Turn a scored suggestion into a plain-English 'why we surfaced this' paragraph.

This is the human-facing explanation that appears under each card on the
dashboard and in the email digest. It is intentionally plain — it names the
basis for the pick (chart pattern, company quality, or both) and ties it back
to the conviction score, without giving advice.
"""
from typing import Dict


def _tier_clause(tier: str, market: str) -> str:
    """The opening clause explaining what KIND of signal this is."""
    if tier == "both":
        return ("it lines up on two fronts at once: the chart shows a constructive "
                "setup, and the underlying business screens as high quality")
    if tier == "technical":
        if market == "Crypto":
            return ("its price action triggered our technical signals — crypto has no "
                    "company fundamentals, so this is a chart-based read only")
        return "its price chart triggered our technical signals"
    if tier == "fundamental":
        return ("the underlying business screens as high quality and reasonably "
                "valued, even though the chart isn't flashing a setup yet")
    return "it cleared our screen"


def explain_suggestion(s: Dict) -> str:
    """Return a short paragraph explaining why this suggestion surfaced."""
    symbol = s.get("symbol", "This name")
    tier = s.get("tier", "none")
    market = s.get("market", "US")
    conviction = s.get("conviction", 0)
    reasons = [r for r in s.get("reasons", []) if r]

    opening = "{} surfaced because {}.".format(symbol, _tier_clause(tier, market))

    if reasons:
        if len(reasons) == 1:
            detail = " The specific trigger was {}.".format(reasons[0].lower())
        else:
            head = ", ".join(r.lower() for r in reasons[:-1])
            detail = " The specific triggers were {}, and {}.".format(
                head, reasons[-1].lower())
    else:
        detail = ""

    close = (" That gives it a conviction score of {}/100 — a research lead to "
             "investigate, not a recommendation to buy.").format(conviction)

    return opening + detail + close
