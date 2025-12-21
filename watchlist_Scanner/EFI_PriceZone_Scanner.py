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
output_file = os.path.join(buylist_dir, 'efi_pricezone_scan_results.txt')
tradingview_file = os.path.join(buylist_dir, 'tradingview_efi_pricezone_list.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def scan_ticker_combined(ticker_symbol, results_dir):
    """
    Scan a single ticker for combined EFI + Price Zone signals

    BUY SIGNAL CONDITIONS:
    1. Force Index is MAROON (strong bearish/oversold)
    2. Price is in BUY ZONE (0-35% of range)
    3. Trend is UPTREND (buying the dip in an uptrend)

    SELL SIGNAL CONDITIONS:
    1. Force Index is MAROON (strong bearish)
    2. Price is in SELL ZONE (65-100% of range)
    3. Trend is DOWNTREND (shorting the bounce in a downtrend)

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

        # Calculate EFI indicator
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)

        # Calculate price range zones
        zones = calculate_price_range_zones(df, lookback_period=100)

        # Determine trend
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

        # Check for BUY signal: Maroon + Buy Zone + Uptrend
        buy_condition_1 = fi_color == 'maroon'
        buy_condition_2 = price_zone == 'buy_zone'
        buy_condition_3 = current_trend == 'uptrend'

        # Check for SELL signal: Maroon + Sell Zone + Downtrend
        sell_condition_1 = fi_color == 'maroon'
        sell_condition_2 = price_zone == 'sell_zone'
        sell_condition_3 = current_trend == 'downtrend'

        signal_type = None

        if buy_condition_1 and buy_condition_2 and buy_condition_3:
            signal_type = 'BUY'
        elif sell_condition_1 and sell_condition_2 and sell_condition_3:
            signal_type = 'SELL'

        if signal_type:
            current_date = df.index[latest_idx]

            return {
                'ticker': ticker_symbol,
                'signal': signal_type,
                'date': current_date,
                'price': current_price,
                'trend': current_trend,
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

def run_combined_scan():
    """Main scanning function"""
    print("=" * 80)
    print("EFI + PRICE ZONE SCANNER - BUY SIGNALS ONLY")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("BUY SIGNAL CRITERIA:")
    print("  1. Force Index is MAROON (strong bearish/oversold)")
    print("  2. Price in BUY ZONE (0-35% of price range)")
    print("  3. Trend is UPTREND (buying the dip)")
    print()
    print("PRICE RANGE ZONES ($1 INCREMENTS):")
    print("  Under $10: $1 increments")
    print("    - $0-$1:   25% = $0.25")
    print("    - $1-$2:   25% = $1.25")
    print("    - $2-$3:   25% = $2.25")
    print("    - ... continues to $9-$10")
    print()
    print("  $10 and above: $10 increments")
    print("    - $10-$20:  25% = $12.50")
    print("    - $20-$30:  25% = $22.50")
    print("    - ... and so on")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Scanning {len(tickers)} tickers...")
    print()

    # Scan all tickers
    signals = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers scanned...")

        result = scan_ticker_combined(ticker, results_dir)

        if result:
            signals.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(signals)} stocks matching criteria")
    print()

    # Separate BUY and SELL signals
    buy_signals = [s for s in signals if s['signal'] == 'BUY']
    sell_signals = [s for s in signals if s['signal'] == 'SELL']

    # Sort by range position (lower is better for BUY, higher for SELL)
    buy_signals.sort(key=lambda x: x['range_position_pct'])
    sell_signals.sort(key=lambda x: x['range_position_pct'], reverse=True)

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("EFI + PRICE ZONE SCANNER RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("STRATEGY OVERVIEW:")
    report_lines.append("  This scanner combines TWO powerful signals:")
    report_lines.append("  1. EFI Maroon (oversold momentum)")
    report_lines.append("  2. Price Range Zones (dynamic support/resistance)")
    report_lines.append("")
    report_lines.append("BUY SIGNALS: Maroon + Buy Zone (0-35%) + Uptrend")
    report_lines.append("  -> Buying dips at support in an uptrend")
    report_lines.append("")
    report_lines.append("SELL SIGNALS: Maroon + Sell Zone (65-100%) + Downtrend")
    report_lines.append("  -> Shorting bounces at resistance in a downtrend")
    report_lines.append("")
    report_lines.append(f"Total BUY Signals: {len(buy_signals)}")
    report_lines.append(f"Total SELL Signals: {len(sell_signals)}")
    report_lines.append("=" * 80)
    report_lines.append("")

    # BUY SIGNALS
    if buy_signals:
        report_lines.append("BUY SIGNALS (Sorted by Range Position - Lower is Better):")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Date':<12} {'Price':<10} {'Range':<15} {'Pos %':<8} {'25% Zone':<10} {'Force Idx':<12}")
        report_lines.append("-" * 80)

        for signal in buy_signals:
            date_str = signal['date'].strftime('%m/%d/%Y')
            range_str = f"${signal['range_floor']:.0f}-${signal['range_ceiling']:.0f}"
            report_lines.append(
                f"{signal['ticker']:<8} "
                f"{date_str:<12} "
                f"${signal['price']:<9.2f} "
                f"{range_str:<15} "
                f"{signal['range_position_pct']:<7.1f}% "
                f"${signal['zone_25_pct']:<9.2f} "
                f"{signal['force_index']:>11.2f}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # SELL SIGNALS
    if sell_signals:
        report_lines.append("SELL SIGNALS (Sorted by Range Position - Higher is Better):")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Date':<12} {'Price':<10} {'Range':<15} {'Pos %':<8} {'75% Zone':<10} {'Force Idx':<12}")
        report_lines.append("-" * 80)

        for signal in sell_signals:
            date_str = signal['date'].strftime('%m/%d/%Y')
            range_str = f"${signal['range_floor']:.0f}-${signal['range_ceiling']:.0f}"
            report_lines.append(
                f"{signal['ticker']:<8} "
                f"{date_str:<12} "
                f"${signal['price']:<9.2f} "
                f"{range_str:<15} "
                f"{signal['range_position_pct']:<7.1f}% "
                f"${signal['zone_75_pct']:<9.2f} "
                f"{signal['force_index']:>11.2f}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    if not signals:
        report_lines.append("No stocks found matching the criteria.")
        report_lines.append("")

    report_lines.append("LEGEND:")
    report_lines.append("  Ticker: Stock symbol")
    report_lines.append("  Date: Most recent trading date")
    report_lines.append("  Price: Current stock price")
    report_lines.append("  Range: Power-of-10 price range (e.g., $10-$20)")
    report_lines.append("  Pos %: Position within range (0% = bottom, 100% = top)")
    report_lines.append("  25% Zone: Buy zone target (support level)")
    report_lines.append("  75% Zone: Sell zone target (resistance level)")
    report_lines.append("  Force Idx: Force Index value (negative = bearish)")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w') as f:
        f.write(report_text)

    # Create TradingView list (BUY signals only)
    create_tradingview_list(buy_signals)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")
    print(f"TradingView list (BUY signals) saved to: {tradingview_file}")

def create_tradingview_list(signals):
    """Create TradingView format watchlist for BUY signals"""
    tickers_list = [signal['ticker'] for signal in signals]

    with open(tradingview_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("EFI + PRICE ZONE SCANNER - TRADINGVIEW WATCHLIST (BUY SIGNALS)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(tickers_list)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")
        f.write(",".join(tickers_list) + "\n\n")
        f.write("-" * 80 + "\n\n")
        f.write("Individual symbols (one per line):\n")
        f.write("-" * 80 + "\n")
        for ticker in tickers_list:
            f.write(ticker + "\n")

if __name__ == "__main__":
    run_combined_scan()
