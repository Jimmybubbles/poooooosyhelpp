"""
GAP DOWN DOUBLE BOTTOM SCANNER
==============================
Finds stocks that just gapped down (in the last day or week) to a price
level that matches an earlier confirmed double-bottom support — i.e. the
gap didn't land in random space, it landed almost exactly on a level the
stock has already proven as support once before. That combination (fresh
gap + pre-existing support right there) is the "potential buy-in" signal.

Built on top of the same confirmed swing-low pivots as the Higher Low
scanner (swing_points.compute_swing_zones — Leviathan Swing Points,
left=15/right=10) for the "this is real support" half of the pattern, and
the same gap-down definition as db_gapdown_scanner.py (open vs. prior
close) for the "just happened" half.

Signal criteria (all must pass):
  1. Range zone    — current price sits in the 0-25% zone of its dollar-
                      range bucket (same bucket system as the Fader
                      scanner) — price is trading near the floor of its
                      current range.

  2. Recent gap     — a gap-down day (open at least GAP_TIERS[-1]% below
                      the prior close, liquidity-filtered) within the
                      last GAP_LOOKBACK_DAYS trading days ("last day /
                      week"). Four tiers are scored/tagged so the results
                      page can filter to 2.5%+, 5%+, 7.5%+, or 10%+ gaps:
                        2.5% - 5%   -> tier '2.5%+'
                        5%   - 7.5% -> tier '5%+'
                        7.5% - 10%  -> tier '7.5%+'
                        10%+        -> tier '10%+'

  3. Matches prior  — the gap day's low is within BOTTOM_TOLERANCE_PCT of
     support           an EARLIER confirmed swing low (occurring before the
                      gap), with a neckline (highest high between them) at
                      least MIN_NECKLINE_PCT above them — otherwise the gap
                      just landed in open space, not on real support.

  4. Still live      — current price must still be within
                      CURRENT_TOLERANCE_PCT of the gap low (hasn't already
                      run away from the level).

Scoring (points system):
  - Base: confirmed gap-down double bottom                  +30
  - Gap size tier: 10%+ +20, 7.5%+ +15, 5%+ +10, 2.5%+ +5
  - Extra touches beyond the required 2 (triple/quad+
    bottom — more retests of the same support = stronger)   +20 each, capped at 3 extra
  - Neckline strength: >=20% +10, >=15% +7, >=10% +5
  - Gap-day volume surge (> 1.5x its 20-day average)         +10
  - Recovered intraday (gap day closed above its open)       +5
  - Deep in zone (position_pct <= 12.5%)                     +5

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
MIN_BARS              = 150   # need enough daily history to find an earlier bottom
GAP_LOOKBACK_DAYS     = 5     # "last day / week" — last 5 trading days
MIN_GAP_PCT           = -2.5  # lowest tier gate; scan captures all 3 tiers, UI filters
MIN_PRIOR_PRICE       = 2.0   # liquidity filter (matches db_gapdown_scanner.py)
MIN_PRIOR_VOLUME      = 200_000
BOTTOM_TOLERANCE_PCT  = 4.0   # how close the gap low must be to the earlier swing low
MIN_NECKLINE_PCT      = 8.0   # peak between the two bottoms must clear this % above them
CURRENT_TOLERANCE_PCT = 8.0   # current price must still be within this % of the gap low
MAX_EXTRA_TOUCH_BONUS = 3     # cap the "extra touches" scoring bonus at this many

# Gap size tiers — (threshold %, score bonus, label). Most negative first.
GAP_TIERS = [(-10.0, 20, '10%+'), (-7.5, 15, '7.5%+'), (-5.0, 10, '5%+'), (-2.5, 5, '2.5%+')]


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


def gap_tier(gap_pct):
    """Return (bonus, label) for the largest tier this gap qualifies for."""
    for threshold, bonus, label in GAP_TIERS:
        if gap_pct <= threshold:
            return bonus, label
    return 0, None


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

    opens  = df['open'].to_numpy(dtype=float)
    highs  = df['high'].to_numpy(dtype=float)
    lows   = df['low'].to_numpy(dtype=float)
    closes = df['close'].to_numpy(dtype=float)
    vols   = df['volume'].to_numpy(dtype=float)
    dates  = df.index
    n      = len(df)

    vol_series = df['volume'].astype(float)
    avg_vol_20 = vol_series.rolling(20, min_periods=10).mean().to_numpy()

    # 2. Find the most recent qualifying gap-down day within the lookback window
    gap_idx = None
    gap_pct = None
    window_start = max(1, n - GAP_LOOKBACK_DAYS)
    for idx in range(n - 1, window_start - 1, -1):
        prior_close = closes[idx - 1]
        prior_vol   = vols[idx - 1]
        if prior_close < MIN_PRIOR_PRICE or prior_vol < MIN_PRIOR_VOLUME:
            continue
        pct = (opens[idx] - prior_close) / prior_close * 100
        if pct <= MIN_GAP_PCT:
            gap_idx = idx
            gap_pct = pct
            break   # most recent qualifying gap wins

    if gap_idx is None:
        return None

    gap_date  = dates[gap_idx]
    gap_open  = float(opens[gap_idx])
    gap_low   = float(lows[gap_idx])
    gap_high  = float(highs[gap_idx])
    gap_close = float(closes[gap_idx])
    gap_vol   = float(vols[gap_idx])
    av20      = avg_vol_20[gap_idx] if not pd.isna(avg_vol_20[gap_idx]) else 0

    if gap_low <= 0:
        return None

    # 3. Current price must still be near the gap low — the level is still live
    if abs(current_price - gap_low) / gap_low * 100 > CURRENT_TOLERANCE_PCT:
        return None

    # 4. Confirmed swing lows from before the gap day, matching the gap low
    zones = compute_swing_zones(df, DEFAULT_LEFT, DEFAULT_RIGHT)
    low_zones = [z for z in zones if z['type'] == 'low' and z['pivot_date'] < gap_date]
    if not low_zones:
        return None

    matches = []
    for z in low_zones:
        diff_pct = abs(z['pivot_price'] - gap_low) / min(z['pivot_price'], gap_low) * 100
        if diff_pct > BOTTOM_TOLERANCE_PCT:
            continue

        seg = df.loc[z['pivot_date']:gap_date]
        if seg.empty:
            continue
        neckline = float(seg['high'].max())
        neckline_date = seg['high'].idxmax()
        lower_of_two = min(z['pivot_price'], gap_low)
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

    touches            = len(matches) + 1   # + the gap day itself
    best_match         = min(matches, key=lambda m: m['diff_pct'])
    strongest_neckline = max(matches, key=lambda m: m['neckline_pct'])
    earliest_match      = min(matches, key=lambda m: m['date'])
    neckline_pct        = strongest_neckline['neckline_pct']
    neckline_price      = strongest_neckline['neckline']

    vol_surge           = bool(av20 and av20 > 0 and gap_vol > av20 * 1.5)
    recovered_intraday  = gap_close > gap_open
    bonus, tier_label    = gap_tier(gap_pct)

    # ── Scoring ────────────────────────────────────────────────────────────
    score = 30
    breakdown = [f"Gap-down double bottom confirmed ({touches}x touches) +30"]

    if bonus:
        score += bonus
        breakdown.append(f"Gap {gap_pct:.1f}% (tier {tier_label}) +{bonus}")

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

    if vol_surge:
        score += 10; breakdown.append("Gap-day volume surge (>1.5x avg) +10")

    if recovered_intraday:
        score += 5; breakdown.append("Recovered intraday (closed above gap open) +5")

    if rng['position_pct'] <= 12.5:
        score += 5; breakdown.append("Deep in zone (<=12.5%) +5")

    # Trade structure: stop below the gap low, target at the neckline
    # (classic double-bottom breakout target), plus the measured-move target.
    stop            = gap_low * 0.97
    target_neckline = neckline_price
    target_measured = neckline_price + (neckline_price - min(gap_low, best_match['price']))
    risk            = current_price - stop
    reward          = target_neckline - current_price
    rr              = round(reward / risk, 2) if risk > 0 else 0

    return {
        'ticker':          ticker,
        'price':           round(current_price, 4),
        'range':           f"${rng['range_low']:.0f}–${rng['range_high']:.0f}",
        'position_pct':    rng['position_pct'],
        'gap_date':        gap_date.strftime('%Y-%m-%d'),
        'gap_pct':         round(gap_pct, 2),
        'gap_tier':        tier_label,
        'gap_open':        round(gap_open, 4),
        'gap_low':         round(gap_low, 4),
        'gap_close':       round(gap_close, 4),
        'vol_surge':       vol_surge,
        'recovered_intraday': recovered_intraday,
        'touches':         touches,
        'bottoms':         [
            {'date': m['date'].strftime('%Y-%m-%d'), 'price': round(m['price'], 4)}
            for m in sorted(matches, key=lambda m: m['date'])
        ] + [{'date': gap_date.strftime('%Y-%m-%d'), 'price': round(gap_low, 4)}],
        'first_bottom_date':  earliest_match['date'].strftime('%Y-%m-%d'),
        'first_bottom_price': round(earliest_match['price'], 4),
        'diff_pct':        round(best_match['diff_pct'], 2),
        'neckline':        round(neckline_price, 4),
        'neckline_date':   strongest_neckline['neckline_date'].strftime('%Y-%m-%d'),
        'neckline_pct':    round(neckline_pct, 2),
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
    log('GAP DOWN DOUBLE BOTTOM SCANNER')
    log('=' * 60)
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("Conditions: price in 0-25% of dollar-range bucket + gap down 2.5%+ "
        "in the last week + gap low matches an earlier confirmed swing low "
        "with a valid neckline (tiers: 2.5%+ / 5%+ / 7.5%+)\n")

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
                log(f"[{i}/{len(tickers)}] {ticker} gap {result['gap_pct']}% on {result['gap_date']} "
                    f"-> {result['touches']}x bottoms @ ~${result['gap_low']:.2f} score {result['score']}")
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
    log(f"COMPLETE — {len(all_results)} gap-down double-bottom signals across {len(tickers)} tickers")
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
