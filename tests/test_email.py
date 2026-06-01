# tests/test_email.py
from engine.notify.email import build_digest


def _suggestion(symbol, conviction, tier, reasons):
    return {"symbol": symbol, "market": "US", "conviction": conviction,
            "tier": tier, "price": 100.0, "reasons": reasons}


def test_build_digest_includes_symbols_and_reasons():
    suggestions = [
        _suggestion("AAPL", 87, "both", ["ROE 25%", "Cup-and-handle forming"]),
        _suggestion("MSFT", 60, "technical", ["Breakout above resistance on volume"]),
    ]
    subject, body = build_digest(suggestions, scanned_at="2026-06-01T21:30:00Z")
    assert "2" in subject
    assert "AAPL" in body
    assert "ROE 25%" in body
    assert "87" in body


def test_build_digest_empty_returns_none():
    result = build_digest([], scanned_at="2026-06-01T21:30:00Z")
    assert result is None
