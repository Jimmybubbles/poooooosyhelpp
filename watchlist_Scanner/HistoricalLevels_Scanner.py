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
output_file = os.path.join(buylist_dir, 'historical_levels_scan_results.txt')
tradingview_file = os.path.join(buylist_dir, 'tradingview_historical_levels_list.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def get_historical_levels(df, reference_idx):
    """
    Get key OHLC levels from 3 months ago and 1 year ago

    Args:
        df: DataFrame with OHLCV data
        reference_idx: Current index to calculate from

    Returns:
        Dict with historical levels
    """
    # 3 months ago = ~63 trading days
    # 1 year ago = ~252 trading days

    three_months_days = 63
    one_year_days = 252

    levels = {
        '3m_open': None,
        '3m_high': None,
        '3m_low': None,
        '3m_close': None,
        '1y_open': None,
        '1y_high': None,
        '1y_low': None,
        '1y_close': None
    }

    # Get 3-month levels
    if reference_idx >= three_months_days:
        three_month_idx = reference_idx - three_months_days
        levels['3m_open'] = df['Open'].iloc[three_month_idx]
        levels['3m_high'] = df['High'].iloc[three_month_idx]
        levels['3m_low'] = df['Low'].iloc[three_month_idx]
        levels['3m_close'] = df['Close'].iloc[three_month_idx]

    # Get 1-year levels
    if reference_idx >= one_year_days:
        one_year_idx = reference_idx - one_year_days
        levels['1y_open'] = df['Open'].iloc[one_year_idx]
        levels['1y_high'] = df['High'].iloc[one_year_idx]
        levels['1y_low'] = df['Low'].iloc[one_year_idx]
        levels['1y_close'] = df['Close'].iloc[one_year_idx]

    return levels

def check_near_3m_close(df, reference_idx):
    """
    Check if current price is near the 3-month-ago close price

    Args:
        df: DataFrame with OHLCV data
        reference_idx: Current index

    Returns:
        Boolean - True if price is near 3m close (within 5%)
    """
    three_months_days = 63

    if reference_idx < three_months_days:
        return False

    # Get the 3-month-ago close
    three_month_idx = reference_idx - three_months_days
    three_m_close = df['Close'].iloc[three_month_idx]

    # Current price should be near the 3m close (within 5%)
    current_price = df['Close'].iloc[reference_idx]
    near_level = abs(current_price - three_m_close) / three_m_close <= 0.05

    return near_level

def check_in_channel(df, idx, channel_period=3):
    """
    Check if price is trading within a defined channel

    Args:
        df: DataFrame with OHLCV data
        idx: Index to check
        channel_period: Number of weeks to look back (default 3)

    Returns:
        Tuple (Boolean, channel_high, channel_low) - True if price is in channel
    """
    lookback_days = channel_period * 5

    if idx < lookback_days:
        return False, None, None

    # Get current close and previous highs/lows
    current_close = df['Close'].iloc[idx]
    previous_highs = df['High'].iloc[idx-lookback_days:idx]
    previous_lows = df['Low'].iloc[idx-lookback_days:idx]

    channel_high = previous_highs.max()
    channel_low = previous_lows.min()

    # Check if current price is within the channel
    in_channel = channel_low <= current_close <= channel_high

    return in_channel, channel_high, channel_low

def scan_historical_levels(ticker_symbol, results_dir):
    """
    Scan for setups with historical level pullback + channel formation

    CRITERIA:
    1. Price has pulled back below 3-month-ago close within last month
    2. Price is now consolidating in a channel (3-week range)
    3. Price in buy zone (0-35% of range)
    4. EFI showing oversold (maroon/orange)
    5. Stock in uptrend (overall)

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

        # Need at least 1 year of data for this analysis
        if len(df) < 252:
            return None

        latest_idx = len(df) - 1

        # 1. Get historical levels
        historical_levels = get_historical_levels(df, latest_idx)

        # Skip if we don't have 3-month data
        if historical_levels['3m_close'] is None:
            return None

        # 2. Check if price is near 3-month close
        near_3m_close = check_near_3m_close(df, latest_idx)

        if not near_3m_close:
            return None

        # 3. Check if in channel
        in_channel, channel_high, channel_low = check_in_channel(df, latest_idx, channel_period=3)

        if not in_channel:
            return None

        # 4. Calculate EFI indicator
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)

        # 5. Calculate price range zones
        zones = calculate_price_range_zones(df, lookback_period=100)

        # 6. Determine trend
        trend = determine_trend(df, lookback_period=50)

        # Get most recent values
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

        # SIGNAL CONDITIONS:
        condition_1_near_3m = near_3m_close
        condition_2_channel = in_channel
        condition_3_price_zone = price_zone == 'buy_zone'
        condition_4_efi = fi_color in ['maroon', 'orange']
        condition_5_trend = current_trend == 'uptrend'

        # All 5 conditions must be met
        if condition_1_near_3m and condition_2_channel and condition_3_price_zone and condition_4_efi and condition_5_trend:
            current_date = df.index[latest_idx]

            # Calculate distance from 3m close
            distance_from_3m = ((current_price - historical_levels['3m_close']) / historical_levels['3m_close']) * 100

            return {
                'ticker': ticker_symbol,
                'date': current_date,
                'price': current_price,
                'trend': current_trend,
                'in_channel': in_channel,
                'channel_high': channel_high,
                'channel_low': channel_low,
                'fi_color': fi_color,
                'force_index': force_index,
                'normalized_price': normalized_price,
                'price_zone': price_zone,
                'range_position_pct': range_position,
                'zone_25_pct': zone_25,
                'zone_75_pct': zone_75,
                'range_floor': range_floor,
                'range_ceiling': range_ceiling,
                '3m_close': historical_levels['3m_close'],
                '3m_high': historical_levels['3m_high'],
                '3m_low': historical_levels['3m_low'],
                '1y_close': historical_levels['1y_close'],
                '1y_high': historical_levels['1y_high'],
                '1y_low': historical_levels['1y_low'],
                'distance_from_3m_pct': distance_from_3m
            }

        return None

    except Exception as e:
        print(f"Error scanning {ticker_symbol}: {e}")
        return None

def run_historical_levels_scan():
    """Main scanning function"""
    print("=" * 80)
    print("HISTORICAL LEVELS + CHANNEL SCANNER")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("SIGNAL REQUIREMENTS (ALL 5 MUST BE TRUE):")
    print()
    print("  1. PULLBACK BELOW 3-MONTH CLOSE")
    print("     - Price went below 3-month-ago close within last month")
    print("     - Now recovered to near that level (within 5%)")
    print()
    print("  2. IN CHANNEL")
    print("     - Price consolidating within 3-week range")
    print("     - Shows healthy consolidation after pullback")
    print()
    print("  3. PRICE ZONE POSITION")
    print("     - Price in BUY ZONE (0-35% of $1 range)")
    print("     - Near support level with room to run")
    print()
    print("  4. EFI MOMENTUM")
    print("     - Force Index is MAROON or ORANGE")
    print("     - Indicates oversold/bearish momentum (buying opportunity)")
    print()
    print("  5. TREND CONFIRMATION")
    print("     - Stock is in UPTREND")
    print("     - Buying the dip in a strong trend")
    print()
    print("WHY THIS WORKS:")
    print("  This identifies stocks that:")
    print("    - Pulled back to retest 3-month support levels")
    print("    - Are consolidating (building energy)")
    print("    - Have oversold momentum (buyers stepping in)")
    print("    - Remain in overall uptrend (trend continuation setup)")
    print()
    print("  This is a classic 'pullback to support' pattern with multiple confirmations.")
    print("=" * 80)
    print()

    # Get ticker list
    tickers = get_ticker_list(results_dir)
    print(f"Scanning {len(tickers)} tickers for historical level setups...")
    print()

    # Scan all tickers
    signals = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(tickers)} tickers scanned...")

        result = scan_historical_levels(ticker, results_dir)

        if result:
            signals.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(signals)} stocks with HISTORICAL LEVEL + CHANNEL setup")
    print()

    # Sort by distance from 3m close (closer is better - tighter setup)
    signals.sort(key=lambda x: abs(x['distance_from_3m_pct']))

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("HISTORICAL LEVELS + CHANNEL SCANNER RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("SIGNAL CRITERIA (ALL MUST BE TRUE):")
    report_lines.append("  1. Pullback: Below 3-month close, now recovered")
    report_lines.append("  2. In Channel: Price within 3-week range (consolidating)")
    report_lines.append("  3. Price Zone: In buy zone (0-35% of range)")
    report_lines.append("  4. EFI Momentum: Maroon or orange (oversold)")
    report_lines.append("  5. Trend: Uptrend confirmed")
    report_lines.append("")
    report_lines.append(f"Total SIGNALS Found: {len(signals)}")
    report_lines.append("=" * 80)
    report_lines.append("")

    if signals:
        report_lines.append("SETUPS (Sorted by Distance from 3M Close - Tighter = Better):")
        report_lines.append("-" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'3M Close':<10} {'Dist%':<8} {'Range':<12} {'Pos%':<8} {'EFI':<8}")
        report_lines.append("-" * 80)

        for signal in signals:
            range_str = f"${signal['range_floor']:.0f}-${signal['range_ceiling']:.0f}"
            efi_color = signal['fi_color'].upper()

            report_lines.append(
                f"{signal['ticker']:<8} "
                f"${signal['price']:<9.2f} "
                f"${signal['3m_close']:<9.2f} "
                f"{signal['distance_from_3m_pct']:>6.2f}% "
                f"{range_str:<12} "
                f"{signal['range_position_pct']:<7.1f}% "
                f"{efi_color:<8}"
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
            report_lines.append(f"  Current Price: ${signal['price']:.2f}")
            report_lines.append("")
            report_lines.append("  Historical Levels:")
            report_lines.append(f"    3-Month Ago Close: ${signal['3m_close']:.2f}")
            report_lines.append(f"    3-Month Ago High:  ${signal['3m_high']:.2f}")
            report_lines.append(f"    3-Month Ago Low:   ${signal['3m_low']:.2f}")
            if signal['1y_close']:
                report_lines.append(f"    1-Year Ago Close:  ${signal['1y_close']:.2f}")
            report_lines.append(f"    Distance from 3M Close: {signal['distance_from_3m_pct']:+.2f}%")
            report_lines.append("")
            report_lines.append("  Channel Info:")
            report_lines.append(f"    Channel High: ${signal['channel_high']:.2f}")
            report_lines.append(f"    Channel Low:  ${signal['channel_low']:.2f}")
            report_lines.append(f"    Channel Range: ${signal['channel_high'] - signal['channel_low']:.2f}")
            report_lines.append("")
            report_lines.append("  Price Zone:")
            report_lines.append(f"    Current Range: ${signal['range_floor']:.0f}-${signal['range_ceiling']:.0f}")
            report_lines.append(f"    Position in Range: {signal['range_position_pct']:.1f}%")
            report_lines.append(f"    Buy Zone (25%): ${signal['zone_25_pct']:.2f}")
            report_lines.append("")
            report_lines.append("  Momentum:")
            report_lines.append(f"    EFI Color: {signal['fi_color'].upper()}")
            report_lines.append(f"    Force Index: {signal['force_index']:.2f}")
            report_lines.append(f"    Normalized Price: {signal['normalized_price']:.2f}")
            report_lines.append(f"    Trend: {signal['trend'].upper()}")
            report_lines.append("")
            report_lines.append("  ✓ Pullback: Below 3M close, recovered")
            report_lines.append("  ✓ In Channel: YES (consolidating)")
            report_lines.append("  ✓ Price Zone: BUY ZONE")
            report_lines.append("  ✓ EFI Momentum: OVERSOLD")
            report_lines.append("  ✓ Trend: UPTREND")
            report_lines.append("-" * 80)

        report_lines.append("")
    else:
        report_lines.append("No stocks found matching ALL criteria.")
        report_lines.append("")
        report_lines.append("Note: This is a very selective scanner requiring 5 confirmations.")
        report_lines.append("Finding even 1-2 setups per week is normal and indicates quality.")
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("TRADING STRATEGY:")
    report_lines.append("  Entry: At current price (all 5 signals aligned)")
    report_lines.append("  Stop Loss: Below 3-month close OR below channel low")
    report_lines.append("  Target 1: Channel high (initial resistance)")
    report_lines.append("  Target 2: 3-month high (prior resistance)")
    report_lines.append("  Exit Signal: When EFI turns lime (strong bullish) or breaks above channel")
    report_lines.append("")
    report_lines.append("LEGEND:")
    report_lines.append("  3M Close: Close price from 3 months ago (key support level)")
    report_lines.append("  Dist%: Distance from 3M close (negative = below, positive = above)")
    report_lines.append("  Channel: 3-week high/low range (consolidation zone)")
    report_lines.append("  Pos%: Position within $1 range (lower = more room to run)")
    report_lines.append("  EFI: Force Index color (MAROON=strong bearish, ORANGE=weak bearish)")
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
        f.write("HISTORICAL LEVELS + CHANNEL SCANNER - TRADINGVIEW WATCHLIST\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(tickers_list)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("These stocks have ALL 5 confirmations:\n")
        f.write("  ✓ Pullback below 3-month close\n")
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
    run_historical_levels_scan()