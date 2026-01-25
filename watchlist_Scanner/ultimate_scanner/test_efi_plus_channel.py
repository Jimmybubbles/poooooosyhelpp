import pandas as pd
import numpy as np
import talib
from pathlib import Path
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

# Scan directory
data_dir = Path('../updated_Results_for_scan')
csv_files = sorted(data_dir.glob('*.csv'))

print("=" * 100)
print("EFI DIVERGENCE + CHANNEL TEST")
print("=" * 100)
print()
print("CRITERIA:")
print("  1. Channel consolidation (< 15% range, 70%+ touches)")
print("  2. EFI Histogram Color: MAROON or ORANGE (oversold)")
print("  3. Normalized Price > 0 (Close above 68 EMA)")
print()
print("=" * 100)
print()

efi_only = 0
channel_only = 0
both = 0
results = []

for i, csv_file in enumerate(csv_files, 1):
    ticker = csv_file.stem

    try:
        df = pd.read_csv(csv_file, skiprows=[1, 2])
        df.columns = df.columns.str.strip()

        if 'Date' not in df.columns or 'Close' not in df.columns:
            continue

        df['Date'] = pd.to_datetime(df['Date'], utc=True)
        df = df.sort_values('Date')
        df = df.dropna()

        if len(df) < 100:
            continue

        # Calculate EFI indicators
        fi_ema, fi_color_list, normprice, basis = calculate_efi_tradingview(df, useemaforboll=True)

        # Check most recent bar
        current_idx = len(df) - 1
        current_fi_color = fi_color_list[current_idx]
        current_normprice = normprice.iloc[current_idx]
        current_fi_value = fi_ema.iloc[current_idx]
        current_price = df.iloc[current_idx]['Close']
        current_basis = basis.iloc[current_idx]
        current_date = df.iloc[current_idx]['Date']

        # Check EFI criteria
        efi_oversold = current_fi_color in ['MAROON', 'ORANGE']
        normprice_positive = current_normprice > 0
        has_efi_divergence = efi_oversold and normprice_positive

        # Check channel
        range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)
        has_channel = range_high is not None and consol_days > 0

        if has_efi_divergence:
            efi_only += 1
        if has_channel:
            channel_only += 1

        if has_efi_divergence and has_channel:
            both += 1
            results.append({
                'Ticker': ticker,
                'Date': current_date.strftime('%Y-%m-%d'),
                'Price': current_price,
                'Basis_68EMA': current_basis,
                'NormPrice': current_normprice,
                'EFI_Value': current_fi_value,
                'EFI_Color': current_fi_color,
                'Channel_Days': consol_days,
                'Range_Pct': range_pct,
                'Range_Low': range_low,
                'Range_High': range_high
            })

    except Exception as e:
        continue

print(f"Scanned {len(csv_files)} stocks")
print()
print(f"Stocks with EFI divergence:        {efi_only}")
print(f"Stocks with channel consolidation: {channel_only}")
print(f"Stocks with BOTH (complete setup): {both}")
print()

if len(results) > 0:
    print("=" * 100)
    print("COMPLETE SETUPS - EFI Divergence + Channel Consolidation")
    print("=" * 100)
    print()

    # Sort by normalized price (highest divergence first)
    results_sorted = sorted(results, key=lambda x: x['NormPrice'], reverse=True)

    print(f"{'Ticker':<8} {'Date':<12} {'Price':>8} {'Norm':>7} {'EFI':>8} {'Ch Days':>8} {'Range%':>7}")
    print("-" * 100)

    for r in results_sorted:
        print(f"{r['Ticker']:<8} {r['Date']:<12} ${r['Price']:>7.2f} "
              f"{r['NormPrice']:>7.2f} {r['EFI_Color']:<8} {r['Channel_Days']:>8}d {r['Range_Pct']:>6.1f}%")

    print()
    print("=" * 100)
    print(f"Total: {len(results)} complete setups")
    print()

    # Create TradingView list
    ticker_list = ', '.join([r['Ticker'] for r in results_sorted])
    print("TradingView Ticker List:")
    print(ticker_list)
    print()

else:
    print("No stocks found with both EFI divergence AND channel consolidation")
    print()
    print("This means the channel requirement (< 15% range with 70%+ touches) is the limiting factor.")
