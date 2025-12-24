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
    """Read ticker symbols from CSV file"""
    try:
        df = pd.read_csv(file_path)
        # Extract just the ticker column
        if 'Ticker' in df.columns:
            tickers = df['Ticker'].tolist()
        else:
            # Fallback: assume first column is ticker
            tickers = df.iloc[:, 0].tolist()
        return tickers
    except Exception as e:
        print(f"Error reading ticker file: {e}")
        return []

def get_last_date_in_csv(file_path):
    """Get the last date from an existing CSV file"""
    try:
        df = pd.read_csv(file_path, index_col=0)
        if len(df) > 0:
            # Convert index to datetime with flexible parsing
            df.index = pd.to_datetime(df.index, errors='coerce', utc=True)

            # Remove any rows with invalid dates
            df = df[df.index.notna()]

            if len(df) == 0:
                return None

            last_date = df.index[-1]

            # Convert to timezone-naive datetime
            if last_date.tzinfo is not None:
                last_date = last_date.tz_localize(None)

            # Convert Timestamp to Python datetime
            return last_date.to_pydatetime()
        return None
    except Exception as e:
        print(f"Error reading file: {str(e)[:50]}")
        return None

def append_new_data(ticker):
    """Download and append only new data for a ticker"""
    file_path = os.path.join(results_directory, f'{ticker}.csv')

    # Check if file exists
    if not os.path.exists(file_path):
        print("File not found, skipping")
        return False

    # Get the last date in the file
    last_date = get_last_date_in_csv(file_path)
    if last_date is None:
        print("Could not read last date")
        return False

    # Calculate start date (day after last date in file)
    start_date = last_date + timedelta(days=1)
    today = datetime.now()

    # Check if we need to download anything
    if start_date >= today:
        print(f"Up to date")
        return True

    try:
        # Download new data
        new_data = yf.download(ticker, start=start_date, end=today, progress=False, auto_adjust=True)

        if new_data.empty:
            print("No new data")
            return True

        # Read existing data
        existing_data = pd.read_csv(file_path, index_col=0)
        existing_data.index = pd.to_datetime(existing_data.index, errors='coerce', utc=True)

        # Convert to timezone-naive
        if existing_data.index.tz is not None:
            existing_data.index = existing_data.index.tz_localize(None)

        # Flatten multi-index columns if present in new_data
        if isinstance(new_data.columns, pd.MultiIndex):
            new_data.columns = new_data.columns.get_level_values(0)

        # Ensure new_data index is also timezone-naive
        if hasattr(new_data.index, 'tz') and new_data.index.tz is not None:
            new_data.index = new_data.index.tz_localize(None)

        # Combine existing and new data
        combined_data = pd.concat([existing_data, new_data])

        # Remove any duplicate dates (just in case)
        combined_data = combined_data[~combined_data.index.duplicated(keep='last')]

        # Sort by date
        combined_data = combined_data.sort_index()

        # Save back to file
        combined_data.to_csv(file_path)

        print(f"Added {len(new_data)} new rows")
        return True

    except Exception as e:
        print(f"Error: {str(e)[:50]}")
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
        print(f"[{i}/{len(tickers)}] Processing {ticker}...", end=" ")
        result = append_new_data(ticker)

        if result:
            success_count += 1
        else:
            error_count += 1

        # Show progress every 100 tickers
        if i % 100 == 0:
            print(f"\nProgress: {i}/{len(tickers)} processed ({success_count} updated, {error_count} errors)")
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
