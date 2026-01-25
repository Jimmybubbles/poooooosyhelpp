import pandas as pd
import numpy as np
import talib
from datetime import datetime
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

def jma(data, length, phase, power, source):
    """Jurik Moving Average (JMA)"""
    phaseRatio = phase if -100 <= phase <= 100 else (100 if phase > 100 else -100)
    phaseRatio = (phaseRatio / 100) + 1.5
    beta = 0.45 * (length - 1) / (0.45 * (length - 1) + 2)
    alpha = np.power(beta, power)

    e0 = np.zeros_like(source)
    e1 = np.zeros_like(source)
    e2 = np.zeros_like(source)
    jma_result = np.zeros_like(source)

    for i in range(1, len(source)):
        e0[i] = (1 - alpha) * source[i] + alpha * e0[i-1]
        e1[i] = (source[i] - e0[i]) * (1 - beta) + beta * e1[i-1]
        e2[i] = (e0[i] + phaseRatio * e1[i] - jma_result[i-1]) * np.power(1 - alpha, 2) + np.power(alpha, 2) * e2[i-1]
        jma_result[i] = e2[i] + jma_result[i-1]

    return jma_result

def calculate_fader_signal(df):
    """Calculate Fader signal"""
    fmal_zl, smal_zl = 2, 2
    tmal_zl = fmal_zl + smal_zl
    Fmal_zl = smal_zl + tmal_zl
    Ftmal_zl = tmal_zl + Fmal_zl
    Smal_zl = Fmal_zl + Ftmal_zl

    close_array = df['Close'].values
    m1_zl = talib.WMA(close_array, timeperiod=fmal_zl)
    m2_zl = talib.WMA(m1_zl, timeperiod=smal_zl)
    m3_zl = talib.WMA(m2_zl, timeperiod=tmal_zl)
    m4_zl = talib.WMA(m3_zl, timeperiod=Fmal_zl)
    m5_zl = talib.WMA(m4_zl, timeperiod=Ftmal_zl)
    mavw_zl = hma(m5_zl, Smal_zl)
    jma_result = jma(close_array, 7, 126, 0.89144, close_array)
    signal = (mavw_zl + jma_result) / 2
    signal_series = pd.Series(signal, index=df.index)
    signal_color = np.where(signal_series > signal_series.shift(1), 'green', 'red')
    return signal_series, signal_color

def calculate_efi_tradingview(df, bollperiod=68, fiperiod=13, fisf=13, fi_asf_len=1, sens=11, useemaforboll=True):
    """
    Calculate EFI exactly as TradingView indicator
    Returns: fi_ema, fi_color, normprice, basis
    """
    # Calculate basis (Bollinger Band middle line)
    if useemaforboll:
        basis = talib.EMA(df['Close'].values, timeperiod=bollperiod)
    else:
        basis = hma(df['Close'].values, bollperiod)
    basis_series = pd.Series(basis, index=df.index)

    # Calculate ATR for volume proxy
    atr = talib.ATR(df['High'].values, df['Low'].values, df['Close'].values, timeperiod=sens)

    # Price_Volume = close * atr
    price_volume = df['Close'] * atr

    # Volume proxy = atr
    fake_volume = atr

    # vw = weighted price
    vw = price_volume / fake_volume

    # Force Index calculation
    close_change = df['Close'].diff()
    vw_sma = pd.Series(vw).rolling(window=fi_asf_len).mean()
    forceindex = (close_change * vw / vw_sma * fisf).fillna(0)

    # EMA of Force Index
    fi_ema = forceindex.ewm(span=fiperiod, adjust=False).mean()

    # Color determination
    fi_change = fi_ema.diff()
    fi_color = []
    for i in range(len(fi_ema)):
        if pd.isna(fi_ema.iloc[i]):
            fi_color.append('orange')
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

    # Normalized Price = close - basis
    normprice = df['Close'] - basis_series

    return fi_ema, fi_color, normprice, basis_series

def find_consolidation_range(df, current_idx, max_lookback=60):
    """Find consolidation"""
    if current_idx < 10:
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

# Load SRRK data
df = pd.read_csv('../updated_Results_for_scan/SRRK.csv')
df['Date'] = pd.to_datetime(df['Date'], utc=True)
df = df.sort_values('Date')
df = df.dropna()

# Find the index for January 9, 2026
target_date = pd.to_datetime('2026-01-09', utc=True)
df_filtered = df[df['Date'] == target_date]

if len(df_filtered) == 0:
    print("No data found for 2026-01-09")
else:
    current_idx = df_filtered.index[0]

    # Calculate TradingView EFI indicators (useemaforboll=True as per your settings)
    fi_ema, fi_color_list, normprice, basis = calculate_efi_tradingview(df, useemaforboll=True)

    # Calculate Fader
    fader_signal, fader_color = calculate_fader_signal(df)

    # Get values for the target date
    fi_value = fi_ema.iloc[current_idx]
    fi_color = fi_color_list[current_idx]
    norm_price_value = normprice.iloc[current_idx]
    basis_value = basis.iloc[current_idx]
    current_fader_color = fader_color[current_idx]
    prev_fader_color = fader_color[current_idx - 1] if current_idx > 0 else 'red'

    # Find consolidation
    range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

    # Get current price info
    current_price = df.iloc[current_idx]['Close']
    current_date = df.iloc[current_idx]['Date']

    print("=" * 90)
    print(f"SRRK ANALYSIS - {current_date.strftime('%A, %B %d, %Y')}")
    print("=" * 90)
    print()
    print(f"Close Price:              ${current_price:.2f}")
    print(f"Bollinger Basis (68 EMA): ${basis_value:.2f}")
    print()

    # Criterion 1: Channel
    print("CRITERION 1: CHANNEL CONSOLIDATION")
    print("-" * 90)
    if range_high is not None:
        position_in_range = ((current_price - range_low) / (range_high - range_low)) * 100
        print(f"  Status:                 ✓ CONSOLIDATING")
        print(f"  Duration:               {consol_days} days")
        print(f"  Range:                  ${range_low:.2f} - ${range_high:.2f}")
        print(f"  Range %:                {range_pct:.1f}%")
        print(f"  Position in Range:      {position_in_range:.1f}%")
        c1_pass = True
    else:
        print(f"  Status:                 ✗ NO CONSOLIDATION DETECTED")
        c1_pass = False
    print()

    # Criterion 2: EFI Histogram
    print("CRITERION 2: EFI HISTOGRAM (MAROON/ORANGE)")
    print("-" * 90)
    print(f"  EFI Value:              {fi_value:,.2f}")
    print(f"  EFI Color:              {fi_color}")
    c2_pass = fi_color in ['MAROON', 'ORANGE']
    if c2_pass:
        print(f"  Status:                 ✓ OVERSOLD ({fi_color})")
    else:
        print(f"  Status:                 ✗ NOT OVERSOLD ({fi_color})")
    print()

    # Criterion 3: Normalized Price (TradingView method)
    print("CRITERION 3: NORMALIZED PRICE > 0 (DIVERGENCE)")
    print("-" * 90)
    print(f"  Normalized Price:       {norm_price_value:.2f}")
    print(f"  (Close - BB Basis):     ${current_price:.2f} - ${basis_value:.2f}")
    c3_pass = norm_price_value > 0
    if c3_pass:
        print(f"  Status:                 ✓ ABOVE 0 (price above basis)")
        if c2_pass:
            print(f"  DIVERGENCE:             ✓ YES! Price strong while EFI weak")
        else:
            print(f"  DIVERGENCE:             ✗ NO (EFI not oversold)")
    else:
        print(f"  Status:                 ✗ BELOW 0 (price below basis)")
    print()

    # Criterion 4: Fader
    print("CRITERION 4: FADER SIGNAL (GREEN)")
    print("-" * 90)
    print(f"  Current Fader:          {current_fader_color.upper()}")
    print(f"  Previous Fader:         {prev_fader_color.upper()}")
    c4_pass = current_fader_color == 'green'
    if c4_pass:
        if prev_fader_color == 'red':
            print(f"  Status:                 ✓ GREEN (JUST TURNED FROM RED!)")
        else:
            print(f"  Status:                 ✓ GREEN (bullish momentum)")
    else:
        print(f"  Status:                 ✗ RED (bearish momentum)")
    print()

    # Final verdict
    print("=" * 90)
    print("FINAL VERDICT")
    print("=" * 90)
    all_pass = c1_pass and c2_pass and c3_pass and c4_pass

    print(f"  1. Channel:             {'✓ PASS' if c1_pass else '✗ FAIL'}")
    print(f"  2. EFI Oversold:        {'✓ PASS' if c2_pass else '✗ FAIL'}")
    print(f"  3. Norm Price > 0:      {'✓ PASS' if c3_pass else '✗ FAIL'}")
    print(f"  4. Fader GREEN:         {'✓ PASS' if c4_pass else '✗ FAIL'}")
    print()

    if all_pass:
        print("  🎯 ALL CRITERIA MET! This is a valid setup.")
    else:
        print(f"  ⚠️  {sum([c1_pass, c2_pass, c3_pass, c4_pass])}/4 criteria met.")
    print("=" * 90)
