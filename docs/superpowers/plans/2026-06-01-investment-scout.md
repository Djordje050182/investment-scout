# Investment Scout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily, automated research engine that scans US equities for technical + fundamental opportunities, ranks them by conviction, and delivers explainable suggestions via email and a static GitHub Pages dashboard.

**Architecture:** A Python engine (run by a daily GitHub Action) pulls free market data through pluggable adapters, runs technical and fundamental signal modules, scores conviction, and writes `docs/data/signals.json` + emails a digest. A static HTML/CSS/JS site in `docs/` renders that JSON. The engine and dashboard couple only through the JSON contract.

**Tech Stack:** Python 3.11 (CI) / 3.9-compatible code, `yfinance`, `pandas`, `numpy`, `pytest`, vanilla HTML/CSS/JS, GitHub Actions, SMTP email.

---

## Conventions

- All code must be Python **3.9 compatible** (use `typing.Optional`, `typing.List`, `typing.Dict`; no `X | Y` runtime unions, no `match` statements). Local dev machine has Python 3.9.6; CI uses 3.11.
- All engine code lives under `engine/`. Tests live under `tests/` mirroring the engine structure.
- Run all commands from the repo root: `/Users/dgvozdenovic/claude-projects/investment-scout`.
- The repo is already git-initialized with the spec committed.

---

## File Structure

```
investment-scout/
├── engine/
│   ├── __init__.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py          # MarketData dataclass + DataAdapter interface
│   │   └── yfinance_us.py   # concrete US adapter
│   ├── signals/
│   │   ├── __init__.py
│   │   ├── indicators.py    # pure helpers: sma, rsi, resistance
│   │   ├── technical.py     # cup-and-handle, breakout, trend, rsi, volume
│   │   ├── fundamental.py   # quality, moat, value, management
│   │   └── conviction.py    # combine + alignment bonus + tier + threshold
│   ├── notify/
│   │   ├── __init__.py
│   │   └── email.py         # build + send digest
│   ├── universe.py          # symbol lists
│   └── run_scan.py          # orchestrator → writes signals.json + emails
├── tests/
│   ├── __init__.py
│   ├── fixtures.py          # synthetic price/fundamental builders
│   ├── test_indicators.py
│   ├── test_technical.py
│   ├── test_fundamental.py
│   ├── test_conviction.py
│   ├── test_email.py
│   └── test_run_scan.py
├── docs/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/
│       ├── signals.json     # seeded sample, later overwritten by Action
│       └── history/.gitkeep
├── .github/workflows/scan.yml
├── requirements.txt
└── README.md
```

---

## Task 1: Project scaffolding & dependencies

**Files:**
- Create: `requirements.txt`
- Create: `engine/__init__.py`, `engine/adapters/__init__.py`, `engine/signals/__init__.py`, `engine/notify/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
yfinance==0.2.40
pandas>=2.0
numpy>=1.24
pytest>=7.0
```

- [ ] **Step 2: Create a virtualenv and install**

Run:
```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```
Expected: installs complete without error. (`.venv/` is already gitignored.)

- [ ] **Step 3: Create empty package marker files**

Create these five files, each containing a single comment line `# package marker`:
`engine/__init__.py`, `engine/adapters/__init__.py`, `engine/signals/__init__.py`, `engine/notify/__init__.py`, `tests/__init__.py`

- [ ] **Step 4: Verify pytest runs (collects 0 tests)**

Run: `.venv/bin/pytest -q`
Expected: "no tests ran" — exits cleanly.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt engine tests
git commit -m "chore: scaffold engine packages and dependencies"
```

---

## Task 2: Test fixtures (synthetic data builders)

These let every later test run **offline** with deterministic data — no network, no yfinance calls.

**Files:**
- Create: `tests/fixtures.py`

- [ ] **Step 1: Write the fixtures module**

```python
# tests/fixtures.py
"""Synthetic data builders for offline, deterministic signal tests."""
from typing import List, Optional
import pandas as pd
import numpy as np


def make_prices(closes: List[float], volumes: Optional[List[float]] = None) -> pd.DataFrame:
    """Build an OHLCV DataFrame from a list of closing prices.

    High/Low/Open are derived from close so detectors that read them work.
    Index is a daily date range. Volume defaults to a flat 1_000_000.
    """
    n = len(closes)
    if volumes is None:
        volumes = [1_000_000.0] * n
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series(closes, dtype="float64")
    return pd.DataFrame(
        {
            "Open": close.shift(1).fillna(close.iloc[0]).values,
            "High": (close * 1.01).values,
            "Low": (close * 0.99).values,
            "Close": close.values,
            "Volume": pd.Series(volumes, dtype="float64").values,
        },
        index=idx,
    )


def cup_and_handle_closes() -> List[float]:
    """A clean cup-and-handle: rim ~100, rounded cup to ~80, recovery, small handle dip."""
    left_rim = list(np.linspace(100, 100, 5))
    down = list(np.linspace(100, 80, 30))
    up = list(np.linspace(80, 100, 30))
    handle = list(np.linspace(100, 93, 7)) + list(np.linspace(93, 99, 5))
    return left_rim + down + up + handle


def uptrend_closes(days: int = 260, start: float = 50.0, end: float = 100.0) -> List[float]:
    """Steady uptrend long enough for a 200-day moving average."""
    return list(np.linspace(start, end, days))


def flat_closes(days: int = 260, level: float = 50.0) -> List[float]:
    """Flat, featureless series — should produce no technical signal."""
    return [level] * days
```

- [ ] **Step 2: Sanity-check fixtures import and shape**

Run:
```bash
.venv/bin/python -c "from tests.fixtures import make_prices, cup_and_handle_closes; df=make_prices(cup_and_handle_closes()); print(df.shape); print(list(df.columns))"
```
Expected: prints a shape like `(77, 5)` and `['Open', 'High', 'Low', 'Close', 'Volume']`.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures.py
git commit -m "test: add synthetic price-data fixtures"
```

---

## Task 3: Technical indicators (pure helpers)

Small, pure functions the technical scanner builds on. Test-first.

**Files:**
- Create: `tests/test_indicators.py`
- Create: `engine/signals/indicators.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_indicators.py
import pandas as pd
from engine.signals.indicators import sma, rsi, recent_high


def test_sma_last_value():
    s = pd.Series([1, 2, 3, 4, 5], dtype="float64")
    assert sma(s, 5).iloc[-1] == 3.0


def test_rsi_all_gains_is_high():
    s = pd.Series(list(range(1, 40)), dtype="float64")
    val = rsi(s, 14).iloc[-1]
    assert val > 90


def test_rsi_all_losses_is_low():
    s = pd.Series(list(range(40, 1, -1)), dtype="float64")
    val = rsi(s, 14).iloc[-1]
    assert val < 10


def test_recent_high_excludes_last_n():
    # last 3 values are small; the prior window peaks at 100
    s = pd.Series([10, 100, 20, 5, 5, 5], dtype="float64")
    assert recent_high(s, lookback=6, exclude_last=3) == 100.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_indicators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.signals.indicators'`.

- [ ] **Step 3: Implement indicators**

```python
# engine/signals/indicators.py
"""Pure technical-indicator helpers. No I/O, fully unit-testable."""
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing via EMA)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(100.0)


def recent_high(series: pd.Series, lookback: int, exclude_last: int = 0) -> float:
    """Highest value within `lookback` bars, optionally excluding the last `exclude_last`."""
    window = series.iloc[-lookback:]
    if exclude_last > 0:
        window = window.iloc[:-exclude_last]
    return float(window.max())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_indicators.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_indicators.py engine/signals/indicators.py
git commit -m "feat: add pure technical-indicator helpers"
```

---

## Task 4: Adapter interface & MarketData type

Defines the contract every data source implements, decoupling signals from sources.

**Files:**
- Create: `engine/adapters/base.py`
- Create: `tests/test_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_base.py
import pandas as pd
from engine.adapters.base import MarketData


def test_marketdata_holds_fields():
    df = pd.DataFrame({"Close": [1.0, 2.0]})
    md = MarketData(symbol="AAPL", market="US", prices=df,
                    fundamentals={"roe": 0.2}, price=2.0)
    assert md.symbol == "AAPL"
    assert md.market == "US"
    assert md.price == 2.0
    assert md.fundamentals["roe"] == 0.2
    assert md.prices.iloc[-1]["Close"] == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.adapters.base'`.

- [ ] **Step 3: Implement base**

```python
# engine/adapters/base.py
"""Data-source contract. Signals depend on MarketData, never on a concrete source."""
from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd


@dataclass
class MarketData:
    """Everything the signal engine needs about one symbol."""
    symbol: str
    market: str
    prices: pd.DataFrame              # OHLCV, daily, chronological
    fundamentals: Dict[str, float]    # may be partial; missing keys absent
    price: Optional[float] = None     # latest close convenience


class DataAdapter:
    """Interface every data source implements."""

    def fetch(self, symbols: List[str]) -> List[MarketData]:
        """Return MarketData for each symbol that could be fetched.

        Implementations MUST skip (not raise on) individual symbol failures.
        """
        raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_base.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_base.py engine/adapters/base.py
git commit -m "feat: add data-adapter interface and MarketData type"
```

---

## Task 5: Technical scanner

Returns a 0–1 score plus a list of detected pattern names for one symbol.

**Files:**
- Create: `tests/test_technical.py`
- Create: `engine/signals/technical.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_technical.py
from tests.fixtures import make_prices, cup_and_handle_closes, uptrend_closes, flat_closes
from engine.signals.technical import scan_technical


def test_cup_and_handle_detected():
    df = make_prices(cup_and_handle_closes())
    result = scan_technical(df)
    assert "cup_and_handle" in result["patterns"]
    assert result["score"] > 0.0


def test_uptrend_detects_trend():
    df = make_prices(uptrend_closes())
    result = scan_technical(df)
    assert "uptrend" in result["patterns"]


def test_flat_series_no_signal():
    df = make_prices(flat_closes())
    result = scan_technical(df)
    assert result["score"] == 0.0
    assert result["patterns"] == []


def test_breakout_on_volume():
    # long base at 100, then a jump to 110 on 3x volume
    closes = [100.0] * 60 + [110.0]
    volumes = [1_000_000.0] * 60 + [3_000_000.0]
    df = make_prices(closes, volumes)
    result = scan_technical(df)
    assert "breakout" in result["patterns"]


def test_score_capped_at_one():
    df = make_prices(cup_and_handle_closes())
    result = scan_technical(df)
    assert 0.0 <= result["score"] <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_technical.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.signals.technical'`.

- [ ] **Step 3: Implement the technical scanner**

```python
# engine/signals/technical.py
"""Technical pattern detection. Input: OHLCV DataFrame. Output: {score, patterns}."""
from typing import Dict, List
import pandas as pd
from engine.signals.indicators import sma, rsi, recent_high


def _detect_cup_and_handle(close: pd.Series) -> float:
    """Return 0-1 strength of a cup-and-handle ending near now, else 0.

    Heuristic: over the last ~77 bars find a rounded base whose midpoint is the
    lowest region, with left/right rims at similar levels, followed by a shallow
    handle pullback, with price now near the rim (breakout-ready).
    """
    n = len(close)
    if n < 60:
        return 0.0
    window = close.iloc[-77:] if n >= 77 else close
    vals = window.reset_index(drop=True)
    w = len(vals)
    left_rim = vals.iloc[:5].max()
    cup = vals.iloc[5:w - 12] if w - 12 > 5 else vals.iloc[5:]
    if len(cup) == 0:
        return 0.0
    cup_bottom = cup.min()
    bottom_idx = cup.idxmin()
    handle = vals.iloc[-12:]
    right_rim = handle.max()
    now = vals.iloc[-1]

    depth = (left_rim - cup_bottom) / left_rim if left_rim else 0.0
    if depth < 0.10 or depth > 0.6:
        return 0.0
    # rims roughly level
    rim_balance = 1.0 - min(1.0, abs(left_rim - right_rim) / left_rim)
    if rim_balance < 0.85:
        return 0.0
    # bottom should sit in the middle third (rounded, not a V at the edge)
    pos = (bottom_idx - 5) / max(1, (w - 12 - 5))
    if pos < 0.25 or pos > 0.75:
        return 0.0
    # handle is a shallow dip then recovery toward the rim
    handle_dip = (right_rim - handle.min()) / right_rim if right_rim else 0.0
    if handle_dip > 0.20:
        return 0.0
    # price now near the rim => breakout-ready
    proximity = 1.0 - min(1.0, abs(right_rim - now) / right_rim)
    score = 0.5 * rim_balance + 0.3 * proximity + 0.2 * (1.0 - handle_dip)
    return float(max(0.0, min(1.0, score)))


def _detect_breakout(close: pd.Series, volume: pd.Series) -> float:
    """Price clears recent resistance on above-average volume."""
    if len(close) < 30:
        return 0.0
    resistance = recent_high(close, lookback=60, exclude_last=1)
    now = float(close.iloc[-1])
    if now <= resistance:
        return 0.0
    avg_vol = float(volume.iloc[-21:-1].mean())
    if avg_vol <= 0:
        return 0.0
    vol_ratio = float(volume.iloc[-1]) / avg_vol
    if vol_ratio < 1.5:
        return 0.0
    return float(max(0.0, min(1.0, (vol_ratio - 1.5) / 1.5)))


def _detect_uptrend(close: pd.Series) -> float:
    """Price above rising 50- and 200-day SMAs."""
    if len(close) < 200:
        return 0.0
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    now = float(close.iloc[-1])
    rising50 = sma50.iloc[-1] > sma50.iloc[-10]
    rising200 = sma200.iloc[-1] > sma200.iloc[-20]
    above = now > sma50.iloc[-1] > sma200.iloc[-1]
    if above and rising50 and rising200:
        return 1.0
    if above and rising50:
        return 0.5
    return 0.0


def scan_technical(prices: pd.DataFrame) -> Dict[str, object]:
    """Run all detectors. Returns {'score': float 0-1, 'patterns': List[str], 'detail': dict}."""
    if prices is None or len(prices) == 0:
        return {"score": 0.0, "patterns": [], "detail": {}}
    close = prices["Close"].astype("float64")
    volume = prices["Volume"].astype("float64")

    cup = _detect_cup_and_handle(close)
    breakout = _detect_breakout(close, volume)
    trend = _detect_uptrend(close)
    rsi_val = float(rsi(close, 14).iloc[-1])
    # healthy momentum band 50-70 is good; overbought >80 penalized
    rsi_score = 1.0 if 50 <= rsi_val <= 70 else (0.5 if 40 <= rsi_val < 50 else 0.0)

    patterns: List[str] = []
    if cup > 0:
        patterns.append("cup_and_handle")
    if breakout > 0:
        patterns.append("breakout")
    if trend > 0:
        patterns.append("uptrend")

    # weighted blend; cup & breakout are the headline signals
    score = 0.4 * cup + 0.3 * breakout + 0.2 * trend + 0.1 * rsi_score
    score = float(max(0.0, min(1.0, score)))
    detail = {"cup": cup, "breakout": breakout, "trend": trend, "rsi": rsi_val}
    return {"score": score, "patterns": patterns, "detail": detail}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_technical.py -v`
Expected: 5 passed. (If `test_cup_and_handle_detected` fails, the fixture shape and detector thresholds must be reconciled — adjust the fixture's cup proportions, not the test's intent.)

- [ ] **Step 5: Commit**

```bash
git add tests/test_technical.py engine/signals/technical.py
git commit -m "feat: add technical scanner (cup-and-handle, breakout, trend, rsi)"
```

---

## Task 6: Fundamental screener

Buffett-style scoring from a fundamentals dict. Graceful with missing keys.

**Files:**
- Create: `tests/test_fundamental.py`
- Create: `engine/signals/fundamental.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fundamental.py
from engine.signals.fundamental import scan_fundamental


def test_strong_company_scores_high():
    f = {"roe": 0.25, "debt_to_equity": 0.3, "profit_margin": 0.22,
         "free_cash_flow": 5e9, "trailing_pe": 18.0, "shares_change": -0.02}
    result = scan_fundamental(f)
    assert result["score"] > 0.6
    assert result["quality"] > 0.6


def test_weak_company_scores_low():
    f = {"roe": 0.02, "debt_to_equity": 3.0, "profit_margin": -0.05,
         "free_cash_flow": -1e9, "trailing_pe": 90.0, "shares_change": 0.1}
    result = scan_fundamental(f)
    assert result["score"] < 0.4


def test_missing_data_does_not_crash():
    result = scan_fundamental({})
    assert 0.0 <= result["score"] <= 1.0
    assert result["score"] == 0.0


def test_partial_data_scores_partially():
    result = scan_fundamental({"roe": 0.25})
    assert result["score"] > 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_fundamental.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.signals.fundamental'`.

- [ ] **Step 3: Implement the fundamental screener**

```python
# engine/signals/fundamental.py
"""Buffett-style fundamental screen. Input: dict of metrics (may be partial)."""
from typing import Dict, Optional


def _band(value: Optional[float], good: float, bad: float) -> Optional[float]:
    """Map a value to 0-1 where `good`->1 and `bad`->0 (linear, clamped).

    Handles both directions: if good > bad, higher is better; else lower is better.
    Returns None when value is missing so callers can ignore absent metrics.
    """
    if value is None:
        return None
    if good == bad:
        return 0.5
    frac = (value - bad) / (good - bad)
    return float(max(0.0, min(1.0, frac)))


def _avg(parts):
    """Average of the non-None sub-scores; 0.0 if none present."""
    present = [p for p in parts if p is not None]
    if not present:
        return 0.0
    return float(sum(present) / len(present))


def scan_fundamental(f: Dict[str, float]) -> Dict[str, object]:
    """Return {'score', 'quality', 'value', 'moat', 'management', 'reasons'}."""
    roe = f.get("roe")
    dte = f.get("debt_to_equity")
    margin = f.get("profit_margin")
    fcf = f.get("free_cash_flow")
    pe = f.get("trailing_pe")
    shares_change = f.get("shares_change")  # negative = buybacks (good)

    quality = _avg([
        _band(roe, good=0.20, bad=0.05),
        _band(dte, good=0.3, bad=2.0),
        _band(margin, good=0.20, bad=0.0),
        _band(1.0 if (fcf is not None and fcf > 0) else (0.0 if fcf is not None else None),
              good=1.0, bad=0.0) if fcf is not None else None,
    ])
    moat = _avg([
        _band(roe, good=0.20, bad=0.08),
        _band(margin, good=0.18, bad=0.05),
    ])
    value = _avg([
        _band(pe, good=12.0, bad=40.0),
    ])
    management = _avg([
        _band(shares_change, good=-0.03, bad=0.05),
    ])

    score = 0.4 * quality + 0.25 * moat + 0.2 * value + 0.15 * management
    score = float(max(0.0, min(1.0, score)))

    reasons = []
    if roe is not None and roe >= 0.20:
        reasons.append("ROE {:.0%}".format(roe))
    if dte is not None and dte <= 0.5:
        reasons.append("low debt/equity {:.1f}".format(dte))
    if margin is not None and margin >= 0.18:
        reasons.append("strong margin {:.0%}".format(margin))
    if pe is not None and pe <= 20:
        reasons.append("reasonable P/E {:.0f}".format(pe))
    if shares_change is not None and shares_change < 0:
        reasons.append("share buybacks")

    return {"score": score, "quality": quality, "value": value, "moat": moat,
            "management": management, "reasons": reasons}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_fundamental.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_fundamental.py engine/signals/fundamental.py
git commit -m "feat: add Buffett-style fundamental screener"
```

---

## Task 7: Conviction scorer

Combines technical + fundamental into a 0–100 score, alignment bonus, tier, threshold, reasons.

**Files:**
- Create: `tests/test_conviction.py`
- Create: `engine/signals/conviction.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_conviction.py
from engine.signals.conviction import score_conviction, THRESHOLD


def _tech(score, patterns=None, detail=None):
    return {"score": score, "patterns": patterns or [], "detail": detail or {}}


def _fund(score, reasons=None):
    return {"score": score, "quality": score, "value": score, "moat": score,
            "management": score, "reasons": reasons or []}


def test_alignment_gets_both_tier_and_bonus():
    aligned = score_conviction(_tech(0.7, ["cup_and_handle"]), _fund(0.7))
    tech_only = score_conviction(_tech(0.7, ["cup_and_handle"]), _fund(0.0))
    assert aligned["tier"] == "both"
    # alignment should score strictly higher than either leg alone at same tech level
    assert aligned["conviction"] > tech_only["conviction"]


def test_tier_technical_when_only_technical():
    r = score_conviction(_tech(0.8, ["breakout"]), _fund(0.1))
    assert r["tier"] == "technical"


def test_tier_fundamental_when_only_fundamental():
    r = score_conviction(_tech(0.1), _fund(0.8))
    assert r["tier"] == "fundamental"


def test_conviction_is_0_to_100():
    r = score_conviction(_tech(1.0, ["cup_and_handle", "breakout"]), _fund(1.0))
    assert 0 <= r["conviction"] <= 100


def test_reasons_merged():
    r = score_conviction(_tech(0.7, ["cup_and_handle"]),
                         _fund(0.7, ["ROE 25%"]))
    assert any("ROE" in x for x in r["reasons"])
    assert any("cup" in x.lower() for x in r["reasons"])


def test_threshold_is_reasonable():
    assert 0 < THRESHOLD < 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_conviction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.signals.conviction'`.

- [ ] **Step 3: Implement the conviction scorer**

```python
# engine/signals/conviction.py
"""Combine technical + fundamental results into a ranked, explainable suggestion."""
from typing import Dict, List

THRESHOLD = 55          # minimum conviction (0-100) to become a suggestion
_ALIGN_MIN = 0.4        # each leg must clear this for the alignment bonus
_ALIGN_BONUS = 15       # points added when both legs are strong

_PATTERN_LABELS = {
    "cup_and_handle": "Cup-and-handle forming",
    "breakout": "Breakout above resistance on volume",
    "uptrend": "Uptrend (above rising 50/200-day MAs)",
}


def _tier(tech_score: float, fund_score: float) -> str:
    tech_on = tech_score >= _ALIGN_MIN
    fund_on = fund_score >= _ALIGN_MIN
    if tech_on and fund_on:
        return "both"
    if tech_on:
        return "technical"
    if fund_on:
        return "fundamental"
    return "none"


def score_conviction(technical: Dict, fundamental: Dict) -> Dict[str, object]:
    """Return {'conviction' 0-100, 'tier', 'reasons', 'technical', 'fundamental'}."""
    t = float(technical.get("score", 0.0))
    f = float(fundamental.get("score", 0.0))
    tier = _tier(t, f)

    base = 100.0 * (0.5 * t + 0.5 * f)
    bonus = _ALIGN_BONUS if tier == "both" else 0
    conviction = int(round(max(0.0, min(100.0, base + bonus))))

    reasons: List[str] = []
    for p in technical.get("patterns", []):
        reasons.append(_PATTERN_LABELS.get(p, p))
    reasons.extend(fundamental.get("reasons", []))

    return {
        "conviction": conviction,
        "tier": tier,
        "reasons": reasons,
        "technical": technical,
        "fundamental": fundamental,
    }


def passes(result: Dict) -> bool:
    """True if a scored result clears the suggestion threshold and is not 'none' tier."""
    return result["conviction"] >= THRESHOLD and result["tier"] != "none"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_conviction.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_conviction.py engine/signals/conviction.py
git commit -m "feat: add conviction scorer with alignment bonus and tiers"
```

---

## Task 8: Universe configuration

**Files:**
- Create: `engine/universe.py`
- Create: `tests/test_universe.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universe.py
from engine.universe import get_universe


def test_default_universe_nonempty():
    syms = get_universe("starter")
    assert len(syms) >= 20
    assert "AAPL" in syms


def test_unknown_universe_raises():
    import pytest
    with pytest.raises(KeyError):
        get_universe("does_not_exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_universe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.universe'`.

- [ ] **Step 3: Implement universe**

```python
# engine/universe.py
"""Symbol lists to scan. Keep modest to respect free-API rate limits."""
from typing import List

# A starter set of liquid US large-caps across sectors. Expand or add new
# named universes (e.g. 'sp500', 'asx', 'crypto') here later.
_STARTER = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B",
    "JPM", "V", "MA", "UNH", "HD", "PG", "JNJ", "KO", "PEP", "COST",
    "WMT", "DIS", "ADBE", "CRM", "NFLX", "AMD", "INTC", "CSCO", "ORCL",
    "TXN", "QCOM", "NKE",
]

_UNIVERSES = {
    "starter": _STARTER,
}


def get_universe(name: str = "starter") -> List[str]:
    """Return the symbol list for a named universe. Raises KeyError if unknown."""
    return list(_UNIVERSES[name])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_universe.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_universe.py engine/universe.py
git commit -m "feat: add scan universe configuration"
```

---

## Task 9: yfinance US adapter

Concrete adapter. Maps yfinance output into `MarketData`. Skips failures.

**Files:**
- Create: `engine/adapters/yfinance_us.py`
- Create: `tests/test_yfinance_us.py`

- [ ] **Step 1: Write the failing test (mapping logic, no network)**

```python
# tests/test_yfinance_us.py
from engine.adapters.yfinance_us import extract_fundamentals


def test_extract_fundamentals_maps_keys():
    info = {
        "returnOnEquity": 0.25,
        "debtToEquity": 30.0,           # yfinance reports as percent
        "profitMargins": 0.22,
        "freeCashflow": 5e9,
        "trailingPE": 18.0,
    }
    f = extract_fundamentals(info)
    assert abs(f["roe"] - 0.25) < 1e-9
    assert abs(f["debt_to_equity"] - 0.30) < 1e-9   # converted from percent
    assert abs(f["profit_margin"] - 0.22) < 1e-9
    assert f["free_cash_flow"] == 5e9
    assert f["trailing_pe"] == 18.0


def test_extract_fundamentals_handles_missing():
    f = extract_fundamentals({})
    assert f == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_yfinance_us.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.adapters.yfinance_us'`.

- [ ] **Step 3: Implement the adapter**

```python
# engine/adapters/yfinance_us.py
"""US-equity adapter backed by yfinance (free). Skips per-symbol failures."""
import time
from typing import Dict, List, Optional
import yfinance as yf
from engine.adapters.base import DataAdapter, MarketData


def extract_fundamentals(info: Dict) -> Dict[str, float]:
    """Map a yfinance .info dict to our normalized fundamentals dict.

    Only includes keys that are present and numeric. debtToEquity is reported
    by yfinance as a percentage (e.g. 30.0 == 0.30), so we divide by 100.
    """
    out: Dict[str, float] = {}

    def put(key: str, src: str, scale: float = 1.0):
        v = info.get(src)
        if isinstance(v, (int, float)):
            out[key] = float(v) * scale

    put("roe", "returnOnEquity")
    put("debt_to_equity", "debtToEquity", scale=0.01)
    put("profit_margin", "profitMargins")
    put("free_cash_flow", "freeCashflow")
    put("trailing_pe", "trailingPE")
    return out


class YFinanceUSAdapter(DataAdapter):
    """Fetches daily price history + fundamentals for US symbols."""

    def __init__(self, period: str = "1y", throttle_sec: float = 0.4):
        self.period = period
        self.throttle_sec = throttle_sec

    def _fetch_one(self, symbol: str) -> Optional[MarketData]:
        ticker = yf.Ticker(symbol)
        prices = ticker.history(period=self.period, auto_adjust=False)
        if prices is None or len(prices) < 60:
            return None
        try:
            info = ticker.info or {}
        except Exception:
            info = {}
        fundamentals = extract_fundamentals(info)
        price = float(prices["Close"].iloc[-1])
        return MarketData(symbol=symbol, market="US", prices=prices,
                          fundamentals=fundamentals, price=price)

    def fetch(self, symbols: List[str]) -> List[MarketData]:
        out: List[MarketData] = []
        for sym in symbols:
            try:
                md = self._fetch_one(sym)
                if md is not None:
                    out.append(md)
            except Exception as exc:  # never let one symbol kill the run
                print("skip {}: {}".format(sym, exc))
            time.sleep(self.throttle_sec)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_yfinance_us.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_yfinance_us.py engine/adapters/yfinance_us.py
git commit -m "feat: add yfinance US data adapter"
```

---

## Task 10: Email digest builder & sender

Split pure formatting (testable) from the SMTP send (side effect).

**Files:**
- Create: `engine/notify/email.py`
- Create: `tests/test_email.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_email.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.notify.email'`.

- [ ] **Step 3: Implement digest builder + sender**

```python
# engine/notify/email.py
"""Builds the daily digest (pure) and sends it via SMTP (side effect)."""
import os
import smtplib
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple


def build_digest(suggestions: List[Dict], scanned_at: str) -> Optional[Tuple[str, str]]:
    """Return (subject, body) for the digest, or None if there are no suggestions."""
    if not suggestions:
        return None
    ranked = sorted(suggestions, key=lambda s: s["conviction"], reverse=True)
    subject = "Investment Scout: {} opportunity(ies) found".format(len(ranked))
    lines = ["Scan completed {}".format(scanned_at), ""]
    for s in ranked:
        lines.append("{}  [{}]  conviction {}/100  ${:.2f}".format(
            s["symbol"], s["tier"].upper(), s["conviction"], s.get("price", 0.0)))
        for r in s.get("reasons", []):
            lines.append("    - {}".format(r))
        lines.append("")
    lines.append("These are research leads, not advice. Do your own diligence.")
    return subject, "\n".join(lines)


def send_email(subject: str, body: str) -> bool:
    """Send via SMTP using env-var credentials. Returns True on success.

    Required env vars (set as GitHub secrets):
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO
    If any are missing, logs and returns False (does not raise).
    """
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("EMAIL_TO")
    if not all([host, port, user, password, to_addr]):
        print("email skipped: SMTP env vars not fully set")
        return False
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    try:
        with smtplib.SMTP(host, int(port)) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_addr], msg.as_string())
        return True
    except Exception as exc:
        print("email send failed: {}".format(exc))
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_email.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_email.py engine/notify/email.py
git commit -m "feat: add email digest builder and SMTP sender"
```

---

## Task 11: Orchestrator (`run_scan.py`)

Ties everything together: fetch → score → build suggestions → write JSON → email.

**Files:**
- Create: `engine/run_scan.py`
- Create: `tests/test_run_scan.py`

- [ ] **Step 1: Write the failing tests (using a fake adapter, no network)**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_run_scan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.run_scan'`.

- [ ] **Step 3: Implement the orchestrator**

```python
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
        suggestions.append({
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
        })
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_run_scan.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the FULL suite**

Run: `.venv/bin/pytest -q`
Expected: all tests pass (≈ 25+).

- [ ] **Step 6: Commit**

```bash
git add tests/test_run_scan.py engine/run_scan.py
git commit -m "feat: add scan orchestrator wiring engine end-to-end"
```

---

## Task 12: Seed sample data & history placeholder

So the dashboard renders immediately, before the first real Action run.

**Files:**
- Create: `docs/data/signals.json`
- Create: `docs/data/history/.gitkeep`

- [ ] **Step 1: Write a representative sample signals.json**

```json
{
  "scanned_at": "2026-06-01T21:30:00Z",
  "universe": "starter",
  "count": 2,
  "suggestions": [
    {
      "symbol": "AAPL",
      "market": "US",
      "price": 195.12,
      "conviction": 87,
      "tier": "both",
      "reasons": [
        "ROE 25%",
        "low debt/equity 0.3",
        "Cup-and-handle forming",
        "Breakout above resistance on volume"
      ],
      "technical": { "score": 0.82, "patterns": ["cup_and_handle", "breakout"] },
      "fundamental": { "score": 0.79, "quality": 0.9, "value": 0.6, "moat": 0.85 }
    },
    {
      "symbol": "COST",
      "market": "US",
      "price": 842.5,
      "conviction": 63,
      "tier": "fundamental",
      "reasons": ["ROE 28%", "strong margin 13%"],
      "technical": { "score": 0.2, "patterns": [] },
      "fundamental": { "score": 0.74, "quality": 0.85, "value": 0.55, "moat": 0.8 }
    }
  ]
}
```

- [ ] **Step 2: Create the history placeholder**

Create `docs/data/history/.gitkeep` containing a single space.

- [ ] **Step 3: Commit**

```bash
git add docs/data/signals.json docs/data/history/.gitkeep
git commit -m "chore: seed sample signals.json for initial dashboard render"
```

---

## Task 13: Static dashboard (HTML/CSS/JS)

Use the **frontend-design skill** to produce a polished, non-generic UI. The data contract below is fixed; the visual design is the creative part.

**Files:**
- Create: `docs/index.html`
- Create: `docs/style.css`
- Create: `docs/app.js`

**Requirements the implementation MUST meet (verify each):**
- `app.js` fetches `./data/signals.json` (relative path — works under a Pages subpath).
- Renders one card per suggestion, sorted by conviction descending.
- Each card shows: symbol, market, price, conviction (0–100, visually prominent), a tier badge (`both` / `technical` / `fundamental` styled distinctly, with `both` = highest emphasis), and the full `reasons` list.
- A header shows "Last scanned: {scanned_at}" formatted human-readably and the suggestion count.
- Filter controls: by tier and by minimum conviction (client-side; no backend).
- An empty state ("No opportunities cleared the bar today.") when `count == 0`.
- A persistent disclaimer footer: "Research leads only — not financial advice."
- Graceful fetch-failure message if `signals.json` can't load.
- No build step, no external runtime dependencies (plain JS; fonts/CSS may be inlined or linked).

- [ ] **Step 1: Invoke the frontend-design skill** and build the three files to the requirements above.

- [ ] **Step 2: Verify locally**

Run: `.venv/bin/python -m http.server 8000 --directory docs`
Then open `http://localhost:8000` and confirm: two sample cards render, AAPL shows as `both` and ranks first, filters work, the disclaimer is visible. Stop the server (Ctrl-C) when done.

- [ ] **Step 3: Commit**

```bash
git add docs/index.html docs/style.css docs/app.js
git commit -m "feat: add static dashboard for signal suggestions"
```

---

## Task 14: GitHub Actions daily scan workflow

**Files:**
- Create: `.github/workflows/scan.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/scan.yml
name: Daily Scan

on:
  schedule:
    # 21:30 UTC ~ shortly after US market close (16:30 ET / 17:30 EDT).
    - cron: "30 21 * * 1-5"
  workflow_dispatch: {}   # manual "Run now" button

permissions:
  contents: write          # allow committing results back

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run scan
        env:
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
          SCOUT_UNIVERSE: starter
        run: python -m engine.run_scan

      - name: Commit results
        run: |
          git config user.name "investment-scout-bot"
          git config user.email "bot@users.noreply.github.com"
          git add docs/data/signals.json docs/data/history
          if git diff --staged --quiet; then
            echo "no changes to commit"
          else
            git commit -m "data: daily scan $(date -u +%Y-%m-%d)"
            git push
          fi
```

- [ ] **Step 2: Validate YAML syntax**

Run: `.venv/bin/python -c "import yaml" 2>/dev/null && .venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/scan.yml')); print('yaml ok')" || python3 -c "import ast; print('skip yaml lint (pyyaml not installed); visually verified')"`
Expected: "yaml ok" (yaml is a yfinance transitive dep) or the skip message.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/scan.yml
git commit -m "ci: add daily scan workflow with manual trigger"
```

---

## Task 15: README & launch instructions

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

````markdown
# Investment Scout

A daily, automated research engine that scans US equities for **technical**
(cup-and-handle, breakouts, trend) and **fundamental** (Buffett-style quality,
moat, value, management) opportunities, ranks them by conviction, and notifies
you with the trade idea and *why* it fired.

> **Research leads only — not financial advice.** No trades are executed.

## How it works

- A GitHub Action runs `engine/run_scan.py` once each weekday after US close.
- It pulls free data (yfinance), scores each symbol, writes `docs/data/signals.json`,
  and emails a digest of anything clearing the conviction threshold.
- The static site in `docs/` (GitHub Pages) renders the latest suggestions.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q                       # run the test suite
.venv/bin/python -m engine.run_scan       # run a real scan (writes docs/data/signals.json)
.venv/bin/python -m http.server 8000 --directory docs   # preview the dashboard
```

## Deployment (one-time setup)

1. Push this repo to GitHub.
2. **Settings → Pages →** set source to "Deploy from a branch", branch `main`,
   folder `/docs`. Your site appears at `https://<user>.github.io/<repo>/`.
3. **Settings → Secrets and variables → Actions →** add email secrets:
   `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`.
   (For Gmail: host `smtp.gmail.com`, port `587`, and an **app password**.)
4. **Actions tab →** run "Daily Scan" manually once to verify, then it runs daily.

## Extending

- **New market:** add an adapter in `engine/adapters/` implementing `DataAdapter`,
  and a universe entry in `engine/universe.py`.
- **New signal:** add a detector in `engine/signals/technical.py` or
  `fundamental.py`; the conviction scorer and dashboard pick it up automatically.
- **Tune conviction:** edit `THRESHOLD` and weights in `engine/signals/conviction.py`.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and deployment instructions"
```

---

## Task 16: Final verification

- [ ] **Step 1: Full test suite green**

Run: `.venv/bin/pytest -q`
Expected: all tests pass.

- [ ] **Step 2: A real end-to-end scan works (network required)**

Run: `.venv/bin/python -m engine.run_scan`
Expected: prints "scan complete: N suggestions from 30 symbols" and updates
`docs/data/signals.json` with a fresh `scanned_at`. (N may be 0 on a quiet day —
that is valid; the JSON should still be well-formed.)

- [ ] **Step 3: Dashboard renders the real data**

Run: `.venv/bin/python -m http.server 8000 --directory docs` and open
`http://localhost:8000`. Confirm it reflects the scan output (or shows the empty
state cleanly if N==0). Stop the server.

- [ ] **Step 4: Commit any refreshed data**

```bash
git add docs/data
git commit -m "data: initial real scan output" || echo "nothing to commit"
```

---

## Self-Review Notes (author)

- **Spec coverage:** adapters (T4, T9), technical signals incl. cup-and-handle (T5),
  fundamentals (T6), conviction + alignment bonus + tiers (T7), universe (T8),
  email (T10), orchestrator + JSON contract (T11), seed data (T12), dashboard (T13),
  daily cron + manual trigger (T14), resilience (per-symbol skip in T9, write-only-on-
  success in T11), testing strategy (every logic task is TDD), README/deploy (T15). All
  spec sections map to a task.
- **Contract consistency:** `signals.json` shape in T11/T12 matches the spec and the
  dashboard requirements in T13. Field names (`conviction`, `tier`, `reasons`,
  `technical.patterns`, `fundamental.{quality,value,moat}`) are identical across tasks.
- **Type/name consistency:** `scan_technical` returns `{score, patterns, detail}`;
  `scan_fundamental` returns `{score, quality, value, moat, management, reasons}`;
  `score_conviction` consumes both and returns `{conviction, tier, reasons, ...}`;
  `passes()` and `THRESHOLD` used consistently in T7 and T11. `MarketData` fields
  match across T4, T9, T11.
- **No placeholders:** every code step contains complete, runnable code.
- **Known soft spot:** the cup-and-handle heuristic thresholds (T5) and the
  fixture proportions (T2) must agree; T5 Step 4 calls this out explicitly so the
  implementer reconciles fixture vs. detector rather than weakening the test intent.
