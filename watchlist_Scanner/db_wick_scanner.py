"""
WEEKLY WICK SCANNER
===================
Scans all tickers in the prices DB for weekly candles with long lower wicks
that have held — no subsequent candle has traded below the wick low.

Signal criteria:
  - Lower wick >= 2x body
  - Close in top 30% of the candle's total range
  - Upper wick <= 50% of lower wick (directional — not a spinning top)
  - Wick candle must be within the last 8 weeks

Scoring (max ~13):
  - Wick ratio   2x = 0, 3x = +1, 4x+ = +2
  - Close pos    top 20% of range = +1
  - Body size    body < 10% of total range (doji) = +1
  - Weeks held   +1 per subsequent weekly candle that has NOT breached the
                 wick low (max 8) — the longer it holds, the stronger the signal
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

RESULTS_FILE    = os.path.join(BASE_DIR, 'last_wick_results.json')
MAX_WEEKS_BACK  = 8   # how far back to look for wick candles
MAX_HOLD_WEEKS  = 8   # max bonus points for holding


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
    """Fetch full daily OHLCV for a ticker."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT date, open, high, low, close, volume
            FROM prices WHERE ticker = %s ORDER BY date ASC
        """, (ticker,))
        rows = cur.fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=['date','open','high','low','close','volume'])
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    for col in ['open','high','low','close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(int)
    return df.dropna(subset=['open','high','low','close'])


def to_weekly(df):
    """Resample daily OHLCV to weekly candles (week ending Friday)."""
    return df.resample('W-FRI').agg({
        'open':   'first',
        'high':   'max',
        'low':    'min',
        'close':  'last',
        'volume': 'sum',
    }).dropna(subset=['open','high','low','close'])


def score_candle(o, h, l, c):
    """
    Returns (passes, score, meta) for a single weekly candle.
    passes = True if it meets the base wick criteria.
    """
    total_range = h - l
    if total_range <= 0:
        return False, 0, {}

    body        = abs(c - o)
    body_bottom = min(o, c)
    body_top    = max(o, c)
    lower_wick  = body_bottom - l
    upper_wick  = h - body_top

    if lower_wick <= 0:
        return False, 0, {}

    # Wick ratio — handle doji (near-zero body)
    wick_ratio = lower_wick / body if body > 0 else lower_wick / (total_range * 0.01)

    # ── Base criteria ──────────────────────────────────────────
    if wick_ratio < 2.0:
        return False, 0, {}

    close_pct = (c - l) / total_range          # 0 = low, 1 = high
    if close_pct < 0.70:                        # close must be in top 30%
        return False, 0, {}

    if upper_wick > lower_wick * 0.5:           # upper wick must be small
        return False, 0, {}

    # ── Scoring ────────────────────────────────────────────────
    score = 0

    if wick_ratio >= 4.0:   score += 2
    elif wick_ratio >= 3.0: score += 1

    if close_pct >= 0.80:   score += 1          # close in top 20%

    if body <= total_range * 0.10: score += 1   # near-doji body

    meta = {
        'wick_ratio': round(wick_ratio, 1),
        'close_pct':  round(close_pct * 100, 1),
        'body_pct':   round((body / total_range) * 100, 1) if total_range else 0,
    }
    return True, score, meta


def run_wick_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('WEEKLY WICK SCANNER')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    cutoff = pd.Timestamp(datetime.now() - timedelta(weeks=MAX_WEEKS_BACK))

    conn = get_connection()
    tickers = get_all_tickers(conn)
    log(f"Scanning {len(tickers)} tickers...\n")

    all_results = []
    errors = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            df = get_ticker_daily(conn, ticker)
            if df is None or len(df) < 15:
                continue

            weekly = to_weekly(df)
            if len(weekly) < 3:
                continue

            dates  = weekly.index.tolist()
            opens  = weekly['open'].tolist()
            highs  = weekly['high'].tolist()
            lows   = weekly['low'].tolist()
            closes = weekly['close'].tolist()

            current_price = closes[-1]

            # Scan each week within the lookback window
            for idx in range(len(dates) - 1):
                if dates[idx] < cutoff:
                    continue

                passes, base_score, meta = score_candle(
                    opens[idx], highs[idx], lows[idx], closes[idx]
                )
                if not passes:
                    continue

                # Count subsequent weeks that held above the wick low
                wick_low = lows[idx]
                weeks_held = 0
                for j in range(idx + 1, min(idx + 1 + MAX_HOLD_WEEKS, len(dates))):
                    if lows[j] > wick_low:
                        weeks_held += 1
                    else:
                        break   # breached — stop counting

                total_score = base_score + weeks_held
                gain_pct    = (current_price - closes[idx]) / closes[idx] * 100

                all_results.append({
                    'ticker':        ticker,
                    'wick_date':     dates[idx].strftime('%Y-%m-%d'),
                    'wick_low':      round(float(wick_low), 4),
                    'close':         round(float(closes[idx]), 4),
                    'current_price': round(float(current_price), 4),
                    'wick_ratio':    meta['wick_ratio'],
                    'close_pct':     meta['close_pct'],
                    'body_pct':      meta['body_pct'],
                    'weeks_held':    weeks_held,
                    'score':         total_score,
                    'gain_pct':      round(gain_pct, 2),
                })

                log(f"[{i}/{len(tickers)}] {ticker} {dates[idx].date()} "
                    f"wick×{meta['wick_ratio']} held {weeks_held}w score {total_score}")

        except Exception as e:
            errors += 1
            if errors <= 10:
                log(f"[{i}/{len(tickers)}] {ticker}: ERROR — {str(e)[:60]}")

        # Reconnect every 300 tickers
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
    log(f"COMPLETE — {len(all_results)} wick signals found across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_wick_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_wick_scan()
