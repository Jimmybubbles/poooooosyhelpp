import pandas as pd
import os
from datetime import datetime, timedelta
from EFI_Indicator import EFI_Indicator

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'efi_backtest_results.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def backtest_ticker(ticker_symbol, results_dir, hold_days=21):
    """
    Backtest EFI maroon signal strategy for a single ticker

    Strategy:
    - BUY when Force Index color turns maroon (strong bearish)
    - HOLD for specified days (default 21 days / 3 weeks)
    - Calculate profit/loss

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files
        hold_days: Number of days to hold the position

    Returns:
        List of trade results
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker_symbol}.csv")

        if not os.path.exists(csv_file):
            return []

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

        if len(df) < 100:
            return []

        # Calculate EFI indicator
        indicator = EFI_Indicator()
        results = indicator.calculate(df)

        # Find all maroon signals
        trades = []

        for i in range(len(df) - hold_days):
            fi_color = results['fi_color'].iloc[i]

            # Buy signal: Force Index turns maroon (strong bearish)
            if fi_color == 'maroon':
                signal_date = df.index[i]
                signal_price = df['Close'].iloc[i]
                normalized_price = results['normalized_price'].iloc[i]
                force_index = results['force_index'].iloc[i]

                # Find exit date (hold_days later)
                exit_idx = i + hold_days
                exit_date = df.index[exit_idx]
                exit_price = df['Close'].iloc[exit_idx]

                # Calculate P&L
                pnl_pct = ((exit_price - signal_price) / signal_price) * 100

                trades.append({
                    'ticker': ticker_symbol,
                    'signal_date': signal_date,
                    'signal_price': signal_price,
                    'exit_date': exit_date,
                    'exit_price': exit_price,
                    'pnl_pct': pnl_pct,
                    'normalized_price': normalized_price,
                    'force_index': force_index,
                    'hold_days': hold_days
                })

        return trades

    except Exception as e:
        print(f"Error backtesting {ticker_symbol}: {e}")
        return []

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

def run_backtest(hold_days=21):
    """Run the EFI backtest analysis"""
    print("=" * 80)
    print("EFI MAROON SIGNAL BACKTEST ANALYSIS")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("STRATEGY:")
    print("  - BUY when Force Index color turns MAROON (strong bearish)")
    print(f"  - HOLD for {hold_days} days")
    print("  - Calculate P&L at exit")
    print()
    print("THEORY:")
    print("  Maroon color indicates Force Index is negative AND decreasing")
    print("  This suggests strong bearish momentum, potentially oversold")
    print("  Buying at this point may capture a reversal or bounce")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Backtesting {len(tickers)} tickers...")
    print()

    # Run backtest for all tickers
    all_trades = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers backtested...")

        trades = backtest_ticker(ticker, results_dir, hold_days)
        all_trades.extend(trades)

    print()
    print(f"Backtest complete!")
    print(f"Found {len(all_trades)} total maroon signals to analyze")
    print()

    if not all_trades:
        print("No trades found.")
        return

    # Calculate statistics
    total_trades = len(all_trades)
    profitable = sum(1 for t in all_trades if t['pnl_pct'] > 0)
    losing = sum(1 for t in all_trades if t['pnl_pct'] <= 0)
    avg_pnl = sum(t['pnl_pct'] for t in all_trades) / total_trades
    win_rate = (profitable / total_trades * 100) if total_trades > 0 else 0

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
        stats = analyze_price_range(all_trades, min_price, max_price, range_name)
        if stats:
            range_stats.append(stats)

    # Sort trades by P&L
    all_trades.sort(key=lambda x: x['pnl_pct'], reverse=True)
    profitable_trades = [t for t in all_trades if t['pnl_pct'] > 0]
    losing_trades = [t for t in all_trades if t['pnl_pct'] <= 0]

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("EFI MAROON SIGNAL BACKTEST RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("STRATEGY:")
    report_lines.append("  - BUY when Force Index color turns MAROON (strong bearish)")
    report_lines.append(f"  - HOLD for {hold_days} days")
    report_lines.append("")
    report_lines.append("OVERALL STATISTICS:")
    report_lines.append(f"  Total Trades: {total_trades}")
    report_lines.append(f"  Profitable: {profitable} ({win_rate:.1f}%)")
    report_lines.append(f"  Losing: {losing} ({(losing/total_trades*100):.1f}%)")
    report_lines.append(f"  Average P&L: {avg_pnl:+.2f}%")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Add price range analysis
    if range_stats:
        report_lines.append("PERFORMANCE BY PRICE RANGE:")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Range':<15} {'Total':<8} {'Wins':<8} {'Losses':<8} {'Win Rate':<12} {'Avg P&L':<10}")
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

    # Top 20 profitable trades
    report_lines.append("TOP 20 PROFITABLE TRADES:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Signal Date':<12} {'Entry $':<10} {'Exit $':<10} {'P&L %':<10} {'Norm Price':<12} {'Force Idx':<12}")
    report_lines.append("-" * 80)

    for trade in profitable_trades[:20]:
        signal_date_str = trade['signal_date'].strftime('%m/%d/%Y')
        report_lines.append(
            f"{trade['ticker']:<8} "
            f"{signal_date_str:<12} "
            f"${trade['signal_price']:<9.2f} "
            f"${trade['exit_price']:<9.2f} "
            f"{trade['pnl_pct']:>8.2f}% "
            f"{trade['normalized_price']:>11.2f} "
            f"{trade['force_index']:>11.2f}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Top 20 losing trades
    report_lines.append("TOP 20 LOSING TRADES:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Signal Date':<12} {'Entry $':<10} {'Exit $':<10} {'P&L %':<10} {'Norm Price':<12} {'Force Idx':<12}")
    report_lines.append("-" * 80)

    for trade in losing_trades[-20:]:
        signal_date_str = trade['signal_date'].strftime('%m/%d/%Y')
        report_lines.append(
            f"{trade['ticker']:<8} "
            f"{signal_date_str:<12} "
            f"${trade['signal_price']:<9.2f} "
            f"${trade['exit_price']:<9.2f} "
            f"{trade['pnl_pct']:>8.2f}% "
            f"{trade['normalized_price']:>11.2f} "
            f"{trade['force_index']:>11.2f}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("LEGEND:")
    report_lines.append("  Ticker: Stock symbol")
    report_lines.append("  Signal Date: Date when maroon signal occurred")
    report_lines.append("  Entry $: Price at signal (buy price)")
    report_lines.append("  Exit $: Price after hold period (sell price)")
    report_lines.append("  P&L %: Profit/Loss percentage")
    report_lines.append("  Norm Price: Normalized price at signal (distance from BB basis)")
    report_lines.append("  Force Idx: Force Index value at signal (negative = bearish)")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w') as f:
        f.write(report_text)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")

if __name__ == "__main__":
    # Default: hold for 21 days (3 weeks)
    # You can change this value to test different hold periods
    run_backtest(hold_days=5)