# engine/attention.py
"""Free alternative-data collectors for the AI supply chain view.

Four sources, all free, all optional — every collector returns None (or {})
on any failure so a flaky third party can never break the scan:

1. Google Trends (pytrends, unofficial): search interest per layer theme.
   Datacentre IPs are often rate-limited, so CI runs may come back empty —
   the UI simply hides the chip.
2. GDELT DOC 2.0 (no key): global news volume per layer theme. Rate limit
   is one request per 5 seconds — collectors throttle accordingly.
3. TWSE OpenAPI (no key): Taiwan-listed monthly revenue. TSMC's monthly
   revenue is the best free leading indicator for the whole chain's demand.
4. SEC EDGAR (no key, UA header required): per-company filing activity —
   insider Form 4 count in the last 90 days and the latest 8-K date.

Pure computation helpers are separated from I/O so they unit-test offline.
"""
import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

_UA = "investment-scout/1.0 (research tool; dj1982@outlook.com)"
_GDELT_THROTTLE = 7.5          # stated limit is 5s, but bursts still 429 — pad it
_GDELT_RETRY_WAIT = 25.0       # one retry after a longer cool-off


def _get_json(url: str, timeout: int = 20) -> Optional[object]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------

def interest_ratio(values: List[float], recent: int = 4) -> Optional[float]:
    """Mean of the last `recent` points vs the mean of the whole series.

    >1 = attention above its 12-month norm. None when not computable.
    """
    vals = [float(v) for v in values if v is not None]
    if len(vals) < recent + 4:
        return None
    base = sum(vals) / len(vals)
    if base <= 0:
        return None
    tail = sum(vals[-recent:]) / recent
    return round(tail / base, 2)


def volume_ratio(series: List[Dict], recent_days: int = 30) -> Optional[float]:
    """GDELT timeline: mean daily volume of the last `recent_days` vs the rest.

    `series` is GDELT's [{date: 'YYYYMMDDT...', value: n}, ...]. >1 = the
    theme is in the news more than its recent baseline.
    """
    if not series or len(series) < recent_days + 14:
        return None
    values = [float(p.get("value") or 0.0) for p in series]
    head, tail = values[:-recent_days], values[-recent_days:]
    base = sum(head) / len(head)
    if base <= 0:
        return None
    return round((sum(tail) / len(tail)) / base, 2)


def parse_twse_row(row: Dict) -> Optional[Dict]:
    """Normalize one TWSE monthly-revenue row (ROC-dated, zh-TW keys)."""
    try:
        ym = row["資料年月"]                       # e.g. '11504' = ROC 115, month 04
        year = int(ym[:3]) + 1911
        month = int(ym[3:])
        return {
            "month": "{:04d}-{:02d}".format(year, month),
            "revenue_twd_k": int(row["營業收入-當月營收"]),
            "mom_pct": round(float(row["營業收入-上月比較增減(%)"]), 2),
            "yoy_pct": round(float(row["營業收入-去年同月增減(%)"]), 2),
            "ytd_yoy_pct": round(float(row["累計營業收入-前期比較增減(%)"]), 2),
        }
    except (KeyError, ValueError, TypeError):
        return None


def edgar_form_counts(submissions: Dict, since: date) -> Dict:
    """From an EDGAR submissions payload: Form 4 count since `since` and the
    most recent 8-K date. Tolerates missing keys."""
    out = {"form4_90d": 0, "last_8k": None}
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    for form, fdate in zip(forms, dates):
        try:
            d = date.fromisoformat(fdate)
        except (ValueError, TypeError):
            continue
        if form == "4" and d >= since:
            out["form4_90d"] += 1
        if form == "8-K" and (out["last_8k"] is None or fdate > out["last_8k"]):
            out["last_8k"] = fdate
    return out


# ---------------------------------------------------------------------------
# Collectors (network; every one fails soft)
# ---------------------------------------------------------------------------

def fetch_trends(terms: List[str]) -> Dict[str, Optional[float]]:
    """Google Trends interest ratio per term (12-month window, batches of 5)."""
    out: Dict[str, Optional[float]] = {}
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(5, 20))
        for i in range(0, len(terms), 5):
            batch = terms[i:i + 5]
            try:
                pt.build_payload(batch, timeframe="today 12-m")
                df = pt.interest_over_time()
                for term in batch:
                    if term in df:
                        out[term] = interest_ratio(list(df[term]))
                time.sleep(2.0)
            except Exception as exc:
                print("trends batch failed ({}): {}".format(batch, exc))
    except Exception as exc:
        print("trends unavailable: {}".format(exc))
    return out


def fetch_gdelt(query: str) -> Optional[float]:
    """News volume ratio for one query (last 30d vs prior baseline).

    Retries once after a long cool-off on a 429 — GDELT's limiter is
    stricter than its stated 1-per-5s under bursty traffic.
    """
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?query={}"
           "&mode=timelinevolraw&timespan=120d&format=json").format(
               urllib.parse.quote('"{}"'.format(query)))
    for attempt in (1, 2):
        try:
            data = _get_json(url)
            timeline = (data or {}).get("timeline") or []
            series = timeline[0].get("data") if timeline else None
            time.sleep(_GDELT_THROTTLE)
            return volume_ratio(series or [])
        except Exception as exc:
            print("gdelt failed ({}, attempt {}): {}".format(query, attempt, exc))
            if attempt == 1 and "429" in str(exc):
                time.sleep(_GDELT_RETRY_WAIT)
            else:
                time.sleep(_GDELT_THROTTLE)
                return None
    return None


# TWSE codes worth tracking as chain-demand proxies.
TWSE_PROXIES = {"2330": "TSMC", "2317": "Hon Hai (Foxconn)"}


def fetch_twse_revenue() -> Dict[str, Dict]:
    """Latest monthly revenue for the Taiwan chain proxies (TSMC, Hon Hai)."""
    try:
        rows = _get_json("https://openapi.twse.com.tw/v1/opendata/t187ap05_L")
        out = {}
        for row in rows or []:
            code = row.get("公司代號")
            if code in TWSE_PROXIES:
                parsed = parse_twse_row(row)
                if parsed:
                    parsed["name"] = TWSE_PROXIES[code]
                    out[code] = parsed
        return out
    except Exception as exc:
        print("twse failed: {}".format(exc))
        return {}


def fetch_edgar_activity(tickers: List[str], throttle: float = 0.15) -> Dict[str, Dict]:
    """Filing activity per US ticker: Form 4 count (90d) + last 8-K date."""
    out: Dict[str, Dict] = {}
    try:
        mapping = _get_json("https://www.sec.gov/files/company_tickers.json") or {}
        by_ticker = {v["ticker"]: int(v["cik_str"]) for v in mapping.values()}
    except Exception as exc:
        print("edgar ticker map failed: {}".format(exc))
        return out
    since = date.today() - timedelta(days=90)
    for t in tickers:
        cik = by_ticker.get(t.replace("-", ""))   # BRK-B -> BRKB style
        if cik is None:
            cik = by_ticker.get(t)
        if cik is None:
            continue
        try:
            subs = _get_json("https://data.sec.gov/submissions/CIK{:010d}.json".format(cik))
            out[t] = edgar_form_counts(subs or {}, since)
        except Exception as exc:
            print("edgar failed ({}): {}".format(t, exc))
        time.sleep(throttle)
    return out


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def collect_attention(layer_themes: Dict[str, Dict],
                      us_tickers: List[str]) -> Dict:
    """Gather everything; any missing source just yields empty fields.

    layer_themes: {layer_key: {"trends": term, "news": term}}
    Returns {"layers": {key: {"trends_ratio", "trends_term",
                              "news_ratio", "news_term"}},
             "pulse": {"twse": {...}},
             "edgar": {ticker: {...}}}
    """
    trend_terms = [t["trends"] for t in layer_themes.values() if t.get("trends")]
    trends = fetch_trends(trend_terms)

    layers: Dict[str, Dict] = {}
    for key, themes in layer_themes.items():
        entry: Dict = {}
        term = themes.get("trends")
        if term and trends.get(term) is not None:
            entry["trends_ratio"] = trends[term]
            entry["trends_term"] = term
        news_term = themes.get("news")
        if news_term:
            ratio = fetch_gdelt(news_term)
            if ratio is not None:
                entry["news_ratio"] = ratio
                entry["news_term"] = news_term
        layers[key] = entry

    generated = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "generated_at": generated,
        "layers": layers,
        "pulse": {"twse": fetch_twse_revenue()},
        "edgar": fetch_edgar_activity(us_tickers),
    }
