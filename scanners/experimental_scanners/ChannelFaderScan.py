import pandas as pd
import numpy as np
import os
import talib
from datetime import datetime, timedelta

# Directory path
input_directory = r'watchlist_Scanner\updated_Results_for_scan'

# Sorted results output file
sorted_output_file_name = "sorted_fader_scan_results.txt"
sorted_output_file_path = os.path.join('watchlist_Scanner', 'buylist', sorted_output_file_name)

# EMA and ATR parameters for channel detection
ema1_per = 5
ema2_per = 26
atr_per = 50
atr_mult = 0.4

# Fader parameters (from Pine Script)
# Note: TA-Lib requires minimum period of 2 for WMA, adjusted from original Pine Script values
fmal_zl = 2  # Rainbow Length 1 (original: 1, adjusted for TA-Lib)
smal_zl = 2  # Rainbow Length 2 (original: 1, adjusted for TA-Lib)
length_jma = 7  # JMA Smoothing Length
phase = 126  # JMA Smoothing Phase
power = 0.89144  # JMA Smoothing Power

# Get the date for one week ago (focus on recent signals)
one_week_ago = datetime.now() - timedelta(days=7)

# Get yesterday's date (we want signals from the previous trading day)
yesterday = datetime.now() - timedelta(days=1)

# Minimum trading days for channel formation (reduced to catch more signals)
min_channel_days = 3  # Just need a channel to be forming, not necessarily 3 weeks

def write_to_sorted_file(text):
    with open(sorted_output_file_path, 'a') as file:
        file.write(text + '\n')

def hma(data, period):
    """
    Calculate Hull Moving Average (HMA).
    HMA = WMA(2 * WMA(n/2) - WMA(n), sqrt(n))
    """
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))

    wma_half = talib.WMA(data, timeperiod=half_period)
    wma_full = talib.WMA(data, timeperiod=period)

    # 2 * WMA(n/2) - WMA(n)
    raw_hma = 2 * wma_half - wma_full

    # WMA of the result with sqrt(n) period
    hma_result = talib.WMA(raw_hma, timeperiod=sqrt_period)

    return hma_result

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

def calculate_fader(data):
    """
    Translate Pine Script Fader indicator to Python.
    Returns the fader signal and color (True for green/bullish, False for red/bearish).
    """
    close_prices = data['Close'].values

    # Calculate the rainbow lengths from Pine Script
    tmal_zl = fmal_zl + smal_zl
    Fmal_zl = smal_zl + tmal_zl
    Ftmal_zl = tmal_zl + Fmal_zl
    Smal_zl = Fmal_zl + Ftmal_zl

    # Calculate WMAs (Weighted Moving Averages)
    M1_zl = talib.WMA(close_prices, timeperiod=fmal_zl)
    M2_zl = talib.WMA(M1_zl, timeperiod=smal_zl)
    M3_zl = talib.WMA(M2_zl, timeperiod=tmal_zl)
    M4_zl = talib.WMA(M3_zl, timeperiod=Fmal_zl)
    M5_zl = talib.WMA(M4_zl, timeperiod=Ftmal_zl)

    # Calculate HMA (Hull Moving Average) - using custom implementation
    MAVW_zl = hma(M5_zl, Smal_zl)

    # JMA (Jurik Moving Average) calculation
    phaseRatio = 0.5 if phase < -100 else (2.5 if phase > 100 else phase / 100 + 1.5)
    beta = 0.45 * (length_jma - 1) / (0.45 * (length_jma - 1) + 2)
    alpha = pow(beta, power)

    # Initialize JMA arrays
    jma_2 = np.zeros(len(close_prices))
    e0 = np.zeros(len(close_prices))
    e1 = np.zeros(len(close_prices))
    e2 = np.zeros(len(close_prices))

    # Calculate JMA iteratively (this mimics Pine Script's series behavior)
    for i in range(len(close_prices)):
        if i == 0:
            e0[i] = close_prices[i]
            e1[i] = 0
            e2[i] = 0
            jma_2[i] = close_prices[i]
        else:
            e0[i] = (1 - alpha) * close_prices[i] + alpha * e0[i-1]
            e1[i] = (close_prices[i] - e0[i]) * (1 - beta) + beta * e1[i-1]
            e2[i] = (e0[i] + phaseRatio * e1[i] - jma_2[i-1]) * pow(1 - alpha, 2) + pow(alpha, 2) * e2[i-1]
            jma_2[i] = e2[i] + jma_2[i-1]

    # Calculate final signal (average of MAVW_zl and jma_2)
    signal = (MAVW_zl + jma_2) / 2

    # Determine if signal is bullish (green) or bearish (red)
    # Green when signal > previous signal
    is_green = pd.Series(signal).diff() > 0

    return signal, is_green

def check_fader_turn_green_yesterday(is_green, current_index):
    """
    Check if fader turned from red to green on the current day (most recent bar).
    Returns True if there was a turn from red to green at current_index.
    """
    if current_index < 1:
        return False

    # Check if previous bar was red and current bar is green
    return not is_green.iloc[current_index - 1] and is_green.iloc[current_index]

# Clear the sorted output file before starting
if os.path.exists(sorted_output_file_path):
    os.remove(sorted_output_file_path)

# Store all signals for sorting
buy_signals = []

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

        # Need at least 100 bars for calculations
        if len(data) < 100:
            continue

        # Calculate EMAs and ATR for channel detection
        ema1 = talib.EMA(data['Close'], timeperiod=ema1_per)
        ema2 = talib.EMA(data['Close'], timeperiod=ema2_per)
        atr = talib.ATR(data['High'], data['Low'], data['Close'], timeperiod=atr_per) * atr_mult

        # Calculate Squeeze Channel Levels
        SqLup = (ema2 + atr).where((ema2 - ema1).abs() < atr, float('nan'))
        SqLdn = (ema2 - atr).where((ema2 - ema1).abs() < atr, float('nan'))

        # Calculate Fader indicator
        fader_signal, is_green = calculate_fader(data)

        # Check for channel breakouts over last week (focus on recent signals)
        for i in range(3, len(data)):
            date_of_event = pd.Timestamp(data.index[i]).tz_localize(None) if pd.Timestamp(data.index[i]).tzinfo else pd.Timestamp(data.index[i])
            if date_of_event < one_week_ago:
                continue

            # Check if fader turned from red to green on this bar (yesterday's close)
            fader_turned_green = check_fader_turn_green_yesterday(is_green, i)

            # If fader turned green, check if there's a channel present
            if fader_turned_green:
                # Check if a channel is currently forming (both upper and lower bounds exist)
                channel_exists = not pd.isna(SqLup.iloc[i]) and not pd.isna(SqLdn.iloc[i])

                if channel_exists:
                    # Count how long the channel has been forming
                    channel_days = count_channel_days(SqLup, SqLdn, i)

                    # Only proceed if channel existed for minimum required days
                    if channel_days >= min_channel_days:
                        buy_signals.append({
                            'ticker': ticker_symbol,
                            'date': date_of_event.strftime('%m/%d/%Y'),
                            'channel_days': channel_days,
                            'price': data['Close'].iloc[i],
                            'fader_value': round(fader_signal[i], 3)
                        })

    except Exception as e:
        print(f"Exception encountered for {ticker_symbol}: {str(e)}")
        print(f"Exception type: {type(e)}")

# Sort buy signals by price (ascending - cheaper stocks first)
buy_signals.sort(key=lambda x: x['price'])

# Write sorted BUY signals
write_to_sorted_file("=" * 80)
write_to_sorted_file(f"FADER GREEN + CHANNEL FORMING SIGNALS ({len(buy_signals)} total)")
write_to_sorted_file("=" * 80)
write_to_sorted_file("Conditions: Channel forming (squeeze) + Fader turned RED to GREEN yesterday")
write_to_sorted_file("Timeframe: Daily | Scanning last week for Fader turning green while in a channel")
write_to_sorted_file("=" * 80)
for signal in buy_signals:
    write_to_sorted_file(f"BUY {signal['ticker']} {signal['date']} : {signal['channel_days']} day channel breakout - Price: {round(signal['price'], 3)} - Fader: {signal['fader_value']}")

write_to_sorted_file("\n" + "=" * 80)
write_to_sorted_file("Scan process completed")
write_to_sorted_file("=" * 80)

print(f"\nScan completed! Found {len(buy_signals)} BUY signals with Fader confirmation.")
print(f"Results saved to: {sorted_output_file_path}")
