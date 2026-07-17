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
website/                        ← git repo root's website/ subfolder = live app on PythonAnywhere
  flask_app.py                  ← ~7500 lines, ALL routes, HTML, and logic in one file
  db_config.py                  ← MySQL creds + admin passwords + secrets (gitignored — never commit)
  db_daily_update.py            ← yfinance → MySQL price sync (reads CSV/5000.csv for ticker list)
  db_channel_scanner.py         ← EMA compression scanner (daily + weekly)
  db_price_channel_scanner.py   ← Ascending parallel price channel scanner
  db_fader_scanner.py           ← Dollar range zone + fader indicator scanner
  db_efi_scanner.py             ← Elder Force Index scanner
  db_wick_scanner.py            ← Weekly long lower wick scanner
  db_hammer_scanner.py          ← Daily hammer candlestick scanner
  db_marubozu_scanner.py        ← Daily bullish Marubozu candlestick scanner
  db_extreme_scanner.py         ← TD Buy/Sell setup count + ADX Momentum Warning scanner
  db_gapdown_scanner.py         ← 10%+ gap-down on above-avg volume, mean-reversion/gap-fill scanner
  EFI_Indicator.py              ← standalone indicator module used by db_efi_scanner.py
  range_oscillator.py           ← Range Oscillator (Zeiierman) Pine→Python port, not wired into any page yet
  db_picks.py                   ← Jimmy's Picks portfolio: buys, sells, history
  db_options_data.py            ← Options chain fetch/cache (on-demand lookup + open-position refresh)
  db_ask.py                     ← Member Q&A system (register, login, ask, answer)
  db_dividend.py                ← Dividend watchlist with per-stock thesis notes
  db_asx.py                     ← ASX 200 price data + ASX picks portfolio (separate `asx_prices` table)
  db_asx_update.py              ← ASX price update script
  templates/                    ← LightweightCharts HTML templates

  # Gitignored — server-side runtime state, never committed (see "Deployment" below):
  CSV/5000.csv                  ← US ticker master list (~3,400 active tickers), mutated by db_daily_update.py
  last_*_results.json           ← Cached scan outputs (one file per scanner)
  last_run.log                  ← Running job log (overwritten each run)
  last_refresh_date.txt         ← Last "Update US & ASX Prices" timestamp
  skip_tickers.txt              ← Auto-maintained list of delisted/no-data tickers
  deploy_log.txt                ← Output of the last git-pull auto-deploy
  uploads/                      ← TradingView screenshot uploads for Jimmy's Picks

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
| Extreme | db_extreme_scanner.py | Daily | TD Sequential-style setup count (fires at 8/9) OR ADX(8)/DI(8) momentum warning — either triggers, both shown for context, confluence bonus if same direction |
| Gap Down | db_gapdown_scanner.py | Daily | Open gapped down 10%+ vs prior close on above-average volume; scores on volume confirmation, intraday recovery, and days the gap-day low has held |

---

## Flask App Structure (flask_app.py)

The whole app is one big file (~7500 lines). All CSS, HTML, and route logic live
together — no Jinja templates for the main pages (except `templates/` for a couple
of standalone chart pages). Use the `# ─── Section ─────` markers to navigate.

- Lines 1–107:      imports, PythonAnywhere WSGI note, app init, BASE_DIR/REPO_DIR
- Lines 108–898:    global helpers — sector performance, DB helpers, job system, shared CSS/nav (incl. "Markets" dropdown)
- Lines 898–1102:   Dashboard (`/`)
- Lines 1102–1355:  Channel scanner + results
- Lines 1355–1587:  Chart page + chart data API + on-demand options chain lookup (`/api/options-lookup/<ticker>`)
- Lines 1587–1616:  Auth — `/login` (multi-password: ADMIN/JANG/HODAN), `/logout`
- Lines 1616–1836:  `/deploy-webhook` (auto-deploy), data actions (daily update, initial download), log view, status
- Lines 1836–2124:  Jimmy's Picks portfolio (buy/sell/image)
- Lines 2124–2569:  Options Picks + Options Tracker
- Lines 2569–2764:  Ask Jimmy Q&A
- Lines 2764–3024:  Range Level scanner
- Lines 3024–3525:  ASX 200
- Lines 3525–3811:  ASX Picks
- Lines 3811–4080:  Trade Journal
- Lines 4080–4983:  Fader, Wick, Hammer scanners
- Lines 4983–5343:  Gap Down scanner
- Lines 5343–5702:  Marubozu scanner
- Lines 5702–6073:  Extreme scanner (TD Buy/Sell + ADX Momentum Warning)
- Lines 6073–6469:  Price Channel scanner
- Lines 6469–6963:  Jang's Wicks
- Lines 6963–7273:  Semiconductors, EFI scanner
- Lines 7273–7768:  Indexes & ETFs (Dow/Nasdaq/S&P 500/Russell — all under the "Markets" nav dropdown now)
- Lines 7768–7871:  legacy options demo API (superseded by the on-demand lookup at line 1531)
- Lines 7871–8026:  Kids Corner (`/kids`) — candle-pattern learning page for beginners
- Lines 8026–8199:  How It Works
- Lines 8199–8593:  Dividend Picks
- Lines 8593–end:    Admin Analytics, Admin Hub (scanner buttons, job status, DB stats)

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
| `/marubozu` | Marubozu scanner results |
| `/extreme` | Extreme scanner results (TD Buy/Sell + ADX Momentum Warning) |
| `/gapdown` | Gap Down scanner results |
| `/kids` | Kids Corner — candle-pattern learning page (public) |
| `/picks` | Jimmy's Picks portfolio |
| `/asx-picks` | ASX picks portfolio |
| `/ask` | Member Q&A |
| `/dividend` | Dividend watchlist |
| `/chart/<ticker>` | Full-page TradingView chart, incl. "Look Up Options Chain" button |
| `/api/options-lookup/<ticker>` | JSON: live options chain for ticker (on-demand, all expirations), caches into `options_chain_snapshots` |
| `/api/us-chart/<ticker>` | JSON: OHLCV + EMA5 + EMA26 (used by inline charts) |
| `/api/channel-lines/<ticker>/<tf>` | JSON: channel trendline data for overlay |
| `/api/asx-chart/<ticker>` | JSON: ASX OHLCV + EMA5 + EMA26 |
| `/run-scan` | Trigger channel scan (admin) |
| `/run-fader` | Trigger fader scan (admin) |
| `/run-efi` | Trigger EFI scan (admin) |
| `/run-wick` | Trigger wick scan (admin) |
| `/run-gapdown` | Trigger Gap Down scan (admin) |
| `/run-hammer` | Trigger hammer scan (admin) |
| `/run-marubozu` | Trigger Marubozu scan (admin) |
| `/run-extreme` | Trigger Extreme scan (admin) |
| `/run-channels` | Trigger price channel scan (admin) |
| `/status` | JSON job status (used by UI polling) |
| `/deploy-webhook` | POST-only. GitHub push webhook — HMAC-verified, runs `git pull` + reload |

---

## Frontend

- Dark theme (#0a0c14 background, #60a5fa blue, #22c55e green, #ef4444 red)
- LightweightCharts v4.1.3 for candlestick charts (CDN loaded per page)
- Click any row in a scanner table → expands inline chart with EMA5/EMA26
- Charts use a custom `VerticalLine` primitive (paneViews → renderer → draw pattern — v4 API required)
- TradingView watchlist export on each scanner page (copy tickers as comma-separated list)
- Sortable columns on all scanner tables
- Top nav has a "Markets" dropdown (click-to-toggle, click-outside-to-close) folding in Indexes & ETFs,
  Nasdaq 100, Dow 30, S&P 500, Russell/Small Caps, and Semiconductors — highlights active if the
  current page is any of the six

---

## Deployment (git-based auto-deploy, set up 2026-07-04)

- Live app: `/home/JimmyTrader/JimmyTrader/website/` — a git clone of
  https://github.com/Jimmybubbles/JimmyTrader.git (username `JimmyTrader`)
- **To ship a change: just `git push origin main`.** GitHub webhook →
  `/deploy-webhook` (HMAC-verified via `GITHUB_WEBHOOK_SECRET`) → server runs
  `git pull origin main` → touches `WSGI_RELOAD_FILE`
  (`/var/www/jimmytrader_pythonanywhere_com_wsgi.py`) to reload. No more
  manual Files-tab uploads.
- `website/db_config.py` is gitignored (DB creds + `ADMIN_PASSWORD` +
  `JANG_PASSWORD` + `HODAN_PASSWORD` + `SECRET_KEY` + `GITHUB_WEBHOOK_SECRET`
  + `WSGI_RELOAD_FILE`) — never touched by `git pull`, must be edited
  directly on the server via Bash console if it changes.
- Several other files under `website/` are also gitignored because they're
  server-side runtime state that mutates on every run (see file tree above:
  `CSV/5000.csv`, `last_*_results.json`, `last_run.log`, `skip_tickers.txt`,
  `deploy_log.txt`, `uploads/`). **These must be manually present on the
  server** — if a fresh clone/migration is ever done again, copy them over
  from the previous deployment first, or scans/updates will silently find
  nothing (this exact bug happened right after the 2026-07-04 migration:
  `CSV/5000.csv` was missing, so `db_daily_update.py` had no tickers to
  refresh and `prices` went stale for the real US universe).
- Tracking any of these gitignored files by accident (e.g. `git add -A`)
  will make the *next* `git pull` refuse with "untracked working tree files
  would be overwritten by merge" (hit this with `EFI_Indicator.py`, which
  legitimately needed to be added to git since it's static code, not
  runtime state — fixed by `rm`-ing the stray copy on the server once).
- MySQL DB also on PythonAnywhere
- Admin login (`/login`) accepts any of `ADMIN_PASSWORD`, `JANG_PASSWORD`,
  `HODAN_PASSWORD` — all three grant identical full admin rights via
  `session['admin'] = True`; there's no per-user identity, just a shared
  password check. To add another person: add `<NAME>_PASSWORD` to
  `db_config.py` (locally + manually on the server first), add it to the
  `from db_config import (...)` line and the login route's password tuple,
  then push (but only after the server's `db_config.py` has the new
  constant, or the import crashes the site on deploy).
- All scan triggers are manual (admin clicks "Run X Scan")

---

## Indicators Used

- **EMA5 / EMA26** — displayed on all charts
- **HMA(8)** — Hull Moving Average, used in fader scanner
- **JMA(7,126,0.89)** — Jurik Moving Average, fader scanner
- **ATR(50)** — Average True Range, fader scanner
- **EFI** — Elder Force Index (force_index = (close - prev_close) × volume)
- **ROCWMA** — Rate of Change with WMA smoothing
- **TD Buy/Sell count** — simplified TD Sequential setup counter (Extreme scanner), fires at 8/9
- **ADX(8)/DI(8) Momentum Warning** — Extreme scanner; RMA approximated with EMA(span), same
  no-talib convention as ATR/EMA elsewhere

---

## Adding a New Scanner (Checklist)

1. Create `db_<name>_scanner.py` — follow `db_wick_scanner.py` or `db_hammer_scanner.py` as template
2. Add `from db_<name>_scanner import run_<name>_scan, load_last_<name>_results` to top of `flask_app.py`
3. Add `_run_<name>_scan_job()`, `start_<name>_scan()`, `@app.route('/run-<name>')`, `@app.route('/<name>')` functions
4. Add `<name>_btn = job_btn(...)` and `<name>_last = load_last_<name>_results()` in admin dashboard
5. Add button + scan_summary to admin scanners grid
6. Add results link to admin "Scanner Results & Tools" section
