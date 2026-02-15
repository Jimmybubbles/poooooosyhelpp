"""
LONG CROSS INDICATIONS SCANNER
================================
Detects bullish crossover signals:
1. Normalized Price Line crosses above 0 (close crosses above 68 EMA)
2. EFI Histogram changes from ORANGE/MAROON to LIME/GREEN
3. Jimmy Squeeze Channel actively printing
4. Fader line is GREEN (bullish momentum)

This catches the exact moment of bullish reversal/breakout
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
output_file = os.path.join(script_dir, 'long_cross_indications.txt')
tradingview_file = os.path.join(script_dir, 'tradingview_long_cross_list.txt')

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

def find_consolidation_range(df, current_idx, ema1_per=5, ema2_per=26, atr_per=50, atr_mult=0.4):
    """Jimmy Channel Scan - Squeeze Channel detection"""
    if current_idx < max(ema1_per, ema2_per, atr_per):
        return None, None, 0, 0

    ema1 = talib.EMA(df['Close'].values, timeperiod=ema1_per)
    ema2 = talib.EMA(df['Close'].values, timeperiod=ema2_per)
    atr = talib.ATR(df['High'].values, df['Low'].values, df['Close'].values, timeperiod=atr_per) * atr_mult

    ema_diff = np.abs(ema2 - ema1)
    in_squeeze = ema_diff < atr

    SqLup = ema2 + atr
    SqLdn = ema2 - atr

    current_in_squeeze = in_squeeze[current_idx]

    if not current_in_squeeze:
        return None, None, 0, 0

    range_high = SqLup[current_idx]
    range_low = SqLdn[current_idx]
    range_pct = ((range_high - range_low) / range_low) * 100 if range_low > 0 else 0

    lookback = min(60, current_idx)
    consol_days = 0
    for i in range(current_idx, max(0, current_idx - lookback), -1):
        if in_squeeze[i]:
            consol_days += 1
        else:
            break

    return range_high, range_low, consol_days, range_pct

def scan_stock(ticker, df):
    """Scan for long cross indications"""
    if len(df) < 70:
        return None

    current_idx = len(df) - 1
    prev_idx = current_idx - 1

    current_date = df.index[current_idx]
    if pd.isna(current_date):
        return None

    current_price = df['Close'].iloc[current_idx]

    # Calculate indicators
    fi_ema, fi_color_list, normalized_price, basis = calculate_efi_tradingview(df, useemaforboll=True)
    fader_signal, fader_color = calculate_fader_signal(df)
    range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

    if range_high is None:
        return None

    # Current and previous values
    current_norm_price = normalized_price.iloc[current_idx]
    prev_norm_price = normalized_price.iloc[prev_idx]

    current_fi_color = fi_color_list[current_idx]
    prev_fi_color = fi_color_list[prev_idx]

    current_fader = fader_color[current_idx]

    # CRITERIA FOR LONG CROSS INDICATION

    # 1. Normalized Price crosses above 0 (from negative to positive)
    norm_price_cross = (prev_norm_price <= 0 and current_norm_price > 0)

    # 2. EFI Histogram changes from bearish to bullish
    # Previous was ORANGE or MAROON, current is LIME or TEAL
    efi_color_change = (prev_fi_color in ['ORANGE', 'MAROON']) and (current_fi_color in ['LIME', 'TEAL'])

    # 3. Channel printing
    channel_printing = consol_days > 0

    # 4. Fader is GREEN
    fader_green = current_fader == 'green'

    # ALL CRITERIA MUST BE MET
    if not (norm_price_cross and efi_color_change and channel_printing and fader_green):
        return None

    # Calculate quality score
    quality_score = 0

    # Points for channel duration (max 25)
    quality_score += min(25, consol_days / 2)

    # Points for strength of norm price cross (max 25)
    quality_score += min(25, current_norm_price * 25)

    # Points for EFI strength (max 25)
    fi_value = fi_ema.iloc[current_idx]
    if fi_value > 0:
        quality_score += min(25, fi_value * 10)

    # Points for tight channel (max 25)
    if range_pct < 5:
        quality_score += 25
    elif range_pct < 10:
        quality_score += 15
    elif range_pct < 15:
        quality_score += 10

    return {
        'ticker': ticker,
        'date': current_date.strftime('%m/%d/%Y'),
        'price': current_price,
        'basis_68ema': basis.iloc[current_idx],
        'norm_price_prev': prev_norm_price,
        'norm_price_current': current_norm_price,
        'fi_color_prev': prev_fi_color,
        'fi_color_current': current_fi_color,
        'fi_value': fi_value,
        'fader_color': current_fader,
        'channel_days': consol_days,
        'range_high': range_high,
        'range_low': range_low,
        'range_pct': range_pct,
        'quality_score': int(quality_score)
    }

def scan_all_stocks():
    """Scan all stocks for long cross indications"""
    print("=" * 100)
    print("LONG CROSS INDICATIONS SCANNER")
    print("=" * 100)
    print(f"Scan started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print("CRITERIA:")
    print("  1. Normalized Price crosses ABOVE 0 (Close crosses above 68 EMA)")
    print("  2. EFI Histogram changes from ORANGE/MAROON to LIME/TEAL (bullish reversal)")
    print("  3. Jimmy Squeeze Channel actively PRINTING")
    print("  4. Fader line is GREEN (bullish momentum)")
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

            signal = scan_stock(ticker, df)

            if signal:
                results.append(signal)

        except Exception as e:
            continue

    print(f"\n{'=' * 100}")
    print(f"Scan complete! Found {len(results)} LONG CROSS INDICATIONS")
    print(f"{'=' * 100}\n")

    if len(results) > 0:
        results.sort(key=lambda x: x['quality_score'], reverse=True)

        print(f"{'Ticker':<8} {'Date':<12} {'Price':>8} {'Prev->Curr':>15} {'EFI Color':>20} {'Ch Days':>8} {'Score':>6}")
        print("-" * 100)

        for r in results:
            norm_change = f"{r['norm_price_prev']:>6.2f}->{r['norm_price_current']:>6.2f}"
            efi_change = f"{r['fi_color_prev']:>8}->{r['fi_color_current']:<8}"
            print(f"{r['ticker']:<8} {r['date']:<12} ${r['price']:>7.2f} {norm_change:>15} {efi_change:>20} "
                  f"{r['channel_days']:>8}d {r['quality_score']:>6}")

        print()
        print("=" * 100)
        print("DETAILED ANALYSIS (First 10 Signals)")
        print("=" * 100)
        print()

        for i, r in enumerate(results[:10], 1):
            print(f"SIGNAL #{i} - {r['ticker']} - Quality Score: {r['quality_score']}/100")
            print("-" * 100)
            print(f"  Date:                     {r['date']}")
            print(f"  Current Price:            ${r['price']:.2f}")
            print(f"  68 EMA (Basis):           ${r['basis_68ema']:.2f}")
            print()
            print(f"  CROSSOVER SIGNALS:")
            print(f"    Norm Price:             {r['norm_price_prev']:.2f} -> {r['norm_price_current']:.2f} (CROSSED ABOVE 0)")
            print(f"    EFI Histogram:          {r['fi_color_prev']} -> {r['fi_color_current']} (BULLISH REVERSAL)")
            print(f"    Fader:                  {r['fader_color'].upper()} (BULLISH MOMENTUM)")
            print()
            print(f"  CHANNEL:")
            print(f"    Days Printing:          {r['channel_days']} days")
            print(f"    Range:                  ${r['range_low']:.2f} - ${r['range_high']:.2f} ({r['range_pct']:.1f}%)")
            print()
            print(f"  => LONG CROSS INDICATION: All bullish signals aligned!")
            print()

    save_report(results)
    return results

def save_report(results):
    """Save results to file"""
    lines = []
    lines.append("=" * 100)
    lines.append("LONG CROSS INDICATIONS SCANNER - RESULTS")
    lines.append("=" * 100)
    lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("CRITERIA:")
    lines.append("  1. Normalized Price crosses ABOVE 0 (Close crosses above 68 EMA)")
    lines.append("  2. EFI Histogram changes from ORANGE/MAROON to LIME/TEAL")
    lines.append("  3. Jimmy Squeeze Channel actively PRINTING")
    lines.append("  4. Fader line is GREEN")
    lines.append("")
    lines.append(f"Total Signals Found: {len(results)}")
    lines.append("=" * 100)
    lines.append("")

    if len(results) > 0:
        lines.append(f"{'Ticker':<8} {'Date':<12} {'Price':>8} {'Norm Cross':>15} {'EFI Change':>20} {'Ch Days':>8} {'Score':>6}")
        lines.append("-" * 100)

        for r in results:
            norm_change = f"{r['norm_price_prev']:>6.2f}->{r['norm_price_current']:>6.2f}"
            efi_change = f"{r['fi_color_prev']:>8}->{r['fi_color_current']:<8}"
            lines.append(f"{r['ticker']:<8} {r['date']:<12} ${r['price']:>7.2f} {norm_change:>15} {efi_change:>20} "
                        f"{r['channel_days']:>8}d {r['quality_score']:>6}")

        lines.append("")
        lines.append("TradingView Ticker List:")
        lines.append(",".join([r['ticker'] for r in results]))

    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

    # Save TradingView list
    tv_lines = []
    tv_lines.append("=" * 100)
    tv_lines.append("LONG CROSS INDICATIONS - TRADINGVIEW LIST")
    tv_lines.append("=" * 100)
    tv_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    tv_lines.append(f"Total Signals: {len(results)}")
    tv_lines.append("")
    tv_lines.append("Copy and paste into TradingView:")
    tv_lines.append("-" * 100)
    if len(results) > 0:
        tv_lines.append(",".join([r['ticker'] for r in results]))

    with open(tradingview_file, 'w') as f:
        f.write('\n'.join(tv_lines))

    print(f"\nReport saved to: {output_file}")
    print(f"TradingView list saved to: {tradingview_file}")

if __name__ == '__main__':
    results = scan_all_stocks()

    if len(results) > 0:
        print(f"\nFound {len(results)} LONG CROSS INDICATIONS!")
        print(f"Top 3 highest quality:")
        for i, sig in enumerate(results[:3], 1):
            print(f"  {i}. {sig['ticker']} - Score: {sig['quality_score']}/100, "
                  f"Norm: {sig['norm_price_prev']:.2f}->{sig['norm_price_current']:.2f}, "
                  f"EFI: {sig['fi_color_prev']}->{sig['fi_color_current']}")
    else:
        print("\nNo long cross indications found on current scan day")
        print("These signals are rare - they catch the exact moment of bullish reversal")
