import pandas as pd
import numpy as np
import os
from datetime import datetime
from EFI_Indicator import EFI_Indicator
from PriceRangeZones import calculate_price_range_zones, determine_trend

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'triple_signal_maroon_backtest_results.txt')

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

def backtest_maroon_signal(ticker_symbol, results_dir, hold_days=63):
    """
    Backtest MAROON-only strategy with normalized price constraint

    Strategy:
    - BUY when all conditions are met:
      1. In Channel (price within 3-week range)
      2. Price in Buy Zone (0-35% of $1 range)
      3. EFI is MAROON (strongest oversold signal)
      4. Normalized Price < -0.5 (more than half range below zero - deep oversold)
      5. Uptrend confirmed
    - HOLD for specified trading days
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

        # Find all MAROON signal occurrences with normalized price constraint
        trades = []

        # Start at index 100 to ensure we have enough data for indicators
        # End at len(df) - hold_days to ensure we can hold for full period
        for i in range(100, len(df) - hold_days):
            # Check all conditions
            in_channel = check_in_channel(df, i, channel_period=3)
            fi_color = efi_results['fi_color'].iloc[i]
            normalized_price = efi_results['normalized_price'].iloc[i]
            price_zone = zones['price_zone'].iloc[i]
            current_trend = trend.iloc[i]

            condition_1_channel = in_channel
            condition_2_price_zone = price_zone == 'buy_zone'
            condition_3_maroon = fi_color == 'maroon'  # ONLY MAROON
            condition_4_normalized = normalized_price < -0.5  # More than half range below zero
            condition_5_trend = current_trend == 'uptrend'

            # If all conditions are met, record the trade
            if condition_1_channel and condition_2_price_zone and condition_3_maroon and condition_4_normalized and condition_5_trend:
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
                    'normalized_price': normalized_price,
                    'force_index': force_index,
                    'range_position_pct': range_position,
                    'range_floor': range_floor,
                    'range_ceiling': range_ceiling
                })

        return trades

    except Exception as e:
        print(f"Error backtesting {ticker_symbol}: {e}")
        return []

def analyze_by_normalized_range(results):
    """Analyze results by normalized price depth"""
    ranges = [
        (-1.0, -0.75, "Very Deep Oversold (-1.0 to -0.75)"),
        (-0.75, -0.5, "Deep Oversold (-0.75 to -0.5)"),
    ]

    analysis = []
    for min_norm, max_norm, range_name in ranges:
        filtered = [r for r in results if min_norm <= r['normalized_price'] < max_norm]

        if not filtered:
            continue

        total = len(filtered)
        profitable = sum(1 for r in filtered if r['pnl_pct'] > 0)
        avg_pnl = sum(r['pnl_pct'] for r in filtered) / total
        median_pnl = sorted([r['pnl_pct'] for r in filtered])[total // 2]
        best_pnl = max(r['pnl_pct'] for r in filtered)
        worst_pnl = min(r['pnl_pct'] for r in filtered)

        analysis.append({
            'range_name': range_name,
            'total': total,
            'profitable': profitable,
            'win_rate': (profitable / total * 100) if total > 0 else 0,
            'avg_pnl': avg_pnl,
            'median_pnl': median_pnl,
            'best_pnl': best_pnl,
            'worst_pnl': worst_pnl
        })

    return analysis

def run_maroon_backtest(hold_days=63):
    """
    Run the MAROON-only backtest analysis

    Args:
        hold_days: Number of trading days to hold (default 63 = business quarter)
    """
    print("=" * 80)
    print("MAROON SIGNAL BACKTEST - EXTREME OVERSOLD STRATEGY")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("STRATEGY:")
    print("  BUY when ALL conditions are met:")
    print("    1. In Channel (price within 3-week range)")
    print("    2. Price in Buy Zone (0-35% of $1 range)")
    print("    3. EFI is MAROON (strongest oversold signal)")
    print("    4. Normalized Price < -0.5 (deep oversold - bottom half of range)")
    print("    5. Uptrend confirmed")
    print()
    print(f"  HOLD for {hold_days} trading days (~1 business quarter)")
    print("  EXIT automatically after hold period")
    print()
    print("RATIONALE:")
    print("  MAROON signals represent extreme selling pressure and capitulation.")
    print("  Combined with normalized price < -0.5, we're catching the deepest")
    print("  oversold moments in uptrends - classic 'blood in the streets' setups.")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Backtesting {len(tickers)} tickers for MAROON signals...")
    print()

    # Run backtest for all tickers
    all_trades = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers backtested...")

        trades = backtest_maroon_signal(ticker, results_dir, hold_days)

        # Keep only the FIRST signal per ticker (most recent)
        if trades:
            all_trades.append(trades[0])  # Add only the first trade

    print()
    print(f"Backtest complete!")
    print(f"Found {len(all_trades)} MAROON signal setups to analyze")
    print()

    if not all_trades:
        print("No MAROON trades found with these strict criteria.")
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

    # Analyze by normalized price depth
    normalized_analysis = analyze_by_normalized_range(all_trades)

    # Sort trades by P&L
    all_trades.sort(key=lambda x: x['pnl_pct'], reverse=True)
    profitable_trades = [t for t in all_trades if t['pnl_pct'] > 0]
    losing_trades = [t for t in all_trades if t['pnl_pct'] <= 0]

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("MAROON SIGNAL BACKTEST - EXTREME OVERSOLD RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("STRATEGY:")
    report_lines.append("  Entry: When all 5 conditions are met (MAROON + deep oversold)")
    report_lines.append(f"  Hold: {hold_days} trading days (~1 business quarter)")
    report_lines.append("  Exit: Automatic after hold period")
    report_lines.append("")
    report_lines.append("KEY DIFFERENCE FROM STANDARD TRIPLE SIGNAL:")
    report_lines.append("  - ONLY MAROON signals (not orange)")
    report_lines.append("  - Normalized Price < -0.5 (deep in oversold territory)")
    report_lines.append("  - This catches EXTREME capitulation moments")
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

    # Portfolio simulation
    portfolio_size = 1000
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

    # Normalized price depth analysis
    if normalized_analysis:
        report_lines.append("PERFORMANCE BY OVERSOLD DEPTH:")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Normalized Range':<40} {'Total':<8} {'Wins':<7} {'Win%':<9} {'Avg%':<10} {'Med%':<10}")
        report_lines.append("-" * 80)

        for stats in normalized_analysis:
            report_lines.append(
                f"{stats['range_name']:<40} "
                f"{stats['total']:<8} "
                f"{stats['profitable']:<7} "
                f"{stats['win_rate']:<8.1f}% "
                f"{stats['avg_pnl']:>8.2f}% "
                f"{stats['median_pnl']:>8.2f}%"
            )

        report_lines.append("")
        report_lines.append("INSIGHT:")
        deepest = max(normalized_analysis, key=lambda x: x['avg_pnl']) if normalized_analysis else None
        if deepest:
            report_lines.append(f"  Best performance: {deepest['range_name']}")
            report_lines.append(f"  Average return: {deepest['avg_pnl']:+.2f}%")
            report_lines.append(f"  Win rate: {deepest['win_rate']:.1f}%")

        report_lines.append("=" * 80)
        report_lines.append("")

    # Top 20 profitable trades
    report_lines.append("TOP 20 MOST PROFITABLE MAROON TRADES:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Entry Date':<12} {'Entry $':<10} {'Exit $':<10} {'P&L %':<10} {'Norm Price':<11}")
    report_lines.append("-" * 80)

    for trade in profitable_trades[:20]:
        entry_date_str = trade['entry_date'].strftime('%m/%d/%Y')
        report_lines.append(
            f"{trade['ticker']:<8} "
            f"{entry_date_str:<12} "
            f"${trade['entry_price']:<9.2f} "
            f"${trade['exit_price']:<9.2f} "
            f"{trade['pnl_pct']:>8.2f}% "
            f"{trade['normalized_price']:>10.2f}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Top 20 losing trades
    report_lines.append("TOP 20 WORST MAROON TRADES:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Entry Date':<12} {'Entry $':<10} {'Exit $':<10} {'P&L %':<10} {'Norm Price':<11}")
    report_lines.append("-" * 80)

    for trade in losing_trades[-20:]:
        entry_date_str = trade['entry_date'].strftime('%m/%d/%Y')
        report_lines.append(
            f"{trade['ticker']:<8} "
            f"{entry_date_str:<12} "
            f"${trade['entry_price']:<9.2f} "
            f"${trade['exit_price']:<9.2f} "
            f"{trade['pnl_pct']:>8.2f}% "
            f"{trade['normalized_price']:>10.2f}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("ANALYSIS NOTES:")
    report_lines.append("  - Business Quarter = 63 trading days (~3 months)")
    report_lines.append("  - MAROON = Strongest EFI oversold signal (Force Index < -2.0)")
    report_lines.append("  - Normalized Price < -0.5 = Deep oversold (bottom half of range)")
    report_lines.append("  - This catches extreme selling exhaustion in uptrends")
    report_lines.append("  - Each signal treated as independent trade opportunity")
    report_lines.append("  - Does not account for: slippage, commissions, or taxes")
    report_lines.append("")
    report_lines.append("KEY INSIGHTS:")
    if win_rate > 50:
        report_lines.append(f"  ✓ Win rate of {win_rate:.1f}% shows strong edge with MAROON signals")
    else:
        report_lines.append(f"  ⚠ Win rate of {win_rate:.1f}% - consider additional filters")

    if avg_pnl > 0:
        report_lines.append(f"  ✓ Positive average return of {avg_pnl:.2f}% validates deep oversold entry")
    else:
        report_lines.append(f"  ⚠ Negative average return of {avg_pnl:.2f}%")

    if median_pnl > avg_pnl:
        report_lines.append(f"  ⚠ Median > Average suggests some large losers pulling down average")
    elif avg_pnl > median_pnl:
        report_lines.append(f"  ✓ Average > Median suggests some large winners boosting performance")

    report_lines.append("")
    report_lines.append("COMPARISON TO STANDARD TRIPLE SIGNAL:")
    report_lines.append("  Standard (MAROON + ORANGE): More signals, less selective")
    report_lines.append("  MAROON-only with deep oversold: Fewer signals, higher conviction")
    report_lines.append("  Use this data to determine if extreme selectivity improves returns")
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
    run_maroon_backtest(hold_days=63)