import pandas as pd
import numpy as np
import talib
import os

def hma(data, period):
    """Calculate Hull Moving Average (HMA)"""
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    wma_half = talib.WMA(data, timeperiod=half_period)
    wma_full = talib.WMA(data, timeperiod=period)
    raw_hma = 2 * wma_half - wma_full
    hma_result = talib.WMA(raw_hma, timeperiod=sqrt_period)
    return hma_result

def calculate_efi_tradingview(df, bollperiod=68, fiperiod=13, fisf=13, fi_asf_len=1, sens=11, useemaforboll=True):
    """Calculate EFI exactly as TradingView indicator"""
    if useemaforboll:
        basis = talib.EMA(df['Close'].values, timeperiod=bollperiod)
    else:
        basis = hma(df['Close'].values, bollperiod)
    basis_series = pd.Series(basis, index=df.index)

    atr = talib.ATR(df['High'].values, df['Low'].values, df['Close'].values, timeperiod=sens)
    price_volume = df['Close'] * atr
    fake_volume = atr
    vw = price_volume / fake_volume

    close_change = df['Close'].diff()
    vw_sma = pd.Series(vw).rolling(window=fi_asf_len).mean()
    forceindex = (close_change * vw / vw_sma * fisf).fillna(0)
    fi_ema = forceindex.ewm(span=fiperiod, adjust=False).mean()

    fi_change = fi_ema.diff()
    fi_color = []
    for i in range(len(fi_ema)):
        if pd.isna(fi_ema.iloc[i]):
            fi_color.append('ORANGE')
        elif fi_ema.iloc[i] > 0:
            if i > 0 and fi_change.iloc[i] > 0:
                fi_color.append('LIME')
            else:
                fi_color.append('TEAL')
        else:
            if i > 0 and fi_change.iloc[i] < 0:
                fi_color.append('MAROON')
            else:
                fi_color.append('ORANGE')

    normprice = df['Close'] - basis_series
    return fi_ema, fi_color, normprice, basis_series

def find_consolidation_range(df, current_idx, lookback=20):
    """Simple channel detection"""
    if current_idx < lookback:
        lookback = current_idx

    if lookback < 1:
        return None, None, 0, 0

    window_data = df.iloc[max(0, current_idx - lookback + 1):current_idx + 1]
    range_high = window_data['High'].max()
    range_low = window_data['Low'].min()
    range_pct = ((range_high - range_low) / range_low) * 100 if range_low > 0 else 0

    return range_high, range_low, lookback, range_pct

# Test AMR
ticker = 'AMR'
file_path = f'../updated_Results_for_scan/{ticker}.csv'

df = pd.read_csv(file_path, skiprows=[1, 2])
df.columns = df.columns.str.strip()

# Check if required columns exist
required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
print(f"Columns in CSV: {df.columns.tolist()}")
print(f"Has all required: {all(col in df.columns for col in required_cols)}")
print()

# Prepare data
df['Date'] = pd.to_datetime(df['Date'], utc=True)
df = df.sort_values('Date')
df.set_index('Date', inplace=True)

# Convert to numeric
for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

df = df.dropna()

print(f"Data loaded: {len(df)} rows")
print(f"Date range: {df.index[0]} to {df.index[-1]}")
print()

current_idx = len(df) - 1
current_price = df['Close'].iloc[current_idx]

print(f"Current index: {current_idx}")
print(f"Current price: ${current_price:.2f}")
print()

# Calculate EFI
fi_ema, fi_color_list, normprice, basis = calculate_efi_tradingview(df, useemaforboll=True)
fi_value = fi_ema.iloc[current_idx]
fi_color = fi_color_list[current_idx]
norm_price_value = normprice.iloc[current_idx]

print(f"EFI Value: {fi_value:.2f}")
print(f"EFI Color: {fi_color}")
print(f"Normalized Price: {norm_price_value:.2f}")
print()

# Find channel
range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

print(f"Range High: {range_high}")
print(f"Range Low: {range_low}")
print(f"Consol Days: {consol_days}")
print(f"Range %: {range_pct}")
print()

# Check criteria
criterion_1 = consol_days > 0
criterion_2 = fi_color in ['MAROON', 'ORANGE']
criterion_3 = norm_price_value > 0

print(f"Criterion 1 (Channel > 0): {criterion_1}")
print(f"Criterion 2 (EFI oversold): {criterion_2}")
print(f"Criterion 3 (Norm Price > 0): {criterion_3}")
print()

if range_high is None:
    print("FAIL: range_high is None")
elif criterion_1 and criterion_2 and criterion_3:
    print("SUCCESS: All criteria met!")
else:
    print("FAIL: Not all criteria met")
