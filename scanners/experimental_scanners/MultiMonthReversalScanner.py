import pandas as pd
import numpy as np
import os
from datetime import datetime
import sys

# Add the watchlist_Scanner directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from EFI_Indicator import EFI_Indicator
from PriceRangeZones import determine_trend

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'multi_month_reversal_scan_results.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def detect_multi_month_reversal(ticker_symbol, results_dir, lookback_days=30):
    """
    Detect multi-month level reversal setups:
    1. Price recently broke below ANY of the previous 3 months' levels (High/Low/Open/Close)
    2. EFI shows reversal (color change from negative to positive)
    3. Stock is in uptrend (pullback buy)

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files
        lookback_days: Days to look back for the breakdown (default 30)

    Returns:
        Dictionary with reversal setup data or None
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

        # Need at least 6 months of data
        if len(df) < 126:
            return None

        # Calculate EFI indicator
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)

        # Calculate trend
        trend = determine_trend(df, lookback_period=50)

        # Resample to monthly data
        monthly_df = df.resample('ME').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()

        if len(monthly_df) < 4:  # Need at least 4 months (current + 3 previous)
            return None

        # Get previous 3 months' levels (indices -2, -3, -4 because -1 is current incomplete)
        month_1 = monthly_df.iloc[-2]  # Most recent complete month
        month_2 = monthly_df.iloc[-3]  # 2 months ago
        month_3 = monthly_df.iloc[-4]  # 3 months ago

        month_1_date = monthly_df.index[-2]
        month_2_date = monthly_df.index[-3]
        month_3_date = monthly_df.index[-4]

        # Collect all key levels from the 3 months
        key_levels = {
            'Month-1 Low': (month_1['Low'], month_1_date, 'M1-Low'),
            'Month-1 Open': (month_1['Open'], month_1_date, 'M1-Open'),
            'Month-1 Close': (month_1['Close'], month_1_date, 'M1-Close'),
            'Month-1 High': (month_1['High'], month_1_date, 'M1-High'),
            'Month-2 Low': (month_2['Low'], month_2_date, 'M2-Low'),
            'Month-2 Open': (month_2['Open'], month_2_date, 'M2-Open'),
            'Month-2 Close': (month_2['Close'], month_2_date, 'M2-Close'),
            'Month-2 High': (month_2['High'], month_2_date, 'M2-High'),
            'Month-3 Low': (month_3['Low'], month_3_date, 'M3-Low'),
            'Month-3 Open': (month_3['Open'], month_3_date, 'M3-Open'),
            'Month-3 Close': (month_3['Close'], month_3_date, 'M3-Close'),
            'Month-3 High': (month_3['High'], month_3_date, 'M3-High'),
        }

        # Current data
        current_idx = len(df) - 1
        current_price = df['Close'].iloc[current_idx]
        current_date = df.index[current_idx]
        current_trend = trend.iloc[current_idx]

        # Current EFI data
        current_fi_color = efi_results['fi_color'].iloc[current_idx]
        current_force_index = efi_results['force_index'].iloc[current_idx]
        current_normalized_price = efi_results['normalized_price'].iloc[current_idx]

        # FILTER 1: Must be in UPTREND
        if current_trend != 'uptrend':
            return None

        # FILTER 2: EFI must show bullish momentum (positive or turning positive)
        efi_is_bullish = (
            current_fi_color in ['lime', 'green'] or
            (current_force_index > 0) or
            (current_force_index > -50 and current_normalized_price > -0.3)  # Improving
        )

        if not efi_is_bullish:
            return None

        # Look back to find which levels were violated and when
        lookback_start = max(0, current_idx - lookback_days)

        violations = []

        for level_name, (level_value, level_date, level_code) in key_levels.items():
            # Check if price went below this level recently
            for i in range(lookback_start, current_idx + 1):
                price_low = df['Low'].iloc[i]

                # For lows and opens, we look for price breaking BELOW
                if 'Low' in level_name or 'Open' in level_name:
                    if price_low < level_value:
                        violation_date = df.index[i]
                        violation_low = price_low
                        days_since = current_idx - i

                        # Check if we've recovered above the level
                        recovered = current_price > level_value

                        # Calculate violation depth
                        violation_depth_pct = ((level_value - violation_low) / level_value) * 100

                        # Get EFI at violation point
                        violation_fi_color = efi_results['fi_color'].iloc[i]
                        violation_force_index = efi_results['force_index'].iloc[i]

                        # Check for EFI reversal (was negative/red, now positive/green)
                        efi_reversed = False
                        if violation_fi_color in ['maroon', 'red', 'orange']:
                            if current_fi_color in ['lime', 'green', 'teal'] or current_force_index > 0:
                                efi_reversed = True

                        if efi_reversed:
                            violations.append({
                                'level_name': level_name,
                                'level_value': level_value,
                                'level_code': level_code,
                                'violation_date': violation_date,
                                'violation_low': violation_low,
                                'violation_depth_pct': violation_depth_pct,
                                'days_since': days_since,
                                'recovered': recovered,
                                'violation_fi_color': violation_fi_color,
                                'efi_reversed': efi_reversed
                            })

                        break  # Only track first violation of this level

        # FILTER 3: Must have at least one level violation with EFI reversal
        if not violations:
            return None

        # Find the most significant violation (deepest or most recent)
        best_violation = max(violations, key=lambda x: (x['violation_depth_pct'], -x['days_since']))

        # Calculate recovery metrics
        recovery_from_low_pct = ((current_price - best_violation['violation_low']) / best_violation['violation_low']) * 100
        distance_from_level_pct = ((current_price - best_violation['level_value']) / best_violation['level_value']) * 100

        # Count how many levels were violated
        levels_violated_count = len(violations)
        levels_recovered_count = sum(1 for v in violations if v['recovered'])

        # Signal strength scoring
        signal_strength = 0
        signal_notes = []

        # Stronger if recovered above the violated level
        if best_violation['recovered']:
            signal_strength += 3
            signal_notes.append("Reclaimed level")

        # Stronger if EFI is bullish green/lime
        if current_fi_color in ['lime', 'green']:
            signal_strength += 3
            signal_notes.append("EFI bullish")
        elif current_force_index > 0:
            signal_strength += 2
            signal_notes.append("FI positive")

        # Stronger if reversal is quick
        if best_violation['days_since'] <= 10:
            signal_strength += 2
            signal_notes.append("Quick reversal")
        elif best_violation['days_since'] <= 20:
            signal_strength += 1

        # Stronger if big recovery
        if recovery_from_low_pct > 5:
            signal_strength += 2
            signal_notes.append("Strong bounce")
        elif recovery_from_low_pct > 2:
            signal_strength += 1

        # Stronger if violation was deep
        if best_violation['violation_depth_pct'] > 3:
            signal_strength += 2
            signal_notes.append("Deep shakeout")
        elif best_violation['violation_depth_pct'] > 1:
            signal_strength += 1

        # Stronger if multiple levels were violated and recovered
        if levels_violated_count > 1:
            signal_strength += 1
            signal_notes.append(f"{levels_violated_count} levels hit")

        # Only keep signals with strength >= 5
        if signal_strength < 5:
            return None

        # Prepare levels summary
        levels_violated = [v['level_code'] for v in violations[:3]]  # Top 3

        return {
            'ticker': ticker_symbol,
            'current_date': current_date,
            'current_price': current_price,
            'current_fi_color': current_fi_color,
            'current_force_index': current_force_index,
            'current_normalized_price': current_normalized_price,
            'best_violation': best_violation,
            'levels_violated_count': levels_violated_count,
            'levels_recovered_count': levels_recovered_count,
            'levels_violated': levels_violated,
            'recovery_from_low_pct': recovery_from_low_pct,
            'distance_from_level_pct': distance_from_level_pct,
            'signal_strength': signal_strength,
            'signal_notes': signal_notes,
            'trend': current_trend,
            'all_violations': violations
        }

    except Exception as e:
        print(f"Error scanning {ticker_symbol}: {e}")
        return None

def run_multi_month_reversal_scan(lookback_days=30):
    """
    Run the Multi-Month Reversal scan across all tickers

    Args:
        lookback_days: Days to look back for violations (default 30)
    """
    print("=" * 80)
    print("MULTI-MONTH LEVEL REVERSAL SCANNER")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("SCANNING FOR:")
    print("  1. Price violated ANY level from previous 3 months")
    print("     (High, Low, Open, Close from each month)")
    print("  2. EFI reversed from negative to positive")
    print("  3. Stock in uptrend (pullback buy)")
    print()
    print("STRATEGY:")
    print("  Buy when price breaks key monthly levels, shakes out weak hands,")
    print("  then reverses with positive EFI momentum in uptrending stocks")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Scanning {len(tickers)} tickers...")
    print()

    # Scan all tickers
    all_setups = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers scanned...")

        result = detect_multi_month_reversal(ticker, results_dir, lookback_days)

        if result:
            all_setups.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(all_setups)} multi-month reversal setups")
    print()

    if not all_setups:
        print("No multi-month reversal setups found.")
        return

    # Sort by signal strength (best setups first)
    all_setups.sort(key=lambda x: x['signal_strength'], reverse=True)

    # Categorize by recovery status
    confirmed_reversals = [s for s in all_setups if s['best_violation']['recovered']]
    emerging_reversals = [s for s in all_setups if not s['best_violation']['recovered']]

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("MULTI-MONTH LEVEL REVERSAL SCANNER - RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("CONCEPT:")
    report_lines.append("  Scans previous 3 months' key levels (High/Low/Open/Close).")
    report_lines.append("  Finds stocks that violated these levels then reversed with")
    report_lines.append("  positive EFI momentum. More levels = more opportunities!")
    report_lines.append("")
    report_lines.append(f"Total Setups Found: {len(all_setups)}")
    report_lines.append(f"  Confirmed Reversals: {len(confirmed_reversals)} (Reclaimed level)")
    report_lines.append(f"  Emerging Reversals: {len(emerging_reversals)} (Still below but reversing)")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # TOP 25 BEST SETUPS
    report_lines.append("TOP 25 BEST SETUPS (Highest Signal Strength):")
    report_lines.append("=" * 80)
    report_lines.append(f"{'Ticker':<8} {'Price':<10} {'EFI':<10} {'Strength':<9} {'Level Hit':<12} {'Recovery%':<11} {'Days':<6}")
    report_lines.append("-" * 80)

    for setup in all_setups[:25]:
        level_code = setup['best_violation']['level_code']
        report_lines.append(
            f"{setup['ticker']:<8} "
            f"${setup['current_price']:<9.2f} "
            f"{setup['current_fi_color']:<10} "
            f"{setup['signal_strength']:<9} "
            f"{level_code:<12} "
            f"{setup['recovery_from_low_pct']:>9.2f}% "
            f"{setup['best_violation']['days_since']:<6}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # CONFIRMED REVERSALS
    if confirmed_reversals:
        report_lines.append("[STRONG BUY] CONFIRMED REVERSALS (Reclaimed Level):")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'Level':<12} {'Levels Hit':<15} {'Recovery%':<11} {'EFI':<10} {'Notes'}")
        report_lines.append("-" * 80)

        for setup in confirmed_reversals[:40]:  # Top 40
            levels_str = ",".join(setup['levels_violated'])
            notes_str = ", ".join(setup['signal_notes'][:2])
            report_lines.append(
                f"{setup['ticker']:<8} "
                f"${setup['current_price']:<9.2f} "
                f"{setup['best_violation']['level_code']:<12} "
                f"{levels_str:<15} "
                f"{setup['recovery_from_low_pct']:>9.2f}% "
                f"{setup['current_fi_color']:<10} "
                f"{notes_str}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # EMERGING REVERSALS
    if emerging_reversals:
        report_lines.append("[WATCH] EMERGING REVERSALS (Below Level, Reversing):")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'Level':<12} {'Below%':<10} {'Recovery%':<11} {'EFI':<10} {'Days':<6}")
        report_lines.append("-" * 80)

        for setup in emerging_reversals[:30]:  # Top 30
            report_lines.append(
                f"{setup['ticker']:<8} "
                f"${setup['current_price']:<9.2f} "
                f"{setup['best_violation']['level_code']:<12} "
                f"{setup['distance_from_level_pct']:>8.2f}% "
                f"{setup['recovery_from_low_pct']:>9.2f}% "
                f"{setup['current_fi_color']:<10} "
                f"{setup['best_violation']['days_since']:<6}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # MULTI-LEVEL VIOLATIONS (Stocks that hit multiple levels)
    multi_level_hits = [s for s in all_setups if s['levels_violated_count'] > 1]
    if multi_level_hits:
        multi_level_hits.sort(key=lambda x: x['levels_violated_count'], reverse=True)

        report_lines.append("MULTI-LEVEL HITS (Hit Multiple Monthly Levels):")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'Levels Hit':<12} {'Recovered':<10} {'All Levels':<40}")
        report_lines.append("-" * 80)

        for setup in multi_level_hits[:20]:  # Top 20
            all_levels_str = ",".join(setup['levels_violated'])
            report_lines.append(
                f"{setup['ticker']:<8} "
                f"${setup['current_price']:<9.2f} "
                f"{setup['levels_violated_count']:<12} "
                f"{setup['levels_recovered_count']}/{setup['levels_violated_count']:<9} "
                f"{all_levels_str[:40]}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # DETAILED TABLE
    report_lines.append("DETAILED ANALYSIS - ALL SETUPS:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Strength':<9} {'Violation Date':<14} {'Days':<6} {'Depth%':<8} {'Recovery%':<10} {'Level'}")
    report_lines.append("-" * 80)

    for setup in all_setups[:50]:  # Top 50
        report_lines.append(
            f"{setup['ticker']:<8} "
            f"{setup['signal_strength']:<9} "
            f"{setup['best_violation']['violation_date'].strftime('%Y-%m-%d'):<14} "
            f"{setup['best_violation']['days_since']:<6} "
            f"{setup['best_violation']['violation_depth_pct']:>6.2f}% "
            f"{setup['recovery_from_low_pct']:>8.2f}% "
            f"{setup['best_violation']['level_code']}"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("LEGEND:")
    report_lines.append("  Level Codes:")
    report_lines.append("    M1 = Most recent complete month")
    report_lines.append("    M2 = 2 months ago")
    report_lines.append("    M3 = 3 months ago")
    report_lines.append("    -Low, -Open, -Close, -High = The specific level violated")
    report_lines.append("")
    report_lines.append("  Metrics:")
    report_lines.append("    Depth%: How far below the level price went (bigger = more panic)")
    report_lines.append("    Recovery%: Bounce from violation low to current price")
    report_lines.append("    Below%: Current distance below level (negative = still below)")
    report_lines.append("    Levels Hit: Number of different monthly levels violated")
    report_lines.append("    Recovered: How many violated levels have been reclaimed")
    report_lines.append("")
    report_lines.append("TRADING STRATEGY:")
    report_lines.append("")
    report_lines.append("  [STRONG BUY] CONFIRMED REVERSALS:")
    report_lines.append("    - Price reclaimed the violated level")
    report_lines.append("    - EFI reversed from negative to positive")
    report_lines.append("    - Entry: Buy now or on pullback to reclaimed level")
    report_lines.append("    - Stop: Below violation low")
    report_lines.append("    - Target: Next monthly high or 2R+")
    report_lines.append("")
    report_lines.append("  [WATCH] EMERGING REVERSALS:")
    report_lines.append("    - Price still below level but EFI reversing")
    report_lines.append("    - Early reversal signal forming")
    report_lines.append("    - Action: Add to watchlist")
    report_lines.append("    - Entry: When price reclaims the level with volume")
    report_lines.append("")
    report_lines.append("  MULTI-LEVEL HITS:")
    report_lines.append("    - Violated multiple monthly levels = severe shakeout")
    report_lines.append("    - If recovering, these can be explosive moves")
    report_lines.append("    - Higher risk, higher reward setups")
    report_lines.append("")
    report_lines.append("WHY THIS WORKS:")
    report_lines.append("  Monthly levels represent key institutional price memory.")
    report_lines.append("  Breaks create panic selling from weak hands. When EFI")
    report_lines.append("  reverses positive, it signals smart money accumulation.")
    report_lines.append("  In uptrends, these reversals often produce V-shaped recoveries.")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Create TradingView lists
    create_tradingview_lists(confirmed_reversals, emerging_reversals, all_setups[:25], multi_level_hits[:20] if multi_level_hits else [])

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")

def create_tradingview_lists(confirmed_reversals, emerging_reversals, top_25, multi_level):
    """Create TradingView watchlists for different categories"""

    # Confirmed Reversals
    with open(os.path.join(buylist_dir, 'tradingview_multimonth_confirmed.txt'), 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("MULTI-MONTH REVERSALS - CONFIRMED (Strong Buy)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(confirmed_reversals)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        if confirmed_reversals:
            tickers = [s['ticker'] for s in confirmed_reversals]
            f.write(",".join(tickers) + "\n\n")
            f.write("-" * 80 + "\n\n")
            f.write("Individual symbols (one per line):\n")
            f.write("-" * 80 + "\n")
            for ticker in tickers:
                f.write(ticker + "\n")

    # Emerging Reversals
    with open(os.path.join(buylist_dir, 'tradingview_multimonth_emerging.txt'), 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("MULTI-MONTH REVERSALS - EMERGING (Watch List)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(emerging_reversals)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        if emerging_reversals:
            tickers = [s['ticker'] for s in emerging_reversals]
            f.write(",".join(tickers) + "\n\n")
            f.write("-" * 80 + "\n\n")
            f.write("Individual symbols (one per line):\n")
            f.write("-" * 80 + "\n")
            for ticker in tickers:
                f.write(ticker + "\n")

    # Top 25
    with open(os.path.join(buylist_dir, 'tradingview_multimonth_top25.txt'), 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("MULTI-MONTH REVERSALS - TOP 25 BEST SETUPS\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(top_25)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        if top_25:
            tickers = [s['ticker'] for s in top_25]
            f.write(",".join(tickers) + "\n\n")
            f.write("-" * 80 + "\n\n")
            f.write("Individual symbols (one per line):\n")
            f.write("-" * 80 + "\n")
            for ticker in tickers:
                f.write(ticker + "\n")

    # Multi-Level Hits
    if multi_level:
        with open(os.path.join(buylist_dir, 'tradingview_multimonth_multilevel.txt'), 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("MULTI-MONTH REVERSALS - MULTI-LEVEL HITS (Extreme Shakeouts)\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total symbols: {len(multi_level)}\n")
            f.write("=" * 80 + "\n\n")
            f.write("Copy the line below and paste into TradingView watchlist:\n")
            f.write("-" * 80 + "\n\n")

            tickers = [s['ticker'] for s in multi_level]
            f.write(",".join(tickers) + "\n\n")
            f.write("-" * 80 + "\n\n")
            f.write("Individual symbols (one per line):\n")
            f.write("-" * 80 + "\n")
            for ticker in tickers:
                f.write(ticker + "\n")

if __name__ == "__main__":
    # You can adjust lookback_days (default 30 trading days)
    run_multi_month_reversal_scan(lookback_days=30)
