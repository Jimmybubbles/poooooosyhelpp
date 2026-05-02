"""
Convert ASXListedCompanies.csv to TradingView ticker list
"""

import pandas as pd

# Read the ASX file
df = pd.read_csv('ASXListedCompanies.csv')

# Get all tickers
tickers = df['Ticker'].tolist()

# Create comma-separated list
tradingview_list = ','.join(tickers)

# Save to file
output_file = 'tradingview_asx_list.txt'

with open(output_file, 'w') as f:
    f.write("=" * 100 + "\n")
    f.write("TRADINGVIEW ASX TICKER LIST\n")
    f.write("=" * 100 + "\n")
    f.write(f"Total ASX Companies: {len(tickers)}\n")
    f.write("\n")
    f.write("Copy and paste the line below into TradingView:\n")
    f.write("-" * 100 + "\n")
    f.write(tradingview_list + "\n")
    f.write("\n")

print(f"Created TradingView list with {len(tickers)} ASX tickers")
print(f"\nFirst 20 tickers: {','.join(tickers[:20])}")
print(f"\nFile saved as: {output_file}")
