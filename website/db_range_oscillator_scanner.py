"""
RANGE OSCILLATOR (ZEIIERMAN) BREAKOUT SCANNER
==============================================
Scans all tickers in the prices DB for a fresh "strong" breakout on the
Range Oscillator (Zeiierman) — see range_oscillator.py for the shared
compute_range_oscillator() this is built on (ported from the TradingView
Pine source at scanners/range_oscillator.py).

The oscillator normally swings roughly -100..+100 as price drifts within
its own ATR-scaled range around a volatility-weighted moving average. A
reading beyond that band (close > ma + rangeATR, or close < ma - rangeATR)
is the indicator's own "strong bullish"/"strong bearish" override color —
a genuine break out of the stock's normal volatility envelope, not just a
strong trend. This scanner flags the first day a ticker crosses into that
state (both directions), then tracks how many subsequent days it's held.

Signal criteria:
  - Price >= $2.00  (filter out penny stocks)
  - Oscillator breakout ('up' or 'down') on a day within the last 15
    trading days
  - Must be the FIRST day of that breakout streak (previous day wasn't
    already in breakout the same direction) — keeps the scan to fresh
    extremes rather than re-flagging an extended move every day

Scoring (max ~9):
  - |osc| at signal >= 250 = +3, >= 150 = +2, else +1
    (always qualifies for at least +1 since a breakout implies |osc| > 100)
  - Volume > 20-day avg on signal day = +1
  - Days held +1 per subsequent day the breakout direction has persisted
    (max 5)

Usage:
    python db_range_oscillator_scanner.py
"""

import pandas as pd
import pymysql
import os
import sys
import json
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
from range_oscillator import compute_range_oscillator

RESULTS_FILE  = os.path.join(BASE_DIR, 'last_range_oscillator_results.json')
MAX_DAYS_BACK = 15   # how far back to look for a fresh breakout
MAX_HOLD_DAYS = 5    # cap on days-held bonus


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
    # like ^TNX) — a $0 close would otherwise divide-by-zero downstream.
    return df[(df[['open', 'high', 'low', 'close']] > 0).all(axis=1)]


def run_range_oscillator_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('RANGE OSCILLATOR (ZEIIERMAN) BREAKOUT SCANNER')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    cutoff = pd.Timestamp(datetime.now() - timedelta(days=MAX_DAYS_BACK * 2))

    conn = get_connection()
    tickers = get_all_tickers(conn)
    log(f"Scanning {len(tickers)} tickers...\n")

    all_results = []
    errors = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            df = get_ticker_daily(conn, ticker)
            if df is None or len(df) < 60:
                continue
            if df['close'].iloc[-1] < 2.0:
                continue

            osc_df = compute_range_oscillator(df['high'], df['low'], df['close'],
                                               skip_heatmap=True)
            dates    = df.index.tolist()
            closes   = df['close'].tolist()
            vols     = df['volume'].tolist()
            breakout = osc_df['breakout'].tolist()
            osc_vals = osc_df['osc'].tolist()

            current_price = closes[-1]
            avg_vol_20 = df['volume'].astype(float).rolling(20, min_periods=10).mean().tolist()

            for idx in range(len(dates)):
                if dates[idx] < cutoff:
                    continue

                direction = breakout[idx]
                if direction not in ('up', 'down'):
                    continue

                prev_direction = breakout[idx - 1] if idx > 0 else None
                if prev_direction == direction:
                    continue   # not the first day of this breakout streak

                osc_val = osc_vals[idx]
                if osc_val is None or pd.isna(osc_val):
                    continue

                # Days held: how many subsequent days the same-direction
                # breakout has persisted since the signal day.
                days_held = 0
                for j in range(idx + 1, min(idx + 1 + MAX_HOLD_DAYS, len(dates))):
                    if breakout[j] == direction:
                        days_held += 1
                    else:
                        break

                av20 = avg_vol_20[idx] if avg_vol_20[idx] else 0
                vol_surge = bool(av20 > 0 and vols[idx] > av20)

                score = 3 if abs(osc_val) >= 250 else (2 if abs(osc_val) >= 150 else 1)
                if vol_surge:
                    score += 1
                score += days_held

                gain_pct = (current_price - closes[idx]) / closes[idx] * 100

                all_results.append({
                    'ticker':        ticker,
                    'signal_date':   dates[idx].strftime('%Y-%m-%d'),
                    'direction':     'bullish' if direction == 'up' else 'bearish',
                    'osc':           round(float(osc_val), 1),
                    'vol_surge':     vol_surge,
                    'days_held':     days_held,
                    'current_price': round(float(current_price), 4),
                    'score':         score,
                    'gain_pct':      round(gain_pct, 2),
                })

                log(f"[{i}/{len(tickers)}] {ticker} {dates[idx].date()} "
                    f"{direction} osc {round(osc_val, 1)} score {score}")

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
    log(f"COMPLETE — {len(all_results)} breakout signals across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_range_oscillator_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_range_oscillator_scan()
