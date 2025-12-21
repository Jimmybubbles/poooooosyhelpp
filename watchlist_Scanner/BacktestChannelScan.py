import yfinance as yf
import pandas as pd
import os
from datetime import datetime
import re

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# Path to the Channel 3-Week scan results file
results_file = os.path.join(script_dir, 'buylist', 'sorted_scan_results_3week.txt')
output_file = os.path.join(script_dir, 'buylist', 'backtest_channel_results.txt')

def parse_scan_results(file_path):
    """Parse the Channel scan results file and extract signals"""
    buy_signals = []
    sell_signals = []

    try:
        with open(file_path, 'r') as f:
            content = f.read()

        # Pattern for BUY: BUY TICKER DATE : Upside Breakout after X days channel - Price: Y.YY
        buy_pattern = r'BUY\s+([A-Z]+)\s+(\d{2}/\d{2}/\d{4})\s+:\s+Upside\s+Breakout\s+after\s+\d+\s+days\s+channel\s+-\s+Price:\s+([\d.]+)'

        # Pattern for SELL: SELL TICKER DATE : Downside Breakdown after X days channel - Price: Y.YY
        sell_pattern = r'SELL\s+([A-Z]+)\s+(\d{2}/\d{2}/\d{4})\s+:\s+Downside\s+Breakdown\s+after\s+\d+\s+days\s+channel\s+-\s+Price:\s+([\d.]+)'

        # Find BUY signals
        buy_matches = re.findall(buy_pattern, content)
        for ticker, date_str, price_str in buy_matches:
            signal_date = datetime.strptime(date_str, '%m/%d/%Y')
            signal_price = float(price_str)

            buy_signals.append({
                'ticker': ticker,
                'signal_date': signal_date,
                'signal_date_str': date_str,
                'signal_price': signal_price,
                'type': 'BUY'
            })

        # Find SELL signals
        sell_matches = re.findall(sell_pattern, content)
        for ticker, date_str, price_str in sell_matches:
            signal_date = datetime.strptime(date_str, '%m/%d/%Y')
            signal_price = float(price_str)

            sell_signals.append({
                'ticker': ticker,
                'signal_date': signal_date,
                'signal_date_str': date_str,
                'signal_price': signal_price,
                'type': 'SELL'
            })

        return buy_signals, sell_signals

    except Exception as e:
        print(f"Error parsing results file: {e}")
        return [], []

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

def calculate_pnl(signal_price, current_price, signal_type):
    """Calculate profit/loss percentage based on signal type"""
    if signal_price == 0:
        return 0

    if signal_type == 'BUY':
        # For BUY signals: profit if price went up
        return ((current_price - signal_price) / signal_price) * 100
    else:  # SELL
        # For SELL signals: profit if price went down (short position)
        return ((signal_price - current_price) / signal_price) * 100

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
    print("CHANNEL 3-WEEK BREAKOUT BACKTEST ANALYSIS")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Parse scan results
    print("Reading scan results...")
    buy_signals, sell_signals = parse_scan_results(results_file)

    if not buy_signals and not sell_signals:
        print("No signals found in results file!")
        return

    print(f"Found {len(buy_signals)} BUY signals and {len(sell_signals)} SELL signals to backtest")
    print()

    # Backtest BUY signals
    buy_results = []
    print("Testing BUY signals...")
    for i, signal in enumerate(buy_signals, 1):
        ticker = signal['ticker']
        signal_price = signal['signal_price']
        signal_date = signal['signal_date_str']

        print(f"[{i}/{len(buy_signals)}] Testing {ticker}...", end=' ')

        current_price = get_current_price(ticker)

        if current_price is None:
            print("FAILED (no price data)")
            continue

        pnl = calculate_pnl(signal_price, current_price, 'BUY')

        buy_results.append({
            'ticker': ticker,
            'signal_date': signal_date,
            'signal_price': signal_price,
            'current_price': current_price,
            'pnl_pct': pnl,
            'status': 'PROFIT' if pnl > 0 else 'LOSS'
        })

        print(f"PnL: {pnl:+.2f}%")

    print()

    # Backtest SELL signals
    sell_results = []
    print("Testing SELL signals...")
    for i, signal in enumerate(sell_signals, 1):
        ticker = signal['ticker']
        signal_price = signal['signal_price']
        signal_date = signal['signal_date_str']

        print(f"[{i}/{len(sell_signals)}] Testing {ticker}...", end=' ')

        current_price = get_current_price(ticker)

        if current_price is None:
            print("FAILED (no price data)")
            continue

        pnl = calculate_pnl(signal_price, current_price, 'SELL')

        sell_results.append({
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
    buy_results.sort(key=lambda x: x['pnl_pct'], reverse=True)
    sell_results.sort(key=lambda x: x['pnl_pct'], reverse=True)

    # Calculate statistics for BUY signals
    total_buy = len(buy_results)
    profitable_buy = sum(1 for r in buy_results if r['pnl_pct'] > 0)
    losing_buy = sum(1 for r in buy_results if r['pnl_pct'] <= 0)
    avg_pnl_buy = sum(r['pnl_pct'] for r in buy_results) / total_buy if total_buy > 0 else 0

    # Calculate statistics for SELL signals
    total_sell = len(sell_results)
    profitable_sell = sum(1 for r in sell_results if r['pnl_pct'] > 0)
    losing_sell = sum(1 for r in sell_results if r['pnl_pct'] <= 0)
    avg_pnl_sell = sum(r['pnl_pct'] for r in sell_results) / total_sell if total_sell > 0 else 0

    # Overall statistics
    all_results = buy_results + sell_results
    total_signals = len(all_results)
    total_profitable = profitable_buy + profitable_sell
    total_losing = losing_buy + losing_sell
    overall_avg_pnl = sum(r['pnl_pct'] for r in all_results) / total_signals if total_signals > 0 else 0

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

    # Analyze price ranges for BUY signals
    buy_range_stats = []
    for min_price, max_price, range_name in price_ranges:
        stats = analyze_price_range(buy_results, min_price, max_price, range_name)
        if stats:
            buy_range_stats.append(stats)

    # Analyze price ranges for SELL signals
    sell_range_stats = []
    for min_price, max_price, range_name in price_ranges:
        stats = analyze_price_range(sell_results, min_price, max_price, range_name)
        if stats:
            sell_range_stats.append(stats)

    # Analyze price ranges for ALL signals
    all_range_stats = []
    for min_price, max_price, range_name in price_ranges:
        stats = analyze_price_range(all_results, min_price, max_price, range_name)
        if stats:
            all_range_stats.append(stats)

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("CHANNEL 3-WEEK BREAKOUT BACKTEST RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("OVERALL STATISTICS:")
    report_lines.append("-" * 80)
    report_lines.append(f"Total Signals Analyzed: {total_signals}")
    report_lines.append(f"Total Profitable: {total_profitable} ({total_profitable/total_signals*100:.1f}%)")
    report_lines.append(f"Total Losing: {total_losing} ({total_losing/total_signals*100:.1f}%)")
    report_lines.append(f"Overall Average PnL: {overall_avg_pnl:+.2f}%")
    report_lines.append("")
    report_lines.append("BUY SIGNALS STATISTICS:")
    report_lines.append(f"  Total: {total_buy}")
    report_lines.append(f"  Profitable: {profitable_buy} ({profitable_buy/total_buy*100:.1f}%)" if total_buy > 0 else "  Profitable: 0")
    report_lines.append(f"  Losing: {losing_buy} ({losing_buy/total_buy*100:.1f}%)" if total_buy > 0 else "  Losing: 0")
    report_lines.append(f"  Average PnL: {avg_pnl_buy:+.2f}%")
    report_lines.append("")
    report_lines.append("SELL SIGNALS STATISTICS:")
    report_lines.append(f"  Total: {total_sell}")
    report_lines.append(f"  Profitable: {profitable_sell} ({profitable_sell/total_sell*100:.1f}%)" if total_sell > 0 else "  Profitable: 0")
    report_lines.append(f"  Losing: {losing_sell} ({losing_sell/total_sell*100:.1f}%)" if total_sell > 0 else "  Losing: 0")
    report_lines.append(f"  Average PnL: {avg_pnl_sell:+.2f}%")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Add price range analysis for ALL SIGNALS
    if all_range_stats:
        report_lines.append("OVERALL PERFORMANCE BY PRICE RANGE (ALL SIGNALS):")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Range':<15} {'Total':<8} {'Wins':<8} {'Losses':<8} {'Win Rate':<12} {'Avg PnL':<10}")
        report_lines.append("-" * 80)

        for stats in all_range_stats:
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

    # Add price range analysis for BUY SIGNALS
    if buy_range_stats:
        report_lines.append("BUY SIGNALS PERFORMANCE BY PRICE RANGE:")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Range':<15} {'Total':<8} {'Wins':<8} {'Losses':<8} {'Win Rate':<12} {'Avg PnL':<10}")
        report_lines.append("-" * 80)

        for stats in buy_range_stats:
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

    # Add price range analysis for SELL SIGNALS
    if sell_range_stats:
        report_lines.append("SELL SIGNALS PERFORMANCE BY PRICE RANGE:")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Range':<15} {'Total':<8} {'Wins':<8} {'Losses':<8} {'Win Rate':<12} {'Avg PnL':<10}")
        report_lines.append("-" * 80)

        for stats in sell_range_stats:
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

    # BUY SIGNALS - Profitable positions
    report_lines.append("BUY SIGNALS - PROFITABLE POSITIONS:")
    report_lines.append("-" * 80)
    profitable_buy_results = [r for r in buy_results if r['pnl_pct'] > 0]

    if profitable_buy_results:
        for r in profitable_buy_results:
            report_lines.append(
                f"{r['ticker']:6s} | Signal: {r['signal_date']:12s} | "
                f"Buy: ${r['signal_price']:8.2f} | Current: ${r['current_price']:8.2f} | "
                f"PnL: {r['pnl_pct']:+7.2f}%"
            )
    else:
        report_lines.append("No profitable positions")

    report_lines.append("")

    # BUY SIGNALS - Losing positions
    report_lines.append("BUY SIGNALS - LOSING POSITIONS:")
    report_lines.append("-" * 80)
    losing_buy_results = [r for r in buy_results if r['pnl_pct'] <= 0]

    if losing_buy_results:
        for r in losing_buy_results:
            report_lines.append(
                f"{r['ticker']:6s} | Signal: {r['signal_date']:12s} | "
                f"Buy: ${r['signal_price']:8.2f} | Current: ${r['current_price']:8.2f} | "
                f"PnL: {r['pnl_pct']:+7.2f}%"
            )
    else:
        report_lines.append("No losing positions")

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # SELL SIGNALS - Profitable positions
    report_lines.append("SELL SIGNALS - PROFITABLE POSITIONS:")
    report_lines.append("-" * 80)
    profitable_sell_results = [r for r in sell_results if r['pnl_pct'] > 0]

    if profitable_sell_results:
        for r in profitable_sell_results:
            report_lines.append(
                f"{r['ticker']:6s} | Signal: {r['signal_date']:12s} | "
                f"Sell: ${r['signal_price']:8.2f} | Current: ${r['current_price']:8.2f} | "
                f"PnL: {r['pnl_pct']:+7.2f}%"
            )
    else:
        report_lines.append("No profitable positions")

    report_lines.append("")

    # SELL SIGNALS - Losing positions
    report_lines.append("SELL SIGNALS - LOSING POSITIONS:")
    report_lines.append("-" * 80)
    losing_sell_results = [r for r in sell_results if r['pnl_pct'] <= 0]

    if losing_sell_results:
        for r in losing_sell_results:
            report_lines.append(
                f"{r['ticker']:6s} | Signal: {r['signal_date']:12s} | "
                f"Sell: ${r['signal_price']:8.2f} | Current: ${r['current_price']:8.2f} | "
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
