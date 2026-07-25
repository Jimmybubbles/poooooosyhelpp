"""
WEEKLY HIGHER-LOW SCANNER (Leviathan Swing Points)
====================================================
Finds a specific 3-dot swing-low shape on the weekly chart, built on top of
swing_points.compute_swing_zones() (see db_swing_scanner.py for the single-
dot "fresh green dot" scanner this extends):

    Dot A (green) --- Dot B (green, an OBVIOUS flush below A) --- Dot C (green, confirms ABOVE B)

i.e. three consecutive confirmed swing lows where the middle one dips
meaningfully below the one before it (a "flush"/stop-run), then the next
swing low confirms back above that flush — the classic "higher low"
continuation shape: one final shakeout under the prior low, then price
proves it was a spring by printing a new low that's actually higher.

Signal criteria:
  - Price >= $2.00 (filter out penny stocks)
  - Three consecutive confirmed weekly swing lows A, B, C where:
      B is at least MIN_FLUSH_PCT below A (an "obvious" flush, not noise)
      C is above B (the higher low)
  - C (the confirming dot) must have confirmed within the last
    RECENT_WEEKS weeks — keeps results to patterns that just played out,
    not ancient history

Scoring (max ~9):
  - Flush depth (B below A): >=8% = +3, >=5% = +2, >=3% = +1
  - Recovery strength (C above B): >=8% = +2, >=3% = +1
  - C also reclaims above A (full round-trip, not just a scrape above B) = +1
  - Volume on C's pivot week > 10-week avg = +1

Usage:
    python db_higher_low_scanner.py
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
from swing_points import compute_swing_zones, DEFAULT_LEFT, DEFAULT_RIGHT
from db_price_channel_scanner import resample_weekly

RESULTS_FILE   = os.path.join(BASE_DIR, 'last_higher_low_results.json')
MIN_FLUSH_PCT  = 3.0    # B must be at least this % below A to count as "obvious"
RECENT_WEEKS   = 12     # only report patterns where C confirmed within this many weeks


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
    return df.dropna(subset=['open', 'high', 'low', 'close'])


def find_higher_low_patterns(low_zones, min_flush_pct=MIN_FLUSH_PCT):
    """
    low_zones: list of swing-low zone dicts (type == 'low'), already sorted
    chronologically by confirm_date (compute_swing_zones does this).

    Returns a list of (A, B, C) triplets — every consecutive-dot window
    matching the higher-low shape, oldest to newest.
    """
    patterns = []
    for i in range(2, len(low_zones)):
        a, b, c = low_zones[i - 2], low_zones[i - 1], low_zones[i]
        flush_pct = (a['pivot_price'] - b['pivot_price']) / a['pivot_price'] * 100
        if flush_pct < min_flush_pct:
            continue
        if c['pivot_price'] <= b['pivot_price']:
            continue
        patterns.append((a, b, c))
    return patterns


def run_higher_low_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('WEEKLY HIGHER-LOW SCANNER (Leviathan Swing Points)')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    min_weeks = DEFAULT_LEFT + DEFAULT_RIGHT + 5
    recent_cutoff = pd.Timestamp(datetime.now() - timedelta(weeks=RECENT_WEEKS))

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
            low_zones = [z for z in zones if z['type'] == 'low']
            if len(low_zones) < 3:
                continue

            patterns = find_higher_low_patterns(low_zones)
            if not patterns:
                continue

            # Only the most recent qualifying pattern per ticker, and only
            # if it's actually recent (C confirmed within RECENT_WEEKS)
            a, b, c = patterns[-1]
            if c['confirm_date'] < recent_cutoff:
                continue

            current_price = float(weekly['close'].iloc[-1])
            flush_pct   = (a['pivot_price'] - b['pivot_price']) / a['pivot_price'] * 100
            recover_pct = (c['pivot_price'] - b['pivot_price']) / b['pivot_price'] * 100
            reclaimed_a = c['pivot_price'] > a['pivot_price']

            avg_vol_10 = weekly['volume'].astype(float).rolling(10, min_periods=5).mean()
            c_loc = weekly.index.get_loc(c['pivot_date'])
            vol_at_c = weekly['volume'].iloc[c_loc]
            avg_vol_at_c = avg_vol_10.iloc[c_loc]
            vol_surge = bool(avg_vol_at_c and avg_vol_at_c > 0 and vol_at_c > avg_vol_at_c)

            score = 3 if flush_pct >= 8 else (2 if flush_pct >= 5 else 1)
            score += 2 if recover_pct >= 8 else (1 if recover_pct >= 3 else 0)
            if reclaimed_a:
                score += 1
            if vol_surge:
                score += 1

            all_results.append({
                'ticker':         ticker,
                'a_date':         a['pivot_date'].strftime('%Y-%m-%d'),
                'a_price':        round(a['pivot_price'], 4),
                'b_date':         b['pivot_date'].strftime('%Y-%m-%d'),
                'b_price':        round(b['pivot_price'], 4),
                'c_date':         c['pivot_date'].strftime('%Y-%m-%d'),
                'c_confirm_date': c['confirm_date'].strftime('%Y-%m-%d'),
                'c_price':        round(c['pivot_price'], 4),
                'flush_pct':      round(flush_pct, 2),
                'recover_pct':    round(recover_pct, 2),
                'reclaimed_a':    reclaimed_a,
                'vol_surge':      vol_surge,
                'current_price':  round(current_price, 4),
                'score':          score,
            })

            log(f"[{i}/{len(tickers)}] {ticker} A {a['pivot_date'].date()}@{a['pivot_price']:.2f} "
                f"-> B {b['pivot_date'].date()}@{b['pivot_price']:.2f} (-{flush_pct:.1f}%) "
                f"-> C {c['pivot_date'].date()}@{c['pivot_price']:.2f} (+{recover_pct:.1f}%) score {score}")

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
    log(f"COMPLETE — {len(all_results)} higher-low patterns across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_higher_low_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_higher_low_scan()
