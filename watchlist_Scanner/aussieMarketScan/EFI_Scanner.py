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

# Paths - updated for aussieMarketScan structure
data_dir = os.path.join(script_dir, 'asx_data')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'sorted_efi_scan_results.txt')
tradingview_file = os.path.join(buylist_dir, 'tradingview_efi_list.txt')

# Create directories if they don't exist
if not os.path.exists(buylist_dir):
    os.makedirs(buylist_dir)

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        # Get all CSV files in the directory
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        # Extract ticker symbols (filename without .csv extension)
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def scan_ticker(ticker_symbol, results_dir):
    """
    Scan a single ticker for EFI conditions:
    - Normalized price > 0 (positive, above zero line)
    - Force Index < 0 (negative, below zero)
    - Force Index color is red (maroon) or orange (weak bearish or strong bearish)
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker_symbol}.csv")

        if not os.path.exists(csv_file):
            return None

        # Read CSV - handle both old format and yfinance multi-header format
        with open(csv_file, 'r') as f:
            first_line = f.readline().strip()

        # Check for yfinance multi-header format
        if 'Price' in first_line or 'Ticker' in first_line:
            # Use row 0 as header, skip rows 1 and 2
            df = pd.read_csv(csv_file, header=0, skiprows=[1, 2], index_col=0)
        elif 'Date' in first_line or 'Open' in first_line:
            # Standard header format
            df = pd.read_csv(csv_file, header=0, index_col=0)
        else:
            # No header
            df = pd.read_csv(csv_file, header=None, index_col=0)
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

        # Ensure we have the required columns
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_columns):
            return None

        df.index = pd.to_datetime(df.index, errors='coerce', utc=True)
        df = df[df.index.notna()]

        if len(df) < 100:  # Need enough data
            return None

        # Initialize EFI indicator with default parameters
        indicator = EFI_Indicator()

        # Calculate indicator values
        results = indicator.calculate(df)

        # Get the most recent values
        latest_idx = -1
        normalized_price = results['normalized_price'].iloc[latest_idx]
        force_index = results['force_index'].iloc[latest_idx]
        fi_color = results['fi_color'].iloc[latest_idx]
        histogram = results['histogram'].iloc[latest_idx]

        # Check conditions:
        # 1. Normalized price > 0 (positive, above zero line)
        # 2. Force Index < 0 (below zero line)
        # 3. Force Index color is maroon (strong bearish) or orange (weak bearish)

        condition_1 = normalized_price > 0  # Normalized price positive
        condition_2 = force_index < 0  # Force Index negative (below zero)
        condition_3 = fi_color in ['maroon', 'orange']  # Red or orange bars

        if condition_1 and condition_2 and condition_3:
            current_date = df.index[latest_idx]
            current_price = df['Close'].iloc[latest_idx]

            return {
                'ticker': ticker_symbol,
                'date': current_date,
                'price': current_price,
                'normalized_price': normalized_price,
                'force_index': force_index,
                'histogram': histogram,
                'fi_color': fi_color,
                'upper_band': results['upper_band'].iloc[latest_idx],
                'lower_band': results['lower_band'].iloc[latest_idx]
            }

        return None

    except Exception as e:
        print(f"Error scanning {ticker_symbol}: {e}")
        return None

def run_scan():
    """Main scanning function"""
    print("=" * 80)
    print("EFI SCANNER - NORMALIZED PRICE DIVERGENCE")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("Scan Criteria:")
    print("  1. Normalized Price > 0 (positive, above zero line)")
    print("  2. Force Index < 0 (negative, below zero)")
    print("  3. Force Index bars are RED (maroon) or ORANGE")
    print()
    print("This indicates potential bearish divergence:")
    print("  - Price is above BB basis (bullish price action)")
    print("  - But Force Index is negative (bearish momentum)")
    print("=" * 80)
    print()

    # Get ticker list from ASX data directory
    tickers = get_ticker_list(data_dir)
    print(f"Scanning {len(tickers)} tickers from asx_data...")
    print()

    # Scan all tickers
    signals = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers scanned...")

        result = scan_ticker(ticker, data_dir)

        if result:
            signals.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(signals)} stocks matching criteria")
    print()

    # Sort by normalized price (highest first - most bullish price action)
    signals.sort(key=lambda x: x['normalized_price'], reverse=True)

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("EFI SCANNER - NORMALIZED PRICE DIVERGENCE RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("SCAN CRITERIA:")
    report_lines.append("  1. Normalized Price > 0 (price above BB basis)")
    report_lines.append("  2. Force Index < 0 (negative momentum)")
    report_lines.append("  3. Force Index color is RED or ORANGE")
    report_lines.append("")
    report_lines.append("INTERPRETATION:")
    report_lines.append("  This shows potential bearish divergence where price appears strong")
    report_lines.append("  but underlying momentum (Force Index) is weakening or turning negative.")
    report_lines.append("  Can indicate potential reversal or consolidation.")
    report_lines.append("")
    report_lines.append(f"Total Matches: {len(signals)}")
    report_lines.append("=" * 80)
    report_lines.append("")

    if signals:
        report_lines.append("STOCKS WITH BEARISH DIVERGENCE PATTERN:")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Date':<12} {'Price':<10} {'Norm Price':<12} {'Force Idx':<12} {'Color':<10}")
        report_lines.append("-" * 80)

        for signal in signals:
            date_str = signal['date'].strftime('%m/%d/%Y')
            report_lines.append(
                f"{signal['ticker']:<8} "
                f"{date_str:<12} "
                f"${signal['price']:<9.2f} "
                f"{signal['normalized_price']:>11.2f} "
                f"{signal['force_index']:>11.2f} "
                f"{signal['fi_color']:<10}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")
        report_lines.append("LEGEND:")
        report_lines.append("  Ticker: Stock symbol")
        report_lines.append("  Date: Most recent trading date")
        report_lines.append("  Price: Current stock price")
        report_lines.append("  Norm Price: Normalized price (distance from BB basis)")
        report_lines.append("  Force Idx: Force Index value (negative = bearish momentum)")
        report_lines.append("  Color: Force Index bar color")
        report_lines.append("    - maroon: Strong bearish (FI negative and decreasing)")
        report_lines.append("    - orange: Weak bearish (FI negative but increasing)")
        report_lines.append("")
    else:
        report_lines.append("No stocks found matching the criteria.")
        report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w') as f:
        f.write(report_text)

    # Create TradingView list
    create_tradingview_list(signals)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")
    print(f"TradingView list saved to: {tradingview_file}")

def create_tradingview_list(signals):
    """Create TradingView format watchlist"""
    tickers_list = [signal['ticker'] for signal in signals]

    with open(tradingview_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("EFI SCANNER - TRADINGVIEW WATCHLIST\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(tickers_list)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")
        f.write(",".join(tickers_list) + "\n\n")
        f.write("-" * 80 + "\n\n")
        f.write("Individual symbols (one per line):\n")
        f.write("-" * 80 + "\n")
        for ticker in tickers_list:
            f.write(ticker + "\n")

if __name__ == "__main__":
    run_scan()
