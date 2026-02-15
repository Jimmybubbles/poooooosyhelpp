"""
RANGE LEVEL SCANNER
====================
Based on the theory that:
1. Price settles/ranges at 25% and 75% levels within dollar ranges
2. Price passes through 0%, 50%, and 100% levels
3. Price rarely holds beyond 3 ranges from a pivot
4. Built-in R:R: Enter at 25%, stop at 0%, target at 75% (1:2 risk/reward)

TWO TRADE TYPES:
1. Within-Range: Enter at 25%, target 75% (same range)
2. Range-Change: Enter at 75%, target 25% of next range up

Inspired by Mandelbrot's fractal theory applied to price structure.
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime
import sys
import talib

# Add the watchlist_Scanner directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from EFI_Indicator import EFI_Indicator

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'range_level_scan_results.txt')
tradingview_file = os.path.join(buylist_dir, 'tradingview_range_levels.txt')


def get_range_info(price):
    """
    Determine which range a price is in and calculate quarter levels.

    For stocks:
    - $0-10: Use $1 ranges (1-2, 2-3, etc.)
    - $10-100: Use $10 ranges (10-20, 20-30, etc.)
    - $100-500: Use $50 ranges (100-150, 150-200, etc.)
    - $500+: Use $100 ranges (500-600, 600-700, etc.)

    Returns:
        dict with range_low, range_high, levels (0%, 25%, 50%, 75%, 100%),
        position_in_range, and position_pct
    """
    if price <= 0:
        return None

    # Determine range size based on price
    if price < 10:
        range_size = 1.0
        range_low = int(price)
        if range_low == 0:
            range_low = 0
            range_size = 1.0
    elif price < 100:
        range_size = 10.0
        range_low = int(price / 10) * 10
    elif price < 500:
        range_size = 50.0
        range_low = int(price / 50) * 50
    else:
        range_size = 100.0
        range_low = int(price / 100) * 100

    range_high = range_low + range_size

    # Calculate quarter levels
    levels = {
        'L0': range_low,                           # 0%
        'L25': range_low + (range_size * 0.25),    # 25%
        'L50': range_low + (range_size * 0.50),    # 50%
        'L75': range_low + (range_size * 0.75),    # 75%
        'L100': range_high                          # 100%
    }

    # Position in range (0-100%)
    position_pct = ((price - range_low) / range_size) * 100

    # Determine which zone price is in
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
        'range_low': range_low,
        'range_high': range_high,
        'range_size': range_size,
        'levels': levels,
        'position_pct': position_pct,
        'zone': zone
    }


def count_ranges_from_pivot(df, current_idx, lookback=60):
    """
    Count how many ranges price has traveled from a recent pivot low.

    Returns:
        pivot_low, pivot_date, ranges_traveled
    """
    if current_idx < lookback:
        lookback = current_idx

    if lookback < 5:
        return None, None, 0

    # Find the lowest low in lookback period
    lows = df['Low'].iloc[current_idx - lookback:current_idx + 1]
    pivot_idx = lows.idxmin()
    pivot_low = lows.min()

    current_price = df['Close'].iloc[current_idx]

    # Get range info for pivot and current
    pivot_range = get_range_info(pivot_low)
    current_range = get_range_info(current_price)

    if pivot_range is None or current_range is None:
        return pivot_low, pivot_idx, 0

    # Count ranges traveled
    ranges_traveled = (current_range['range_low'] - pivot_range['range_low']) / pivot_range['range_size']

    return pivot_low, pivot_idx, ranges_traveled


def calculate_fader(df, current_idx):
    """Calculate Fader indicator color (simplified)"""
    if current_idx < 50:
        return 'neutral'

    close = df['Close'].values

    # Use HMA-style smoothing
    period = 20
    half_period = period // 2
    sqrt_period = int(np.sqrt(period))

    wma1 = talib.WMA(close, timeperiod=half_period)
    wma2 = talib.WMA(close, timeperiod=period)

    diff = 2 * wma1 - wma2
    hma = talib.WMA(diff, timeperiod=sqrt_period)

    if current_idx >= 2:
        if hma[current_idx] > hma[current_idx - 1]:
            return 'green'
        else:
            return 'red'

    return 'neutral'


def detect_range_setup(ticker_symbol, results_dir):
    """
    Detect range level setups.

    Looking for:
    1. Price at 25% level (entry for within-range trade to 75%)
    2. Price at 75% level (entry for range-change trade to next 25%)
    3. Reversal signals (Fader green, EFI improving)
    4. Not at 3+ ranges from pivot (overextended)
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker_symbol}.csv")

        if not os.path.exists(csv_file):
            return None

        # Read CSV
        df = pd.read_csv(csv_file, skiprows=[1, 2])

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

        if len(df) < 70:
            return None

        current_idx = len(df) - 1
        current_date = df.index[current_idx]

        if pd.isna(current_date):
            return None

        current_price = df['Close'].iloc[current_idx]

        # Skip very low priced stocks (under $0.50) - too much noise
        if current_price < 0.50:
            return None

        # Get range info
        range_info = get_range_info(current_price)
        if range_info is None:
            return None

        # Only interested in 25% and 75% zones (settling zones)
        if range_info['zone'] not in ['NEAR_25', 'NEAR_75']:
            return None

        # Calculate EFI
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)

        current_fi_color = efi_results['fi_color'].iloc[current_idx]
        current_force_index = efi_results['force_index'].iloc[current_idx]
        current_norm_price = efi_results['normalized_price'].iloc[current_idx]

        # Calculate Fader
        fader_color = calculate_fader(df, current_idx)

        # Count ranges from pivot
        pivot_low, pivot_date, ranges_traveled = count_ranges_from_pivot(df, current_idx, lookback=60)

        # Skip if overextended (3+ ranges)
        if ranges_traveled >= 3:
            return None

        # Determine trade type
        if range_info['zone'] == 'NEAR_25':
            trade_type = 'WITHIN_RANGE'
            entry_level = range_info['levels']['L25']
            stop_level = range_info['levels']['L0']
            target_level = range_info['levels']['L75']
            risk = entry_level - stop_level
            reward = target_level - entry_level
        else:  # NEAR_75
            trade_type = 'RANGE_CHANGE'
            entry_level = range_info['levels']['L75']
            stop_level = range_info['levels']['L50']
            # Target is 25% of NEXT range
            next_range_low = range_info['range_high']
            target_level = next_range_low + (range_info['range_size'] * 0.25)
            risk = entry_level - stop_level
            reward = target_level - entry_level

        rr_ratio = reward / risk if risk > 0 else 0

        # Quality scoring
        quality_score = 0
        signal_notes = []

        # Points for Fader green (momentum confirming)
        if fader_color == 'green':
            quality_score += 25
            signal_notes.append("Fader GREEN")

        # Points for EFI improving
        if current_fi_color in ['lime', 'green']:
            quality_score += 25
            signal_notes.append("EFI bullish")
        elif current_fi_color == 'orange' and current_force_index > efi_results['force_index'].iloc[current_idx - 1]:
            quality_score += 15
            signal_notes.append("EFI improving")

        # Points for being close to the level (tighter entry)
        level_target = range_info['levels']['L25'] if trade_type == 'WITHIN_RANGE' else range_info['levels']['L75']
        distance_from_level = abs(current_price - level_target)
        distance_pct = (distance_from_level / range_info['range_size']) * 100

        if distance_pct < 5:
            quality_score += 20
            signal_notes.append("Tight to level")
        elif distance_pct < 10:
            quality_score += 10

        # Points for good R:R
        if rr_ratio >= 2:
            quality_score += 15
            signal_notes.append(f"R:R {rr_ratio:.1f}")
        elif rr_ratio >= 1.5:
            quality_score += 10

        # Points for not being overextended
        if ranges_traveled < 1:
            quality_score += 15
            signal_notes.append("Fresh move")
        elif ranges_traveled < 2:
            quality_score += 10

        # Minimum quality threshold
        if quality_score < 30:
            return None

        return {
            'ticker': ticker_symbol,
            'date': current_date.strftime('%m/%d/%Y'),
            'price': current_price,
            'trade_type': trade_type,
            'range_low': range_info['range_low'],
            'range_high': range_info['range_high'],
            'range_size': range_info['range_size'],
            'position_pct': range_info['position_pct'],
            'zone': range_info['zone'],
            'L0': range_info['levels']['L0'],
            'L25': range_info['levels']['L25'],
            'L50': range_info['levels']['L50'],
            'L75': range_info['levels']['L75'],
            'L100': range_info['levels']['L100'],
            'entry_level': entry_level,
            'stop_level': stop_level,
            'target_level': target_level,
            'risk': risk,
            'reward': reward,
            'rr_ratio': rr_ratio,
            'fader_color': fader_color,
            'efi_color': current_fi_color,
            'force_index': current_force_index,
            'norm_price': current_norm_price,
            'pivot_low': pivot_low,
            'ranges_from_pivot': ranges_traveled,
            'quality_score': quality_score,
            'signal_notes': signal_notes
        }

    except Exception as e:
        return None


def run_range_level_scan():
    """Run the Range Level Scanner"""
    print("=" * 100)
    print("RANGE LEVEL SCANNER")
    print("=" * 100)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("THEORY:")
    print("  - Price settles at 25% and 75% levels within ranges")
    print("  - Price passes through 0%, 50%, 100% levels")
    print("  - Price rarely holds beyond 3 ranges from pivot")
    print()
    print("TRADE TYPES:")
    print("  1. WITHIN_RANGE: Enter at 25%, stop at 0%, target 75% (same range)")
    print("  2. RANGE_CHANGE: Enter at 75%, stop at 50%, target 25% of next range")
    print()
    print("=" * 100)
    print()

    # Get ticker list
    csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
    tickers = [f[:-4] for f in csv_files]

    print(f"Scanning {len(tickers)} stocks...")
    print()

    all_setups = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 500 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} stocks scanned...")

        result = detect_range_setup(ticker, results_dir)

        if result:
            all_setups.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(all_setups)} range level setups")
    print()

    if not all_setups:
        print("No range level setups found.")
        return

    # Sort by quality score
    all_setups.sort(key=lambda x: x['quality_score'], reverse=True)

    # Separate by trade type
    within_range = [s for s in all_setups if s['trade_type'] == 'WITHIN_RANGE']
    range_change = [s for s in all_setups if s['trade_type'] == 'RANGE_CHANGE']

    # Generate report
    report_lines = []
    report_lines.append("=" * 100)
    report_lines.append("RANGE LEVEL SCANNER - RESULTS")
    report_lines.append("=" * 100)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("THEORY:")
    report_lines.append("  Price settles at 25%/75% levels, passes through 0%/50%/100%")
    report_lines.append("  Built-in 1:2 risk/reward when trading level to level")
    report_lines.append("")
    report_lines.append(f"Total Setups Found: {len(all_setups)}")
    report_lines.append(f"  WITHIN_RANGE (25% -> 75%): {len(within_range)}")
    report_lines.append(f"  RANGE_CHANGE (75% -> next 25%): {len(range_change)}")
    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    # TOP 20 BY QUALITY
    report_lines.append("TOP 20 SETUPS (Highest Quality Score):")
    report_lines.append("=" * 100)
    report_lines.append(f"{'Ticker':<8} {'Price':<8} {'Type':<14} {'Range':<10} {'Entry':<8} {'Stop':<8} {'Target':<8} {'R:R':<6} {'Score':<6}")
    report_lines.append("-" * 100)

    for setup in all_setups[:20]:
        report_lines.append(
            f"{setup['ticker']:<8} "
            f"${setup['price']:<7.2f} "
            f"{setup['trade_type']:<14} "
            f"${setup['range_low']:.0f}-${setup['range_high']:.0f}   "
            f"${setup['entry_level']:<7.2f} "
            f"${setup['stop_level']:<7.2f} "
            f"${setup['target_level']:<7.2f} "
            f"{setup['rr_ratio']:<6.1f} "
            f"{setup['quality_score']:<6}"
        )

    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    # WITHIN RANGE SETUPS (25% to 75%)
    if within_range:
        report_lines.append("WITHIN-RANGE SETUPS (Entry at 25%, Target 75%):")
        report_lines.append("=" * 100)
        report_lines.append(f"{'Ticker':<8} {'Price':<8} {'Range':<10} {'Pos%':<6} {'Entry':<8} {'Stop':<8} {'Target':<8} {'Fader':<8} {'EFI':<8}")
        report_lines.append("-" * 100)

        for setup in within_range[:30]:
            report_lines.append(
                f"{setup['ticker']:<8} "
                f"${setup['price']:<7.2f} "
                f"${setup['range_low']:.0f}-${setup['range_high']:.0f}   "
                f"{setup['position_pct']:<5.0f}% "
                f"${setup['entry_level']:<7.2f} "
                f"${setup['stop_level']:<7.2f} "
                f"${setup['target_level']:<7.2f} "
                f"{setup['fader_color']:<8} "
                f"{setup['efi_color']:<8}"
            )

        report_lines.append("")
        report_lines.append("=" * 100)
        report_lines.append("")

    # RANGE CHANGE SETUPS (75% to next 25%)
    if range_change:
        report_lines.append("RANGE-CHANGE SETUPS (Entry at 75%, Target next 25%):")
        report_lines.append("=" * 100)
        report_lines.append(f"{'Ticker':<8} {'Price':<8} {'Range':<10} {'Pos%':<6} {'Entry':<8} {'Stop':<8} {'Target':<8} {'Fader':<8} {'EFI':<8}")
        report_lines.append("-" * 100)

        for setup in range_change[:30]:
            report_lines.append(
                f"{setup['ticker']:<8} "
                f"${setup['price']:<7.2f} "
                f"${setup['range_low']:.0f}-${setup['range_high']:.0f}   "
                f"{setup['position_pct']:<5.0f}% "
                f"${setup['entry_level']:<7.2f} "
                f"${setup['stop_level']:<7.2f} "
                f"${setup['target_level']:<7.2f} "
                f"{setup['fader_color']:<8} "
                f"{setup['efi_color']:<8}"
            )

        report_lines.append("")
        report_lines.append("=" * 100)
        report_lines.append("")

    # Trading guide
    report_lines.append("TRADING GUIDE:")
    report_lines.append("-" * 100)
    report_lines.append("")
    report_lines.append("WITHIN-RANGE TRADE (25% -> 75%):")
    report_lines.append("  - Entry: Price at 25% level of range (e.g., $1.25 in $1-2 range)")
    report_lines.append("  - Stop: Below 0% level (e.g., below $1.00)")
    report_lines.append("  - Target: 75% level (e.g., $1.75)")
    report_lines.append("  - Risk: 25 cents, Reward: 50 cents = 1:2 R:R")
    report_lines.append("")
    report_lines.append("RANGE-CHANGE TRADE (75% -> next 25%):")
    report_lines.append("  - Entry: Price at 75% level (e.g., $1.75 in $1-2 range)")
    report_lines.append("  - Stop: Below 50% level (e.g., below $1.50)")
    report_lines.append("  - Target: 25% of next range (e.g., $2.25 in $2-3 range)")
    report_lines.append("  - Risk: 25 cents, Reward: 50 cents = 1:2 R:R")
    report_lines.append("")
    report_lines.append("CONFIRMATION SIGNALS:")
    report_lines.append("  - Fader GREEN = momentum confirming")
    report_lines.append("  - EFI lime/green = buying pressure")
    report_lines.append("  - Ranges from pivot < 3 = not overextended")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)

    os.makedirs(buylist_dir, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Create TradingView list
    with open(tradingview_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("RANGE LEVEL SETUPS - TRADINGVIEW LIST\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total setups: {len(all_setups)}\n")
        f.write("=" * 80 + "\n\n")

        f.write("ALL SETUPS:\n")
        f.write("-" * 80 + "\n")
        tickers = [s['ticker'] for s in all_setups]
        f.write(",".join(tickers) + "\n\n")

        if within_range:
            f.write("WITHIN-RANGE SETUPS (25% to 75%):\n")
            f.write("-" * 80 + "\n")
            tickers = [s['ticker'] for s in within_range]
            f.write(",".join(tickers) + "\n\n")

        if range_change:
            f.write("RANGE-CHANGE SETUPS (75% to next 25%):\n")
            f.write("-" * 80 + "\n")
            tickers = [s['ticker'] for s in range_change]
            f.write(",".join(tickers) + "\n\n")

    # Print to console
    print(report_text)
    print(f"\nReport saved to: {output_file}")
    print(f"TradingView list saved to: {tradingview_file}")

    return all_setups


if __name__ == "__main__":
    run_range_level_scan()
