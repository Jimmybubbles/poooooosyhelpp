import pandas as pd
import os
import talib
from datetime import datetime, timedelta

# Directory path
input_directory = r'poooooosyhelpp\watchlist_Scanner\updatedResults'

# output to textfile
output_file_name = "multi_timeframe_scan_results.txt"
output_file_path = os.path.join(input_directory, output_file_name)

# EMA and ATR parameters
ema1_per = 5
ema2_per = 26
atr_per = 50
atr_mult = 0.4

# Time periods for lookback
one_day_ago = datetime.now() - timedelta(days=1)
one_week_ago = datetime.now() - timedelta(days=7)
one_month_ago = datetime.now() - timedelta(days=30)

def write_to_file(text):
    with open(output_file_path, 'a') as file:
        file.write(text + '\n')

def resample_to_weekly(data):
    """Resample daily data to weekly"""
    weekly = data.resample('W').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    })
    return weekly.dropna()

def resample_to_monthly(data):
    """Resample daily data to monthly"""
    monthly = data.resample('ME').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    })
    return monthly.dropna()

def check_for_channel(data, lookback_date):
    """
    Check if there's a squeeze channel breakout in the given timeframe
    Returns: (has_breakout, breakout_type, date, price)
    """
    if len(data) < atr_per + 5:
        return False, None, None, None

    # Calculate EMAs and ATR
    ema1 = talib.EMA(data['Close'], timeperiod=ema1_per)
    ema2 = talib.EMA(data['Close'], timeperiod=ema2_per)
    atr = talib.ATR(data['High'], data['Low'], data['Close'], timeperiod=atr_per) * atr_mult

    # Calculate Squeeze Channel Levels
    SqLup = (ema2 + atr).where((ema2 - ema1).abs() < atr, float('nan'))
    SqLdn = (ema2 - atr).where((ema2 - ema1).abs() < atr, float('nan'))

    # Check for channel breakouts
    for i in range(3, len(data)):
        date_of_event = pd.Timestamp(data.index[i])
        if date_of_event.tzinfo:
            date_of_event = date_of_event.tz_localize(None)

        if date_of_event < lookback_date:
            continue

        # Check for upside breakout
        if not pd.isna(SqLup.iloc[i-1]) and pd.isna(SqLup.iloc[i]) and data['Close'].iloc[i] >= SqLup.iloc[i-1]:
            return True, 'BUY', date_of_event, data['Close'].iloc[i]

        # Check for downside breakdown
        elif not pd.isna(SqLdn.iloc[i-1]) and pd.isna(SqLdn.iloc[i]) and data['Close'].iloc[i] <= SqLdn.iloc[i-1]:
            return True, 'SELL', date_of_event, data['Close'].iloc[i]

    return False, None, None, None

# Clear the output file
if os.path.exists(output_file_path):
    os.remove(output_file_path)

write_to_file("=" * 80)
write_to_file("MULTI-TIMEFRAME CHANNEL BREAKOUT SCANNER")
write_to_file(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
write_to_file("=" * 80)
write_to_file("")

# Store results for summary
results = []

# Iterate over the files in the input directory
for file_name in os.listdir(input_directory):
    if not file_name.endswith('.csv'):
        continue

    try:
        file_path = os.path.join(input_directory, file_name)
        ticker_symbol = os.path.splitext(file_name)[0]

        # Read the existing CSV file
        daily_data = pd.read_csv(file_path, index_col=0)

        # Ensure index is DatetimeIndex and handle timezone
        if not isinstance(daily_data.index, pd.DatetimeIndex):
            daily_data.index = pd.to_datetime(daily_data.index, format='mixed', utc=True)

        # Remove timezone info if present to avoid comparison issues
        if hasattr(daily_data.index, 'tz') and daily_data.index.tz is not None:
            daily_data.index = daily_data.index.tz_localize(None)

        # Check daily timeframe
        daily_breakout, daily_type, daily_date, daily_price = check_for_channel(daily_data, one_day_ago)

        # Resample and check weekly timeframe
        weekly_data = resample_to_weekly(daily_data)
        weekly_breakout, weekly_type, weekly_date, weekly_price = check_for_channel(weekly_data, one_week_ago)

        # Resample and check monthly timeframe
        monthly_data = resample_to_monthly(daily_data)
        monthly_breakout, monthly_type, monthly_date, monthly_price = check_for_channel(monthly_data, one_month_ago)

        # If any timeframe has a breakout, record it
        if daily_breakout or weekly_breakout or monthly_breakout:
            result = {
                'ticker': ticker_symbol,
                'daily': (daily_breakout, daily_type, daily_date, daily_price),
                'weekly': (weekly_breakout, weekly_type, weekly_date, weekly_price),
                'monthly': (monthly_breakout, monthly_type, monthly_date, monthly_price)
            }
            results.append(result)

    except Exception as e:
        print(f"Exception encountered for {ticker_symbol}: {str(e)}")
        print(f"Exception type: {type(e)}")

# Write results grouped by signal type
if results:
    # Group by BUY signals
    buy_signals = [r for r in results if any(
        r['daily'][1] == 'BUY' or r['weekly'][1] == 'BUY' or r['monthly'][1] == 'BUY'
    )]

    if buy_signals:
        write_to_file("\n" + "=" * 80)
        write_to_file("BUY SIGNALS (Upside Breakouts)")
        write_to_file("=" * 80)

        for result in buy_signals:
            timeframes = []

            if result['daily'][0] and result['daily'][1] == 'BUY':
                timeframes.append(f"Daily({result['daily'][2].strftime('%m/%d')} @ {result['daily'][3]:.2f})")

            if result['weekly'][0] and result['weekly'][1] == 'BUY':
                timeframes.append(f"Weekly({result['weekly'][2].strftime('%m/%d')} @ {result['weekly'][3]:.2f})")

            if result['monthly'][0] and result['monthly'][1] == 'BUY':
                timeframes.append(f"Monthly({result['monthly'][2].strftime('%m/%d')} @ {result['monthly'][3]:.2f})")

            timeframe_str = " | ".join(timeframes)
            write_to_file(f"{result['ticker']:8s} -> {timeframe_str}")

    # Group by SELL signals
    sell_signals = [r for r in results if any(
        r['daily'][1] == 'SELL' or r['weekly'][1] == 'SELL' or r['monthly'][1] == 'SELL'
    )]

    if sell_signals:
        write_to_file("\n" + "=" * 80)
        write_to_file("SELL SIGNALS (Downside Breakdowns)")
        write_to_file("=" * 80)

        for result in sell_signals:
            timeframes = []

            if result['daily'][0] and result['daily'][1] == 'SELL':
                timeframes.append(f"Daily({result['daily'][2].strftime('%m/%d')} @ {result['daily'][3]:.2f})")

            if result['weekly'][0] and result['weekly'][1] == 'SELL':
                timeframes.append(f"Weekly({result['weekly'][2].strftime('%m/%d')} @ {result['weekly'][3]:.2f})")

            if result['monthly'][0] and result['monthly'][1] == 'SELL':
                timeframes.append(f"Monthly({result['monthly'][2].strftime('%m/%d')} @ {result['monthly'][3]:.2f})")

            timeframe_str = " | ".join(timeframes)
            write_to_file(f"{result['ticker']:8s} -> {timeframe_str}")

    write_to_file("\n" + "=" * 80)
    write_to_file(f"Total signals found: {len(results)}")
    write_to_file(f"Buy signals: {len(buy_signals)}")
    write_to_file(f"Sell signals: {len(sell_signals)}")
else:
    write_to_file("\nNo channel breakouts found in any timeframe.")

write_to_file("\n" + "=" * 80)
write_to_file("Scan process completed")
write_to_file("=" * 80)

print(f"\nScan completed! Results written to {output_file_path}")
print(f"Total signals found: {len(results)}")
