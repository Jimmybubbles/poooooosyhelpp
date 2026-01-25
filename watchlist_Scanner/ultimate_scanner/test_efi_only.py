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

# Scan directory
data_dir = Path('../updated_Results_for_scan')
csv_files = sorted(data_dir.glob('*.csv'))

print("=" * 100)
print("EFI DIVERGENCE TEST - CHECKING ONLY EFI CRITERIA")
print("=" * 100)
print()
print("CRITERIA:")
print("  1. EFI Histogram Color: MAROON or ORANGE (oversold)")
print("  2. Normalized Price > 0 (Close above 68 EMA)")
print()
print("=" * 100)
print()

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

        if efi_oversold and normprice_positive:
            results.append({
                'Ticker': ticker,
                'Date': current_date.strftime('%Y-%m-%d'),
                'Price': current_price,
                'Basis_68EMA': current_basis,
                'NormPrice': current_normprice,
                'EFI_Value': current_fi_value,
                'EFI_Color': current_fi_color
            })

    except Exception as e:
        continue

print(f"Scanned {len(csv_files)} stocks")
print(f"Found {len(results)} stocks meeting EFI divergence criteria")
print()

if len(results) > 0:
    print("=" * 100)
    print("RESULTS - Stocks with EFI Divergence (Oversold EFI + Price Above 68 EMA)")
    print("=" * 100)
    print()

    # Sort by normalized price (highest divergence first)
    results_sorted = sorted(results, key=lambda x: x['NormPrice'], reverse=True)

    print(f"{'Ticker':<8} {'Date':<12} {'Price':>8} {'68EMA':>8} {'Norm':>7} {'EFI Val':>10} {'EFI Color':<8}")
    print("-" * 100)

    for r in results_sorted:
        print(f"{r['Ticker']:<8} {r['Date']:<12} ${r['Price']:>7.2f} ${r['Basis_68EMA']:>7.2f} "
              f"{r['NormPrice']:>7.2f} {r['EFI_Value']:>10.2f} {r['EFI_Color']:<8}")

    print()
    print("=" * 100)
    print(f"Total: {len(results)} stocks showing EFI divergence")
    print()

    # Create TradingView list
    ticker_list = ', '.join([r['Ticker'] for r in results_sorted])
    print("TradingView Ticker List:")
    print(ticker_list)
    print()

else:
    print("No stocks found with EFI divergence (MAROON/ORANGE histogram + normalized price > 0)")
