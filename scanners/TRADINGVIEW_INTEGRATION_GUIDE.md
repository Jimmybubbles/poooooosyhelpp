# TradingView Chart Integration Guide

## 📋 Overview

This guide explains how to embed TradingView charts with your custom indicators into your Flask website.

## 🚀 Quick Start

### 1. Run the Flask App

```bash
cd c:\Users\James\poosy\poooooosyhelpp-1\watchlist_Scanner
python flask_tradingview_app.py
```

Then open your browser to: `http://localhost:5000`

### 2. Available Pages

- **`/`** - Main page with ticker search
- **`/chart/<TICKER>`** - Direct link to specific ticker chart (e.g., `/chart/AAPL`)

## 🎨 Features

### Basic Chart Viewer (`tradingview_chart.html`)
- ✅ Ticker input with search
- ✅ Quick access buttons for popular stocks
- ✅ Embedded TradingView chart
- ✅ Direct link to open in TradingView
- ✅ Clean, modern UI
- ✅ Mobile responsive

### Scanner Integration (`scanner_charts.html`)
- ✅ Shows your scanner results in sidebar
- ✅ Click any ticker to load chart
- ✅ Signal details display (price, date, zone)
- ✅ Filter by signal quality (Excellent/Good)
- ✅ Keyboard navigation (arrow keys)
- ✅ Next/Previous buttons

## 🔧 Adding Your Custom Indicators

### Method 1: Public Indicators (Recommended)

If your indicators are published publicly or invite-only on TradingView:

1. **Publish Your Indicator in TradingView:**
   - Open Pine Editor
   - Write/paste your indicator code
   - Click "Publish Script"
   - Choose visibility (Public or Invite-only)
   - Note the script ID (format: `PUB;xxxxxxxxxxxxx`)

2. **Add to the Embed Code:**

In `tradingview_chart.html` (around line 250), add your indicator IDs:

```javascript
"studies": [
    "PUB;your_indicator_id_here",
    "PUB;another_indicator_id_here"
]
```

Example:
```javascript
"studies": [
    "PUB;jimmys_long_term_levels",
    "PUB;rocwma_indicator_optimized"
]
```

### Method 2: Manual Addition by Users

Users can manually add indicators to the embedded chart:

1. Click the "Indicators" button on the chart
2. Search for your published indicators
3. Click to add them to the chart
4. TradingView will remember the settings

### Method 3: TradingView Template (Advanced)

For private indicators or complex setups:

1. Create a chart template in TradingView with all your indicators
2. Save the template
3. Share the template link with users
4. They load the template once, then the embed remembers it

## 📝 How to Publish Your Indicators

### Publishing "Jimmy's Long Term Levels"

1. Open TradingView Pine Editor
2. Copy your indicator code from: `tradingview_indicators/Jimmys_Long_Term_Levels_with_12M.pine`
3. Paste into Pine Editor
4. Click "Publish Script"
5. Fill out publication form:
   - Title: "Jimmy's Long Term Levels"
   - Description: "Monthly, Quarterly, and 12-Month support/resistance levels"
   - Visibility: Choose "Public" or "Invite-only"
6. Submit
7. Copy the script ID from the URL (looks like: `PUB;xxxxxx`)

### Publishing ROCWMA Indicator

Same process but with your ROCWMA code.

## 🔐 Authentication & Private Indicators

**Important Limitation:** TradingView's embed widget cannot automatically load private indicators that haven't been shared.

**Workarounds:**

1. **Publish as Invite-Only:** Share access with specific users
2. **Use Chart Templates:** Save a template with your indicators, users load it once
3. **Manual Addition:** Users add indicators manually (they persist in browser)
4. **TradingView Premium API:** Requires paid enterprise plan for full automation

## 🎯 Integrating with Your Scanners

### Connecting Scanner Results to Charts

Update `flask_tradingview_app.py`:

```python
import pandas as pd

@app.route('/scanner/triple-signal')
def triple_signal_charts():
    # Read your scanner results
    results_file = 'buylist/tradingview_triple_signal_list.txt'

    with open(results_file, 'r') as f:
        content = f.read()

    # Parse tickers (assuming comma-separated)
    tickers = content.strip().split(',')

    # Load scanner data for each ticker
    scanner_data = []
    for ticker in tickers[:20]:  # Limit to 20 for performance
        # Read from your CSV files
        csv_path = f'updated_Results_for_scan/{ticker}.csv'
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            scanner_data.append({
                'ticker': ticker,
                'price': df['Close'].iloc[-1],
                'zone': 'EXCELLENT'  # Get from your scanner logic
            })

    return render_template('scanner_charts.html', results=scanner_data)
```

Then update the JavaScript in `scanner_charts.html` to use the real data:

```javascript
const scannerResults = {{ results | tojson }};
```

## 🎨 Customization Options

### Chart Settings

Edit the widget configuration in the JavaScript:

```javascript
widget = new TradingView.widget({
    "symbol": ticker,
    "interval": "D",          // D=Daily, W=Weekly, M=Monthly
    "timezone": "America/New_York",
    "theme": "light",         // or "dark"
    "style": "1",             // 1=Candles, 0=Bars, 2=Line, etc.
    "locale": "en",

    // Your custom settings
    "studies": [
        // Add indicator IDs here
    ]
});
```

### Available Chart Styles

- `"style": "0"` - Bars
- `"style": "1"` - Candles (default)
- `"style": "2"` - Line
- `"style": "3"` - Area
- `"style": "9"` - Hollow Candles

### Available Timeframes

- `"interval": "1"` - 1 minute
- `"interval": "5"` - 5 minutes
- `"interval": "15"` - 15 minutes
- `"interval": "60"` - 1 hour
- `"interval": "D"` - Daily
- `"interval": "W"` - Weekly
- `"interval": "M"` - Monthly

## 🌐 Deployment

### Local Development
```bash
python flask_tradingview_app.py
```
Access at: `http://localhost:5000`

### Production Deployment

For production, use a proper WSGI server:

```bash
pip install gunicorn

gunicorn -w 4 -b 0.0.0.0:5000 flask_tradingview_app:app
```

Or use services like:
- **Heroku** - Free tier available
- **PythonAnywhere** - Free tier for Flask apps
- **AWS/Azure/GCP** - More control, requires setup

## 📱 Mobile Support

Both templates are fully responsive:
- ✅ Mobile-friendly layout
- ✅ Touch-friendly buttons
- ✅ Responsive chart sizing
- ✅ Sidebar collapses on mobile

## 🔍 Testing Your Setup

1. **Start the Flask app**
2. **Enter a ticker** (e.g., AAPL)
3. **Chart should load** with default TradingView indicators
4. **Click the indicators button** on the chart
5. **Search for your published indicators**
6. **Add them manually** to verify they work

## ⚠️ Common Issues

### Issue: Chart doesn't load
**Solution:** Check browser console for errors. Ensure internet connection (TradingView widget loads from CDN)

### Issue: Custom indicators don't appear
**Solution:**
- Verify indicator is published
- Check script ID is correct
- Try adding manually first
- Check visibility settings (public/invite-only)

### Issue: Ticker not found
**Solution:** TradingView uses different symbols for some stocks. Try:
- US stocks: Just the symbol (AAPL)
- Foreign stocks: Exchange prefix (TSX:SHOP)

### Issue: Slow loading
**Solution:**
- Limit number of indicators loaded
- Use smaller timeframe data ranges
- Consider caching in Flask

## 💡 Pro Tips

1. **Save Chart Layouts:** Users can save their preferred indicator setup in TradingView, it persists across sessions

2. **Direct Links:** Share direct links like `/chart/AAPL` for specific stocks

3. **Keyboard Shortcuts:** In scanner view, use arrow keys to navigate between charts

4. **Multiple Indicators:** You can load multiple custom indicators at once

5. **Templates:** Create TradingView templates for different strategies (swing, day trading, etc.)

## 📚 Additional Resources

- [TradingView Widget Documentation](https://www.tradingview.com/widget/)
- [Pine Script Manual](https://www.tradingview.com/pine-script-docs/)
- [Flask Documentation](https://flask.palletsprojects.com/)

## 🆘 Support

If you need help:
1. Check the TradingView widget console for errors (F12 in browser)
2. Verify your indicators are published and accessible
3. Test indicators work manually on TradingView.com first
4. Check Flask logs for server-side errors

---

**Created for Jimmy's Trading Scanners**
Version 1.0 - December 2024
