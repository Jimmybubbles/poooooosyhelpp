"""
DMI Stochastic Scanner
======================
Converts the "glaz DMI Stoch" Pine Script indicator to Python.

Scans for stocks where:
1. DMI Stochastic entered oversold zone (<=10) - "black arrows"
2. Stayed in oversold for 2-3+ candles (confirming it sat in the zone)
3. Then crossed back above oversold - "green arrow" (buy signal)

This pattern means the stock was deeply oversold with sustained selling pressure
that has now exhausted, triggering a potential reversal.
"""

import pandas as pd
import numpy as np
import os
import talib
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Configuration
CSV_DIR = os.path.join(script_dir, 'updated_Results_for_scan')
OUTPUT_DIR = os.path.join(script_dir, 'buylist')

# Scanner parameters
MIN_PRICE = 1.0
MAX_PRICE = 500.0
MIN_VOLUME = 100000
MIN_BARS_IN_OS = 2  # Minimum black arrows before green arrow
MAX_BARS_IN_OS = 20 # Don't want it stuck in OS forever

# DMI Stochastic parameters (matching Pine Script)
DMI_LENGTH = 32
STOCH_LENGTH = 50
STOCH_SMOOTH = 9
OVERSOLD = 10
OVERBOUGHT = 90
DSL_SIGNAL_PERIOD = 9


def calculate_dmi_stochastic(df):
    """
    Calculate DMI Stochastic - Python conversion of Pine Script.

    Pine Script logic:
        [diplus, diminus, adx] = ta.dmi(DMIlength, 1)
        osc = diplus - diminus
        Stoch = ta.sma(ta.stoch(osc, osc, osc, Stolength), 9)
    """
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    close = df['Close'].values.astype(float)

    # Calculate DMI (DI+ and DI-)
    diplus = talib.PLUS_DI(high, low, close, timeperiod=DMI_LENGTH)
    diminus = talib.MINUS_DI(high, low, close, timeperiod=DMI_LENGTH)

    # Oscillator = DI+ minus DI-
    osc = diplus - diminus

    # Stochastic of the oscillator
    # In Pine: stoch(osc, osc, osc, length) = (osc - lowest(osc, length)) / (highest(osc, length) - lowest(osc, length)) * 100
    osc_series = pd.Series(osc)
    highest = osc_series.rolling(window=STOCH_LENGTH).max()
    lowest = osc_series.rolling(window=STOCH_LENGTH).min()

    raw_stoch = np.where(
        (highest - lowest) != 0,
        (osc_series - lowest) / (highest - lowest) * 100,
        0
    )

    # Smooth with SMA(9)
    stoch = pd.Series(raw_stoch).rolling(window=STOCH_SMOOTH).mean().values

    # DSL (Dynamic Support Level) calculation
    alpha = 2.0 / (1.0 + DSL_SIGNAL_PERIOD)
    levelu = np.zeros(len(stoch))
    leveld = np.zeros(len(stoch))

    for i in range(1, len(stoch)):
        if np.isnan(stoch[i]):
            levelu[i] = levelu[i-1]
            leveld[i] = leveld[i-1]
            continue
        levelu[i] = levelu[i-1]
        leveld[i] = leveld[i-1]
        if stoch[i] > 50:
            levelu[i] = levelu[i-1] + alpha * (stoch[i] - levelu[i-1])
        if stoch[i] < 50:
            leveld[i] = leveld[i-1] + alpha * (stoch[i] - leveld[i-1])

    return stoch, levelu, leveld


def check_green_arrow_signal(stoch):
    """
    Check for the green arrow pattern:
    - Stoch was in oversold (<=10) for MIN_BARS_IN_OS+ candles
    - Then crossed back above oversold

    Returns:
        dict with signal info or None
    """
    if len(stoch) < STOCH_LENGTH + STOCH_SMOOTH + 10:
        return None

    # Current and previous values
    current = stoch[-1]
    prev = stoch[-2]

    if np.isnan(current) or np.isnan(prev):
        return None

    # Green arrow: crossover above oversold
    green_arrow = prev <= OVERSOLD and current > OVERSOLD

    if not green_arrow:
        return None

    # Count how many consecutive bars were in OS zone before this crossover
    bars_in_os = 0
    for i in range(2, min(len(stoch), MAX_BARS_IN_OS + 5)):
        val = stoch[-i]
        if np.isnan(val):
            break
        if val <= OVERSOLD:
            bars_in_os += 1
        else:
            break

    # Need at least MIN_BARS_IN_OS black arrows before the green arrow
    if bars_in_os < MIN_BARS_IN_OS:
        return None

    return {
        'bars_in_os': bars_in_os,
        'stoch_value': current,
        'prev_stoch': prev,
    }


def load_stock_data(ticker):
    """Load stock data from CSV"""
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


def scan_all_stocks():
    """Run the DMI Stochastic scanner"""
    print("=" * 80)
    print("DMI STOCHASTIC GREEN ARROW SCANNER")
    print("Oversold zone (2-3+ black arrows) then green arrow crossover")
    print("=" * 80)
    print()
    print(f"Parameters: DMI={DMI_LENGTH}, Stoch={STOCH_LENGTH}, Smooth={STOCH_SMOOTH}")
    print(f"Oversold={OVERSOLD}, Min bars in OS={MIN_BARS_IN_OS}")
    print()

    # Get tickers from CSV files
    csv_files = [f for f in os.listdir(CSV_DIR) if f.endswith('.csv')]
    tickers = [f[:-4] for f in csv_files]
    print(f"Scanning {len(tickers)} stocks...")
    print()

    results = []
    scanned = 0

    for ticker in tickers:
        df = load_stock_data(ticker)

        if df is None or len(df) < 100:
            continue

        current_price = df['Close'].iloc[-1]
        avg_volume = df['Volume'].iloc[-20:].mean()

        if current_price < MIN_PRICE or current_price > MAX_PRICE:
            continue
        if avg_volume < MIN_VOLUME:
            continue

        scanned += 1

        try:
            stoch, levelu, leveld = calculate_dmi_stochastic(df)
            signal = check_green_arrow_signal(stoch)

            if signal:
                results.append({
                    'ticker': ticker,
                    'price': current_price,
                    'stoch': signal['stoch_value'],
                    'prev_stoch': signal['prev_stoch'],
                    'bars_in_os': signal['bars_in_os'],
                    'volume': df['Volume'].iloc[-1],
                    'avg_volume': avg_volume,
                    'vol_ratio': df['Volume'].iloc[-1] / avg_volume if avg_volume > 0 else 0,
                    'date': df.index[-1],
                })
        except Exception:
            continue

        if scanned % 500 == 0:
            print(f"  Scanned {scanned} stocks... Found {len(results)} signals")

    print(f"\nScan complete! Scanned {scanned} stocks")
    print(f"Found {len(results)} green arrow signals (after {MIN_BARS_IN_OS}+ bars in OS)")
    print()

    return results


def save_results(results):
    """Save results to files"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Sort by bars in OS (more time in OS = stronger signal), then volume
    results.sort(key=lambda x: (x['bars_in_os'], x['vol_ratio']), reverse=True)

    results_file = os.path.join(OUTPUT_DIR, 'dmi_stoch_green_arrow_results.txt')

    with open(results_file, 'w') as f:
        f.write("=" * 100 + "\n")
        f.write("DMI STOCHASTIC GREEN ARROW SCANNER - RESULTS\n")
        f.write("=" * 100 + "\n")
        f.write(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("\n")
        f.write("PATTERN:\n")
        f.write("  1. DMI Stochastic drops into oversold zone (<= 10)\n")
        f.write("  2. Stays in oversold for 2+ candles (black arrows)\n")
        f.write("  3. Crosses back above oversold (green arrow = BUY)\n")
        f.write("\n")
        f.write(f"Parameters: DMI={DMI_LENGTH}, Stoch={STOCH_LENGTH}, Smooth={STOCH_SMOOTH}\n")
        f.write(f"Oversold={OVERSOLD}, Min bars in OS={MIN_BARS_IN_OS}\n")
        f.write(f"\nTotal Signals: {len(results)}\n")
        f.write("\n")

        f.write("=" * 100 + "\n")
        f.write(f"{'Ticker':<8} {'Price':>10} {'Stoch':>8} {'BarsOS':>8} {'VolRatio':>10} {'Signal':<20}\n")
        f.write("-" * 100 + "\n")

        for r in results:
            strength = "STRONG" if r['bars_in_os'] >= 3 else "MODERATE"
            f.write(f"{r['ticker']:<8} ${r['price']:>9.2f} {r['stoch']:>8.1f} "
                   f"{r['bars_in_os']:>8d} {r['vol_ratio']:>10.2f}x {strength:<20}\n")

    print(f"Results saved to: {results_file}")

    # Save TradingView list (comma separated)
    tv_file = os.path.join(OUTPUT_DIR, 'tradingview_dmi_stoch_green.txt')
    with open(tv_file, 'w') as f:
        f.write(",".join(r['ticker'] for r in results[:30]))

    print(f"TradingView list saved to: {tv_file}")

    return results_file


def main():
    results = scan_all_stocks()

    if results:
        save_results(results)

        print("\n" + "=" * 80)
        print("TOP SIGNALS (Most time in oversold)")
        print("=" * 80)
        print(f"{'Ticker':<8} {'Price':>10} {'Stoch':>8} {'Bars in OS':>12} {'Vol':>10}")
        print("-" * 55)

        for r in results[:15]:
            print(f"{r['ticker']:<8} ${r['price']:>9.2f} {r['stoch']:>8.1f} "
                  f"{r['bars_in_os']:>12d} {r['vol_ratio']:>10.2f}x")
    else:
        print("No signals found.")


if __name__ == "__main__":
    main()
