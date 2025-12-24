from flask import Flask, render_template, jsonify, request
import subprocess
import os
import threading
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import re

app = Flask(__name__)

# Store scan status and results
scan_status = {
    'channel_3week': {'running': False, 'last_run': None, 'results': ''},
    'fader': {'running': False, 'last_run': None, 'results': ''},
    'append_data': {'running': False, 'last_run': None, 'results': ''},
    'backtest_fader': {'running': False, 'last_run': None, 'results': ''},
    'backtest_channel': {'running': False, 'last_run': None, 'results': ''},
    'backtest_maroon': {'running': False, 'last_run': None, 'results': ''},
    'zerolag_scan': {'running': False, 'last_run': None, 'results': ''},
    'triple_signal': {'running': False, 'last_run': None, 'results': ''}
}

def read_file_contents(file_path):
    """Read and return file contents"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return "No results yet. Run a scan first."
    except Exception as e:
        return f"Error reading file: {str(e)}"

def parse_backtest_results(content):
    """Parse backtest results into structured data for better visualization"""
    try:
        lines = content.split('\n')

        # Extract key metrics
        metrics = {}
        for line in lines:
            if 'Total Trades:' in line:
                metrics['total_trades'] = line.split(':')[1].strip()
            elif 'Profitable:' in line and '(' in line:
                parts = line.split(':')[1].strip().split('(')
                metrics['profitable'] = parts[0].strip()
                metrics['win_rate'] = parts[1].replace(')', '').strip()
            elif 'Losing:' in line and '(' in line:
                parts = line.split(':')[1].strip().split('(')
                metrics['losing'] = parts[0].strip()
                metrics['loss_rate'] = parts[1].replace(')', '').strip()
            elif 'Average P&L:' in line:
                metrics['avg_pnl'] = line.split(':')[1].strip()
            elif 'Median P&L:' in line:
                metrics['median_pnl'] = line.split(':')[1].strip()
            elif 'Portfolio Return:' in line:
                metrics['portfolio_return'] = line.split(':')[1].strip()
            elif 'Best Trade:' in line:
                metrics['best_trade'] = line.split(':')[1].strip()
            elif 'Worst Trade:' in line:
                metrics['worst_trade'] = line.split(':')[1].strip()

        return metrics
    except Exception as e:
        print(f"Error parsing backtest results: {e}")
        return {}

def run_script_background(script_name, scan_type):
    """Run a Python script in the background and capture output"""
    global scan_status

    try:
        scan_status[scan_type]['running'] = True
        scan_status[scan_type]['results'] = f"Starting {scan_type} scan...\n"

        # Run the script and capture output
        result = subprocess.run(
            ['python', script_name],
            capture_output=True,
            text=True,
            timeout=900,  # 15 minute timeout for backtests
            encoding='utf-8',
            errors='replace'
        )

        # Combine stdout and stderr
        output = result.stdout + result.stderr

        scan_status[scan_type]['results'] = output
        scan_status[scan_type]['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        scan_status[scan_type]['running'] = False

    except subprocess.TimeoutExpired:
        scan_status[scan_type]['results'] = "Scan timed out after 15 minutes"
        scan_status[scan_type]['running'] = False
    except Exception as e:
        scan_status[scan_type]['results'] = f"Error running scan: {str(e)}"
        scan_status[scan_type]['running'] = False

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/run_scan/<scan_type>', methods=['POST'])
def run_scan(scan_type):
    """Run a specific scan"""
    global scan_status

    if scan_status[scan_type]['running']:
        return jsonify({
            'status': 'error',
            'message': 'Scan is already running'
        })

    # Map scan types to script files
    scripts = {
        'channel_3week': 'watchlist_Scanner/JimmyChannelScan_3week_test.py',
        'fader': 'watchlist_Scanner/ChannelFaderScan.py',
        'append_data': 'watchlist_Scanner/AppendDailyData.py',
        'backtest_fader': 'watchlist_Scanner/BacktestFaderScan.py',
        'backtest_channel': 'watchlist_Scanner/BacktestChannelScan.py',
        'backtest_maroon': 'watchlist_Scanner/BacktestTripleSignal_Maroon.py',
        'zerolag_scan': 'watchlist_Scanner/ZeroLag_Scanner.py',
        'triple_signal': 'watchlist_Scanner/TripleSignal_Scanner.py'
    }

    if scan_type not in scripts:
        return jsonify({
            'status': 'error',
            'message': 'Invalid scan type'
        })

    # Start scan in background thread
    thread = threading.Thread(
        target=run_script_background,
        args=(scripts[scan_type], scan_type)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        'status': 'success',
        'message': f'{scan_type} scan started'
    })

@app.route('/scan_status/<scan_type>')
def get_scan_status(scan_type):
    """Get the status of a specific scan"""
    if scan_type not in scan_status:
        return jsonify({'status': 'error', 'message': 'Invalid scan type'})

    return jsonify({
        'running': scan_status[scan_type]['running'],
        'last_run': scan_status[scan_type]['last_run'],
        'results': scan_status[scan_type]['results']
    })

@app.route('/view_results/<result_type>')
def view_results(result_type):
    """View saved scan results from files"""
    files = {
        'channel_3week': 'watchlist_Scanner/buylist/sorted_scan_results_3week.txt',
        'fader': 'watchlist_Scanner/buylist/sorted_fader_scan_results.txt',
        'tradingview_list': 'watchlist_Scanner/buylist/tradingview_fader_list.txt',
        'backtest_fader': 'watchlist_Scanner/buylist/backtest_fader_results.txt',
        'backtest_channel': 'watchlist_Scanner/buylist/backtest_channel_results.txt',
        'backtest_maroon': 'watchlist_Scanner/buylist/triple_signal_maroon_backtest_results.txt',
        'zerolag_results': 'watchlist_Scanner/buylist/zerolag_scan_results.txt',
        'triple_signal_results': 'watchlist_Scanner/buylist/triple_signal_scan_results.txt'
    }

    if result_type not in files:
        return jsonify({'status': 'error', 'message': 'Invalid result type'})

    content = read_file_contents(files[result_type])

    # Parse metrics if it's a backtest result
    metrics = {}
    if 'backtest' in result_type:
        metrics = parse_backtest_results(content)

    return jsonify({
        'status': 'success',
        'content': content,
        'file': files[result_type],
        'metrics': metrics
    })

@app.route('/get_chart/<ticker>')
def get_chart(ticker):
    """Fetch chart data for a specific ticker"""
    try:
        # Get optional signal_date parameter from query string
        signal_date = request.args.get('signal_date', None)

        # Get chart data for the last 6 months
        end_date = datetime.now()
        start_date = end_date - timedelta(days=180)

        # Download data using yfinance
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date, end=end_date)

        if df.empty:
            return jsonify({
                'status': 'error',
                'message': f'No data found for {ticker}'
            })

        # Prepare data for chart
        dates = df.index.strftime('%Y-%m-%d').tolist()
        prices = df['Close'].round(2).tolist()
        volumes = df['Volume'].tolist()
        highs = df['High'].round(2).tolist()
        lows = df['Low'].round(2).tolist()
        opens = df['Open'].round(2).tolist()

        return jsonify({
            'status': 'success',
            'ticker': ticker,
            'dates': dates,
            'prices': prices,
            'volumes': volumes,
            'highs': highs,
            'lows': lows,
            'opens': opens,
            'signal_date': signal_date
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error fetching data for {ticker}: {str(e)}'
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)