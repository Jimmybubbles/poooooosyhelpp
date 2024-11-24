import pandas as pd
import os
import talib
from datetime import datetime, timedelta

# Directory path
input_directory = 'Squeezescan/CSV/updatedResults'

# output to textfile
output_file_name = "scan_results_text"
output_file_path = os.path.join(input_directory, output_file_name) # Full path to the output file

# EMA and ATR parameters
ema1_per = 5
ema2_per = 26
atr_per = 50
atr_mult = 0.4

# Get the date for one month ago
# one_month_ago = datetime.now() - timedelta(days=30)

# Get the date for one week ago
one_week_ago = datetime.now() - timedelta(days=7)

# Get 1 day ago
two_days_ago = datetime.now() - timedelta(days=2)

def write_to_file(text):
    with open(output_file_path, 'a') as file: # a stands for append mode
        file.write(text + '\n')

# Iterate over the files in the input directory
for file_name in os.listdir(input_directory):
    try:
        # Input file path for current file
        file_path = os.path.join(input_directory, file_name)
        ticker_symbol = os.path.splitext(file_name)[0]
        

        # Read the existing CSV file
        data = pd.read_csv(file_path, index_col=0, parse_dates=True)

        # Calculate EMAs and ATR
        ema1 = talib.EMA(data['Close'], timeperiod=ema1_per)
        ema2 = talib.EMA(data['Close'], timeperiod=ema2_per)
        atr = talib.ATR(data['High'], data['Low'], data['Close'], timeperiod=atr_per) * atr_mult

        # Calculate Squeeze Channel Levels
        SqLup = (ema2 + atr).where((ema2 - ema1).abs() < atr, float('nan'))
        SqLdn = (ema2 - atr).where((ema2 - ema1).abs() < atr, float('nan'))

        # Check for channel breakouts over last month
        
        # for i in range(3, len(data)):
        #     date_of_event = data.index[i].replace(tzinfo=None)  # Convert to offset-naive datetime
        #     if date_of_event < one_month_ago:
        #         continue
        

        # Check for channel breakouts over last week
        for i in range(3, len(data)):
            date_of_event = data.index[i].replace(tzinfo=None)  # Convert to offset-naive datetime
            if date_of_event < one_week_ago:
                continue

            if not pd.isna(SqLup.iloc[i-1]) and pd.isna(SqLup.iloc[i]) and data['Close'].iloc[i] >= SqLup.iloc[i-1]:
                # print(f"{ticker_symbol} channel forming")
                write_to_file(f"BUY {ticker_symbol} {date_of_event.strftime('%m/%d/%Y')} : Upside Breakout {data['Close'].iloc[1].round(3)} " )
            elif not pd.isna(SqLdn.iloc[i-1]) and pd.isna(SqLdn.iloc[i]) and data['Close'].iloc[i] <= SqLdn.iloc[i-1]:
                # print(f"{ticker_symbol} channel forming")
                write_to_file(f"SELL {ticker_symbol} {date_of_event.strftime('%m/%d/%Y')} : Downside Breakdown  {data['Close'].iloc[1].round(3)}")
        # use print for console and use write to file for file


    except Exception as e:
        print(f"Exception encountered for {ticker_symbol}: {str(e)}")
        print(f"Exception type: {type(e)}")

write_to_file("n\Scan process completed")

print("\nScan process completed.")