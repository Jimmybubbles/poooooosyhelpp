"""
EFI Zero Touch Scanner
======================
Finds stocks where the EFI price line (normalized price) has just touched 0 from above.

This is a potential support/pullback signal - price was above the basis (mean) and
has now pulled back to touch it.

Theory:
- EFI Price Line = Close - Basis (Bollinger middle band)
- When price line > 0: Price is above the mean
- When price line touches 0 from above: Price has pulled back to the mean
- This can be a buying opportunity in an uptrend (pullback to support)
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime
from EFI_Indicator import EFI_Indicator

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Configuration - use same directories as other scanners
CSV_DIR = os.path.join(script_dir, 'updated_Results_for_scan')
TICKER_LIST = os.path.join(script_dir, 'CSV', '5000.csv')
OUTPUT_DIR = os.path.join(script_dir, 'buylist')

# Scanner parameters
MIN_PRICE = 1.0
MAX_PRICE = 500.0
MIN_VOLUME = 100000
TOUCH_THRESHOLD = 0.05  # How close to zero counts as "touching" (as % of price)
LOOKBACK_ABOVE = 5      # How many bars to look back for being above zero


def load_ticker_list():
    """Load list of tickers from CSV files in the data directory"""
    try:
        csv_files = [f for f in os.listdir(CSV_DIR) if f.endswith('.csv')]
        tickers = [f[:-4] for f in csv_files]
        return tickers
    except Exception as e:
        print(f"Error loading ticker list: {e}")
        return []


def load_stock_data(ticker):
    """Load stock data from CSV - matches RangeLevelScanner format"""
    csv_path = os.path.join(CSV_DIR, f"{ticker}.csv")

    if not os.path.exists(csv_path):
        return None

    try:
        df = pd.read_csv(csv_path, skiprows=[1, 2])

        if 'Price' in df.columns:
            df.rename(columns={'Price': 'Date'}, inplace=True)

        required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_cols):
            return None

        df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
        df = df.dropna(subset=['Date'])
        df = df.sort_values('Date')
        df.set_index('Date', inplace=True)

        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna()

        return df

    except Exception as e:
        return None


def check_zero_touch(df, indicator):
    """
    Check if EFI price line has just touched 0 from above

    Returns:
        dict with signal info or None
    """
    if len(df) < 100:
        return None

    # Calculate EFI indicator
    try:
        results = indicator.calculate(df)
    except Exception as e:
        return None

    # Get recent values
    norm_price = results['normalized_price']
    fi_ema = results['force_index']
    fi_color = results['fi_color']

    if len(norm_price) < LOOKBACK_ABOVE + 2:
        return None

    # Current and previous normalized price
    current_norm = norm_price.iloc[-1]
    prev_norm = norm_price.iloc[-2]

    # Current price for threshold calculation
    current_price = df['Close'].iloc[-1]
    threshold = current_price * (TOUCH_THRESHOLD / 100)

    # Check if price line was above zero recently and has now touched zero
    # Condition 1: Was above zero in the lookback period
    was_above = (norm_price.iloc[-LOOKBACK_ABOVE-1:-1] > threshold).any()

    # Condition 2: Current bar has touched or crossed zero (within threshold)
    touches_zero = abs(current_norm) <= threshold or (prev_norm > 0 and current_norm <= 0)

    # Condition 3: Previous bar was above zero (coming down to touch)
    coming_from_above = prev_norm > 0

    if was_above and touches_zero and coming_from_above:
        # Calculate additional context
        avg_volume = df['Volume'].iloc[-20:].mean()
        current_volume = df['Volume'].iloc[-1]

        # Get EFI color state
        current_fi = fi_ema.iloc[-1]
        current_fi_color = fi_color.iloc[-1]

        # Check trend context (is EFI still bullish?)
        efi_bullish = current_fi > 0 or current_fi_color in ['lime', 'teal']

        return {
            'ticker': None,  # Will be filled by caller
            'price': current_price,
            'norm_price': current_norm,
            'prev_norm': prev_norm,
            'efi_value': current_fi,
            'efi_color': current_fi_color,
            'efi_bullish': efi_bullish,
            'volume': current_volume,
            'avg_volume': avg_volume,
            'vol_ratio': current_volume / avg_volume if avg_volume > 0 else 0,
            'date': df.index[-1]
        }

    return None


def scan_all_stocks():
    """Run the scanner on all stocks"""
    print("=" * 80)
    print("EFI ZERO TOUCH SCANNER")
    print("Finding stocks where EFI price line touched 0 from above")
    print("=" * 80)
    print()

    tickers = load_ticker_list()
    print(f"Loaded {len(tickers)} tickers to scan")
    print()

    # Initialize indicator
    indicator = EFI_Indicator()

    # Results storage
    all_results = []
    bullish_results = []  # EFI still bullish (potential bounce)

    scanned = 0
    for ticker in tickers:
        df = load_stock_data(ticker)

        if df is None or len(df) < 100:
            continue

        # Filter by price and volume
        current_price = df['Close'].iloc[-1]
        avg_volume = df['Volume'].iloc[-20:].mean()

        if current_price < MIN_PRICE or current_price > MAX_PRICE:
            continue
        if avg_volume < MIN_VOLUME:
            continue

        scanned += 1

        # Check for zero touch
        result = check_zero_touch(df, indicator)

        if result:
            result['ticker'] = ticker
            all_results.append(result)

            if result['efi_bullish']:
                bullish_results.append(result)

        if scanned % 500 == 0:
            print(f"  Scanned {scanned} stocks... Found {len(all_results)} setups")

    print(f"\nScan complete! Scanned {scanned} stocks")
    print(f"Found {len(all_results)} zero touch setups")
    print(f"  Bullish context (EFI > 0): {len(bullish_results)}")
    print()

    return all_results, bullish_results


def save_results(all_results, bullish_results):
    """Save results to files"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Sort by volume ratio (higher = more significant)
    all_results.sort(key=lambda x: x['vol_ratio'], reverse=True)
    bullish_results.sort(key=lambda x: x['vol_ratio'], reverse=True)

    # Save main results file
    results_file = os.path.join(OUTPUT_DIR, 'efi_zero_touch_results.txt')

    with open(results_file, 'w') as f:
        f.write("=" * 100 + "\n")
        f.write("EFI ZERO TOUCH SCANNER - RESULTS\n")
        f.write("=" * 100 + "\n")
        f.write(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("\n")
        f.write("THEORY:\n")
        f.write("  EFI Price Line = Close - Basis (Bollinger middle band)\n")
        f.write("  When price line touches 0 from above: Price pulled back to the mean\n")
        f.write("  Bullish setups: EFI > 0 (momentum still positive) = potential bounce point\n")
        f.write("\n")
        f.write(f"Total Setups Found: {len(all_results)}\n")
        f.write(f"  Bullish Context (EFI > 0): {len(bullish_results)}\n")
        f.write("\n")

        # Bullish setups (best opportunities)
        f.write("=" * 100 + "\n")
        f.write("BULLISH ZERO TOUCH (EFI > 0 - Potential Bounce Points)\n")
        f.write("=" * 100 + "\n")
        f.write(f"{'Ticker':<8} {'Price':>10} {'Norm':>10} {'EFI':>10} {'Color':<8} {'VolRatio':>10}\n")
        f.write("-" * 100 + "\n")

        for r in bullish_results[:50]:
            f.write(f"{r['ticker']:<8} ${r['price']:>9.2f} {r['norm_price']:>10.3f} "
                   f"{r['efi_value']:>10.3f} {r['efi_color']:<8} {r['vol_ratio']:>10.2f}x\n")

        f.write("\n")

        # All setups
        f.write("=" * 100 + "\n")
        f.write("ALL ZERO TOUCH SETUPS\n")
        f.write("=" * 100 + "\n")
        f.write(f"{'Ticker':<8} {'Price':>10} {'Norm':>10} {'EFI':>10} {'Color':<8} {'VolRatio':>10} {'Context':<10}\n")
        f.write("-" * 100 + "\n")

        for r in all_results[:100]:
            context = "BULLISH" if r['efi_bullish'] else "BEARISH"
            f.write(f"{r['ticker']:<8} ${r['price']:>9.2f} {r['norm_price']:>10.3f} "
                   f"{r['efi_value']:>10.3f} {r['efi_color']:<8} {r['vol_ratio']:>10.2f}x {context:<10}\n")

    print(f"Results saved to: {results_file}")

    # Save TradingView watchlist
    tv_file = os.path.join(OUTPUT_DIR, 'tradingview_efi_zero_touch.txt')

    with open(tv_file, 'w') as f:
        # Bullish setups first
        for r in bullish_results[:30]:
            f.write(f"{r['ticker']}\n")

    print(f"TradingView list saved to: {tv_file}")

    return results_file


def main():
    """Main entry point"""
    all_results, bullish_results = scan_all_stocks()

    if all_results:
        save_results(all_results, bullish_results)

        # Print summary
        print("\n" + "=" * 80)
        print("TOP 10 BULLISH ZERO TOUCH SETUPS")
        print("=" * 80)
        print(f"{'Ticker':<8} {'Price':>10} {'EFI Color':<10} {'Vol Ratio':>10}")
        print("-" * 50)

        for r in bullish_results[:10]:
            print(f"{r['ticker']:<8} ${r['price']:>9.2f} {r['efi_color']:<10} {r['vol_ratio']:>10.2f}x")
    else:
        print("No setups found.")


if __name__ == "__main__":
    main()
