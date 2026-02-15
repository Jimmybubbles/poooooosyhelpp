"""
CHANNEL + RANGE LEVEL SHAKEOUT SCANNER
======================================
Finds the EME-style setup:
1. Stock was consolidating in a channel near a range level (like 25%)
2. Price dropped/shook out to touch the 0% level (or below)
3. Now recovering back into the range
4. Target: 75% level of the range

This combines channel detection with range level theory.
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'channel_range_shakeout_results.txt')


def get_range_info(price):
    """Get range levels for a price"""
    if price <= 0:
        return None

    if price < 10:
        range_size = 1.0
        range_low = int(price)
    elif price < 100:
        range_size = 10.0
        range_low = int(price / 10) * 10
    elif price < 500:
        range_size = 50.0
        range_low = int(price / 50) * 50
    else:
        range_size = 100.0
        range_low = int(price / 100) * 100

    return {
        'range_low': range_low,
        'range_high': range_low + range_size,
        'range_size': range_size,
        'L0': range_low,
        'L25': range_low + (range_size * 0.25),
        'L50': range_low + (range_size * 0.50),
        'L75': range_low + (range_size * 0.75),
        'L100': range_low + range_size
    }


def detect_channel_at_level(prices, range_info, lookback=15):
    """
    Detect if price was consolidating near a range level.
    Returns the level it was consolidating near (L25, L50, L75) or None.
    """
    if len(prices) < lookback:
        return None, 0

    channel_prices = prices[-lookback:]
    avg_price = np.mean(channel_prices)
    price_range = max(channel_prices) - min(channel_prices)
    range_size = range_info['range_size']

    # Check if price range is tight (consolidation) - less than 15% of range
    if price_range > range_size * 0.20:
        return None, 0

    # Check which level the consolidation was near
    levels = [
        ('L25', range_info['L25']),
        ('L50', range_info['L50']),
        ('L75', range_info['L75']),
    ]

    for level_name, level_price in levels:
        # If average was within 5% of range from level
        if abs(avg_price - level_price) <= range_size * 0.10:
            channel_tightness = 1 - (price_range / (range_size * 0.20))  # 0 to 1
            return level_name, channel_tightness

    return None, 0


def find_shakeout_setup(ticker, results_dir, channel_lookback=15, shakeout_lookback=10):
    """
    Find the channel + range shakeout setup:
    1. Was consolidating in a channel near a range level
    2. Recently dropped to touch 0% level (shakeout)
    3. Now recovering
    """
    csv_file = os.path.join(results_dir, f"{ticker}.csv")

    if not os.path.exists(csv_file):
        return None

    try:
        df = pd.read_csv(csv_file, skiprows=[1, 2])

        if 'Price' in df.columns:
            df.rename(columns={'Price': 'Date'}, inplace=True)

        required_cols = ['Date', 'Open', 'High', 'Low', 'Close']
        if not all(col in df.columns for col in required_cols):
            return None

        df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
        df = df.dropna(subset=['Date'])
        df = df.sort_values('Date')

        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna()

        # Need enough data
        min_data = channel_lookback + shakeout_lookback + 5
        if len(df) < min_data:
            return None

        # Get recent data
        df = df.tail(50)

        current_price = df['Close'].iloc[-1]
        current_date = df['Date'].iloc[-1]

        # Get range info based on current price
        range_info = get_range_info(current_price)
        if range_info is None:
            return None

        # Step 1: Check for prior channel/consolidation (before recent action)
        # Look at prices from channel_lookback+shakeout_lookback to shakeout_lookback ago
        channel_start = -(channel_lookback + shakeout_lookback)
        channel_end = -shakeout_lookback

        if abs(channel_start) > len(df):
            return None

        channel_prices = df['Close'].iloc[channel_start:channel_end].values

        # Check if there was a channel near a range level
        channel_level, channel_tightness = detect_channel_at_level(
            channel_prices, range_info, lookback=channel_lookback
        )

        # Step 2: Check for shakeout (drop to 0% level) in recent days
        recent_lows = df['Low'].iloc[-shakeout_lookback:].values
        shakeout_low = min(recent_lows)

        # Did price touch or go below the 0% level?
        touched_L0 = shakeout_low <= range_info['L0'] * 1.02  # 2% tolerance
        went_below_L0 = shakeout_low < range_info['L0']

        if not touched_L0:
            return None

        # Step 3: Check for recovery - current price back above L0
        recovering = current_price > range_info['L0']
        recovery_strength = (current_price - shakeout_low) / range_info['range_size'] * 100

        if not recovering:
            return None

        # Calculate setup quality
        quality = 0
        notes = []

        if channel_level:
            quality += 2
            notes.append(f"Channel at {channel_level}")

        if went_below_L0:
            quality += 2
            notes.append("Shakeout below L0")
        elif touched_L0:
            quality += 1
            notes.append("Touched L0")

        if recovery_strength > 10:
            quality += 1
            notes.append(f"Strong recovery ({recovery_strength:.0f}%)")

        # Current position in range
        position_in_range = (current_price - range_info['L0']) / range_info['range_size'] * 100

        # Best setups: was at L25 channel, shook out to L0, now recovering
        if channel_level == 'L25' and went_below_L0:
            quality += 2
            notes.append("CLASSIC L25 SHAKEOUT")

        if quality < 2:
            return None

        # Calculate trade levels
        entry = current_price
        stop = range_info['L0'] - (range_info['range_size'] * 0.02)  # Just below L0
        target = range_info['L75']

        risk = entry - stop
        reward = target - entry
        rr_ratio = reward / risk if risk > 0 else 0

        return {
            'ticker': ticker,
            'current_price': current_price,
            'date': current_date,
            'range': f"${range_info['L0']:.0f}-${range_info['L100']:.0f}",
            'L0': range_info['L0'],
            'L25': range_info['L25'],
            'L50': range_info['L50'],
            'L75': range_info['L75'],
            'shakeout_low': shakeout_low,
            'channel_level': channel_level or 'None',
            'position_pct': position_in_range,
            'recovery_pct': recovery_strength,
            'entry': entry,
            'stop': stop,
            'target': target,
            'rr_ratio': rr_ratio,
            'quality': quality,
            'notes': ', '.join(notes)
        }

    except Exception as e:
        return None


def run_scanner():
    """Run the channel + range shakeout scanner"""
    print("=" * 100)
    print("CHANNEL + RANGE LEVEL SHAKEOUT SCANNER")
    print("=" * 100)
    print(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("LOOKING FOR (EME-style setup):")
    print("  1. Stock was consolidating in a channel near a range level (like L25)")
    print("  2. Recently dropped/shook out to touch the L0 level")
    print("  3. Now recovering back into the range")
    print("  4. Target: L75 level")
    print()
    print("=" * 100)
    print()

    csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
    tickers = [f[:-4] for f in csv_files]

    print(f"Scanning {len(tickers)} stocks...")

    all_setups = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 500 == 0:
            print(f"  Progress: {i + 1}/{len(tickers)}...")

        setup = find_shakeout_setup(ticker, results_dir)
        if setup:
            all_setups.append(setup)

    print()
    print(f"Found {len(all_setups)} channel + range shakeout setups")
    print()

    if not all_setups:
        print("No setups found matching criteria.")
        return

    # Sort by quality
    all_setups.sort(key=lambda x: (x['quality'], x['rr_ratio']), reverse=True)

    # Separate by type
    classic_setups = [s for s in all_setups if 'CLASSIC L25 SHAKEOUT' in s['notes']]
    other_setups = [s for s in all_setups if 'CLASSIC L25 SHAKEOUT' not in s['notes']]

    # Generate report
    report_lines = []
    report_lines.append("=" * 100)
    report_lines.append("CHANNEL + RANGE LEVEL SHAKEOUT SCANNER - RESULTS")
    report_lines.append("=" * 100)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Total Setups: {len(all_setups)}")
    report_lines.append(f"  Classic L25 Shakeouts: {len(classic_setups)}")
    report_lines.append(f"  Other Shakeouts: {len(other_setups)}")
    report_lines.append("")
    report_lines.append("SETUP CRITERIA:")
    report_lines.append("  - Was consolidating in channel near range level")
    report_lines.append("  - Dropped to touch/break L0 (shakeout)")
    report_lines.append("  - Now recovering")
    report_lines.append("  - Target: L75")
    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    # Classic L25 shakeouts (best setups)
    if classic_setups:
        report_lines.append("[BEST] CLASSIC L25 SHAKEOUTS (Channel at 25%, dropped to 0%):")
        report_lines.append("-" * 100)
        report_lines.append(f"{'Ticker':<7} {'Price':<9} {'Range':<14} {'Low':<9} {'Entry':<9} {'Stop':<9} {'Target':<9} {'R:R':<6}")
        report_lines.append("-" * 100)

        for setup in classic_setups[:20]:
            report_lines.append(
                f"{setup['ticker']:<7} "
                f"${setup['current_price']:<8.2f} "
                f"{setup['range']:<14} "
                f"${setup['shakeout_low']:<8.2f} "
                f"${setup['entry']:<8.2f} "
                f"${setup['stop']:<8.2f} "
                f"${setup['target']:<8.2f} "
                f"{setup['rr_ratio']:<5.1f}x"
            )

        report_lines.append("")

    # All setups
    report_lines.append("ALL SETUPS (by quality):")
    report_lines.append("-" * 100)
    report_lines.append(f"{'Ticker':<7} {'Price':<9} {'Range':<14} {'Channel':<10} {'Shakeout':<10} {'Recovery':<10} {'Notes'}")
    report_lines.append("-" * 100)

    for setup in all_setups[:40]:
        report_lines.append(
            f"{setup['ticker']:<7} "
            f"${setup['current_price']:<8.2f} "
            f"{setup['range']:<14} "
            f"{setup['channel_level']:<10} "
            f"${setup['shakeout_low']:<9.2f} "
            f"{setup['recovery_pct']:<9.1f}% "
            f"{setup['notes']}"
        )

    report_lines.append("")
    report_lines.append("=" * 100)

    # Write report
    report_text = '\n'.join(report_lines)

    os.makedirs(buylist_dir, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Create TradingView list
    tv_file = os.path.join(buylist_dir, 'tradingview_channel_shakeout.txt')
    with open(tv_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("CHANNEL + RANGE SHAKEOUT SETUPS\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total: {len(all_setups)} setups\n")
        f.write("=" * 80 + "\n\n")

        if classic_setups:
            f.write("CLASSIC L25 SHAKEOUTS (Best):\n")
            f.write(",".join([s['ticker'] for s in classic_setups]) + "\n\n")

        f.write("ALL SETUPS:\n")
        f.write(",".join([s['ticker'] for s in all_setups]) + "\n")

    print(report_text)
    print()
    print(f"Report saved: {output_file}")
    print(f"TradingView list: {tv_file}")


if __name__ == "__main__":
    run_scanner()
