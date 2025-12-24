"""
ULTIMATE HIGH PROBABILITY SCANNER
==================================
Combines the best elements from all scanners:
- Dynamic consolidation detection (no fixed timeframes)
- EFI momentum divergence (MAROON/ORANGE oversold)
- Normalized price (position in range)
- Trend confirmation (Fader/SMA)
- Volume analysis

Strategy: Buy dips in uptrends when stock is consolidating and oversold
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os

# File paths - get script directory and build absolute paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))

data_folder = os.path.join(project_root, 'watchlist_Scanner', 'results')
output_file = os.path.join(script_dir, 'ultimate_high_probability_signals.txt')
tradingview_file = os.path.join(script_dir, 'tradingview_ultimate_list.txt')

def calculate_elder_force_index(df, period=13):
    """Calculate Elder's Force Index"""
    force_index = df['Volume'] * (df['Close'] - df['Close'].shift(1))
    ema_force = force_index.ewm(span=period, adjust=False).mean()
    return ema_force

def get_force_index_color(fi_value, fi_std):
    """Determine Force Index color based on value"""
    if fi_value < -2.0 * fi_std:
        return 'maroon'
    elif fi_value < 0:
        return 'orange'
    elif fi_value > 2.0 * fi_std:
        return 'green'
    elif fi_value > 0:
        return 'lime'
    else:
        return 'gray'

def calculate_normalized_price(df, lookback=20):
    """Calculate normalized price position in range"""
    highest = df['High'].rolling(window=lookback).max()
    lowest = df['Low'].rolling(window=lookback).min()
    range_size = highest - lowest

    # Avoid division by zero
    range_size = range_size.replace(0, np.nan)

    # Normalized price: where current price sits in the range (-1 to +1)
    # -1 = at bottom, 0 = middle, +1 = at top
    normalized = 2 * ((df['Close'] - lowest) / range_size) - 1

    return normalized

def find_consolidation_range(df, current_idx, max_lookback=60):
    """
    Dynamically find consolidation range and duration
    Returns: (range_high, range_low, consolidation_days, range_percent)
    """
    if current_idx < 20:
        return None, None, 0, 0

    # Start with a 10-day window and expand
    best_range_days = 0
    best_high = None
    best_low = None
    best_range_pct = 0

    # Try different window sizes to find consolidation
    for window in range(10, min(max_lookback, current_idx), 5):
        start_idx = max(0, current_idx - window)
        window_data = df.iloc[start_idx:current_idx + 1]

        high = window_data['High'].max()
        low = window_data['Low'].min()
        range_pct = ((high - low) / low) * 100

        # Consolidation = tight range (< 15% range)
        if range_pct < 15:
            # Check if price stayed mostly within this range
            days_in_range = 0
            for i in range(start_idx, current_idx + 1):
                if low <= df['Low'].iloc[i] and df['High'].iloc[i] <= high:
                    days_in_range += 1

            # If most days are in range, this is a valid consolidation
            if days_in_range >= window * 0.7:  # 70% of days must be in range
                if days_in_range > best_range_days:
                    best_range_days = days_in_range
                    best_high = high
                    best_low = low
                    best_range_pct = range_pct

    return best_high, best_low, best_range_days, best_range_pct

def check_uptrend(df, current_idx, sma_period=50):
    """Check if stock is in an uptrend"""
    if current_idx < sma_period:
        return False

    sma = df['Close'].rolling(window=sma_period).mean()
    current_price = df['Close'].iloc[current_idx]
    current_sma = sma.iloc[current_idx]
    sma_10_days_ago = sma.iloc[max(0, current_idx - 10)]

    # Uptrend if: price above SMA and SMA is rising
    above_sma = current_price > current_sma
    sma_rising = current_sma > sma_10_days_ago

    return above_sma and sma_rising

def calculate_volume_strength(df, current_idx, lookback=20):
    """Calculate if current volume is above average"""
    if current_idx < lookback:
        return False, 0

    avg_volume = df['Volume'].iloc[max(0, current_idx - lookback):current_idx].mean()
    current_volume = df['Volume'].iloc[current_idx]

    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
    above_average = volume_ratio > 1.0

    return above_average, volume_ratio

def scan_stock(ticker, df):
    """
    Scan a single stock for ultimate high probability setup
    Returns signal dict if all criteria met, None otherwise
    """
    if len(df) < 60:
        return None

    current_idx = len(df) - 1
    current_date = df.index[current_idx]
    current_price = df['Close'].iloc[current_idx]

    # 1. Calculate Force Index
    force_index = calculate_elder_force_index(df)
    fi_value = force_index.iloc[current_idx]
    fi_std = force_index.std()
    fi_color = get_force_index_color(fi_value, fi_std)

    # 2. Calculate Normalized Price
    normalized_price = calculate_normalized_price(df)
    norm_price_value = normalized_price.iloc[current_idx]

    # 3. Find Dynamic Consolidation
    range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

    if range_high is None:
        return None  # No consolidation found

    # Calculate position in consolidation range
    range_size = range_high - range_low
    if range_size == 0:
        return None

    position_in_range = ((current_price - range_low) / range_size) * 100

    # 4. Check Uptrend
    in_uptrend = check_uptrend(df, current_idx)

    # 5. Check Volume
    volume_above_avg, volume_ratio = calculate_volume_strength(df, current_idx)

    # ========================================
    # ULTIMATE CRITERIA (ALL MUST BE TRUE)
    # ========================================

    # Criterion 1: In consolidation (any duration - quality score will favor longer)
    criterion_1 = consol_days > 0

    # Criterion 2: In uptrend
    criterion_2 = in_uptrend

    # Criterion 3: Price in lower 35% of consolidation range (buy zone)
    criterion_3 = position_in_range <= 35

    # Criterion 4: EFI oversold (MAROON or ORANGE)
    criterion_4 = fi_color in ['maroon', 'orange']

    # Criterion 5: Normalized price oversold (< -0.2)
    criterion_5 = norm_price_value < -0.2

    # Check if ALL criteria are met
    if not (criterion_1 and criterion_2 and criterion_3 and criterion_4 and criterion_5):
        return None

    # Calculate quality score (0-100)
    quality_score = 0

    # Points for consolidation duration (max 25 points)
    quality_score += min(25, consol_days / 2)

    # Points for how oversold (max 25 points)
    quality_score += min(25, abs(norm_price_value) * 25)

    # Points for EFI strength (max 25 points)
    if fi_color == 'maroon':
        quality_score += 25
    else:  # orange
        quality_score += 15

    # Points for volume (max 25 points)
    if volume_above_avg:
        quality_score += min(25, (volume_ratio - 1.0) * 50)

    # Return signal with all details
    return {
        'ticker': ticker,
        'date': current_date.strftime('%m/%d/%Y'),
        'price': current_price,
        'consolidation_days': consol_days,
        'range_high': range_high,
        'range_low': range_low,
        'range_pct': range_pct,
        'position_in_range': position_in_range,
        'normalized_price': norm_price_value,
        'force_index': fi_value,
        'fi_color': fi_color,
        'volume_ratio': volume_ratio,
        'quality_score': quality_score
    }

def run_ultimate_scan():
    """Run the ultimate high probability scanner"""
    print("=" * 80)
    print("ULTIMATE HIGH PROBABILITY SCANNER")
    print("=" * 80)
    print(f"Scan started: {datetime.now()}")
    print("\nLoading stock data from individual CSV files...")

    # Get all CSV files in the results folder
    csv_files = [f for f in os.listdir(data_folder) if f.endswith('.csv')]

    print(f"Found {len(csv_files)} stock files to scan...\n")

    signals = []

    for i, csv_file in enumerate(csv_files):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(csv_files)} stocks scanned...")

        ticker = csv_file.replace('.csv', '')
        file_path = os.path.join(data_folder, csv_file)

        try:
            # Load ticker data - skip rows 1 and 2 (ticker names and "Date" row)
            df = pd.read_csv(file_path, skiprows=[1, 2])

            # Rename 'Price' column to 'Date' if it exists
            if 'Price' in df.columns:
                df.rename(columns={'Price': 'Date'}, inplace=True)

            # Ensure required columns exist
            required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in df.columns for col in required_cols):
                continue

            # Prepare data
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date')
            df.set_index('Date', inplace=True)

            # Convert columns to numeric (in case they were read as strings)
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Drop any rows with NaN values
            df = df.dropna()

            # Scan this stock
            signal = scan_stock(ticker, df)

            if signal:
                signals.append(signal)

        except Exception as e:
            # Skip files that can't be read
            continue

    print(f"\nScan complete! Found {len(signals)} high probability setups.\n")

    # Sort signals by quality score (best first)
    signals.sort(key=lambda x: x['quality_score'], reverse=True)

    # Generate report
    generate_report(signals)
    create_tradingview_list(signals)

    return signals

def generate_report(signals):
    """Generate detailed report of signals"""
    report_lines = []

    report_lines.append("=" * 80)
    report_lines.append("ULTIMATE HIGH PROBABILITY SCANNER - RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("STRATEGY CRITERIA:")
    report_lines.append("  1. Consolidating for at least 10 days")
    report_lines.append("  2. In uptrend (price > 50 SMA, SMA rising)")
    report_lines.append("  3. Price in lower 35% of consolidation range")
    report_lines.append("  4. EFI oversold (MAROON or ORANGE)")
    report_lines.append("  5. Normalized price < -0.2 (oversold)")
    report_lines.append("")
    report_lines.append("QUALITY SCORE:")
    report_lines.append("  Based on consolidation duration, oversold level, EFI strength, volume")
    report_lines.append("  Higher score = higher probability setup")
    report_lines.append("")
    report_lines.append(f"Total High Probability Setups Found: {len(signals)}")
    report_lines.append("=" * 80)
    report_lines.append("")

    if signals:
        report_lines.append("TOP HIGH PROBABILITY SETUPS (sorted by quality score):")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Score':<7} {'Days':<6} {'Range':<8} {'Pos%':<6} {'Norm':<7} {'EFI':<8} {'Vol':<5}")
        report_lines.append("-" * 80)

        for signal in signals:
            ticker = signal['ticker']
            score = f"{signal['quality_score']:.0f}"
            days = f"{signal['consolidation_days']}"
            range_pct = f"{signal['range_pct']:.1f}%"
            pos = f"{signal['position_in_range']:.0f}%"
            norm = f"{signal['normalized_price']:.2f}"
            fi_color = signal['fi_color'].upper()[:6]
            vol = f"{signal['volume_ratio']:.1f}x"

            report_lines.append(f"{ticker:<8} {score:<7} {days:<6} {range_pct:<8} {pos:<6} {norm:<7} {fi_color:<8} {vol:<5}")

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("DETAILED SIGNALS:")
        report_lines.append("=" * 80)

        for i, signal in enumerate(signals, 1):
            report_lines.append("")
            report_lines.append(f"SIGNAL #{i} - {signal['ticker']} - Quality Score: {signal['quality_score']:.0f}/100")
            report_lines.append("-" * 80)
            report_lines.append(f"  Date:                {signal['date']}")
            report_lines.append(f"  Current Price:       ${signal['price']:.2f}")
            report_lines.append(f"  Consolidation:       {signal['consolidation_days']} days")
            report_lines.append(f"  Range:               ${signal['range_low']:.2f} - ${signal['range_high']:.2f} ({signal['range_pct']:.1f}%)")
            report_lines.append(f"  Position in Range:   {signal['position_in_range']:.0f}% (lower third = buy zone)")
            report_lines.append(f"  Normalized Price:    {signal['normalized_price']:.2f} (oversold)")
            report_lines.append(f"  Force Index:         {signal['force_index']:.2f} ({signal['fi_color'].upper()})")
            report_lines.append(f"  Volume:              {signal['volume_ratio']:.1f}x average")
            report_lines.append("")
            report_lines.append(f"  SETUP: {signal['ticker']} consolidating for {signal['consolidation_days']} days in uptrend,")
            report_lines.append(f"         now oversold ({signal['fi_color'].upper()} EFI) at low end of range.")
            report_lines.append(f"         Buy zone entry with {signal['quality_score']:.0f}/100 quality score.")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Print to console
    try:
        print(report_text)
    except UnicodeEncodeError:
        print(report_text.encode('ascii', errors='replace').decode('ascii'))

    print(f"\nReport saved to: {output_file}")
    print(f"TradingView list saved to: {tradingview_file}")

def create_tradingview_list(signals):
    """Create TradingView format watchlist"""
    if not signals:
        return

    tickers_list = [signal['ticker'] for signal in signals]

    lines = []
    lines.append("=" * 80)
    lines.append("ULTIMATE HIGH PROBABILITY SCANNER - TRADINGVIEW WATCHLIST")
    lines.append("=" * 80)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total symbols: {len(tickers_list)}")
    lines.append("")
    lines.append("Copy the comma-separated line below into TradingView:")
    lines.append("-" * 80)
    lines.append(','.join(tickers_list))
    lines.append("")

    with open(tradingview_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

if __name__ == "__main__":
    signals = run_ultimate_scan()

    if signals:
        print(f"\n✓ Found {len(signals)} high probability setups!")
        print(f"✓ Top 3 highest quality scores:")
        for i, signal in enumerate(signals[:3], 1):
            print(f"   {i}. {signal['ticker']} - Score: {signal['quality_score']:.0f}/100")
    else:
        print("\nNo setups found matching all criteria.")