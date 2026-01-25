import pandas as pd
import numpy as np
import talib
import sys
import io

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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

def find_consolidation_range(df, current_idx, max_lookback=60):
    """Find consolidation"""
    if current_idx < 20:
        return None, None, None, None

    lookback_data = df.iloc[max(0, current_idx - max_lookback):current_idx + 1]
    best_range = None
    best_days = 0

    for window in range(60, 9, -1):
        if window > len(lookback_data):
            continue

        window_data = lookback_data.tail(window)
        high = window_data['High'].max()
        low = window_data['Low'].min()
        range_pct = ((high - low) / low) * 100

        if range_pct <= 15:
            touches = 0
            tolerance = (high - low) * 0.15

            for _, row in window_data.iterrows():
                if row['Low'] <= (low + tolerance) or row['High'] >= (high - tolerance):
                    touches += 1

            touch_pct = (touches / len(window_data)) * 100

            if touch_pct >= 70:
                if window > best_days:
                    best_range = (high, low)
                    best_days = window

    if best_range and best_days > 0:
        range_pct = ((best_range[0] - best_range[1]) / best_range[1]) * 100
        return best_range[0], best_range[1], best_days, range_pct

    return None, None, None, None

# Test AMR (should be in results)
ticker = 'AMR'
df = pd.read_csv(f'../updated_Results_for_scan/{ticker}.csv', skiprows=[1, 2])
df.columns = df.columns.str.strip()
df['Date'] = pd.to_datetime(df['Date'], utc=True)
df = df.sort_values('Date')
df = df.dropna()
df = df.set_index('Date')

current_idx = len(df) - 1

# Calculate EFI
fi_ema, fi_color_list, normprice, basis = calculate_efi_tradingview(df, useemaforboll=True)

# Find consolidation
range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

print(f"Testing {ticker}")
print(f"Current Index: {current_idx}")
print(f"Date: {df.index[current_idx]}")
print()
print(f"Close: ${df['Close'].iloc[current_idx]:.2f}")
print(f"Basis (68 EMA): ${basis.iloc[current_idx]:.2f}")
print(f"Normalized Price: {normprice.iloc[current_idx]:.2f}")
print(f"EFI Value: {fi_ema.iloc[current_idx]:.2f}")
print(f"EFI Color: {fi_color_list[current_idx]}")
print()
print(f"Channel: {range_high is not None}")
if range_high:
    print(f"  Range High: ${range_high:.2f}")
    print(f"  Range Low: ${range_low:.2f}")
    print(f"  Days: {consol_days}")
    print(f"  Range %: {range_pct:.1f}%")
print()
print(f"✓ Criterion 1 (Channel): {consol_days > 0 if consol_days else False}")
print(f"✓ Criterion 2 (EFI oversold): {fi_color_list[current_idx] in ['MAROON', 'ORANGE']}")
print(f"✓ Criterion 3 (Norm Price > 0): {normprice.iloc[current_idx] > 0}")
print()
all_pass = (consol_days and consol_days > 0) and (fi_color_list[current_idx] in ['MAROON', 'ORANGE']) and (normprice.iloc[current_idx] > 0)
print(f"ALL CRITERIA MET: {all_pass}")
