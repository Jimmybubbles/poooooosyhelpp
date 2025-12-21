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
output_file = os.path.join(buylist_dir, 'triple_signal_scan_results.txt')
tradingview_file = os.path.join(buylist_dir, 'tradingview_triple_signal_list.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def check_in_channel(df, channel_period=3):
    """
    Check if price is trading within a defined channel

    Returns True if:
    - Price is contained within the high/low range of previous N periods

    Args:
        df: DataFrame with OHLCV data
        channel_period: Number of weeks to look back (default 3)

    Returns:
        Boolean - True if price is in channel
    """
    if len(df) < channel_period * 5:  # Need at least N weeks of data (5 trading days per week)
        return False

    # Calculate lookback period in days (approximately)
    lookback_days = channel_period * 5

    # Get current close and previous highs/lows
    current_close = df['Close'].iloc[-1]
    previous_highs = df['High'].iloc[-(lookback_days+1):-1]  # Previous N periods, excluding current
    previous_lows = df['Low'].iloc[-(lookback_days+1):-1]

    channel_high = previous_highs.max()
    channel_low = previous_lows.min()

    # Check if current price is within the channel
    if channel_low <= current_close <= channel_high:
        return True

    return False

def scan_triple_signal(ticker_symbol, results_dir):
    """
    Scan for TRIPLE CONFIRMATION signal:

    1. IN CHANNEL: Price is consolidating within 3-week channel
    2. PRICE ZONE: Price in buy zone (0-35% of $1 range)
    3. EFI MOMENTUM: Force Index is maroon or orange (bearish/oversold)
    4. TREND: Uptrend (buying the dip in strong trend)

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files

    Returns:
        Dict with signal information or None
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
            return None

        # 1. Check if price is in channel
        in_channel = check_in_channel(df, channel_period=3)

        # 2. Calculate EFI indicator
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)

        # 3. Calculate price range zones
        zones = calculate_price_range_zones(df, lookback_period=100)

        # 4. Determine trend
        trend = determine_trend(df, lookback_period=50)

        # Get most recent values
        latest_idx = -1
        fi_color = efi_results['fi_color'].iloc[latest_idx]
        normalized_price = efi_results['normalized_price'].iloc[latest_idx]
        force_index = efi_results['force_index'].iloc[latest_idx]

        current_price = df['Close'].iloc[latest_idx]
        price_zone = zones['price_zone'].iloc[latest_idx]
        current_trend = trend.iloc[latest_idx]
        range_position = zones['range_position_pct'].iloc[latest_idx]
        zone_25 = zones['zone_25_pct'].iloc[latest_idx]
        zone_75 = zones['zone_75_pct'].iloc[latest_idx]
        range_floor = zones['range_floor'].iloc[latest_idx]
        range_ceiling = zones['range_ceiling'].iloc[latest_idx]

        # TRIPLE SIGNAL CONDITIONS:
        condition_1_channel = in_channel
        condition_2_price_zone = price_zone == 'buy_zone'
        condition_3_efi = fi_color in ['maroon', 'orange']  # Bearish/oversold momentum
        condition_4_trend = current_trend == 'uptrend'

        # All 4 conditions must be met
        if condition_1_channel and condition_2_price_zone and condition_3_efi and condition_4_trend:
            current_date = df.index[latest_idx]

            return {
                'ticker': ticker_symbol,
                'date': current_date,
                'price': current_price,
                'trend': current_trend,
                'in_channel': in_channel,
                'fi_color': fi_color,
                'force_index': force_index,
                'normalized_price': normalized_price,
                'price_zone': price_zone,
                'range_position_pct': range_position,
                'zone_25_pct': zone_25,
                'zone_75_pct': zone_75,
                'range_floor': range_floor,
                'range_ceiling': range_ceiling
            }

        return None

    except Exception as e:
        print(f"Error scanning {ticker_symbol}: {e}")
        return None

def run_triple_scan():
    """Main scanning function"""
    print("=" * 80)
    print("TRIPLE SIGNAL SCANNER - ULTIMATE BUY SETUP")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("SIGNAL REQUIREMENTS (ALL 4 MUST BE TRUE):")
    print()
    print("  1. IN CHANNEL")
    print("     - Price consolidating within 3-week range")
    print("     - Shows price containment and range-bound behavior")
    print()
    print("  2. PRICE ZONE POSITION")
    print("     - Price in BUY ZONE (0-35% of $1 range)")
    print("     - Near support level with room to run")
    print()
    print("  3. EFI MOMENTUM")
    print("     - Force Index is MAROON or ORANGE")
    print("     - Indicates oversold/bearish momentum (buying opportunity)")
    print()
    print("  4. TREND CONFIRMATION")
    print("     - Stock is in UPTREND")
    print("     - Buying the dip in a strong trend")
    print()
    print("WHY THIS WORKS:")
    print("  Four independent confirmation signals reduce false positives.")
    print("  Each signal validates different aspects of the setup:")
    print("    - Channel: Price consolidation (not overextended)")
    print("    - Zone: Risk/reward positioning")
    print("    - EFI: Momentum exhaustion (reversal point)")
    print("    - Trend: Overall direction (buying dips in uptrend)")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Scanning {len(tickers)} tickers for TRIPLE signals...")
    print()

    # Scan all tickers
    signals = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers scanned...")

        result = scan_triple_signal(ticker, results_dir)

        if result:
            signals.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(signals)} stocks with TRIPLE SIGNAL confirmation")
    print()

    # Sort by range position (lower is better - more room to run)
    signals.sort(key=lambda x: x['range_position_pct'])

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("TRIPLE SIGNAL SCANNER - ULTIMATE BUY SETUP RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("SIGNAL CRITERIA (ALL MUST BE TRUE):")
    report_lines.append("  1. In Channel: Price within 3-week range (consolidating)")
    report_lines.append("  2. Price Zone: In buy zone (0-35% of range)")
    report_lines.append("  3. EFI Momentum: Maroon or orange (oversold)")
    report_lines.append("  4. Trend: Uptrend confirmed")
    report_lines.append("")
    report_lines.append(f"Total TRIPLE SIGNALS Found: {len(signals)}")
    report_lines.append("=" * 80)
    report_lines.append("")

    if signals:
        report_lines.append("TRIPLE SIGNAL SETUPS (Sorted by Range Position - Lower = Better):")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Date':<12} {'Price':<10} {'Range':<12} {'Pos %':<8} {'EFI':<8} {'Force Idx':<12}")
        report_lines.append("-" * 80)

        for signal in signals:
            date_str = signal['date'].strftime('%m/%d/%Y')
            range_str = f"${signal['range_floor']:.0f}-${signal['range_ceiling']:.0f}"
            efi_color = signal['fi_color'].upper()

            report_lines.append(
                f"{signal['ticker']:<8} "
                f"{date_str:<12} "
                f"${signal['price']:<9.2f} "
                f"{range_str:<12} "
                f"{signal['range_position_pct']:<7.1f}% "
                f"{efi_color:<8} "
                f"{signal['force_index']:>11.2f}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")
        report_lines.append("DETAILED BREAKDOWN:")
        report_lines.append("-" * 80)

        for signal in signals:
            report_lines.append("")
            report_lines.append(f"TICKER: {signal['ticker']}")
            report_lines.append(f"  Date: {signal['date'].strftime('%Y-%m-%d')}")
            report_lines.append(f"  Price: ${signal['price']:.2f}")
            report_lines.append(f"  Range: ${signal['range_floor']:.0f}-${signal['range_ceiling']:.0f}")
            report_lines.append(f"  Position in Range: {signal['range_position_pct']:.1f}%")
            report_lines.append(f"  Buy Zone (25%): ${signal['zone_25_pct']:.2f}")
            report_lines.append(f"  EFI Color: {signal['fi_color'].upper()}")
            report_lines.append(f"  Force Index: {signal['force_index']:.2f}")
            report_lines.append(f"  Normalized Price: {signal['normalized_price']:.2f}")
            report_lines.append(f"  Trend: {signal['trend'].upper()}")
            report_lines.append(f"  ✓ In Channel: YES (consolidating)")
            report_lines.append(f"  ✓ Price Zone: BUY ZONE")
            report_lines.append(f"  ✓ EFI Momentum: OVERSOLD")
            report_lines.append(f"  ✓ Trend: UPTREND")
            report_lines.append("-" * 80)

        report_lines.append("")
    else:
        report_lines.append("No stocks found matching ALL criteria.")
        report_lines.append("")
        report_lines.append("Note: This is a very selective scanner requiring 4 confirmations.")
        report_lines.append("Finding even 1-2 setups per day is normal and indicates quality.")
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("TRADING STRATEGY:")
    report_lines.append("  Entry: At current price (all signals aligned)")
    report_lines.append("  Stop Loss: Below range floor (below support)")
    report_lines.append("  Target 1: 25% zone → 75% zone (range midpoint)")
    report_lines.append("  Target 2: Top of range (range ceiling)")
    report_lines.append("  Exit Signal: When EFI turns lime (strong bullish)")
    report_lines.append("")
    report_lines.append("LEGEND:")
    report_lines.append("  Ticker: Stock symbol")
    report_lines.append("  Date: Most recent trading date")
    report_lines.append("  Price: Current stock price")
    report_lines.append("  Range: $1 increment range (e.g., $2-$3)")
    report_lines.append("  Pos %: Position within range (lower = more room to run)")
    report_lines.append("  EFI: Force Index color (MAROON=strong bearish, ORANGE=weak bearish)")
    report_lines.append("  Force Idx: Force Index value (negative = bearish momentum)")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Create TradingView list
    create_tradingview_list(signals)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")
    print(f"TradingView list saved to: {tradingview_file}")

def create_tradingview_list(signals):
    """Create TradingView format watchlist"""
    tickers_list = [signal['ticker'] for signal in signals]

    with open(tradingview_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("TRIPLE SIGNAL SCANNER - TRADINGVIEW WATCHLIST\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(tickers_list)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("These stocks have ALL 4 confirmations:\n")
        f.write("  ✓ In Channel (consolidating)\n")
        f.write("  ✓ Price in Buy Zone\n")
        f.write("  ✓ EFI Oversold\n")
        f.write("  ✓ Uptrend\n")
        f.write("\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")
        f.write(",".join(tickers_list) + "\n\n")
        f.write("-" * 80 + "\n\n")
        f.write("Individual symbols (one per line):\n")
        f.write("-" * 80 + "\n")
        for ticker in tickers_list:
            f.write(ticker + "\n")

if __name__ == "__main__":
    run_triple_scan()