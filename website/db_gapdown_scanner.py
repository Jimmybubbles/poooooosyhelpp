"""
GAP DOWN SCANNER
================
Scans all tickers in the prices DB for daily gap-downs of 10%+ (today's open
vs. prior day's close), looking for potential mean-reversion / gap-fill
candidates. Unlike the compression-based scanners (Channel, Fader, EFI),
these are usually news/event-driven moves, so scoring leans on volume
confirmation and whether the stock has actually started to hold/reclaim
ground since the gap rather than assuming reversion is automatic.

Signal criteria (all must pass):
  - Gap = (open - prior_close) / prior_close <= -10%
  - Prior close >= $2 and prior-day volume >= 200,000 shares (liquidity filter,
    avoids penny-stock/illiquid noise gaps)
  - Gap day must be within the last 15 trading days

Scoring (max ~7 base + up to 10 hold-days bonus):
  - Gap size       -10% to -15% = +1, -15% to -25% = +2, beyond -25% = +3
  - Volume surge    gap-day volume > 1.5x 20-day avg = +1
  - Recovered intraday (closed above the gap open, i.e. not straight down) = +1
  - Closed in upper 40% of the gap day's range = +1
  - Currently above the gap-day close (reversion already underway) = +1
  - Days held       +1 per subsequent daily candle that has NOT broken below
                    the gap-day low (max 10) — hasn't made a new low since
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

RESULTS_FILE     = os.path.join(BASE_DIR, 'last_gapdown_results.json')
MAX_DAYS_BACK    = 15        # how far back to look for gap-down days
MAX_HOLD_DAYS    = 10        # max bonus points for holding above the gap low
MIN_GAP_PCT      = -10.0     # must gap down at least this much
MIN_PRIOR_PRICE  = 2.0       # liquidity filter
MIN_PRIOR_VOLUME = 200_000   # liquidity filter


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


def score_gap(prior_close, prior_vol, gap_open, gap_high, gap_low, gap_close, gap_vol, avg_vol_20):
    """Returns (passes, score, meta) for a single gap-down day."""
    if prior_close < MIN_PRIOR_PRICE or prior_vol < MIN_PRIOR_VOLUME:
        return False, 0, {}

    gap_pct = (gap_open - prior_close) / prior_close * 100
    if gap_pct > MIN_GAP_PCT:
        return False, 0, {}

    total_range = gap_high - gap_low
    close_pct = ((gap_close - gap_low) / total_range * 100) if total_range > 0 else 50.0
    vol_surge = avg_vol_20 > 0 and gap_vol > avg_vol_20 * 1.5
    recovered_intraday = gap_close > gap_open

    score = 0
    if gap_pct <= -25:   score += 3
    elif gap_pct <= -15: score += 2
    else:                score += 1

    if vol_surge:            score += 1
    if recovered_intraday:   score += 1
    if close_pct >= 60:      score += 1

    meta = {
        'gap_pct':             round(gap_pct, 2),
        'close_pct':           round(close_pct, 1),
        'vol_surge':           vol_surge,
        'recovered_intraday':  recovered_intraday,
    }
    return True, score, meta


def run_gapdown_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('GAP DOWN SCANNER')
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
            if df is None or len(df) < 25:
                continue

            dates  = df.index.tolist()
            opens  = df['open'].tolist()
            highs  = df['high'].tolist()
            lows   = df['low'].tolist()
            closes = df['close'].tolist()
            vols   = df['volume'].tolist()

            current_price = closes[-1]

            vol_series = df['volume'].astype(float)
            avg_vol_20 = vol_series.rolling(20, min_periods=10).mean().tolist()

            for idx in range(1, len(dates)):
                if dates[idx] < cutoff:
                    continue

                av20 = avg_vol_20[idx] if avg_vol_20[idx] else 0
                prior_close = closes[idx - 1]
                prior_vol   = vols[idx - 1]

                passes, base_score, meta = score_gap(
                    prior_close, prior_vol,
                    opens[idx], highs[idx], lows[idx], closes[idx],
                    vols[idx], av20
                )
                if not passes:
                    continue

                gap_low = lows[idx]
                days_held = 0
                for j in range(idx + 1, min(idx + 1 + MAX_HOLD_DAYS, len(dates))):
                    if lows[j] > gap_low:
                        days_held += 1
                    else:
                        break  # made a new low since the gap — stop counting

                total_score = base_score + days_held
                gain_pct = (current_price - closes[idx]) / closes[idx] * 100

                gap_span = prior_close - opens[idx]
                fill_pct = ((current_price - opens[idx]) / gap_span * 100) if gap_span > 0 else 0.0

                all_results.append({
                    'ticker':               ticker,
                    'gap_date':             dates[idx].strftime('%Y-%m-%d'),
                    'prior_close':          round(float(prior_close), 4),
                    'gap_open':             round(float(opens[idx]), 4),
                    'gap_low':              round(float(gap_low), 4),
                    'close':                round(float(closes[idx]), 4),
                    'current_price':        round(float(current_price), 4),
                    'gap_pct':              meta['gap_pct'],
                    'close_pct':            meta['close_pct'],
                    'vol_surge':            meta['vol_surge'],
                    'recovered_intraday':   meta['recovered_intraday'],
                    'days_held':            days_held,
                    'fill_pct':             round(fill_pct, 1),
                    'score':                total_score,
                    'gain_pct':             round(gain_pct, 2),
                })

                log(f"[{i}/{len(tickers)}] {ticker} {dates[idx].date()} "
                    f"gap {meta['gap_pct']}% held {days_held}d score {total_score}")

        except Exception as e:
            errors += 1
            if errors <= 10:
                log(f"[{i}/{len(tickers)}] {ticker}: ERROR — {str(e)[:60]}")

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
    log(f"COMPLETE — {len(all_results)} gap-down signals found across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_gapdown_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_gapdown_scan()
