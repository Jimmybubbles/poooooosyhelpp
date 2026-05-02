"""
Range Level Backtest - Trade Type Comparison
=============================================
Compares two trade types:
1. WITHIN_RANGE: Buy at 25%, sell at 75% of SAME range
2. RANGE_CHANGE: Buy at 75%, sell at 25% of NEXT range up

Tests which type of trade has better win rate and expectancy.
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
output_file = os.path.join(script_dir, 'buylist', 'range_level_trade_type_comparison.txt')


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


def get_next_range_info(current_range_info):
    """Get info for the next range up"""
    next_range_low = current_range_info['range_high']
    range_size = current_range_info['range_size']

    # For prices crossing into new magnitude, adjust range size
    if next_range_low == 10:
        range_size = 10.0
    elif next_range_low == 100:
        range_size = 50.0
    elif next_range_low == 500:
        range_size = 100.0

    next_range_high = next_range_low + range_size

    return {
        'range_low': next_range_low,
        'range_high': next_range_high,
        'range_size': range_size,
        'levels': {
            'L0': next_range_low,
            'L25': next_range_low + (range_size * 0.25),
            'L50': next_range_low + (range_size * 0.50),
            'L75': next_range_low + (range_size * 0.75),
            'L100': next_range_high
        }
    }


def backtest_within_range(ticker, results_dir, lookback_days=252):
    """
    Backtest WITHIN_RANGE trades: Buy at 25%, target 75%, stop at 0%
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker}.csv")
        if not os.path.exists(csv_file):
            return []

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

        if len(df) > lookback_days:
            df = df.iloc[-lookback_days:]

        if len(df) < 20:
            return []

        trades = []
        in_trade = False
        entry_price = 0
        entry_date = None
        target_price = 0
        stop_price = 0

        for i in range(1, len(df)):
            current_date = df.index[i]
            current_low = df['Low'].iloc[i]
            current_high = df['High'].iloc[i]
            prev_close = df['Close'].iloc[i-1]

            if not in_trade:
                range_info = get_range_info(prev_close)
                if range_info is None:
                    continue

                level_25 = range_info['levels']['L25']
                level_0 = range_info['levels']['L0']
                level_75 = range_info['levels']['L75']

                # Entry: price drops from above 25% to touch 25%
                if prev_close > level_25 and current_low <= level_25 and current_low > level_0:
                    in_trade = True
                    entry_price = level_25
                    entry_date = current_date
                    target_price = level_75
                    stop_price = level_0

            else:
                hit_target = current_high >= target_price
                hit_stop = current_low <= stop_price

                if hit_target and hit_stop:
                    open_price = df['Open'].iloc[i]
                    if abs(open_price - stop_price) < abs(open_price - target_price):
                        hit_target = False
                    else:
                        hit_stop = False

                if hit_target:
                    profit_pct = ((target_price - entry_price) / entry_price) * 100
                    trades.append({
                        'ticker': ticker,
                        'trade_type': 'WITHIN_RANGE',
                        'entry_date': entry_date,
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': target_price,
                        'profit_pct': profit_pct,
                        'result': 'WIN',
                        'days_held': max(1, (current_date - entry_date).days)
                    })
                    in_trade = False

                elif hit_stop:
                    profit_pct = ((stop_price - entry_price) / entry_price) * 100
                    trades.append({
                        'ticker': ticker,
                        'trade_type': 'WITHIN_RANGE',
                        'entry_date': entry_date,
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': stop_price,
                        'profit_pct': profit_pct,
                        'result': 'LOSS',
                        'days_held': max(1, (current_date - entry_date).days)
                    })
                    in_trade = False

        return trades

    except Exception as e:
        return []


def backtest_range_change(ticker, results_dir, lookback_days=252):
    """
    Backtest RANGE_CHANGE trades: Buy at 75%, target next range 25%, stop at 50%

    Entry: Price rises from below 75% to touch 75%
    Target: 25% level of NEXT range up (L100 + 25% of next range)
    Stop: 50% level (middle of current range)
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker}.csv")
        if not os.path.exists(csv_file):
            return []

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

        if len(df) > lookback_days:
            df = df.iloc[-lookback_days:]

        if len(df) < 20:
            return []

        trades = []
        in_trade = False
        entry_price = 0
        entry_date = None
        target_price = 0
        stop_price = 0

        for i in range(1, len(df)):
            current_date = df.index[i]
            current_low = df['Low'].iloc[i]
            current_high = df['High'].iloc[i]
            prev_close = df['Close'].iloc[i-1]

            if not in_trade:
                range_info = get_range_info(prev_close)
                if range_info is None:
                    continue

                level_75 = range_info['levels']['L75']
                level_50 = range_info['levels']['L50']
                level_100 = range_info['levels']['L100']

                # Entry: price rises from below 75% to touch 75%
                if prev_close < level_75 and current_high >= level_75 and current_high < level_100:
                    # Get next range info for target
                    next_range = get_next_range_info(range_info)

                    in_trade = True
                    entry_price = level_75
                    entry_date = current_date
                    target_price = next_range['levels']['L25']  # 25% of next range
                    stop_price = level_50  # 50% of current range

            else:
                hit_target = current_high >= target_price
                hit_stop = current_low <= stop_price

                if hit_target and hit_stop:
                    open_price = df['Open'].iloc[i]
                    if abs(open_price - stop_price) < abs(open_price - target_price):
                        hit_target = False
                    else:
                        hit_stop = False

                if hit_target:
                    profit_pct = ((target_price - entry_price) / entry_price) * 100
                    trades.append({
                        'ticker': ticker,
                        'trade_type': 'RANGE_CHANGE',
                        'entry_date': entry_date,
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': target_price,
                        'profit_pct': profit_pct,
                        'result': 'WIN',
                        'days_held': max(1, (current_date - entry_date).days)
                    })
                    in_trade = False

                elif hit_stop:
                    profit_pct = ((stop_price - entry_price) / entry_price) * 100
                    trades.append({
                        'ticker': ticker,
                        'trade_type': 'RANGE_CHANGE',
                        'entry_date': entry_date,
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': stop_price,
                        'profit_pct': profit_pct,
                        'result': 'LOSS',
                        'days_held': max(1, (current_date - entry_date).days)
                    })
                    in_trade = False

        return trades

    except Exception as e:
        return []


def run_comparison(lookback_days=252, min_price=0.50, max_price=500):
    """
    Run both backtests and compare results.
    """
    print("=" * 100)
    print("RANGE LEVEL BACKTEST - TRADE TYPE COMPARISON")
    print("=" * 100)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("COMPARING TWO TRADE TYPES:")
    print()
    print("  1. WITHIN_RANGE (Consolidation Play)")
    print("     Entry: Buy at 25% level (price dips from above)")
    print("     Target: 75% level (+50% of range = 2R)")
    print("     Stop: 0% level (-25% of range = 1R)")
    print("     R:R = 1:2")
    print()
    print("  2. RANGE_CHANGE (Breakout Play)")
    print("     Entry: Buy at 75% level (price rises from below)")
    print("     Target: 25% of NEXT range up")
    print("     Stop: 50% level (-25% of range = 1R)")
    print("     R:R = 1:2")
    print()
    print("=" * 100)
    print()

    # Get ticker list
    csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
    tickers = [f[:-4] for f in csv_files]

    print(f"Backtesting {len(tickers)} stocks...")
    print()

    # Run WITHIN_RANGE backtest
    print("Running WITHIN_RANGE backtest...")
    within_range_trades = []
    for i, ticker in enumerate(tickers):
        if (i + 1) % 500 == 0:
            print(f"  Progress: {i + 1}/{len(tickers)}...")
        trades = backtest_within_range(ticker, results_dir, lookback_days)
        trades = [t for t in trades if min_price <= t['entry_price'] <= max_price]
        within_range_trades.extend(trades)
    print(f"  Complete: {len(within_range_trades)} trades")
    print()

    # Run RANGE_CHANGE backtest
    print("Running RANGE_CHANGE backtest...")
    range_change_trades = []
    for i, ticker in enumerate(tickers):
        if (i + 1) % 500 == 0:
            print(f"  Progress: {i + 1}/{len(tickers)}...")
        trades = backtest_range_change(ticker, results_dir, lookback_days)
        trades = [t for t in trades if min_price <= t['entry_price'] <= max_price]
        range_change_trades.extend(trades)
    print(f"  Complete: {len(range_change_trades)} trades")
    print()

    # Calculate statistics
    def calc_stats(trades, name):
        if not trades:
            return None

        total = len(trades)
        wins = [t for t in trades if t['result'] == 'WIN']
        losses = [t for t in trades if t['result'] == 'LOSS']

        win_count = len(wins)
        win_rate = (win_count / total) * 100 if total > 0 else 0

        avg_win = np.mean([t['profit_pct'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['profit_pct'] for t in losses]) if losses else 0

        expectancy = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)

        gross_profit = sum([t['profit_pct'] for t in wins]) if wins else 0
        gross_loss = abs(sum([t['profit_pct'] for t in losses])) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        avg_days = np.mean([t['days_held'] for t in trades])

        return {
            'name': name,
            'total_trades': total,
            'wins': win_count,
            'losses': len(losses),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'expectancy': expectancy,
            'profit_factor': profit_factor,
            'avg_days': avg_days,
            'total_return': sum([t['profit_pct'] for t in trades])
        }

    within_stats = calc_stats(within_range_trades, "WITHIN_RANGE")
    change_stats = calc_stats(range_change_trades, "RANGE_CHANGE")

    # Generate report
    report_lines = []
    report_lines.append("=" * 100)
    report_lines.append("RANGE LEVEL BACKTEST - TRADE TYPE COMPARISON")
    report_lines.append("=" * 100)
    report_lines.append(f"Backtest Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Lookback Period: {lookback_days} trading days")
    report_lines.append("")
    report_lines.append("TRADE TYPES:")
    report_lines.append("-" * 100)
    report_lines.append("  WITHIN_RANGE: Buy 25% dip, sell at 75% (consolidation/mean reversion)")
    report_lines.append("  RANGE_CHANGE: Buy 75% breakout, sell at next range 25% (momentum/breakout)")
    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    if within_stats and change_stats:
        report_lines.append("COMPARISON RESULTS:")
        report_lines.append("-" * 100)
        report_lines.append(f"{'Metric':<25} {'WITHIN_RANGE':<20} {'RANGE_CHANGE':<20} {'DIFFERENCE':<20}")
        report_lines.append("-" * 100)

        metrics = [
            ('Total Trades', 'total_trades', '{:,}'),
            ('Winning Trades', 'wins', '{:,}'),
            ('Losing Trades', 'losses', '{:,}'),
            ('Win Rate', 'win_rate', '{:.1f}%'),
            ('Average Win', 'avg_win', '+{:.2f}%'),
            ('Average Loss', 'avg_loss', '{:.2f}%'),
            ('Expectancy', 'expectancy', '{:+.2f}%'),
            ('Profit Factor', 'profit_factor', '{:.2f}'),
            ('Avg Days Held', 'avg_days', '{:.1f}'),
        ]

        for label, key, fmt in metrics:
            within_val = within_stats[key]
            change_val = change_stats[key]

            if key == 'win_rate':
                diff = change_val - within_val
                diff_str = f"{diff:+.1f}%"
                within_str = f"{within_val:.1f}%"
                change_str = f"{change_val:.1f}%"
            elif key == 'expectancy':
                diff = change_val - within_val
                diff_str = f"{diff:+.2f}%"
                within_str = f"{within_val:+.2f}%"
                change_str = f"{change_val:+.2f}%"
            elif key == 'profit_factor':
                diff = change_val - within_val
                diff_str = f"{diff:+.2f}"
                within_str = f"{within_val:.2f}"
                change_str = f"{change_val:.2f}"
            elif key in ['total_trades', 'wins', 'losses']:
                diff = change_val - within_val
                diff_str = f"{diff:+,}"
                within_str = f"{within_val:,}"
                change_str = f"{change_val:,}"
            elif key == 'avg_win':
                diff = change_val - within_val
                diff_str = f"{diff:+.2f}%"
                within_str = f"+{within_val:.2f}%"
                change_str = f"+{change_val:.2f}%"
            elif key == 'avg_loss':
                diff = change_val - within_val
                diff_str = f"{diff:+.2f}%"
                within_str = f"{within_val:.2f}%"
                change_str = f"{change_val:.2f}%"
            else:
                diff = change_val - within_val
                diff_str = f"{diff:+.1f}"
                within_str = f"{within_val:.1f}"
                change_str = f"{change_val:.1f}"

            report_lines.append(f"{label:<25} {within_str:<20} {change_str:<20} {diff_str:<20}")

        report_lines.append("-" * 100)
        report_lines.append("")

        # Analysis
        report_lines.append("=" * 100)
        report_lines.append("ANALYSIS:")
        report_lines.append("-" * 100)

        # Determine winner
        within_score = 0
        change_score = 0

        if within_stats['win_rate'] > change_stats['win_rate']:
            within_score += 1
            report_lines.append(f"  Win Rate: WITHIN_RANGE wins ({within_stats['win_rate']:.1f}% vs {change_stats['win_rate']:.1f}%)")
        else:
            change_score += 1
            report_lines.append(f"  Win Rate: RANGE_CHANGE wins ({change_stats['win_rate']:.1f}% vs {within_stats['win_rate']:.1f}%)")

        if within_stats['expectancy'] > change_stats['expectancy']:
            within_score += 1
            report_lines.append(f"  Expectancy: WITHIN_RANGE wins ({within_stats['expectancy']:+.2f}% vs {change_stats['expectancy']:+.2f}%)")
        else:
            change_score += 1
            report_lines.append(f"  Expectancy: RANGE_CHANGE wins ({change_stats['expectancy']:+.2f}% vs {within_stats['expectancy']:+.2f}%)")

        if within_stats['profit_factor'] > change_stats['profit_factor']:
            within_score += 1
            report_lines.append(f"  Profit Factor: WITHIN_RANGE wins ({within_stats['profit_factor']:.2f} vs {change_stats['profit_factor']:.2f})")
        else:
            change_score += 1
            report_lines.append(f"  Profit Factor: RANGE_CHANGE wins ({change_stats['profit_factor']:.2f} vs {within_stats['profit_factor']:.2f})")

        report_lines.append("")
        report_lines.append(f"  SCORE: WITHIN_RANGE {within_score} - RANGE_CHANGE {change_score}")
        report_lines.append("")

        if within_score > change_score:
            report_lines.append("  WINNER: WITHIN_RANGE (Buy the dip at 25%)")
            report_lines.append("  This is a mean-reversion strategy that works well in ranging markets.")
        elif change_score > within_score:
            report_lines.append("  WINNER: RANGE_CHANGE (Buy the breakout at 75%)")
            report_lines.append("  This is a momentum strategy that captures range transitions.")
        else:
            report_lines.append("  RESULT: TIE - Both strategies have similar performance")
            report_lines.append("  Consider using both depending on market conditions.")

        report_lines.append("")
        report_lines.append("INTERPRETATION:")
        report_lines.append("  - WITHIN_RANGE = Mean reversion / Consolidation play")
        report_lines.append("  - RANGE_CHANGE = Momentum / Breakout play")
        report_lines.append("  - Higher win rate doesn't always mean better (check expectancy)")
        report_lines.append("  - Both can be combined for a complete range-based system")

    report_lines.append("")
    report_lines.append("=" * 100)

    # Write report
    report_text = '\n'.join(report_lines)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    print(report_text)
    print(f"\nReport saved to: {output_file}")

    return within_stats, change_stats


if __name__ == "__main__":
    run_comparison(lookback_days=252)
