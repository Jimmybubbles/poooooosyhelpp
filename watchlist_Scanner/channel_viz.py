"""
CHANNEL VISUALIZER
==================
Generates PNG charts for the top channel scan results so you can visually
verify the algorithm is finding channels in the right place.

Fetches price data via yfinance (no DB needed — runs locally).
Loads channel results from last_price_channel_results.json.

Run from the watchlist_Scanner folder:
    python channel_viz.py

Charts are saved to: watchlist_Scanner/channel_charts/
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os, sys, json
import yfinance as yf
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR   = os.path.join(BASE_DIR, 'channel_charts')
RESULTS_FILE = os.path.join(BASE_DIR, 'last_price_channel_results.json')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -- Inline helpers (mirrors db_price_channel_scanner, no DB import needed) --

CONFIGS = {
    'daily':   {'bars': 180, 'pivot_lb': 8,  'tolerance': 0.15, 'log_scale': False, 'max_width': 35.0,
                'label': 'Daily',   'sublabel': 'Short channels — weeks to months'},
    'weekly':  {'bars': 78,  'pivot_lb': 5,  'tolerance': 0.15, 'log_scale': False, 'max_width': 50.0,
                'label': 'Weekly',  'sublabel': 'Medium channels — months to ~1.5 years'},
    'monthly': {'bars': 60,  'pivot_lb': 3,  'tolerance': 0.15, 'log_scale': True,  'max_width': 65.0,
                'label': 'Monthly', 'sublabel': 'Mega channels — multi-year'},
}

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

TOP_N = 10   # charts per timeframe


def fetch_price_data(ticker, period='2y'):
    """Fetch OHLCV via yfinance and return a clean DataFrame."""
    try:
        df = yf.download(ticker, period=period, interval='1d',
                         auto_adjust=True, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['open', 'high', 'low', 'close'])
    except Exception as e:
        print(f"    yfinance error: {e}")
        return None


def resample_weekly(df):
    return df.resample('W-FRI').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    ).dropna()


def resample_monthly(df):
    return df.resample('MS').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    ).dropna()


def get_channel_lines(df, cfg):
    """Reconstruct channel lines from price data."""
    n_bars    = cfg['bars']
    lb        = cfg['pivot_lb']
    tol       = cfg['tolerance']
    use_log   = cfg['log_scale']
    max_width = cfg['max_width']
    MIN_R2    = 0.65

    sub = df.tail(n_bars).reset_index(drop=True)
    n   = len(sub)
    if n < max(20, n_bars // 4):
        return None

    raw_h = sub['high'].values.astype(float)
    raw_l = sub['low'].values.astype(float)
    raw_c = sub['close'].values.astype(float)

    if use_log and np.any(raw_l <= 0):
        return None

    wh = np.log(raw_h) if use_log else raw_h
    wl = np.log(raw_l) if use_log else raw_l
    x  = np.arange(n, dtype=float)

    ph = find_pivot_highs(wh.tolist(), lb)
    pl = find_pivot_lows(wl.tolist(), lb)
    if len(ph) < 2 or len(pl) < 2:
        return None

    low_slope, low_intercept, r2 = fit_line(
        [float(i) for i in pl], [float(wl[i]) for i in pl]
    )
    if low_slope is None or low_slope <= 0 or r2 < MIN_R2:
        return None

    lower_line = low_slope * x + low_intercept
    offsets    = [float(wh[i]) - float(lower_line[i]) for i in ph]
    if not offsets or max(offsets) <= 0:
        return None

    ch_offset  = float(max(offsets))
    upper_line = lower_line + ch_offset

    # Width filter -- match scanner behaviour
    c_low_now = float(lower_line[-1])
    if use_log:
        width_pct = float((np.exp(ch_offset) - 1) * 100)
    else:
        width_pct = float(ch_offset / abs(c_low_now) * 100) if c_low_now > 0 else 0.0
    if width_pct > max_width:
        return None

    lower_price = np.exp(lower_line) if use_log else lower_line.copy()
    upper_price = np.exp(upper_line) if use_log else upper_line.copy()

    thresh = ch_offset * tol
    low_touches  = sum(1 for i in pl if abs(float(wl[i]) - float(lower_line[i])) <= thresh)
    high_touches = sum(1 for i in ph if abs(float(wh[i]) - float(upper_line[i])) <= thresh)

    return {
        'n': n, 'x': x,
        'raw_h': raw_h, 'raw_l': raw_l, 'raw_c': raw_c,
        'lower': lower_price, 'upper': upper_price,
        'ph': ph, 'pl': pl,
        'r2': round(r2, 3),
        'low_touches': low_touches,
        'high_touches': high_touches,
        'ch_offset': ch_offset,
        'use_log': use_log,
        'tol': tol,
    }


def plot_channel(ticker, result, lines, tf_label, output_path):
    n     = lines['n']
    x     = lines['x']
    raw_h = lines['raw_h']
    raw_l = lines['raw_l']
    raw_c = lines['raw_c']
    lower = lines['lower']
    upper = lines['upper']
    ph    = lines['ph']
    pl    = lines['pl']
    tol   = lines['tol']
    offset = lines['ch_offset']
    use_log = lines['use_log']

    fig, axes = plt.subplots(1, 2, figsize=(18, 6),
                             gridspec_kw={'width_ratios': [3, 1]})
    fig.patch.set_facecolor('#0a0c14')

    for ax in axes:
        ax.set_facecolor('#0a0c14')
        ax.tick_params(colors='#666', labelsize=8)
        for spine in ax.spines.values():
            spine.set_color('#2a2d3e')
        ax.grid(True, color='#1a1d2e', linewidth=0.5, alpha=0.8)

    def draw_panel(ax, x_range, label_zoom=False):
        xi = x_range
        hi = raw_h[xi]
        li = raw_l[xi]
        ci = raw_c[xi]
        lw = lower[xi]
        up = upper[xi]
        local_x = np.arange(len(xi))

        # OHLC bars
        for j, gi in enumerate(xi):
            color = '#22c55e' if (gi == 0 or raw_c[gi] >= raw_c[gi - 1]) else '#ef4444'
            ax.plot([j, j], [li[j], hi[j]], color=color, linewidth=0.9, alpha=0.65, zorder=2)
            body_h = abs(ci[j] - (raw_c[gi - 1] if gi > 0 else ci[j]))
            body_b = min(ci[j], raw_c[gi - 1] if gi > 0 else ci[j])
            if body_h > 0:
                ax.add_patch(plt.Rectangle(
                    (j - 0.3, body_b), 0.6, body_h,
                    color=color, alpha=0.7, zorder=3
                ))

        # Channel fill
        ax.fill_between(local_x, lw, up, alpha=0.07, color='#60a5fa', zorder=1)

        # Channel lines
        ax.plot(local_x, lw, color='#22c55e', linewidth=2.2, label='Lower line', zorder=5)
        ax.plot(local_x, up, color='#60a5fa', linewidth=2.2, label='Upper line', zorder=5)

        # Signal zone (bottom 10% of channel)
        sig_up = lw + (up - lw) * 0.10
        ax.fill_between(local_x, lw, sig_up, alpha=0.28, color='#f59e0b',
                        label='Signal zone (bottom 10%)', zorder=4)

        # Pivot markers (only on full view)
        if not label_zoom:
            ph_in = [i for i in ph if i in xi]
            pl_in = [i for i in pl if i in xi]
            ph_local = [list(xi).index(i) for i in ph_in]
            pl_local = [list(xi).index(i) for i in pl_in]
            if ph_local:
                ax.scatter(ph_local, raw_h[np.array(ph_in)],
                           color='#60a5fa', s=55, zorder=8, marker='^')
            if pl_local:
                ax.scatter(pl_local, raw_l[np.array(pl_in)],
                           color='#22c55e', s=55, zorder=8, marker='v')

        # Current price line
        curr = raw_c[-1]
        ax.axhline(y=curr, color='#f59e0b', linewidth=1.2, linestyle='--',
                   alpha=0.85, label=f'${curr:,.2f}', zorder=6)

        if not label_zoom:
            ax.legend(loc='upper left', facecolor='#0d0f1a', edgecolor='#2a2d3e',
                      labelcolor='#888', fontsize=7.5, framealpha=0.95)
            ax.set_xlabel('Bars', color='#555', fontsize=8)
        else:
            ax.set_title('Last 30 bars', color='#666', fontsize=8, pad=6)

    # Full view
    draw_panel(axes[0], np.arange(n), label_zoom=False)

    # Zoomed view (last 30 bars)
    zoom_n = min(30, n)
    draw_panel(axes[1], np.arange(n - zoom_n, n), label_zoom=True)

    sc = result['score']
    sc_col = '#22c55e' if sc >= 8 else '#f59e0b' if sc >= 5 else '#888'
    title = (
        f"{ticker}  ·  {tf_label}  ·  "
        f"Score: {sc}  ·  "
        f"In channel: {result['ch_pct']}%  ·  "
        f"R²: {lines['r2']}  ·  "
        f"Touches: {lines['low_touches']}L / {lines['high_touches']}H  ·  "
        f"Width: {result['width_pct']}%"
    )
    fig.suptitle(title, color='#ddd', fontsize=9.5, y=1.01)
    plt.tight_layout(pad=1.5)
    plt.savefig(output_path, dpi=130, facecolor='#0a0c14', bbox_inches='tight')
    plt.close()
    return True


# Test tickers from Jang's images + a few classics — used when no scan results exist
TEST_TICKERS = {
    'daily':   ['TRT', 'AAPL', 'MSFT', 'JPM', 'BAC', 'NVDA', 'AMD', 'GS', 'CAT', 'DE'],
    'weekly':  ['TRT', 'AAPL', 'MSFT', 'JPM', 'XOM', 'CVX', 'UNH', 'WMT', 'HD', 'MCD'],
    'monthly': ['ON', 'OCLL', 'ETSY', 'PLUG', 'NOW', 'ZI', 'AMAT', 'LRCX', 'KLAC', 'ASML'],
}

PERIOD_MAP = {'daily': '2y', 'weekly': '3y', 'monthly': '5y'}


def run_detection_on_ticker(ticker, tf):
    """Fetch data via yfinance and run channel detection. Returns (result_dict, lines) or None."""
    cfg = CONFIGS[tf]
    daily_df = fetch_price_data(ticker, period=PERIOD_MAP[tf])
    if daily_df is None or len(daily_df) < 30:
        return None, None

    if tf == 'weekly':
        df = resample_weekly(daily_df)
    elif tf == 'monthly':
        df = resample_monthly(daily_df)
    else:
        df = daily_df

    lines = get_channel_lines(df, cfg)
    if lines is None:
        return None, None

    # Build a result dict matching what the scanner would produce
    lower_now = lines['lower'][-1]
    upper_now = lines['upper'][-1]
    curr      = lines['raw_c'][-1]
    ch_pct    = float(max(0, min(100, (curr - lower_now) / max(upper_now - lower_now, 1e-6) * 100)))
    width_pct = (upper_now - lower_now) / max(lower_now, 1e-6) * 100

    # Dummy score for test mode (real score comes from scanner)
    s = 0
    if   ch_pct <= 2:  s += 4
    elif ch_pct <= 5:  s += 3
    elif ch_pct <= 7:  s += 2
    elif ch_pct <= 10: s += 1
    r2 = lines['r2']
    if   r2 >= 0.92: s += 3
    elif r2 >= 0.82: s += 2
    elif r2 >= 0.70: s += 1

    result = {
        'ticker':       ticker,
        'ch_pct':       round(ch_pct, 1),
        'width_pct':    round(width_pct, 1),
        'r2':           r2,
        'score':        s,
        'low_touches':  lines['low_touches'],
        'high_touches': lines['high_touches'],
    }
    return result, lines


def main():
    print('=' * 60)
    print('CHANNEL VISUALIZER')
    print('=' * 60)

    use_results_file = os.path.exists(RESULTS_FILE)

    if use_results_file:
        with open(RESULTS_FILE) as f:
            data = json.load(f)
        print(f"Mode      : Scan results file")
        print(f"Scan date : {data['scan_date']}")
        print(f"Daily     : {data['daily']['total']} signals")
        print(f"Weekly    : {data['weekly']['total']} signals")
        print(f"Monthly   : {data['monthly']['total']} signals")
    else:
        print(f"Mode      : TEST (no scan results — testing known tickers via yfinance)")
        print(f"Tickers   : {TEST_TICKERS}")

    print(f"\nGenerating up to {TOP_N} charts per timeframe -> {OUTPUT_DIR}\n")

    for tf in ['daily', 'weekly', 'monthly']:
        cfg   = CONFIGS[tf]
        label = cfg['label']
        print(f"\n-- {label.upper()} --")

        if use_results_file:
            scan_results = data[tf]['results'][:TOP_N]
            ticker_list  = [(r['ticker'], r) for r in scan_results]
        else:
            ticker_list = [(t, None) for t in TEST_TICKERS[tf]]

        found = 0
        for ticker, preset_result in ticker_list:
            print(f"  {ticker}  ", end='', flush=True)
            try:
                if preset_result is not None:
                    # Results from scan file — re-fetch data for plotting
                    daily_df = fetch_price_data(ticker, period=PERIOD_MAP[tf])
                    if daily_df is None:
                        print('SKIP: no data'); continue
                    df = resample_weekly(daily_df) if tf == 'weekly' else \
                         resample_monthly(daily_df) if tf == 'monthly' else daily_df
                    lines = get_channel_lines(df, cfg)
                    result = preset_result
                else:
                    # Test mode — detect from scratch
                    result, lines = run_detection_on_ticker(ticker, tf)

                if lines is None or result is None:
                    print('no channel found'); continue

                ch_pct = result['ch_pct']
                print(f"score={result['score']}  ch%={ch_pct}  R²={result['r2']}  ", end='')

                fname = f"{tf}_{ticker}_score{result['score']}.png"
                fpath = os.path.join(OUTPUT_DIR, fname)
                plot_channel(ticker, result, lines, label, fpath)
                print(f"-> {fname}")
                found += 1

            except Exception as e:
                print(f'ERROR: {e}')

        if found == 0:
            print(f"  No channels detected for any ticker in this timeframe.")

    print(f"\n{'='*60}")
    print(f"Done. Open this folder to view charts:")
    print(f"  {OUTPUT_DIR}".encode('ascii', errors='replace').decode())
    print('=' * 60)


if __name__ == '__main__':
    main()
