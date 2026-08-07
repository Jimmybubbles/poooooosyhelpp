"""
DAILY DOUBLE BOTTOM SCANNER
===========================
Finds double-bottom (and triple/quadruple-bottom) setups on the daily chart,
using the same confirmed swing-low pivots as the Higher Low scanner
(swing_points.compute_swing_zones — Leviathan Swing Points, left=15/right=10).

Signal criteria (all must pass):
  1. Range zone   — current price sits in the 0-25% zone of its dollar-range
                     bucket (same bucket system as the Fader scanner):
                       $0-10   -> $1 buckets    (e.g. $1-$2,   0-25% = $1.00-$1.25)
                       $10-100 -> $10 buckets   (e.g. $10-$20, 0-25% = $10-$12.50)
                       $100-500-> $50 buckets
                       $500+   -> $100 buckets
                     i.e. price is trading near the floor of its current range —
                     where a bottom would be expected to sit.

  2. Recent bottom — the most recent confirmed swing low is still within
                     CURRENT_TOLERANCE_PCT of the current price (the pattern
                     is still "live", not something price has already run
                     away from).

  3. Prior match(es) — at least one EARLIER confirmed swing low within
                     BOTTOM_TOLERANCE_PCT of the recent low's price (the
                     second "bottom" of the double bottom), with a neckline
                     (highest high between the two lows) at least
                     MIN_NECKLINE_PCT above them — otherwise it's not a
                     distinct enough dip-and-retest, just noise.

Scoring (points system):
  - Base: confirmed double bottom                          +30
  - Extra touches beyond the required 2 (triple/quad+
    bottom — more retests of the same support = stronger)  +20 each, capped at 3 extra
  - Neckline strength (size of the bounce between bottoms):
      >=20%  +10   >=15%  +7   >=10%  +5
  - Volume confirmation on the most recent bottom
    (> 1.1x its 20-day average)                             +5
  - Deep in zone (position_pct <= 12.5%, i.e. bottom half
    of the already-required 0-25% zone)                     +5

Usage:
    python db_doublebottom_scanner.py
"""

import pandas as pd
import pymysql
import os
import sys
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db_config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
from swing_points import compute_swing_zones, DEFAULT_LEFT, DEFAULT_RIGHT

RESULTS_FILE          = os.path.join(BASE_DIR, 'last_doublebottom_results.json')
MIN_BARS              = 150   # need enough daily history to find two separated bottoms
BOTTOM_TOLERANCE_PCT  = 4.0   # how close two swing lows must be to count as "the same" bottom
MIN_NECKLINE_PCT      = 8.0   # peak between the two bottoms must clear this % above them
CURRENT_TOLERANCE_PCT = 8.0   # current price must still be within this % of the recent bottom
MAX_EXTRA_TOUCH_BONUS = 3     # cap the "extra touches" scoring bonus at this many


# ── Dollar range logic (same bucket system as db_fader_scanner.py) ───────────

def get_range_info(price):
    """Return dollar-range bucket info for a price. 0-25% = bottom of the bucket."""
    if price is None or price <= 0:
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

    return {
        'range_low':    range_low,
        'range_high':   range_high,
        'range_size':   range_size,
        'position_pct': round(position_pct, 1),
    }


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
    # like ^TNX) — avoids divide-by-zero downstream.
    return df[(df[['open', 'high', 'low', 'close']] > 0).all(axis=1)]


# ── Per-ticker scan ───────────────────────────────────────────────────────────

def scan_ticker(ticker, df):
    if df is None or len(df) < MIN_BARS:
        return None

    current_price = float(df['close'].iloc[-1])

    # 1. Range zone — must be in the 0-25% (bottom) zone of its dollar bucket
    rng = get_range_info(current_price)
    if rng is None or rng['position_pct'] > 25:
        return None

    # 2. Confirmed swing lows
    zones = compute_swing_zones(df, DEFAULT_LEFT, DEFAULT_RIGHT)
    low_zones = [z for z in zones if z['type'] == 'low']
    if len(low_zones) < 2:
        return None

    recent = low_zones[-1]
    recent_price = recent['pivot_price']
    if recent_price <= 0:
        return None

    # 3. Recent bottom must still be "live" — current price close to it
    if abs(current_price - recent_price) / recent_price * 100 > CURRENT_TOLERANCE_PCT:
        return None

    # 4. Find earlier swing lows matching the recent bottom's price, with a
    #    real neckline (peak) between them
    matches = []
    for z in low_zones[:-1]:
        diff_pct = abs(z['pivot_price'] - recent_price) / min(z['pivot_price'], recent_price) * 100
        if diff_pct > BOTTOM_TOLERANCE_PCT:
            continue

        seg = df.loc[z['pivot_date']:recent['pivot_date']]
        if seg.empty:
            continue
        neckline = float(seg['high'].max())
        neckline_date = seg['high'].idxmax()
        lower_of_two = min(z['pivot_price'], recent_price)
        neckline_pct = (neckline - lower_of_two) / lower_of_two * 100
        if neckline_pct < MIN_NECKLINE_PCT:
            continue

        matches.append({
            'date':          z['pivot_date'],
            'price':         z['pivot_price'],
            'diff_pct':      diff_pct,
            'neckline':      neckline,
            'neckline_date': neckline_date,
            'neckline_pct':  neckline_pct,
        })

    if not matches:
        return None

    touches               = len(matches) + 1   # + the recent bottom itself
    best_match            = min(matches, key=lambda m: m['diff_pct'])
    strongest_neckline    = max(matches, key=lambda m: m['neckline_pct'])
    earliest_match        = min(matches, key=lambda m: m['date'])
    neckline_pct          = strongest_neckline['neckline_pct']
    neckline_price        = strongest_neckline['neckline']

    # Volume confirmation on the most recent bottom
    vol_series   = df['volume'].astype(float)
    avg_vol_20   = vol_series.rolling(20, min_periods=10).mean()
    recent_loc   = df.index.get_loc(recent['pivot_date'])
    vol_at_recent = vol_series.iloc[recent_loc]
    avg_at_recent = avg_vol_20.iloc[recent_loc]
    vol_confirmed = bool(avg_at_recent and avg_at_recent > 0 and vol_at_recent > avg_at_recent * 1.1)

    # ── Scoring ────────────────────────────────────────────────────────────
    score = 30
    breakdown = [f"Double bottom confirmed ({touches}x touches) +30"]

    extra = min(touches - 2, MAX_EXTRA_TOUCH_BONUS)
    if extra > 0:
        pts = extra * 20
        score += pts
        breakdown.append(f"+{extra} extra touch{'es' if extra > 1 else ''} beyond double (triple/quad+ bottom) +{pts}")

    if neckline_pct >= 20:
        score += 10; breakdown.append(f"Strong neckline ({neckline_pct:.0f}%) +10")
    elif neckline_pct >= 15:
        score += 7;  breakdown.append(f"Neckline ({neckline_pct:.0f}%) +7")
    elif neckline_pct >= 10:
        score += 5;  breakdown.append(f"Neckline ({neckline_pct:.0f}%) +5")

    if vol_confirmed:
        score += 5; breakdown.append("Volume confirmation on bottom +5")

    if rng['position_pct'] <= 12.5:
        score += 5; breakdown.append("Deep in zone (<=12.5%) +5")

    # Trade structure: stop below the recent low, target at the neckline
    # (classic double-bottom breakout target), plus the measured-move target
    # (neckline + the height of the pattern) for reference.
    stop            = recent_price * 0.97
    target_neckline = neckline_price
    target_measured = neckline_price + (neckline_price - min(recent_price, best_match['price']))
    risk            = current_price - stop
    reward          = target_neckline - current_price
    rr              = round(reward / risk, 2) if risk > 0 else 0

    return {
        'ticker':          ticker,
        'price':           round(current_price, 4),
        'range':           f"${rng['range_low']:.0f}–${rng['range_high']:.0f}",
        'position_pct':    rng['position_pct'],
        'touches':         touches,
        'bottoms':         [
            {'date': m['date'].strftime('%Y-%m-%d'), 'price': round(m['price'], 4)}
            for m in sorted(matches, key=lambda m: m['date'])
        ] + [{'date': recent['pivot_date'].strftime('%Y-%m-%d'), 'price': round(recent_price, 4)}],
        'first_bottom_date':  earliest_match['date'].strftime('%Y-%m-%d'),
        'first_bottom_price': round(earliest_match['price'], 4),
        'second_bottom_date': recent['pivot_date'].strftime('%Y-%m-%d'),
        'second_bottom_price': round(recent_price, 4),
        'diff_pct':        round(best_match['diff_pct'], 2),
        'neckline':        round(neckline_price, 4),
        'neckline_date':   strongest_neckline['neckline_date'].strftime('%Y-%m-%d'),
        'neckline_pct':    round(neckline_pct, 2),
        'vol_confirmed':   vol_confirmed,
        'stop':            round(stop, 4),
        'target_neckline': round(target_neckline, 4),
        'target_measured': round(target_measured, 4),
        'rr':              rr,
        'score':           score,
        'score_breakdown': breakdown,
        'date':            df.index[-1].strftime('%Y-%m-%d'),
    }


# ── Full scan ─────────────────────────────────────────────────────────────────

def run_doublebottom_scan(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg + '\n')

    log('=' * 60)
    log('DAILY DOUBLE BOTTOM SCANNER')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("Conditions: price in 0-25% of dollar-range bucket + 2+ confirmed "
        "swing lows within tolerance + valid neckline\n")

    conn    = get_connection()
    tickers = get_all_tickers(conn)
    log(f"Scanning {len(tickers)} tickers...\n")

    all_results = []
    errors = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            df = get_ticker_daily(conn, ticker)
            result = scan_ticker(ticker, df)
            if result:
                all_results.append(result)
                log(f"[{i}/{len(tickers)}] {ticker} {result['touches']}x bottoms @ "
                    f"~${result['second_bottom_price']:.2f} score {result['score']}")
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
    log(f"COMPLETE — {len(all_results)} double-bottom signals across {len(tickers)} tickers")
    log(f"Errors: {errors}")
    log('=' * 60)
    return output


def load_last_doublebottom_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    run_doublebottom_scan()
