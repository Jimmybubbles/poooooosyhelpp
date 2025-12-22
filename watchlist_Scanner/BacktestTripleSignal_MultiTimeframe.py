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
output_file = os.path.join(buylist_dir, 'triple_signal_multi_timeframe_backtest.txt')

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

def backtest_triple_signal_multi_timeframe(ticker_symbol, results_dir, hold_periods):
    """
    Backtest Triple Signal strategy for multiple hold periods

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files
        hold_periods: List of tuples (days, name) for different hold periods

    Returns:
        Dict with results for each hold period
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker_symbol}.csv")

        if not os.path.exists(csv_file):
            return {}

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

        # Need enough data for longest hold period
        max_hold_days = max(days for days, _ in hold_periods)

        if len(df) < 100 + max_hold_days:
            return {}

        # Calculate indicators for all data
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)
        zones = calculate_price_range_zones(df, lookback_period=100)
        trend = determine_trend(df, lookback_period=50)

        # Store results for each hold period
        results_by_period = {name: [] for _, name in hold_periods}

        # Find all triple signal occurrences
        for i in range(100, len(df) - max_hold_days):
            # Check all 4 conditions
            in_channel = check_in_channel(df, i, channel_period=3)
            fi_color = efi_results['fi_color'].iloc[i]
            price_zone = zones['price_zone'].iloc[i]
            current_trend = trend.iloc[i]

            condition_1_channel = in_channel
            condition_2_price_zone = price_zone == 'buy_zone'
            condition_3_efi = fi_color in ['maroon', 'orange']
            condition_4_trend = current_trend == 'uptrend'

            # If all conditions are met, record trades for all hold periods
            if condition_1_channel and condition_2_price_zone and condition_3_efi and condition_4_trend:
                entry_date = df.index[i]
                entry_price = df['Close'].iloc[i]

                # Test each hold period
                for hold_days, period_name in hold_periods:
                    # Make sure we have enough data
                    if i + hold_days >= len(df):
                        continue

                    exit_idx = i + hold_days
                    exit_date = df.index[exit_idx]
                    exit_price = df['Close'].iloc[exit_idx]

                    # Calculate P&L
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                    pnl_dollars = exit_price - entry_price

                    results_by_period[period_name].append({
                        'ticker': ticker_symbol,
                        'entry_date': entry_date,
                        'entry_price': entry_price,
                        'exit_date': exit_date,
                        'exit_price': exit_price,
                        'pnl_pct': pnl_pct,
                        'pnl_dollars': pnl_dollars,
                        'hold_days': hold_days,
                        'fi_color': fi_color
                    })

        return results_by_period

    except Exception as e:
        print(f"Error backtesting {ticker_symbol}: {e}")
        return {}

def calculate_statistics(trades):
    """Calculate statistics for a list of trades"""
    if not trades:
        return None

    total = len(trades)
    profitable = sum(1 for t in trades if t['pnl_pct'] > 0)
    losing = sum(1 for t in trades if t['pnl_pct'] <= 0)

    avg_pnl = sum(t['pnl_pct'] for t in trades) / total
    median_pnl = sorted([t['pnl_pct'] for t in trades])[total // 2]

    best_pnl = max(t['pnl_pct'] for t in trades)
    worst_pnl = min(t['pnl_pct'] for t in trades)

    win_rate = (profitable / total * 100) if total > 0 else 0

    # Calculate average winner and average loser
    winners = [t['pnl_pct'] for t in trades if t['pnl_pct'] > 0]
    losers = [t['pnl_pct'] for t in trades if t['pnl_pct'] <= 0]

    avg_winner = sum(winners) / len(winners) if winners else 0
    avg_loser = sum(losers) / len(losers) if losers else 0

    # Profit factor
    total_profit = sum(winners) if winners else 0
    total_loss = abs(sum(losers)) if losers else 0
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

    return {
        'total': total,
        'profitable': profitable,
        'losing': losing,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'median_pnl': median_pnl,
        'best_pnl': best_pnl,
        'worst_pnl': worst_pnl,
        'avg_winner': avg_winner,
        'avg_loser': avg_loser,
        'profit_factor': profit_factor
    }

def run_multi_timeframe_backtest():
    """
    Run the Triple Signal backtest across multiple timeframes
    """
    # Define hold periods (trading days, name)
    hold_periods = [
        (5, '1_week'),
        (21, '1_month'),
        (63, '3_months'),
        (126, '6_months'),
        (252, '1_year')
    ]

    print("=" * 80)
    print("TRIPLE SIGNAL MULTI-TIMEFRAME BACKTEST")
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
    print("HOLD PERIODS TESTED:")
    print("  - 1 Week (5 trading days)")
    print("  - 1 Month (21 trading days)")
    print("  - 3 Months (63 trading days)")
    print("  - 6 Months (126 trading days)")
    print("  - 1 Year (252 trading days)")
    print()
    print("This will show you which timeframe performs best for this strategy.")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Backtesting {len(tickers)} tickers across {len(hold_periods)} timeframes...")
    print()

    # Store all results by period
    all_results = {name: [] for _, name in hold_periods}

    # Run backtest for all tickers
    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers backtested...")

        results = backtest_triple_signal_multi_timeframe(ticker, results_dir, hold_periods)

        # Aggregate results
        for period_name in all_results.keys():
            if period_name in results:
                all_results[period_name].extend(results[period_name])

    print()
    print(f"Backtest complete!")
    print()

    # Calculate statistics for each period
    stats_by_period = {}
    for period_name, trades in all_results.items():
        stats = calculate_statistics(trades)
        if stats:
            stats_by_period[period_name] = stats
            print(f"{period_name.replace('_', ' ').title()}: {stats['total']} trades found")

    print()

    # Generate comprehensive report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("TRIPLE SIGNAL MULTI-TIMEFRAME BACKTEST RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("STRATEGY:")
    report_lines.append("  Entry: When all 4 Triple Signal conditions are met")
    report_lines.append("  Exit: Automatic after specified hold period")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("PERFORMANCE COMPARISON ACROSS TIMEFRAMES")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Create comparison table
    report_lines.append(f"{'Period':<12} {'Total':<8} {'Win%':<10} {'Avg%':<10} {'Med%':<10} {'Best%':<10} {'Worst%':<10} {'PF':<8}")
    report_lines.append("-" * 80)

    period_order = ['1_week', '1_month', '3_months', '6_months', '1_year']
    period_display = {
        '1_week': '1 Week',
        '1_month': '1 Month',
        '3_months': '3 Months',
        '6_months': '6 Months',
        '1_year': '1 Year'
    }

    for period_name in period_order:
        if period_name in stats_by_period:
            stats = stats_by_period[period_name]
            pf_display = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "∞"

            report_lines.append(
                f"{period_display[period_name]:<12} "
                f"{stats['total']:<8} "
                f"{stats['win_rate']:<9.1f}% "
                f"{stats['avg_pnl']:>8.2f}% "
                f"{stats['median_pnl']:>8.2f}% "
                f"{stats['best_pnl']:>8.2f}% "
                f"{stats['worst_pnl']:>8.2f}% "
                f"{pf_display:<8}"
            )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Detailed breakdown for each period
    for period_name in period_order:
        if period_name not in stats_by_period:
            continue

        stats = stats_by_period[period_name]
        trades = all_results[period_name]

        report_lines.append(f"{period_display[period_name].upper()} - DETAILED ANALYSIS")
        report_lines.append("-" * 80)
        report_lines.append(f"  Total Trades: {stats['total']}")
        report_lines.append(f"  Profitable: {stats['profitable']} ({stats['win_rate']:.1f}%)")
        report_lines.append(f"  Losing: {stats['losing']} ({(stats['losing']/stats['total']*100):.1f}%)")
        report_lines.append("")
        report_lines.append(f"  Average P&L: {stats['avg_pnl']:+.2f}%")
        report_lines.append(f"  Median P&L: {stats['median_pnl']:+.2f}%")
        report_lines.append(f"  Average Winner: {stats['avg_winner']:+.2f}%")
        report_lines.append(f"  Average Loser: {stats['avg_loser']:+.2f}%")
        report_lines.append("")
        report_lines.append(f"  Best Trade: {stats['best_pnl']:+.2f}%")
        report_lines.append(f"  Worst Trade: {stats['worst_pnl']:+.2f}%")

        pf_display = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "∞"
        report_lines.append(f"  Profit Factor: {pf_display}")
        report_lines.append("")

        # Portfolio simulation ($1000 per trade)
        portfolio_size = 1000
        total_invested = portfolio_size * stats['total']
        total_returns = sum((t['pnl_pct'] / 100) * portfolio_size for t in trades)
        portfolio_return_pct = (total_returns / total_invested) * 100

        report_lines.append(f"  Portfolio Simulation ($1,000 per signal):")
        report_lines.append(f"    Total Invested: ${total_invested:,.2f}")
        report_lines.append(f"    Total Returns: ${total_returns:+,.2f}")
        report_lines.append(f"    Portfolio Return: {portfolio_return_pct:+.2f}%")
        report_lines.append("")

        # Top 5 best trades for this period
        sorted_trades = sorted(trades, key=lambda x: x['pnl_pct'], reverse=True)
        report_lines.append(f"  Top 5 Best Trades:")
        for trade in sorted_trades[:5]:
            report_lines.append(
                f"    {trade['ticker']:<8} "
                f"{trade['entry_date'].strftime('%m/%d/%Y'):<12} "
                f"${trade['entry_price']:.2f} → ${trade['exit_price']:.2f} "
                f"({trade['pnl_pct']:+.2f}%)"
            )
        report_lines.append("")

        # Top 5 worst trades for this period
        report_lines.append(f"  Top 5 Worst Trades:")
        for trade in sorted_trades[-5:]:
            report_lines.append(
                f"    {trade['ticker']:<8} "
                f"{trade['entry_date'].strftime('%m/%d/%Y'):<12} "
                f"${trade['entry_price']:.2f} → ${trade['exit_price']:.2f} "
                f"({trade['pnl_pct']:+.2f}%)"
            )
        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # Recommendations
    report_lines.append("KEY INSIGHTS & RECOMMENDATIONS:")
    report_lines.append("-" * 80)

    # Find best performing period by average P&L
    if stats_by_period:
        best_period = max(stats_by_period.items(), key=lambda x: x[1]['avg_pnl'])
        best_win_rate = max(stats_by_period.items(), key=lambda x: x[1]['win_rate'])
        best_profit_factor = max(stats_by_period.items(),
                                key=lambda x: x[1]['profit_factor'] if x[1]['profit_factor'] != float('inf') else 0)

        report_lines.append(f"  Best Average Return: {period_display[best_period[0]]} ({best_period[1]['avg_pnl']:+.2f}%)")
        report_lines.append(f"  Best Win Rate: {period_display[best_win_rate[0]]} ({best_win_rate[1]['win_rate']:.1f}%)")
        report_lines.append(f"  Best Profit Factor: {period_display[best_profit_factor[0]]} ({best_profit_factor[1]['profit_factor']:.2f})")
        report_lines.append("")

        report_lines.append("  Analysis:")
        if best_period[1]['avg_pnl'] > 0:
            report_lines.append(f"    ✓ The strategy shows positive returns across timeframes")
            report_lines.append(f"    ✓ {period_display[best_period[0]]} appears to be the optimal hold period")
        else:
            report_lines.append(f"    ⚠ Consider adjusting entry criteria or timeframes")

        # Check if longer holds are better
        if '1_year' in stats_by_period and '1_week' in stats_by_period:
            year_vs_week = stats_by_period['1_year']['avg_pnl'] - stats_by_period['1_week']['avg_pnl']
            if year_vs_week > 5:
                report_lines.append(f"    → Longer holds significantly outperform (trend-following strategy)")
            elif year_vs_week < -5:
                report_lines.append(f"    → Shorter holds significantly outperform (mean-reversion strategy)")

    report_lines.append("")
    report_lines.append("NOTES:")
    report_lines.append("  - PF = Profit Factor (Total Profits / Total Losses)")
    report_lines.append("  - Win% = Percentage of profitable trades")
    report_lines.append("  - Med% = Median return (less affected by outliers)")
    report_lines.append("  - Does not account for: slippage, commissions, or taxes")
    report_lines.append("  - Past performance does not guarantee future results")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")

if __name__ == "__main__":
    run_multi_timeframe_backtest()