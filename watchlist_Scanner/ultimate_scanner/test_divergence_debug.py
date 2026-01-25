import pandas as pd
import numpy as np
import os
from pathlib import Path

def calculate_force_index(df):
    """Calculate Elder Force Index (13-period EMA)"""
    force = (df['Close'] - df['Close'].shift(1)) * df['Volume']
    return force.ewm(span=13, adjust=False).mean()

def get_force_index_color(fi_value, fi_std):
    """Determine Force Index color"""
    if fi_value < -2.0 * fi_std:
        return 'maroon'
    elif fi_value < 0:
        return 'orange'
    elif fi_value > 2.0 * fi_std:
        return 'green'
    else:
        return 'lime'

def calculate_normalized_price(df, lookback=20):
    """Calculate normalized price position in range"""
    highest = df['High'].rolling(window=lookback).max()
    lowest = df['Low'].rolling(window=lookback).min()
    range_size = highest - lowest
    range_size = range_size.replace(0, np.nan)
    normalized = 2 * ((df['Close'] - lowest) / range_size) - 1
    return normalized

# Test on sample stocks
data_dir = Path("../updated_Results_for_scan")
test_tickers = ['AAPL', 'MSFT', 'TSLA', 'NVDA', 'AMD', 'GOOGL', 'META', 'AMZN', 'NFLX', 'SPY']

print("=" * 80)
print("DIVERGENCE DEBUG - Checking current market conditions")
print("=" * 80)
print()

oversold_count = 0
norm_positive_count = 0
divergence_count = 0

for ticker in test_tickers:
    file_path = data_dir / f"{ticker}.csv"
    if not file_path.exists():
        continue

    try:
        df = pd.read_csv(file_path, skiprows=[1, 2])
        if 'Price' in df.columns:
            df.rename(columns={'Price': 'Date'}, inplace=True)

        df['Date'] = pd.to_datetime(df['Date'], utc=True)
        df = df.sort_values('Date')

        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna()

        if len(df) < 60:
            continue

        # Calculate indicators
        force_index = calculate_force_index(df)
        normalized_price = calculate_normalized_price(df)

        # Get latest values
        fi_value = force_index.iloc[-1]
        fi_std = force_index.std()
        fi_color = get_force_index_color(fi_value, fi_std)
        norm_price_value = normalized_price.iloc[-1]

        # Check conditions
        is_oversold = fi_color in ['maroon', 'orange']
        is_norm_positive = norm_price_value > 0
        is_divergence = is_oversold and is_norm_positive

        if is_oversold:
            oversold_count += 1
        if is_norm_positive:
            norm_positive_count += 1
        if is_divergence:
            divergence_count += 1

        status = ""
        if is_divergence:
            status = " *** DIVERGENCE ***"

        print(f"{ticker:6s} | EFI: {fi_color:7s} ({fi_value:>12,.0f}) | Norm Price: {norm_price_value:>6.3f} | {status}")

    except Exception as e:
        print(f"{ticker:6s} | ERROR: {e}")

print()
print("=" * 80)
print(f"Summary out of {len(test_tickers)} stocks:")
print(f"  EFI Oversold (MAROON/ORANGE): {oversold_count}")
print(f"  Normalized Price > 0:         {norm_positive_count}")
print(f"  DIVERGENCE (both):            {divergence_count}")
print("=" * 80)
