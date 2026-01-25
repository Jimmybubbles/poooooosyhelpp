from flask import Flask, render_template, request, jsonify
import os

app = Flask(__name__)

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def index():
    """Main page with ticker input and chart display"""
    return render_template('tradingview_chart.html')

@app.route('/chart/<ticker>')
def chart(ticker):
    """Display chart for specific ticker"""
    return render_template('tradingview_chart.html', ticker=ticker.upper())

@app.route('/api/validate_ticker', methods=['POST'])
def validate_ticker():
    """API endpoint to validate ticker exists"""
    data = request.get_json()
    ticker = data.get('ticker', '').upper().strip()

    if not ticker:
        return jsonify({'valid': False, 'message': 'Please enter a ticker symbol'})

    # Basic validation
    if len(ticker) > 10 or not ticker.isalnum():
        return jsonify({'valid': False, 'message': 'Invalid ticker format'})

    return jsonify({'valid': True, 'ticker': ticker})

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    templates_dir = os.path.join(script_dir, 'templates')
    os.makedirs(templates_dir, exist_ok=True)

    print("=" * 80)
    print("TRADINGVIEW CHART FLASK APP")
    print("=" * 80)
    print("Starting Flask server...")
    print("Access the app at: http://localhost:5000")
    print("=" * 80)

    app.run(debug=True, host='0.0.0.0', port=5000)
