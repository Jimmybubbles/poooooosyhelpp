"""
RANGE LEVEL BACKTEST
====================
Backtests the theory of:
- Entry: Price touches 25% level of range
- Target: 75% level of same range (50% of range profit)
- Stop: 0% level (25% of range loss)
- R:R = 1:2

Tests historical data to see win rate and expectancy.
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime
import sys

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
output_file = os.path.join(script_dir, 'buylist', 'range_level_backtest_results.txt')


def get_range_info(price):
    """Determine which range a price is in and calculate quarter levels."""
    if price <= 0:
        return None

    if price < 10:
        range_size = 1.0
        range_low = int(price)
        if range_low == 0:
            range_low = 0
    elif price < 100:
        range_size = 10.0
        range_low = int(price / 10) * 10
    elif price < 500:
        range_size = 50.0
        range_low = int(price / 50) * 50
    else:
        range_size = 100.0
        range_low = int(price / 100) * 100

    range_high = range_low + range_size

    levels = {
        'L0': range_low,
        'L25': range_low + (range_size * 0.25),
        'L50': range_low + (range_size * 0.50),
        'L75': range_low + (range_size * 0.75),
        'L100': range_high
    }

    return {
        'range_low': range_low,
        'range_high': range_high,
        'range_size': range_size,
        'levels': levels
    }


def backtest_stock(ticker, results_dir, lookback_days=252):
    """
    Backtest the 25% -> 75% strategy on a single stock.

    Entry: When price crosses DOWN to touch the 25% level
    Exit: Either hits 75% (win) or 0% (loss)

    Returns list of trades with results.
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker}.csv")

        if not os.path.exists(csv_file):
            return []

        # Read CSV
        df = pd.read_csv(csv_file, skiprows=[1, 2])

        if 'Price' in df.columns:
            df.rename(columns={'Price': 'Date'}, inplace=True)

        required_cols = ['Date', 'Open', 'High', 'Low', 'Close']
        if not all(col in df.columns for col in required_cols):
            return []

        df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
        df = df.dropna(subset=['Date'])
        df = df.sort_values('Date')
        df.set_index('Date', inplace=True)

        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna()

        # Use last N days for backtest
        if len(df) > lookback_days:
            df = df.iloc[-lookback_days:]

        if len(df) < 20:
            return []

        trades = []
        in_trade = False
        entry_price = 0
        entry_date = None
        entry_level_25 = 0
        target_level_75 = 0
        stop_level_0 = 0
        current_range_low = 0

        for i in range(1, len(df)):
            current_date = df.index[i]
            current_low = df['Low'].iloc[i]
            current_high = df['High'].iloc[i]
            current_close = df['Close'].iloc[i]
            prev_close = df['Close'].iloc[i-1]

            if not in_trade:
                # Look for entry - price touches 25% level from above
                range_info = get_range_info(prev_close)
                if range_info is None:
                    continue

                level_25 = range_info['levels']['L25']
                level_0 = range_info['levels']['L0']
                level_75 = range_info['levels']['L75']

                # Check if price was above 25% and now touches or crosses it
                # Entry signal: Low reaches down to 25% level
                if prev_close > level_25 and current_low <= level_25 and current_low > level_0:
                    # Enter trade at 25% level
                    in_trade = True
                    entry_price = level_25
                    entry_date = current_date
                    entry_level_25 = level_25
                    target_level_75 = level_75
                    stop_level_0 = level_0
                    current_range_low = range_info['range_low']

            else:
                # Check for exit
                # Win: High reaches 75% target
                # Loss: Low reaches 0% stop

                hit_target = current_high >= target_level_75
                hit_stop = current_low <= stop_level_0

                if hit_target and hit_stop:
                    # Both hit same day - assume stop hit first if open was closer to stop
                    open_price = df['Open'].iloc[i]
                    if abs(open_price - stop_level_0) < abs(open_price - target_level_75):
                        hit_target = False
                    else:
                        hit_stop = False

                if hit_target:
                    # WIN - hit 75% target
                    exit_price = target_level_75
                    profit = exit_price - entry_price
                    profit_pct = (profit / entry_price) * 100

                    trades.append({
                        'ticker': ticker,
                        'entry_date': entry_date,
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'target': target_level_75,
                        'stop': stop_level_0,
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'result': 'WIN',
                        'range': f"${current_range_low:.0f}-${current_range_low + (target_level_75 - entry_level_25) * 2:.0f}",
                        'days_held': (current_date - entry_date).days
                    })
                    in_trade = False

                elif hit_stop:
                    # LOSS - hit 0% stop
                    exit_price = stop_level_0
                    profit = exit_price - entry_price
                    profit_pct = (profit / entry_price) * 100

                    trades.append({
                        'ticker': ticker,
                        'entry_date': entry_date,
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'target': target_level_75,
                        'stop': stop_level_0,
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'result': 'LOSS',
                        'range': f"${current_range_low:.0f}-${current_range_low + (target_level_75 - entry_level_25) * 2:.0f}",
                        'days_held': (current_date - entry_date).days
                    })
                    in_trade = False

        return trades

    except Exception as e:
        return []


def run_backtest(lookback_days=252, min_price=0.50, max_price=500):
    """
    Run backtest across all stocks.

    Args:
        lookback_days: Number of trading days to backtest (252 = 1 year)
        min_price: Minimum stock price to include
        max_price: Maximum stock price to include
    """
    print("=" * 100)
    print("RANGE LEVEL BACKTEST")
    print("=" * 100)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("STRATEGY:")
    print("  Entry: Price touches 25% level of range (from above)")
    print("  Target: 75% level (same range)")
    print("  Stop: 0% level (bottom of range)")
    print("  R:R = 1:2 (risk 25% of range, reward 50% of range)")
    print()
    print(f"PARAMETERS:")
    print(f"  Lookback: {lookback_days} trading days (~{lookback_days//252} year(s))")
    print(f"  Price range: ${min_price:.2f} - ${max_price:.2f}")
    print()
    print("=" * 100)
    print()

    # Get ticker list
    csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
    tickers = [f[:-4] for f in csv_files]

    print(f"Backtesting {len(tickers)} stocks...")
    print()

    all_trades = []
    stocks_with_trades = 0

    for i, ticker in enumerate(tickers):
        if (i + 1) % 500 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} stocks analyzed...")

        trades = backtest_stock(ticker, results_dir, lookback_days)

        # Filter by price
        trades = [t for t in trades if min_price <= t['entry_price'] <= max_price]

        if trades:
            stocks_with_trades += 1
            all_trades.extend(trades)

    print()
    print(f"Backtest complete!")
    print(f"Stocks with trades: {stocks_with_trades}")
    print(f"Total trades: {len(all_trades)}")
    print()

    if not all_trades:
        print("No trades found in backtest period.")
        return

    # Calculate statistics
    wins = [t for t in all_trades if t['result'] == 'WIN']
    losses = [t for t in all_trades if t['result'] == 'LOSS']

    total_trades = len(all_trades)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0

    avg_win = np.mean([t['profit_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['profit_pct'] for t in losses]) if losses else 0

    total_profit_pct = sum([t['profit_pct'] for t in all_trades])
    avg_profit_pct = total_profit_pct / total_trades if total_trades > 0 else 0

    # Expectancy = (Win% * Avg Win) + (Loss% * Avg Loss)
    expectancy = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)

    # Profit factor = Gross Profit / Gross Loss
    gross_profit = sum([t['profit_pct'] for t in wins]) if wins else 0
    gross_loss = abs(sum([t['profit_pct'] for t in losses])) if losses else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    avg_days_held = np.mean([t['days_held'] for t in all_trades])
    avg_days_win = np.mean([t['days_held'] for t in wins]) if wins else 0
    avg_days_loss = np.mean([t['days_held'] for t in losses]) if losses else 0

    # Generate report
    report_lines = []
    report_lines.append("=" * 100)
    report_lines.append("RANGE LEVEL BACKTEST - RESULTS")
    report_lines.append("=" * 100)
    report_lines.append(f"Backtest Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Lookback Period: {lookback_days} trading days")
    report_lines.append("")
    report_lines.append("STRATEGY:")
    report_lines.append("  Entry: Price touches 25% level of range")
    report_lines.append("  Target: 75% level (+50% of range)")
    report_lines.append("  Stop: 0% level (-25% of range)")
    report_lines.append("  Theoretical R:R = 1:2")
    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    report_lines.append("OVERALL STATISTICS:")
    report_lines.append("-" * 100)
    report_lines.append(f"  Total Trades:        {total_trades}")
    report_lines.append(f"  Winning Trades:      {win_count} ({win_rate:.1f}%)")
    report_lines.append(f"  Losing Trades:       {loss_count} ({100-win_rate:.1f}%)")
    report_lines.append("")
    report_lines.append(f"  Average Win:         +{avg_win:.2f}%")
    report_lines.append(f"  Average Loss:        {avg_loss:.2f}%")
    report_lines.append(f"  Average Trade:       {avg_profit_pct:+.2f}%")
    report_lines.append("")
    report_lines.append(f"  Expectancy:          {expectancy:+.2f}% per trade")
    report_lines.append(f"  Profit Factor:       {profit_factor:.2f}")
    report_lines.append("")
    report_lines.append(f"  Avg Days Held:       {avg_days_held:.1f} days")
    report_lines.append(f"  Avg Days (Win):      {avg_days_win:.1f} days")
    report_lines.append(f"  Avg Days (Loss):     {avg_days_loss:.1f} days")
    report_lines.append("")
    report_lines.append(f"  Total Return:        {total_profit_pct:+.2f}% (if equal sizing)")
    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    # Breakeven analysis
    # With 1:2 R:R, you need 33.3% win rate to break even
    breakeven_winrate = 100 / 3  # 33.33%
    report_lines.append("ANALYSIS:")
    report_lines.append("-" * 100)
    report_lines.append(f"  Theoretical breakeven win rate (1:2 R:R): {breakeven_winrate:.1f}%")
    report_lines.append(f"  Actual win rate: {win_rate:.1f}%")
    if win_rate > breakeven_winrate:
        edge = win_rate - breakeven_winrate
        report_lines.append(f"  EDGE: +{edge:.1f}% above breakeven")
        report_lines.append(f"  STATUS: PROFITABLE STRATEGY")
    else:
        deficit = breakeven_winrate - win_rate
        report_lines.append(f"  DEFICIT: -{deficit:.1f}% below breakeven")
        report_lines.append(f"  STATUS: NEEDS IMPROVEMENT")
    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    # By price range breakdown
    report_lines.append("RESULTS BY PRICE RANGE:")
    report_lines.append("-" * 100)

    price_ranges = [
        ("$0.50-$2", 0.50, 2),
        ("$2-$5", 2, 5),
        ("$5-$10", 5, 10),
        ("$10-$20", 10, 20),
        ("$20-$50", 20, 50),
        ("$50-$100", 50, 100),
        ("$100+", 100, 10000)
    ]

    report_lines.append(f"{'Range':<15} {'Trades':<10} {'Wins':<10} {'Win%':<10} {'Avg Win':<12} {'Avg Loss':<12} {'Expectancy':<12}")
    report_lines.append("-" * 100)

    for range_name, min_p, max_p in price_ranges:
        range_trades = [t for t in all_trades if min_p <= t['entry_price'] < max_p]
        if range_trades:
            r_wins = [t for t in range_trades if t['result'] == 'WIN']
            r_losses = [t for t in range_trades if t['result'] == 'LOSS']
            r_win_rate = (len(r_wins) / len(range_trades)) * 100
            r_avg_win = np.mean([t['profit_pct'] for t in r_wins]) if r_wins else 0
            r_avg_loss = np.mean([t['profit_pct'] for t in r_losses]) if r_losses else 0
            r_expectancy = (r_win_rate/100 * r_avg_win) + ((100-r_win_rate)/100 * r_avg_loss)

            report_lines.append(
                f"{range_name:<15} {len(range_trades):<10} {len(r_wins):<10} {r_win_rate:<9.1f}% "
                f"+{r_avg_win:<10.2f}% {r_avg_loss:<11.2f}% {r_expectancy:+.2f}%"
            )

    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    # Recent trades sample
    report_lines.append("SAMPLE TRADES (Last 30):")
    report_lines.append("-" * 100)
    report_lines.append(f"{'Ticker':<8} {'Entry Date':<12} {'Entry$':<10} {'Exit$':<10} {'P/L%':<10} {'Result':<8} {'Days':<6}")
    report_lines.append("-" * 100)

    # Sort by date and get last 30
    sorted_trades = sorted(all_trades, key=lambda x: x['entry_date'], reverse=True)[:30]

    for trade in sorted_trades:
        report_lines.append(
            f"{trade['ticker']:<8} "
            f"{trade['entry_date'].strftime('%Y-%m-%d'):<12} "
            f"${trade['entry_price']:<9.2f} "
            f"${trade['exit_price']:<9.2f} "
            f"{trade['profit_pct']:+8.2f}% "
            f"{trade['result']:<8} "
            f"{trade['days_held']:<6}"
        )

    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    # Best and worst trades
    if wins:
        best_trade = max(wins, key=lambda x: x['profit_pct'])
        report_lines.append("BEST TRADE:")
        report_lines.append(f"  {best_trade['ticker']} - Entry: ${best_trade['entry_price']:.2f} on {best_trade['entry_date'].strftime('%Y-%m-%d')}")
        report_lines.append(f"  Exit: ${best_trade['exit_price']:.2f} - Profit: +{best_trade['profit_pct']:.2f}%")
        report_lines.append("")

    if losses:
        worst_trade = min(losses, key=lambda x: x['profit_pct'])
        report_lines.append("WORST TRADE:")
        report_lines.append(f"  {worst_trade['ticker']} - Entry: ${worst_trade['entry_price']:.2f} on {worst_trade['entry_date'].strftime('%Y-%m-%d')}")
        report_lines.append(f"  Exit: ${worst_trade['exit_price']:.2f} - Loss: {worst_trade['profit_pct']:.2f}%")
        report_lines.append("")

    report_lines.append("=" * 100)

    # Write to file
    report_text = '\n'.join(report_lines)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Print to console
    print(report_text)
    print(f"\nReport saved to: {output_file}")

    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'expectancy': expectancy,
        'profit_factor': profit_factor,
        'all_trades': all_trades
    }


if __name__ == "__main__":
    # Run 1-year backtest
    run_backtest(lookback_days=252, min_price=0.50, max_price=500)
