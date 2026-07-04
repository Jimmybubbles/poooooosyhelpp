"""
DAILY EXTREME SCANNER
=====================
Ported from extreme_scan.py (Pine v4 "Neo" indicator) — combines two of
Jimmy's momentum/exhaustion signals into one daily scan:

  - TD Buy/Sell count — a simplified TD Sequential setup counter. Counts
    consecutive closes below (buy) / above (sell) the close 4 bars back;
    fires at count 8 and count 9.
  - ADX Momentum Change Warning — ADX(8)/DI(8) based. Flags when a 2-bar
    SMA of (ADX-30) crosses back over itself while ADX is elevated (>40).
    Direction (up/down warning) comes from which DI (+/-) was dominant —
    i.e. an established trend's momentum just started rolling over.

Either signal can trigger a row on its own — no confluence is required —
but both indicators' current values are always shown together for context,
plus a bonus when they agree on direction the same day.

Signal criteria (any one triggers a row):
  - TD Buy/Sell count reaches 8 or 9
  - ADX momentum warning fires (up or down)

Scoring (max ~10):
  - TD9  = +3, TD8 = +2
  - ADX warning = +2
  - Same-direction TD + ADX signal on the same day = +2 confluence bonus

Usage:
    python db_extreme_scanner.py
"""

import pandas as pd
import numpy as np
import pymysql
import os
import sys
import json
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT

RESULTS_FILE  = os.path.join(BASE_DIR, 'last_extreme_results.json')
MAX_DAYS_BACK = 15   # how far back to look for signals

# ADX Momentum Change Warning params (from extreme_scan.py)
ADX_LEN   = 8
DI_LEN    = 8
ADX_THOLD = 10


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


def td_counts(closes):
    """
    Simplified TD Sequential setup counter (ported line-for-line from
    extreme_scan.py). Counts consecutive closes below (buy) / above (sell)
    the close 4 bars back, resetting to 0 the moment the condition breaks
    and wrapping 9 -> 1 rather than climbing past it.
    Returns (buy_counts, sell_counts) int arrays aligned to `closes`.
    """
    n = len(closes)
    buy  = np.zeros(n, dtype=int)
    sell = np.zeros(n, dtype=int)
    for i in range(4, n):
        buy[i]  = (1 if buy[i - 1]  == 9 else buy[i - 1]  + 1) if closes[i] < closes[i - 4] else 0
        sell[i] = (1 if sell[i - 1] == 9 else sell[i - 1] + 1) if closes[i] > closes[i - 4] else 0
    return buy, sell


def adx_warnings(df):
    """
    ADX Momentum Change Warning, ported from extreme_scan.py.
    RMA is approximated with an EMA(span) — same convention already used
    for ATR/EMA elsewhere in this codebase (no talib on PythonAnywhere).
    Returns (sig, up_warning, down_warning) pandas Series aligned to df.
    """
    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)

    up_move   = high.diff()
    down_move = -low.diff()
    plus_dm   = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm  = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    tr_s    = tr.ewm(span=DI_LEN, adjust=False).mean()
    plus_s  = plus_dm.ewm(span=DI_LEN, adjust=False).mean()
    minus_s = minus_dm.ewm(span=DI_LEN, adjust=False).mean()

    plus_di  = (100 * plus_s  / tr_s.replace(0, np.nan)).ffill().fillna(0)
    minus_di = (100 * minus_s / tr_s.replace(0, np.nan)).ffill().fillna(0)

    dx_sum = (plus_di + minus_di).replace(0, 1)
    dx     = 100 * (plus_di - minus_di).abs() / dx_sum
    adx    = dx.ewm(span=ADX_LEN, adjust=False).mean()

    sig      = adx - 30
    up_adx   = plus_di  - 30
    down_adx = minus_di - 30
    sig_slow = sig.rolling(2).mean()

    crossover    = (sig_slow.shift(1) <= sig.shift(1)) & (sig_slow > sig)
    up_warning   = crossover & (sig > ADX_THOLD) & (up_adx > down_adx)
    down_warning = crossover & (sig > ADX_THOLD) & (up_adx < down_adx)

    return sig, up_warning, down_warning


def run_extreme_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('DAILY EXTREME SCANNER (TD Buy/Sell + ADX Momentum Warning)')
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
            if df is None or len(df) < 40:
                continue

            dates  = df.index.tolist()
            closes = df['close'].tolist()
            current_price = closes[-1]

            buy_counts, sell_counts = td_counts(closes)
            sig, up_warn, down_warn = adx_warnings(df)
            sig_vals   = sig.tolist()
            up_warns   = up_warn.tolist()
            down_warns = down_warn.tolist()

            for idx in range(len(dates)):
                if dates[idx] < cutoff:
                    continue

                signals    = []
                score      = 0
                directions = set()

                tb, ts = int(buy_counts[idx]), int(sell_counts[idx])
                if tb == 9:
                    signals.append('TD9 Buy');  score += 3; directions.add('bullish')
                elif tb == 8:
                    signals.append('TD8 Buy');  score += 2; directions.add('bullish')
                if ts == 9:
                    signals.append('TD9 Sell'); score += 3; directions.add('bearish')
                elif ts == 8:
                    signals.append('TD8 Sell'); score += 2; directions.add('bearish')

                if down_warns[idx]:
                    signals.append('ADX Down Warning'); score += 2; directions.add('bullish')
                if up_warns[idx]:
                    signals.append('ADX Up Warning');   score += 2; directions.add('bearish')

                if not signals:
                    continue

                if len(directions) == 1:
                    direction = next(iter(directions))
                    has_td  = any('TD'  in s for s in signals)
                    has_adx = any('ADX' in s for s in signals)
                    if has_td and has_adx:
                        score += 2   # same-direction confluence bonus
                else:
                    direction = 'mixed'

                gain_pct  = (current_price - closes[idx]) / closes[idx] * 100
                sig_today = sig_vals[idx]

                all_results.append({
                    'ticker':           ticker,
                    'signal_date':      dates[idx].strftime('%Y-%m-%d'),
                    'signals':          signals,
                    'direction':        direction,
                    'td_buy_count':     tb,
                    'td_sell_count':    ts,
                    'adx_signal':       None if pd.isna(sig_today) else round(float(sig_today), 1),
                    'adx_up_warning':   bool(up_warns[idx]),
                    'adx_down_warning': bool(down_warns[idx]),
                    'close':            round(float(closes[idx]), 4),
                    'current_price':    round(float(current_price), 4),
                    'gain_pct':         round(gain_pct, 2),
                    'score':            score,
                })

                log(f"[{i}/{len(tickers)}] {ticker} {dates[idx].date()} "
                    f"{'/'.join(signals)} score {score}")

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
    log(f"COMPLETE — {len(all_results)} signals across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_extreme_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_extreme_scan()
