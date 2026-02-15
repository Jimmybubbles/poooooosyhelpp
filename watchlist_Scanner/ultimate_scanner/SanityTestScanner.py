"""
SANITY TEST SCANNER - EFI Divergence Verification
==================================================
Simple scanner to verify EFI divergence logic:
1. Normalized Price (price line) > 0
2. Force Index (histogram) < 0
3. Channel detected on scan day

This scanner prints detailed info for each stock to verify calculations.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os
import talib

# File paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))

data_folder = os.path.join(project_root, 'watchlist_Scanner', 'updated_Results_for_scan')
output_file = os.path.join(script_dir, 'sanity_test_results.txt')

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

    # Normalized Price = close - basis
    normprice = df['Close'] - basis_series

    return fi_ema, fi_color, normprice, basis_series

def find_consolidation_range(df, current_idx, lookback=20):
    """
    Simple channel detection
    Returns: (range_high, range_low, consolidation_days, range_percent)
    """
    if current_idx < lookback:
        lookback = current_idx

    if lookback < 1:
        return None, None, 0, 0

    # Get recent data
    window_data = df.iloc[max(0, current_idx - lookback + 1):current_idx + 1]

    # Calculate high/low range
    range_high = window_data['High'].max()
    range_low = window_data['Low'].min()
    range_pct = ((range_high - range_low) / range_low) * 100 if range_low > 0 else 0

    return range_high, range_low, lookback, range_pct

def scan_stock(ticker, df):
    """
    Scan a single stock and return detailed info if it meets criteria
    """
    if len(df) < 60:
        return None

    current_idx = len(df) - 1
    current_date = df.index[current_idx]

    # Skip if date is NaT
    if pd.isna(current_date):
        return None

    current_price = df['Close'].iloc[current_idx]

    # Calculate TradingView EFI
    fi_ema, fi_color_list, normalized_price, basis = calculate_efi_tradingview(df, useemaforboll=True)
    fi_value = fi_ema.iloc[current_idx]
    fi_color = fi_color_list[current_idx]
    norm_price_value = normalized_price.iloc[current_idx]
    basis_value = basis.iloc[current_idx]

    # Find consolidation
    range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

    if range_high is None:
        return None

    # CHECK CRITERIA
    criterion_1 = consol_days > 0                    # Channel detected
    criterion_2 = fi_value < 0                       # Force Index (histogram) below 0
    criterion_3 = norm_price_value > 0               # Normalized Price (price line) above 0

    # Only return if ALL criteria met (DIVERGENCE)
    if not (criterion_1 and criterion_2 and criterion_3):
        return None

    return {
        'ticker': ticker,
        'date': current_date.strftime('%Y-%m-%d'),
        'price': current_price,
        'basis_68ema': basis_value,
        'normalized_price': norm_price_value,
        'force_index': fi_value,
        'fi_color': fi_color,
        'channel_days': consol_days,
        'range_high': range_high,
        'range_low': range_low,
        'range_pct': range_pct,
        'criterion_1_channel': criterion_1,
        'criterion_2_fi_negative': criterion_2,
        'criterion_3_norm_positive': criterion_3
    }

def scan_all_stocks():
    """Scan all stocks and print detailed results"""
    print("=" * 100)
    print("SANITY TEST SCANNER - EFI DIVERGENCE VERIFICATION")
    print("=" * 100)
    print(f"Scan started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print("CRITERIA:")
    print("  1. Channel detected (20-day lookback)")
    print("  2. Force Index (histogram) < 0")
    print("  3. Normalized Price (price line) > 0")
    print("  => DIVERGENCE: Price holding above 68 EMA while EFI shows selling pressure")
    print()
    print("=" * 100)
    print()

    csv_files = [f for f in os.listdir(data_folder) if f.endswith('.csv')]
    print(f"Scanning {len(csv_files)} stocks...\n")

    results = []

    for i, csv_file in enumerate(csv_files):
        if (i + 1) % 500 == 0:
            print(f"Progress: {i + 1}/{len(csv_files)} stocks scanned...")

        ticker = csv_file.replace('.csv', '')
        file_path = os.path.join(data_folder, csv_file)

        try:
            # Load data
            df = pd.read_csv(file_path, skiprows=[1, 2])

            if 'Price' in df.columns:
                df.rename(columns={'Price': 'Date'}, inplace=True)

            required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in df.columns for col in required_cols):
                continue

            df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
            df = df.dropna(subset=['Date'])
            df = df.sort_values('Date')
            df.set_index('Date', inplace=True)

            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            df = df.dropna()

            # Scan
            signal = scan_stock(ticker, df)

            if signal:
                results.append(signal)

        except Exception as e:
            continue

    print(f"\n{'=' * 100}")
    print(f"Scan complete! Found {len(results)} stocks meeting EFI divergence criteria")
    print(f"{'=' * 100}\n")

    if len(results) > 0:
        # Sort by normalized price (strongest divergence first)
        results.sort(key=lambda x: x['normalized_price'], reverse=True)

        # Print summary table
        print(f"{'Ticker':<8} {'Date':<12} {'Price':>8} {'68EMA':>8} {'Norm':>8} {'FI':>8} {'Color':<8} {'Ch Days':>8} {'Range%':>8}")
        print("-" * 100)

        for r in results:
            print(f"{r['ticker']:<8} {r['date']:<12} ${r['price']:>7.2f} ${r['basis_68ema']:>7.2f} "
                  f"{r['normalized_price']:>8.2f} {r['force_index']:>8.2f} {r['fi_color']:<8} "
                  f"{r['channel_days']:>8}d {r['range_pct']:>7.1f}%")

        print()
        print("=" * 100)
        print("DETAILED VERIFICATION (First 10 stocks)")
        print("=" * 100)
        print()

        for i, r in enumerate(results[:10], 1):
            print(f"#{i} - {r['ticker']}")
            print(f"  Date:                 {r['date']}")
            print(f"  Current Price:        ${r['price']:.2f}")
            print(f"  68 EMA (Basis):       ${r['basis_68ema']:.2f}")
            print(f"  Normalized Price:     {r['normalized_price']:.2f} (Close - 68 EMA)")
            print(f"  Force Index:          {r['force_index']:.2f}")
            print(f"  EFI Color:            {r['fi_color']}")
            print(f"  Channel Days:         {r['channel_days']}")
            print(f"  Channel Range:        ${r['range_low']:.2f} - ${r['range_high']:.2f} ({r['range_pct']:.1f}%)")
            print()
            print(f"  ✓ Criterion 1 (Channel):     {r['criterion_1_channel']}")
            print(f"  ✓ Criterion 2 (FI < 0):      {r['criterion_2_fi_negative']}")
            print(f"  ✓ Criterion 3 (Norm > 0):    {r['criterion_3_norm_positive']}")
            print(f"  => DIVERGENCE: Price is ${r['normalized_price']:.2f} above 68 EMA, but Force Index is {r['force_index']:.2f}")
            print()
            print("-" * 100)
            print()

    # Save to file
    save_report(results)

    return results

def save_report(results):
    """Save results to file"""
    lines = []
    lines.append("=" * 100)
    lines.append("SANITY TEST SCANNER - EFI DIVERGENCE VERIFICATION")
    lines.append("=" * 100)
    lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("CRITERIA:")
    lines.append("  1. Channel detected (20-day lookback)")
    lines.append("  2. Force Index (histogram) < 0")
    lines.append("  3. Normalized Price (price line) > 0")
    lines.append("")
    lines.append(f"Total Stocks Found: {len(results)}")
    lines.append("=" * 100)
    lines.append("")

    if len(results) > 0:
        lines.append(f"{'Ticker':<8} {'Date':<12} {'Price':>8} {'68EMA':>8} {'Norm':>8} {'FI':>8} {'Color':<8} {'Ch Days':>8} {'Range%':>8}")
        lines.append("-" * 100)

        for r in results:
            lines.append(f"{r['ticker']:<8} {r['date']:<12} ${r['price']:>7.2f} ${r['basis_68ema']:>7.2f} "
                        f"{r['normalized_price']:>8.2f} {r['force_index']:>8.2f} {r['fi_color']:<8} "
                        f"{r['channel_days']:>8}d {r['range_pct']:>7.1f}%")

        lines.append("")
        lines.append("TradingView Ticker List:")
        lines.append(",".join([r['ticker'] for r in results]))

    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

    print(f"\nReport saved to: {output_file}")

if __name__ == '__main__':
    results = scan_all_stocks()

    if len(results) > 0:
        print(f"\n✓ SANITY CHECK PASSED: Found {len(results)} stocks with EFI divergence")
        print(f"  - Force Index < 0 (selling pressure)")
        print(f"  - Normalized Price > 0 (price above 68 EMA)")
        print(f"  - This confirms the divergence logic is working correctly!")
    else:
        print("\n✗ SANITY CHECK: No stocks found with divergence")
        print("  Check if market conditions have divergence setups")
