import yfinance as yf
import pandas as pd
import os
import talib
import numpy as np
from datetime import datetime, timedelta

# Directory paths
input_directory = r'poooooosyhelpp\watchlist_Scanner\results'
output_directory = r'poooooosyhelpp\watchlist_Scanner\updatedResults'

# Create output directory if it doesn't exist
if not os.path.exists(output_directory):
    os.makedirs(output_directory)

# Function to convert date string to datetime object
def parse_date(x):
    if isinstance(x, str):
        return datetime.strptime(x, '%Y-%m-%d %H:%M:%S%z')
    return x

# Iterate over the files in the input directory
for file_name in os.listdir(input_directory):
    try:
        file_path = os.path.join(input_directory, file_name)
        ticker_symbol = os.path.splitext(file_name)[0]

        # Read the existing CSV file, skipping the first 3 rows and setting the index
        existing_data = pd.read_csv(file_path, skiprows=3, header=None, names=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        existing_data['Date'] = existing_data['Date'].apply(parse_date)
        existing_data = existing_data.set_index('Date')

        # Find the last date in the existing data
        last_date = existing_data.index.max()
        if isinstance(last_date, datetime):
            start_date = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')

            # Download new data with 1-day interval
            new_data = yf.download(ticker_symbol, start=start_date, end=end_date, interval="1d")

            # Check if the DataFrame is empty
            if new_data.empty:
                print(f"No new data found for {ticker_symbol} in the specified date range.")
                continue

            # Convert DataFrame columns to numpy arrays for TA-Lib
            close_array = new_data['Close'].values
            high_array = new_data['High'].values
            low_array = new_data['Low'].values

            # Ensure the arrays are 1D
            close_array = close_array.reshape(-1)
            high_array = high_array.reshape(-1)
            low_array = low_array.reshape(-1)

            # Calculate EMA 5, 21, 26, and ATR 50 using numpy arrays
            for period in [5, 21, 26]:
                new_data[f'EMA{period}'] = talib.EMA(close_array, timeperiod=period)
            new_data['ATR50'] = talib.ATR(high_array, low_array, close_array, timeperiod=50)

            # Append the new data to the existing data
            combined_data = pd.concat([existing_data, new_data])

            # Save the combined data to a new CSV file
            output_file_path = os.path.join(output_directory, file_name)
            combined_data.to_csv(output_file_path)

            print(f"Updated data for {ticker_symbol} and saved to {output_file_path}")
        else:
            print(f"Last date for {ticker_symbol} is not a datetime object: {last_date}")
    except Exception as e:
        print(f"Exception encountered for {ticker_symbol}: {str(e)}")
        print(f"Exception type: {type(e)}")

print("\nUpdate process completed.")