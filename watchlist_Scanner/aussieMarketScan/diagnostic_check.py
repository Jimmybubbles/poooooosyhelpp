import pandas as pd
import os
import sys
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Add parent directory to path to import EFI_Indicator
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

from EFI_Indicator import EFI_Indicator

# Paths
data_dir = os.path.join(script_dir, 'asx_data')

def check_stock(ticker_symbol):
    """Check EFI values for a specific stock"""
    try:
        csv_file = os.path.join(data_dir, f"{ticker_symbol}.csv")

        if not os.path.exists(csv_file):
            print(f"{ticker_symbol}: File not found")
            return

        # Read CSV
        with open(csv_file, 'r') as f:
            first_line = f.readline().strip()

        if 'Price' in first_line or 'Ticker' in first_line:
            df = pd.read_csv(csv_file, header=0, skiprows=[1, 2], index_col=0)
        else:
            df = pd.read_csv(csv_file, header=0, index_col=0)

        df.index = pd.to_datetime(df.index, errors='coerce', utc=True)
        df = df[df.index.notna()]

        if len(df) < 100:
            print(f"{ticker_symbol}: Not enough data ({len(df)} days)")
            return

        # Initialize EFI indicator
        indicator = EFI_Indicator()

        # Calculate indicator values
        results = indicator.calculate(df)

        # Get the most recent values
        latest_idx = -1
        normalized_price = results['normalized_price'].iloc[latest_idx]
        force_index = results['force_index'].iloc[latest_idx]
        fi_color = results['fi_color'].iloc[latest_idx]
        current_price = df['Close'].iloc[latest_idx]
        current_date = df.index[latest_idx]

        print(f"\n{ticker_symbol}:")
        print(f"  Date: {current_date.strftime('%Y-%m-%d')}")
        print(f"  Price: ${current_price:.2f}")
        print(f"  Normalized Price: {normalized_price:>8.2f} {'[YES]' if normalized_price > 0 else '[NO]'}")
        print(f"  Force Index: {force_index:>12.2f} {'[YES]' if force_index < 0 else '[NO]'}")
        print(f"  FI Color: {fi_color:>10} {'[YES]' if fi_color in ['maroon', 'orange'] else '[NO]'}")

        # Check if it meets all criteria
        meets_criteria = (normalized_price > 0) and (force_index < 0) and (fi_color in ['maroon', 'orange'])
        print(f"  Meets ALL criteria: {'*** YES ***' if meets_criteria else 'NO'}")

    except Exception as e:
        print(f"{ticker_symbol}: Error - {str(e)}")

# Check a sample of stocks
print("=" * 80)
print("EFI DIAGNOSTIC CHECK - SAMPLE STOCKS")
print("=" * 80)

# Get list of available stocks
csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
tickers = sorted([f[:-4] for f in csv_files])

print(f"\nTotal stocks available: {len(tickers)}")
print("\nChecking first 10 stocks:")
print("=" * 80)

for ticker in tickers[:10]:
    check_stock(ticker)

print("\n" + "=" * 80)
print("\nChecking some popular ASX stocks (if available):")
print("=" * 80)

# Check some well-known ASX stocks
popular_stocks = ['CBA', 'BHP', 'WBC', 'ANZ', 'NAB', 'CSL', 'WES', 'WOW', 'FMG', 'RIO']
for ticker in popular_stocks:
    if ticker in tickers:
        check_stock(ticker)

print("\n" + "=" * 80)
print("\nSUMMARY OF SCAN CRITERIA:")
print("=" * 80)
print("To match, a stock must have ALL THREE conditions:")
print("  1. Normalized Price > 0 (price above Bollinger Band basis)")
print("  2. Force Index < 0 (negative momentum)")
print("  3. Force Index color = 'maroon' or 'orange'")
print("\nThis represents bearish divergence - price looks strong but momentum is weak")
print("=" * 80)
