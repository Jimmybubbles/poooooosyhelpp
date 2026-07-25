"""
Swing Points and Liquidity — Python translation
=================================================
Translated from "Swing Points and Liquidity - By Leviathan" (Pine v5 — see
Swing_indicator.py for the original source). Finds confirmed swing high/low
pivots (a bar that's the extreme within a left/right lookback window) and
tracks each one as an open "liquidity zone" at that price level until a
later bar's high/low trades back through it ("filled").

The original indicator's Open Interest overlay (Binance/BitMEX/Kraken
perpetual futures data) is crypto-specific and dropped here — this platform
scans US/ASX equities, which don't have that data. Everything else (the
actual swing-point / liquidity-zone detection) is a straight port.

A swing LOW is the "green" (buy-colored) zone in the original indicator —
a resting-liquidity level below price that often acts as support. A swing
HIGH is the "red" (sell-colored) zone above price.

Defaults match the reference Pine settings:
  Bars Left  = 15
  Bars Right = 10   (a pivot only confirms — "prints" — once this many
                      bars have passed with nothing more extreme; the box
                      itself is drawn back at the actual swing bar)
"""

import numpy as np
import pandas as pd

DEFAULT_LEFT  = 15
DEFAULT_RIGHT = 10


def find_pivot_lows(low, left=DEFAULT_LEFT, right=DEFAULT_RIGHT):
    """
    Indices (0-based, into `low`) confirmed as pivot lows — Pine's
    ta.pivotlow(left, right) semantics: low[i] must be <= every value in
    the window [i-left, i+right]. The pivot isn't knowable until bar
    i+right (that's when it "prints" on the original indicator).
    """
    vals = np.asarray(low, dtype=float)
    n = len(vals)
    pivots = []
    for i in range(left, n - right):
        window = vals[i - left: i + right + 1]
        if vals[i] <= window.min():
            pivots.append(i)
    return pivots


def find_pivot_highs(high, left=DEFAULT_LEFT, right=DEFAULT_RIGHT):
    """Mirror of find_pivot_lows for swing highs (Pine ta.pivothigh)."""
    vals = np.asarray(high, dtype=float)
    n = len(vals)
    pivots = []
    for i in range(left, n - right):
        window = vals[i - left: i + right + 1]
        if vals[i] >= window.max():
            pivots.append(i)
    return pivots


def compute_swing_zones(df, left=DEFAULT_LEFT, right=DEFAULT_RIGHT):
    """
    df: DataFrame with 'high'/'low' columns, DatetimeIndex, chronological.

    Returns a list of dicts, one per confirmed swing point (both types),
    each tracked forward to see if/when it's since been "filled" (a later
    bar's high/low trading back through the level):
      type          - 'low' (green) or 'high' (red)
      pivot_date    - the bar where the actual extreme occurred
      pivot_price   - the swing price level
      confirm_date  - the bar `right` places later, when the swing first
                       becomes knowable — this is when it "prints"
      filled        - whether a later bar has traded back through the level
      filled_date   - date it was filled, or None if still open
    """
    highs = df['high'].to_numpy(dtype=float)
    lows  = df['low'].to_numpy(dtype=float)
    dates = df.index

    def _filled_after(level, confirm_idx):
        for j in range(confirm_idx + 1, len(dates)):
            if highs[j] >= level >= lows[j]:
                return dates[j]
        return None

    zones = []
    for i in find_pivot_lows(lows, left, right):
        level = float(lows[i])
        confirm_idx = i + right
        filled_date = _filled_after(level, confirm_idx)
        zones.append({
            'type':         'low',
            'pivot_date':   dates[i],
            'pivot_price':  level,
            'confirm_date': dates[confirm_idx],
            'filled':       filled_date is not None,
            'filled_date':  filled_date,
        })

    for i in find_pivot_highs(highs, left, right):
        level = float(highs[i])
        confirm_idx = i + right
        filled_date = _filled_after(level, confirm_idx)
        zones.append({
            'type':         'high',
            'pivot_date':   dates[i],
            'pivot_price':  level,
            'confirm_date': dates[confirm_idx],
            'filled':       filled_date is not None,
            'filled_date':  filled_date,
        })

    zones.sort(key=lambda z: z['confirm_date'])
    return zones


if __name__ == '__main__':
    import sys
    from db_channel_scanner import get_connection, get_ticker_data
    from db_price_channel_scanner import resample_weekly

    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else 'NFLX'
    conn = get_connection()
    df = get_ticker_data(conn, ticker)
    conn.close()

    if df is None or df.empty:
        print(f'No price data for {ticker}')
    else:
        weekly = resample_weekly(df)
        for z in compute_swing_zones(weekly)[-10:]:
            print(z)
