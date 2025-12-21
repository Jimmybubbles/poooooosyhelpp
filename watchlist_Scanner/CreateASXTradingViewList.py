import pandas as pd
import os
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Input and output files
input_file = os.path.join(script_dir, 'CSV', 'ASX_stocks.csv')
output_file = os.path.join(script_dir, 'buylist', 'tradingview_ASX_list.txt')

def create_tradingview_list():
    """
    Create a TradingView format list from ASX stocks CSV
    TradingView format: ASX:TICKER
    """
    print("=" * 80)
    print("CREATING TRADINGVIEW ASX WATCHLIST")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Read the CSV file
    df = pd.read_csv(input_file)

    print(f"Loaded {len(df)} ASX stocks from CSV")
    print()

    # Create TradingView format list
    tradingview_symbols = []

    for ticker in df['Ticker']:
        # TradingView format for ASX: ASX:TICKER
        tv_symbol = f"ASX:{ticker}"
        tradingview_symbols.append(tv_symbol)

    # Join all symbols with commas (TradingView format)
    tradingview_list = ",".join(tradingview_symbols)

    # Write to file
    with open(output_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("TRADINGVIEW ASX WATCHLIST\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(tradingview_symbols)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")
        f.write(tradingview_list + "\n\n")
        f.write("-" * 80 + "\n\n")
        f.write("Individual symbols (one per line):\n")
        f.write("-" * 80 + "\n")
        for symbol in tradingview_symbols:
            f.write(symbol + "\n")

    print("TradingView list created successfully!")
    print(f"Output file: {output_file}")
    print()
    print("Format: ASX:TICKER")
    print()
    print("First 10 symbols:")
    for symbol in tradingview_symbols[:10]:
        print(f"  {symbol}")
    print()
    print("USAGE INSTRUCTIONS:")
    print("=" * 80)
    print("1. Open TradingView (tradingview.com)")
    print("2. Go to Watchlist")
    print("3. Click 'Import list'")
    print("4. Copy the comma-separated list from the output file")
    print("5. Paste into TradingView")
    print()
    print("OR add symbols one by one:")
    print("1. Click the '+' button in your watchlist")
    print("2. Type the symbol (e.g., ASX:BHP)")
    print("3. Press Enter to add")
    print()
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    create_tradingview_list()
