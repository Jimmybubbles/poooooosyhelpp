import pandas as pd
import numpy as np
import os
from pathlib import Path
import talib

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

def calculate_fader_signal(df, fmal_zl=2, smal_zl=2, length_jma=7, phase=126, power=0.89144):
    """Calculate Fader signal (green = bullish, red = bearish)"""
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

    jma_result = jma(close_array, length_jma, phase, power, close_array)

    signal = (mavw_zl + jma_result) / 2
    signal_series = pd.Series(signal, index=df.index)
    signal_color = np.where(signal_series > signal_series.shift(1), 'green', 'red')

    return signal_series, signal_color

def calculate_force_index(df):
    """Calculate Elder Force Index (13-period EMA)"""
    force = (df['Close'] - df['Close'].shift(1)) * df['Volume']
    return force.ewm(span=13, adjust=False).mean()

def get_force_index_color(fi_value, fi_std):
    """Determine Force Index color"""
    if fi_value < -2.0 * fi_std:
        return 'maroon'
    elif fi_value < 0:
        return 'orange'
    elif fi_value > 2.0 * fi_std:
        return 'green'
    else:
        return 'lime'

def calculate_normalized_price(df, lookback=20):
    """Calculate normalized price position in range"""
    highest = df['High'].rolling(window=lookback).max()
    lowest = df['Low'].rolling(window=lookback).min()
    range_size = highest - lowest
    range_size = range_size.replace(0, np.nan)
    normalized = 2 * ((df['Close'] - lowest) / range_size) - 1
    return normalized

def find_consolidation_range(df, current_idx, max_lookback=60):
    """Find dynamic consolidation range"""
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

    if best_range and best_days >= 10:
        range_pct = ((best_range[0] - best_range[1]) / best_range[1]) * 100
        return best_range[0], best_range[1], best_days, range_pct

    return None, None, None, None

# Test on sample stocks
data_dir = Path("../updated_Results_for_scan")
test_tickers = ['AAPL', 'MSFT', 'TSLA', 'NVDA', 'AMD', 'GOOGL', 'META', 'AMZN', 'NFLX', 'SPY',
                'KBH', 'FORM', 'TWI', 'XPO', 'NUE', 'AMAT', 'VFC', 'CMI']

print("=" * 110)
print("FULL CRITERIA TEST - Channel + EFI Divergence + Fader")
print("=" * 110)
print()
print(f"{'Ticker':<8} {'C1:Ch10d':<10} {'C2:EFI<0':<12} {'C3:Norm>0':<12} {'C4:Fader':<12} {'ALL':<6}")
print("-" * 110)

stats = {
    'total': 0,
    'c1_pass': 0,
    'c2_pass': 0,
    'c3_pass': 0,
    'c4_pass': 0,
    'all_pass': 0
}

for ticker in test_tickers:
    file_path = data_dir / f"{ticker}.csv"
    if not file_path.exists():
        continue

    try:
        df = pd.read_csv(file_path, skiprows=[1, 2])
        if 'Price' in df.columns:
            df.rename(columns={'Price': 'Date'}, inplace=True)

        df['Date'] = pd.to_datetime(df['Date'], utc=True)
        df = df.sort_values('Date')

        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna()

        if len(df) < 60:
            continue

        stats['total'] += 1
        current_idx = len(df) - 1

        # Calculate indicators
        force_index = calculate_force_index(df)
        normalized_price = calculate_normalized_price(df)
        fader_signal, fader_color = calculate_fader_signal(df)

        fi_value = force_index.iloc[current_idx]
        fi_std = force_index.std()
        fi_color = get_force_index_color(fi_value, fi_std)
        norm_price_value = normalized_price.iloc[current_idx]
        current_fader_color = fader_color[current_idx]

        range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

        # Check criteria
        c1 = (range_high is not None) and (consol_days >= 10)
        c2 = fi_color in ['maroon', 'orange']
        c3 = norm_price_value > 0
        c4 = current_fader_color == 'green'
        all_pass = c1 and c2 and c3 and c4

        if c1:
            stats['c1_pass'] += 1
        if c2:
            stats['c2_pass'] += 1
        if c3:
            stats['c3_pass'] += 1
        if c4:
            stats['c4_pass'] += 1
        if all_pass:
            stats['all_pass'] += 1

        c1_str = f"PASS ({consol_days}d)" if c1 else "FAIL"
        c2_str = f"PASS ({fi_color})" if c2 else f"FAIL ({fi_color})"
        c3_str = f"PASS ({norm_price_value:.2f})" if c3 else f"FAIL ({norm_price_value:.2f})"
        c4_str = f"PASS ({current_fader_color})" if c4 else f"FAIL ({current_fader_color})"
        all_str = "YES !" if all_pass else "NO"

        print(f"{ticker:<8} {c1_str:<10} {c2_str:<12} {c3_str:<12} {c4_str:<12} {all_str:<6}")

    except Exception as e:
        print(f"{ticker:<8} ERROR: {e}")

print("-" * 110)
print()
print("SUMMARY:")
print(f"  Total stocks tested:           {stats['total']}")
print(f"  C1 (Channel 10+ days):         {stats['c1_pass']}/{stats['total']} ({stats['c1_pass']/stats['total']*100:.1f}%)")
print(f"  C2 (EFI Oversold):             {stats['c2_pass']}/{stats['total']} ({stats['c2_pass']/stats['total']*100:.1f}%)")
print(f"  C3 (Norm Price > 0):           {stats['c3_pass']}/{stats['total']} ({stats['c3_pass']/stats['total']*100:.1f}%)")
print(f"  C4 (Fader GREEN):              {stats['c4_pass']}/{stats['total']} ({stats['c4_pass']/stats['total']*100:.1f}%)")
print(f"  ALL CRITERIA PASS:             {stats['all_pass']}/{stats['total']} ({stats['all_pass']/stats['total']*100:.1f}%)")
print("=" * 110)
