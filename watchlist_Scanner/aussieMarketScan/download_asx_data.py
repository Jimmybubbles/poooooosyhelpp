import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Path to ASX stock ticker list
ticker_file_path = os.path.join(script_dir, "ASXListedCompanies.csv")

# Directory to save CSV files
output_dir = os.path.join(script_dir, "asx_data")

# Create output directory if it doesn't exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Read tickers from the ASX CSV file
print("Reading ASX companies list...")
tickers_df = pd.read_csv(ticker_file_path, skiprows=2)  # Skip the first 2 lines (header info)
tickers = tickers_df['ASX code'].tolist()

print(f"Found {len(tickers)} ASX companies")

# Define the time period (last 5 years - approximately 1825 days)
start_date = (datetime.now() - timedelta(days=1825)).strftime('%Y-%m-%d')
end_date = datetime.now().strftime('%Y-%m-%d')

print(f"Downloading data from {start_date} to {end_date}")
print("=" * 80)

# List to hold tickers that encountered errors
error_tickers = []
success_count = 0

# Download and save the data for each ticker
for i, ticker_symbol in enumerate(tickers):
    try:
        # Add .AX suffix for ASX stocks in yfinance
        yf_ticker = f"{ticker_symbol}.AX"

        print(f"[{i+1}/{len(tickers)}] Downloading {ticker_symbol}...", end=" ")

        # Download the data with 1-day interval
        stock_data = yf.download(yf_ticker, start=start_date, end=end_date, interval="1d", auto_adjust=True, progress=False)

        # Check if the download was successful and has data
        if isinstance(stock_data, pd.DataFrame) and not stock_data.empty and len(stock_data) > 0:
            # Flatten multi-index columns if present
            if isinstance(stock_data.columns, pd.MultiIndex):
                stock_data.columns = stock_data.columns.get_level_values(0)

            # Ensure index is datetime
            if isinstance(stock_data.index, pd.DatetimeIndex):
                # Ensure timezone-aware (UTC)
                if stock_data.index.tz is None:
                    stock_data.index = stock_data.index.tz_localize('UTC')

                # Select the required columns
                stock_data = stock_data[['Open', 'High', 'Low', 'Close', 'Volume']]

                # Save the data to a CSV file
                file_name = os.path.join(output_dir, f"{ticker_symbol}.csv")
                stock_data.to_csv(file_name, header=True)

                success_count += 1
                print(f"✓ ({len(stock_data)} days)")
            else:
                print(f"✗ Invalid data format")
                error_tickers.append((ticker_symbol, "Invalid data format"))
        else:
            print(f"✗ No data available")
            error_tickers.append((ticker_symbol, "No data available"))

    except Exception as e:
        print(f"✗ Error: {str(e)[:50]}")
        error_tickers.append((ticker_symbol, str(e)))

print()
print("=" * 80)
print(f"Download complete!")
print(f"Successfully downloaded: {success_count}/{len(tickers)} stocks")
print(f"Failed: {len(error_tickers)} stocks")

# Print the tickers that triggered errors
if error_tickers:
    print("\nStocks that encountered errors:")
    print("-" * 80)
    for ticker, error in error_tickers[:20]:  # Show first 20 errors
        print(f"{ticker}: {error[:60]}")
    if len(error_tickers) > 20:
        print(f"... and {len(error_tickers) - 20} more")
else:
    print("\nAll tickers downloaded successfully!")