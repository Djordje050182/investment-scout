# engine/allocators_scan.py
"""Fetch the Capital Allocators data from SEC EDGAR and write docs/data/allocators.json.

Daily flow:
1. For each manager in the roster: latest two 13F-HR filings -> holdings,
   weights, quarter-over-quarter changes.
2. Map CUSIPs to tickers via OpenFIGI (keyless, throttled), cached in
   engine/data/cusip_map.json so re-runs only look up new names.
3. Berkshire's rough asset mix + cash direction from 10-Q XBRL.
4. Form 4 open-market insider buys across INSIDER_WATCH (last 120 days).
5. Consensus scores -> copy-the-legends basket; change feed; meter summary.

13Fs only change quarterly, but the daily run means a new filing shows up
on the site within a day of hitting EDGAR — that's the "winds are changing"
alarm. All fetchers fail soft: a manager that errors is skipped, the rest
of the file still writes.

Usage: python -m engine.allocators_scan
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

from engine.allocators import (
    MANAGERS, INSIDER_WATCH, BRK_MIX_CONCEPTS, CUSIP_SEED,
    parse_info_table, aggregate_holdings, portfolio_weights, diff_holdings,
    consensus_scores, build_basket, parse_form4, activity_summary,
)

DEFAULT_OUT = "docs/data/allocators.json"
CUSIP_MAP_PATH = "engine/data/cusip_map.json"
UA = {"User-Agent": "investment-scout/1.0 (research tool; dj1982@outlook.com)"}
THROTTLE = 0.30          # EDGAR asks for <10 req/s; stay well under
FIGI_BATCH = 10          # keyless OpenFIGI: 10 jobs/request, 25 req/min
FIGI_SLEEP = 2.6
TOP_HOLDINGS = 15        # shown per manager card
CONSENSUS_DEPTH = 50     # holdings per manager that feed the consensus
FORM4_LOOKBACK_DAYS = 120
FORM4_PER_COMPANY = 8


def _get(url: str, timeout: int = 30) -> bytes:
    time.sleep(THROTTLE)
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def _get_json(url: str) -> Dict:
    return json.loads(_get(url).decode("utf-8", "replace"))


# ---------------------------------------------------------------------------
# 13F fetching

def latest_13f_filings(cik: int, n: int = 2) -> List[Dict]:
    subs = _get_json("https://data.sec.gov/submissions/CIK%010d.json" % cik)
    r = subs["filings"]["recent"]
    out = []
    for form, fdate, rdate, acc in zip(
            r["form"], r["filingDate"], r["reportDate"], r["accessionNumber"]):
        if form == "13F-HR":
            out.append({"accession": acc, "filed": fdate, "period": rdate})
        if len(out) >= n:
            break
    return out


def fetch_info_table_xml(cik: int, accession: str) -> str:
    accnd = accession.replace("-", "")
    idx = _get_json("https://www.sec.gov/Archives/edgar/data/%d/%s/index.json"
                    % (cik, accnd))
    names = [it["name"] for it in idx["directory"]["item"]
             if it["name"].lower().endswith(".xml")
             and "primary_doc" not in it["name"].lower()]
    if not names:
        raise RuntimeError("no information table xml in %s" % accession)
    return _get("https://www.sec.gov/Archives/edgar/data/%d/%s/%s"
                % (cik, accnd, names[0])).decode("utf-8", "replace")


def fetch_manager(mgr: Dict) -> Optional[Dict]:
    try:
        filings = latest_13f_filings(mgr["cik"])
        if not filings:
            return None
        cur_xml = fetch_info_table_xml(mgr["cik"], filings[0]["accession"])
        cur = aggregate_holdings(parse_info_table(cur_xml))
        cur_total, holdings = portfolio_weights(cur)
        changes: List[Dict] = []
        if len(filings) > 1:
            prev_xml = fetch_info_table_xml(mgr["cik"], filings[1]["accession"])
            prev = aggregate_holdings(parse_info_table(prev_xml))
            prev_total = sum(h["value"] for h in prev.values())
            changes = diff_holdings(cur, prev, cur_total, prev_total)
        return {
            "key": mgr["key"], "fund": mgr["fund"], "person": mgr["person"],
            "style": mgr["style"], "bio": mgr["bio"], "exclude": mgr["exclude"],
            "as_of": filings[0]["period"], "filed": filings[0]["filed"],
            "total_value": cur_total,
            "positions": len(cur),
            "holdings": holdings[:CONSENSUS_DEPTH],
            "changes": changes[:12],
        }
    except Exception as exc:
        print("  ! %s failed: %s" % (mgr["fund"], exc))
        return None


# ---------------------------------------------------------------------------
# CUSIP -> ticker via OpenFIGI, cached

def load_cusip_map() -> Dict[str, str]:
    m = dict(CUSIP_SEED)
    if os.path.exists(CUSIP_MAP_PATH):
        with open(CUSIP_MAP_PATH) as fh:
            m.update(json.load(fh))
    return m


def map_cusips(cusips: List[str], cache: Dict[str, str]) -> Dict[str, str]:
    """Resolve missing CUSIPs via OpenFIGI; unknowns cached as "" to skip."""
    missing = sorted({c for c in cusips if c and c not in cache})
    for i in range(0, len(missing), FIGI_BATCH):
        batch = missing[i:i + FIGI_BATCH]
        jobs = [{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"}
                for c in batch]
        try:
            req = urllib.request.Request(
                "https://api.openfigi.com/v3/mapping",
                data=json.dumps(jobs).encode(),
                headers={"Content-Type": "application/json"})
            res = json.loads(urllib.request.urlopen(req, timeout=30).read())
            for c, r in zip(batch, res):
                data = r.get("data") or []
                cache[c] = data[0].get("ticker", "") if data else ""
        except Exception as exc:
            print("  ! openfigi batch failed: %s" % exc)
        time.sleep(FIGI_SLEEP)
    return cache


def save_cusip_map(cache: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(CUSIP_MAP_PATH), exist_ok=True)
    with open(CUSIP_MAP_PATH, "w") as fh:
        json.dump(cache, fh, indent=0, sort_keys=True)


# ---------------------------------------------------------------------------
# Berkshire asset mix (10-Q XBRL)

def fetch_brk_mix() -> Dict:
    mix, prev_cash, cur_cash = [], None, None
    for concept, label in BRK_MIX_CONCEPTS:
        try:
            d = _get_json(
                "https://data.sec.gov/api/xbrl/companyconcept/CIK0001067983/us-gaap/%s.json"
                % concept)
            rows = [u for u in d["units"]["USD"]
                    if u.get("form") in ("10-Q", "10-K")]
            rows.sort(key=lambda u: (u["end"], u["filed"]))
            # de-dup by period end, keep latest filing of each
            by_end: Dict[str, Dict] = {}
            for u in rows:
                by_end[u["end"]] = u
            ordered = [by_end[k] for k in sorted(by_end)]
            if not ordered:
                continue
            latest = ordered[-1]
            mix.append({"label": label, "value": latest["val"],
                        "as_of": latest["end"]})
            if concept.startswith("CashCash"):
                cur_cash = latest["val"]
                if len(ordered) > 1:
                    prev_cash = ordered[-2]["val"]
        except Exception as exc:
            print("  ! brk concept %s failed: %s" % (concept, exc))
    cash_dir = "flat"
    if cur_cash and prev_cash:
        chg = (cur_cash - prev_cash) / prev_cash
        if chg > 0.10:
            cash_dir = "building"
        elif chg < -0.10:
            cash_dir = "deploying"
    return {"mix": mix, "cash_dir": cash_dir,
            "cash_prev": prev_cash, "cash_now": cur_cash}


# ---------------------------------------------------------------------------
# Form 4 insider buys

def fetch_insider_buys() -> List[Dict]:
    cutoff = _days_ago_iso(FORM4_LOOKBACK_DAYS)
    out: List[Dict] = []
    for ticker, meta in INSIDER_WATCH.items():
        try:
            subs = _get_json("https://data.sec.gov/submissions/CIK%010d.json"
                             % meta["cik"])
            r = subs["filings"]["recent"]
            f4 = [(acc, fdate, doc) for form, fdate, acc, doc in zip(
                      r["form"], r["filingDate"], r["accessionNumber"],
                      r["primaryDocument"])
                  if form == "4" and fdate >= cutoff][:FORM4_PER_COMPANY]
            for acc, fdate, doc in f4:
                accnd = acc.replace("-", "")
                raw = doc.split("/")[-1]
                try:
                    xml = _get("https://www.sec.gov/Archives/edgar/data/%d/%s/%s"
                               % (meta["cik"], accnd, raw)).decode("utf-8", "replace")
                except Exception:
                    continue
                for b in parse_form4(xml):
                    out.append(dict(b, ticker=ticker, company=meta["name"],
                                    filed=fdate))
        except Exception as exc:
            print("  ! form4 %s failed: %s" % (ticker, exc))
    out.sort(key=lambda b: (b.get("date") or b["filed"]), reverse=True)
    return out


def _days_ago_iso(days: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Orchestration

def attach_tickers(managers_data: List[Dict], cusip_map: Dict[str, str]) -> None:
    for m in managers_data:
        for h in m["holdings"]:
            h["ticker"] = cusip_map.get(h["cusip"], "") or None
        for c in m["changes"]:
            c["ticker"] = cusip_map.get(c["cusip"], "") or None


def build_change_feed(managers_data: List[Dict]) -> List[Dict]:
    feed = []
    for m in managers_data:
        for c in m["changes"]:
            feed.append({
                "manager": m["person"], "fund": m["fund"], "key": m["key"],
                "filed": m["filed"], "as_of": m["as_of"],
                "type": c["type"], "ticker": c.get("ticker"),
                "name": c["name"].title(), "pct": c["pct"],
                "swing": c.get("swing"), "put_call": c["put_call"],
            })
    order = {"new": 0, "exit": 1, "added": 2, "trimmed": 3}
    feed.sort(key=lambda c: (c["filed"], -order[c["type"]], c["pct"]),
              reverse=True)
    return feed


def build_payload() -> Dict:
    print("Capital Allocators scan")
    managers_data: List[Dict] = []
    for mgr in MANAGERS:
        print("  13F: %s" % mgr["fund"])
        got = fetch_manager(mgr)
        if got:
            managers_data.append(got)

    cusips = [h["cusip"] for m in managers_data for h in m["holdings"]]
    cusips += [c["cusip"] for m in managers_data for c in m["changes"]]
    print("  mapping %d cusips" % len(set(cusips)))
    cusip_map = map_cusips(cusips, load_cusip_map())
    save_cusip_map({k: v for k, v in cusip_map.items() if k not in CUSIP_SEED})
    attach_tickers(managers_data, cusip_map)

    print("  berkshire mix")
    brk = fetch_brk_mix()
    print("  insider form 4s")
    insiders = fetch_insider_buys()

    scores = consensus_scores(managers_data)
    basket = build_basket(scores)
    feed = build_change_feed(managers_data)
    summary = activity_summary(feed, brk["cash_dir"])

    # trim manager holdings for the payload (consensus already computed)
    for m in managers_data:
        m["holdings"] = m["holdings"][:TOP_HOLDINGS]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "managers": managers_data,
        "consensus": scores[:40],
        "basket": basket,
        "changes": feed[:60],
        "insiders": insiders[:30],
        "berkshire": brk,
        "summary": summary,
    }


def write_output(payload: Dict, path: str = DEFAULT_OUT) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print("wrote %s (%d managers, %d basket names, %d changes, %d insider buys)"
          % (path, len(payload["managers"]), len(payload["basket"]),
             len(payload["changes"]), len(payload["insiders"])))


if __name__ == "__main__":
    write_output(build_payload())
