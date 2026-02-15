import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
import sys

# Add the watchlist_Scanner directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from EFI_Indicator import EFI_Indicator
from PriceRangeZones import determine_trend

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("Warning: yfinance not installed. Run 'pip install yfinance' for earnings data.")

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
buylist_dir = os.path.join(script_dir, 'buylist')
output_file = os.path.join(buylist_dir, 'shakeout_reversal_scan_results.txt')

def get_ticker_list(results_dir):
    """Get ticker symbols from CSV files in the results directory"""
    try:
        csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading results directory: {e}")
        return []

def get_earnings_date(ticker, days_ahead=5):
    """
    Get upcoming earnings date for a ticker using yfinance.

    Args:
        ticker: Stock ticker symbol
        days_ahead: Number of days to look ahead for earnings

    Returns:
        Earnings date if within days_ahead, None otherwise
    """
    if not YFINANCE_AVAILABLE:
        return None

    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            stock = yf.Ticker(ticker)
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            future_cutoff = today + timedelta(days=days_ahead)

            # Try to get earnings dates from calendar first (faster)
            try:
                calendar = stock.calendar
                if calendar is not None and not calendar.empty:
                    if 'Earnings Date' in calendar.index:
                        earnings_dates = calendar.loc['Earnings Date']
                        if isinstance(earnings_dates, pd.Series):
                            earnings_date = earnings_dates.iloc[0]
                        else:
                            earnings_date = earnings_dates

                        if pd.notna(earnings_date):
                            if isinstance(earnings_date, str):
                                earnings_date = pd.to_datetime(earnings_date)
                            elif hasattr(earnings_date, 'to_pydatetime'):
                                earnings_date = earnings_date.to_pydatetime()

                            if hasattr(earnings_date, 'tzinfo') and earnings_date.tzinfo is not None:
                                earnings_date = earnings_date.replace(tzinfo=None)

                            if today <= earnings_date <= future_cutoff:
                                return earnings_date
            except Exception:
                pass

    except Exception:
        pass

    return None

def check_earnings_batch(tickers, days_ahead=5):
    """
    Check earnings dates for a batch of tickers.

    Args:
        tickers: List of ticker symbols
        days_ahead: Number of days to look ahead

    Returns:
        Dictionary mapping ticker to earnings date (or None)
    """
    import sys
    earnings_dict = {}
    total = len(tickers)

    print(f"\nChecking earnings dates for {total} stocks (next {days_ahead} days)...")
    sys.stdout.flush()

    for i, ticker in enumerate(tickers):
        if (i + 1) % 25 == 0:
            print(f"  Earnings check progress: {i + 1}/{total}...", flush=True)

        earnings_date = get_earnings_date(ticker, days_ahead)
        if earnings_date:
            earnings_dict[ticker] = earnings_date
            print(f"    {ticker}: Earnings on {earnings_date.strftime('%m/%d/%Y')}", flush=True)

    print(f"  Found {len(earnings_dict)} stocks with earnings in next {days_ahead} days", flush=True)
    return earnings_dict

def detect_shakeout_reversal(ticker_symbol, results_dir, lookback_days=20):
    """
    Detect shakeout reversal setups:
    1. Price recently broke below previous month low/open (shakeout)
    2. EFI is now turning positive (reversal momentum)
    3. Stock is in uptrend (pullback buy, not falling knife)

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files
        lookback_days: Days to look back for the shakeout (default 20)

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

        # Need at least 6 months of data for monthly levels + indicators
        if len(df) < 126:
            return None

        # Calculate EFI indicator
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)

        # Calculate trend
        trend = determine_trend(df, lookback_period=50)

        # Resample to monthly data to get previous month levels
        monthly_df = df.resample('ME').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()

        if len(monthly_df) < 2:
            return None

        # Get PREVIOUS month's levels (index -2 because -1 is current incomplete month)
        prev_month = monthly_df.iloc[-2]
        prev_month_date = monthly_df.index[-2]
        prev_month_low = prev_month['Low']
        prev_month_open = prev_month['Open']
        prev_month_high = prev_month['High']

        # Current data (most recent)
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

        # Look back over recent days to find if there was a shakeout
        lookback_start = max(0, current_idx - lookback_days)
        recent_lows = df['Low'].iloc[lookback_start:current_idx + 1]

        # FILTER 2: Did price break below previous month low recently?
        shakeout_occurred = any(low < prev_month_low for low in recent_lows)

        if not shakeout_occurred:
            return None

        # Find when the shakeout happened (lowest point below prev month low)
        shakeout_indices = [i for i in range(lookback_start, current_idx + 1)
                           if df['Low'].iloc[i] < prev_month_low]

        if not shakeout_indices:
            return None

        shakeout_idx = shakeout_indices[-1]  # Most recent shakeout
        shakeout_date = df.index[shakeout_idx]
        shakeout_low = df['Low'].iloc[shakeout_idx]
        days_since_shakeout = current_idx - shakeout_idx

        # FILTER 3: EFI must be turning positive (reversal signal)
        # Check if current EFI is positive/green OR was recently negative and now improving
        efi_turning_positive = (
            current_fi_color in ['lime', 'green'] or
            (current_force_index > 0 and current_normalized_price > -0.3)
        )

        if not efi_turning_positive:
            return None

        # Check EFI momentum at shakeout vs now
        shakeout_fi_color = efi_results['fi_color'].iloc[shakeout_idx]
        shakeout_force_index = efi_results['force_index'].iloc[shakeout_idx]

        # Calculate recovery metrics
        recovery_from_shakeout_pct = ((current_price - shakeout_low) / shakeout_low) * 100
        distance_from_prev_month_low_pct = ((current_price - prev_month_low) / prev_month_low) * 100

        # Is price back above previous month low? (successful reversal)
        reclaimed_prev_month_low = current_price > prev_month_low

        # Signal strength scoring
        signal_strength = 0
        signal_notes = []

        # Stronger if price reclaimed prev month low
        if reclaimed_prev_month_low:
            signal_strength += 3
            signal_notes.append("Reclaimed prev month low")

        # Stronger if EFI is already green/lime
        if current_fi_color in ['lime', 'green']:
            signal_strength += 3
            signal_notes.append("EFI bullish (green/lime)")
        elif current_force_index > 0:
            signal_strength += 2
            signal_notes.append("Force Index positive")

        # Stronger if recovery is quick (within 10 days)
        if days_since_shakeout <= 10:
            signal_strength += 2
            signal_notes.append("Quick reversal")
        elif days_since_shakeout <= 15:
            signal_strength += 1

        # Stronger if big recovery from shakeout low
        if recovery_from_shakeout_pct > 5:
            signal_strength += 2
            signal_notes.append("Strong bounce")
        elif recovery_from_shakeout_pct > 2:
            signal_strength += 1

        # Stronger if shakeout was deep (more panic = better reversal)
        shakeout_depth_pct = ((prev_month_low - shakeout_low) / prev_month_low) * 100
        if shakeout_depth_pct > 3:
            signal_strength += 2
            signal_notes.append("Deep shakeout")
        elif shakeout_depth_pct > 1:
            signal_strength += 1

        # Only keep signals with strength >= 5 (decent setups)
        if signal_strength < 5:
            return None

        return {
            'ticker': ticker_symbol,
            'current_date': current_date,
            'current_price': current_price,
            'current_fi_color': current_fi_color,
            'current_force_index': current_force_index,
            'current_normalized_price': current_normalized_price,
            'prev_month_low': prev_month_low,
            'prev_month_open': prev_month_open,
            'prev_month_high': prev_month_high,
            'prev_month_date': prev_month_date,
            'shakeout_date': shakeout_date,
            'shakeout_low': shakeout_low,
            'shakeout_depth_pct': shakeout_depth_pct,
            'days_since_shakeout': days_since_shakeout,
            'shakeout_fi_color': shakeout_fi_color,
            'recovery_from_shakeout_pct': recovery_from_shakeout_pct,
            'distance_from_prev_month_low_pct': distance_from_prev_month_low_pct,
            'reclaimed_prev_month_low': reclaimed_prev_month_low,
            'signal_strength': signal_strength,
            'signal_notes': signal_notes,
            'trend': current_trend
        }

    except Exception as e:
        print(f"Error scanning {ticker_symbol}: {e}")
        return None

def run_shakeout_reversal_scan(lookback_days=20, earnings_filter_days=None):
    """
    Run the Shakeout Reversal scan across all tickers

    Args:
        lookback_days: Days to look back for shakeout (default 20)
        earnings_filter_days: If set, only show stocks with earnings in next N days (default None = no filter)
    """
    print("=" * 80)
    print("SHAKEOUT REVERSAL SCANNER")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("SCANNING FOR:")
    print("  1. Price broke below previous month low (shakeout)")
    print("  2. EFI turning positive (reversal momentum)")
    print("  3. Stock in uptrend (pullback buy)")
    if earnings_filter_days:
        print(f"  4. Earnings within next {earnings_filter_days} days")
    print()
    print("STRATEGY:")
    print("  Enter when weak hands get shaken out and smart money steps in")
    print("  Classic 'blood in the streets' reversal in uptrending stocks")
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

        result = detect_shakeout_reversal(ticker, results_dir, lookback_days)

        if result:
            all_setups.append(result)

    print()
    print(f"Scan complete!")
    print(f"Found {len(all_setups)} shakeout reversal setups")

    # Apply earnings filter if requested
    earnings_dict = {}
    if earnings_filter_days and YFINANCE_AVAILABLE:
        setup_tickers = [s['ticker'] for s in all_setups]
        earnings_dict = check_earnings_batch(setup_tickers, earnings_filter_days)

        # Filter to only stocks with upcoming earnings
        all_setups_with_earnings = []
        for setup in all_setups:
            if setup['ticker'] in earnings_dict:
                setup['earnings_date'] = earnings_dict[setup['ticker']]
                all_setups_with_earnings.append(setup)

        print(f"\nFiltered to {len(all_setups_with_earnings)} stocks with earnings in next {earnings_filter_days} days")
        all_setups = all_setups_with_earnings
    elif earnings_filter_days and not YFINANCE_AVAILABLE:
        print("\nWarning: yfinance not installed. Cannot filter by earnings.")
        print("Run: pip install yfinance")

    print()

    if not all_setups:
        print("No shakeout reversal setups found matching criteria.")
        return

    # Sort by signal strength (best setups first)
    all_setups.sort(key=lambda x: x['signal_strength'], reverse=True)

    # Categorize by stage
    confirmed_reversals = [s for s in all_setups if s['reclaimed_prev_month_low']]
    emerging_reversals = [s for s in all_setups if not s['reclaimed_prev_month_low']]

    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("SHAKEOUT REVERSAL SCANNER - RESULTS")
    report_lines.append("=" * 80)
    report_lines.append(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("CONCEPT:")
    report_lines.append("  Shakeout Reversal = Price breaks below prev month low (panic),")
    report_lines.append("  then reverses with positive EFI momentum in an uptrend.")
    report_lines.append("  This catches the exact moment weak hands sell to strong hands.")
    report_lines.append("")
    report_lines.append(f"Total Setups Found: {len(all_setups)}")
    report_lines.append(f"  Confirmed Reversals: {len(confirmed_reversals)} (Price reclaimed prev month low)")
    report_lines.append(f"  Emerging Reversals: {len(emerging_reversals)} (Still below but reversing)")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Check if we have earnings data
    has_earnings_data = any('earnings_date' in s for s in all_setups)

    # TOP 20 BEST SETUPS (by signal strength)
    report_lines.append("TOP 20 BEST SETUPS (Highest Signal Strength):")
    report_lines.append("=" * 100)
    if has_earnings_data:
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'EFI':<10} {'Strength':<9} {'Recovery%':<11} {'Days':<6} {'Earnings':<12} {'Status':<15}")
    else:
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'EFI':<10} {'Strength':<9} {'Recovery%':<11} {'Days':<6} {'Status':<20}")
    report_lines.append("-" * 100)

    for setup in all_setups[:20]:
        status = "RECLAIMED" if setup['reclaimed_prev_month_low'] else "EMERGING"
        earnings_str = ""
        if 'earnings_date' in setup and setup['earnings_date']:
            earnings_str = setup['earnings_date'].strftime('%m/%d/%Y')

        if has_earnings_data:
            report_lines.append(
                f"{setup['ticker']:<8} "
                f"${setup['current_price']:<9.2f} "
                f"{setup['current_fi_color']:<10} "
                f"{setup['signal_strength']:<9} "
                f"{setup['recovery_from_shakeout_pct']:>9.2f}% "
                f"{setup['days_since_shakeout']:<6} "
                f"{earnings_str:<12} "
                f"{status}"
            )
        else:
            report_lines.append(
                f"{setup['ticker']:<8} "
                f"${setup['current_price']:<9.2f} "
                f"{setup['current_fi_color']:<10} "
                f"{setup['signal_strength']:<9} "
                f"{setup['recovery_from_shakeout_pct']:>9.2f}% "
                f"{setup['days_since_shakeout']:<6} "
                f"{status}"
            )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")

    # CONFIRMED REVERSALS - Price reclaimed prev month low
    if confirmed_reversals:
        report_lines.append("[STRONG BUY] CONFIRMED REVERSALS (Reclaimed Prev Month Low):")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'M-Low':<10} {'Shakeout$':<11} {'Recovery%':<11} {'EFI':<10} {'Notes'}")
        report_lines.append("-" * 80)

        for setup in confirmed_reversals:
            notes_str = ", ".join(setup['signal_notes'][:2])  # First 2 notes
            report_lines.append(
                f"{setup['ticker']:<8} "
                f"${setup['current_price']:<9.2f} "
                f"${setup['prev_month_low']:<9.2f} "
                f"${setup['shakeout_low']:<10.2f} "
                f"{setup['recovery_from_shakeout_pct']:>9.2f}% "
                f"{setup['current_fi_color']:<10} "
                f"{notes_str}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # EMERGING REVERSALS - Still below prev month low but reversing
    if emerging_reversals:
        report_lines.append("[WATCH] EMERGING REVERSALS (Below Prev Month Low, Reversing):")
        report_lines.append("=" * 80)
        report_lines.append(f"{'Ticker':<8} {'Price':<10} {'M-Low':<10} {'Below%':<10} {'Recovery%':<11} {'EFI':<10} {'Days':<6}")
        report_lines.append("-" * 80)

        for setup in emerging_reversals:
            report_lines.append(
                f"{setup['ticker']:<8} "
                f"${setup['current_price']:<9.2f} "
                f"${setup['prev_month_low']:<9.2f} "
                f"{setup['distance_from_prev_month_low_pct']:>8.2f}% "
                f"{setup['recovery_from_shakeout_pct']:>9.2f}% "
                f"{setup['current_fi_color']:<10} "
                f"{setup['days_since_shakeout']:<6}"
            )

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")

    # DETAILED TABLE - All setups with full info
    report_lines.append("DETAILED ANALYSIS - ALL SETUPS:")
    report_lines.append("-" * 80)
    report_lines.append(f"{'Ticker':<8} {'Strength':<9} {'Shakeout Date':<14} {'Days Ago':<9} {'Depth%':<8} {'Recovery%':<10}")
    report_lines.append("-" * 80)

    for setup in all_setups:
        report_lines.append(
            f"{setup['ticker']:<8} "
            f"{setup['signal_strength']:<9} "
            f"{setup['shakeout_date'].strftime('%Y-%m-%d'):<14} "
            f"{setup['days_since_shakeout']:<9} "
            f"{setup['shakeout_depth_pct']:>6.2f}% "
            f"{setup['recovery_from_shakeout_pct']:>8.2f}%"
        )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append("LEGEND:")
    report_lines.append("  Price: Current stock price")
    report_lines.append("  M-Low: Previous month low (the level that was broken)")
    report_lines.append("  Shakeout$: Lowest price during the shakeout")
    report_lines.append("  Depth%: How far below prev month low the shakeout went (bigger = more panic)")
    report_lines.append("  Recovery%: How much price bounced from shakeout low")
    report_lines.append("  Below%: Current distance below prev month low (negative = still below)")
    report_lines.append("  Days: Days since the shakeout occurred")
    report_lines.append("  EFI: Current Elder Force Index color")
    report_lines.append("  Strength: Signal strength score (higher = better setup)")
    report_lines.append("")
    report_lines.append("TRADING STRATEGY:")
    report_lines.append("")
    report_lines.append("  [STRONG BUY] CONFIRMED REVERSALS:")
    report_lines.append("    - Price has reclaimed previous month low")
    report_lines.append("    - EFI turning positive = momentum shifting bullish")
    report_lines.append("    - Entry: Buy on confirmation, stop below shakeout low")
    report_lines.append("    - Target: Previous month high or beyond")
    report_lines.append("")
    report_lines.append("  [WATCH] EMERGING REVERSALS:")
    report_lines.append("    - Price still below prev month low but reversing")
    report_lines.append("    - EFI improving = early reversal signal")
    report_lines.append("    - Action: Add to watchlist, wait for price to reclaim prev month low")
    report_lines.append("    - Entry: On break above prev month low with confirmation")
    report_lines.append("")
    report_lines.append("SIGNAL STRENGTH SCORING:")
    report_lines.append("  Points awarded for:")
    report_lines.append("    - Reclaimed prev month low (+3)")
    report_lines.append("    - EFI bullish green/lime (+3)")
    report_lines.append("    - Force Index positive (+2)")
    report_lines.append("    - Quick reversal (<10 days: +2, <15 days: +1)")
    report_lines.append("    - Strong bounce (>5%: +2, >2%: +1)")
    report_lines.append("    - Deep shakeout (>3%: +2, >1%: +1)")
    report_lines.append("  Minimum score: 5 (filters out weak setups)")
    report_lines.append("")
    report_lines.append("WHY THIS WORKS:")
    report_lines.append("  Shakeouts create fear and force weak hands to sell at lows.")
    report_lines.append("  Smart money accumulates during panic. When EFI turns positive,")
    report_lines.append("  it signals the shift from sellers to buyers. In an uptrend,")
    report_lines.append("  these reversals often lead to strong moves higher.")
    report_lines.append("")

    # Write to file
    report_text = '\n'.join(report_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Create TradingView lists
    create_tradingview_lists(confirmed_reversals, emerging_reversals, all_setups[:20], all_setups)

    # Print to console
    print(report_text)
    print(f"Report saved to: {output_file}")

def create_tradingview_lists(confirmed_reversals, emerging_reversals, top_20, all_setups):
    """Create TradingView watchlists for different categories"""

    # ALL SETUPS - Combined list
    all_tickers_file = os.path.join(buylist_dir, 'tradingview_shakeout_ALL.txt')
    with open(all_tickers_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("SHAKEOUT REVERSALS - ALL SETUPS\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(all_setups)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        if all_setups:
            tickers = [s['ticker'] for s in all_setups]
            f.write(",".join(tickers) + "\n")

    print(f"\nTradingView list saved: {all_tickers_file}")

    # Confirmed Reversals - Strong Buy
    confirmed_file = os.path.join(buylist_dir, 'tradingview_shakeout_confirmed.txt')
    with open(confirmed_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("SHAKEOUT REVERSALS - CONFIRMED (Strong Buy)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(confirmed_reversals)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        if confirmed_reversals:
            tickers = [s['ticker'] for s in confirmed_reversals]
            f.write(",".join(tickers) + "\n")

    print(f"TradingView list saved: {confirmed_file}")

    # Emerging Reversals - Watch List
    emerging_file = os.path.join(buylist_dir, 'tradingview_shakeout_emerging.txt')
    with open(emerging_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("SHAKEOUT REVERSALS - EMERGING (Watch List)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(emerging_reversals)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        if emerging_reversals:
            tickers = [s['ticker'] for s in emerging_reversals]
            f.write(",".join(tickers) + "\n")

    print(f"TradingView list saved: {emerging_file}")

    # Top 20 - Best Setups
    top20_file = os.path.join(buylist_dir, 'tradingview_shakeout_top20.txt')
    with open(top20_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("SHAKEOUT REVERSALS - TOP 20 BEST SETUPS\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total symbols: {len(top_20)}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Copy the line below and paste into TradingView watchlist:\n")
        f.write("-" * 80 + "\n\n")

        if top_20:
            tickers = [s['ticker'] for s in top_20]
            f.write(",".join(tickers) + "\n")

    print(f"TradingView list saved: {top20_file}")

    # Earnings filter list (if earnings data present)
    setups_with_earnings = [s for s in all_setups if 'earnings_date' in s and s['earnings_date']]
    if setups_with_earnings:
        earnings_file = os.path.join(buylist_dir, 'tradingview_shakeout_EARNINGS.txt')
        with open(earnings_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("SHAKEOUT REVERSALS - WITH UPCOMING EARNINGS\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total symbols: {len(setups_with_earnings)}\n")
            f.write("=" * 80 + "\n\n")
            f.write("STOCKS WITH EARNINGS IN NEXT 5 DAYS:\n")
            f.write("-" * 80 + "\n")
            for s in sorted(setups_with_earnings, key=lambda x: x['earnings_date']):
                f.write(f"{s['ticker']:<8} Earnings: {s['earnings_date'].strftime('%m/%d/%Y')}\n")
            f.write("\n")
            f.write("Copy the line below and paste into TradingView watchlist:\n")
            f.write("-" * 80 + "\n\n")
            tickers = [s['ticker'] for s in setups_with_earnings]
            f.write(",".join(tickers) + "\n")

        print(f"TradingView list saved: {earnings_file}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Shakeout Reversal Scanner')
    parser.add_argument('--earnings', '-e', type=int, default=None,
                        help='Filter for stocks with earnings in next N days (e.g., --earnings 5)')
    parser.add_argument('--lookback', '-l', type=int, default=20,
                        help='Days to look back for shakeout (default: 20)')

    args = parser.parse_args()

    # Run the scanner
    # Use --earnings 5 to filter for upcoming earnings
    # Without --earnings flag, shows all setups
    run_shakeout_reversal_scan(lookback_days=args.lookback, earnings_filter_days=args.earnings)
