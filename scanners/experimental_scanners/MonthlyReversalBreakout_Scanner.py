"""
MONTHLY REVERSAL BREAKOUT SCANNER (The TAN Pattern)
====================================================
Finds stocks following the TAN solar ETF pattern:

SEQUENCE:
1. Reversal candle on monthly chart (hammer/hangman/doji) after a decline
2. Monthly Fader turns GREEN (trend shift confirmed)
3. Channel forms (consolidation/squeeze = energy building)
4. Breakout from channel -> continuation

STAGES (where is the stock in this sequence?):
  STAGE 1: Reversal candle appeared, fader still RED (early - watching)
  STAGE 2: Fader turned GREEN after reversal (trend confirmed - getting ready)
  STAGE 3: Channel forming with green fader (consolidation - preparing entry)
  STAGE 4: Channel breakout with green fader (GO - entering/continuing)

The further along the sequence, the higher confidence the move continues.
"""

import pandas as pd
import numpy as np
import os
import sys
import talib
from datetime import datetime

# Add the watchlist_Scanner directory to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from EFI_Indicator import EFI_Indicator

# Configuration
CSV_DIR = os.path.join(script_dir, 'updated_Results_for_scan')
OUTPUT_DIR = os.path.join(script_dir, 'buylist')

# Parameters
MAX_PRICE = 500.0
MIN_PRICE = 1.0
MIN_DAILY_ROWS = 250  # Need ~1yr daily data for monthly resampling

# Channel parameters
CHANNEL_EMA_FAST = 5
CHANNEL_EMA_SLOW = 26
CHANNEL_ATR_PERIOD = 50
CHANNEL_ATR_MULT = 0.4

# Lookback for reversal candle (months)
REVERSAL_LOOKBACK = 12

# Minimum decline before reversal counts (%)
MIN_DECLINE_PCT = 15


def load_stock_data(ticker):
    """Load daily stock data."""
    csv_path = os.path.join(CSV_DIR, f"{ticker}.csv")
    if not os.path.exists(csv_path):
        return None

    try:
        df = pd.read_csv(csv_path, skiprows=[1, 2])

        if 'Price' in df.columns:
            df.rename(columns={'Price': 'Date'}, inplace=True)

        required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_cols):
            return None

        df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
        df = df.dropna(subset=['Date'])
        df = df.sort_values('Date')
        df.set_index('Date', inplace=True)

        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna()
        return df

    except Exception:
        return None


def analyze_monthly(df):
    """
    Analyze stock on monthly timeframe for the TAN pattern.
    Returns dict with stage and details, or None.
    """
    # Resample to monthly
    monthly = df.resample('MS').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna()

    if len(monthly) < 24:
        return None

    close = monthly['Close'].values.astype(float)
    open_p = monthly['Open'].values.astype(float)
    high = monthly['High'].values.astype(float)
    low = monthly['Low'].values.astype(float)

    # === MONTHLY FADER (HMA) ===
    period = 20
    half_period = period // 2
    sqrt_period = int(np.sqrt(period))

    wma1 = talib.WMA(close, timeperiod=half_period)
    wma2 = talib.WMA(close, timeperiod=period)
    diff_hma = 2 * wma1 - wma2
    hma = talib.WMA(diff_hma, timeperiod=sqrt_period)

    # Current fader state
    current_fader = 'neutral'
    if len(hma) >= 2 and not np.isnan(hma[-1]) and not np.isnan(hma[-2]):
        current_fader = 'green' if hma[-1] > hma[-2] else 'red'

    # Find when fader turned green (scan backwards)
    fader_green_month = None
    fader_green_idx = None
    for i in range(len(hma) - 1, 1, -1):
        if np.isnan(hma[i]) or np.isnan(hma[i-1]):
            continue
        was_red = hma[i-1] <= hma[i-2] if i >= 2 and not np.isnan(hma[i-2]) else False
        is_green = hma[i] > hma[i-1]
        if was_red and is_green:
            fader_green_month = monthly.index[i]
            fader_green_idx = i
            break

    # === CHANNEL DETECTION ===
    ema_fast = talib.EMA(close, timeperiod=CHANNEL_EMA_FAST)
    ema_slow = talib.EMA(close, timeperiod=CHANNEL_EMA_SLOW)

    # Use SMA for ATR approximation on monthly
    atr_vals = talib.ATR(high, low, close, timeperiod=min(CHANNEL_ATR_PERIOD, len(monthly) - 1))
    in_channel = np.abs(ema_fast - ema_slow) < (atr_vals * CHANNEL_ATR_MULT)

    # Count recent channel bars
    channel_bars = 0
    for i in range(len(in_channel) - 1, max(0, len(in_channel) - 6), -1):
        if not np.isnan(in_channel[i]) and in_channel[i]:
            channel_bars += 1

    currently_in_channel = not np.isnan(in_channel[-1]) and in_channel[-1]
    was_in_channel = channel_bars >= 2

    # Detect channel breakout (was in channel, now out, price above upper channel)
    channel_breakout = False
    if was_in_channel and not currently_in_channel:
        channel_upper = ema_slow[-1] + atr_vals[-1] * CHANNEL_ATR_MULT
        if close[-1] > channel_upper:
            channel_breakout = True

    # === REVERSAL CANDLE DETECTION ===
    # Detect hammer, hangman, doji, engulfing on monthly
    hammers = talib.CDLHAMMER(open_p, high, low, close)
    hangmen = talib.CDLHANGINGMAN(open_p, high, low, close)
    dojis = talib.CDLDOJI(open_p, high, low, close)
    engulfing = talib.CDLENGULFING(open_p, high, low, close)
    morning_star = talib.CDLMORNINGSTAR(open_p, high, low, close)

    # Also check manually for long lower wick (hammer-like)
    # A candle with lower wick > 60% of total range
    manual_hammer = np.zeros(len(close))
    for i in range(len(close)):
        total_range = high[i] - low[i]
        if total_range > 0:
            lower_wick = min(close[i], open_p[i]) - low[i]
            if lower_wick / total_range > 0.6:
                manual_hammer[i] = 1

    # Find most recent reversal candle in lookback period
    reversal_month = None
    reversal_type = None
    reversal_idx = None

    for i in range(len(close) - 1, max(0, len(close) - REVERSAL_LOOKBACK - 1), -1):
        if hammers[i] != 0:
            reversal_month = monthly.index[i]
            reversal_type = 'HAMMER'
            reversal_idx = i
            break
        elif hangmen[i] != 0:
            reversal_month = monthly.index[i]
            reversal_type = 'HANGMAN'
            reversal_idx = i
            break
        elif dojis[i] != 0:
            reversal_month = monthly.index[i]
            reversal_type = 'DOJI'
            reversal_idx = i
            break
        elif engulfing[i] > 0:
            reversal_month = monthly.index[i]
            reversal_type = 'BULL_ENGULF'
            reversal_idx = i
            break
        elif morning_star[i] != 0:
            reversal_month = monthly.index[i]
            reversal_type = 'MORNING_STAR'
            reversal_idx = i
            break
        elif manual_hammer[i]:
            reversal_month = monthly.index[i]
            reversal_type = 'LONG_WICK'
            reversal_idx = i
            break

    # === CHECK FOR PRIOR DECLINE ===
    had_decline = False
    decline_pct = 0
    if reversal_idx is not None and reversal_idx >= 3:
        # Look back from reversal for a peak
        lookback_start = max(0, reversal_idx - 12)
        peak = np.max(high[lookback_start:reversal_idx])
        trough = low[reversal_idx]
        if peak > 0:
            decline_pct = (peak - trough) / peak * 100
            had_decline = decline_pct >= MIN_DECLINE_PCT

    # === DETERMINE STAGE ===
    stage = 0
    stage_desc = ''

    has_reversal = reversal_month is not None and had_decline
    fader_is_green = current_fader == 'green'
    fader_after_reversal = (fader_green_idx is not None and reversal_idx is not None
                           and fader_green_idx >= reversal_idx)

    if has_reversal and fader_is_green and fader_after_reversal and channel_breakout:
        stage = 4
        stage_desc = 'BREAKOUT - Channel breakout with green fader'
    elif has_reversal and fader_is_green and fader_after_reversal and was_in_channel:
        stage = 3
        stage_desc = 'CHANNEL - Consolidating with green fader'
    elif has_reversal and fader_is_green and fader_after_reversal:
        stage = 2
        stage_desc = 'TREND CONFIRMED - Fader green after reversal'
    elif has_reversal:
        stage = 1
        stage_desc = 'REVERSAL CANDLE - Watching for fader turn'
    else:
        return None

    if stage == 0:
        return None

    # Calculate months since reversal
    months_since_reversal = len(monthly) - 1 - reversal_idx if reversal_idx is not None else 0

    # Current price info
    current_price = close[-1]
    reversal_price = close[reversal_idx] if reversal_idx is not None else 0
    gain_since_reversal = ((current_price - reversal_price) / reversal_price * 100) if reversal_price > 0 else 0

    return {
        'price': current_price,
        'stage': stage,
        'stage_desc': stage_desc,
        'reversal_type': reversal_type,
        'reversal_month': reversal_month.strftime('%Y-%m') if reversal_month else '',
        'reversal_price': reversal_price,
        'decline_pct': decline_pct,
        'months_since_reversal': months_since_reversal,
        'gain_since_reversal': gain_since_reversal,
        'fader': current_fader,
        'fader_green_month': fader_green_month.strftime('%Y-%m') if fader_green_month else '',
        'channel_bars': channel_bars,
        'in_channel': currently_in_channel,
        'channel_breakout': channel_breakout,
    }


def run_scan():
    """Run the full scan."""
    print("=" * 90)
    print("MONTHLY REVERSAL BREAKOUT SCANNER (The TAN Pattern)")
    print("=" * 90)
    print()
    print("PATTERN: Reversal candle -> Fader GREEN -> Channel -> Breakout")
    print("STAGES:  1=Reversal  2=Fader Green  3=Channel  4=Breakout")
    print()

    csv_files = [f for f in os.listdir(CSV_DIR) if f.endswith('.csv')]
    tickers = [f[:-4] for f in csv_files]
    print(f"Scanning {len(tickers)} tickers...")
    print()

    results = []
    scanned = 0

    for ticker in tickers:
        df = load_stock_data(ticker)

        if df is None or len(df) < MIN_DAILY_ROWS:
            continue

        current_price = df['Close'].iloc[-1]
        if current_price < MIN_PRICE or current_price > MAX_PRICE:
            continue

        scanned += 1

        try:
            result = analyze_monthly(df)
            if result:
                result['ticker'] = ticker
                results.append(result)
        except Exception:
            continue

        if scanned % 500 == 0:
            print(f"  {scanned} scanned... {len(results)} setups found")

    # Sort by stage (highest first), then gain
    results.sort(key=lambda x: (x['stage'], x['gain_since_reversal']), reverse=True)

    print(f"\nScan complete! {scanned} stocks scanned")
    print(f"Found {len(results)} stocks in the TAN pattern")

    # Count by stage
    for s in [4, 3, 2, 1]:
        count = sum(1 for r in results if r['stage'] == s)
        if count > 0:
            labels = {4: 'BREAKOUT', 3: 'CHANNEL', 2: 'FADER GREEN', 1: 'REVERSAL CANDLE'}
            print(f"  Stage {s} ({labels[s]}): {count}")

    return results


def save_results(results):
    """Save results to files."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results_file = os.path.join(OUTPUT_DIR, 'monthly_reversal_breakout_results.txt')

    with open(results_file, 'w') as f:
        f.write("=" * 110 + "\n")
        f.write("MONTHLY REVERSAL BREAKOUT SCANNER (The TAN Pattern)\n")
        f.write("=" * 110 + "\n")
        f.write(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("\n")
        f.write("PATTERN (from TAN solar ETF):\n")
        f.write("  1. Monthly reversal candle (hammer/doji) after 15%+ decline\n")
        f.write("  2. Monthly Fader turns GREEN (trend shift confirmed)\n")
        f.write("  3. Channel forms (squeeze/consolidation = energy building)\n")
        f.write("  4. Breakout from channel -> continuation\n")
        f.write("\n")
        f.write(f"Total Found: {len(results)}\n")

        for s in [4, 3, 2, 1]:
            count = sum(1 for r in results if r['stage'] == s)
            if count > 0:
                labels = {4: 'BREAKOUT', 3: 'CHANNEL', 2: 'FADER GREEN', 1: 'REVERSAL'}
                f.write(f"  Stage {s} ({labels[s]}): {count}\n")

        f.write("\n")

        # Stage 4 - Breakouts (best opportunities)
        stage4 = [r for r in results if r['stage'] == 4]
        if stage4:
            f.write("=" * 110 + "\n")
            f.write("STAGE 4: BREAKOUT (Channel breakout with green fader - HIGHEST CONVICTION)\n")
            f.write("=" * 110 + "\n")
            f.write(f"{'Ticker':<10} {'Price':>8} {'Reversal':<12} {'Type':<12} {'Decline':>8} "
                    f"{'Fader Grn':<10} {'Gain':>8} {'ChBars':>7}\n")
            f.write("-" * 110 + "\n")
            for r in stage4:
                f.write(f"{r['ticker']:<10} ${r['price']:>7.2f} {r['reversal_month']:<12} "
                        f"{r['reversal_type']:<12} {r['decline_pct']:>7.0f}% "
                        f"{r['fader_green_month']:<10} {r['gain_since_reversal']:>+7.1f}% "
                        f"{r['channel_bars']:>7}\n")
            f.write("\n")

        # Stage 3 - Channel forming
        stage3 = [r for r in results if r['stage'] == 3]
        if stage3:
            f.write("=" * 110 + "\n")
            f.write("STAGE 3: CHANNEL (Consolidating with green fader - WATCH FOR BREAKOUT)\n")
            f.write("=" * 110 + "\n")
            f.write(f"{'Ticker':<10} {'Price':>8} {'Reversal':<12} {'Type':<12} {'Decline':>8} "
                    f"{'Fader Grn':<10} {'Gain':>8} {'ChBars':>7}\n")
            f.write("-" * 110 + "\n")
            for r in stage3:
                f.write(f"{r['ticker']:<10} ${r['price']:>7.2f} {r['reversal_month']:<12} "
                        f"{r['reversal_type']:<12} {r['decline_pct']:>7.0f}% "
                        f"{r['fader_green_month']:<10} {r['gain_since_reversal']:>+7.1f}% "
                        f"{r['channel_bars']:>7}\n")
            f.write("\n")

        # Stage 2 - Fader green
        stage2 = [r for r in results if r['stage'] == 2]
        if stage2:
            f.write("=" * 110 + "\n")
            f.write("STAGE 2: FADER GREEN (Trend confirmed after reversal - GETTING READY)\n")
            f.write("=" * 110 + "\n")
            f.write(f"{'Ticker':<10} {'Price':>8} {'Reversal':<12} {'Type':<12} {'Decline':>8} "
                    f"{'Fader Grn':<10} {'Gain':>8}\n")
            f.write("-" * 110 + "\n")
            for r in stage2[:30]:
                f.write(f"{r['ticker']:<10} ${r['price']:>7.2f} {r['reversal_month']:<12} "
                        f"{r['reversal_type']:<12} {r['decline_pct']:>7.0f}% "
                        f"{r['fader_green_month']:<10} {r['gain_since_reversal']:>+7.1f}%\n")
            f.write("\n")

        # Stage 1 - Reversal only
        stage1 = [r for r in results if r['stage'] == 1]
        if stage1:
            f.write("=" * 110 + "\n")
            f.write("STAGE 1: REVERSAL CANDLE (Watching for fader turn - EARLY)\n")
            f.write("=" * 110 + "\n")
            f.write(f"{'Ticker':<10} {'Price':>8} {'Reversal':<12} {'Type':<12} {'Decline':>8} "
                    f"{'Fader':>8} {'Gain':>8}\n")
            f.write("-" * 110 + "\n")
            for r in stage1[:30]:
                f.write(f"{r['ticker']:<10} ${r['price']:>7.2f} {r['reversal_month']:<12} "
                        f"{r['reversal_type']:<12} {r['decline_pct']:>7.0f}% "
                        f"{r['fader'].upper():>8} {r['gain_since_reversal']:>+7.1f}%\n")

        f.write("\n" + "=" * 110 + "\n")
        # TradingView lists by stage
        for s in [4, 3, 2]:
            stage_tickers = [r['ticker'] for r in results if r['stage'] == s]
            if stage_tickers:
                labels = {4: 'BREAKOUT', 3: 'CHANNEL', 2: 'FADER_GREEN'}
                f.write(f"TRADINGVIEW STAGE {s} ({labels[s]}): {','.join(stage_tickers[:30])}\n")

        f.write("=" * 110 + "\n")

    print(f"\nResults saved to: {results_file}")

    # TradingView list - prioritize stage 4 and 3
    tv_file = os.path.join(OUTPUT_DIR, 'tradingview_monthly_reversal.txt')
    top_tickers = ([r['ticker'] for r in results if r['stage'] == 4] +
                   [r['ticker'] for r in results if r['stage'] == 3] +
                   [r['ticker'] for r in results if r['stage'] == 2])
    with open(tv_file, 'w') as f:
        f.write(",".join(top_tickers[:30]))
    print(f"TradingView list saved to: {tv_file}")

    return results_file


def main():
    results = run_scan()

    if results:
        save_results(results)

        # Print top results by stage
        print("\n" + "=" * 90)
        for s in [4, 3, 2]:
            stage_results = [r for r in results if r['stage'] == s]
            if stage_results:
                labels = {4: 'BREAKOUT', 3: 'CHANNEL', 2: 'FADER GREEN'}
                print(f"\nSTAGE {s}: {labels[s]}")
                print("-" * 90)
                print(f"{'Ticker':<10} {'Price':>8} {'Reversal':<12} {'Type':<12} "
                      f"{'Decline':>8} {'Gain':>8}")
                for r in stage_results[:10]:
                    print(f"{r['ticker']:<10} ${r['price']:>7.2f} {r['reversal_month']:<12} "
                          f"{r['reversal_type']:<12} {r['decline_pct']:>7.0f}% "
                          f"{r['gain_since_reversal']:>+7.1f}%")
    else:
        print("No patterns found.")


if __name__ == "__main__":
    main()
