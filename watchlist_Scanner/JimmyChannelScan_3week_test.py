import pandas as pd
import os
import talib
from datetime import datetime, timedelta

# Directory path
input_directory = r'watchlist_Scanner\updated_Results_for_scan'

# output to textfile
output_file_name = "scan_results_3week_test"
output_file_path = os.path.join(input_directory, output_file_name) # Full path to the output file

# Sorted results output file
sorted_output_file_name = "sorted_scan_results_3week.txt"
sorted_output_file_path = os.path.join('watchlist_Scanner', 'buylist', sorted_output_file_name)

# EMA and ATR parameters
ema1_per = 5
ema2_per = 26
atr_per = 50
atr_mult = 0.4

# Get the date for one month ago
one_month_ago = datetime.now() - timedelta(days=30)

# Get the date for one week ago
one_week_ago = datetime.now() - timedelta(days=7)

# Get 1 day ago
two_days_ago = datetime.now() - timedelta(days=2)

# Minimum trading days for channel formation (3 weeks = ~15 trading days)
min_channel_days = 15

def write_to_file(text):
    with open(output_file_path, 'a') as file: # a stands for append mode
        file.write(text + '\n')

def write_to_sorted_file(text):
    with open(sorted_output_file_path, 'a') as file:
        file.write(text + '\n')

def count_channel_days(SqLup, SqLdn, current_index):
    """
    Count how many consecutive days a valid channel existed before the current index.
    A valid channel means both SqLup and SqLdn are not NaN.
    """
    channel_days = 0
    for j in range(current_index - 1, -1, -1):
        # Check if both upper and lower channel lines exist
        if not pd.isna(SqLup.iloc[j]) and not pd.isna(SqLdn.iloc[j]):
            channel_days += 1
        else:
            # Channel broke, stop counting
            break
    return channel_days

# Clear the sorted output file before starting
if os.path.exists(sorted_output_file_path):
    os.remove(sorted_output_file_path)

# Store all signals for sorting
buy_signals = []
sell_signals = []

# Iterate over the files in the input directory
for file_name in os.listdir(input_directory):
    try:
        # Skip non-CSV files
        if not file_name.endswith('.csv'):
            continue

        # Input file path for current file
        file_path = os.path.join(input_directory, file_name)
        ticker_symbol = os.path.splitext(file_name)[0]


        # Read the existing CSV file
        data = pd.read_csv(file_path, index_col=0, parse_dates=True, date_format='ISO8601')

        # Calculate EMAs and ATR
        ema1 = talib.EMA(data['Close'], timeperiod=ema1_per)
        ema2 = talib.EMA(data['Close'], timeperiod=ema2_per)
        atr = talib.ATR(data['High'], data['Low'], data['Close'], timeperiod=atr_per) * atr_mult

        # Calculate Squeeze Channel Levels
        SqLup = (ema2 + atr).where((ema2 - ema1).abs() < atr, float('nan'))
        SqLdn = (ema2 - atr).where((ema2 - ema1).abs() < atr, float('nan'))

        # Check for channel breakouts over last month

        for i in range(3, len(data)):
            date_of_event = pd.Timestamp(data.index[i]).tz_localize(None) if pd.Timestamp(data.index[i]).tzinfo else pd.Timestamp(data.index[i])
            if date_of_event < one_month_ago:
                continue

            # NEW LOGIC: Check if channel has been forming for at least 3 weeks
            channel_days = count_channel_days(SqLup, SqLdn, i)

            # Only proceed if channel existed for minimum required days
            if channel_days < min_channel_days:
                continue

            # Check for upside breakout
            if not pd.isna(SqLup.iloc[i-1]) and pd.isna(SqLup.iloc[i]) and data['Close'].iloc[i] >= SqLup.iloc[i-1]:
                buy_signals.append({
                    'ticker': ticker_symbol,
                    'date': date_of_event.strftime('%m/%d/%Y'),
                    'channel_days': channel_days,
                    'price': data['Close'].iloc[i]
                })

            # Check for downside breakdown
            elif not pd.isna(SqLdn.iloc[i-1]) and pd.isna(SqLdn.iloc[i]) and data['Close'].iloc[i] <= SqLdn.iloc[i-1]:
                sell_signals.append({
                    'ticker': ticker_symbol,
                    'date': date_of_event.strftime('%m/%d/%Y'),
                    'channel_days': channel_days,
                    'price': data['Close'].iloc[i]
                })


    except Exception as e:
        print(f"Exception encountered for {ticker_symbol}: {str(e)}")
        print(f"Exception type: {type(e)}")

# Sort buy signals by price (ascending - cheaper stocks first)
buy_signals.sort(key=lambda x: x['price'])

# Sort sell signals by price (descending - higher priced stocks first)
sell_signals.sort(key=lambda x: x['price'], reverse=True)

# Write sorted BUY signals to BOTH files
write_to_file("=" * 80)
write_to_file(f"BUY SIGNALS ({len(buy_signals)} total)")
write_to_file("=" * 80)

write_to_sorted_file("=" * 80)
write_to_sorted_file(f"BUY SIGNALS ({len(buy_signals)} total)")
write_to_sorted_file("=" * 80)

for signal in buy_signals:
    output_line = f"BUY {signal['ticker']} {signal['date']} : Upside Breakout after {signal['channel_days']} days channel - Price: {round(signal['price'], 3)}"
    write_to_file(output_line)
    write_to_sorted_file(output_line)

# Write sorted SELL signals to BOTH files
write_to_file("\n" + "=" * 80)
write_to_file(f"SELL SIGNALS ({len(sell_signals)} total)")
write_to_file("=" * 80)

write_to_sorted_file("\n" + "=" * 80)
write_to_sorted_file(f"SELL SIGNALS ({len(sell_signals)} total)")
write_to_sorted_file("=" * 80)

for signal in sell_signals:
    output_line = f"SELL {signal['ticker']} {signal['date']} : Downside Breakdown after {signal['channel_days']} days channel - Price: {round(signal['price'], 3)}"
    write_to_file(output_line)
    write_to_sorted_file(output_line)

write_to_file("\n" + "=" * 80)
write_to_file("Scan process completed")
write_to_file("=" * 80)

write_to_sorted_file("\n" + "=" * 80)
write_to_sorted_file("Scan process completed")
write_to_sorted_file("=" * 80)

print(f"\nScan completed! Found {len(buy_signals)} BUY signals and {len(sell_signals)} SELL signals.")
print(f"Results saved to:")
print(f"  - {output_file_path}")
print(f"  - {sorted_output_file_path}")
