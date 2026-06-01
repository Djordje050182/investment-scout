# engine/run_scan.py
"""Daily scan orchestrator: fetch -> score -> write signals.json -> email."""
import json
import os
from datetime import datetime, timezone
from typing import Dict, List
from engine.adapters.base import DataAdapter
from engine.adapters.yfinance_us import YFinanceUSAdapter
from engine.signals.technical import scan_technical
from engine.signals.fundamental import scan_fundamental
from engine.signals.conviction import score_conviction, passes
from engine.signals.explain import explain_suggestion
from engine.universe import get_universe
from engine.notify.email import build_digest, send_email

DEFAULT_OUT = "docs/data/signals.json"
DEFAULT_HISTORY = "docs/data/history"


def build_suggestions(adapter: DataAdapter, symbols: List[str]) -> List[Dict]:
    """Fetch each symbol, score it, return suggestions that pass the threshold."""
    suggestions: List[Dict] = []
    for md in adapter.fetch(symbols):
        technical = scan_technical(md.prices)
        fundamental = scan_fundamental(md.fundamentals)
        scored = score_conviction(technical, fundamental)
        if not passes(scored):
            continue
        suggestion = {
            "symbol": md.symbol,
            "market": md.market,
            "price": md.price,
            "conviction": scored["conviction"],
            "tier": scored["tier"],
            "reasons": scored["reasons"],
            "technical": {"score": technical["score"], "patterns": technical["patterns"]},
            "fundamental": {"score": fundamental["score"],
                            "quality": fundamental["quality"],
                            "value": fundamental["value"],
                            "moat": fundamental["moat"]},
        }
        suggestion["summary"] = explain_suggestion(suggestion)
        suggestions.append(suggestion)
    suggestions.sort(key=lambda s: s["conviction"], reverse=True)
    return suggestions


def write_output(suggestions: List[Dict], out_file: str, history_dir: str,
                 scanned_at: str, universe: str) -> None:
    """Write signals.json and a dated history snapshot. Only called on success."""
    payload = {
        "scanned_at": scanned_at,
        "universe": universe,
        "count": len(suggestions),
        "suggestions": suggestions,
    }
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    os.makedirs(history_dir, exist_ok=True)
    text = json.dumps(payload, indent=2)
    with open(out_file, "w") as fh:
        fh.write(text)
    stamp = scanned_at.replace(":", "").replace("-", "")[:15]
    with open(os.path.join(history_dir, "{}.json".format(stamp)), "w") as fh:
        fh.write(text)


def main() -> None:
    universe_name = os.environ.get("SCOUT_UNIVERSE", "starter")
    symbols = get_universe(universe_name)
    scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    adapter = YFinanceUSAdapter()
    suggestions = build_suggestions(adapter, symbols)
    write_output(suggestions, DEFAULT_OUT, DEFAULT_HISTORY, scanned_at, universe_name)
    digest = build_digest(suggestions, scanned_at)
    if digest is not None:
        send_email(digest[0], digest[1])
    print("scan complete: {} suggestions from {} symbols".format(
        len(suggestions), len(symbols)))


if __name__ == "__main__":
    main()
