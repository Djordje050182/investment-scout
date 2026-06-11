# Investment Scout

A daily, automated research engine that scans **US, ASX, and crypto** markets
with **12 technical pattern detectors** (cup-and-handle, breakout, bull flag,
double bottom, golden cross, Bollinger squeeze, pullback-to-trend, OBV
accumulation, and more) and a **Buffett-style fundamental screen** (quality,
moat, value, management). Every lead gets a 0–100 conviction score, a full
indicator snapshot (RSI, MACD, ADX, ATR, stochastics, relative returns), and
an **ATR-based trade plan** (entry / stop / targets / R:R).

The dashboard is a dark terminal-style site with real candlestick charts,
a live ticker tape, market-regime and breadth readouts, a near-miss radar,
and **live crypto prices streamed from Binance** in the browser.

> **Research leads only — not financial advice.** No trades are executed.

## How it works

- A GitHub Action runs `engine/run_scan.py` once each weekday after US close.
  It pulls free data (yfinance), runs every detector, scores conviction,
  writes `docs/data/signals.json` (signals + radar + movers + market regime +
  embedded chart data), and emails a digest of anything clearing the bar.
- A second Action (`quotes.yml`) refreshes `docs/data/quotes.json` every
  30 minutes during US market hours, so equity prices on the dashboard stay
  near-live between scans.
- In the browser, crypto prices stream in real time over Binance's public
  WebSocket, and the crypto Fear & Greed index comes from alternative.me.
- `engine/track_record.py` (run daily after the scan) scores every past lead
  against what price actually did — forward returns and stop/target resolution
  — and feeds the dashboard's Track Record panel.
- `engine/backtest.py` is a walk-forward backtest of all detectors (run
  manually: `SCOUT_BT_YEARS=8 python -m engine.backtest`); its output powers
  the Detector Edge panel.
- Leads reporting earnings within 21 days carry a warning chip; every lead
  shows relative strength vs its market benchmark (SPY / ASX 200 / BTC).
- A star on any signal pins it to a localStorage watchlist that tracks the
  price since you starred it.
- The static site in `docs/` (GitHub Pages) renders all of it. Candlestick
  charts use TradingView's lightweight-charts via CDN.

## Engine layout

```
engine/
  run_scan.py            orchestrator: fetch -> score -> signals.json -> email
  refresh_quotes.py      intraday quote refresh (quotes.json)
  track_record.py        score past leads vs forward returns (track_record.json)
  backtest.py            walk-forward detector backtest (backtest.json)
  universe.py            symbol lists (us / asx / crypto / all)
  adapters/              data sources (yfinance)
  signals/
    indicators.py        pure indicator math (SMA/EMA/RSI/MACD/ATR/ADX/OBV/BB/...)
    technical.py         12 pattern detectors + setup/trend/momentum/volume blend
    fundamental.py       Buffett-style screen
    conviction.py        technical+fundamental -> 0-100 conviction + tier
    trade_plan.py        ATR/structure-based entry, stop, targets, R:R
    regime.py            benchmark trends + universe breadth -> market regime
    scores.py            company backing & strength scores
    explain.py           plain-English "why it surfaced"
  notify/email.py        SMTP digest
```

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q                       # run the test suite
.venv/bin/python -m engine.run_scan       # run a real scan (writes docs/data/signals.json)
.venv/bin/python -m engine.refresh_quotes # refresh intraday quotes only
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

- **New market / symbols:** edit the lists in `engine/universe.py` (named
  universes: `us`, `asx`, `crypto`, `all`). The daily Action scans `all`.
- **New signal:** add a detector function in `engine/signals/technical.py` and
  register it in `_DETECTORS`; the scorer, dashboard, and email pick it up
  automatically. Give it a label in `conviction.py` and `app.js`.
- **Tune conviction:** `THRESHOLD` and weights in `engine/signals/conviction.py`;
  sub-score weights at the bottom of `technical.py`; the radar floor
  (`RADAR_MIN`) in `run_scan.py`.
- **Tune trade plans:** ATR multiples and stop logic in `engine/signals/trade_plan.py`.
