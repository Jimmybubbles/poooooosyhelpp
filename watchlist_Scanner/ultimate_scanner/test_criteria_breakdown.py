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

def find_consolidation_range(df, current_idx, max_lookback=60):
    """Find dynamic consolidation range"""
    if current_idx < 10:
        return None, None, None, None

    lookback_data = df.iloc[max(0, current_idx - max_lookback):current_idx + 1]

    best_range = None
    best_days = 0

    for window in range(60, 9, -1):
        if window > len(lookback_data):
            continue

        window_data = lookback_data.tail(window)
        high = window_data['High'].max()
        low = window_data['Low'].min()
        range_pct = ((high - low) / low) * 100

        if range_pct <= 15:
            touches = 0
            tolerance = (high - low) * 0.15

            for _, row in window_data.iterrows():
                if row['Low'] <= (low + tolerance) or row['High'] >= (high - tolerance):
                    touches += 1

            touch_pct = (touches / len(window_data)) * 100

            if touch_pct >= 70:
                if window > best_days:
                    best_range = (high, low)
                    best_days = window

    if best_range and best_days >= 10:
        range_pct = ((best_range[0] - best_range[1]) / best_range[1]) * 100
        return best_range[0], best_range[1], best_days, range_pct

    return None, None, None, None

def check_uptrend(df, current_idx):
    """Check if in uptrend"""
    if current_idx < 50:
        return False

    sma_50 = df['Close'].iloc[max(0, current_idx - 49):current_idx + 1].mean()
    current_price = df['Close'].iloc[current_idx]

    if current_price <= sma_50:
        return False

    sma_50_prev = df['Close'].iloc[max(0, current_idx - 54):current_idx - 4].mean()

    return sma_50 > sma_50_prev

# Test on sample stocks
data_dir = Path("../updated_Results_for_scan")
test_tickers = ['AAPL', 'MSFT', 'TSLA', 'NVDA', 'AMD', 'GOOGL', 'META', 'AMZN', 'NFLX', 'SPY',
                'KBH', 'FORM', 'TWI', 'XPO', 'NUE', 'AMAT', 'VFC', 'CMI']

print("=" * 100)
print("CRITERIA BREAKDOWN - Testing each criterion")
print("=" * 100)
print()
print(f"{'Ticker':<8} {'C1:Consol':<12} {'C2:Uptrend':<12} {'C3:EFI<0':<12} {'C4:Norm>-0.5':<13} {'ALL PASS':<10}")
print("-" * 100)

stats = {
    'total': 0,
    'c1_pass': 0,
    'c2_pass': 0,
    'c3_pass': 0,
    'c4_pass': 0,
    'all_pass': 0
}

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

        stats['total'] += 1
        current_idx = len(df) - 1

        # Calculate indicators
        force_index = calculate_force_index(df)
        normalized_price = calculate_normalized_price(df)

        fi_value = force_index.iloc[current_idx]
        fi_std = force_index.std()
        fi_color = get_force_index_color(fi_value, fi_std)
        norm_price_value = normalized_price.iloc[current_idx]

        range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)
        in_uptrend = check_uptrend(df, current_idx)

        # Check criteria
        c1 = range_high is not None
        c2 = in_uptrend
        c3 = fi_color in ['maroon', 'orange']
        c4 = norm_price_value > -0.5
        all_pass = c1 and c2 and c3 and c4

        if c1:
            stats['c1_pass'] += 1
        if c2:
            stats['c2_pass'] += 1
        if c3:
            stats['c3_pass'] += 1
        if c4:
            stats['c4_pass'] += 1
        if all_pass:
            stats['all_pass'] += 1

        c1_str = f"PASS ({consol_days}d)" if c1 else "FAIL"
        c2_str = "PASS" if c2 else "FAIL"
        c3_str = f"PASS ({fi_color})" if c3 else f"FAIL ({fi_color})"
        c4_str = f"PASS ({norm_price_value:.2f})" if c4 else f"FAIL ({norm_price_value:.2f})"
        all_str = "YES ✓" if all_pass else "NO"

        print(f"{ticker:<8} {c1_str:<12} {c2_str:<12} {c3_str:<12} {c4_str:<13} {all_str:<10}")

    except Exception as e:
        print(f"{ticker:<8} ERROR: {e}")

print("-" * 100)
print()
print("SUMMARY:")
print(f"  Total stocks tested: {stats['total']}")
print(f"  C1 (Consolidating):  {stats['c1_pass']}/{stats['total']} ({stats['c1_pass']/stats['total']*100:.1f}%)")
print(f"  C2 (Uptrend):        {stats['c2_pass']}/{stats['total']} ({stats['c2_pass']/stats['total']*100:.1f}%)")
print(f"  C3 (EFI Oversold):   {stats['c3_pass']}/{stats['total']} ({stats['c3_pass']/stats['total']*100:.1f}%)")
print(f"  C4 (Norm > -0.5):    {stats['c4_pass']}/{stats['total']} ({stats['c4_pass']/stats['total']*100:.1f}%)")
print(f"  ALL CRITERIA PASS:   {stats['all_pass']}/{stats['total']} ({stats['all_pass']/stats['total']*100:.1f}%)")
print("=" * 100)
