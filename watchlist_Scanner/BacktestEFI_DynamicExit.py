import pandas as pd
import os
from datetime import datetime, timedelta
from EFI_Indicator import EFI_Indicator

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'efi_backtest_dynamic_exit_results.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def backtest_ticker_dynamic_exit(ticker_symbol, results_dir, max_hold_days=21):
    """
    Backtest EFI maroon signal strategy with dynamic exit

    Strategy:
    - BUY when Force Index color turns maroon (strong bearish)
    - EXIT when normalized price crosses down through 0 (price falls back to/below BB basis)
    - OR exit after max_hold_days if normalized price never crosses down
    - Calculate profit/loss

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files
        max_hold_days: Maximum days to hold if exit signal doesn't occur

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

        # Find all maroon signals and apply dynamic exit
        trades = []

        for i in range(len(df) - max_hold_days):
            fi_color = results['fi_color'].iloc[i]

            # Buy signal: Force Index turns maroon (strong bearish)
            if fi_color == 'maroon':
                signal_date = df.index[i]
                signal_price = df['Close'].iloc[i]
                normalized_price_entry = results['normalized_price'].iloc[i]
                force_index_entry = results['force_index'].iloc[i]

                # Look for exit signal in subsequent days
                exit_idx = None
                exit_reason = None

                # Check each day after entry for exit condition
                for j in range(i + 1, min(i + max_hold_days + 1, len(df))):
                    current_norm_price = results['normalized_price'].iloc[j]
                    previous_norm_price = results['normalized_price'].iloc[j - 1]

                    # EXIT CONDITION: Normalized price crosses down through 0
                    # (was above 0, now at or below 0)
                    if previous_norm_price > 0 and current_norm_price <= 0:
                        exit_idx = j
                        exit_reason = 'norm_price_cross_down'
                        break

                # If no exit signal found, exit at max hold period
                if exit_idx is None:
                    exit_idx = i + max_hold_days
                    exit_reason = 'max_hold_period'

                # Calculate exit stats
                if exit_idx < len(df):
                    exit_date = df.index[exit_idx]
                    exit_price = df['Close'].iloc[exit_idx]
                    days_held = (exit_date - signal_date).days

                    # Calculate P&L
                    pnl_pct = ((exit_price - signal_price) / signal_price) * 100

                    trades.append({
                        'ticker': ticker_symbol,
                        'signal_date': signal_date,
                        'signal_price': signal_price,
                        'exit_date': exit_date,
                        'exit_price': exit_price,
                        'pnl_pct': pnl_pct,
                        'normalized_price_entry': normalized_price_entry,
                        'force_index_entry': force_index_entry,
                        'days_held': days_held,
                        'exit_reason': exit_reason
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
    avg_days = sum(r['days_held'] for r in filtered) / total

    return {
        'range_name': range_name,
        'total': total,
        'profitable': profitable,
        'losing': losing,
        'avg_pnl': avg_pnl,
        'avg_days': avg_days,
        'win_rate': (profitable / total * 100) if total > 0 else 0
    }

def run_dynamic_exit_backtest(max_hold_days=21):
    """Run the dynamic exit EFI backtest analysis"""
    print("=" * 80)
    print("EFI MAROON SIGNAL BACKTEST - DYNAMIC EXIT")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("DYNAMIC EXIT STRATEGY:")
    print("  - BUY when Force Index color is MAROON (strong bearish)")
    print("  - EXIT when Normalized Price crosses DOWN through 0")
    print("    (price falls back to or below BB basis)")
    print(f"  - OR exit after {max_hold_days} days if no exit signal")
    print()
    print("RATIONALE:")
    print("  When normalized price crosses down through 0, it means the bounce")
    print("  is over and price is returning to the mean or going oversold again.")
    print("  This preserves gains and prevents giving back profits.")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Backtesting {len(tickers)} tickers with dynamic exit...")
    print()

    # Run backtest for all tickers
    all_trades = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers backtested...")

        trades = backtest_ticker_dynamic_exit(ticker, results_dir, max_hold_days)
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
    avg_days_held = sum(t['days_held'] for t in all_trades) / total_trades
    win_rate = (profitable / total_trades * 100) if total_trades > 0 else 0

    # Exit reason statistics
    dynamic_exits = sum(1 for t in all_trades if t['exit_reason'] == 'norm_price_cross_down')
    max_hold_exits = sum(1 for t in all_trades if t['exit_reason'] == 'max_hold_period')

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
    report_lines.append("EFI MAROON SIGNAL BACKTEST - DYNAMIC EXIT RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("STRATEGY:")
    report_lines.append("  - BUY when Force Index color is MAROON (strong bearish)")
    report_lines.append("  - EXIT when Normalized Price crosses DOWN through 0")
    report_lines.append(f"  - OR exit after {max_hold_days} days maximum")
    report_lines.append("")
    report_lines.append("OVERALL STATISTICS:")
    report_lines.append(f"  Total Trades: {total_trades}")
    report_lines.append(f"  Profitable: {profitable} ({win_rate:.1f}%)")
    report_lines.append(f"  Losing: {losing} ({(losing/total_trades*100):.1f}%)")
    report_lines.append(f"  Average P&L: {avg_pnl:+.2f}%")
    report_lines.append(f"  Average Days Held: {avg_days_held:.1f} days")
    report_lines.append("")
    report_lines.append("EXIT REASON BREAKDOWN:")
    report_lines.append(f"  Dynamic Exit (norm price crossed down): {dynamic_exits} ({(dynamic_exits/total_trades*100):.1f}%)")
    report_lines.append(f"  Max Hold Period Reached: {max_hold_exits} ({(max_hold_exits/total_trades*100):.1f}%)")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Add price range analysis
    if range_stats:
        report_lines.append("PERFORMANCE BY PRICE RANGE:")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Range':<15} {'Total':<8} {'Wins':<8} {'Losses':<8} {'Win Rate':<12} {'Avg P&L':<12} {'Avg Days':<10}")
        report_lines.append("-" * 80)

        for stats in range_stats:
            report_lines.append(
                f"{stats['range_name']:<15} "
                f"{stats['total']:<8} "
                f"{stats['profitable']:<8} "
                f"{stats['losing']:<8} "
                f"{stats['win_rate']:<11.1f}% "
                f"{stats['avg_pnl']:>10.2f}% "
                f"{stats['avg_days']:>9.1f}"
            )

        report_lines.append("=" * 80)
        report_lines.append("")

    # Top 20 profitable trades
    report_lines.append("TOP 20 PROFITABLE TRADES:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Entry Date':<12} {'Entry $':<10} {'Exit $':<10} {'P&L %':<10} {'Days':<6} {'Exit Reason':<20}")
    report_lines.append("-" * 80)

    for trade in profitable_trades[:20]:
        signal_date_str = trade['signal_date'].strftime('%m/%d/%Y')
        exit_reason_display = 'Norm Price Cross' if trade['exit_reason'] == 'norm_price_cross_down' else 'Max Hold'
        report_lines.append(
            f"{trade['ticker']:<8} "
            f"{signal_date_str:<12} "
            f"${trade['signal_price']:<9.2f} "
            f"${trade['exit_price']:<9.2f} "
            f"{trade['pnl_pct']:>8.2f}% "
            f"{trade['days_held']:<6} "
            f"{exit_reason_display:<20}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Top 20 losing trades
    report_lines.append("TOP 20 LOSING TRADES:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Entry Date':<12} {'Entry $':<10} {'Exit $':<10} {'P&L %':<10} {'Days':<6} {'Exit Reason':<20}")
    report_lines.append("-" * 80)

    for trade in losing_trades[-20:]:
        signal_date_str = trade['signal_date'].strftime('%m/%d/%Y')
        exit_reason_display = 'Norm Price Cross' if trade['exit_reason'] == 'norm_price_cross_down' else 'Max Hold'
        report_lines.append(
            f"{trade['ticker']:<8} "
            f"{signal_date_str:<12} "
            f"${trade['signal_price']:<9.2f} "
            f"${trade['exit_price']:<9.2f} "
            f"{trade['pnl_pct']:>8.2f}% "
            f"{trade['days_held']:<6} "
            f"{exit_reason_display:<20}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("ANALYSIS NOTES:")
    report_lines.append("  Dynamic exit based on normalized price crossing down through 0")
    report_lines.append("  allows us to capture the bounce and exit before giving back profits.")
    report_lines.append("  This should improve average P&L compared to fixed hold periods.")
    report_lines.append("")
    report_lines.append("LEGEND:")
    report_lines.append("  Ticker: Stock symbol")
    report_lines.append("  Entry Date: Date when maroon signal occurred")
    report_lines.append("  Entry $: Price at signal (buy price)")
    report_lines.append("  Exit $: Price at exit")
    report_lines.append("  P&L %: Profit/Loss percentage")
    report_lines.append("  Days: Number of days position was held")
    report_lines.append("  Exit Reason: Why the trade was closed")
    report_lines.append("    - Norm Price Cross: Normalized price crossed down through 0")
    report_lines.append("    - Max Hold: Maximum hold period reached")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w') as f:
        f.write(report_text)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")

if __name__ == "__main__":
    # Run backtest with dynamic exit
    # Max hold period is 21 days (3 weeks) if exit signal never occurs
    run_dynamic_exit_backtest(max_hold_days=21)