"""
Test the UltimateScanner to check EFI and normalized price conditions
"""
import pandas as pd
import numpy as np
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from UltimateScanner import (
    calculate_elder_force_index,
    get_force_index_color,
    calculate_normalized_price,
    scan_stock
)

# Paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
data_folder = os.path.join(project_root, 'watchlist_Scanner', 'updated_Results_for_scan')

print("=" * 80)
print("ULTIMATE SCANNER TEST - EFI & NORMALIZED PRICE CHECK")
print("=" * 80)
print()

# Test on a few sample stocks
test_tickers = ['AAPL', 'TSLA', 'MSFT', 'NVDA', 'SPY']

print("UPDATED Criteria in UltimateScanner.py:")
print("-" * 80)
print("  Criterion 4: EFI oversold (MAROON or ORANGE) - fi_color in ['maroon', 'orange']")
print("  Criterion 5: Normalized price > 0 (DIVERGENCE SETUP)")
print()
print("This finds DIVERGENCE: Price showing strength while EFI shows weakness")
print()
print("Testing if stocks meet these criteria...")
print()

results = []

for ticker in test_tickers:
    file_path = os.path.join(data_folder, f"{ticker}.csv")

    if not os.path.exists(file_path):
        print(f"[SKIP] {ticker}: File not found")
        continue

    try:
        # Load data
        df = pd.read_csv(file_path, index_col=0)
        df.index = pd.to_datetime(df.index, errors='coerce', utc=True)
        df = df[df.index.notna()]

        # Convert to numeric
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna()

        if len(df) < 60:
            print(f"[SKIP] {ticker}: Not enough data")
            continue

        # Calculate indicators
        force_index = calculate_elder_force_index(df)
        fi_value = force_index.iloc[-1]
        fi_std = force_index.std()
        fi_color = get_force_index_color(fi_value, fi_std)

        normalized_price = calculate_normalized_price(df)
        norm_price_value = normalized_price.iloc[-1]

        current_price = df['Close'].iloc[-1]

        # Check criteria
        criterion_4 = fi_color in ['maroon', 'orange']
        criterion_5 = norm_price_value > 0

        results.append({
            'ticker': ticker,
            'price': current_price,
            'fi_value': fi_value,
            'fi_color': fi_color,
            'norm_price': norm_price_value,
            'criterion_4': criterion_4,
            'criterion_5': criterion_5
        })

        # Display results
        status_4 = "[YES]" if criterion_4 else "[NO]"
        status_5 = "[YES]" if criterion_5 else "[NO]"

        print(f"{ticker}:")
        print(f"  Price:              ${current_price:.2f}")
        print(f"  Force Index:        {fi_value:.2f} ({fi_color.upper()})")
        print(f"  Normalized Price:   {norm_price_value:.3f}")
        print(f"  {status_4} Criterion 4 (EFI oversold): {criterion_4}")
        print(f"  {status_5} Criterion 5 (Norm > 0):     {criterion_5}")

        # Show divergence status
        if criterion_4 and criterion_5:
            print(f"  >>> DIVERGENCE DETECTED! Price strong, EFI weak <<<")
        print()

    except Exception as e:
        print(f"[ERROR] {ticker}: {e}")
        continue

print("=" * 80)
print("SUMMARY")
print("=" * 80)

if results:
    print(f"Tested {len(results)} stocks")
    print()

    # Count how many meet each criterion
    efi_oversold_count = sum(1 for r in results if r['criterion_4'])
    norm_oversold_count = sum(1 for r in results if r['criterion_5'])
    both_criteria = sum(1 for r in results if r['criterion_4'] and r['criterion_5'])

    print(f"EFI Oversold (MAROON/ORANGE):  {efi_oversold_count}/{len(results)} stocks")
    print(f"Normalized Price > 0:          {norm_oversold_count}/{len(results)} stocks")
    print(f"DIVERGENCE (Both Criteria):    {both_criteria}/{len(results)} stocks")
    print()

    # Show normalized price distribution
    norm_prices = [r['norm_price'] for r in results]
    print("Normalized Price Distribution:")
    print(f"  Min:     {min(norm_prices):.3f}")
    print(f"  Max:     {max(norm_prices):.3f}")
    print(f"  Average: {np.mean(norm_prices):.3f}")
    print()

    # Show if you want to change to > 0
    print("DIVERGENCE STRATEGY EXPLANATION:")
    print("-" * 80)
    print("Criterion 5 is now: norm_price_value > 0")
    print()
    print("This creates a BULLISH DIVERGENCE setup:")
    print("  - Price is in the UPPER half of range (showing strength)")
    print("  - EFI is OVERSOLD/NEGATIVE (showing selling pressure)")
    print()
    print("This divergence suggests:")
    print("  Smart money accumulating while weak hands sell")
    print("  Price resilience despite selling pressure")
    print("  Potential reversal/continuation setup")

else:
    print("No stocks could be tested. Check file paths.")

print("=" * 80)
