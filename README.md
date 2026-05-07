# Jimmy Trader — Stock Scanner Platform

A Flask web app hosted on PythonAnywhere. James (JimmyTrader) runs it as a
subscription platform where members get trade signals and can track the
"Jimmy's Picks" model portfolio.

Live: **jimmytrader.pythonanywhere.com**

---

## What it does

- **Technical scanners** run across ~3,400 US stocks and flag setups based on
  price action, volume, and indicators. Results are stored as JSON and rendered
  in sortable tables with inline LightweightCharts v4 candlestick charts.
- **Jimmy's Picks** is a $100k paper portfolio — James logs buys and sells so
  members can copy-trade or follow along.
- **Ask Jimmy** is a member Q&A system — registered users submit ticker
  questions, James answers from the admin panel.
- **ASX section** covers Australian stocks (ASX 200) with the same picks /
  chart infrastructure.

---

## Scanners

| Scanner | Timeframe | What it looks for |
|---------|-----------|-------------------|
| Channel Finder | Daily + Weekly | EMA(5)/EMA(26) compressed inside ATR(50)×0.4 |
| Price Channel | Daily / Weekly / Monthly | Ascending parallel channel, price near lower line |
| Fader | Daily | Channel printing + fader rising + price at 25% of dollar range |
| EFI | Daily | Channel printing + Elder Force Index pullback below zero |
| Wick | Weekly | Long lower wick held for multiple weeks |
| Hammer | Daily | Long lower wick, bullish body, optional volume surge |

---

## Project layout

```
website/              ← deploy this folder to PythonAnywhere
  flask_app.py        ← main Flask app (all routes + HTML)
  db_config.py        ← MySQL credentials (gitignored — never commit)
  db_daily_update.py  ← yfinance → MySQL price sync (scheduled task)
  db_channel_scanner.py
  db_price_channel_scanner.py
  db_fader_scanner.py
  db_efi_scanner.py
  db_wick_scanner.py
  db_hammer_scanner.py
  db_picks.py         ← Jimmy's Picks portfolio DB operations
  db_ask.py           ← Member Q&A DB operations
  db_dividend.py      ← Dividend watchlist DB operations
  db_asx.py           ← ASX picks + chart data
  CSV/5000.csv        ← US ticker master list
  requirements.txt

scanners/             ← original standalone scripts (archive / dev reference)
archive/              ← older experimental code
```

---

## PythonAnywhere setup

1. Upload the `website/` folder to `/home/JimmyTrader/watchlist_Scanner/`
2. WSGI config (`/var/www/...wsgi.py`):
   ```python
   import sys
   sys.path.insert(0, '/home/JimmyTrader/watchlist_Scanner')
   from flask_app import app as application
   ```
3. Virtualenv: `/home/JimmyTrader/.virtualenvs/jimmyenv` — install `requirements.txt`
4. Scheduled task: `python /home/JimmyTrader/watchlist_Scanner/db_daily_update.py`
   runs daily after market close to keep the prices DB current.

---

## Database

MySQL on PythonAnywhere (`JimmyTrader$JimmyTrader`).

| Table | Purpose |
|-------|---------|
| `prices` | Daily OHLCV for all US tickers — unique on (ticker, date) |
| `asx_prices` | Daily OHLCV for ASX 200 tickers |
| `jimmy_account` | US paper account cash balance |
| `jimmy_picks` | US open positions |
| `jimmy_trades` | Full US trade history |
| `asx_account` | ASX paper account cash balance |
| `asx_picks` | ASX open positions |
| `asx_trades` | Full ASX trade history |
| `ask_users` | Member accounts (hashed passwords) |
| `ask_questions` | Q&A threads |
| `dividend_stocks` | Dividend watchlist with thesis notes |

---

## Tech stack

- Python 3.11 · Flask · pymysql · pandas · numpy · yfinance
- LightweightCharts v4.1.3 (CDN) for candlestick charts
- Dark theme UI — all CSS/HTML generated inline in `flask_app.py` (no template engine)
