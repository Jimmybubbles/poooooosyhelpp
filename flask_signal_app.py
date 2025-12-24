from flask import Flask, render_template, request, jsonify
import pandas as pd
import os
from datetime import datetime
import sys

# Add the watchlist_Scanner directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'watchlist_Scanner'))

from EFI_Indicator import EFI_Indicator
from PriceRangeZones import calculate_price_range_zones, determine_trend

app = Flask(__name__)

# Configuration
RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'watchlist_Scanner', 'updated_Results_for_scan')

def check_in_channel(df, idx, channel_period=3):
    """Check if price is trading within a defined channel"""
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

def find_maroon_signals(ticker_symbol, hold_days=63):
    """
    Find all MAROON signal occurrences for a ticker

    Returns:
        List of signal dictionaries with entry/exit data
    """
    try:
        csv_file = os.path.join(RESULTS_DIR, f"{ticker_symbol}.csv")

        if not os.path.exists(csv_file):
            return {'error': f'Ticker {ticker_symbol} not found in database'}

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

        if len(df) < 100 + hold_days:
            return {'error': f'Not enough data for {ticker_symbol}. Need at least {100 + hold_days} days.'}

        # Calculate indicators
        indicator = EFI_Indicator()
        efi_results = indicator.calculate(df)
        zones = calculate_price_range_zones(df, lookback_period=100)
        trend = determine_trend(df, lookback_period=50)

        # Find all MAROON signals
        signals = []

        for i in range(100, len(df) - hold_days):
            # Check all conditions
            in_channel = check_in_channel(df, i, channel_period=3)
            fi_color = efi_results['fi_color'].iloc[i]
            normalized_price = efi_results['normalized_price'].iloc[i]
            price_zone = zones['price_zone'].iloc[i]
            current_trend = trend.iloc[i]

            condition_1_channel = in_channel
            condition_2_price_zone = price_zone == 'buy_zone'
            condition_3_maroon = fi_color == 'maroon'
            condition_4_normalized = normalized_price < -0.5
            condition_5_trend = current_trend == 'uptrend'

            # If all conditions are met, record the signal
            if condition_1_channel and condition_2_price_zone and condition_3_maroon and condition_4_normalized and condition_5_trend:
                entry_date = df.index[i]
                entry_price = df['Close'].iloc[i]

                # Calculate exit
                exit_idx = i + hold_days
                exit_date = df.index[exit_idx]
                exit_price = df['Close'].iloc[exit_idx]

                # Calculate P&L
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                pnl_dollars = exit_price - entry_price

                # Get signal details
                force_index = efi_results['force_index'].iloc[i]
                range_position = zones['range_position_pct'].iloc[i]

                signals.append({
                    'entry_date': entry_date.strftime('%Y-%m-%d'),
                    'entry_price': round(entry_price, 2),
                    'exit_date': exit_date.strftime('%Y-%m-%d'),
                    'exit_price': round(exit_price, 2),
                    'pnl_pct': round(pnl_pct, 2),
                    'pnl_dollars': round(pnl_dollars, 2),
                    'hold_days': hold_days,
                    'normalized_price': round(normalized_price, 2),
                    'force_index': round(force_index, 2),
                    'range_position_pct': round(range_position, 2)
                })

        if not signals:
            return {'info': f'No MAROON signals found for {ticker_symbol} with the strict criteria'}

        return {'ticker': ticker_symbol, 'signals': signals}

    except Exception as e:
        return {'error': f'Error analyzing {ticker_symbol}: {str(e)}'}

@app.route('/')
def index():
    """Main page"""
    return render_template('signal_search.html')

@app.route('/api/search', methods=['POST'])
def search_signal():
    """API endpoint to search for signals"""
    data = request.get_json()
    ticker = data.get('ticker', '').strip().upper()
    hold_days = int(data.get('hold_days', 63))

    if not ticker:
        return jsonify({'error': 'Please enter a ticker symbol'}), 400

    result = find_maroon_signals(ticker, hold_days)
    return jsonify(result)

@app.route('/api/tickers', methods=['GET'])
def get_available_tickers():
    """Get list of available tickers"""
    try:
        csv_files = [f for f in os.listdir(RESULTS_DIR) if f.endswith('.csv')]
        tickers = sorted([f[:-4] for f in csv_files])
        return jsonify({'tickers': tickers[:100]})  # Return first 100 for autocomplete
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
