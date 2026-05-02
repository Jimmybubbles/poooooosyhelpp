import pandas as pd
import numpy as np
import os
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'monthly_channel_scan_results.txt')
tradingview_file = os.path.join(buylist_dir, 'tradingview_monthly_channel_list.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def resample_to_monthly(df):
    """Resample daily data to monthly"""
    monthly = df.resample('ME').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    })
    return monthly.dropna()

def detect_monthly_channel(ticker_symbol, results_dir, lookback_months=6):
    """
    Detect if a stock is trading in a channel on the MONTHLY timeframe

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files
        lookback_months: Number of months to analyze for channel (default 6)

    Returns:
        Dictionary with channel info or None
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker_symbol}.csv")

        if not os.path.exists(csv_file):
            return None

        # Read CSV
        with open(csv_file, 'r') as f:
            first_line = f.readline().strip()

        has_header = 'Ticker' in first_line or 'Date' in first_line or 'Open' in first_line

        if has_header:
            df = pd.read_csv(csv_file, header=0, index_col=0)
        else:
            df = pd.read_csv(csv_file, header=None, index_col=0)
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

        df.index = pd.to_datetime(df.index, errors='coerce', utc=True)
        df = df[df.index.notna()]

        # Need at least 12 months of data (1 year)
        if len(df) < 252:  # ~252 trading days in a year
            return None

        # Resample to monthly
        monthly_df = resample_to_monthly(df)

        if len(monthly_df) < 12:
            return None

        # Get the last N months for analysis
        analysis_months = monthly_df.tail(lookback_months)

        if len(analysis_months) < lookback_months:
            return None

        # Calculate channel boundaries
        channel_high = analysis_months['High'].max()
        channel_low = analysis_months['Low'].min()
        channel_range = channel_high - channel_low
        channel_midpoint = (channel_high + channel_low) / 2

        # Get current price (most recent close)
        current_price = monthly_df['Close'].iloc[-1]
        current_date = monthly_df.index[-1]

        # Calculate where current price is in the channel (0% = bottom, 100% = top)
        price_position_pct = ((current_price - channel_low) / channel_range) * 100 if channel_range > 0 else 50

        # Determine if it's a valid channel
        # Channel characteristics:
        # 1. Range should be significant (at least 10% of midpoint)
        # 2. Price should be within the channel
        # 3. Should have touched both top and bottom multiple times

        channel_range_pct = (channel_range / channel_midpoint) * 100

        # Check if price is within channel
        in_channel = channel_low <= current_price <= channel_high

        # Count touches at top and bottom (within 5% of boundaries)
        top_threshold = channel_high * 0.95
        bottom_threshold = channel_low * 1.05

        top_touches = sum(1 for high in analysis_months['High'] if high >= top_threshold)
        bottom_touches = sum(1 for low in analysis_months['Low'] if low <= bottom_threshold)

        # Valid channel: at least 2 touches on each side
        is_valid_channel = (
            top_touches >= 2 and
            bottom_touches >= 2 and
            channel_range_pct >= 10 and
            in_channel
        )

        if not is_valid_channel:
            return None

        # Determine channel zone (Bottom, Middle, Top)
        if price_position_pct <= 33:
            zone = 'Bottom Third'
        elif price_position_pct <= 66:
            zone = 'Middle Third'
        else:
            zone = 'Top Third'

        # Calculate monthly volatility
        monthly_returns = monthly_df['Close'].pct_change().tail(12)
        volatility = monthly_returns.std() * 100

        return {
            'ticker': ticker_symbol,
            'current_date': current_date,
            'current_price': current_price,
            'channel_high': channel_high,
            'channel_low': channel_low,
            'channel_range': channel_range,
            'channel_range_pct': channel_range_pct,
            'price_position_pct': price_position_pct,
            'zone': zone,
            'top_touches': top_touches,
            'bottom_touches': bottom_touches,
            'lookback_months': lookback_months,
            'volatility': volatility
        }

    except Exception as e:
        print(f"Error scanning {ticker_symbol}: {e}")
        return None

def run_monthly_channel_scan(lookback_months=6):
    """
    Run the monthly channel scan

    Args:
        lookback_months: Number of months to analyze (default 6)
    """
    print("=" * 80)
    print("MONTHLY CHANNEL SCANNER")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("SCANNING FOR:")
    print(f"  - Stocks trading in a defined channel on MONTHLY timeframe")
    print(f"  - Lookback period: {lookback_months} months")
    print(f"  - Minimum 2 touches at top and bottom")
    print(f"  - Channel range at least 10% of price")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Scanning {len(tickers)} tickers for monthly channels...")
    print()

    # Scan all tickers
    channels = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers scanned...")

        result = detect_monthly_channel(ticker, results_dir, lookback_months)

        if result:
            channels.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(channels)} stocks trading in monthly channels")
    print()

    if not channels:
        print("No monthly channels found.")
        return

    # Sort by position in channel (lowest to highest - bottom to top)
    channels.sort(key=lambda x: x['price_position_pct'])

    # Separate by zone
    bottom_third = [c for c in channels if c['zone'] == 'Bottom Third']
    middle_third = [c for c in channels if c['zone'] == 'Middle Third']
    top_third = [c for c in channels if c['zone'] == 'Top Third']

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("MONTHLY CHANNEL SCANNER RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append(f"Lookback Period: {lookback_months} months")
    report_lines.append(f"Total Channels Found: {len(channels)}")
    report_lines.append("")
    report_lines.append("ZONE BREAKDOWN:")
    report_lines.append(f"  Bottom Third (0-33%):  {len(bottom_third)} stocks - POTENTIAL BUY ZONE")
    report_lines.append(f"  Middle Third (33-66%): {len(middle_third)} stocks")
    report_lines.append(f"  Top Third (66-100%):   {len(top_third)} stocks - POTENTIAL SELL ZONE")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Bottom Third - Best buy opportunities
    if bottom_third:
        report_lines.append("BOTTOM THIRD - POTENTIAL BUY OPPORTUNITIES:")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'Channel Low':<12} {'Channel High':<12} {'Position':<10} {'Range%':<8}")
        report_lines.append("-" * 80)

        for channel in bottom_third:
            report_lines.append(
                f"{channel['ticker']:<8} "
                f"${channel['current_price']:<9.2f} "
                f"${channel['channel_low']:<11.2f} "
                f"${channel['channel_high']:<11.2f} "
                f"{channel['price_position_pct']:>8.1f}% "
                f"{channel['channel_range_pct']:>7.1f}%"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # Middle Third
    if middle_third:
        report_lines.append("MIDDLE THIRD - NEUTRAL ZONE:")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'Channel Low':<12} {'Channel High':<12} {'Position':<10} {'Range%':<8}")
        report_lines.append("-" * 80)

        for channel in middle_third:
            report_lines.append(
                f"{channel['ticker']:<8} "
                f"${channel['current_price']:<9.2f} "
                f"${channel['channel_low']:<11.2f} "
                f"${channel['channel_high']:<11.2f} "
                f"{channel['price_position_pct']:>8.1f}% "
                f"{channel['channel_range_pct']:>7.1f}%"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # Top Third - Potential sell/short opportunities
    if top_third:
        report_lines.append("TOP THIRD - POTENTIAL SELL/RESISTANCE ZONE:")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'Channel Low':<12} {'Channel High':<12} {'Position':<10} {'Range%':<8}")
        report_lines.append("-" * 80)

        for channel in top_third:
            report_lines.append(
                f"{channel['ticker']:<8} "
                f"${channel['current_price']:<9.2f} "
                f"${channel['channel_low']:<11.2f} "
                f"${channel['channel_high']:<11.2f} "
                f"{channel['price_position_pct']:>8.1f}% "
                f"{channel['channel_range_pct']:>7.1f}%"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # Detailed channel information
    report_lines.append("DETAILED CHANNEL ANALYSIS:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Zone':<14} {'Top Touches':<12} {'Bottom Touches':<15} {'Volatility%':<12}")
    report_lines.append("-" * 80)

    for channel in channels:
        report_lines.append(
            f"{channel['ticker']:<8} "
            f"{channel['zone']:<14} "
            f"{channel['top_touches']:<12} "
            f"{channel['bottom_touches']:<15} "
            f"{channel['volatility']:>10.2f}%"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("LEGEND:")
    report_lines.append("  Position: Where current price is in the channel (0% = bottom, 100% = top)")
    report_lines.append("  Range%: Channel range as percentage of price")
    report_lines.append("  Top/Bottom Touches: Number of times price touched channel boundaries")
    report_lines.append("  Volatility: Monthly price volatility (standard deviation)")
    report_lines.append("")
    report_lines.append("TRADING STRATEGY:")
    report_lines.append("  - Bottom Third: Consider BUYING (support area)")
    report_lines.append("  - Middle Third: WAIT for better entry (neutral zone)")
    report_lines.append("  - Top Third: Consider SELLING/TAKING PROFITS (resistance area)")
    report_lines.append("  - Channel breakouts: Watch for moves above/below channel boundaries")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w') as f:
        f.write(report_text)

    # Create TradingView lists
    create_tradingview_lists(bottom_third, middle_third, top_third)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")
    print(f"TradingView lists saved to: {buylist_dir}")

def create_tradingview_lists(bottom_third, middle_third, top_third):
    """Create TradingView format watchlists by zone"""

    # Bottom third (buy zone)
    with open(os.path.join(buylist_dir, 'tradingview_monthly_channel_bottom.txt'), 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("MONTHLY CHANNELS - BOTTOM THIRD (BUY ZONE)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(bottom_third)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")
        tickers = [c['ticker'] for c in bottom_third]
        f.write(",".join(tickers) + "\n\n")
        f.write("-" * 80 + "\n\n")
        f.write("Individual symbols (one per line):\n")
        f.write("-" * 80 + "\n")
        for ticker in tickers:
            f.write(ticker + "\n")

    # Top third (sell zone)
    with open(os.path.join(buylist_dir, 'tradingview_monthly_channel_top.txt'), 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("MONTHLY CHANNELS - TOP THIRD (SELL/RESISTANCE ZONE)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(top_third)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")
        tickers = [c['ticker'] for c in top_third]
        f.write(",".join(tickers) + "\n\n")
        f.write("-" * 80 + "\n\n")
        f.write("Individual symbols (one per line):\n")
        f.write("-" * 80 + "\n")
        for ticker in tickers:
            f.write(ticker + "\n")

if __name__ == "__main__":
    # You can adjust the lookback_months parameter (default is 6 months)
    run_monthly_channel_scan(lookback_months=6)
