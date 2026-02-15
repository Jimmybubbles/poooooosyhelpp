"""
FADER CHANNEL SCANNER
=====================
Scans for Fader momentum shifts inside channels:
1. Jimmy Squeeze Channel actively PRINTING
2. Fader changes from RED to GREEN
3. Fader stays GREEN for at least 2 consecutive days
4. All signals occur INSIDE the channel

This catches early momentum shifts within consolidation
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
output_file = os.path.join(script_dir, 'fader_channel_signals.txt')
tradingview_file = os.path.join(script_dir, 'tradingview_fader_channel_list.txt')

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
    """Scan for Fader color change from red to green inside channel"""
    if len(df) < 70:
        return None

    current_idx = len(df) - 1
    current_date = df.index[current_idx]

    if pd.isna(current_date):
        return None

    current_price = df['Close'].iloc[current_idx]

    # Calculate Fader
    fader_signal, fader_color = calculate_fader_signal(df)

    # Calculate channel for current day
    range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

    if range_high is None:
        return None

    # CRITERIA FOR FADER CHANNEL SIGNAL

    # 1. Current day: Fader is GREEN
    current_fader = fader_color[current_idx]
    if current_fader != 'green':
        return None

    # 2. Yesterday: Fader is GREEN (2nd day of green)
    day1_fader = fader_color[current_idx - 1]
    if day1_fader != 'green':
        return None

    # 3. Day before yesterday: Fader was RED (the change happened)
    day2_fader = fader_color[current_idx - 2]
    if day2_fader != 'red':
        return None

    # 4. All 3 days must be inside the channel
    # Check if prices stayed within channel boundaries for the last 3 days
    for i in range(current_idx - 2, current_idx + 1):
        # Get channel for that day
        ch_high, ch_low, _, _ = find_consolidation_range(df, i)

        if ch_high is None:
            return None  # Channel wasn't printing one of those days

        # Check if price was inside channel
        day_close = df['Close'].iloc[i]
        if day_close < ch_low or day_close > ch_high:
            return None  # Price outside channel

    # Calculate quality score
    quality_score = 0

    # Points for channel duration (max 30)
    quality_score += min(30, consol_days)

    # Points for tight channel (max 30)
    if range_pct < 2:
        quality_score += 30
    elif range_pct < 5:
        quality_score += 20
    elif range_pct < 10:
        quality_score += 10

    # Points for position in channel (max 20)
    # Prefer if near bottom of channel (more upside)
    position_pct = ((current_price - range_low) / (range_high - range_low)) * 100 if range_high != range_low else 50
    if position_pct < 30:  # Lower third
        quality_score += 20
    elif position_pct < 50:  # Middle lower
        quality_score += 15
    elif position_pct < 70:  # Middle upper
        quality_score += 10

    # Points for strength of channel (max 20)
    # More days = stronger
    if consol_days >= 10:
        quality_score += 20
    elif consol_days >= 5:
        quality_score += 15
    elif consol_days >= 3:
        quality_score += 10

    # Get the day the change happened
    change_date = df.index[current_idx - 2]

    return {
        'ticker': ticker,
        'date': current_date.strftime('%m/%d/%Y'),
        'change_date': change_date.strftime('%m/%d/%Y'),
        'price': current_price,
        'channel_high': range_high,
        'channel_low': range_low,
        'channel_days': consol_days,
        'range_pct': range_pct,
        'position_in_channel': position_pct,
        'fader_day2': day2_fader,
        'fader_day1': day1_fader,
        'fader_current': current_fader,
        'quality_score': int(quality_score)
    }

def scan_all_stocks():
    """Scan all stocks for Fader channel signals"""
    print("=" * 100)
    print("FADER CHANNEL SCANNER")
    print("=" * 100)
    print(f"Scan started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print("CRITERIA:")
    print("  1. Jimmy Squeeze Channel actively PRINTING")
    print("  2. Fader changes from RED to GREEN")
    print("  3. Fader stays GREEN for 2 consecutive days")
    print("  4. All price action INSIDE the channel")
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
    print(f"Scan complete! Found {len(results)} FADER CHANNEL SIGNALS")
    print(f"{'=' * 100}\n")

    if len(results) > 0:
        results.sort(key=lambda x: x['quality_score'], reverse=True)

        print(f"{'Ticker':<8} {'Current':<12} {'Change On':<12} {'Price':>8} {'Ch Days':>8} {'Range%':>7} {'Pos%':>6} {'Score':>6}")
        print("-" * 100)

        for r in results:
            print(f"{r['ticker']:<8} {r['date']:<12} {r['change_date']:<12} ${r['price']:>7.2f} "
                  f"{r['channel_days']:>8}d {r['range_pct']:>6.1f}% {r['position_in_channel']:>5.0f}% {r['quality_score']:>6}")

        print()
        print("=" * 100)
        print("DETAILED ANALYSIS (First 10 Signals)")
        print("=" * 100)
        print()

        for i, r in enumerate(results[:10], 1):
            print(f"SIGNAL #{i} - {r['ticker']} - Quality Score: {r['quality_score']}/100")
            print("-" * 100)
            print(f"  Current Date:             {r['date']}")
            print(f"  Fader Change Date:        {r['change_date']}")
            print(f"  Current Price:            ${r['price']:.2f}")
            print()
            print(f"  FADER SIGNAL:")
            print(f"    2 Days Ago:             {r['fader_day2'].upper()} (RED)")
            print(f"    Yesterday:              {r['fader_day1'].upper()} (GREEN - Day 1)")
            print(f"    Today:                  {r['fader_current'].upper()} (GREEN - Day 2)")
            print()
            print(f"  CHANNEL:")
            print(f"    Days Printing:          {r['channel_days']} days")
            print(f"    Range:                  ${r['channel_low']:.2f} - ${r['channel_high']:.2f} ({r['range_pct']:.1f}%)")
            print(f"    Position in Channel:    {r['position_in_channel']:.0f}%")
            print()
            print(f"  => FADER shifted to GREEN inside channel with 2 days confirmation!")
            print()

    save_report(results)
    return results

def save_report(results):
    """Save results to file"""
    lines = []
    lines.append("=" * 100)
    lines.append("FADER CHANNEL SCANNER - RESULTS")
    lines.append("=" * 100)
    lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("CRITERIA:")
    lines.append("  1. Jimmy Squeeze Channel actively PRINTING")
    lines.append("  2. Fader changes from RED to GREEN")
    lines.append("  3. Fader stays GREEN for 2 consecutive days")
    lines.append("  4. All price action INSIDE the channel")
    lines.append("")
    lines.append(f"Total Signals Found: {len(results)}")
    lines.append("=" * 100)
    lines.append("")

    if len(results) > 0:
        lines.append(f"{'Ticker':<8} {'Current':<12} {'Change On':<12} {'Price':>8} {'Ch Days':>8} {'Range%':>7} {'Pos%':>6} {'Score':>6}")
        lines.append("-" * 100)

        for r in results:
            lines.append(f"{r['ticker']:<8} {r['date']:<12} {r['change_date']:<12} ${r['price']:>7.2f} "
                        f"{r['channel_days']:>8}d {r['range_pct']:>6.1f}% {r['position_in_channel']:>5.0f}% {r['quality_score']:>6}")

        lines.append("")
        lines.append("TradingView Ticker List:")
        lines.append(",".join([r['ticker'] for r in results]))

    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

    # Save TradingView list
    tv_lines = []
    tv_lines.append("=" * 100)
    tv_lines.append("FADER CHANNEL SIGNALS - TRADINGVIEW LIST")
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
        print(f"\nFound {len(results)} FADER CHANNEL SIGNALS!")
        print(f"Top 3 highest quality:")
        for i, sig in enumerate(results[:3], 1):
            print(f"  {i}. {sig['ticker']} - Score: {sig['quality_score']}/100, "
                  f"Channel: {sig['channel_days']}d, Change: {sig['change_date']}")
    else:
        print("\nNo Fader channel signals found on current scan")
        print("Looking for: RED->GREEN->GREEN inside channel")
