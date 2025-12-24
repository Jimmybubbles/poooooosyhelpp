# Triple Signal Maroon Scanner - Flask Web Application

A beautiful web interface to search for Triple Signal Maroon setups for any ticker in your database.

## Features

- **Search by Ticker**: Enter any ticker symbol to find historical MAROON signals
- **Customizable Hold Period**: Adjust the hold days (default: 63 trading days / 1 quarter)
- **Visual Results**: See all signals with entry/exit prices, P&L, and signal details
- **Summary Statistics**: View win rate, average P&L, and total returns at a glance
- **Beautiful UI**: Modern, responsive design with gradient colors and smooth animations

## Installation

1. Make sure you have Flask installed:
```bash
pip install flask
```

2. Ensure all dependencies are installed:
```bash
pip install pandas yfinance
```

## Running the Application

1. Open a terminal in the project directory
2. Run the Flask app:
```bash
python flask_signal_app.py
```

3. Open your browser and go to:
```
http://localhost:5000
```

## How to Use

1. **Enter a Ticker**: Type a stock ticker symbol (e.g., AAPL, MSFT, TSLA)
2. **Set Hold Days** (optional): Default is 63 days (1 business quarter)
3. **Click Search**: The app will find all MAROON signals for that ticker
4. **View Results**: See:
   - Number of signals found
   - Win rate and profitability
   - Individual signal cards with entry/exit details
   - P&L for each signal

## Signal Criteria

The app searches for the **Triple Signal Maroon** setup:
- ✓ In Channel (price within 3-week range)
- ✓ Price in Buy Zone (0-35% of $1 range)
- ✓ EFI is MAROON (strongest oversold signal)
- ✓ Normalized Price < -0.5 (deep oversold)
- ✓ Uptrend confirmed

## Example Searches

Try these tickers to see signals:
- AAPL (Apple)
- MSFT (Microsoft)
- BELFB (Bel Fuse Inc - shown in your backtest with 75.92% return!)
- Any ticker in your `updated_Results_for_scan` folder

## File Structure

```
flask_signal_app.py          # Main Flask application
templates/
  └── signal_search.html     # Frontend HTML template
watchlist_Scanner/
  ├── updated_Results_for_scan/  # Your stock data
  ├── EFI_Indicator.py
  └── PriceRangeZones.py
```

## Features Explained

### Summary Statistics
- **Total Signals**: How many MAROON signals occurred historically
- **Profitable**: Number and percentage of winning trades
- **Average P&L**: Mean return across all signals
- **Total P&L**: Sum of all dollar gains/losses

### Signal Cards
Each signal shows:
- Entry Date and Price
- Exit Date and Price (after hold period)
- P&L in both % and $
- Normalized Price (how oversold)
- Force Index (momentum strength)
- Range Position (where in the $1 range)

### Color Coding
- **Green border**: Profitable signal
- **Red border**: Losing signal
- **Green badge**: Positive P&L
- **Red badge**: Negative P&L

## Troubleshooting

**"Ticker not found"**: The ticker doesn't exist in your `updated_Results_for_scan` folder. Run your data download scripts first.

**"Not enough data"**: The ticker needs at least 163 days of data (100 for indicators + 63 for holding period).

**"No signals found"**: The ticker never met the strict MAROON criteria. This is normal - MAROON signals are rare!

## Customization

You can modify the hold period in the web interface, or change defaults in `flask_signal_app.py`:
- Line 83: Change default `hold_days` parameter
- Adjust signal criteria in the `find_maroon_signals()` function

## Notes

- The app uses historical data from your `updated_Results_for_scan` folder
- Make sure your data is up to date using `AppendDailyData.py`
- Signals are backtested - past performance doesn't guarantee future results
- The app shows ALL historical signals for a ticker, not just the most recent one

Enjoy finding those extreme oversold opportunities!
