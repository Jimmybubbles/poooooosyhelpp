import yfinance as yf
import pandas as pd
import os
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Directory paths
data_directory = os.path.join(script_dir, 'asx_data')

# Check if data directory exists
if not os.path.exists(data_directory):
    print(f"Error: Data directory not found: {data_directory}")
    print("Please run download_asx_data.py first to download initial data.")
    exit(1)

print("=" * 80)
print("ASX DATA UPDATER")
print("=" * 80)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Get list of CSV files
csv_files = [f for f in os.listdir(data_directory) if f.endswith('.csv')]
print(f"Found {len(csv_files)} stocks to update")
print("=" * 80)
print()

success_count = 0
no_update_count = 0
error_count = 0

# Iterate over the files in the data directory
for i, file_name in enumerate(csv_files):
    try:
        file_path = os.path.join(data_directory, file_name)
        ticker_symbol = os.path.splitext(file_name)[0]

        print(f"[{i+1}/{len(csv_files)}] {ticker_symbol}...", end=" ")

        # Read the existing CSV file
        # Check for header format - some files may have multiple header rows from yfinance
        with open(file_path, 'r') as f:
            first_line = f.readline().strip()

        # If first line contains "Price" or "Ticker", skip the extra yfinance headers
        if 'Price' in first_line or 'Ticker' in first_line:
            # Use row 0 as header, skip rows 1 and 2
            existing_data = pd.read_csv(file_path, header=0, skiprows=[1, 2], index_col=0)
        else:
            existing_data = pd.read_csv(file_path, index_col=0)

        # Convert index to datetime with error handling
        try:
            existing_data.index = pd.to_datetime(existing_data.index, utc=True, errors='coerce')
        except Exception as e:
            print(f"✗ Date parsing error: {str(e)[:40]}")
            error_count += 1
            continue

        # Remove rows with invalid dates
        existing_data = existing_data[existing_data.index.notna()]

        # Check if we have any valid data left
        if len(existing_data) == 0:
            print(f"✗ No valid data in file")
            error_count += 1
            continue

        # Find the last date in the existing data
        last_date = existing_data.index.max()

        if pd.isna(last_date):
            print(f"✗ Invalid date in file")
            error_count += 1
            continue

        # Calculate date range for new data
        start_date = (last_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')

        # Check if update is needed
        if start_date >= end_date:
            print(f"✓ Already up to date")
            no_update_count += 1
            continue

        # Add .AX suffix for ASX stocks
        yf_ticker = f"{ticker_symbol}.AX"

        # Download new data with 1-day interval
        new_data = yf.download(yf_ticker, start=start_date, end=end_date, interval="1d", auto_adjust=True, progress=False)

        # Check if the DataFrame is empty or has no new data
        if new_data.empty or len(new_data) == 0:
            print(f"✓ No new data available")
            no_update_count += 1
            continue

        # Ensure timezone-aware (UTC)
        if new_data.index.tz is None:
            new_data.index = new_data.index.tz_localize('UTC')

        # Keep only the columns that exist in existing_data
        new_data = new_data[['Open', 'High', 'Low', 'Close', 'Volume']]

        # Append the new data to the existing data
        combined_data = pd.concat([existing_data, new_data])

        # Remove any duplicate dates (keep last)
        combined_data = combined_data[~combined_data.index.duplicated(keep='last')]

        # Sort by date
        combined_data = combined_data.sort_index()

        # Save the combined data back to the CSV file
        combined_data.to_csv(file_path)

        print(f"✓ Added {len(new_data)} new days")
        success_count += 1

    except Exception as e:
        print(f"✗ Error: {str(e)[:50]}")
        error_count += 1

print()
print("=" * 80)
print("Update Summary:")
print(f"  Updated: {success_count} stocks")
print(f"  Already current: {no_update_count} stocks")
print(f"  Errors: {error_count} stocks")
print(f"  Total processed: {len(csv_files)} stocks")
print("=" * 80)
print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")