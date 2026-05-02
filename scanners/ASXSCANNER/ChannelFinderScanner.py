"""
CHANNEL FINDER SCANNER
======================
Checks 2 timeframes (Weekly, Daily) for EMA squeeze channels.
Stocks with BOTH timeframes in a channel = strongest consolidation signal.

Channel Detection Method (EMA Squeeze):
  EMA Fast (5) vs EMA Slow (26)
  Channel exists when abs(EMA_fast - EMA_slow) < ATR(50) * 0.4
  At least 5 of last 10 bars must be in channel

Scoring:
  2/2 = BOTH (daily + weekly channel alignment)
  1/2 = reported but weaker (only one timeframe)

NOTE: Monthly/3-Month channels need 5+ years of daily data to compute properly.
      With current ~14 months of data, check higher TFs visually on TradingView.
      Suggested TradingView params for higher timeframes:
        Monthly:  EMA(3) vs EMA(13), ATR(14) * 0.5
        3-Month:  EMA(3) vs EMA(10), ATR(8)  * 0.6
"""

import pandas as pd
import numpy as np
import os
import talib
from datetime import datetime

# Configuration
script_dir = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(script_dir, 'Updated_Results')
OUTPUT_DIR = os.path.join(script_dir, 'buylist')

# Channel parameters (from JimmyChannelScan)
CHANNEL_EMA_FAST = 5
CHANNEL_EMA_SLOW = 26
CHANNEL_ATR_PERIOD = 50
CHANNEL_ATR_MULT = 0.4
CHANNEL_BARS_NEEDED = 5
CHANNEL_LOOKBACK = 10

MIN_DATA_ROWS = 100

TIMEFRAMES = ['Weekly', 'Daily']

RESAMPLE_AGG = {
    'Open': 'first',
    'High': 'max',
    'Low': 'min',
    'Close': 'last',
    'Volume': 'sum',
}


def detect_channel(df):
    """
    Detect squeeze channel consolidation using EMA convergence.
    Returns True if currently in a channel (at least 5 of last 10 bars).
    """
    if len(df) < CHANNEL_ATR_PERIOD + CHANNEL_LOOKBACK:
        return False

    try:
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)

        ema_fast = talib.EMA(close, timeperiod=CHANNEL_EMA_FAST)
        ema_slow = talib.EMA(close, timeperiod=CHANNEL_EMA_SLOW)
        atr = talib.ATR(high, low, close, timeperiod=CHANNEL_ATR_PERIOD) * CHANNEL_ATR_MULT

        in_channel = np.abs(ema_fast - ema_slow) < atr

        recent = in_channel[-CHANNEL_LOOKBACK:]
        bars_in_channel = np.sum(recent[~np.isnan(recent)])

        return bars_in_channel >= CHANNEL_BARS_NEEDED
    except Exception:
        return False


def scan_stock(ticker):
    """
    Scan a single stock on Weekly and Daily for channel patterns.
    Returns result dict or None.
    """
    csv_file = os.path.join(CSV_DIR, f"{ticker}.csv")

    if not os.path.exists(csv_file):
        return None

    try:
        df = pd.read_csv(csv_file, skiprows=[1, 2])

        if 'Price' in df.columns:
            df.rename(columns={'Price': 'Date'}, inplace=True)

        required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_cols):
            return None

        df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
        df = df.dropna(subset=['Date'])
        df = df.sort_values('Date')
        df.set_index('Date', inplace=True)

        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna()

        if len(df) < MIN_DATA_ROWS:
            return None

        current_price = df['Close'].iloc[-1]
        if current_price <= 0:
            return None

        # Daily channel
        daily_channel = detect_channel(df)

        # Weekly channel
        weekly_df = df.resample('W').agg(RESAMPLE_AGG).dropna()
        weekly_channel = detect_channel(weekly_df) if len(weekly_df) >= 60 else False

        score = sum([daily_channel, weekly_channel])

        if score < 1:
            return None

        label = 'BOTH' if score == 2 else 'SINGLE'

        return {
            'ticker': ticker,
            'price': current_price,
            'score': score,
            'label': label,
            'daily': daily_channel,
            'weekly': weekly_channel,
        }

    except Exception:
        return None


def build_report(results):
    """Build the text report from scan results."""
    lines = []
    lines.append("=" * 100)
    lines.append("CHANNEL FINDER SCANNER - RESULTS")
    lines.append("=" * 100)
    lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("METHOD: EMA Squeeze - EMA(5) vs EMA(26) within ATR(50) * 0.4")
    lines.append("TIMEFRAMES: Weekly | Daily")
    lines.append("SCORING: 2/2 = BOTH timeframes in channel | 1/2 = single timeframe")
    lines.append("")

    both = [r for r in results if r['score'] == 2]
    single = [r for r in results if r['score'] == 1]

    lines.append(f"Total Setups:  {len(results)}")
    lines.append(f"  BOTH (2/2):   {len(both)}")
    lines.append(f"  SINGLE (1/2): {len(single)}")
    lines.append("")
    lines.append("=" * 100)

    def yn(val):
        return "YES" if val else " - "

    header = f"{'Ticker':<8} {'Price':>10}   {'Score':<8} {'Week':<8} {'Day':<8}"
    separator = "-" * 80

    if both:
        lines.append("")
        lines.append("[BOTH] WEEKLY + DAILY CHANNEL:")
        lines.append(separator)
        lines.append(header)
        lines.append(separator)
        for r in both:
            lines.append(
                f"{r['ticker']:<8} ${r['price']:>9.2f}   {r['score']}/2      "
                f"{yn(r['weekly']):<8} {yn(r['daily']):<8}"
            )
        lines.append("")

    if single:
        lines.append("")
        lines.append("[SINGLE] ONE TIMEFRAME IN CHANNEL:")
        lines.append(separator)
        lines.append(header)
        lines.append(separator)
        for r in single:
            lines.append(
                f"{r['ticker']:<8} ${r['price']:>9.2f}   {r['score']}/2      "
                f"{yn(r['weekly']):<8} {yn(r['daily']):<8}"
            )
        lines.append("")

    lines.append("=" * 100)
    return '\n'.join(lines)


def main():
    print("=" * 100)
    print("CHANNEL FINDER SCANNER")
    print("=" * 100)
    print(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("Checking 2 timeframes: Weekly | Daily")
    print("Channel: EMA(5) vs EMA(26) squeeze within ATR(50) * 0.4")
    print()
    print("=" * 100)
    print()

    csv_files = [f for f in os.listdir(CSV_DIR) if f.endswith('.csv')]
    tickers = [f[:-4] for f in csv_files]

    print(f"Scanning {len(tickers)} stocks...")
    print()

    results = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 500 == 0:
            print(f"  Progress: {i + 1}/{len(tickers)}...")

        result = scan_stock(ticker)
        if result:
            results.append(result)

    # Sort by score descending, then ticker alphabetically
    results.sort(key=lambda x: (-x['score'], x['ticker']))

    print()
    print(f"Found {len(results)} stocks with channel on 1+ timeframes")
    print()

    if not results:
        print("No setups found.")
        return

    # Build and print report
    report = build_report(results)
    print(report)

    # Save report
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    report_file = os.path.join(OUTPUT_DIR, 'channel_finder_results.txt')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)

    # Save TradingView lists
    tv_file = os.path.join(OUTPUT_DIR, 'tradingview_channel_finder.txt')
    both = [r['ticker'] for r in results if r['score'] == 2]
    all_tickers = [r['ticker'] for r in results]

    with open(tv_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("CHANNEL FINDER - WEEKLY + DAILY\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total: {len(results)} setups\n")
        f.write("=" * 80 + "\n\n")

        if both:
            f.write(f"BOTH (2/2) - {len(both)} stocks:\n")
            f.write(",".join(both) + "\n\n")

        f.write(f"ALL (1/2+) - {len(all_tickers)} stocks:\n")
        f.write(",".join(all_tickers) + "\n")

    print()
    print(f"Report saved: {report_file}")
    print(f"TradingView list: {tv_file}")


if __name__ == "__main__":
    main()
