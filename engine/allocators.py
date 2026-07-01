# engine/allocators.py
"""The Capital Allocators roster + pure 13F/Form-4 parsing and scoring logic.

Who we track and why
--------------------
Any US fund manager running more than $100m must publish their portfolio
quarterly on SEC form 13F. That is the only legal, free window into what the
best capital allocators in the world actually own — exact tickers, share
counts and position sizes. We track a hand-picked roster of all-time greats.

What a 13F does NOT show (we say this in the UI too):
- cash, bonds, shorts, non-US listings, private stakes;
- anything faster than quarterly, filed up to 45 days after quarter end.

Berkshire's cash pile and asset mix come separately from its 10-Q (XBRL).
Insider conviction comes from Form 4 open-market purchases (code "P") —
an executive spending their own money on their own stock.

Everything here is pure logic (no network) so it unit-tests cleanly;
fetching lives in engine/allocators_scan.py.
"""
import html
import re
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# The roster. CIKs verified against EDGAR July 2026.
# "exclude" = the manager's own listed vehicle; owning yourself isn't a pick.
MANAGERS: List[Dict] = [
    {
        "key": "berkshire", "cik": 1067983,
        "fund": "Berkshire Hathaway", "person": "Warren Buffett",
        "style": "Quality compounders, held forever",
        "bio": "The greatest long-term record in history — roughly 20% a year for six decades. Buys wonderful businesses at fair prices and almost never sells.",
        "exclude": [],
    },
    {
        "key": "duquesne", "cik": 1536411,
        "fund": "Duquesne Family Office", "person": "Stanley Druckenmiller",
        "style": "Macro trends, ridden hard",
        "bio": "30 years without a single losing year. Famous for finding the big macro theme early and betting it in size — he was early into AI names.",
        "exclude": [],
    },
    {
        "key": "pershing", "cik": 1336528,
        "fund": "Pershing Square", "person": "Bill Ackman",
        "style": "Concentrated activist bets",
        "bio": "Runs one of the most concentrated books in the world — usually 8-12 large positions he knows inside out, often pushing management to improve.",
        "exclude": [],
    },
    {
        "key": "appaloosa", "cik": 1656456,
        "fund": "Appaloosa", "person": "David Tepper",
        "style": "Buys panic, sells euphoria",
        "bio": "The king of distressed buying — made billions buying banks in 2009 when everyone else was running. Watch what he buys during sell-offs.",
        "exclude": [],
    },
    {
        "key": "bridgewater", "cik": 1350694,
        "fund": "Bridgewater Associates", "person": "Ray Dalio",
        "style": "Diversified 'all-weather' machine",
        "bio": "The world's largest hedge fund. Thousands of positions balanced across scenarios — its top holdings show where the machine sees durable value.",
        "exclude": [],
    },
    {
        "key": "baupost", "cik": 1061768,
        "fund": "Baupost Group", "person": "Seth Klarman",
        "style": "Deep value, huge patience",
        "bio": "Wrote the cult classic 'Margin of Safety'. Happy to sit in cash for years until something is genuinely mispriced.",
        "exclude": [],
    },
    {
        "key": "himalaya", "cik": 1709323,
        "fund": "Himalaya Capital", "person": "Li Lu",
        "style": "Very few, very big, very long",
        "bio": "The investor Charlie Munger trusted with his own family's money. A handful of positions held for many years.",
        "exclude": [],
    },
    {
        "key": "icahn", "cik": 921669,
        "fund": "Icahn Enterprises", "person": "Carl Icahn",
        "style": "Activist pressure plays",
        "bio": "The original corporate raider. Takes big stakes and forces change. His 13F is dominated by his own vehicle, so we look past it to the actual bets.",
        "exclude": ["IEP"],
    },
    {
        "key": "fundsmith", "cik": 1569205,
        "fund": "Fundsmith", "person": "Terry Smith",
        "style": "Buy quality, do nothing",
        "bio": "Britain's answer to Buffett. Three rules: buy good companies, don't overpay, do nothing. Owns global quality compounders for years.",
        "exclude": [],
    },
    {
        "key": "scion", "cik": 1649339,
        "fund": "Scion Asset Management", "person": "Michael Burry",
        "style": "Contrarian, often early",
        "bio": "Called the 2008 housing crash (The Big Short). Filings are sporadic since he returned outside money — shown here for his signal value when he does file.",
        "exclude": [],
    },
]

# Executives whose own-money buying we watch (Form 4, code P).
# This is the honest version of "what are Musk / Dimon / Saylor doing" —
# their personal wealth isn't public, but their own-stock trades are.
INSIDER_WATCH: Dict[str, Dict] = {
    "AAPL":  {"cik": 320193,  "name": "Apple"},
    "MSFT":  {"cik": 789019,  "name": "Microsoft"},
    "NVDA":  {"cik": 1045810, "name": "Nvidia"},
    "TSLA":  {"cik": 1318605, "name": "Tesla"},
    "JPM":   {"cik": 19617,   "name": "JPMorgan"},
    "META":  {"cik": 1326801, "name": "Meta"},
    "AMZN":  {"cik": 1018724, "name": "Amazon"},
    "GOOGL": {"cik": 1652044, "name": "Alphabet"},
    "AVGO":  {"cik": 1730168, "name": "Broadcom"},
    "MU":    {"cik": 723125,  "name": "Micron"},
    "MSTR":  {"cik": 1050446, "name": "Strategy"},
    "BRK-B": {"cik": 1067983, "name": "Berkshire Hathaway"},
}

# Berkshire balance-sheet concepts (10-Q XBRL) for the rough asset mix.
BRK_MIX_CONCEPTS: List[Tuple[str, str]] = [
    ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash & equivalents"),
    ("EquitySecuritiesFvNi", "Listed shares"),
    ("AvailableForSaleSecuritiesDebtSecurities", "Bonds"),
    ("EquityMethodInvestments", "Big minority stakes"),
]

# Hand-seeded CUSIP -> ticker for names OpenFIGI maps to odd listings.
CUSIP_SEED: Dict[str, str] = {
    "H1467J104": "CB",       # Chubb (Swiss-incorporated)
    "G0176J109": "STZ",      # historical oddities kept harmless if unused
}

# Same company, two tickers — merge so conviction isn't split across classes.
TICKER_MERGE: Dict[str, str] = {"GOOG": "GOOGL", "BRK/A": "BRK/B", "BRK.A": "BRK.B"}

# Changes below these floors are noise, not signal.
MIN_POSITION_PCT = 1.0       # a "new buy"/"exit" must be >= 1% of the book
MIN_SWING_PCT = 25.0         # an "added"/"trimmed" needs >= 25% share change
MIN_INSIDER_USD = 200_000    # ignore token insider purchases
BASKET_MAX = 12              # positions in the copy-the-legends basket
BASKET_CAP = 0.20            # no single name over 20% of the basket


# ---------------------------------------------------------------------------
# 13F parsing (pure; xml text in, rows out)

def _tag(row: str, tag: str) -> str:
    m = re.search(r"<(?:\w+:)?%s>(.*?)</(?:\w+:)?%s>" % (tag, tag), row, re.S)
    return html.unescape(m.group(1).strip()) if m else ""


def parse_info_table(xml_text: str) -> List[Dict]:
    """Parse a 13F information-table XML into holding rows.

    Values are whole dollars in modern filings. Rows with the same CUSIP
    (Berkshire files one per sub-manager) are NOT merged here — see
    aggregate_holdings.
    """
    rows = []
    for chunk in re.findall(r"<(?:\w+:)?infoTable>.*?</(?:\w+:)?infoTable>", xml_text, re.S):
        try:
            value = int(float(_tag(chunk, "value") or 0))
        except ValueError:
            continue
        try:
            shares = int(float(_tag(chunk, "sshPrnamt") or 0))
        except ValueError:
            shares = 0
        rows.append({
            "name": _tag(chunk, "nameOfIssuer"),
            "cusip": _tag(chunk, "cusip"),
            "value": value,
            "shares": shares,
            "put_call": _tag(chunk, "putCall").upper(),  # "" | PUT | CALL
        })
    return rows


def aggregate_holdings(rows: List[Dict]) -> Dict[str, Dict]:
    """Merge rows by CUSIP (+ option type). Returns {key: holding}."""
    agg: Dict[str, Dict] = {}
    for r in rows:
        if not r["cusip"] or r["value"] <= 0:
            continue
        key = r["cusip"] + ("|" + r["put_call"] if r["put_call"] else "")
        h = agg.setdefault(key, {
            "name": r["name"], "cusip": r["cusip"],
            "value": 0, "shares": 0, "put_call": r["put_call"],
        })
        h["value"] += r["value"]
        h["shares"] += r["shares"]
    return agg


def portfolio_weights(agg: Dict[str, Dict]) -> Tuple[int, List[Dict]]:
    """Total reported value + holdings sorted by weight (pct of book).

    Values should be whole dollars (post-2023 rule), but some filers still
    report thousands. A 13F is only required above $100m, so a total under
    $50m means the filing is in thousands — scale it up.
    """
    total = sum(h["value"] for h in agg.values())
    if 0 < total < 50_000_000:
        for h in agg.values():
            h["value"] *= 1000
        total *= 1000
    out = []
    for h in agg.values():
        pct = 100.0 * h["value"] / total if total else 0.0
        out.append(dict(h, pct=round(pct, 2)))
    out.sort(key=lambda h: -h["value"])
    return total, out


def diff_holdings(cur: Dict[str, Dict], prev: Dict[str, Dict],
                  cur_total: int, prev_total: int) -> List[Dict]:
    """Quarter-over-quarter changes worth flagging: new / exit / added / trimmed."""
    changes = []
    for key, h in cur.items():
        pct = 100.0 * h["value"] / cur_total if cur_total else 0.0
        p = prev.get(key)
        if p is None:
            if pct >= MIN_POSITION_PCT:
                changes.append({"type": "new", "cusip": h["cusip"], "name": h["name"],
                                "put_call": h["put_call"], "pct": round(pct, 1)})
        elif p["shares"] > 0 and h["shares"] > 0:
            swing = 100.0 * (h["shares"] - p["shares"]) / p["shares"]
            if swing >= MIN_SWING_PCT and pct >= MIN_POSITION_PCT:
                changes.append({"type": "added", "cusip": h["cusip"], "name": h["name"],
                                "put_call": h["put_call"], "pct": round(pct, 1),
                                "swing": round(swing)})
            elif swing <= -MIN_SWING_PCT:
                changes.append({"type": "trimmed", "cusip": h["cusip"], "name": h["name"],
                                "put_call": h["put_call"], "pct": round(pct, 1),
                                "swing": round(swing)})
    for key, p in prev.items():
        if key not in cur:
            prev_pct = 100.0 * p["value"] / prev_total if prev_total else 0.0
            if prev_pct >= MIN_POSITION_PCT:
                changes.append({"type": "exit", "cusip": p["cusip"], "name": p["name"],
                                "put_call": p["put_call"], "pct": round(prev_pct, 1)})
    order = {"new": 0, "exit": 1, "added": 2, "trimmed": 3}
    changes.sort(key=lambda c: (order[c["type"]], -c["pct"]))
    return changes


# ---------------------------------------------------------------------------
# Consensus basket — conviction-weighted across the roster

def consensus_scores(managers_data: List[Dict]) -> List[Dict]:
    """Score every ticker by how much conviction the roster has in it.

    conviction points = sum over managers of that manager's portfolio weight
    (capped at 25 so one mega-position can't drown everything). A stock held
    at 20% by Buffett beats one held at 0.4% by five funds — position size IS
    the signal, that's the whole point of conviction weighting.

    Skips: options (puts/calls), a manager's own vehicle, unmapped CUSIPs.
    """
    book: Dict[str, Dict] = {}
    for m in managers_data:
        excl = set(m.get("exclude") or [])
        merged: Dict[str, Dict] = {}
        for h in m.get("holdings", []):
            t = h.get("ticker")
            if not t or h.get("put_call") or t in excl:
                continue
            t = TICKER_MERGE.get(t, t)
            if t in merged:
                merged[t]["pct"] = round(merged[t]["pct"] + h["pct"], 2)
            else:
                merged[t] = dict(h, ticker=t)
        for t, h in merged.items():
            e = book.setdefault(t, {"ticker": t, "name": h["name"].title(),
                                    "points": 0.0, "held_by": []})
            pts = min(h["pct"], 25.0)
            e["points"] += pts
            e["held_by"].append({"key": m["key"], "person": m["person"],
                                 "pct": h["pct"]})
    out = sorted(book.values(), key=lambda e: -e["points"])
    for e in out:
        e["points"] = round(e["points"], 1)
        e["held_by"].sort(key=lambda x: -x["pct"])
    return out


def build_basket(scores: List[Dict]) -> List[Dict]:
    """Top conviction names -> suggested split of a dollar amount.

    A name qualifies if 2+ legends hold it, or one holds it at 5%+ of their
    book (a table-thumping single bet still counts). Split is proportional to
    conviction points, capped at BASKET_CAP per name, renormalised to 100%.
    """
    picks = [e for e in scores
             if len(e["held_by"]) >= 2 or e["held_by"][0]["pct"] >= 5.0][:BASKET_MAX]
    total_pts = sum(e["points"] for e in picks)
    if not total_pts:
        return []
    weights = [min(e["points"] / total_pts, BASKET_CAP) for e in picks]
    norm = sum(weights)
    out = []
    for e, w in zip(picks, weights):
        out.append({
            "ticker": e["ticker"], "name": e["name"],
            "weight": round(w / norm, 4),
            "points": e["points"],
            "held_by": e["held_by"],
        })
    return out


# ---------------------------------------------------------------------------
# Form 4 (insider) parsing — pure

def parse_form4(xml_text: str) -> List[Dict]:
    """Extract open-market purchases (transaction code P) from one Form 4."""
    owner = _tag(xml_text, "rptOwnerName").title()
    title = _tag(xml_text, "officerTitle") or (
        "Director" if "<isDirector>1" in xml_text or "<isDirector>true" in xml_text else "Insider")
    if title.lower().startswith("see remarks"):
        title = "Insider"
    buys = []
    for chunk in re.findall(
            r"<nonDerivativeTransaction>.*?</nonDerivativeTransaction>", xml_text, re.S):
        if _tag(chunk, "transactionCode") != "P":
            continue
        m_sh = re.search(r"<transactionShares>\s*<value>([\d.]+)</value>", chunk)
        m_px = re.search(r"<transactionPricePerShare>\s*<value>([\d.]+)</value>", chunk)
        m_ad = re.search(r"<transactionAcquiredDisposedCode>\s*<value>(\w)</value>", chunk)
        m_dt = re.search(r"<transactionDate>\s*<value>([\d-]+)</value>", chunk)
        if not (m_sh and m_px):
            continue
        if m_ad and m_ad.group(1) != "A":
            continue
        shares = float(m_sh.group(1))
        price = float(m_px.group(1))
        buys.append({
            "owner": owner, "title": title,
            "shares": round(shares), "price": round(price, 2),
            "value": round(shares * price),
            "date": m_dt.group(1) if m_dt else "",
        })
    return [b for b in buys if b["value"] >= MIN_INSIDER_USD]


# ---------------------------------------------------------------------------
# Summary for the buy meter

def activity_summary(all_changes: List[Dict], brk_cash_dir: str) -> Dict:
    """Net read across the roster's latest quarter: adding or pulling back?"""
    buys = sum(1 for c in all_changes if c["type"] in ("new", "added"))
    sells = sum(1 for c in all_changes if c["type"] in ("exit", "trimmed"))
    if buys >= sells * 1.5 and buys >= 3:
        net = "adding"
    elif sells >= buys * 1.5 and sells >= 3:
        net = "pulling_back"
    else:
        net = "mixed"
    return {"net_activity": net, "buys": buys, "sells": sells,
            "brk_cash_dir": brk_cash_dir}
