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
