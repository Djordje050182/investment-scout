# tests/test_attention.py
from datetime import date
from engine.attention import (interest_ratio, volume_ratio, parse_twse_row,
                              edgar_form_counts)
from engine.ai_chain import LAYERS, THEMES


def test_themes_cover_every_layer():
    keys = {l["key"] for l in LAYERS}
    assert set(THEMES.keys()) == keys
    for t in THEMES.values():
        assert t.get("trends") and t.get("news")


def test_interest_ratio_above_norm():
    series = [50] * 48 + [100, 100, 100, 100]   # recent spike
    r = interest_ratio(series)
    assert r is not None and r > 1.5


def test_interest_ratio_insufficient_or_zero():
    assert interest_ratio([1, 2, 3]) is None
    assert interest_ratio([0] * 52) is None


def test_volume_ratio_news_spike():
    series = ([{"date": "x", "value": 10}] * 90
              + [{"date": "x", "value": 30}] * 30)
    r = volume_ratio(series)
    assert r is not None and 2.5 < r < 3.5
    assert volume_ratio([]) is None


def test_parse_twse_row_roc_dates():
    row = {
        "資料年月": "11504",
        "營業收入-當月營收": "410725118",
        "營業收入-上月比較增減(%)": "-1.0757",
        "營業收入-去年同月增減(%)": "17.4954",
        "累計營業收入-前期比較增減(%)": "29.9463",
    }
    parsed = parse_twse_row(row)
    assert parsed["month"] == "2026-04"          # ROC 115 -> 2026
    assert parsed["yoy_pct"] == 17.5
    assert parsed["ytd_yoy_pct"] == 29.95
    assert parse_twse_row({"資料年月": "bad"}) is None


def test_edgar_form_counts():
    subs = {"filings": {"recent": {
        "form": ["4", "8-K", "4", "10-Q", "4", "8-K"],
        "filingDate": ["2026-06-01", "2026-05-20", "2026-04-15",
                       "2026-04-01", "2025-12-01", "2026-02-10"],
    }}}
    out = edgar_form_counts(subs, since=date(2026, 3, 14))
    assert out["form4_90d"] == 2                 # Dec one is too old
    assert out["last_8k"] == "2026-05-20"
    assert edgar_form_counts({}, since=date(2026, 1, 1)) == {"form4_90d": 0, "last_8k": None}
