# Project Overview — Stock Scanner Platform

Read this file to get up to speed on the codebase before asking questions or making changes.

---

## What This Is

A Flask web app (hosted on PythonAnywhere) for scanning US stocks using technical analysis.
James runs it as a subscription platform — members get "Jimmy's Picks" trade signals.
The admin dashboard lets him trigger scans, view results, and manage the portfolio.

---

## Key Directories

```
website/                        ← deploy this folder to PythonAnywhere
  flask_app.py                  ← ~6700 lines, ALL routes, HTML, and logic in one file
  db_config.py                  ← MySQL credentials (gitignored — never commit)
  db_daily_update.py            ← yfinance → MySQL price sync (scheduled task)
  db_channel_scanner.py         ← EMA compression scanner (daily + weekly)
  db_price_channel_scanner.py   ← Ascending parallel price channel scanner
  db_fader_scanner.py           ← Dollar range zone + fader indicator scanner
  db_efi_scanner.py             ← Elder Force Index scanner
  db_wick_scanner.py            ← Weekly long lower wick scanner
  db_hammer_scanner.py          ← Daily hammer candlestick scanner
  db_picks.py                   ← Jimmy's Picks portfolio: buys, sells, history
  db_ask.py                     ← Member Q&A system (register, login, ask, answer)
  db_dividend.py                ← Dividend watchlist with per-stock thesis notes
  db_asx.py                     ← ASX 200 price data + ASX picks portfolio
  db_asx_update.py              ← ASX price update script
  CSV/5000.csv                  ← US ticker master list (~3,400 active tickers)
  last_*_results.json           ← Cached scan outputs (one file per scanner)
  last_run.log                  ← Running job log (overwritten each run)
  skip_tickers.txt              ← Auto-maintained list of delisted/no-data tickers
  templates/                    ← LightweightCharts HTML templates

scanners/                       ← original standalone scripts (archive / dev reference)
archive/                        ← older experimental code
```

---

## Database

MySQL on PythonAnywhere.

Main table: `prices(ticker, date, open, high, low, close, volume)` — unique on (ticker, date).
All scanners read from this table. `db_daily_update.py` keeps it current via yfinance.

Other tables: `jimmy_picks`, `jimmy_trades`, `asx_picks`, `asx_trades`,
`ask_users`, `ask_questions`, `dividend_stocks`.

---

## Scanners — How They Work

Every scanner follows the same pattern:
1. Read all tickers from `prices` DB
2. Fetch daily OHLCV per ticker
3. Optionally resample to weekly (wick scanner does this)
4. Apply pattern detection criteria
5. Score signals
6. Save results to `last_<name>_results.json`
7. Flask route reads the JSON and renders an HTML table with clickable chart rows

### Scanner Summary

| Scanner | File | Timeframe | Signal |
|---------|------|-----------|--------|
| Channel | db_channel_scanner.py | Daily + Weekly | EMA(5)/EMA(26) compressed inside ATR(50)×0.4 |
| Price Channel | db_price_channel_scanner.py | Daily / Weekly / Monthly | Ascending parallel channel, price near lower line |
| Fader | db_fader_scanner.py | Daily | Channel + fader rising + price at 25% of dollar range |
| EFI | db_efi_scanner.py | Daily | Channel + Elder Force Index pulling back below zero |
| Wick | db_wick_scanner.py | Weekly | Long lower wick (2×+ body), close top 30%, scores weeks held |
| Hammer | db_hammer_scanner.py | Daily | Long lower wick (2×+ body), close top 50%, bullish body, vol surge bonus |
| Marubozu | db_marubozu_scanner.py | Daily | Body >= 75% of range, wicks <= 10%, bullish — clean momentum candle |

---

## Flask App Structure (flask_app.py)

The whole app is one big file (~6700 lines). All CSS, HTML, and route logic live
together — no Jinja templates for the main pages (except `templates/` for a couple
of standalone chart pages). Use the `# ─── Section ─────` markers to navigate.

- Lines ~1–80:    imports, PythonAnywhere WSGI note, app init
- Lines ~80–800:  global helpers — job system, DB stats, sparklines, sector ETFs
- Lines ~800–820: `page_wrap()` — the HTML shell every page returns
- Lines ~820–1600: dashboard (`/`), chart pages, chart data API
- Lines ~1600–2700: Jimmy's Picks portfolio, ASX portfolio, Q&A, dividend tab
- Lines ~2700–3500: range scanner, channel scanner results
- Lines ~3500–4200: Fader scanner
- Lines ~4200–4600: Wick scanner
- Lines ~4600–5100: Hammer scanner
- Lines ~5100–5700: EFI scanner, price channel scanner
- Lines ~5700–6700: Admin dashboard

### Key Helper Functions
- `page_wrap(title, active, content, auto_refresh=False)` — returns a full HTML page with nav and CSS
- `is_admin()` — checks session for admin role
- `get_log()` — reads last_run.log
- `start_script_job(script_path, label)` — launches a Python script as a daemon thread; only one job runs at a time
- `start_scan_job()` / `start_<name>_scan_job()` — same pattern for in-process scans
- `_job_running`, `_job_name`, `_job_lock` — global one-job-at-a-time state
- `scan_summary(last, results_url)` — renders last scan info card for admin dashboard
- `sparkline_svg(closes)` — tiny inline SVG line chart from a price list

### URL Structure
| URL | What it does |
|-----|-------------|
| `/` | Dashboard — portfolio summary, DB stats, sector heatmap |
| `/admin` | Admin dashboard — scan buttons, job status |
| `/results` | Channel scanner results table |
| `/channels` | Price channel scanner results |
| `/fader` | Fader scanner results |
| `/efi` | EFI scanner results |
| `/range` | Range level scanner |
| `/wick` | Wick scanner results |
| `/hammer` | Hammer scanner results |
| `/picks` | Jimmy's Picks portfolio |
| `/asx-picks` | ASX picks portfolio |
| `/ask` | Member Q&A |
| `/dividend` | Dividend watchlist |
| `/chart/<ticker>` | Full-page TradingView chart |
| `/api/us-chart/<ticker>` | JSON: OHLCV + EMA5 + EMA26 (used by inline charts) |
| `/api/channel-lines/<ticker>/<tf>` | JSON: channel trendline data for overlay |
| `/api/asx-chart/<ticker>` | JSON: ASX OHLCV + EMA5 + EMA26 |
| `/run-scan` | Trigger channel scan (admin) |
| `/run-fader` | Trigger fader scan (admin) |
| `/run-efi` | Trigger EFI scan (admin) |
| `/run-wick` | Trigger wick scan (admin) |
| `/run-hammer` | Trigger hammer scan (admin) |
| `/run-channels` | Trigger price channel scan (admin) |
| `/status` | JSON job status (used by UI polling) |

---

## Frontend

- Dark theme (#0a0c14 background, #60a5fa blue, #22c55e green, #ef4444 red)
- LightweightCharts v4.1.3 for candlestick charts (CDN loaded per page)
- Click any row in a scanner table → expands inline chart with EMA5/EMA26
- Charts use a custom `VerticalLine` primitive (paneViews → renderer → draw pattern — v4 API required)
- TradingView watchlist export on each scanner page (copy tickers as comma-separated list)
- Sortable columns on all scanner tables

---

## Deployment

- PythonAnywhere Flask app
- MySQL DB also on PythonAnywhere
- Daily price update runs via PythonAnywhere scheduled task
- All scan triggers are manual (admin clicks "Run X Scan")

---

## Indicators Used

- **EMA5 / EMA26** — displayed on all charts
- **HMA(8)** — Hull Moving Average, used in fader scanner
- **JMA(7,126,0.89)** — Jurik Moving Average, fader scanner
- **ATR(50)** — Average True Range, fader scanner
- **EFI** — Elder Force Index (force_index = (close - prev_close) × volume)
- **ROCWMA** — Rate of Change with WMA smoothing

---

## Adding a New Scanner (Checklist)

1. Create `db_<name>_scanner.py` — follow `db_wick_scanner.py` or `db_hammer_scanner.py` as template
2. Add `from db_<name>_scanner import run_<name>_scan, load_last_<name>_results` to top of `flask_app.py`
3. Add `_run_<name>_scan_job()`, `start_<name>_scan()`, `@app.route('/run-<name>')`, `@app.route('/<name>')` functions
4. Add `<name>_btn = job_btn(...)` and `<name>_last = load_last_<name>_results()` in admin dashboard
5. Add button + scan_summary to admin scanners grid
6. Add results link to admin "Scanner Results & Tools" section
