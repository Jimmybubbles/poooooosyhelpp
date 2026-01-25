"""
DIAGNOSTIC SCANNER - Understand why Ultimate Scanner isn't finding signals
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os

# File paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
data_folder = os.path.join(project_root, 'watchlist_Scanner', 'results')

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
    range_size = range_size.replace(0, np.nan)
    normalized = 2 * ((df['Close'] - lowest) / range_size) - 1
    return normalized

def find_consolidation_range(df, current_idx, max_lookback=60):
    """Dynamically find consolidation range and duration"""
    if current_idx < 20:
        return None, None, 0, 0

    best_range_days = 0
    best_high = None
    best_low = None
    best_range_pct = 0

    for window in range(10, min(max_lookback, current_idx), 5):
        start_idx = max(0, current_idx - window)
        window_data = df.iloc[start_idx:current_idx + 1]

        high = window_data['High'].max()
        low = window_data['Low'].min()
        range_pct = ((high - low) / low) * 100

        if range_pct < 15:
            days_in_range = 0
            for i in range(start_idx, current_idx + 1):
                if low <= df['Low'].iloc[i] and df['High'].iloc[i] <= high:
                    days_in_range += 1

            if days_in_range >= window * 0.7:
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

    above_sma = current_price > current_sma
    sma_rising = current_sma > sma_10_days_ago

    return above_sma and sma_rising

def run_diagnostic():
    """Run diagnostic to see criteria breakdown"""
    print("=" * 80)
    print("DIAGNOSTIC SCANNER - Analyzing Why Criteria Not Met")
    print("=" * 80)

    # Get all CSV files
    csv_files = [f for f in os.listdir(data_folder) if f.endswith('.csv')]
    print(f"Scanning {len(csv_files)} stocks...\n")

    # Counters for each criterion
    stats = {
        'total_stocks': 0,
        'enough_data': 0,
        'has_consolidation': 0,
        'in_uptrend': 0,
        'in_buy_zone': 0,
        'efi_oversold': 0,
        'norm_price_oversold': 0,
        'all_criteria': 0
    }

    # Examples of stocks meeting each criterion
    examples = {
        'has_consolidation': [],
        'in_uptrend': [],
        'in_buy_zone': [],
        'efi_oversold': [],
        'norm_price_oversold': []
    }

    for csv_file in csv_files[:500]:  # Sample first 500 stocks
        ticker = csv_file.replace('.csv', '')
        file_path = os.path.join(data_folder, csv_file)
        stats['total_stocks'] += 1

        try:
            # Load ticker data - skip first row (contains ticker names)
            df = pd.read_csv(file_path, skiprows=[1])

            # Rename 'Price' column to 'Date' if it exists
            if 'Price' in df.columns:
                df.rename(columns={'Price': 'Date'}, inplace=True)

            required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in df.columns for col in required_cols):
                continue

            df['Date'] = pd.to_datetime(df['Date'], utc=True)
            df = df.sort_values('Date')
            df.set_index('Date', inplace=True)

            # Convert columns to numeric
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Drop any rows with NaN values
            df = df.dropna()

            if len(df) < 60:
                continue

            stats['enough_data'] += 1
            current_idx = len(df) - 1
            current_price = df['Close'].iloc[current_idx]

            # Calculate all indicators
            force_index = calculate_elder_force_index(df)
            fi_value = force_index.iloc[current_idx]
            fi_std = force_index.std()
            fi_color = get_force_index_color(fi_value, fi_std)

            normalized_price = calculate_normalized_price(df)
            norm_price_value = normalized_price.iloc[current_idx]

            range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

            in_uptrend = check_uptrend(df, current_idx)

            # Check each criterion
            has_consolidation = consol_days > 0
            if has_consolidation:
                stats['has_consolidation'] += 1
                if len(examples['has_consolidation']) < 5:
                    examples['has_consolidation'].append(f"{ticker} ({consol_days} days)")

            if in_uptrend:
                stats['in_uptrend'] += 1
                if len(examples['in_uptrend']) < 5:
                    examples['in_uptrend'].append(ticker)

            # Buy zone check (only if consolidation exists)
            in_buy_zone = False
            if range_high is not None and range_low is not None:
                range_size = range_high - range_low
                if range_size > 0:
                    position_in_range = ((current_price - range_low) / range_size) * 100
                    in_buy_zone = position_in_range <= 35
                    if in_buy_zone:
                        stats['in_buy_zone'] += 1
                        if len(examples['in_buy_zone']) < 5:
                            examples['in_buy_zone'].append(f"{ticker} ({position_in_range:.0f}%)")

            efi_oversold = fi_color in ['maroon', 'orange']
            if efi_oversold:
                stats['efi_oversold'] += 1
                if len(examples['efi_oversold']) < 5:
                    examples['efi_oversold'].append(f"{ticker} ({fi_color})")

            norm_oversold = norm_price_value < -0.2
            if norm_oversold:
                stats['norm_price_oversold'] += 1
                if len(examples['norm_price_oversold']) < 5:
                    examples['norm_price_oversold'].append(f"{ticker} ({norm_price_value:.2f})")

            # Check if ALL criteria met
            if has_consolidation and in_uptrend and in_buy_zone and efi_oversold and norm_oversold:
                stats['all_criteria'] += 1

        except Exception as e:
            continue

    # Print results
    print("\nCRITERIA BREAKDOWN:")
    print("-" * 80)
    total = stats['enough_data']
    print(f"Total stocks with enough data: {total}")
    print()
    print(f"Criterion 1 - Has Consolidation (any days):    {stats['has_consolidation']:4d} / {total:4d} ({100*stats['has_consolidation']/total if total > 0 else 0:.1f}%)")
    print(f"  Examples: {', '.join(examples['has_consolidation'][:5])}")
    print()
    print(f"Criterion 2 - In Uptrend:                       {stats['in_uptrend']:4d} / {total:4d} ({100*stats['in_uptrend']/total if total > 0 else 0:.1f}%)")
    print(f"  Examples: {', '.join(examples['in_uptrend'][:5])}")
    print()
    print(f"Criterion 3 - In Buy Zone (lower 35%):          {stats['in_buy_zone']:4d} / {total:4d} ({100*stats['in_buy_zone']/total if total > 0 else 0:.1f}%)")
    print(f"  Examples: {', '.join(examples['in_buy_zone'][:5])}")
    print()
    print(f"Criterion 4 - EFI Oversold (MAROON/ORANGE):     {stats['efi_oversold']:4d} / {total:4d} ({100*stats['efi_oversold']/total if total > 0 else 0:.1f}%)")
    print(f"  Examples: {', '.join(examples['efi_oversold'][:5])}")
    print()
    print(f"Criterion 5 - Normalized Price < -0.2:          {stats['norm_price_oversold']:4d} / {total:4d} ({100*stats['norm_price_oversold']/total if total > 0 else 0:.1f}%)")
    print(f"  Examples: {', '.join(examples['norm_price_oversold'][:5])}")
    print()
    print("-" * 80)
    print(f"ALL 5 CRITERIA MET:                             {stats['all_criteria']:4d} / {total:4d} ({100*stats['all_criteria']/total if total > 0 else 0:.1f}%)")
    print("=" * 80)

    return stats

if __name__ == "__main__":
    run_diagnostic()