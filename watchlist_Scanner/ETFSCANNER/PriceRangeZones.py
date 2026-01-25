import pandas as pd
import numpy as np
import os
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

def calculate_price_range_zones(df, lookback_period=100):
    """
    Calculate dynamic price range zones for a stock

    The price range is determined by $1 increments:
    - $0-$1 range: zones at $0.25 (25%) and $0.75 (75%)
    - $1-$2 range: zones at $1.25 (25%) and $1.75 (75%)
    - $2-$3 range: zones at $2.25 (25%) and $2.75 (75%)
    - ... continues up to $10
    - Above $10: uses $10 ranges ($10-$20, $20-$30, etc.)

    Args:
        df: DataFrame with OHLCV data
        lookback_period: Number of bars to look back for high/low (default 100)

    Returns:
        DataFrame with zone calculations
    """

    # Calculate rolling high and low over lookback period
    rolling_high = df['High'].rolling(window=lookback_period).max()
    rolling_low = df['Low'].rolling(window=lookback_period).min()

    current_price = df['Close']

    # Determine range floor and ceiling based on $1 increments
    range_floor = pd.Series(index=df.index, dtype=float)
    range_ceiling = pd.Series(index=df.index, dtype=float)

    for i in range(len(df)):
        price = current_price.iloc[i]

        if price < 10:
            # For prices under $10: use $1 increments (0-1, 1-2, 2-3, etc.)
            floor = np.floor(price)
            ceiling = floor + 1
        else:
            # For prices $10 and above: use $10 increments (10-20, 20-30, etc.)
            floor = np.floor(price / 10) * 10
            ceiling = floor + 10

        range_floor.iloc[i] = floor
        range_ceiling.iloc[i] = ceiling

    # Calculate 25% and 75% zones within the range
    range_25_pct = range_floor + (range_ceiling - range_floor) * 0.25
    range_75_pct = range_floor + (range_ceiling - range_floor) * 0.75

    # Calculate where current price sits in the range (0-100%)
    range_position = ((current_price - range_floor) / (range_ceiling - range_floor)) * 100

    # Determine if price is in buy zone (0-35%), neutral (35-65%), or sell zone (65-100%)
    price_zone = pd.Series(index=df.index, dtype=str)

    for i in range(len(df)):
        pos = range_position.iloc[i]
        if pos <= 35:
            price_zone.iloc[i] = 'buy_zone'
        elif pos >= 65:
            price_zone.iloc[i] = 'sell_zone'
        else:
            price_zone.iloc[i] = 'neutral_zone'

    # Create results DataFrame
    results = pd.DataFrame({
        'close': current_price,
        'range_floor': range_floor,
        'range_ceiling': range_ceiling,
        'zone_25_pct': range_25_pct,
        'zone_75_pct': range_75_pct,
        'range_position_pct': range_position,
        'price_zone': price_zone,
        'rolling_high': rolling_high,
        'rolling_low': rolling_low
    }, index=df.index)

    return results

def determine_trend(df, lookback_period=50):
    """
    Determine if stock is in uptrend or downtrend

    Uses simple moving average crossover:
    - Uptrend: Price > SMA
    - Downtrend: Price < SMA

    Args:
        df: DataFrame with OHLCV data
        lookback_period: Period for trend SMA

    Returns:
        Series with trend direction ('uptrend', 'downtrend', 'neutral')
    """
    sma = df['Close'].rolling(window=lookback_period).mean()

    trend = pd.Series(index=df.index, dtype=str)

    for i in range(len(df)):
        if pd.isna(sma.iloc[i]):
            trend.iloc[i] = 'neutral'
        elif df['Close'].iloc[i] > sma.iloc[i]:
            trend.iloc[i] = 'uptrend'
        else:
            trend.iloc[i] = 'downtrend'

    return trend

def analyze_ticker_zones(ticker_symbol, results_dir):
    """
    Analyze price range zones for a single ticker

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files

    Returns:
        Dict with current zone analysis or None
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

        # Calculate price range zones
        zones = calculate_price_range_zones(df, lookback_period=100)

        # Determine trend
        trend = determine_trend(df, lookback_period=50)

        # Get most recent data
        latest_idx = -1
        current_date = df.index[latest_idx]
        current_price = df['Close'].iloc[latest_idx]
        current_zone = zones['price_zone'].iloc[latest_idx]
        current_trend = trend.iloc[latest_idx]
        range_position = zones['range_position_pct'].iloc[latest_idx]
        zone_25 = zones['zone_25_pct'].iloc[latest_idx]
        zone_75 = zones['zone_75_pct'].iloc[latest_idx]
        range_floor = zones['range_floor'].iloc[latest_idx]
        range_ceiling = zones['range_ceiling'].iloc[latest_idx]

        return {
            'ticker': ticker_symbol,
            'date': current_date,
            'price': current_price,
            'trend': current_trend,
            'price_zone': current_zone,
            'range_position_pct': range_position,
            'zone_25_pct': zone_25,
            'zone_75_pct': zone_75,
            'range_floor': range_floor,
            'range_ceiling': range_ceiling
        }

    except Exception as e:
        print(f"Error analyzing {ticker_symbol}: {e}")
        return None

def demo_price_ranges():
    """
    Demonstrate how price ranges work with examples
    """
    print("=" * 80)
    print("PRICE RANGE ZONES - DEMONSTRATION ($1 INCREMENTS)")
    print("=" * 80)
    print()
    print("How it works:")
    print()
    print("Stocks under $10 use $1 increments:")
    print("  - $0-$1:   25% zone = $0.25,  75% zone = $0.75")
    print("  - $1-$2:   25% zone = $1.25,  75% zone = $1.75")
    print("  - $2-$3:   25% zone = $2.25,  75% zone = $2.75")
    print("  - $3-$4:   25% zone = $3.25,  75% zone = $3.75")
    print("  - ... continues to $9-$10")
    print()
    print("Stocks $10+ use $10 increments:")
    print("  - $10-$20:  25% zone = $12.50, 75% zone = $17.50")
    print("  - $20-$30:  25% zone = $22.50, 75% zone = $27.50")
    print("  - ... and so on")
    print()
    print("Strategy:")
    print("  UPTREND + Buy Zone (0-35%):  BUY signal - price at support")
    print()
    print("Examples:")
    print("-" * 80)

    examples = [
        (0.30, 'uptrend', 'buy_zone', 30.0),
        (1.20, 'uptrend', 'buy_zone', 20.0),
        (2.85, 'uptrend', 'sell_zone', 85.0),
        (3.15, 'uptrend', 'buy_zone', 15.0),
        (4.75, 'uptrend', 'sell_zone', 75.0),
        (5.25, 'uptrend', 'buy_zone', 25.0),
        (6.80, 'uptrend', 'neutral_zone', 80.0),
        (7.10, 'uptrend', 'buy_zone', 10.0),
        (8.50, 'uptrend', 'neutral_zone', 50.0),
        (9.30, 'uptrend', 'buy_zone', 30.0),
        (15.00, 'uptrend', 'neutral_zone', 50.0),
        (23.50, 'uptrend', 'buy_zone', 35.0),
    ]

    for price, trend, zone, position in examples:
        if price < 10:
            floor = np.floor(price)
            ceiling = floor + 1
        else:
            floor = np.floor(price / 10) * 10
            ceiling = floor + 10

        zone_25 = floor + (ceiling - floor) * 0.25
        zone_75 = floor + (ceiling - floor) * 0.75

        signal = "NONE"
        if trend == 'uptrend' and zone == 'buy_zone':
            signal = "BUY"
        elif trend == 'downtrend' and zone == 'sell_zone':
            signal = "SELL"

        print(f"Price: ${price:>6.2f} | Range: ${floor:.0f}-${ceiling:.0f} | "
              f"25%: ${zone_25:>5.2f} | 75%: ${zone_75:>5.2f} | "
              f"Position: {position:>5.1f}% | Zone: {zone:<12} | Signal: {signal}")

    print("=" * 80)
    print()

if __name__ == "__main__":
    demo_price_ranges()