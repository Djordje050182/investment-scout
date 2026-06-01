# tests/test_run_scan.py
import json
from tests.fixtures import make_prices, cup_and_handle_closes, flat_closes
from engine.adapters.base import MarketData
from engine.run_scan import build_suggestions, write_output


class FakeAdapter:
    def __init__(self, data):
        self._data = data
    def fetch(self, symbols):
        return self._data


def test_build_suggestions_filters_by_threshold():
    strong = MarketData(
        symbol="GOOD", market="US",
        prices=make_prices(cup_and_handle_closes()),
        fundamentals={"roe": 0.25, "debt_to_equity": 0.3, "profit_margin": 0.22,
                      "free_cash_flow": 5e9, "trailing_pe": 18.0, "shares_change": -0.02},
        price=99.0,
    )
    weak = MarketData(
        symbol="MEH", market="US",
        prices=make_prices(flat_closes()),
        fundamentals={}, price=50.0,
    )
    suggestions = build_suggestions(FakeAdapter([strong, weak]), ["GOOD", "MEH"])
    symbols = [s["symbol"] for s in suggestions]
    assert "GOOD" in symbols
    assert "MEH" not in symbols
    g = next(s for s in suggestions if s["symbol"] == "GOOD")
    assert g["conviction"] >= 55
    assert "reasons" in g and len(g["reasons"]) > 0
    # each suggestion carries a plain-English explanation
    assert g.get("summary") and "GOOD" in g["summary"]


def test_write_output_creates_valid_json(tmp_path):
    suggestions = [{"symbol": "AAPL", "market": "US", "conviction": 80,
                    "tier": "both", "price": 100.0, "reasons": ["x"],
                    "technical": {}, "fundamental": {}}]
    out_file = tmp_path / "signals.json"
    hist_dir = tmp_path / "history"
    write_output(suggestions, str(out_file), str(hist_dir),
                 scanned_at="2026-06-01T21:30:00Z", universe="starter")
    data = json.loads(out_file.read_text())
    assert data["count"] == 1
    assert data["suggestions"][0]["symbol"] == "AAPL"
    assert data["scanned_at"] == "2026-06-01T21:30:00Z"
    # a dated history snapshot was also written
    assert len(list(hist_dir.glob("*.json"))) == 1
