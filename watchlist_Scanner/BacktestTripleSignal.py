import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from EFI_Indicator import EFI_Indicator
from PriceRangeZones import calculate_price_range_zones, determine_trend

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'triple_signal_backtest_results.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def check_in_channel(df, idx, channel_period=3):
    """
    Check if price is trading within a defined channel at a specific index

    Args:
        df: DataFrame with OHLCV data
        idx: Index to check
        channel_period: Number of weeks to look back (default 3)

    Returns:
        Boolean - True if price is in channel
    """
    lookback_days = channel_period * 5

    if idx < lookback_days:
        return False

    # Get current close and previous highs/lows
    current_close = df['Close'].iloc[idx]
    previous_highs = df['High'].iloc[idx-lookback_days:idx]
    previous_lows = df['Low'].iloc[idx-lookback_days:idx]

    channel_high = previous_highs.max()
    channel_low = previous_lows.min()

    # Check if current price is within the channel
    if channel_low <= current_close <= channel_high:
        return True

    return False

def backtest_triple_signal(ticker_symbol, results_dir, hold_days=63):
    """
    Backtest Triple Signal strategy for a single ticker

    Strategy:
    - BUY when all 4 conditions are met:
      1. In Channel (price within 3-week range)
      2. Price in Buy Zone (0-35% of $1 range)
      3. EFI is maroon or orange (oversold)
      4. Uptrend confirmed
    - HOLD for a business quarter (63 trading days)
    - Calculate profit/loss

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files
        hold_days: Number of trading days to hold (default 63 = ~1 quarter)

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

        if len(df) < 100 + hold_days:
            return []

        # Calculate indicators for all data
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)
        zones = calculate_price_range_zones(df, lookback_period=100)
        trend = determine_trend(df, lookback_period=50)

        # Find all triple signal occurrences
        trades = []

        # Start at index 100 to ensure we have enough data for indicators
        # End at len(df) - hold_days to ensure we can hold for full period
        for i in range(100, len(df) - hold_days):
            # Check all 4 conditions
            in_channel = check_in_channel(df, i, channel_period=3)
            fi_color = efi_results['fi_color'].iloc[i]
            price_zone = zones['price_zone'].iloc[i]
            current_trend = trend.iloc[i]

            condition_1_channel = in_channel
            condition_2_price_zone = price_zone == 'buy_zone'
            condition_3_efi = fi_color in ['maroon', 'orange']
            condition_4_trend = current_trend == 'uptrend'

            # If all conditions are met, record the trade
            if condition_1_channel and condition_2_price_zone and condition_3_efi and condition_4_trend:
                entry_date = df.index[i]
                entry_price = df['Close'].iloc[i]

                # Calculate exit (hold_days later)
                exit_idx = i + hold_days
                exit_date = df.index[exit_idx]
                exit_price = df['Close'].iloc[exit_idx]

                # Calculate P&L
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                pnl_dollars = exit_price - entry_price

                # Get signal details
                normalized_price = efi_results['normalized_price'].iloc[i]
                force_index = efi_results['force_index'].iloc[i]
                range_position = zones['range_position_pct'].iloc[i]
                range_floor = zones['range_floor'].iloc[i]
                range_ceiling = zones['range_ceiling'].iloc[i]

                trades.append({
                    'ticker': ticker_symbol,
                    'entry_date': entry_date,
                    'entry_price': entry_price,
                    'exit_date': exit_date,
                    'exit_price': exit_price,
                    'pnl_pct': pnl_pct,
                    'pnl_dollars': pnl_dollars,
                    'hold_days': hold_days,
                    'fi_color': fi_color,
                    'force_index': force_index,
                    'normalized_price': normalized_price,
                    'range_position_pct': range_position,
                    'range_floor': range_floor,
                    'range_ceiling': range_ceiling
                })

        return trades

    except Exception as e:
        print(f"Error backtesting {ticker_symbol}: {e}")
        return []

def analyze_price_range(results, min_price, max_price, range_name):
    """Analyze results for a specific price range"""
    filtered = [r for r in results if min_price <= r['entry_price'] < max_price]

    if not filtered:
        return None

    total = len(filtered)
    profitable = sum(1 for r in filtered if r['pnl_pct'] > 0)
    losing = sum(1 for r in filtered if r['pnl_pct'] <= 0)
    avg_pnl = sum(r['pnl_pct'] for r in filtered) / total
    median_pnl = sorted([r['pnl_pct'] for r in filtered])[total // 2]
    best_pnl = max(r['pnl_pct'] for r in filtered)
    worst_pnl = min(r['pnl_pct'] for r in filtered)

    return {
        'range_name': range_name,
        'total': total,
        'profitable': profitable,
        'losing': losing,
        'avg_pnl': avg_pnl,
        'median_pnl': median_pnl,
        'best_pnl': best_pnl,
        'worst_pnl': worst_pnl,
        'win_rate': (profitable / total * 100) if total > 0 else 0
    }

def run_triple_signal_backtest(hold_days=63):
    """
    Run the Triple Signal backtest analysis

    Args:
        hold_days: Number of trading days to hold (default 63 = business quarter)
    """
    print("=" * 80)
    print("TRIPLE SIGNAL BACKTEST - BUSINESS QUARTER HOLD")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("STRATEGY:")
    print("  BUY when ALL 4 conditions are met:")
    print("    1. In Channel (price within 3-week range)")
    print("    2. Price in Buy Zone (0-35% of $1 range)")
    print("    3. EFI is maroon or orange (oversold)")
    print("    4. Uptrend confirmed")
    print()
    print(f"  HOLD for {hold_days} trading days (~1 business quarter)")
    print("  EXIT automatically after hold period")
    print()
    print("RATIONALE:")
    print("  This tests whether the Triple Signal setup provides profitable")
    print("  entries for swing trades held over a business quarter.")
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

        trades = backtest_triple_signal(ticker, results_dir, hold_days)
        all_trades.extend(trades)

    print()
    print(f"Backtest complete!")
    print(f"Found {len(all_trades)} total Triple Signal setups to analyze")
    print()

    if not all_trades:
        print("No trades found.")
        return

    # Calculate overall statistics
    total_trades = len(all_trades)
    profitable = sum(1 for t in all_trades if t['pnl_pct'] > 0)
    losing = sum(1 for t in all_trades if t['pnl_pct'] <= 0)
    avg_pnl = sum(t['pnl_pct'] for t in all_trades) / total_trades
    median_pnl = sorted([t['pnl_pct'] for t in all_trades])[total_trades // 2]
    total_pnl_dollars = sum(t['pnl_dollars'] for t in all_trades)
    avg_pnl_dollars = total_pnl_dollars / total_trades
    win_rate = (profitable / total_trades * 100) if total_trades > 0 else 0

    # Best and worst trades
    best_trade = max(all_trades, key=lambda x: x['pnl_pct'])
    worst_trade = min(all_trades, key=lambda x: x['pnl_pct'])

    # Analyze by price ranges
    price_ranges = [
        (0, 1, "$0-$1"),
        (1, 2, "$1-$2"),
        (2, 3, "$2-$3"),
        (3, 4, "$3-$4"),
        (4, 5, "$4-$5"),
        (5, 10, "$5-$10"),
        (10, 20, "$10-$20"),
        (20, 50, "$20-$50"),
        (50, 100, "$50-$100"),
        (100, float('inf'), "$100+")
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
    report_lines.append("TRIPLE SIGNAL BACKTEST - BUSINESS QUARTER RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("STRATEGY:")
    report_lines.append("  Entry: When all 4 Triple Signal conditions are met")
    report_lines.append(f"  Hold: {hold_days} trading days (~1 business quarter)")
    report_lines.append("  Exit: Automatic after hold period")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("OVERALL PERFORMANCE")
    report_lines.append("=" * 80)
    report_lines.append(f"  Total Trades: {total_trades}")
    report_lines.append(f"  Profitable: {profitable} ({win_rate:.1f}%)")
    report_lines.append(f"  Losing: {losing} ({(losing/total_trades*100):.1f}%)")
    report_lines.append("")
    report_lines.append(f"  Average P&L: {avg_pnl:+.2f}%")
    report_lines.append(f"  Median P&L: {median_pnl:+.2f}%")
    report_lines.append(f"  Average P&L ($): ${avg_pnl_dollars:+.2f}")
    report_lines.append(f"  Total P&L ($): ${total_pnl_dollars:+,.2f}")
    report_lines.append("")
    report_lines.append(f"  Best Trade: {best_trade['ticker']} ({best_trade['pnl_pct']:+.2f}%)")
    report_lines.append(f"  Worst Trade: {worst_trade['ticker']} ({worst_trade['pnl_pct']:+.2f}%)")
    report_lines.append("")

    # Portfolio simulation (if you bought $1000 of each signal)
    portfolio_size = 1000  # $1000 per trade
    total_invested = portfolio_size * total_trades
    total_returns = sum((t['pnl_pct'] / 100) * portfolio_size for t in all_trades)
    portfolio_return_pct = (total_returns / total_invested) * 100

    report_lines.append("PORTFOLIO SIMULATION ($1,000 per signal):")
    report_lines.append(f"  Total Invested: ${total_invested:,.2f}")
    report_lines.append(f"  Total Returns: ${total_returns:+,.2f}")
    report_lines.append(f"  Portfolio Return: {portfolio_return_pct:+.2f}%")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Add price range analysis
    if range_stats:
        report_lines.append("PERFORMANCE BY PRICE RANGE:")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Range':<12} {'Total':<7} {'Wins':<7} {'Losses':<7} {'Win%':<9} {'Avg%':<10} {'Med%':<10} {'Best%':<10} {'Worst%':<10}")
        report_lines.append("-" * 80)

        for stats in range_stats:
            report_lines.append(
                f"{stats['range_name']:<12} "
                f"{stats['total']:<7} "
                f"{stats['profitable']:<7} "
                f"{stats['losing']:<7} "
                f"{stats['win_rate']:<8.1f}% "
                f"{stats['avg_pnl']:>8.2f}% "
                f"{stats['median_pnl']:>8.2f}% "
                f"{stats['best_pnl']:>8.2f}% "
                f"{stats['worst_pnl']:>8.2f}%"
            )

        report_lines.append("=" * 80)
        report_lines.append("")

    # Top 20 profitable trades
    report_lines.append("TOP 20 MOST PROFITABLE TRADES:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Entry Date':<12} {'Entry $':<10} {'Exit $':<10} {'P&L %':<10} {'P&L $':<10} {'EFI':<8}")
    report_lines.append("-" * 80)

    for trade in profitable_trades[:20]:
        entry_date_str = trade['entry_date'].strftime('%m/%d/%Y')
        report_lines.append(
            f"{trade['ticker']:<8} "
            f"{entry_date_str:<12} "
            f"${trade['entry_price']:<9.2f} "
            f"${trade['exit_price']:<9.2f} "
            f"{trade['pnl_pct']:>8.2f}% "
            f"${trade['pnl_dollars']:>8.2f} "
            f"{trade['fi_color'].upper():<8}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Top 20 losing trades
    report_lines.append("TOP 20 WORST TRADES:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Entry Date':<12} {'Entry $':<10} {'Exit $':<10} {'P&L %':<10} {'P&L $':<10} {'EFI':<8}")
    report_lines.append("-" * 80)

    for trade in losing_trades[-20:]:
        entry_date_str = trade['entry_date'].strftime('%m/%d/%Y')
        report_lines.append(
            f"{trade['ticker']:<8} "
            f"{entry_date_str:<12} "
            f"${trade['entry_price']:<9.2f} "
            f"${trade['exit_price']:<9.2f} "
            f"{trade['pnl_pct']:>8.2f}% "
            f"${trade['pnl_dollars']:>8.2f} "
            f"{trade['fi_color'].upper():<8}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("ANALYSIS NOTES:")
    report_lines.append("  - Business Quarter = 63 trading days (~3 months)")
    report_lines.append("  - Each signal treated as independent trade opportunity")
    report_lines.append("  - No position sizing or risk management applied")
    report_lines.append("  - Does not account for: slippage, commissions, or taxes")
    report_lines.append("  - Past performance does not guarantee future results")
    report_lines.append("")
    report_lines.append("KEY INSIGHTS:")
    if win_rate > 50:
        report_lines.append(f"  ✓ Win rate of {win_rate:.1f}% suggests edge in the strategy")
    else:
        report_lines.append(f"  ⚠ Win rate of {win_rate:.1f}% is below 50%")

    if avg_pnl > 0:
        report_lines.append(f"  ✓ Positive average return of {avg_pnl:.2f}%")
    else:
        report_lines.append(f"  ⚠ Negative average return of {avg_pnl:.2f}%")

    if median_pnl > avg_pnl:
        report_lines.append(f"  ⚠ Median > Average suggests outliers pulling down average")

    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")

if __name__ == "__main__":
    # Run backtest with business quarter hold period (63 trading days)
    # You can change this value to test different hold periods
    run_triple_signal_backtest(hold_days=63)