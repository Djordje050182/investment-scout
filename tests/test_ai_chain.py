# tests/test_ai_chain.py
from engine.ai_chain import LAYERS, ETFS, all_company_symbols, all_etf_symbols
from engine.ai_scan import score_company, layer_heat, find_catch_up


def test_taxonomy_integrity():
    keys = [l["key"] for l in LAYERS]
    assert len(keys) == len(set(keys))
    for layer in LAYERS:
        assert layer["name"] and layer["role"] and layer["watch"]
        assert len(layer["companies"]) >= 3
        for c in layer["companies"]:
            assert c["symbol"] and c["note"]
    syms = all_company_symbols()
    assert len(syms) == len(set(syms))          # no duplicate tickers
    assert len(syms) >= 50                      # comprehensive coverage
    assert len(all_etf_symbols()) == len(ETFS) >= 8


def test_score_company_strong_vs_weak():
    strong = score_company({"rel_3m": 0.20, "high_52w_dist": -0.01, "above_200dma": True,
                            "rev_growth": 0.40, "earn_growth": 0.80, "gross_margin": 0.65,
                            "fwd_pe": 25.0, "upside": 0.25})
    weak = score_company({"rel_3m": -0.20, "high_52w_dist": -0.40, "above_200dma": False,
                          "rev_growth": -0.05, "earn_growth": -0.10, "gross_margin": 0.15,
                          "fwd_pe": 60.0, "upside": -0.15})
    assert strong["ai_score"] >= 80
    assert weak["ai_score"] <= 20
    assert strong["momentum_score"] > weak["momentum_score"]
    assert strong["growth_score"] > weak["growth_score"]


def test_score_company_tolerates_missing():
    r = score_company({})
    assert r["growth_score"] is None
    assert r["ai_score"] is None or 0 <= r["ai_score"] <= 100
    partial = score_company({"rel_3m": 0.10, "above_200dma": True})
    assert partial["momentum_score"] is not None
    assert 0 <= partial["ai_score"] <= 100


def test_layer_heat_hot_and_cool():
    hot = layer_heat([
        {"rel_3m": 0.12, "above_50dma": True},
        {"rel_3m": 0.08, "above_50dma": True},
        {"rel_3m": 0.20, "above_50dma": True},
    ])
    cool = layer_heat([
        {"rel_3m": -0.12, "above_50dma": False},
        {"rel_3m": -0.08, "above_50dma": False},
    ])
    assert hot["label"] == "hot" and hot["score"] >= 60
    assert cool["label"] == "cool" and cool["score"] <= 40


def test_find_catch_up_micron_pattern():
    # hot layer; LAG trails the median with strong growth, intact trend, sane P/E
    companies = [
        {"symbol": "HOT1", "rel_3m": 0.25, "above_50dma": True, "above_200dma": True,
         "growth_score": 80, "fwd_pe": 35.0, "ai_score": 85},
        {"symbol": "HOT2", "rel_3m": 0.18, "above_50dma": True, "above_200dma": True,
         "growth_score": 75, "fwd_pe": 30.0, "ai_score": 80},
        {"symbol": "LAG", "rel_3m": -0.02, "above_50dma": True, "above_200dma": True,
         "growth_score": 70, "fwd_pe": 12.0, "ai_score": 60, "price": 100.0},
        {"symbol": "BROKEN", "rel_3m": -0.10, "above_50dma": False, "above_200dma": False,
         "growth_score": 20, "fwd_pe": 50.0, "ai_score": 20},
    ]
    layer = {"key": "memory", "name": "Memory", "companies": companies}
    heat = layer_heat(companies)
    assert heat["label"] == "hot"
    picks = find_catch_up(layer, heat)
    syms = [p["symbol"] for p in picks]
    assert "LAG" in syms          # lagging, healthy, cheap -> candidate
    assert "BROKEN" not in syms   # broken trend + weak growth -> excluded
    assert "HOT1" not in syms     # already re-rated
    assert picks[0]["thesis"]


def test_find_catch_up_requires_hot_layer():
    companies = [
        {"symbol": "A", "rel_3m": -0.10, "above_50dma": False, "above_200dma": True,
         "growth_score": 70, "fwd_pe": 10.0},
        {"symbol": "B", "rel_3m": -0.12, "above_50dma": False, "above_200dma": True,
         "growth_score": 70, "fwd_pe": 10.0},
    ]
    layer = {"key": "x", "name": "X", "companies": companies}
    heat = layer_heat(companies)
    assert find_catch_up(layer, heat) == []
