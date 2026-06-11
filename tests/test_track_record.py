# tests/test_track_record.py
from tests.fixtures import make_prices
from engine.track_record import extract_episodes, evaluate_episode, aggregate


def _snap(date, symbols):
    return {
        "scanned_at": date + "T21:30:00Z",
        "suggestions": [
            {"symbol": s, "market": "US", "price": 100.0, "conviction": 70,
             "tier": "both", "technical": {"patterns": ["breakout"]}}
            for s in symbols
        ],
    }


def test_episodes_dedupe_consecutive_days():
    snaps = [_snap("2026-06-01", ["AAA", "BBB"]),
             _snap("2026-06-02", ["AAA"]),          # AAA continues: no new episode
             _snap("2026-06-03", ["AAA", "BBB"])]   # BBB re-appears: new episode
    eps = extract_episodes(snaps)
    keys = [(e["symbol"], e["date"]) for e in eps]
    assert ("AAA", "2026-06-01") in keys
    assert ("BBB", "2026-06-01") in keys
    assert ("BBB", "2026-06-03") in keys
    assert ("AAA", "2026-06-02") not in keys
    assert len(eps) == 3


def test_evaluate_episode_returns_and_plan():
    # 30 rising bars after the signal date
    closes = [100.0 + i for i in range(40)]
    prices = make_prices(closes)
    # signal on the 5th bar's date (2024-01-05); entry 100
    ep = {"symbol": "AAA", "market": "US", "date": "2024-01-05", "price": 104.0,
          "conviction": 70, "tier": "both", "patterns": ["breakout"],
          "trade_plan": {"stop": 95.0, "target1": 115.0}}
    out = evaluate_episode(ep, prices)
    assert out["returns"]["r5"] > 0
    assert out["returns"]["r21"] > 0
    assert out["plan_outcome"] == "target1"
    assert out["status"] == "closed"


def test_evaluate_episode_stop_conservative():
    # falling series: stop must trigger, not target
    closes = [100.0 - i for i in range(40)]
    prices = make_prices(closes)
    ep = {"symbol": "AAA", "market": "US", "date": "2024-01-05", "price": 96.0,
          "trade_plan": {"stop": 90.0, "target1": 110.0}, "patterns": []}
    out = evaluate_episode(ep, prices)
    assert out["plan_outcome"] == "stopped"


def test_evaluate_episode_no_prices_is_unpriced():
    ep = {"symbol": "AAA", "market": "US", "date": "2024-01-05", "price": 100.0,
          "patterns": []}
    assert evaluate_episode(ep, None)["status"] == "unpriced"


def test_aggregate_by_pattern_and_tier():
    rows = [
        {"patterns": ["breakout"], "tier": "both", "market": "US",
         "returns": {"r5": 0.05, "r21": 0.10}, "plan_outcome": "target1"},
        {"patterns": ["breakout"], "tier": "technical", "market": "US",
         "returns": {"r5": -0.02, "r21": -0.04}, "plan_outcome": "stopped"},
    ]
    agg = aggregate(rows)
    assert agg["overall"]["episodes"] == 2
    assert agg["overall"]["win_rate_1m"] == 0.5
    assert agg["by_pattern"]["breakout"]["episodes"] == 2
    assert agg["by_pattern"]["breakout"]["target_rate"] == 0.5
    assert agg["by_tier"]["both"]["episodes"] == 1
