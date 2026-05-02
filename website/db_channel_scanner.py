"""
DB CHANNEL FINDER SCANNER
=========================
Same logic as ChannelFinderScanner.py but reads from MySQL DB
instead of CSV files. Uses pure pandas (no talib dependency).

Channel Detection:
  EMA(5) vs EMA(26) — channel when abs(EMA_fast - EMA_slow) < ATR(50) * 0.4
  At least 5 of last 10 bars must be in channel
  Checked on Daily and Weekly timeframes.
"""

import pandas as pd
import numpy as np
import pymysql
import os
import sys
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT

# Channel parameters
CHANNEL_EMA_FAST   = 5
CHANNEL_EMA_SLOW   = 26
CHANNEL_ATR_PERIOD = 50
CHANNEL_ATR_MULT   = 0.4
CHANNEL_BARS_NEEDED = 5
CHANNEL_LOOKBACK   = 10
MIN_DATA_ROWS      = 100

RESULTS_FILE = os.path.join(BASE_DIR, 'last_scan_results.json')

RESAMPLE_AGG = {
    'open':  'first',
    'high':  'max',
    'low':   'min',
    'close': 'last',
    'volume':'sum',
}


# ─── Indicators (pure pandas) ─────────────────────────────────────────────────

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calc_atr(high, low, close, period):
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def detect_channel(df):
    """Returns True if currently in a squeeze channel."""
    if len(df) < CHANNEL_ATR_PERIOD + CHANNEL_LOOKBACK:
        return False
    try:
        ema_fast = calc_ema(df['close'], CHANNEL_EMA_FAST)
        ema_slow = calc_ema(df['close'], CHANNEL_EMA_SLOW)
        atr      = calc_atr(df['high'], df['low'], df['close'], CHANNEL_ATR_PERIOD) * CHANNEL_ATR_MULT

        in_channel = (ema_fast - ema_slow).abs() < atr
        recent = in_channel.iloc[-CHANNEL_LOOKBACK:]
        return int(recent.sum()) >= CHANNEL_BARS_NEEDED
    except Exception:
        return False


# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, port=DB_PORT, charset='utf8mb4'
    )


def get_all_tickers(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT ticker FROM prices ORDER BY ticker")
        return [row[0] for row in cur.fetchall()]


def get_ticker_data(conn, ticker):
    """Fetch daily OHLCV for a ticker as a DataFrame indexed by date."""
    sql = """
        SELECT date, open, high, low, close, volume
        FROM prices
        WHERE ticker = %s
        ORDER BY date ASC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (ticker,))
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
    return df


# ─── Scanner ──────────────────────────────────────────────────────────────────

def scan_ticker(conn, ticker):
    df = get_ticker_data(conn, ticker)
    if df is None or len(df) < MIN_DATA_ROWS:
        return None

    current_price = float(df['close'].iloc[-1])
    if current_price <= 0:
        return None

    daily_channel = detect_channel(df)

    weekly_df = df.resample('W').agg(RESAMPLE_AGG).dropna()
    weekly_channel = detect_channel(weekly_df) if len(weekly_df) >= 60 else False

    score = int(daily_channel) + int(weekly_channel)
    if score < 1:
        return None

    return {
        'ticker':  ticker,
        'price':   round(current_price, 4),
        'score':   score,
        'label':   'BOTH' if score == 2 else 'SINGLE',
        'daily':   bool(daily_channel),
        'weekly':  bool(weekly_channel),
    }


def run_scan(log_callback=None):
    """
    Run the full channel scan across all tickers in the DB.
    Returns list of result dicts sorted by score desc.
    Optionally calls log_callback(str) for progress updates.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    log(f"Channel Finder Scan started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    conn = get_connection()
    tickers = get_all_tickers(conn)
    log(f"Scanning {len(tickers)} tickers...\n")

    results = []
    for i, ticker in enumerate(tickers, 1):
        try:
            result = scan_ticker(conn, ticker)
            if result:
                results.append(result)
        except Exception as e:
            pass

        if i % 500 == 0:
            log(f"  Progress: {i}/{len(tickers)} — found {len(results)} so far\n")

        # Reconnect every 1000 tickers
        if i % 1000 == 0:
            conn.close()
            conn = get_connection()

    conn.close()

    results.sort(key=lambda x: (-x['score'], x['ticker']))

    both   = sum(1 for r in results if r['score'] == 2)
    single = sum(1 for r in results if r['score'] == 1)

    log(f"\nScan complete: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    log(f"Total setups:   {len(results)}\n")
    log(f"  BOTH (2/2):   {both}\n")
    log(f"  SINGLE (1/2): {single}\n")

    # Save results to file
    payload = {
        'scan_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(results),
        'both': both,
        'single': single,
        'results': results,
    }
    with open(RESULTS_FILE, 'w') as f:
        json.dump(payload, f)

    return results


def load_last_results():
    """Load the last scan results from file."""
    if not os.path.exists(RESULTS_FILE):
        return None
    try:
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return None


if __name__ == '__main__':
    run_scan(log_callback=print)
