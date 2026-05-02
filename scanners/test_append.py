import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Directory where CSV files are stored
results_directory = os.path.join(script_dir, 'updated_Results_for_scan')

# Ticker list file
ticker_file = os.path.join(script_dir, 'CSV', '5000.csv')

def read_ticker_list(file_path):
    """Read ticker symbols from CSV file"""
    try:
        df = pd.read_csv(file_path)
        if 'Ticker' in df.columns:
            tickers = df['Ticker'].tolist()
        else:
            tickers = df.iloc[:, 0].tolist()
        return tickers
    except Exception as e:
        print(f"Error reading ticker file: {e}")
        return []

def get_last_date_in_csv(file_path):
    """Get the last date from an existing CSV file"""
    try:
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        if len(df) > 0:
            last_date = df.index[-1]
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

    if not os.path.exists(file_path):
        print("File not found")
        return False

    last_date = get_last_date_in_csv(file_path)
    if last_date is None:
        print("Could not read last date")
        return False

    start_date = last_date + timedelta(days=1)
    today = datetime.now()

    if start_date >= today:
        print(f"Up to date (last: {last_date.strftime('%Y-%m-%d')})")
        return True

    try:
        new_data = yf.download(ticker, start=start_date, end=today, progress=False)

        if new_data.empty:
            print("No new data available")
            return True

        existing_data = pd.read_csv(file_path, index_col=0, parse_dates=True)
        combined_data = pd.concat([existing_data, new_data])
        combined_data = combined_data[~combined_data.index.duplicated(keep='last')]
        combined_data = combined_data.sort_index()
        combined_data.to_csv(file_path)

        print(f"Added {len(new_data)} rows")
        return True

    except Exception as e:
        print(f"Error: {str(e)[:50]}")
        return False

# Test with first 5 tickers
if __name__ == "__main__":
    print("Testing AppendDailyData with first 5 tickers...")
    print("=" * 80)

    tickers = read_ticker_list(ticker_file)
    test_tickers = tickers[:5]

    print(f"Testing {len(test_tickers)} tickers: {test_tickers}")
    print()

    for i, ticker in enumerate(test_tickers, 1):
        print(f"[{i}/{len(test_tickers)}] {ticker}...", end=" ")
        result = append_new_data(ticker)

    print("\nTest complete!")
