"""
DAILY MARUBOZU SCANNER
======================
Scans all tickers in the prices DB for bullish Marubozu candlestick patterns
on the daily chart.

A Marubozu (Japanese: "close-cropped") is a candle where the body fills almost
the entire range — tiny or no wicks. On a bullish Marubozu, buyers controlled
the session from open to close without sellers pushing the price back. It signals
strong, clean momentum rather than a fight at the extremes.

Signal criteria (all must pass):
  - Close > Open  (bullish — green candle)
  - Body >= 75% of total range  (body dominates the candle)
  - Upper wick <= 10% of total range  (close near the high)
  - Lower wick <= 10% of total range  (open near the low)
  - Total range >= 0.4% of price  (avoids flat, near-zero range bars)
  - Price >= $2.00  (filter out penny stocks)
  - Candle must be within the last 15 trading days

Scoring (max ~10):
  - Body pct   >= 85% = +1, >= 92% = +2
  - Upper wick <  2% of range (essentially zero) = +1
  - Lower wick <  2% of range (essentially zero) = +1
  - Volume     > 20-day avg = +1
  - Days held  +1 per subsequent day that closes above the Marubozu open
               (max 5) — confirms buyers are still in control

Usage:
    python db_marubozu_scanner.py
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

RESULTS_FILE  = os.path.join(BASE_DIR, 'last_marubozu_results.json')
MAX_DAYS_BACK = 15   # how far back to look for Marubozu candles
MAX_HOLD_DAYS = 5    # max bonus points for days held


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


def score_candle(o, h, l, c, vol, avg_vol_20):
    """
    Returns (passes, score, meta) for a single daily candle.
    passes = True only if all Marubozu base criteria are met.
    """
    total_range = h - l
    if total_range <= 0:
        return False, 0, {}

    # Filter out penny stocks and near-flat bars
    if c < 2.0:
        return False, 0, {}
    if total_range / c < 0.004:   # range must be >= 0.4% of price
        return False, 0, {}

    # Bullish only
    if c <= o:
        return False, 0, {}

    body        = c - o
    upper_wick  = h - c   # gap between close and high
    lower_wick  = o - l   # gap between open and low

    body_pct        = body        / total_range * 100
    upper_wick_pct  = upper_wick  / total_range * 100
    lower_wick_pct  = lower_wick  / total_range * 100

    # ── Base criteria ───────────────────────────────────────────
    if body_pct       < 75.0:   return False, 0, {}
    if upper_wick_pct > 10.0:   return False, 0, {}
    if lower_wick_pct > 10.0:   return False, 0, {}

    # ── Scoring ─────────────────────────────────────────────────
    score = 0

    if body_pct >= 92.0:    score += 2
    elif body_pct >= 85.0:  score += 1

    if upper_wick_pct < 2.0:   score += 1   # close essentially == high
    if lower_wick_pct < 2.0:   score += 1   # open  essentially == low

    if avg_vol_20 > 0 and vol > avg_vol_20:
        score += 1

    meta = {
        'body_pct':       round(body_pct, 1),
        'upper_wick_pct': round(upper_wick_pct, 1),
        'lower_wick_pct': round(lower_wick_pct, 1),
        'vol_surge':      (avg_vol_20 > 0 and vol > avg_vol_20),
    }
    return True, score, meta


def run_marubozu_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('DAILY MARUBOZU SCANNER')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Use 2× calendar days to safely cover MAX_DAYS_BACK trading days
    cutoff = pd.Timestamp(datetime.now() - timedelta(days=MAX_DAYS_BACK * 2))

    conn = get_connection()
    tickers = get_all_tickers(conn)
    log(f"Scanning {len(tickers)} tickers...\n")

    all_results = []
    errors = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            df = get_ticker_daily(conn, ticker)
            if df is None or len(df) < 25:
                continue

            dates  = df.index.tolist()
            opens  = df['open'].tolist()
            highs  = df['high'].tolist()
            lows   = df['low'].tolist()
            closes = df['close'].tolist()
            vols   = df['volume'].tolist()

            current_price = closes[-1]

            # 20-day rolling average volume for each bar
            avg_vol_20 = df['volume'].astype(float).rolling(20, min_periods=10).mean().tolist()

            for idx in range(len(dates)):
                if dates[idx] < cutoff:
                    continue

                av20 = avg_vol_20[idx] if avg_vol_20[idx] else 0

                passes, base_score, meta = score_candle(
                    opens[idx], highs[idx], lows[idx], closes[idx],
                    vols[idx], av20
                )
                if not passes:
                    continue

                # Days held: count subsequent closes that stay above the Marubozu open.
                # Using the open as the "floor" — a close below open means sellers
                # have fully reversed the session's buying pressure.
                marubozu_open = opens[idx]
                days_held = 0
                for j in range(idx + 1, min(idx + 1 + MAX_HOLD_DAYS, len(dates))):
                    if closes[j] > marubozu_open:
                        days_held += 1
                    else:
                        break

                total_score = base_score + days_held
                gain_pct    = (current_price - closes[idx]) / closes[idx] * 100

                all_results.append({
                    'ticker':        ticker,
                    'marubozu_date': dates[idx].strftime('%Y-%m-%d'),
                    'open':          round(float(opens[idx]), 4),
                    'close':         round(float(closes[idx]), 4),
                    'current_price': round(float(current_price), 4),
                    'body_pct':      meta['body_pct'],
                    'upper_wick_pct': meta['upper_wick_pct'],
                    'lower_wick_pct': meta['lower_wick_pct'],
                    'vol_surge':     meta['vol_surge'],
                    'days_held':     days_held,
                    'score':         total_score,
                    'gain_pct':      round(gain_pct, 2),
                })

                log(f"[{i}/{len(tickers)}] {ticker} {dates[idx].date()} "
                    f"body {meta['body_pct']}% held {days_held}d score {total_score}")

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
    log(f"COMPLETE — {len(all_results)} Marubozu signals across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_marubozu_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_marubozu_scan()
