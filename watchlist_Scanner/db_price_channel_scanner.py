"""
PRICE CHANNEL SCANNER
=====================
Scans for stocks forming ascending parallel price channels where current
price is near the lower channel boundary — the buy zone.

Timeframes (same algorithm, different data resolution):
  Daily   : last 180 bars, pivot lookback 8  — short channels (weeks–months)
  Weekly  : last 78 weeks, pivot lookback 5  — medium channels (months–1.5yr)
  Monthly : last 60 months, pivot lookback 3 — mega channels (multi-year, log scale)

Channel Detection:
  1. Find pivot highs and lows using a rolling window
  2. Fit linear regression through pivot lows → lower trendline
     Monthly timeframe uses log(price) so channels are straight on log scale
  3. Create parallel upper line offset to best fit the pivot highs
  4. Validate: slope must be positive (ascending only), R² >= 0.65,
     >= 2 touches on each line within 15% of channel width
  5. Signal: current price within bottom 10% of channel width of lower line

Scoring (max 14):
  Channel position  0–4  (how close price is to lower line)
  Trendline quality 0–3  (R² of lower line fit)
  Touch count       0–4  (extra touches above minimum 2+2)
  Channel age       0–2  (longer channel = more reliable)
  Width bonus       0–1  (narrower channel = cleaner signal)
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

RESULTS_FILE = os.path.join(BASE_DIR, 'last_price_channel_results.json')

# Signal threshold: price must be within this % of channel width of the lower line
SIGNAL_THRESHOLD_PCT = 10.0

CONFIGS = {
    'daily': {
        'bars':      180,
        'pivot_lb':  8,
        'tolerance': 0.15,   # touch = within 15% of channel width of the line
        'log_scale': False,
        'label':     'Daily',
        'sublabel':  'Short channels — weeks to months',
    },
    'weekly': {
        'bars':      78,
        'pivot_lb':  5,
        'tolerance': 0.15,
        'log_scale': False,
        'label':     'Weekly',
        'sublabel':  'Medium channels — months to ~1.5 years',
    },
    'monthly': {
        'bars':      60,
        'pivot_lb':  3,
        'tolerance': 0.15,
        'log_scale': True,   # log scale for multi-year channels
        'label':     'Monthly',
        'sublabel':  'Mega channels — multi-year',
    },
}


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


def resample_weekly(df):
    return df.resample('W-FRI').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    ).dropna(subset=['open', 'high', 'low', 'close'])


def resample_monthly(df):
    return df.resample('MS').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    ).dropna(subset=['open', 'high', 'low', 'close'])


def find_pivot_highs(arr, lb):
    pivots = []
    n = len(arr)
    for i in range(lb, n - lb):
        if arr[i] >= max(arr[max(0, i - lb): i + lb + 1]):
            pivots.append(i)
    return pivots


def find_pivot_lows(arr, lb):
    pivots = []
    n = len(arr)
    for i in range(lb, n - lb):
        if arr[i] <= min(arr[max(0, i - lb): i + lb + 1]):
            pivots.append(i)
    return pivots


def fit_line(x_list, y_list):
    """Linear regression through points. Returns (slope, intercept, r2)."""
    if len(x_list) < 2:
        return None, None, 0.0
    x = np.array(x_list, dtype=float)
    y = np.array(y_list, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    y_pred  = slope * x + intercept
    ss_res  = float(np.sum((y - y_pred) ** 2))
    ss_tot  = float(np.sum((y - float(np.mean(y))) ** 2))
    r2      = 1.0 - ss_res / ss_tot if ss_tot > 1e-10 else 0.0
    return float(slope), float(intercept), float(max(0.0, r2))


def detect_channel(df, cfg):
    """
    Attempt to detect an ascending parallel price channel.
    Returns a result dict or None.
    """
    n_bars   = cfg['bars']
    lb       = cfg['pivot_lb']
    tol      = cfg['tolerance']
    use_log  = cfg['log_scale']
    MIN_R2   = 0.65
    MIN_BARS = max(20, n_bars // 4)

    sub = df.tail(n_bars).reset_index(drop=True)
    n   = len(sub)
    if n < MIN_BARS:
        return None

    raw_h = sub['high'].values.astype(float)
    raw_l = sub['low'].values.astype(float)
    raw_c = sub['close'].values.astype(float)

    # Guard against zero/negative prices for log
    if use_log and (np.any(raw_l <= 0) or np.any(raw_h <= 0)):
        return None

    # Work in log space for monthly, linear for daily/weekly
    wh = np.log(raw_h) if use_log else raw_h
    wl = np.log(raw_l) if use_log else raw_l
    wc = np.log(raw_c) if use_log else raw_c

    x = np.arange(n, dtype=float)

    # Find pivot highs and lows
    ph = find_pivot_highs(wh.tolist(), lb)
    pl = find_pivot_lows(wl.tolist(), lb)
    if len(ph) < 2 or len(pl) < 2:
        return None

    # Fit lower trendline through all pivot lows
    low_slope, low_intercept, r2 = fit_line(
        [float(i) for i in pl],
        [float(wl[i]) for i in pl]
    )
    if low_slope is None or r2 < MIN_R2:
        return None

    # Ascending channel only
    if low_slope <= 0:
        return None

    lower_line = low_slope * x + low_intercept

    # Parallel upper line: positioned at the maximum upward offset from the
    # lower line at each pivot high — this makes the upper line touch the
    # highest peak while staying parallel to the lower line
    offsets = [float(wh[i]) - float(lower_line[i]) for i in ph]
    if not offsets or max(offsets) <= 0:
        return None
    ch_offset = float(max(offsets))
    upper_line = lower_line + ch_offset

    # Count how many pivots are "touching" each line
    # (within tol × channel_width of the line at that bar)
    thresh = ch_offset * tol
    low_touches  = sum(1 for i in pl if abs(float(wl[i]) - float(lower_line[i])) <= thresh)
    high_touches = sum(1 for i in ph if abs(float(wh[i]) - float(upper_line[i])) <= thresh)

    if low_touches < 2 or high_touches < 2:
        return None

    # Current price position in the channel
    curr_c = float(wc[-1])
    c_low  = float(lower_line[-1])
    c_up   = float(upper_line[-1])

    # Allow a small slack below the line (price can briefly pierce)
    slack = ch_offset * 0.20
    if curr_c < c_low - slack:
        return None   # broken below channel
    if curr_c > c_up + slack:
        return None   # above channel — not a lower-line signal

    # Channel position: 0% = right at lower line, 100% = at upper line
    ch_pct = (curr_c - c_low) / ch_offset * 100.0
    ch_pct = float(max(0.0, min(100.0, ch_pct)))

    if ch_pct > SIGNAL_THRESHOLD_PCT:
        return None   # not close enough to the lower line

    # Channel age in bars (from first pivot to now)
    first_pivot = min(pl[0], ph[0])
    age_bars    = int(n - first_pivot)

    # ── Scoring ──────────────────────────────────────────────────────────────
    score = 0

    # Position (closer to lower line = higher score)
    if   ch_pct <= 2:  score += 4
    elif ch_pct <= 5:  score += 3
    elif ch_pct <= 7:  score += 2
    else:              score += 1

    # Trendline quality
    if   r2 >= 0.92: score += 3
    elif r2 >= 0.82: score += 2
    elif r2 >= 0.70: score += 1

    # Extra touches beyond the minimum 2+2
    extra_touches = (low_touches - 2) + (high_touches - 2)
    score += min(extra_touches, 4)

    # Channel age
    age_ratio = age_bars / n
    if   age_ratio >= 0.70: score += 2
    elif age_ratio >= 0.40: score += 1

    # Width bonus: narrower channel = cleaner signal
    # width_pct = channel width as % of the lower line price
    if use_log:
        width_pct = float((np.exp(ch_offset) - 1) * 100)
    else:
        width_pct = float(ch_offset / abs(c_low) * 100) if c_low > 0 else 0.0

    if width_pct < 20: score += 1

    # ── Convert back to actual prices ────────────────────────────────────────
    if use_log:
        lower_price = float(np.exp(c_low))
        upper_price = float(np.exp(c_up))
        # slope in log space → approximate % gain per bar
        slope_pct = float(low_slope * 100)
    else:
        lower_price = float(c_low)
        upper_price = float(c_up)
        mid         = (lower_price + upper_price) / 2
        slope_pct   = float(low_slope / mid * 100) if mid > 0 else 0.0

    current_price = float(raw_c[-1])

    return {
        'ch_pct':       round(ch_pct, 1),
        'lower':        round(lower_price, 4),
        'upper':        round(upper_price, 4),
        'current':      round(current_price, 4),
        'r2':           round(r2, 3),
        'low_touches':  int(low_touches),
        'high_touches': int(high_touches),
        'age_bars':     age_bars,
        'slope_pct':    round(slope_pct, 4),
        'width_pct':    round(width_pct, 1),
        'score':        int(score),
    }


def run_price_channel_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('PRICE CHANNEL SCANNER  (ascending channels, bottom 10%)')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    conn    = get_connection()
    tickers = get_all_tickers(conn)
    log(f"Scanning {len(tickers)} tickers across 3 timeframes...\n")

    results = {'daily': [], 'weekly': [], 'monthly': []}
    errors  = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            daily_df = get_ticker_daily(conn, ticker)
            if daily_df is None or len(daily_df) < 30:
                continue

            weekly_df  = resample_weekly(daily_df)
            monthly_df = resample_monthly(daily_df)

            for tf, df in [('daily', daily_df), ('weekly', weekly_df), ('monthly', monthly_df)]:
                cfg = CONFIGS[tf]
                hit = detect_channel(df, cfg)
                if hit:
                    hit['ticker'] = ticker
                    results[tf].append(hit)
                    log(f"[{i}] {ticker} {tf}: score {hit['score']} "
                        f"ch%={hit['ch_pct']} R²={hit['r2']} "
                        f"touches {hit['low_touches']}L/{hit['high_touches']}H")

        except Exception as e:
            errors += 1
            if errors <= 10:
                log(f"[{i}] {ticker}: ERROR — {str(e)[:80]}")

        if i % 300 == 0:
            conn.close()
            conn = get_connection()
            log(f"\n--- Reconnected at ticker {i} ---\n")

    conn.close()

    # Sort each timeframe by score descending
    for tf in results:
        results[tf].sort(key=lambda x: x['score'], reverse=True)

    output = {
        'scan_date':       datetime.now().strftime('%Y-%m-%d %H:%M'),
        'tickers_scanned': len(tickers),
        'errors':          errors,
        'daily':   {'total': len(results['daily']),   'results': results['daily']},
        'weekly':  {'total': len(results['weekly']),  'results': results['weekly']},
        'monthly': {'total': len(results['monthly']), 'results': results['monthly']},
    }

    with open(RESULTS_FILE, 'w') as f:
        json.dump(output, f)

    log(f"\n{'='*60}")
    log(f"COMPLETE")
    log(f"  Daily:   {len(results['daily'])} channels")
    log(f"  Weekly:  {len(results['weekly'])} channels")
    log(f"  Monthly: {len(results['monthly'])} channels")
    log(f"  Errors:  {errors}")
    log('=' * 60)
    return output


def load_last_price_channel_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_price_channel_scan()
