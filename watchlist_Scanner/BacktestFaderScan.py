import yfinance as yf
import pandas as pd
import os
from datetime import datetime
import re

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# Path to the Fader scan results file
results_file = os.path.join(script_dir, 'buylist', 'sorted_fader_scan_results.txt')
output_file = os.path.join(script_dir, 'buylist', 'backtest_fader_results.txt')

def parse_scan_results(file_path):
    """Parse the Fader scan results file and extract signals"""
    signals = []

    try:
        with open(file_path, 'r') as f:
            content = f.read()

        # Pattern: BUY TICKER DATE : X day channel breakout - Price: Y.YY - Fader: Z.ZZ
        pattern = r'BUY\s+([A-Z]+)\s+(\d{2}/\d{2}/\d{4})\s+:\s+\d+\s+day\s+channel\s+breakout\s+-\s+Price:\s+([\d.]+)'

        matches = re.findall(pattern, content)

        for ticker, date_str, price_str in matches:
            # Convert date from MM/DD/YYYY to datetime
            signal_date = datetime.strptime(date_str, '%m/%d/%Y')
            signal_price = float(price_str)

            signals.append({
                'ticker': ticker,
                'signal_date': signal_date,
                'signal_date_str': date_str,
                'signal_price': signal_price
            })

        return signals

    except Exception as e:
        print(f"Error parsing results file: {e}")
        return []

def get_current_price(ticker):
    """Get the current price for a ticker"""
    try:
        stock = yf.Ticker(ticker)
        # Get the most recent price
        hist = stock.history(period='1d')

        if not hist.empty:
            return hist['Close'].iloc[-1]
        else:
            return None
    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
        return None

def calculate_pnl(signal_price, current_price):
    """Calculate profit/loss percentage"""
    if signal_price == 0:
        return 0
    return ((current_price - signal_price) / signal_price) * 100

def analyze_price_range(results, min_price, max_price, range_name):
    """Analyze results for a specific price range"""
    filtered = [r for r in results if min_price <= r['signal_price'] < max_price]

    if not filtered:
        return None

    total = len(filtered)
    profitable = sum(1 for r in filtered if r['pnl_pct'] > 0)
    losing = sum(1 for r in filtered if r['pnl_pct'] <= 0)
    avg_pnl = sum(r['pnl_pct'] for r in filtered) / total

    return {
        'range_name': range_name,
        'total': total,
        'profitable': profitable,
        'losing': losing,
        'avg_pnl': avg_pnl,
        'win_rate': (profitable / total * 100) if total > 0 else 0
    }

def run_backtest():
    """Run the backtest analysis"""
    print("=" * 80)
    print("FADER SCAN BACKTEST ANALYSIS")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Parse scan results
    print("Reading scan results...")
    signals = parse_scan_results(results_file)

    if not signals:
        print("No signals found in results file!")
        return

    print(f"Found {len(signals)} signals to backtest")
    print()

    # Backtest each signal
    results = []

    for i, signal in enumerate(signals, 1):
        ticker = signal['ticker']
        signal_price = signal['signal_price']
        signal_date = signal['signal_date_str']

        print(f"[{i}/{len(signals)}] Testing {ticker}...", end=' ')

        current_price = get_current_price(ticker)

        if current_price is None:
            print("FAILED (no price data)")
            continue

        pnl = calculate_pnl(signal_price, current_price)

        results.append({
            'ticker': ticker,
            'signal_date': signal_date,
            'signal_price': signal_price,
            'current_price': current_price,
            'pnl_pct': pnl,
            'status': 'PROFIT' if pnl > 0 else 'LOSS'
        })

        print(f"PnL: {pnl:+.2f}%")

    print()
    print("=" * 80)
    print("GENERATING REPORT")
    print("=" * 80)

    # Sort by PnL (best to worst)
    results.sort(key=lambda x: x['pnl_pct'], reverse=True)

    # Calculate statistics
    total_signals = len(results)
    profitable = sum(1 for r in results if r['pnl_pct'] > 0)
    losing = sum(1 for r in results if r['pnl_pct'] <= 0)
    avg_pnl = sum(r['pnl_pct'] for r in results) / total_signals if total_signals > 0 else 0

    # Analyze by price ranges
    price_ranges = [
        (0, 1, "$0-$1"),
        (1, 5, "$1-$5"),
        (5, 10, "$5-$10"),
        (10, 20, "$10-$20"),
        (20, 50, "$20-$50"),
        (50, 100, "$50-$100"),
        (100, 500, "$100-$500"),
        (500, float('inf'), "$500+")
    ]

    range_stats = []
    for min_price, max_price, range_name in price_ranges:
        stats = analyze_price_range(results, min_price, max_price, range_name)
        if stats:
            range_stats.append(stats)

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("FADER SCAN BACKTEST RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Total Signals Analyzed: {total_signals}")
    report_lines.append(f"Profitable Positions: {profitable} ({profitable/total_signals*100:.1f}%)")
    report_lines.append(f"Losing Positions: {losing} ({losing/total_signals*100:.1f}%)")
    report_lines.append(f"Average PnL: {avg_pnl:+.2f}%")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Add price range analysis
    report_lines.append("PERFORMANCE BY PRICE RANGE:")
    report_lines.append("=" * 80)
    report_lines.append(f"{'Range':<15} {'Total':<8} {'Wins':<8} {'Losses':<8} {'Win Rate':<12} {'Avg PnL':<10}")
    report_lines.append("-" * 80)

    for stats in range_stats:
        report_lines.append(
            f"{stats['range_name']:<15} "
            f"{stats['total']:<8} "
            f"{stats['profitable']:<8} "
            f"{stats['losing']:<8} "
            f"{stats['win_rate']:<11.1f}% "
            f"{stats['avg_pnl']:+.2f}%"
        )

    report_lines.append("=" * 80)
    report_lines.append("")

    # Profitable positions
    report_lines.append("PROFITABLE POSITIONS:")
    report_lines.append("-" * 80)
    profitable_results = [r for r in results if r['pnl_pct'] > 0]

    if profitable_results:
        for r in profitable_results:
            report_lines.append(
                f"{r['ticker']:6s} | Signal: {r['signal_date']:12s} | "
                f"Buy: ${r['signal_price']:8.2f} | Current: ${r['current_price']:8.2f} | "
                f"PnL: {r['pnl_pct']:+7.2f}%"
            )
    else:
        report_lines.append("No profitable positions")

    report_lines.append("")

    # Losing positions
    report_lines.append("LOSING POSITIONS:")
    report_lines.append("-" * 80)
    losing_results = [r for r in results if r['pnl_pct'] <= 0]

    if losing_results:
        for r in losing_results:
            report_lines.append(
                f"{r['ticker']:6s} | Signal: {r['signal_date']:12s} | "
                f"Buy: ${r['signal_price']:8.2f} | Current: ${r['current_price']:8.2f} | "
                f"PnL: {r['pnl_pct']:+7.2f}%"
            )
    else:
        report_lines.append("No losing positions")

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("END OF BACKTEST REPORT")
    report_lines.append("=" * 80)

    # Write to file
    report_text = '\n'.join(report_lines)

    with open(output_file, 'w') as f:
        f.write(report_text)

    # Print to console
    print(report_text)
    print()
    print(f"Report saved to: {output_file}")

if __name__ == "__main__":
    run_backtest()
