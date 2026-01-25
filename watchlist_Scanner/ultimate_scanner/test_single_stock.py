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

print(f"Testing {ticker}")
print(f"Current Index: {current_idx}")
print(f"Date: {df.index[current_idx]}")
print(f"Close: ${df['Close'].iloc[current_idx]:.2f}")
print(f"Basis (68 EMA): ${basis.iloc[current_idx]:.2f}")
print(f"Normalized Price: {normprice.iloc[current_idx]:.2f}")
print(f"EFI Value: {fi_ema.iloc[current_idx]:.2f}")
print(f"EFI Color: {fi_color_list[current_idx]}")
print()
print(f"Criterion 2 (EFI oversold): {fi_color_list[current_idx] in ['MAROON', 'ORANGE']}")
print(f"Criterion 3 (Norm Price > 0): {normprice.iloc[current_idx] > 0}")
