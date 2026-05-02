"""
Range Level Backtest with Weekly Fader Filter
==============================================
Tests the range theory: Buy at 25% level, sell at 75%, stop at 0%
ENHANCED: Only take trades when weekly Fader is GREEN (higher timeframe confirmation)

Theory: Higher timeframe takes precedence - if weekly trend is up (Fader green),
        then daily 25% level buys should have better odds.
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime
from ta.trend import WMAIndicator

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
output_file = os.path.join(script_dir, 'buylist', 'range_level_weekly_fader_comparison.txt')

# Fader Parameters
FADER_PARAMS = {
    'fmal_zl': 1,
    'smal_zl': 1,
    'length_jma': 7,
    'phase': 126,
    'power': 0.89144,
}


def jma(source, length, phase, power):
    """Jurik Moving Average (JMA)"""
    phaseRatio = phase if -100 <= phase <= 100 else (100 if phase > 100 else -100)
    phaseRatio = (phaseRatio / 100) + 1.5
    beta = 0.45 * (length - 1) / (0.45 * (length - 1) + 2)
    alpha = np.power(beta, power)

    source_arr = np.array(source)
    e0 = np.zeros(len(source_arr))
    e1 = np.zeros(len(source_arr))
    e2 = np.zeros(len(source_arr))
    jma_result = np.zeros(len(source_arr))

    for i in range(1, len(source_arr)):
        e0[i] = (1 - alpha) * source_arr[i] + alpha * e0[i-1]
        e1[i] = (source_arr[i] - e0[i]) * (1 - beta) + beta * e1[i-1]
        e2[i] = (e0[i] + phaseRatio * e1[i] - jma_result[i-1]) * np.power(1 - alpha, 2) + np.power(alpha, 2) * e2[i-1]
        jma_result[i] = e2[i] + jma_result[i-1]

    return jma_result


def calculate_weekly_fader(df):
    """
    Calculate weekly Fader from daily data.
    Returns dict mapping week-ending date to fader color ('green' or 'red')
    """
    if len(df) < 50:
        return {}

    # Resample to weekly
    df_copy = df.copy()

    # Make sure index is datetime
    if not isinstance(df_copy.index, pd.DatetimeIndex):
        return {}

    # Remove timezone if present
    if df_copy.index.tz is not None:
        df_copy.index = df_copy.index.tz_localize(None)

    weekly = df_copy.resample('W').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last'
    }).dropna()

    if len(weekly) < 20:
        return {}

    # Calculate Fader on weekly
    fmal_zl = FADER_PARAMS['fmal_zl']
    smal_zl = FADER_PARAMS['smal_zl']
    length_jma = FADER_PARAMS['length_jma']
    phase = FADER_PARAMS['phase']
    power = FADER_PARAMS['power']

    tmal_zl = fmal_zl + smal_zl
    Fmal_zl = smal_zl + tmal_zl
    Ftmal_zl = tmal_zl + Fmal_zl
    Smal_zl = Fmal_zl + Ftmal_zl

    close = weekly['Close'].astype(float)

    try:
        # Cascaded WMAs
        m1 = WMAIndicator(close, window=fmal_zl).wma()
        m2 = WMAIndicator(m1.fillna(method='ffill'), window=smal_zl).wma()
        m3 = WMAIndicator(m2.fillna(method='ffill'), window=tmal_zl).wma()
        m4 = WMAIndicator(m3.fillna(method='ffill'), window=Fmal_zl).wma()
        m5 = WMAIndicator(m4.fillna(method='ffill'), window=Ftmal_zl).wma()

        # Hull MA approximation
        half_len = max(1, Smal_zl // 2)
        sqrt_len = max(1, int(np.sqrt(Smal_zl)))
        wma1 = WMAIndicator(m5.fillna(method='ffill'), window=half_len).wma()
        wma2 = WMAIndicator(m5.fillna(method='ffill'), window=Smal_zl).wma()
        raw_hma = 2 * wma1 - wma2
        mavw = WMAIndicator(raw_hma.fillna(method='ffill'), window=sqrt_len).wma()

        # JMA
        jma_result = jma(close.values, length_jma, phase, power)

        # Final signal
        signal = (mavw.values + jma_result) / 2

        # Determine color for each week
        fader_colors = {}
        for i in range(1, len(weekly)):
            week_date = weekly.index[i]
            if pd.notna(signal[i]) and pd.notna(signal[i-1]):
                color = 'green' if signal[i] > signal[i-1] else 'red'
                fader_colors[week_date] = color

        return fader_colors

    except Exception as e:
        return {}


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


def backtest_stock(ticker, results_dir, lookback_days=252, weekly_fader_filter=None):
    """
    Backtest the 25% -> 75% strategy on a single stock.

    Args:
        ticker: Stock symbol
        results_dir: Directory with CSV files
        lookback_days: How many days to backtest
        weekly_fader_filter: Dict of week-end dates to colors, or None to disable filter

    Returns list of trades with results.
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker}.csv")

        if not os.path.exists(csv_file):
            return []

        # Read CSV - same as original working backtest
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
                if prev_close > level_25 and current_low <= level_25 and current_low > level_0:

                    # Apply weekly fader filter if provided
                    if weekly_fader_filter is not None:
                        # Get week-ending date for current date
                        current_date_naive = current_date.replace(tzinfo=None) if hasattr(current_date, 'tzinfo') and current_date.tzinfo else current_date

                        # Find most recent week ending before or on current date
                        fader_color = None
                        for week_date in sorted(weekly_fader_filter.keys(), reverse=True):
                            week_naive = week_date.replace(tzinfo=None) if hasattr(week_date, 'tzinfo') and week_date.tzinfo else week_date
                            if week_naive <= current_date_naive:
                                fader_color = weekly_fader_filter[week_date]
                                break

                        # Skip trade if weekly fader is not green
                        if fader_color != 'green':
                            continue

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
                hit_target = current_high >= target_level_75
                hit_stop = current_low <= stop_level_0

                if hit_target and hit_stop:
                    open_price = df['Open'].iloc[i]
                    if abs(open_price - stop_level_0) < abs(open_price - target_level_75):
                        hit_target = False
                    else:
                        hit_stop = False

                if hit_target:
                    exit_price = target_level_75
                    profit = exit_price - entry_price
                    profit_pct = (profit / entry_price) * 100

                    trades.append({
                        'ticker': ticker,
                        'entry_date': entry_date,
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'profit_pct': profit_pct,
                        'result': 'WIN',
                        'days_held': max(1, (current_date - entry_date).days)
                    })
                    in_trade = False

                elif hit_stop:
                    exit_price = stop_level_0
                    profit = exit_price - entry_price
                    profit_pct = (profit / entry_price) * 100

                    trades.append({
                        'ticker': ticker,
                        'entry_date': entry_date,
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'profit_pct': profit_pct,
                        'result': 'LOSS',
                        'days_held': max(1, (current_date - entry_date).days)
                    })
                    in_trade = False

        return trades

    except Exception as e:
        return []


def run_comparison_backtest(lookback_days=252, min_price=0.50, max_price=500):
    """
    Run backtest twice: once without filter, once with weekly fader filter.
    Compare results.
    """
    print("=" * 100)
    print("RANGE LEVEL BACKTEST - WEEKLY FADER COMPARISON")
    print("=" * 100)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("TESTING TWO SCENARIOS:")
    print("  1. BASELINE: Buy at 25% level, target 75%, stop 0% (no filter)")
    print("  2. ENHANCED: Same strategy but ONLY when weekly Fader is GREEN")
    print()
    print("HYPOTHESIS: Weekly Fader green = higher timeframe uptrend = better win rate")
    print("=" * 100)
    print()

    # Get ticker list
    csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
    tickers = [f[:-4] for f in csv_files]

    print(f"Backtesting {len(tickers)} stocks...")
    print()

    # First, calculate weekly faders for all stocks (we need more data for weekly calc)
    print("Step 1: Calculating weekly Fader for each stock...")
    print("-" * 50)

    weekly_faders = {}
    for i, ticker in enumerate(tickers):
        if (i + 1) % 500 == 0:
            print(f"  Calculating Fader: {i + 1}/{len(tickers)}...")

        csv_file = os.path.join(results_dir, f"{ticker}.csv")
        if not os.path.exists(csv_file):
            continue

        try:
            df = pd.read_csv(csv_file, skiprows=[1, 2])

            if 'Price' in df.columns:
                df.rename(columns={'Price': 'Date'}, inplace=True)

            if 'Date' not in df.columns or 'Close' not in df.columns:
                continue

            df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
            df = df.dropna(subset=['Date'])
            df.set_index('Date', inplace=True)

            for col in ['Open', 'High', 'Low', 'Close']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df = df.dropna()

            if len(df) > 50:
                fader_colors = calculate_weekly_fader(df)
                if fader_colors:
                    weekly_faders[ticker] = fader_colors

        except:
            continue

    print(f"  Weekly Fader calculated for {len(weekly_faders)} stocks")
    print()

    # Run baseline backtest (no filter)
    print("Step 2: Running BASELINE backtest (no filter)...")
    print("-" * 50)

    baseline_trades = []
    for i, ticker in enumerate(tickers):
        if (i + 1) % 500 == 0:
            print(f"  Baseline: {i + 1}/{len(tickers)}...")

        trades = backtest_stock(ticker, results_dir, lookback_days, weekly_fader_filter=None)
        trades = [t for t in trades if min_price <= t['entry_price'] <= max_price]
        baseline_trades.extend(trades)

    print(f"  Baseline complete: {len(baseline_trades)} trades")
    print()

    # Run enhanced backtest (with weekly fader filter)
    print("Step 3: Running ENHANCED backtest (weekly Fader GREEN required)...")
    print("-" * 50)

    enhanced_trades = []
    for i, ticker in enumerate(tickers):
        if (i + 1) % 500 == 0:
            print(f"  Enhanced: {i + 1}/{len(tickers)}...")

        # Get weekly fader for this ticker
        fader_filter = weekly_faders.get(ticker, None)

        trades = backtest_stock(ticker, results_dir, lookback_days, weekly_fader_filter=fader_filter)
        trades = [t for t in trades if min_price <= t['entry_price'] <= max_price]
        enhanced_trades.extend(trades)

    print(f"  Enhanced complete: {len(enhanced_trades)} trades")
    print()

    # Calculate statistics
    def calc_stats(trades):
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
            'total_trades': total,
            'wins': win_count,
            'losses': len(losses),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'expectancy': expectancy,
            'profit_factor': profit_factor,
            'avg_days': avg_days
        }

    baseline_stats = calc_stats(baseline_trades)
    enhanced_stats = calc_stats(enhanced_trades)

    # Generate report
    report_lines = []
    report_lines.append("=" * 100)
    report_lines.append("RANGE LEVEL BACKTEST - WEEKLY FADER COMPARISON RESULTS")
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
    report_lines.append("FILTER TEST:")
    report_lines.append("  BASELINE: Take all valid entries")
    report_lines.append("  ENHANCED: Only enter when WEEKLY FADER is GREEN (uptrend)")
    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")

    if baseline_stats and enhanced_stats:
        report_lines.append("COMPARISON RESULTS:")
        report_lines.append("-" * 100)
        report_lines.append(f"{'Metric':<25} {'BASELINE':<20} {'ENHANCED (Fader)':<20} {'DIFFERENCE':<20}")
        report_lines.append("-" * 100)

        # Total trades
        diff_trades = enhanced_stats['total_trades'] - baseline_stats['total_trades']
        report_lines.append(f"{'Total Trades':<25} {baseline_stats['total_trades']:<20,} {enhanced_stats['total_trades']:<20,} {diff_trades:+,}")

        # Win rate
        diff_winrate = enhanced_stats['win_rate'] - baseline_stats['win_rate']
        report_lines.append(f"{'Win Rate':<25} {baseline_stats['win_rate']:<19.1f}% {enhanced_stats['win_rate']:<19.1f}% {diff_winrate:+.1f}%")

        # Wins
        diff_wins = enhanced_stats['wins'] - baseline_stats['wins']
        report_lines.append(f"{'Winning Trades':<25} {baseline_stats['wins']:<20,} {enhanced_stats['wins']:<20,} {diff_wins:+,}")

        # Avg Win
        diff_avgwin = enhanced_stats['avg_win'] - baseline_stats['avg_win']
        report_lines.append(f"{'Average Win':<25} +{baseline_stats['avg_win']:<18.2f}% +{enhanced_stats['avg_win']:<18.2f}% {diff_avgwin:+.2f}%")

        # Avg Loss
        diff_avgloss = enhanced_stats['avg_loss'] - baseline_stats['avg_loss']
        report_lines.append(f"{'Average Loss':<25} {baseline_stats['avg_loss']:<19.2f}% {enhanced_stats['avg_loss']:<19.2f}% {diff_avgloss:+.2f}%")

        # Expectancy
        diff_exp = enhanced_stats['expectancy'] - baseline_stats['expectancy']
        report_lines.append(f"{'Expectancy':<25} {baseline_stats['expectancy']:+<18.2f}% {enhanced_stats['expectancy']:+<18.2f}% {diff_exp:+.2f}%")

        # Profit Factor
        diff_pf = enhanced_stats['profit_factor'] - baseline_stats['profit_factor']
        report_lines.append(f"{'Profit Factor':<25} {baseline_stats['profit_factor']:<20.2f} {enhanced_stats['profit_factor']:<20.2f} {diff_pf:+.2f}")

        # Avg Days
        diff_days = enhanced_stats['avg_days'] - baseline_stats['avg_days']
        report_lines.append(f"{'Avg Days Held':<25} {baseline_stats['avg_days']:<19.1f} {enhanced_stats['avg_days']:<19.1f} {diff_days:+.1f}")

        report_lines.append("-" * 100)
        report_lines.append("")

        # Analysis
        report_lines.append("=" * 100)
        report_lines.append("ANALYSIS:")
        report_lines.append("-" * 100)

        trade_reduction = ((baseline_stats['total_trades'] - enhanced_stats['total_trades']) / baseline_stats['total_trades']) * 100 if baseline_stats['total_trades'] > 0 else 0

        report_lines.append(f"  Trade Reduction: {trade_reduction:.1f}% fewer trades with filter (more selective)")
        report_lines.append(f"  Win Rate Change: {diff_winrate:+.1f}%")
        report_lines.append(f"  Expectancy Change: {diff_exp:+.2f}% per trade")
        report_lines.append("")

        if diff_winrate > 0 and diff_exp > 0:
            report_lines.append("  RESULT: ✓ WEEKLY FADER FILTER IMPROVES RESULTS")
            report_lines.append("  Higher timeframe trend confirmation increases both win rate and expectancy.")
            report_lines.append("  Recommendation: Use the weekly Fader filter for better risk-adjusted returns.")
        elif diff_winrate > 0:
            report_lines.append("  RESULT: ~ MIXED - Higher win rate but lower expectancy per trade")
            report_lines.append("  The filter improves win rate but may reduce total opportunities.")
        elif diff_exp > 0:
            report_lines.append("  RESULT: ~ MIXED - Lower win rate but higher expectancy")
            report_lines.append("  Fewer wins but larger winners may be worth the trade-off.")
        else:
            report_lines.append("  RESULT: ✗ WEEKLY FADER FILTER DID NOT IMPROVE RESULTS")
            report_lines.append("  The baseline strategy may already capture the edge.")

        report_lines.append("")
        report_lines.append("INTERPRETATION:")
        report_lines.append("  - Weekly Fader GREEN = price above weekly Fader line = uptrend")
        report_lines.append("  - Buying 25% dips in an uptrend should have better odds")
        report_lines.append("  - Higher timeframe alignment = fractal edge")

    else:
        report_lines.append("ERROR: Could not calculate statistics (insufficient data)")

    report_lines.append("")
    report_lines.append("=" * 100)

    # Write report
    report_text = '\n'.join(report_lines)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Print to console
    print(report_text)
    print(f"\nReport saved to: {output_file}")

    return baseline_stats, enhanced_stats


if __name__ == "__main__":
    import sys

    lookback = 252
    if len(sys.argv) > 1:
        try:
            lookback = int(sys.argv[1])
        except:
            pass

    run_comparison_backtest(lookback_days=lookback)
