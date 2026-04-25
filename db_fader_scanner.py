"""
DB FADER SCANNER
================
Daily-chart scanner. Three conditions must ALL be true:

  1. Channel printing  — EMA(5)/EMA(26) compressed within ATR(50)*0.4,
                         at least 5 of last 10 bars. Daily only.

  2. Fader green       — Fader line is rising on the current bar.
                         Fader = (WMA-chain → HMA(8)  +  JMA(7, 126, 0.89)) / 2
                         Matches fader.py exactly, pure numpy/pandas.

  3. At 25% of range   — Price is in the NEAR_25 zone of its dollar range.
                         Dollar ranges (from RangeLevelScanner.py):
                           $0-10   → $1 ranges   (e.g. $1-$2,  25% = $1.25)
                           $10-100 → $10 ranges  (e.g. $10-$20, 25% = $12.50)
                           $100-500→ $50 ranges  (e.g. $100-$150, 25% = $112.50)
                           $500+   → $100 ranges (e.g. $500-$600, 25% = $525)
                         NEAR_25 zone = position 12.5% – 37.5% within the range.

Usage:
    python db_fader_scanner.py
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

# ── Parameters ────────────────────────────────────────────────────────────────
CHANNEL_EMA_FAST    = 5
CHANNEL_EMA_SLOW    = 26
CHANNEL_ATR_PERIOD  = 50
CHANNEL_ATR_MULT    = 0.4
CHANNEL_BARS_NEEDED = 5
CHANNEL_LOOKBACK    = 10

FADER_JMA_LEN   = 7
FADER_JMA_PHASE = 126
FADER_JMA_POWER = 0.89144

MIN_BARS = 100

RESULTS_FILE = os.path.join(BASE_DIR, 'fader_scan_results.json')


# ── Dollar range logic (from RangeLevelScanner.py) ────────────────────────────

def get_range_info(price):
    """Return range levels for a given price using the dollar range system."""
    if price <= 0:
        return None

    if price < 10:
        range_size = 1.0
        range_low  = float(int(price))
    elif price < 100:
        range_size = 10.0
        range_low  = float(int(price / 10) * 10)
    elif price < 500:
        range_size = 50.0
        range_low  = float(int(price / 50) * 50)
    else:
        range_size = 100.0
        range_low  = float(int(price / 100) * 100)

    range_high   = range_low + range_size
    position_pct = (price - range_low) / range_size * 100

    if position_pct <= 12.5:
        zone = 'NEAR_0'
    elif position_pct <= 37.5:
        zone = 'NEAR_25'
    elif position_pct <= 62.5:
        zone = 'NEAR_50'
    elif position_pct <= 87.5:
        zone = 'NEAR_75'
    else:
        zone = 'NEAR_100'

    return {
        'range_low':    range_low,
        'range_high':   range_high,
        'range_size':   range_size,
        'L0':           range_low,
        'L25':          range_low + range_size * 0.25,
        'L50':          range_low + range_size * 0.50,
        'L75':          range_low + range_size * 0.75,
        'L100':         range_high,
        'position_pct': round(position_pct, 1),
        'zone':         zone,
    }


# ── Indicators (pure numpy/pandas) ────────────────────────────────────────────

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


def _wma(series, period):
    """Weighted Moving Average."""
    if period <= 1:
        return series.copy()
    weights = np.arange(1, period + 1, dtype=float)
    w_sum   = weights.sum()
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / w_sum, raw=True
    )


def _hma(series, period):
    """Hull Moving Average: WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    if period <= 1:
        return series.copy()
    half   = max(1, period // 2)
    sqrt_p = max(1, round(period ** 0.5))
    raw    = 2.0 * _wma(series, half) - _wma(series, period)
    return _wma(raw, sqrt_p)


def _jma(source_arr, length, phase, power):
    """Jurik Moving Average — matches fader.py exactly."""
    phase = max(-100.0, min(100.0, float(phase)))
    phase_ratio = phase / 100.0 + 1.5
    beta  = 0.45 * (length - 1) / (0.45 * (length - 1) + 2)
    alpha = beta ** power

    n   = len(source_arr)
    e0  = np.zeros(n)
    e1  = np.zeros(n)
    e2  = np.zeros(n)
    out = np.zeros(n)

    for i in range(1, n):
        e0[i]  = (1 - alpha) * source_arr[i] + alpha * e0[i - 1]
        e1[i]  = (source_arr[i] - e0[i]) * (1 - beta) + beta * e1[i - 1]
        e2[i]  = (e0[i] + phase_ratio * e1[i] - out[i - 1]) * (1 - alpha) ** 2 \
                 + alpha ** 2 * e2[i - 1]
        out[i] = e2[i] + out[i - 1]

    return out


# ── Core checks ───────────────────────────────────────────────────────────────

def is_channel_printing(df):
    """True if daily chart is in an EMA(5)/EMA(26) squeeze channel."""
    if len(df) < CHANNEL_ATR_PERIOD + CHANNEL_LOOKBACK:
        return False
    try:
        ema_fast   = calc_ema(df['close'], CHANNEL_EMA_FAST)
        ema_slow   = calc_ema(df['close'], CHANNEL_EMA_SLOW)
        atr        = calc_atr(df['high'], df['low'], df['close'], CHANNEL_ATR_PERIOD) * CHANNEL_ATR_MULT
        in_channel = (ema_fast - ema_slow).abs() < atr
        return int(in_channel.iloc[-CHANNEL_LOOKBACK:].sum()) >= CHANNEL_BARS_NEEDED
    except Exception:
        return False


def is_fader_green(close_series):
    """
    True if the Fader line is rising on the last bar.
    Fader = average of HMA-chain and JMA, matching fader.py params:
      fmal_zl=1, smal_zl=1  →  tmal=2, Fmal=3, Ftmal=5, Smal=8
      JMA: length=7, phase=126, power=0.89144
    """
    try:
        # WMA chain
        m1   = _wma(close_series, 1)   # = close
        m2   = _wma(m1,           1)   # = close
        m3   = _wma(m2,           2)
        m4   = _wma(m3,           3)
        m5   = _wma(m4,           5)
        mavw = _hma(m5,           8)

        # JMA
        jma_arr    = _jma(close_series.values, FADER_JMA_LEN, FADER_JMA_PHASE, FADER_JMA_POWER)
        jma_series = pd.Series(jma_arr, index=close_series.index)

        signal = (mavw + jma_series) / 2.0
        return bool(signal.iloc[-1] > signal.iloc[-2])
    except Exception:
        return False


# ── DB helpers ────────────────────────────────────────────────────────────────

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


# ── Per-ticker scan ───────────────────────────────────────────────────────────

def scan_ticker(conn, ticker):
    df = get_ticker_data(conn, ticker)
    if df is None or len(df) < MIN_BARS:
        return None

    current_price = float(df['close'].iloc[-1])
    if current_price < 0.50:   # skip sub-penny / illiquid
        return None

    # 1. Dollar range — must be in NEAR_25 zone
    rng = get_range_info(current_price)
    if rng is None or rng['zone'] != 'NEAR_25':
        return None

    # 2. Channel must be printing
    if not is_channel_printing(df):
        return None

    # 3. Fader must be green
    if not is_fader_green(df['close']):
        return None

    # Entry / stop / target (within-range trade)
    entry  = rng['L25']
    stop   = rng['L0']
    target = rng['L75']
    risk   = entry - stop
    reward = target - entry
    rr     = round(reward / risk, 2) if risk > 0 else 0

    return {
        'ticker':       ticker,
        'price':        round(current_price, 4),
        'range':        f"${rng['range_low']:.0f}–${rng['range_high']:.0f}",
        'range_size':   rng['range_size'],
        'position_pct': rng['position_pct'],
        'L0':           rng['L0'],
        'L25':          rng['L25'],
        'L50':          rng['L50'],
        'L75':          rng['L75'],
        'entry':        round(entry,  4),
        'stop':         round(stop,   4),
        'target':       round(target, 4),
        'risk':         round(risk,   4),
        'reward':       round(reward, 4),
        'rr':           rr,
    }


# ── Full scan ─────────────────────────────────────────────────────────────────

def run_fader_scan(log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)

    log(f"Fader Scanner started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    log("Conditions: channel printing (daily) + fader green + price at 25% of dollar range\n\n")

    conn    = get_connection()
    tickers = get_all_tickers(conn)
    log(f"Scanning {len(tickers)} tickers...\n")

    results = []
    for i, ticker in enumerate(tickers, 1):
        try:
            result = scan_ticker(conn, ticker)
            if result:
                results.append(result)
        except Exception:
            pass

        if i % 500 == 0:
            log(f"  Progress: {i}/{len(tickers)} — {len(results)} hits so far\n")

        if i % 1000 == 0:
            conn.close()
            conn = get_connection()

    conn.close()

    # Sort: closest to the 25% level first (tightest entry)
    results.sort(key=lambda x: abs(x['position_pct'] - 25))

    log(f"\nScan complete: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    log(f"Total setups found: {len(results)}\n")

    payload = {
        'scan_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total':     len(results),
        'results':   results,
    }
    with open(RESULTS_FILE, 'w') as f:
        json.dump(payload, f)

    return results


def load_last_fader_results():
    if not os.path.exists(RESULTS_FILE):
        return None
    try:
        with open(RESULTS_FILE) as f:
            return json.load(f)
    except Exception:
        return None


if __name__ == '__main__':
    run_fader_scan(log_callback=print)
