"""
LOW PRICE CHANNEL SCANNER
=========================
Scans for low-priced stocks ($1-$5) with Jimmy Squeeze Channel printing

CRITERIA:
1. Stock price between $1.00 and $5.00
2. Jimmy Squeeze Channel actively PRINTING today
3. Channel must be stable (at least 3 days)

This finds consolidating low-priced stocks ready for potential moves
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
output_file = os.path.join(script_dir, 'low_price_channel_signals.txt')
tradingview_file = os.path.join(script_dir, 'tradingview_low_price_channel_list.txt')

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
    """Scan for low-priced stocks with channel printing"""
    if len(df) < 70:
        return None

    current_idx = len(df) - 1
    current_date = df.index[current_idx]

    if pd.isna(current_date):
        return None

    current_price = df['Close'].iloc[current_idx]

    # CRITERIA 1: Price between $1 and $5
    if current_price < 1.0 or current_price > 5.0:
        return None

    # CRITERIA 2: Channel printing today
    range_high, range_low, consol_days, range_pct = find_consolidation_range(df, current_idx)

    if range_high is None:
        return None

    # CRITERIA 3: Channel stable (at least 3 days)
    if consol_days < 3:
        return None

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
    position_pct = ((current_price - range_low) / (range_high - range_low)) * 100 if range_high != range_low else 50
    if position_pct < 30:  # Lower third
        quality_score += 20
    elif position_pct < 50:  # Middle lower
        quality_score += 15
    elif position_pct < 70:  # Middle upper
        quality_score += 10

    # Points for channel strength (max 20)
    if consol_days >= 10:
        quality_score += 20
    elif consol_days >= 5:
        quality_score += 15
    elif consol_days >= 3:
        quality_score += 10

    return {
        'ticker': ticker,
        'date': current_date.strftime('%m/%d/%Y'),
        'price': current_price,
        'channel_high': range_high,
        'channel_low': range_low,
        'channel_days': consol_days,
        'range_pct': range_pct,
        'position_in_channel': position_pct,
        'quality_score': int(quality_score)
    }

def scan_all_stocks():
    """Scan all stocks for low-priced channel setups"""
    print("=" * 100)
    print("LOW PRICE CHANNEL SCANNER")
    print("=" * 100)
    print(f"Scan started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print("CRITERIA:")
    print("  1. Stock price between $1.00 and $5.00")
    print("  2. Jimmy Squeeze Channel actively PRINTING today")
    print("  3. Channel stable for at least 3 days")
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
    print(f"Scan complete! Found {len(results)} LOW PRICE CHANNEL SETUPS")
    print(f"{'=' * 100}\n")

    if len(results) > 0:
        results.sort(key=lambda x: x['quality_score'], reverse=True)

        print(f"{'Ticker':<8} {'Date':<12} {'Price':>8} {'Ch Days':>8} {'Range%':>7} {'Pos%':>6} {'Score':>6}")
        print("-" * 100)

        for r in results:
            print(f"{r['ticker']:<8} {r['date']:<12} ${r['price']:>7.2f} "
                  f"{r['channel_days']:>8}d {r['range_pct']:>6.1f}% {r['position_in_channel']:>5.0f}% {r['quality_score']:>6}")

        print()
        print("=" * 100)
        print("DETAILED ANALYSIS (First 20 Signals)")
        print("=" * 100)
        print()

        for i, r in enumerate(results[:20], 1):
            print(f"SIGNAL #{i} - {r['ticker']} - Quality Score: {r['quality_score']}/100")
            print("-" * 100)
            print(f"  Date:                     {r['date']}")
            print(f"  Current Price:            ${r['price']:.2f}")
            print()
            print(f"  CHANNEL:")
            print(f"    Days Printing:          {r['channel_days']} days")
            print(f"    Range:                  ${r['channel_low']:.2f} - ${r['channel_high']:.2f} ({r['range_pct']:.1f}%)")
            print(f"    Position in Channel:    {r['position_in_channel']:.0f}%")
            print()
            print(f"  => Low-priced stock consolidating in squeeze channel!")
            print()

    save_report(results)
    return results

def save_report(results):
    """Save results to file"""
    lines = []
    lines.append("=" * 100)
    lines.append("LOW PRICE CHANNEL SCANNER - RESULTS")
    lines.append("=" * 100)
    lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("CRITERIA:")
    lines.append("  1. Stock price between $1.00 and $5.00")
    lines.append("  2. Jimmy Squeeze Channel actively PRINTING today")
    lines.append("  3. Channel stable for at least 3 days")
    lines.append("")
    lines.append(f"Total Signals Found: {len(results)}")
    lines.append("=" * 100)
    lines.append("")

    if len(results) > 0:
        lines.append(f"{'Ticker':<8} {'Date':<12} {'Price':>8} {'Ch Days':>8} {'Range%':>7} {'Pos%':>6} {'Score':>6}")
        lines.append("-" * 100)

        for r in results:
            lines.append(f"{r['ticker']:<8} {r['date']:<12} ${r['price']:>7.2f} "
                        f"{r['channel_days']:>8}d {r['range_pct']:>6.1f}% {r['position_in_channel']:>5.0f}% {r['quality_score']:>6}")

        lines.append("")
        lines.append("TradingView Ticker List:")
        lines.append(",".join([r['ticker'] for r in results]))

    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

    # Save TradingView list
    tv_lines = []
    tv_lines.append("=" * 100)
    tv_lines.append("LOW PRICE CHANNEL SETUPS - TRADINGVIEW LIST")
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
        print(f"\nFound {len(results)} LOW PRICE CHANNEL SETUPS!")
        print(f"Top 5 highest quality:")
        for i, sig in enumerate(results[:5], 1):
            print(f"  {i}. {sig['ticker']} - ${sig['price']:.2f}, Score: {sig['quality_score']}/100, "
                  f"Channel: {sig['channel_days']}d, Range: {sig['range_pct']:.1f}%")
    else:
        print("\nNo low-priced channel setups found on current scan")
        print("Looking for: $1-$5 stocks with channel printing")
