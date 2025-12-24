"""
MOMENTUM REVERSAL SCANNER
=========================
Detects momentum reversals when:
1. Normalized Price crosses above 0 (price moving above middle of range)
2. EFI Histogram changes from RED to GREEN (negative to positive momentum)

Strategy: Catch the turn from oversold to bullish momentum
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os

# File paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))

data_folder = os.path.join(project_root, 'watchlist_Scanner', 'results')
output_file = os.path.join(script_dir, 'momentum_reversal_signals.txt')
tradingview_file = os.path.join(script_dir, 'tradingview_momentum_reversal_list.txt')

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
        return 'red'
    elif fi_value > 2.0 * fi_std:
        return 'lime'
    elif fi_value > 0:
        return 'green'
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

def scan_stock(ticker, df):
    """
    Scan a single stock for momentum reversal
    Returns signal dict if criteria met, None otherwise
    """
    if len(df) < 30:
        return None

    current_idx = len(df) - 1
    prev_idx = current_idx - 1

    if prev_idx < 1:
        return None

    current_date = df.index[current_idx]
    current_price = df['Close'].iloc[current_idx]

    # Calculate Force Index
    force_index = calculate_elder_force_index(df)
    fi_current = force_index.iloc[current_idx]
    fi_prev = force_index.iloc[prev_idx]
    fi_std = force_index.std()

    fi_color_current = get_force_index_color(fi_current, fi_std)
    fi_color_prev = get_force_index_color(fi_prev, fi_std)

    # Calculate Normalized Price
    normalized_price = calculate_normalized_price(df)
    norm_current = normalized_price.iloc[current_idx]
    norm_prev = normalized_price.iloc[prev_idx]

    # ========================================
    # REVERSAL CRITERIA (BOTH MUST BE TRUE)
    # ========================================

    # Criterion 1: Normalized price crosses above 0
    # (was negative or zero, now positive)
    norm_cross_up = norm_prev <= 0 and norm_current > 0

    # Criterion 2: EFI histogram changes from RED to GREEN
    # (was negative, now positive)
    efi_turns_green = fi_color_prev == 'red' and fi_color_current == 'green'

    # Check if BOTH criteria are met
    if not (norm_cross_up and efi_turns_green):
        return None

    # Calculate strength score (0-100)
    strength_score = 0

    # Points for how much above 0 normalized price is (max 30 points)
    strength_score += min(30, norm_current * 30)

    # Points for EFI strength (max 40 points)
    if fi_current > 0:
        strength_score += min(40, (fi_current / fi_std) * 10)

    # Points for volume (max 30 points)
    if current_idx >= 20:
        avg_volume = df['Volume'].iloc[current_idx - 20:current_idx].mean()
        current_volume = df['Volume'].iloc[current_idx]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        if volume_ratio > 1.0:
            strength_score += min(30, (volume_ratio - 1.0) * 60)

    # Return signal with all details
    return {
        'ticker': ticker,
        'date': current_date.strftime('%m/%d/%Y'),
        'price': current_price,
        'normalized_price_prev': norm_prev,
        'normalized_price_current': norm_current,
        'force_index_current': fi_current,
        'force_index_prev': fi_prev,
        'fi_color_prev': fi_color_prev,
        'fi_color_current': fi_color_current,
        'strength_score': strength_score
    }

def run_momentum_reversal_scan():
    """Run the momentum reversal scanner"""
    print("=" * 80)
    print("MOMENTUM REVERSAL SCANNER")
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
            df['Date'] = pd.to_datetime(df['Date'], utc=True)
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

    print(f"\nScan complete! Found {len(signals)} momentum reversal signals.\n")

    # Sort signals by strength score (best first)
    signals.sort(key=lambda x: x['strength_score'], reverse=True)

    # Generate report
    generate_report(signals)
    create_tradingview_list(signals)

    return signals

def generate_report(signals):
    """Generate detailed report of signals"""
    report_lines = []

    report_lines.append("=" * 80)
    report_lines.append("MOMENTUM REVERSAL SCANNER - RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("STRATEGY CRITERIA:")
    report_lines.append("  1. Normalized Price crosses above 0 (was <= 0, now > 0)")
    report_lines.append("  2. EFI Histogram changes from RED to GREEN (momentum turn)")
    report_lines.append("")
    report_lines.append("STRENGTH SCORE:")
    report_lines.append("  Based on normalized price level, EFI strength, volume")
    report_lines.append("  Higher score = stronger reversal signal")
    report_lines.append("")
    report_lines.append(f"Total Momentum Reversals Found: {len(signals)}")
    report_lines.append("=" * 80)
    report_lines.append("")

    if signals:
        report_lines.append("TOP MOMENTUM REVERSALS (sorted by strength score):")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Score':<7} {'Price':<10} {'Norm Prev':<10} {'Norm Now':<10} {'EFI':<12}")
        report_lines.append("-" * 80)

        for signal in signals:
            ticker = signal['ticker']
            score = f"{signal['strength_score']:.0f}"
            price = f"${signal['price']:.2f}"
            norm_prev = f"{signal['normalized_price_prev']:.2f}"
            norm_now = f"{signal['normalized_price_current']:.2f}"
            efi = f"{signal['fi_color_prev'].upper()}->{signal['fi_color_current'].upper()}"

            report_lines.append(f"{ticker:<8} {score:<7} {price:<10} {norm_prev:<10} {norm_now:<10} {efi:<12}")

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("DETAILED SIGNALS:")
        report_lines.append("=" * 80)

        for i, signal in enumerate(signals, 1):
            report_lines.append("")
            report_lines.append(f"SIGNAL #{i} - {signal['ticker']} - Strength Score: {signal['strength_score']:.0f}/100")
            report_lines.append("-" * 80)
            report_lines.append(f"  Date:                     {signal['date']}")
            report_lines.append(f"  Current Price:            ${signal['price']:.2f}")
            report_lines.append(f"  Normalized Price (prev):  {signal['normalized_price_prev']:.3f}")
            report_lines.append(f"  Normalized Price (now):   {signal['normalized_price_current']:.3f} (CROSSED ABOVE 0)")
            report_lines.append(f"  Force Index (prev):       {signal['force_index_prev']:.2f} ({signal['fi_color_prev'].upper()})")
            report_lines.append(f"  Force Index (now):        {signal['force_index_current']:.2f} ({signal['fi_color_current'].upper()})")
            report_lines.append("")
            report_lines.append(f"  REVERSAL: {signal['ticker']} momentum turned positive!")
            report_lines.append(f"            Normalized price crossed above 0, EFI turned GREEN.")
            report_lines.append(f"            Strength score: {signal['strength_score']:.0f}/100")

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
    lines.append("MOMENTUM REVERSAL SCANNER - TRADINGVIEW WATCHLIST")
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
    signals = run_momentum_reversal_scan()

    if signals:
        try:
            print(f"\n✓ Found {len(signals)} momentum reversals!")
            print(f"✓ Top 3 highest strength scores:")
            for i, signal in enumerate(signals[:3], 1):
                print(f"   {i}. {signal['ticker']} - Score: {signal['strength_score']:.0f}/100")
        except UnicodeEncodeError:
            print(f"\nFound {len(signals)} momentum reversals!")
            print(f"Top 3 highest strength scores:")
            for i, signal in enumerate(signals[:3], 1):
                print(f"   {i}. {signal['ticker']} - Score: {signal['strength_score']:.0f}/100")
    else:
        print("\nNo momentum reversals found matching all criteria.")