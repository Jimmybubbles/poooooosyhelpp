"""
WEEKLY EXTREME-EXIT SCANNER (Range Oscillator cooling off)
=============================================================
Companion to db_range_oscillator_scanner.py (which flags a fresh breakout
STARTING) — this flags the opposite: a WEEKLY strong-bearish extreme that
has just STOPPED confirming, i.e. price closed below its normal volatility
range last week but is no longer doing so as of the most recent weekly bar.
Ported from the mirror "extreme ending" signal added to
weekly_bearish_marker.pine (the green exit line) — same
compute_range_oscillator() from range_oscillator.py, just resampled to
WEEKLY bars here (26-week lookback, ATR(2000 weeks) falling back to
ATR(200 weeks)) instead of daily, matching the Pine script's
request.security(..., 'W', ...) pull.

Only the bearish ("strong bearish"/red) exit is scanned, matching what was
asked for — the bullish breakout has the same shape and could be added the
same way later if wanted.

Signal criteria:
  - Price >= $2.00 (filter out penny stocks)
  - Enough weekly history for the 26-week weighted MA + ATR(200) fallback
    to be meaningful (>= 260 weeks, ~5 years)
  - The most recently CLOSED weekly bar was NOT a bearish breakout, but the
    weekly bar immediately before it WAS — i.e. the extreme just ended

Scoring (max ~6):
  - |osc| at the extreme week: >=250 = +3, >=150 = +2, else +1
  - Oscillator already climbing back up (not just barely exiting) = +2
  - Extreme was sustained 2+ weeks, not a single-week spike = +1

Usage:
    python db_extreme_exit_scanner.py
"""

import pandas as pd
import pymysql
import os
import sys
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
from range_oscillator import compute_range_oscillator
from db_price_channel_scanner import resample_weekly

RESULTS_FILE = os.path.join(BASE_DIR, 'last_extreme_exit_results.json')
MIN_WEEKS    = 260   # ~5 years — comfortably past ATR(200-week)'s own minimum runway


def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def get_all_tickers(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT ticker FROM prices ORDER BY ticker")
        return [row[0] for row in cur.fetchall()]


def get_ticker_daily(conn, ticker):
    """Fetch full daily OHLCV for a ticker, sorted oldest first."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT date, open, high, low, close, volume
            FROM prices WHERE ticker = %s ORDER BY date ASC
        """, (ticker,))
        rows = cur.fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(int)
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    # Drop degenerate zero/negative-price rows (bad data, e.g. index tickers
    # like ^TNX) — same guard as the other weekly scanners.
    return df[(df[['open', 'high', 'low', 'close']] > 0).all(axis=1)]


def run_extreme_exit_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('WEEKLY EXTREME-EXIT SCANNER (Range Oscillator cooling off)')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    conn = get_connection()
    tickers = get_all_tickers(conn)
    log(f"Scanning {len(tickers)} tickers...\n")

    all_results = []
    errors = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            df = get_ticker_daily(conn, ticker)
            if df is None or len(df) < 90:
                continue
            if df['close'].iloc[-1] < 2.0:
                continue

            weekly = resample_weekly(df)
            if len(weekly) < MIN_WEEKS:
                continue

            osc = compute_range_oscillator(weekly['high'], weekly['low'], weekly['close'],
                                            skip_heatmap=True)
            breakout = osc['breakout']

            prev_breakout = breakout.iloc[-2]
            cur_breakout  = breakout.iloc[-1]
            if prev_breakout != 'down' or cur_breakout == 'down':
                continue

            osc_prev = osc['osc'].iloc[-2]
            osc_cur  = osc['osc'].iloc[-1]
            if pd.isna(osc_prev):
                continue

            current_price = float(weekly['close'].iloc[-1])
            extreme_date  = weekly.index[-2].strftime('%Y-%m-%d')
            exit_date     = weekly.index[-1].strftime('%Y-%m-%d')
            week_low      = float(weekly['low'].iloc[-2])
            gain_pct      = (current_price - week_low) / week_low * 100 if week_low else 0.0

            climbing = (not pd.isna(osc_cur)) and osc_cur > osc_prev
            sustained = len(breakout) >= 3 and breakout.iloc[-3] == 'down'

            score = 3 if abs(osc_prev) >= 250 else (2 if abs(osc_prev) >= 150 else 1)
            if climbing:
                score += 2
            if sustained:
                score += 1

            all_results.append({
                'ticker':         ticker,
                'extreme_date':   extreme_date,
                'exit_date':      exit_date,
                'osc_at_extreme': round(float(osc_prev), 1),
                'osc_now':        round(float(osc_cur), 1) if not pd.isna(osc_cur) else None,
                'sustained':      sustained,
                'gain_pct':       round(gain_pct, 2),
                'current_price':  round(current_price, 4),
                'score':          score,
            })

            log(f"[{i}/{len(tickers)}] {ticker} extreme week {extreme_date} "
                f"(osc {round(osc_prev, 1)}) -> exited {exit_date} score {score}")

        except Exception as e:
            errors += 1
            if errors <= 10:
                log(f"[{i}/{len(tickers)}] {ticker}: ERROR — {str(e)[:60]}")

        # Reconnect every 300 tickers to avoid MySQL timeout on long scans
        if i % 300 == 0:
            conn.close()
            conn = get_connection()
            log(f"\n--- Reconnected at ticker {i} ---\n")

    conn.close()

    all_results.sort(key=lambda x: x['score'], reverse=True)

    output = {
        'scan_date':       datetime.now().strftime('%Y-%m-%d %H:%M'),
        'total':           len(all_results),
        'tickers_scanned': len(tickers),
        'errors':          errors,
        'results':         all_results,
    }

    with open(RESULTS_FILE, 'w') as f:
        json.dump(output, f)

    log(f"\n{'='*60}")
    log(f"COMPLETE — {len(all_results)} extreme-exit signals across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_extreme_exit_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_extreme_exit_scan()
