"""
Range Oscillator (Zeiierman) — Python translation
====================================================
Translated from the TradingView Pine Script v6 indicator "Range Oscillator
(Zeiierman)" (see range_ossilator.py for the original Pine source). Measures
how far price has drifted from a volatility-weighted moving average, scaled
by ATR, then colors each reading by how often price has recently "touched"
that same oscillator level — a heatmap of support/resistance in oscillator
space. Meant to be read for divergence against candlestick patterns, not as
a standalone buy/sell signal.

Settings match the TradingView chart used as reference:
  Minimum Range Length   = 26   (length)
  Range Width Multiplier = 5    (mult)
  Number of Heat Levels  = 2    (levels)
  Minimum Touches/Level  = 1    (heat_thresh)
"""

import numpy as np
import pandas as pd

# ── Defaults, matching the reference TradingView settings ──────────────────
DEFAULT_LENGTH      = 26    # Minimum Range Length
DEFAULT_MULT        = 5.0   # Range Width Multiplier
DEFAULT_LEVELS      = 2     # Number of Heat Levels
DEFAULT_HEAT_THRESH = 1     # Minimum Touches per Level
HEAT_LOOKBACK       = 100   # bars of oscillator history the heatmap buckets over

STRONG_BULLISH = '#09ff00'
STRONG_BEARISH = '#ff0000'
WEAK_BULLISH   = '#008000'
WEAK_BEARISH   = '#800000'
TRANSITION     = '#0000ff'


def _true_range(high, low, close):
    prev_close = close.shift(1)
    return pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)


def _atr(high, low, close, period):
    """Wilder-style ATR approximated with an EMA — same convention used
    elsewhere in this codebase (see db_fader_scanner.calc_atr)."""
    tr = _true_range(high, low, close)
    return tr.ewm(span=period, adjust=False, min_periods=period).mean()


def _weighted_ma(close, length):
    """Volatility-weighted moving average. Each of the last `length` closes
    is weighted by the size of its own bar-to-bar % change, so bars with
    bigger moves count for more. Recomputed fresh at every bar (matches the
    Pine source's per-bar loop, not a simple rolling average)."""
    n = len(close)
    ma = np.full(n, np.nan)
    closes = close.to_numpy(dtype=float)

    for t in range(n):
        if t - length < 0:
            continue  # need close[t-length] for the oldest weight's denominator
        sum_w  = 0.0
        sum_wc = 0.0
        for i in range(length):
            c_i  = closes[t - i]
            c_i1 = closes[t - i - 1]
            if c_i1 == 0 or np.isnan(c_i) or np.isnan(c_i1):
                continue
            w = abs(c_i - c_i1) / c_i1
            sum_w  += w
            sum_wc += c_i * w
        ma[t] = sum_wc / sum_w if sum_w != 0 else np.nan

    return pd.Series(ma, index=close.index)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _blend_hex(hex_color, opacity):
    """Dim a hex color toward black by (1 - opacity) — approximates Pine's
    color.new(color, transparency) since we're not rendering to a real
    canvas here, just giving 'hot' levels a more solid color."""
    opacity = _clamp(opacity, 0.0, 1.0)
    r = int(hex_color[1:3], 16) * opacity
    g = int(hex_color[3:5], 16) * opacity
    b = int(hex_color[5:7], 16) * opacity
    return f'#{int(r):02x}{int(g):02x}{int(b):02x}'


def compute_range_oscillator(high, low, close,
                              length=DEFAULT_LENGTH, mult=DEFAULT_MULT,
                              levels=DEFAULT_LEVELS, heat_thresh=DEFAULT_HEAT_THRESH,
                              heat_lookback=HEAT_LOOKBACK):
    """
    high, low, close: pandas Series, same index, chronological order.

    Returns a DataFrame (same index) with columns:
      osc        - oscillator value, ~ -100..+100 under normal conditions,
                   can exceed that range on a breakout
      ma         - the volatility-weighted moving average
      range_atr  - ATR(2000, falls back to ATR(200)) * mult — the box half-width
      trend_dir  - 1 (bullish) / -1 (bearish) / 0 (undefined, start of series)
      breakout   - 'up' / 'down' / None
      touches    - how many of the last `heat_lookback` bars had an oscillator
                   reading in the same heat level as this bar
      color      - hex color approximating the Pine plot color at this bar
    """
    atr_2000  = _atr(high, low, close, 2000)
    atr_200   = _atr(high, low, close, 200)
    atr_raw   = atr_2000.fillna(atr_200)
    range_atr = atr_raw * mult

    ma = _weighted_ma(close, length)

    osc = pd.Series(
        np.where(range_atr != 0, 100 * (close - ma) / range_atr, np.nan),
        index=close.index,
    )

    # Trend direction — sticky, holds the last known direction through na/flat patches
    trend_dir = np.zeros(len(close), dtype=int)
    prev = 0
    for i in range(len(close)):
        c, m = close.iloc[i], ma.iloc[i]
        if pd.isna(c) or pd.isna(m):
            trend_dir[i] = prev
        elif c > m:
            trend_dir[i] = 1
        elif c < m:
            trend_dir[i] = -1
        else:
            trend_dir[i] = prev
        prev = trend_dir[i]
    trend_dir = pd.Series(trend_dir, index=close.index)
    flipped = trend_dir != trend_dir.shift(1)

    breakout = pd.Series([None] * len(close), index=close.index, dtype=object)
    breakout[close > ma + range_atr] = 'up'
    breakout[close < ma - range_atr] = 'down'

    # Heatmap — bucket the trailing `heat_lookback` osc readings into `levels`
    # bands spanning their own recent high/low, count touches per band, then
    # find which band today's reading falls closest to.
    touches = np.full(len(close), np.nan)
    colors  = [None] * len(close)
    osc_vals = osc.to_numpy()

    for t in range(len(close)):
        window = osc_vals[max(0, t - heat_lookback + 1):t + 1]
        window = window[~np.isnan(window)]

        cold_hot_col = WEAK_BULLISH if trend_dir.iloc[t] == 1 else WEAK_BEARISH

        if len(window) == 0 or pd.isna(osc_vals[t]):
            colors[t] = TRANSITION
            continue

        hi, lo = window.max(), window.min()
        rng = hi - lo
        if rng <= 0:
            colors[t] = TRANSITION
            continue

        step = rng / levels
        best_dist, best_cnt = None, 0
        for i in range(levels):
            lvl = lo + step * (i + 0.5)
            cnt = int(np.sum((window >= lvl - step / 2) & (window < lvl + step / 2)))
            dist = abs(osc_vals[t] - lvl)
            if best_dist is None or dist < best_dist:
                best_dist, best_cnt = dist, cnt

        touches[t] = best_cnt
        heat_frac = _clamp((best_cnt - heat_thresh) / 10.0, 0.0, 1.0)
        col = _blend_hex(cold_hot_col, 0.2 + 0.8 * heat_frac)  # floor so cold levels stay visible
        colors[t] = TRANSITION if bool(flipped.iloc[t]) else col

    for i in range(len(close)):
        b = breakout.iloc[i]
        if b == 'up':
            colors[i] = STRONG_BULLISH
        elif b == 'down':
            colors[i] = STRONG_BEARISH

    return pd.DataFrame({
        'osc': osc, 'ma': ma, 'range_atr': range_atr,
        'trend_dir': trend_dir, 'breakout': breakout,
        'touches': touches, 'color': colors,
    }, index=close.index)


if __name__ == '__main__':
    import sys
    from db_channel_scanner import get_connection, get_ticker_data

    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else 'NFLX'
    conn = get_connection()
    df = get_ticker_data(conn, ticker)
    conn.close()

    if df is None or df.empty:
        print(f'No price data for {ticker}')
    else:
        result = compute_range_oscillator(df['high'], df['low'], df['close'])
        print(result.tail(20).to_string())
