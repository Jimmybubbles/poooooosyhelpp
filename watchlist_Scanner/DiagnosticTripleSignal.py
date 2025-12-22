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
output_file = os.path.join(buylist_dir, 'triple_signal_diagnostic.txt')

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
    """Check if price is trading within a defined channel at a specific index"""
    lookback_days = channel_period * 5

    if idx < lookback_days:
        return False

    current_close = df['Close'].iloc[idx]
    previous_highs = df['High'].iloc[idx-lookback_days:idx]
    previous_lows = df['Low'].iloc[idx-lookback_days:idx]

    channel_high = previous_highs.max()
    channel_low = previous_lows.min()

    if channel_low <= current_close <= channel_high:
        return True

    return False

def diagnose_ticker(ticker_symbol, results_dir):
    """
    Diagnose why a ticker might not be generating signals
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker_symbol}.csv")

        if not os.path.exists(csv_file):
            return None

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
            return {'ticker': ticker_symbol, 'error': 'insufficient_data', 'rows': len(df)}

        # Calculate indicators
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)
        zones = calculate_price_range_zones(df, lookback_period=100)
        trend = determine_trend(df, lookback_period=50)

        # Count how many times each condition is met (last 100 days)
        recent_days = min(100, len(df) - 100)
        start_idx = len(df) - recent_days

        condition_counts = {
            'in_channel': 0,
            'buy_zone': 0,
            'efi_oversold': 0,
            'uptrend': 0,
            'all_four': 0,
            'any_three': 0
        }

        # Check recent history
        for i in range(start_idx, len(df)):
            in_channel = check_in_channel(df, i, channel_period=3)
            fi_color = efi_results['fi_color'].iloc[i]
            price_zone = zones['price_zone'].iloc[i]
            current_trend = trend.iloc[i]

            c1 = in_channel
            c2 = price_zone == 'buy_zone'
            c3 = fi_color in ['maroon', 'orange']
            c4 = current_trend == 'uptrend'

            if c1:
                condition_counts['in_channel'] += 1
            if c2:
                condition_counts['buy_zone'] += 1
            if c3:
                condition_counts['efi_oversold'] += 1
            if c4:
                condition_counts['uptrend'] += 1

            # Count combinations
            conditions_met = sum([c1, c2, c3, c4])
            if conditions_met == 4:
                condition_counts['all_four'] += 1
            elif conditions_met == 3:
                condition_counts['any_three'] += 1

        # Get current state
        latest_idx = -1
        current_state = {
            'ticker': ticker_symbol,
            'date': df.index[latest_idx].strftime('%Y-%m-%d'),
            'price': df['Close'].iloc[latest_idx],
            'in_channel': check_in_channel(df, len(df) - 1, channel_period=3),
            'fi_color': efi_results['fi_color'].iloc[latest_idx],
            'price_zone': zones['price_zone'].iloc[latest_idx],
            'trend': trend.iloc[latest_idx],
            'range_position': zones['range_position_pct'].iloc[latest_idx],
            'condition_counts': condition_counts,
            'total_days_checked': recent_days
        }

        return current_state

    except Exception as e:
        return {'ticker': ticker_symbol, 'error': str(e)}

def run_diagnostic():
    """Run diagnostic analysis"""
    print("=" * 80)
    print("TRIPLE SIGNAL DIAGNOSTIC - CONDITION ANALYSIS")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("This diagnostic will show:")
    print("  1. How often each condition is met")
    print("  2. Current state of each ticker")
    print("  3. Where the bottleneck is in the filtering")
    print()
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Analyzing {len(tickers)} tickers...")
    print()

    # Collect diagnostics
    all_diagnostics = []
    errors = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers analyzed...")

        result = diagnose_ticker(ticker, results_dir)
        if result:
            if 'error' in result:
                errors.append(result)
            else:
                all_diagnostics.append(result)

    print()
    print(f"Analysis complete!")
    print(f"Successfully analyzed: {len(all_diagnostics)} tickers")
    print(f"Errors: {len(errors)} tickers")
    print()

    # Aggregate statistics
    total_condition_counts = {
        'in_channel': 0,
        'buy_zone': 0,
        'efi_oversold': 0,
        'uptrend': 0,
        'all_four': 0,
        'any_three': 0
    }

    current_state_summary = {
        'in_channel': 0,
        'buy_zone': 0,
        'efi_oversold': 0,
        'uptrend': 0,
        'all_four': 0
    }

    total_days = 0

    for diag in all_diagnostics:
        counts = diag['condition_counts']
        for key in total_condition_counts:
            total_condition_counts[key] += counts[key]
        total_days += diag['total_days_checked']

        # Current state
        if diag['in_channel']:
            current_state_summary['in_channel'] += 1
        if diag['price_zone'] == 'buy_zone':
            current_state_summary['buy_zone'] += 1
        if diag['fi_color'] in ['maroon', 'orange']:
            current_state_summary['efi_oversold'] += 1
        if diag['trend'] == 'uptrend':
            current_state_summary['uptrend'] += 1

        # Check if current state has all 4
        if (diag['in_channel'] and
            diag['price_zone'] == 'buy_zone' and
            diag['fi_color'] in ['maroon', 'orange'] and
            diag['trend'] == 'uptrend'):
            current_state_summary['all_four'] += 1

    # Find stocks currently meeting all 4 conditions
    current_signals = [d for d in all_diagnostics
                      if (d['in_channel'] and
                          d['price_zone'] == 'buy_zone' and
                          d['fi_color'] in ['maroon', 'orange'] and
                          d['trend'] == 'uptrend')]

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("TRIPLE SIGNAL DIAGNOSTIC REPORT")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append(f"Tickers Analyzed: {len(all_diagnostics)}")
    report_lines.append(f"Total Historical Days Checked: {total_days:,}")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("HISTORICAL CONDITION FREQUENCY (Last ~100 Days per Stock)")
    report_lines.append("=" * 80)
    report_lines.append("")

    if total_days > 0:
        report_lines.append(f"{'Condition':<30} {'Count':<12} {'% of Days':<12}")
        report_lines.append("-" * 80)
        report_lines.append(f"{'1. In Channel':<30} {total_condition_counts['in_channel']:<12,} {(total_condition_counts['in_channel']/total_days*100):<11.2f}%")
        report_lines.append(f"{'2. Price in Buy Zone':<30} {total_condition_counts['buy_zone']:<12,} {(total_condition_counts['buy_zone']/total_days*100):<11.2f}%")
        report_lines.append(f"{'3. EFI Oversold (M/O)':<30} {total_condition_counts['efi_oversold']:<12,} {(total_condition_counts['efi_oversold']/total_days*100):<11.2f}%")
        report_lines.append(f"{'4. Uptrend':<30} {total_condition_counts['uptrend']:<12,} {(total_condition_counts['uptrend']/total_days*100):<11.2f}%")
        report_lines.append("")
        report_lines.append(f"{'All 4 Conditions Met':<30} {total_condition_counts['all_four']:<12,} {(total_condition_counts['all_four']/total_days*100):<11.2f}%")
        report_lines.append(f"{'Any 3 Conditions Met':<30} {total_condition_counts['any_three']:<12,} {(total_condition_counts['any_three']/total_days*100):<11.2f}%")

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("CURRENT STATE SUMMARY (Most Recent Data)")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append(f"{'Condition':<30} {'Stocks':<12} {'% of Total':<12}")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Currently In Channel':<30} {current_state_summary['in_channel']:<12} {(current_state_summary['in_channel']/len(all_diagnostics)*100):<11.2f}%")
    report_lines.append(f"{'Currently in Buy Zone':<30} {current_state_summary['buy_zone']:<12} {(current_state_summary['buy_zone']/len(all_diagnostics)*100):<11.2f}%")
    report_lines.append(f"{'Currently EFI Oversold':<30} {current_state_summary['efi_oversold']:<12} {(current_state_summary['efi_oversold']/len(all_diagnostics)*100):<11.2f}%")
    report_lines.append(f"{'Currently in Uptrend':<30} {current_state_summary['uptrend']:<12} {(current_state_summary['uptrend']/len(all_diagnostics)*100):<11.2f}%")
    report_lines.append("")
    report_lines.append(f"{'ALL 4 CONDITIONS NOW':<30} {current_state_summary['all_four']:<12} {(current_state_summary['all_four']/len(all_diagnostics)*100):<11.2f}%")

    report_lines.append("")
    report_lines.append("=" * 80)

    if current_signals:
        report_lines.append(f"STOCKS CURRENTLY MEETING ALL 4 CONDITIONS ({len(current_signals)})")
        report_lines.append("=" * 80)
        report_lines.append("")
        report_lines.append(f"{'Ticker':<10} {'Price':<12} {'Range Pos%':<12} {'EFI':<10} {'Trend':<10}")
        report_lines.append("-" * 80)

        for sig in current_signals:
            report_lines.append(
                f"{sig['ticker']:<10} "
                f"${sig['price']:<11.2f} "
                f"{sig['range_position']:<11.1f}% "
                f"{sig['fi_color'].upper():<10} "
                f"{sig['trend'].upper():<10}"
            )
        report_lines.append("")
    else:
        report_lines.append("STOCKS CURRENTLY MEETING ALL 4 CONDITIONS (0)")
        report_lines.append("=" * 80)
        report_lines.append("")
        report_lines.append("No stocks currently meet all 4 conditions.")
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("KEY INSIGHTS")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Identify bottleneck
    conditions_historical = [
        ('In Channel', total_condition_counts['in_channel'] / total_days * 100 if total_days > 0 else 0),
        ('Buy Zone', total_condition_counts['buy_zone'] / total_days * 100 if total_days > 0 else 0),
        ('EFI Oversold', total_condition_counts['efi_oversold'] / total_days * 100 if total_days > 0 else 0),
        ('Uptrend', total_condition_counts['uptrend'] / total_days * 100 if total_days > 0 else 0)
    ]

    bottleneck = min(conditions_historical, key=lambda x: x[1])

    report_lines.append(f"  Bottleneck: '{bottleneck[0]}' is the rarest condition ({bottleneck[1]:.2f}% of days)")
    report_lines.append("")

    if total_condition_counts['all_four'] == 0:
        report_lines.append("  ⚠ WARNING: No historical instances of all 4 conditions aligning!")
        report_lines.append("    Consider:")
        report_lines.append("    - Relaxing one or more conditions")
        report_lines.append("    - Testing with 3-signal combinations instead")
        report_lines.append("    - Expanding the EFI oversold definition")
    elif total_condition_counts['all_four'] < 100:
        report_lines.append("  ⚠ Very rare signal (< 100 occurrences in entire history)")
        report_lines.append("    This is a highly selective strategy")
    else:
        report_lines.append(f"  ✓ Found {total_condition_counts['all_four']} historical occurrences")

    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")

if __name__ == "__main__":
    run_diagnostic()