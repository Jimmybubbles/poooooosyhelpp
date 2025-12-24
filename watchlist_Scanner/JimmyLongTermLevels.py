import pandas as pd
import numpy as np
import os
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'jimmy_long_term_levels.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def calculate_jimmy_levels(ticker_symbol, results_dir, show_monthly=False, show_quarterly=True):
    """
    Calculate Jimmy's Long Term Levels (Monthly and Quarterly support/resistance)

    This replicates the TradingView indicator that shows:
    - Previous Month: High, Low, Open, Close
    - Previous Quarter: High, Low, Open, Close

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files
        show_monthly: Show monthly levels (default False)
        show_quarterly: Show quarterly levels (default True)

    Returns:
        Dictionary with level data or None
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

        # Need at least 6 months of data
        if len(df) < 126:  # ~6 months of trading days
            return None

        # Get current price
        current_price = df['Close'].iloc[-1]
        current_date = df.index[-1]

        # Resample to monthly data
        monthly_df = df.resample('ME').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()

        # Resample to quarterly data (3 months)
        quarterly_df = df.resample('QE').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()

        levels = {
            'ticker': ticker_symbol,
            'current_date': current_date,
            'current_price': current_price,
            'monthly': None,
            'quarterly': None
        }

        # Get PREVIOUS month's OHLC (index -2 because -1 is current incomplete month)
        if show_monthly and len(monthly_df) >= 2:
            last_complete_month = monthly_df.iloc[-2]
            month_date = monthly_df.index[-2]

            levels['monthly'] = {
                'date': month_date,
                'high': last_complete_month['High'],
                'low': last_complete_month['Low'],
                'open': last_complete_month['Open'],
                'close': last_complete_month['Close']
            }

        # Get PREVIOUS quarter's OHLC (index -2 because -1 is current incomplete quarter)
        if show_quarterly and len(quarterly_df) >= 2:
            last_complete_quarter = quarterly_df.iloc[-2]
            quarter_date = quarterly_df.index[-2]

            levels['quarterly'] = {
                'date': quarter_date,
                'high': last_complete_quarter['High'],
                'low': last_complete_quarter['Low'],
                'open': last_complete_quarter['Open'],
                'close': last_complete_quarter['Close']
            }

        # Check if current price is near any levels (within 2%)
        def is_near_level(price, level, tolerance=0.02):
            """Check if price is within tolerance% of level"""
            return abs(price - level) / level <= tolerance

        # Analyze which levels price is near
        levels['near_levels'] = []

        if levels['monthly']:
            m = levels['monthly']
            if is_near_level(current_price, m['high']):
                levels['near_levels'].append('Monthly High')
            if is_near_level(current_price, m['low']):
                levels['near_levels'].append('Monthly Low')
            if is_near_level(current_price, m['open']):
                levels['near_levels'].append('Monthly Open')
            if is_near_level(current_price, m['close']):
                levels['near_levels'].append('Monthly Close')

        if levels['quarterly']:
            q = levels['quarterly']
            if is_near_level(current_price, q['high']):
                levels['near_levels'].append('Quarterly High')
            if is_near_level(current_price, q['low']):
                levels['near_levels'].append('Quarterly Low')
            if is_near_level(current_price, q['open']):
                levels['near_levels'].append('Quarterly Open')
            if is_near_level(current_price, q['close']):
                levels['near_levels'].append('Quarterly Close')

        return levels

    except Exception as e:
        print(f"Error calculating levels for {ticker_symbol}: {e}")
        return None

def run_jimmy_levels_scan(show_monthly=False, show_quarterly=True):
    """
    Run Jimmy's Long Term Levels scan across all tickers

    Args:
        show_monthly: Include monthly levels (default False)
        show_quarterly: Include quarterly levels (default True)
    """
    print("=" * 80)
    print("JIMMY'S LONG TERM LEVELS SCANNER")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("LEVELS CALCULATED:")
    if show_monthly:
        print("  ✓ Previous Month: High, Low, Open, Close")
    if show_quarterly:
        print("  ✓ Previous Quarter: High, Low, Open, Close")
    print()
    print("Finding stocks near key support/resistance levels...")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Scanning {len(tickers)} tickers...")
    print()

    # Scan all tickers
    all_levels = []
    stocks_near_levels = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers scanned...")

        result = calculate_jimmy_levels(ticker, results_dir, show_monthly, show_quarterly)

        if result:
            all_levels.append(result)
            # Keep stocks that are near any level
            if result['near_levels']:
                stocks_near_levels.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(stocks_near_levels)} stocks near key levels")
    print()

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("JIMMY'S LONG TERM LEVELS - SUPPORT/RESISTANCE SCANNER")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("CONCEPT:")
    report_lines.append("  Previous month and quarter OHLC levels often act as strong")
    report_lines.append("  support and resistance zones. Stocks near these levels may")
    report_lines.append("  bounce (at support) or reverse (at resistance).")
    report_lines.append("")
    report_lines.append(f"Total Stocks Analyzed: {len(all_levels)}")
    report_lines.append(f"Stocks Near Key Levels (within 2%): {len(stocks_near_levels)}")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    if stocks_near_levels:
        # Sort by number of levels nearby (most levels first)
        stocks_near_levels.sort(key=lambda x: len(x['near_levels']), reverse=True)

        report_lines.append("STOCKS NEAR KEY SUPPORT/RESISTANCE LEVELS:")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'Levels Nearby':<50}")
        report_lines.append("-" * 80)

        for stock in stocks_near_levels:
            levels_str = ", ".join(stock['near_levels'])
            report_lines.append(
                f"{stock['ticker']:<8} "
                f"${stock['current_price']:<9.2f} "
                f"{levels_str}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # Detailed levels for top 50 stocks by market cap (or all if less than 50)
    report_lines.append("DETAILED LEVELS - ALL STOCKS:")
    report_lines.append("-" * 80)

    if show_monthly and show_quarterly:
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'M-High':<10} {'M-Low':<10} {'Q-High':<10} {'Q-Low':<10}")
        report_lines.append("-" * 80)

        for stock in all_levels[:100]:  # Show first 100
            m = stock['monthly'] if stock['monthly'] else {'high': 0, 'low': 0}
            q = stock['quarterly'] if stock['quarterly'] else {'high': 0, 'low': 0}

            report_lines.append(
                f"{stock['ticker']:<8} "
                f"${stock['current_price']:<9.2f} "
                f"${m['high']:<9.2f} "
                f"${m['low']:<9.2f} "
                f"${q['high']:<9.2f} "
                f"${q['low']:<9.2f}"
            )

    elif show_quarterly:
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'Q-High':<10} {'Q-Low':<10} {'Q-Open':<10} {'Q-Close':<10}")
        report_lines.append("-" * 80)

        for stock in all_levels[:100]:
            q = stock['quarterly']
            if q:
                report_lines.append(
                    f"{stock['ticker']:<8} "
                    f"${stock['current_price']:<9.2f} "
                    f"${q['high']:<9.2f} "
                    f"${q['low']:<9.2f} "
                    f"${q['open']:<9.2f} "
                    f"${q['close']:<9.2f}"
                )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("LEGEND:")
    report_lines.append("  M-High/M-Low: Previous Month High/Low")
    report_lines.append("  Q-High/Q-Low: Previous Quarter High/Low")
    report_lines.append("  Q-Open/Q-Close: Previous Quarter Open/Close")
    report_lines.append("")
    report_lines.append("TRADING STRATEGY:")
    report_lines.append("  - Watch for bounces at Low levels (support)")
    report_lines.append("  - Watch for rejections at High levels (resistance)")
    report_lines.append("  - Breakouts above resistance can signal strong moves")
    report_lines.append("  - Breakdowns below support can signal weakness")
    report_lines.append("  - Open/Close levels often act as pivot points")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w') as f:
        f.write(report_text)

    # Create TradingView list for stocks near levels
    create_tradingview_list(stocks_near_levels)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")

def create_tradingview_list(stocks_near_levels):
    """Create TradingView watchlist for stocks near levels"""
    tradingview_file = os.path.join(buylist_dir, 'tradingview_jimmy_levels.txt')

    with open(tradingview_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("JIMMY'S LONG TERM LEVELS - STOCKS NEAR KEY LEVELS\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(stocks_near_levels)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        tickers = [stock['ticker'] for stock in stocks_near_levels]
        f.write(",".join(tickers) + "\n\n")

        f.write("-" * 80 + "\n\n")
        f.write("Individual symbols (one per line):\n")
        f.write("-" * 80 + "\n")
        for ticker in tickers:
            f.write(ticker + "\n")

if __name__ == "__main__":
    # Run with quarterly levels (matching the default in Pine Script)
    # Set show_monthly=True if you want to see monthly levels too
    run_jimmy_levels_scan(show_monthly=False, show_quarterly=True)
