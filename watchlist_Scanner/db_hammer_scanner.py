"""
DAILY HAMMER SCANNER
====================
Scans all tickers in the prices DB for daily hammer candlestick patterns.

A hammer is a bullish reversal signal: small body near the top of the range,
a long lower wick showing buyers stepped in and pushed price back up.

Signal criteria (all must pass):
  - Lower wick >= 2x body
  - Upper wick <= 30% of lower wick (directional — not a spinning top)
  - Close in top 50% of the candle's total range
  - Body >= 3% of total range (not a pure doji)
  - Hammer candle must be within the last 15 trading days

Scoring (max ~14):
  - Wick ratio   3x = +1, 4x+ = +2
  - Close pos    top 65%+ of range = +1
  - Bullish body (close > open) = +1
  - Volume       hammer-day volume > 20-day avg = +1
  - Days held    +1 per subsequent daily candle that has NOT breached the
                 hammer low (max 10) — the longer it holds, the stronger
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

RESULTS_FILE    = os.path.join(BASE_DIR, 'last_hammer_results.json')
MAX_DAYS_BACK   = 15   # how far back to look for hammer candles
MAX_HOLD_DAYS   = 10   # max bonus points for holding


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
    passes = True if it meets the hammer criteria.
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

    # Wick ratio — handle near-doji (very small body)
    wick_ratio = lower_wick / body if body > 0 else lower_wick / (total_range * 0.01)

    # ── Base criteria ──────────────────────────────────────────
    if wick_ratio < 2.0:
        return False, 0, {}

    close_pct = (c - l) / total_range          # 0 = low, 1 = high
    if close_pct < 0.50:                        # close must be in top half
        return False, 0, {}

    if upper_wick > lower_wick * 0.3:           # upper wick must be small
        return False, 0, {}

    body_pct = (body / total_range) * 100
    if body_pct < 3.0:                          # must have a real body (not pure doji)
        return False, 0, {}

    # ── Scoring ────────────────────────────────────────────────
    score = 0

    if wick_ratio >= 4.0:   score += 2
    elif wick_ratio >= 3.0: score += 1

    if close_pct >= 0.65:   score += 1          # close in top 35%

    if c > o:               score += 1          # bullish body (green candle)

    if avg_vol_20 > 0 and vol > avg_vol_20 * 1.2:
        score += 1                              # above-average volume confirmation

    meta = {
        'wick_ratio': round(wick_ratio, 1),
        'close_pct':  round(close_pct * 100, 1),
        'body_pct':   round(body_pct, 1),
        'bullish':    c > o,
        'vol_surge':  (avg_vol_20 > 0 and vol > avg_vol_20 * 1.2),
    }
    return True, score, meta


def run_hammer_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('DAILY HAMMER SCANNER')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Cut-off: only look at the last MAX_DAYS_BACK calendar days
    # We use calendar days so weekends/holidays are handled naturally
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

            # Pre-compute 20-day average volume for each index
            vol_series = df['volume'].astype(float)
            avg_vol_20 = vol_series.rolling(20, min_periods=10).mean().tolist()

            # Scan each trading day within the lookback window
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

                # Count subsequent days that held above the hammer low
                hammer_low = lows[idx]
                days_held = 0
                for j in range(idx + 1, min(idx + 1 + MAX_HOLD_DAYS, len(dates))):
                    if lows[j] > hammer_low:
                        days_held += 1
                    else:
                        break   # breached — stop counting

                total_score = base_score + days_held
                gain_pct    = (current_price - closes[idx]) / closes[idx] * 100

                all_results.append({
                    'ticker':        ticker,
                    'hammer_date':   dates[idx].strftime('%Y-%m-%d'),
                    'hammer_low':    round(float(hammer_low), 4),
                    'close':         round(float(closes[idx]), 4),
                    'current_price': round(float(current_price), 4),
                    'wick_ratio':    meta['wick_ratio'],
                    'close_pct':     meta['close_pct'],
                    'body_pct':      meta['body_pct'],
                    'bullish':       meta['bullish'],
                    'vol_surge':     meta['vol_surge'],
                    'days_held':     days_held,
                    'score':         total_score,
                    'gain_pct':      round(gain_pct, 2),
                })

                log(f"[{i}/{len(tickers)}] {ticker} {dates[idx].date()} "
                    f"wick×{meta['wick_ratio']} held {days_held}d score {total_score}")

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
    log(f"COMPLETE — {len(all_results)} hammer signals found across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_hammer_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_hammer_scan()
