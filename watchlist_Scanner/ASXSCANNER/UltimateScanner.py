"""
ULTIMATE HIGH PROBABILITY SCANNER
==================================
Combines the best elements from all scanners:
- Dynamic consolidation detection (no fixed timeframes)
- EFI momentum divergence (MAROON/ORANGE oversold)
- Normalized price (position in range)
- Trend confirmation (Fader/SMA)
- Volume analysis

Strategy: Buy dips in uptrends when stock is consolidating and oversold
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os
import talib

# File paths - get script directory and build absolute paths
script_dir = os.path.dirname(os.path.abspath(__file__))

data_folder = os.path.join(script_dir, 'Updated_Results')
output_file = os.path.join(script_dir, 'ultimate_high_probability_signals.txt')
tradingview_file = os.path.join(script_dir, 'tradingview_ultimate_list.txt')

def hma(data, period):
    """Calculate Hull Moving Average (HMA)"""
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))

    wma_half = talib.WMA(data, timeperiod=half_period)
    wma_full = talib.WMA(data, timeperiod=period)

    # 2 * WMA(n/2) - WMA(n)
    raw_hma = 2 * wma_half - wma_full

    # WMA of the result with sqrt(n) period
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

def calculate_normalized_price_tradingview(df, bollperiod=68):
    """
    Calculate normalized price as per TradingView EFI indicator
    normprice = close - basis (68 EMA)
    Positive value = price above basis (strength)
    Negative value = price below basis (weakness)
    """
    basis = talib.EMA(df['Close'].values, timeperiod=bollperiod)
    basis_series = pd.Series(basis, index=df.index)
    normprice = df['Close'] - basis_series
    return normprice

def find_consolidation_range(df, current_idx, ema1_per=5, ema2_per=26, atr_per=50, atr_mult=0.4):
    """
    Jimmy Channel Scan - Squeeze Channel detection
    Channel only exists when abs(EMA2 - EMA1) < ATR (squeeze condition)
    This ensures channel is "printing" on current day
    Returns: (range_high, range_low, consolidation_days, range_percent)
    """
    if current_idx < max(ema1_per, ema2_per, atr_per):
        return None, None, 0, 0

    # Calculate EMAs and ATR
    ema1 = talib.EMA(df['Close'].values, timeperiod=ema1_per)
    ema2 = talib.EMA(df['Close'].values, timeperiod=ema2_per)
    atr = talib.ATR(df['High'].values, df['Low'].values, df['Close'].values, timeperiod=atr_per) * atr_mult

    # Calculate Squeeze Channel Levels
    # Channel only exists when abs(EMA2 - EMA1) < ATR
    ema_diff = np.abs(ema2 - ema1)
    in_squeeze = ema_diff < atr

    # Upper and lower channel boundaries
    SqLup = ema2 + atr  # Upper channel
    SqLdn = ema2 - atr  # Lower channel

    # Check if channel is printing on current bar
    current_in_squeeze = in_squeeze[current_idx]

    if not current_in_squeeze:
        # Channel not printing today - EMAs too far apart
        return None, None, 0, 0

    # Channel is printing - get the boundaries
    range_high = SqLup[current_idx]
    range_low = SqLdn[current_idx]
    range_pct = ((range_high - range_low) / range_low) * 100 if range_low > 0 else 0

    # Count how many recent days the channel has been printing
    lookback = min(60, current_idx)
    consol_days = 0
    for i in range(current_idx, max(0, current_idx - lookback), -1):
        if in_squeeze[i]:
            consol_days += 1
        else:
            break  # Stop counting when channel disappears

    return range_high, range_low, consol_days, range_pct

def check_uptrend(df, current_idx, sma_period=50):
    """Check if stock is in an uptrend"""
    if current_idx < sma_period:
        return False

    sma = df['Close'].rolling(window=sma_period).mean()
    current_price = df['Close'].iloc[current_idx]
    current_sma = sma.iloc[current_idx]
    sma_10_days_ago = sma.iloc[max(0, current_idx - 5)]

    # Uptrend if: price above SMA and SMA is rising
    above_sma = current_price > current_sma
    sma_rising = current_sma > sma_10_days_ago

    return above_sma and sma_rising

def calculate_volume_strength(df, current_idx, lookback=20):
    """Calculate if current volume is above average"""
    if current_idx < lookback:
        return False, 0

    avg_volume = df['Volume'].iloc[max(0, current_idx - lookback):current_idx].mean()
    current_volume = df['Volume'].iloc[current_idx]

    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
    above_average = volume_ratio > 1.0

    return above_average, volume_ratio

def scan_stock(ticker, df):
    """
    Scan a single stock for ultimate high probability setup
    Returns signal dict if all criteria met, None otherwise
    """
    if len(df) < 60:
        return None

    current_idx = len(df) - 1
    current_date = df.index[current_idx]

    # Skip if date is NaT
    if pd.isna(current_date):
        return None

    current_price = df['Close'].iloc[current_idx]

    # 1. Calculate TradingView EFI (includes normalized price and basis)
    fi_ema, fi_color_list, normalized_price, basis = calculate_efi_tradingview(df, useemaforboll=True)
    fi_value = fi_ema.iloc[current_idx]
    fi_color = fi_color_list[current_idx]
    norm_price_value = normalized_price.iloc[current_idx]
    basis_value = basis.iloc[current_idx]

    # 3. Find Dynamic Consolidation
    range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

    if range_high is None:
        return None  # No consolidation found

    # Calculate position in consolidation range
    range_size = range_high - range_low
    if range_size == 0:
        return None

    position_in_range = ((current_price - range_low) / range_size) * 100

    # 4. Calculate Fader Signal
    fader_signal, fader_color = calculate_fader_signal(df)
    current_fader_color = fader_color[current_idx]
    prev_fader_color = fader_color[current_idx - 1] if current_idx > 0 else 'red'

    # 5. Check Volume
    volume_above_avg, volume_ratio = calculate_volume_strength(df, current_idx)

    # ========================================
    # ULTIMATE CRITERIA (ALL MUST BE TRUE)
    # ========================================

    # Criterion 1: In consolidation (any duration)
    criterion_1 = consol_days > 0

    # Criterion 2: EFI oversold (MAROON or ORANGE - below 0)
    criterion_2 = fi_color in ['MAROON', 'ORANGE']

    # Criterion 3: Normalized price > 0 (DIVERGENCE: strength while EFI weak)
    criterion_3 = norm_price_value > 0

    # Criterion 4: Fader can be red or green (no filter on color)
    criterion_4 = True  # Always pass - we want to see setups with any Fader color

    # Check if first 3 criteria are met
    if not (criterion_1 and criterion_2 and criterion_3):
        return None

    # Calculate quality score (0-100)
    quality_score = 0

    # Points for consolidation duration (max 25 points)
    quality_score += min(25, consol_days / 2)

    # Points for how oversold (max 25 points)
    quality_score += min(25, abs(norm_price_value) * 25)

    # Points for EFI strength (max 25 points)
    if fi_color == 'MAROON':
        quality_score += 25
    else:  # ORANGE
        quality_score += 15

    # Points for volume (max 25 points)
    if volume_above_avg:
        quality_score += min(25, (volume_ratio - 1.0) * 50)

    # Return signal with all details
    return {
        'ticker': ticker,
        'date': current_date.strftime('%m/%d/%Y'),
        'price': current_price,
        'consolidation_days': consol_days,
        'range_high': range_high,
        'range_low': range_low,
        'range_pct': range_pct,
        'position_in_range': position_in_range,
        'normalized_price': norm_price_value,
        'force_index': fi_value,
        'fi_color': fi_color,
        'fader_color': current_fader_color,
        'volume_ratio': volume_ratio,
        'quality_score': quality_score
    }

def run_ultimate_scan():
    """Run the ultimate high probability scanner"""
    print("=" * 80)
    print("ULTIMATE HIGH PROBABILITY SCANNER")
    print("=" * 80)
    print(f"Scan started: {datetime.now()}")
    print("\nLoading stock data from individual CSV files...")

    # Get all CSV files in the results folder
    csv_files = [f for f in os.listdir(data_folder) if f.endswith('.csv')]

    print(f"Found {len(csv_files)} stock files to scan...\n")

    signals = []

    for i, csv_file in enumerate(csv_files):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(csv_files)} stocks scanned...")

        ticker = csv_file.replace('.csv', '')
        file_path = os.path.join(data_folder, csv_file)

        try:
            # Load ticker data - skip rows 1 and 2 (ticker names and "Date" row)
            df = pd.read_csv(file_path, skiprows=[1, 2])

            # Rename 'Price' column to 'Date' if it exists
            if 'Price' in df.columns:
                df.rename(columns={'Price': 'Date'}, inplace=True)

            # Ensure required columns exist
            required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in df.columns for col in required_cols):
                continue

            # Prepare data
            df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')

            # Drop rows with invalid dates FIRST
            df = df.dropna(subset=['Date'])

            df = df.sort_values('Date')
            df.set_index('Date', inplace=True)

            # Convert columns to numeric (in case they were read as strings)
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Drop any rows with NaN values in price/volume columns
            df = df.dropna()

            # Scan this stock
            signal = scan_stock(ticker, df)

            if signal:
                signals.append(signal)

        except Exception as e:
            # Print first error for debugging
            if len(signals) == 0 and i < 10:
                print(f"Error processing {ticker}: {e}")
            continue

    print(f"\nScan complete! Found {len(signals)} high probability setups.\n")

    # Sort signals by quality score (best first)
    signals.sort(key=lambda x: x['quality_score'], reverse=True)

    # Generate report
    generate_report(signals)
    create_tradingview_list(signals)

    return signals

def generate_report(signals):
    """Generate detailed report of signals"""
    report_lines = []

    report_lines.append("=" * 80)
    report_lines.append("ULTIMATE HIGH PROBABILITY SCANNER - RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("STRATEGY CRITERIA:")
    report_lines.append("  1. Jimmy Squeeze Channel PRINTING on scan day (EMA5/26 within ATR distance)")
    report_lines.append("  2. EFI oversold (MAROON or ORANGE - histogram below 0)")
    report_lines.append("  3. Normalized price > 0 (Close above 68 EMA - DIVERGENCE setup)")
    report_lines.append("  (Fader color shown for reference - RED or GREEN both accepted)")
    report_lines.append("")
    report_lines.append("QUALITY SCORE:")
    report_lines.append("  Based on consolidation duration, oversold level, EFI strength, volume")
    report_lines.append("  Higher score = higher probability setup")
    report_lines.append("")
    report_lines.append(f"Total High Probability Setups Found: {len(signals)}")
    report_lines.append("=" * 80)
    report_lines.append("")

    if signals:
        report_lines.append("TOP HIGH PROBABILITY SETUPS (sorted by quality score):")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Score':<7} {'Days':<6} {'Range':<8} {'Pos%':<6} {'Norm':<7} {'EFI':<8} {'Fader':<7} {'Vol':<5}")
        report_lines.append("-" * 90)

        for signal in signals:
            ticker = signal['ticker']
            score = f"{signal['quality_score']:.0f}"
            days = f"{signal['consolidation_days']}"
            range_pct = f"{signal['range_pct']:.1f}%"
            pos = f"{signal['position_in_range']:.0f}%"
            norm = f"{signal['normalized_price']:.2f}"
            fi_color = signal['fi_color'].upper()[:6]
            fader = signal['fader_color'].upper()[:5]
            vol = f"{signal['volume_ratio']:.1f}x"

            report_lines.append(f"{ticker:<8} {score:<7} {days:<6} {range_pct:<8} {pos:<6} {norm:<7} {fi_color:<8} {fader:<7} {vol:<5}")

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("DETAILED SIGNALS:")
        report_lines.append("=" * 80)

        for i, signal in enumerate(signals, 1):
            report_lines.append("")
            report_lines.append(f"SIGNAL #{i} - {signal['ticker']} - Quality Score: {signal['quality_score']:.0f}/100")
            report_lines.append("-" * 80)
            report_lines.append(f"  Date:                {signal['date']}")
            report_lines.append(f"  Current Price:       ${signal['price']:.2f}")
            report_lines.append(f"  Consolidation:       {signal['consolidation_days']} days")
            report_lines.append(f"  Range:               ${signal['range_low']:.2f} - ${signal['range_high']:.2f} ({signal['range_pct']:.1f}%)")
            report_lines.append(f"  Position in Range:   {signal['position_in_range']:.0f}% (lower third = buy zone)")
            report_lines.append(f"  Normalized Price:    {signal['normalized_price']:.2f} (DIVERGENCE)")
            report_lines.append(f"  Force Index:         {signal['force_index']:.2f} ({signal['fi_color'].upper()})")
            report_lines.append(f"  Fader Signal:        {signal['fader_color'].upper()}")
            report_lines.append(f"  Volume:              {signal['volume_ratio']:.1f}x average")
            report_lines.append("")
            report_lines.append(f"  SETUP: {signal['ticker']} consolidating for {signal['consolidation_days']} days,")
            report_lines.append(f"         DIVERGENCE: EFI oversold ({signal['fi_color'].upper()}) but norm price > 0,")
            report_lines.append(f"         Fader {signal['fader_color'].upper()} confirming bullish momentum.")
            report_lines.append(f"         Quality score: {signal['quality_score']:.0f}/100")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Print to console
    try:
        print(report_text)
    except UnicodeEncodeError:
        print(report_text.encode('ascii', errors='replace').decode('ascii'))

    print(f"\nReport saved to: {output_file}")
    print(f"TradingView list saved to: {tradingview_file}")

def create_tradingview_list(signals):
    """Create TradingView format watchlist"""
    if not signals:
        return

    tickers_list = [signal['ticker'] for signal in signals]

    lines = []
    lines.append("=" * 80)
    lines.append("ULTIMATE HIGH PROBABILITY SCANNER - TRADINGVIEW WATCHLIST")
    lines.append("=" * 80)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total symbols: {len(tickers_list)}")
    lines.append("")
    lines.append("Copy the comma-separated line below into TradingView:")
    lines.append("-" * 80)
    lines.append(','.join(tickers_list))
    lines.append("")

    with open(tradingview_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

if __name__ == "__main__":
    signals = run_ultimate_scan()

    if signals:
        print(f"\nFound {len(signals)} high probability setups!")
        print(f"Top 3 highest quality scores:")
        for i, signal in enumerate(signals[:3], 1):
            print(f"   {i}. {signal['ticker']} - Score: {signal['quality_score']:.0f}/100")
    else:
        print("\nNo setups found matching all criteria.")