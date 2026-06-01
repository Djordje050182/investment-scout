# Investment Scout — Design Spec

**Date:** 2026-06-01
**Status:** Approved for planning

## Summary

Investment Scout is a daily, automated **research and idea-generation engine** for
investment opportunities. It scans a market universe once per day, detects
high-conviction setups using both **technical** and **fundamental** signal logic,
and notifies the user with each suggested trade and a plain-English explanation of
*why* it fired. It does **not** execute trades — it surfaces leads for the user to
research and act on themselves.

The system is hosted entirely for free: a scheduled GitHub Action runs the engine
and a static GitHub Pages site displays the results.

## Goals

- Scan a defined market universe daily and rank opportunities by conviction.
- Combine technical patterns (e.g. cup-and-handle, breakouts) with Buffett-style
  fundamental quality/value screening.
- Flag the highest-conviction opportunities as those where technical and
  fundamental signals **align**.
- Deliver suggestions via **email** and a hosted **web dashboard**.
- Make every suggestion fully explainable — no black box.
- Run entirely on free infrastructure and free data sources (for now).

## Non-Goals (YAGNI)

- **No automated trade execution.** No brokerage integration. Research only.
- **No real-time / intraday scanning.** Daily end-of-day cadence only.
- **No paid data** in this version (architecture must allow swapping it in later).
- **No user accounts / multi-user.** Single user (the owner).
- **No backend server / database.** Static hosting + scheduled job only.

## Constraints & Key Decisions

- **Hosting:** GitHub Pages (static only) + GitHub Actions (scheduled compute).
  This is free and requires no server. The engine cannot run "live" — it runs on a
  daily cron.
- **Data:** Free sources only (e.g. `yfinance`). Accept rate limits, narrower
  coverage, and imperfect/occasionally-stale fundamentals. Treat all output as
  research leads, never as gospel.
- **Universe:** Start modest (e.g. S&P 500 constituents) to stay within free
  rate limits. Source-agnostic design so ASX and crypto adapters can be added later
  as a config/adapter change.
- **Cadence:** One end-of-day scan per day, timed after US market close.

## Architecture

Two decoupled halves in one repo, sharing exactly **one contract**: the shape of
`signals.json`. Nothing else couples the engine to the dashboard, so either can be
changed independently (swap data sources, redesign UI).

```
investment-scout/
├── engine/                  # Python — runs in GitHub Actions only
│   ├── adapters/
│   │   ├── base.py          # interface every data adapter implements
│   │   ├── yfinance_us.py   # US equities (free) — first adapter
│   │   └── ...              # asx.py, crypto.py added later
│   ├── signals/
│   │   ├── technical.py     # cup-and-handle, breakout, MA, RSI, volume
│   │   ├── fundamental.py   # Buffett-style quality + value screen
│   │   └── conviction.py    # combines scores; flags technical∩fundamental alignment
│   ├── notify/email.py      # daily email digest
│   ├── universe.py          # symbol list to scan (config)
│   └── run_scan.py          # orchestrator
├── docs/                    # ← GitHub Pages serves THIS folder
│   ├── index.html
│   ├── app.js               # fetches data/signals.json, renders
│   ├── style.css
│   └── data/
│       ├── signals.json     # latest scan (committed by the Action)
│       └── history/         # dated snapshots — audit trail
└── .github/workflows/scan.yml   # daily cron + manual trigger
```

### Data flow

1. Daily cron fires the GitHub Action (after US close); also manually triggerable.
2. `run_scan.py` loads the universe and pulls price/volume + fundamentals via
   adapters (throttled batches, retries/backoff).
3. `technical.py` and `fundamental.py` each emit graded (0–1) sub-scores per symbol.
4. `conviction.py` combines them into a 0–100 score, applies an **alignment bonus**
   when both fire, tags each candidate `technical` / `fundamental` / `both`, and
   keeps only those above a configurable threshold.
5. `run_scan.py` writes `docs/data/signals.json`, archives a dated copy under
   `docs/data/history/`, and emails the digest if any suggestions exist.
6. The Action commits results back; GitHub Pages auto-publishes the updated site.

## Components

### Data adapters (`engine/adapters/`)
- `base.py` defines the interface (fetch price history, fetch fundamentals) that
  every source implements, so the signal engine never knows which source it's using.
- `yfinance_us.py` is the first concrete adapter (US equities, free).
- Adding ASX/crypto later = add a new adapter file + extend the universe.

### Technical scanner (`signals/technical.py`)
Needs only price/volume history. Each detector returns a 0–1 strength score:
- **Cup-and-handle:** rounded base (~7–65 weeks), smaller handle pullback, proximity
  to breakout point.
- **Breakout:** price clearing multi-week resistance on above-average volume.
- **Trend/MA:** price above rising 50- & 200-day MAs; golden-cross.
- **RSI:** healthy momentum vs. overbought.
- **Volume confirmation:** multiplier; weak-volume patterns score lower.

### Fundamental screener (`signals/fundamental.py`)
Buffett-style, using free financial data. Returns graded sub-scores:
- **Quality:** consistent high ROE, healthy margins, low debt/equity, positive FCF.
- **Moat proxy:** stable/expanding margins and ROE over multiple years.
- **Value:** reasonable P/E and P/FCF vs. its own history; rough margin-of-safety.
- **Management proxy:** sensible capital allocation (buybacks/debt paydown, not dilution).

### Conviction scorer (`signals/conviction.py`)
- Combines technical + fundamental into a transparent 0–100 score with a breakdown.
- **Alignment bonus** promotes symbols strong on both into a "High Conviction" tier.
- Applies the threshold; tags tier; attaches human-readable reasons to each suggestion.

### Notifications (`notify/email.py`)
- One email per scan, only when suggestions exist (no noise).
- Ranked picks with score, tier, and plain-English reasons.
- Free SMTP (Gmail app password) or free tier (e.g. Resend). Credentials stored as
  **GitHub repository secrets**, never in code.

### Dashboard (`docs/`)
- Plain HTML/CSS/JS, no build step. Fetches `signals.json` and renders.
- Suggestion cards sorted by conviction, expandable to full reasoning.
- Filters: market, tier, minimum score. "Last scanned" timestamp. History browsing.
- Built with care (frontend-design skill) to avoid generic AI aesthetics.

### Scheduling (`.github/workflows/scan.yml`)
- Daily cron after US market close; also manually triggerable from the Actions tab.
- Checks out repo, runs `run_scan.py`, commits updated JSON back.

## The `signals.json` contract

The single shared interface. Indicative shape:

```json
{
  "scanned_at": "2026-06-01T21:30:00Z",
  "universe": "sp500",
  "count": 3,
  "suggestions": [
    {
      "symbol": "AAPL",
      "market": "US",
      "conviction": 87,
      "tier": "both",
      "price": 195.12,
      "technical": { "score": 0.82, "patterns": ["cup_and_handle", "breakout"] },
      "fundamental": { "score": 0.79, "quality": 0.9, "value": 0.6, "moat": 0.85 },
      "reasons": [
        "ROE 22% sustained over 5yrs; D/E 0.3",
        "Cup-and-handle 94% formed, breakout on 1.8x avg volume"
      ]
    }
  ]
}
```

The dashboard depends only on this shape; the engine is free to change internally.

## Error handling & resilience

- Throttled batch fetching with retries/backoff against free-API rate limits.
- Per-symbol failures are skipped and logged — one bad ticker never kills the run.
- Missing fundamental fields are penalized/skipped gracefully, never crash.
- `signals.json` is overwritten **only** on a successful scan; worst case the site
  shows yesterday's data rather than breaking.

## Testing

- **Signal math** (cup-and-handle geometry, conviction scoring) — unit tested with
  known fixture data. This logic is the product; it gets the most coverage.
- **Adapters** — light tests with mocked API responses.
- **JSON contract** — a test asserting `run_scan.py` output matches the documented
  shape, protecting the engine↔dashboard interface.

## Future extensions (out of scope now, enabled by design)

- Add ASX and crypto via new adapters + universe entries.
- Swap in paid data by replacing/adding adapters (no dashboard change).
- Add Slack notifications alongside email.
- Move engine to a server for intraday cadence (dashboard unchanged).
