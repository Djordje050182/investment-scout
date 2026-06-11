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
        profile={"name": "Good Corp", "sector": "Tech", "country": "United States",
                 "description": "Makes good things.", "held_institutions": 0.7,
                 "held_insiders": 0.03},
        holders=[{"name": "Blackrock Inc.", "pct": 0.08}],
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
    # company profile block is present with scores and named backers
    co = g.get("company")
    assert co and co["name"] == "Good Corp"
    assert co["sector"] == "Tech"
    assert isinstance(co["backing_score"], int) and 0 <= co["backing_score"] <= 100
    assert isinstance(co["strength_score"], int)
    assert co["holders"][0]["name"] == "Blackrock Inc."


def test_build_suggestions_crypto_has_no_company_scores():
    from tests.fixtures import uptrend_closes
    coin = MarketData(
        symbol="BTC-USD", market="Crypto",
        prices=make_prices(uptrend_closes()),
        fundamentals={}, price=70000.0, profile={}, holders=[],
    )
    suggestions = build_suggestions(FakeAdapter([coin]), ["BTC-USD"])
    if suggestions:  # if it cleared the bar on technicals
        co = suggestions[0].get("company")
        # crypto: no backing/strength scores (None), not a fake zero
        assert co is None or (co.get("backing_score") is None
                              and co.get("strength_score") is None)


def test_write_output_creates_valid_json(tmp_path):
    payload = {
        "scanned_at": "2026-06-01T21:30:00Z",
        "universe": "starter",
        "count": 1,
        "suggestions": [{"symbol": "AAPL", "market": "US", "conviction": 80,
                         "tier": "both", "price": 100.0, "reasons": ["x"],
                         "technical": {}, "fundamental": {},
                         "chart": {"dates": ["2026-06-01"], "close": [100.0]}}],
        "radar": [],
        "movers": {"gainers": [], "losers": []},
    }
    out_file = tmp_path / "signals.json"
    hist_dir = tmp_path / "history"
    write_output(payload, str(out_file), str(hist_dir))
    data = json.loads(out_file.read_text())
    assert data["count"] == 1
    assert data["suggestions"][0]["symbol"] == "AAPL"
    assert data["scanned_at"] == "2026-06-01T21:30:00Z"
    assert "chart" in data["suggestions"][0]
    # a dated history snapshot was also written, without the heavy chart blob
    hist_files = list(hist_dir.glob("*.json"))
    assert len(hist_files) == 1
    hist = json.loads(hist_files[0].read_text())
    assert "chart" not in hist["suggestions"][0]


def test_build_scan_emits_radar_movers_and_charts():
    from engine.run_scan import build_scan
    from tests.fixtures import uptrend_closes
    strong = MarketData(
        symbol="GOOD", market="US",
        prices=make_prices(cup_and_handle_closes()),
        fundamentals={"roe": 0.25, "debt_to_equity": 0.3, "profit_margin": 0.22,
                      "free_cash_flow": 5e9, "trailing_pe": 18.0},
        price=99.0, profile={"name": "Good Corp"}, holders=[],
    )
    weak = MarketData(
        symbol="MEH", market="US",
        prices=make_prices(flat_closes()),
        fundamentals={}, price=50.0,
    )
    scan = build_scan(FakeAdapter([strong, weak]), ["GOOD", "MEH"])
    g = next(s for s in scan["suggestions"] if s["symbol"] == "GOOD")
    # embedded chart payload with aligned arrays
    chart = g["chart"]
    assert len(chart["dates"]) == len(chart["close"]) == len(chart["volume"])
    assert len(chart["dates"]) <= 130
    # trade plan with coherent levels
    plan = g["trade_plan"]
    assert plan["stop"] < plan["entry"] < plan["target1"] <= plan["target2"]
    assert plan["rr"] > 0
    # snapshot travels with the suggestion
    assert "rsi14" in g["snapshot"]
    # movers cover everything fetched
    all_movers = scan["movers"]["gainers"] + scan["movers"]["losers"]
    assert any(m["symbol"] == "GOOD" for m in all_movers)
