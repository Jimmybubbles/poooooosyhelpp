"""
WEEKLY SWING LOW SCANNER (Leviathan Swing Points)
==================================================
Finds tickers where a fresh "green dot" — a confirmed swing low pivot — is
printing on the weekly chart THIS WEEK. See swing_points.py for the shared
compute_swing_zones() this is built on (ported from the TradingView
"Swing Points and Liquidity - By Leviathan" Pine source at
Swing_indicator.py).

A swing low only becomes confirmed `right` weeks (default 10) after the
actual low bar — once that many weeks have passed with no lower low. This
scanner flags tickers where that confirmation lands on the current week,
i.e. the actual low happened 10 weeks ago and has just been validated as
a real pivot with nothing lower since.

Signal criteria:
  - Price >= $2.00 (filter out penny stocks)
  - Enough weekly history for the left+right lookback window
  - A swing low pivot (default left=15, right=10) confirms on the most
    recent weekly bar

Scoring (max ~8):
  - Bounce since the low: >=15% = +3, >=8% = +2, >=3% = +1
  - Zone still unfilled (price hasn't traded back down through the level
    since it confirmed) = +2 — the liquidity level is still "clean"
  - Volume on the pivot week > 10-week avg = +1

Usage:
    python db_swing_scanner.py
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
from swing_points import compute_swing_zones, DEFAULT_LEFT, DEFAULT_RIGHT
from db_price_channel_scanner import resample_weekly

RESULTS_FILE = os.path.join(BASE_DIR, 'last_swing_results.json')


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
    # like ^TNX) — a $0 low would otherwise divide-by-zero downstream.
    return df[(df[['open', 'high', 'low', 'close']] > 0).all(axis=1)]


def run_swing_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('WEEKLY SWING LOW SCANNER (Leviathan Swing Points)')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    min_weeks = DEFAULT_LEFT + DEFAULT_RIGHT + 5

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
            if len(weekly) < min_weeks:
                continue

            zones = compute_swing_zones(weekly)
            this_week = weekly.index[-1]
            current_price = float(weekly['close'].iloc[-1])

            fresh = [z for z in zones if z['type'] == 'low' and z['confirm_date'] == this_week]
            if not fresh:
                continue

            avg_vol_10 = weekly['volume'].astype(float).rolling(10, min_periods=5).mean()

            for z in fresh:
                pivot_price = z['pivot_price']
                bounce_pct = (current_price - pivot_price) / pivot_price * 100

                score = 3 if bounce_pct >= 15 else (2 if bounce_pct >= 8 else (1 if bounce_pct >= 3 else 0))
                if not z['filled']:
                    score += 2

                pivot_loc = weekly.index.get_loc(z['pivot_date'])
                vol_at_pivot = weekly['volume'].iloc[pivot_loc]
                avg_vol_at_pivot = avg_vol_10.iloc[pivot_loc]
                vol_surge = bool(avg_vol_at_pivot and avg_vol_at_pivot > 0
                                  and vol_at_pivot > avg_vol_at_pivot)
                if vol_surge:
                    score += 1

                all_results.append({
                    'ticker':        ticker,
                    'pivot_date':    z['pivot_date'].strftime('%Y-%m-%d'),
                    'confirm_date':  z['confirm_date'].strftime('%Y-%m-%d'),
                    'pivot_price':   round(pivot_price, 4),
                    'bounce_pct':    round(bounce_pct, 2),
                    'filled':        z['filled'],
                    'vol_surge':     vol_surge,
                    'current_price': round(current_price, 4),
                    'score':         score,
                })

                log(f"[{i}/{len(tickers)}] {ticker} pivot {z['pivot_date'].date()} "
                    f"confirmed {this_week.date()} bounce {round(bounce_pct, 2)}% score {score}")

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
    log(f"COMPLETE — {len(all_results)} fresh weekly swing lows across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_swing_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_swing_scan()
