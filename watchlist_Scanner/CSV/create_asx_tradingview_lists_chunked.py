"""
Break ASX ticker list into chunks for TradingView
TradingView has a limit of ~200 tickers per watchlist
"""

import pandas as pd

# Read the ASX file
df = pd.read_csv('ASXListedCompanies.csv')

# Get all tickers
tickers = df['Ticker'].tolist()

# Split into chunks of 200
chunk_size = 200
chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]

print(f"Total tickers: {len(tickers)}")
print(f"Creating {len(chunks)} lists with max {chunk_size} tickers each\n")

# Create output file
output_file = 'tradingview_asx_lists_chunked.txt'

with open(output_file, 'w') as f:
    f.write("=" * 100 + "\n")
    f.write("TRADINGVIEW ASX TICKER LISTS (CHUNKED)\n")
    f.write("=" * 100 + "\n")
    f.write(f"Total ASX Companies: {len(tickers)}\n")
    f.write(f"Split into {len(chunks)} lists of ~{chunk_size} tickers each\n")
    f.write("\n")
    f.write("Copy and paste each list below into separate TradingView watchlists:\n")
    f.write("=" * 100 + "\n\n")

    for i, chunk in enumerate(chunks, 1):
        # Create list name
        start_ticker = chunk[0]
        end_ticker = chunk[-1]

        f.write(f"LIST {i} OF {len(chunks)} - ASX {start_ticker} to {end_ticker} ({len(chunk)} tickers)\n")
        f.write("-" * 100 + "\n")
        f.write(",".join(chunk) + "\n")
        f.write("\n\n")

        print(f"List {i}: {len(chunk)} tickers ({start_ticker} to {end_ticker})")

print(f"\nFile saved as: {output_file}")
print(f"\nYou'll need to create {len(chunks)} separate watchlists in TradingView")
