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
watchlist_Scanner/          ← Main Flask app (everything lives here)
  flask_app.py              ← ~5500+ lines, ALL routes, HTML, and logic in one file
  db_config.py              ← MySQL credentials (DB_HOST, DB_USER, etc.)
  db_daily_update.py        ← yfinance → MySQL price sync
  db_channel_scanner.py     ← Channel/EMA compression scanner
  db_fader_scanner.py       ← Dollar range zone + fader indicator scanner
  db_efi_scanner.py         ← Elder Force Index scanner
  db_wick_scanner.py        ← Weekly hammer/wick scanner (existing)
  db_hammer_scanner.py      ← Daily hammer candlestick scanner (new)
  db_picks.py               ← Jimmy's Picks portfolio: buys, sells, history
  db_ask.py                 ← Member Q&A system
  EFI_Indicator.py          ← Elder Force Index + Bollinger Bands
  ROCWMA_Indicator.py       ← Rate-of-Change WMA indicator
  PriceRangeZones.py        ← Dollar range level detection
  fader.py                  ← JMA + WMA chain (Jurik Moving Average)
  CSV/5000.csv              ← Master ticker list (~5000 US stocks)
  last_*_results.json       ← Cached scan outputs (one per scanner)
  scan_log.txt              ← Running job log
  buylist/                  ← Historical scan result files
  templates/                ← Chart HTML templates (LightweightCharts)
```

---

## Database

MySQL on PythonAnywhere.

Main table: `prices(ticker, date, open, high, low, close, volume)` — unique on (ticker, date).
All scanners read from this table. `db_daily_update.py` keeps it current via yfinance.

Other tables: `picks`, `trades`, `ask_users`, `ask_questions`, `asx_prices`.

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
| Channel | db_channel_scanner.py | Daily | EMA compression (price in tight range) |
| Fader | db_fader_scanner.py | Daily | Price at 25% of dollar range zone, fader rising |
| EFI | db_efi_scanner.py | Daily | Elder Force Index — oversold/momentum |
| Wick | db_wick_scanner.py | Weekly | Long lower wick (2×+ body), close in top 30%, scores weeks held |
| Hammer | db_hammer_scanner.py | Daily | Long lower wick (2×+ body), close in top 50%, bullish body, vol surge bonus |

### Hammer Scanner Criteria (daily candles, last 15 trading days)
- Lower wick >= 2× body
- Upper wick <= 30% of lower wick
- Close in top 50% of total range
- Body >= 3% of range (not a doji)

Scoring bonuses: wick 3×=+1, 4×+=+2 | close_pct >= 65%=+1 | bullish body=+1 | volume surge 20% above avg=+1 | days held (max 10)=+1 each

---

## Flask App Structure (flask_app.py)

- Lines ~1–100: imports, config, Flask app init, helper functions
- Lines ~100–1600: channel scanner page, price data routes, ASX routes
- Lines ~1600–3500: picks/portfolio, Jimmy's Picks, range scanner
- Lines ~3500–3870: Fader scanner
- Lines ~3870–4100: Wick scanner
- Lines ~4100–4500: Hammer scanner (NEW)
- Lines ~4500–5000: EFI scanner
- Lines ~5000–5600: Admin dashboard

### Key Helper Functions
- `page_wrap(title, active, content, auto_refresh=False)` — wraps content in site shell with nav
- `is_admin()` — checks session for admin role
- `get_log()` — reads scan_log.txt
- `_job_running`, `_job_name`, `_job_lock` — global job state (only one scan at a time)
- `scan_summary(last, results_url)` — renders last scan info for admin dashboard

### URL Structure
| URL | What it does |
|-----|-------------|
| `/` | Home / picks |
| `/admin` | Admin dashboard |
| `/results` | Channel scanner results |
| `/fader` | Fader scanner results |
| `/efi` | EFI scanner results |
| `/range` | Range level scanner |
| `/wick` | Wick scanner results |
| `/hammer` | Hammer scanner results (NEW) |
| `/run-wick` | Trigger wick scan (admin only) |
| `/run-hammer` | Trigger hammer scan (admin only) |
| `/api/us-chart/<ticker>` | JSON OHLCV + EMA5 + EMA26 for chart |

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
