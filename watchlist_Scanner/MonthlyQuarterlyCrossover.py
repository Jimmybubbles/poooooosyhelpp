import pandas as pd
import numpy as np
import os
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'monthly_quarterly_crossover_results.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def detect_monthly_quarterly_crossover(ticker_symbol, results_dir):
    """
    Detect if previous month crossed below previous quarter levels

    Specifically looking for:
    - Previous Month Low < Previous Quarter Low (breakdown)
    - Previous Month Low < Previous Quarter Open (weakness)
    - Previous Month Close < Previous Quarter Low (confirmed breakdown)
    - Previous Month Close < Previous Quarter Open (confirmed weakness)

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files

    Returns:
        Dictionary with crossover data or None
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

        # Need at least 2 complete months and 2 complete quarters
        if len(monthly_df) < 2 or len(quarterly_df) < 2:
            return None

        # Get PREVIOUS month's OHLC (index -2 because -1 is current incomplete month)
        prev_month = monthly_df.iloc[-2]
        prev_month_date = monthly_df.index[-2]

        # Get PREVIOUS quarter's OHLC (index -2 because -1 is current incomplete quarter)
        prev_quarter = quarterly_df.iloc[-2]
        prev_quarter_date = quarterly_df.index[-2]

        # Check for crossover conditions
        crossovers = []

        # 1. Previous Month Low crossed below Previous Quarter Low
        if prev_month['Low'] < prev_quarter['Low']:
            crossovers.append('Month Low < Quarter Low')

        # 2. Previous Month Low crossed below Previous Quarter Open
        if prev_month['Low'] < prev_quarter['Open']:
            crossovers.append('Month Low < Quarter Open')

        # 3. Previous Month Close crossed below Previous Quarter Low
        if prev_month['Close'] < prev_quarter['Low']:
            crossovers.append('Month Close < Quarter Low')

        # 4. Previous Month Close crossed below Previous Quarter Open
        if prev_month['Close'] < prev_quarter['Open']:
            crossovers.append('Month Close < Quarter Open')

        # If no crossovers detected, return None
        if not crossovers:
            return None

        # Calculate severity metrics
        month_low_vs_quarter_low_pct = ((prev_month['Low'] - prev_quarter['Low']) / prev_quarter['Low']) * 100
        month_close_vs_quarter_low_pct = ((prev_month['Close'] - prev_quarter['Low']) / prev_quarter['Low']) * 100
        month_close_vs_quarter_open_pct = ((prev_month['Close'] - prev_quarter['Open']) / prev_quarter['Open']) * 100

        # Calculate current price vs quarter low (how much recovery/further decline)
        current_vs_quarter_low_pct = ((current_price - prev_quarter['Low']) / prev_quarter['Low']) * 100

        return {
            'ticker': ticker_symbol,
            'current_date': current_date,
            'current_price': current_price,
            'prev_month_date': prev_month_date,
            'prev_month_open': prev_month['Open'],
            'prev_month_high': prev_month['High'],
            'prev_month_low': prev_month['Low'],
            'prev_month_close': prev_month['Close'],
            'prev_quarter_date': prev_quarter_date,
            'prev_quarter_open': prev_quarter['Open'],
            'prev_quarter_high': prev_quarter['High'],
            'prev_quarter_low': prev_quarter['Low'],
            'prev_quarter_close': prev_quarter['Close'],
            'crossovers': crossovers,
            'month_low_vs_quarter_low_pct': month_low_vs_quarter_low_pct,
            'month_close_vs_quarter_low_pct': month_close_vs_quarter_low_pct,
            'month_close_vs_quarter_open_pct': month_close_vs_quarter_open_pct,
            'current_vs_quarter_low_pct': current_vs_quarter_low_pct
        }

    except Exception as e:
        print(f"Error calculating crossovers for {ticker_symbol}: {e}")
        return None

def run_crossover_scan():
    """
    Run the Monthly/Quarterly Crossover scan across all tickers
    """
    print("=" * 80)
    print("MONTHLY vs QUARTERLY CROSSOVER SCANNER")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("SCANNING FOR:")
    print("  - Previous Month Low < Previous Quarter Low (breakdown)")
    print("  - Previous Month Low < Previous Quarter Open (weakness)")
    print("  - Previous Month Close < Previous Quarter Low (confirmed breakdown)")
    print("  - Previous Month Close < Previous Quarter Open (confirmed weakness)")
    print()
    print("Finding stocks with potential breakdowns or weakness signals...")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Scanning {len(tickers)} tickers...")
    print()

    # Scan all tickers
    all_crossovers = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers scanned...")

        result = detect_monthly_quarterly_crossover(ticker, results_dir)

        if result:
            all_crossovers.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(all_crossovers)} stocks with crossover signals")
    print()

    if not all_crossovers:
        print("No crossover signals found.")
        return

    # Categorize by severity
    confirmed_breakdowns = []  # Month Close < Quarter Low
    severe_weakness = []  # Month Low < Quarter Low but Close above
    moderate_weakness = []  # Month Low/Close < Quarter Open only

    for stock in all_crossovers:
        crossovers = stock['crossovers']

        if 'Month Close < Quarter Low' in crossovers:
            confirmed_breakdowns.append(stock)
        elif 'Month Low < Quarter Low' in crossovers:
            severe_weakness.append(stock)
        else:
            moderate_weakness.append(stock)

    # Sort each category by severity (most negative first)
    confirmed_breakdowns.sort(key=lambda x: x['month_close_vs_quarter_low_pct'])
    severe_weakness.sort(key=lambda x: x['month_low_vs_quarter_low_pct'])
    moderate_weakness.sort(key=lambda x: x['month_close_vs_quarter_open_pct'])

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("MONTHLY vs QUARTERLY CROSSOVER SCANNER - BREAKDOWN SIGNALS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("CONCEPT:")
    report_lines.append("  When previous month's levels cross below previous quarter's levels,")
    report_lines.append("  it indicates potential weakness or breakdown. These are bearish signals")
    report_lines.append("  showing deterioration in price structure on higher timeframes.")
    report_lines.append("")
    report_lines.append(f"Total Crossover Signals: {len(all_crossovers)}")
    report_lines.append(f"  Confirmed Breakdowns: {len(confirmed_breakdowns)} (Month Close < Quarter Low)")
    report_lines.append(f"  Severe Weakness: {len(severe_weakness)} (Month Low < Quarter Low)")
    report_lines.append(f"  Moderate Weakness: {len(moderate_weakness)} (Below Quarter Open)")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # CONFIRMED BREAKDOWNS - Most severe
    if confirmed_breakdowns:
        report_lines.append("[CRITICAL] CONFIRMED BREAKDOWNS (Month Close < Quarter Low):")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Ticker':<8} {'Current':<10} {'M-Close':<10} {'Q-Low':<10} {'Breakdown%':<12} {'Recovery%':<12} {'Signals'}")
        report_lines.append("-" * 80)

        for stock in confirmed_breakdowns:
            signals_str = ", ".join(stock['crossovers'])
            report_lines.append(
                f"{stock['ticker']:<8} "
                f"${stock['current_price']:<9.2f} "
                f"${stock['prev_month_close']:<9.2f} "
                f"${stock['prev_quarter_low']:<9.2f} "
                f"{stock['month_close_vs_quarter_low_pct']:>10.2f}% "
                f"{stock['current_vs_quarter_low_pct']:>10.2f}% "
                f"{signals_str}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # SEVERE WEAKNESS - Month low breached quarter low
    if severe_weakness:
        report_lines.append("[WARNING] SEVERE WEAKNESS (Month Low < Quarter Low):")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Ticker':<8} {'Current':<10} {'M-Low':<10} {'Q-Low':<10} {'Breach%':<12} {'Recovery%':<12} {'Signals'}")
        report_lines.append("-" * 80)

        for stock in severe_weakness:
            signals_str = ", ".join(stock['crossovers'])
            report_lines.append(
                f"{stock['ticker']:<8} "
                f"${stock['current_price']:<9.2f} "
                f"${stock['prev_month_low']:<9.2f} "
                f"${stock['prev_quarter_low']:<9.2f} "
                f"{stock['month_low_vs_quarter_low_pct']:>10.2f}% "
                f"{stock['current_vs_quarter_low_pct']:>10.2f}% "
                f"{signals_str}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # MODERATE WEAKNESS
    if moderate_weakness:
        report_lines.append("[CAUTION] MODERATE WEAKNESS (Below Quarter Open):")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Ticker':<8} {'Current':<10} {'M-Close':<10} {'Q-Open':<10} {'Breach%':<12} {'Recovery%':<12} {'Signals'}")
        report_lines.append("-" * 80)

        for stock in moderate_weakness:
            signals_str = ", ".join(stock['crossovers'])
            report_lines.append(
                f"{stock['ticker']:<8} "
                f"${stock['current_price']:<9.2f} "
                f"${stock['prev_month_close']:<9.2f} "
                f"${stock['prev_quarter_open']:<9.2f} "
                f"{stock['month_close_vs_quarter_open_pct']:>10.2f}% "
                f"{stock['current_vs_quarter_low_pct']:>10.2f}% "
                f"{signals_str}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # DETAILED TABLE - All stocks
    report_lines.append("DETAILED ANALYSIS - ALL CROSSOVER STOCKS:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'M-Low':<10} {'M-Close':<10} {'Q-Low':<10} {'Q-Open':<10} {'Category':<20}")
    report_lines.append("-" * 80)

    for stock in all_crossovers:
        if stock in confirmed_breakdowns:
            category = "CONFIRMED BREAKDOWN"
        elif stock in severe_weakness:
            category = "SEVERE WEAKNESS"
        else:
            category = "MODERATE WEAKNESS"

        report_lines.append(
            f"{stock['ticker']:<8} "
            f"${stock['prev_month_low']:<9.2f} "
            f"${stock['prev_month_close']:<9.2f} "
            f"${stock['prev_quarter_low']:<9.2f} "
            f"${stock['prev_quarter_open']:<9.2f} "
            f"{category}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("LEGEND:")
    report_lines.append("  M-Low/M-Close: Previous Month Low/Close")
    report_lines.append("  Q-Low/Q-Open: Previous Quarter Low/Open")
    report_lines.append("  Breakdown%: How far below quarter level (negative = worse)")
    report_lines.append("  Recovery%: Current price vs quarter low (positive = recovering)")
    report_lines.append("")
    report_lines.append("TRADING IMPLICATIONS:")
    report_lines.append("  [CRITICAL] CONFIRMED BREAKDOWN: Avoid or consider shorting")
    report_lines.append("     - Month closed below quarter low = strong bearish signal")
    report_lines.append("     - Wait for reclaim of quarter low before considering long")
    report_lines.append("")
    report_lines.append("  [WARNING] SEVERE WEAKNESS: Caution, watch for further breakdown")
    report_lines.append("     - Month violated quarter low but closed above it")
    report_lines.append("     - Vulnerable, but not confirmed breakdown yet")
    report_lines.append("")
    report_lines.append("  [CAUTION] MODERATE WEAKNESS: Early warning signal")
    report_lines.append("     - Trading below quarter open but above quarter low")
    report_lines.append("     - Monitor for potential recovery or further weakness")
    report_lines.append("")
    report_lines.append("CONTRARIAN OPPORTUNITY:")
    report_lines.append("  Stocks with large negative Breakdown% but positive Recovery%")
    report_lines.append("  may be bouncing from oversold levels - potential reversals")
    report_lines.append("")

    # Write to file with UTF-8 encoding
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Create TradingView lists
    create_tradingview_lists(confirmed_breakdowns, severe_weakness, moderate_weakness)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")

def create_tradingview_lists(confirmed_breakdowns, severe_weakness, moderate_weakness):
    """Create TradingView watchlists for each category"""

    # Confirmed Breakdowns
    with open(os.path.join(buylist_dir, 'tradingview_confirmed_breakdowns.txt'), 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("CONFIRMED BREAKDOWNS - Month Close < Quarter Low\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(confirmed_breakdowns)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        if confirmed_breakdowns:
            tickers = [stock['ticker'] for stock in confirmed_breakdowns]
            f.write(",".join(tickers) + "\n\n")
            f.write("-" * 80 + "\n\n")
            f.write("Individual symbols (one per line):\n")
            f.write("-" * 80 + "\n")
            for ticker in tickers:
                f.write(ticker + "\n")

    # Severe Weakness
    with open(os.path.join(buylist_dir, 'tradingview_severe_weakness.txt'), 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("SEVERE WEAKNESS - Month Low < Quarter Low\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(severe_weakness)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        if severe_weakness:
            tickers = [stock['ticker'] for stock in severe_weakness]
            f.write(",".join(tickers) + "\n\n")
            f.write("-" * 80 + "\n\n")
            f.write("Individual symbols (one per line):\n")
            f.write("-" * 80 + "\n")
            for ticker in tickers:
                f.write(ticker + "\n")

if __name__ == "__main__":
    run_crossover_scan()
