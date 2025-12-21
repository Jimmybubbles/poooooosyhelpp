import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# Directory where CSV files are stored
results_directory = os.path.join(project_root, 'watchlist_Scanner', 'updated_Results_for_scan')

# Ticker list file (same as your main download script)
ticker_file = os.path.join(project_root, 'watchlist_Scanner', 'CSV', '5000.csv')

def read_ticker_list(file_path):
    """Read ticker symbols from file"""
    with open(file_path, 'r') as file:
        tickers = [line.strip() for line in file if line.strip()]
    return tickers

def get_last_date_in_csv(file_path):
    """Get the last date from an existing CSV file"""
    try:
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        if len(df) > 0:
            last_date = df.index[-1]
            # Convert to timezone-naive datetime if needed
            if hasattr(last_date, 'tz_localize'):
                last_date = last_date.tz_localize(None) if last_date.tzinfo else last_date
            return last_date
        return None
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

def append_new_data(ticker):
    """Download and append only new data for a ticker"""
    file_path = os.path.join(results_directory, f'{ticker}.csv')

    # Check if file exists
    if not os.path.exists(file_path):
        print(f"{ticker}: File doesn't exist, skipping (use main download script first)")
        return False

    # Get the last date in the file
    last_date = get_last_date_in_csv(file_path)
    if last_date is None:
        print(f"{ticker}: Could not read last date, skipping")
        return False

    # Calculate start date (day after last date in file)
    start_date = last_date + timedelta(days=1)
    today = datetime.now()

    # Check if we need to download anything
    if start_date >= today:
        print(f"{ticker}: Already up to date (last date: {last_date.strftime('%Y-%m-%d')})")
        return True

    try:
        # Download new data
        print(f"{ticker}: Downloading from {start_date.strftime('%Y-%m-%d')} to today...")
        new_data = yf.download(ticker, start=start_date, end=today, progress=False)

        if new_data.empty:
            print(f"{ticker}: No new data available")
            return True

        # Read existing data
        existing_data = pd.read_csv(file_path, index_col=0, parse_dates=True)

        # Combine existing and new data
        combined_data = pd.concat([existing_data, new_data])

        # Remove any duplicate dates (just in case)
        combined_data = combined_data[~combined_data.index.duplicated(keep='last')]

        # Sort by date
        combined_data = combined_data.sort_index()

        # Save back to file
        combined_data.to_csv(file_path)

        print(f"{ticker}: Added {len(new_data)} new rows (last date: {last_date.strftime('%Y-%m-%d')} -> {combined_data.index[-1].strftime('%Y-%m-%d')})")
        return True

    except Exception as e:
        print(f"{ticker}: Error - {str(e)}")
        return False

# Main execution
if __name__ == "__main__":
    print("=" * 80)
    print("DAILY DATA APPEND SCRIPT")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Read ticker list
    tickers = read_ticker_list(ticker_file)
    print(f"Found {len(tickers)} tickers to update")
    print()

    success_count = 0
    skip_count = 0
    error_count = 0

    # Process each ticker
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Processing {ticker}...")
        result = append_new_data(ticker)

        if result:
            success_count += 1
        else:
            error_count += 1

        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total tickers: {len(tickers)}")
    print(f"Successfully updated: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
