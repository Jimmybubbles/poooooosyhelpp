"""
RANGE + SCORE SCANNER
=====================
Philosophy: Range gives you the TRADE (entry, stop, target, R:R).
            Indicators give you the SCORE (how good is the setup right now).

BASE: Price at 25% of range = entry zone
  - Entry: L25 (25% of range)
  - Stop:  L0  (bottom of range)
  - Target: L75 (75% of range)
  - Fixed 1:2 R:R built in

FILTERS (must pass):
  - Price <= $10 (capital constraint)
  - Weekly Fader GREEN (uptrend bias on higher timeframe)

SCORE SYSTEM (indicators layered on top of range):
  - Channel consolidation at level:    +25 pts
  - EFI price line (normprice) > 0:    +20 pts
  - EFI force index < 0 (exhaustion):  +20 pts
  - Daily Fader green:                 +15 pts
  - DMI Stoch in/near oversold:        +15 pts
  - Volume above average:              +5 pts

Max score = 100
"""

import pandas as pd
import numpy as np
import os
import talib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import sys

# Add the watchlist_Scanner directory to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from EFI_Indicator import EFI_Indicator

# Configuration
CSV_DIR = os.path.join(script_dir, 'updated_Results_for_scan')
OUTPUT_DIR = os.path.join(script_dir, 'buylist')

# Scanner parameters
MAX_PRICE = 10.0
MIN_PRICE = 0.50
MIN_DATA_ROWS = 100

# Channel parameters (from JimmyChannelScan)
CHANNEL_EMA_FAST = 5
CHANNEL_EMA_SLOW = 26
CHANNEL_ATR_PERIOD = 50
CHANNEL_ATR_MULT = 0.4

# DMI Stochastic parameters
DMI_LENGTH = 32
STOCH_LENGTH = 50
STOCH_SMOOTH = 9
OVERSOLD = 10
OVERBOUGHT = 90

# Email config
EMAIL_TO = "james.anthony.russell36@gmail.com"


# ============================================================
# RANGE LOGIC (the trade structure)
# ============================================================

def get_range_info(price):
    """Get range levels for a price. Under $10 uses $1 ranges."""
    if price <= 0:
        return None

    if price < 10:
        range_size = 1.0
        range_low = int(price)
        if range_low == 0:
            range_low = 0
    elif price < 100:
        range_size = 10.0
        range_low = int(price / 10) * 10
    elif price < 500:
        range_size = 50.0
        range_low = int(price / 50) * 50
    else:
        range_size = 100.0
        range_low = int(price / 100) * 100

    range_high = range_low + range_size

    levels = {
        'L0': range_low,
        'L25': range_low + (range_size * 0.25),
        'L50': range_low + (range_size * 0.50),
        'L75': range_low + (range_size * 0.75),
        'L100': range_high
    }

    position_pct = ((price - range_low) / range_size) * 100

    return {
        'range_low': range_low,
        'range_high': range_high,
        'range_size': range_size,
        'levels': levels,
        'position_pct': position_pct,
    }


# ============================================================
# INDICATOR SCORING FUNCTIONS
# ============================================================

def calculate_weekly_fader(df):
    """
    Calculate Fader on weekly resampled data.
    Returns 'green' or 'red'.
    """
    try:
        weekly = df.resample('W').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()

        if len(weekly) < 30:
            return 'neutral'

        close = weekly['Close'].values
        period = 20
        half_period = period // 2
        sqrt_period = int(np.sqrt(period))

        wma1 = talib.WMA(close, timeperiod=half_period)
        wma2 = talib.WMA(close, timeperiod=period)

        diff = 2 * wma1 - wma2
        hma = talib.WMA(diff, timeperiod=sqrt_period)

        if hma[-1] > hma[-2]:
            return 'green'
        else:
            return 'red'
    except Exception:
        return 'neutral'


def calculate_daily_fader(df):
    """Calculate Fader on daily data."""
    if len(df) < 50:
        return 'neutral'

    close = df['Close'].values
    period = 20
    half_period = period // 2
    sqrt_period = int(np.sqrt(period))

    wma1 = talib.WMA(close, timeperiod=half_period)
    wma2 = talib.WMA(close, timeperiod=period)

    diff = 2 * wma1 - wma2
    hma = talib.WMA(diff, timeperiod=sqrt_period)

    idx = len(df) - 1
    if idx >= 2 and not np.isnan(hma[idx]) and not np.isnan(hma[idx - 1]):
        return 'green' if hma[idx] > hma[idx - 1] else 'red'

    return 'neutral'


def detect_channel(df):
    """
    Detect squeeze channel consolidation (from JimmyChannelScan).
    Returns True if currently in a channel or recently broke out.
    """
    try:
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)

        ema_fast = talib.EMA(close, timeperiod=CHANNEL_EMA_FAST)
        ema_slow = talib.EMA(close, timeperiod=CHANNEL_EMA_SLOW)
        atr = talib.ATR(high, low, close, timeperiod=CHANNEL_ATR_PERIOD) * CHANNEL_ATR_MULT

        # Channel exists when abs(ema_fast - ema_slow) < atr * mult
        in_channel = np.abs(ema_fast - ema_slow) < atr

        # Check last 10 bars for channel
        recent = in_channel[-10:]
        bars_in_channel = np.sum(recent[~np.isnan(recent)])

        return bars_in_channel >= 5  # At least 5 of last 10 bars in channel
    except Exception:
        return False


def calculate_dmi_stochastic(df):
    """Calculate DMI Stochastic value."""
    try:
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        close = df['Close'].values.astype(float)

        diplus = talib.PLUS_DI(high, low, close, timeperiod=DMI_LENGTH)
        diminus = talib.MINUS_DI(high, low, close, timeperiod=DMI_LENGTH)

        osc = diplus - diminus
        osc_series = pd.Series(osc)
        highest = osc_series.rolling(window=STOCH_LENGTH).max()
        lowest = osc_series.rolling(window=STOCH_LENGTH).min()

        raw_stoch = np.where(
            (highest - lowest) != 0,
            (osc_series - lowest) / (highest - lowest) * 100,
            50
        )

        stoch = pd.Series(raw_stoch).rolling(window=STOCH_SMOOTH).mean().values
        return stoch[-1] if not np.isnan(stoch[-1]) else 50
    except Exception:
        return 50


# ============================================================
# MAIN SCANNER
# ============================================================

def scan_stock(ticker):
    """
    Scan a single stock.
    Returns dict with trade setup + score, or None.
    """
    csv_file = os.path.join(CSV_DIR, f"{ticker}.csv")
    if not os.path.exists(csv_file):
        return None

    try:
        df = pd.read_csv(csv_file, skiprows=[1, 2])

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

        if len(df) < MIN_DATA_ROWS:
            return None

        current_price = df['Close'].iloc[-1]

        # === HARD FILTERS ===

        # Price filter: max $10
        if current_price < MIN_PRICE or current_price > MAX_PRICE:
            return None

        # Range filter: must be in 25% zone
        range_info = get_range_info(current_price)
        if range_info is None:
            return None

        # Check if in 25% zone (12.5% - 37.5% of range)
        if range_info['position_pct'] < 12.5 or range_info['position_pct'] > 37.5:
            return None

        # Weekly Fader filter: must be GREEN (uptrend)
        weekly_fader = calculate_weekly_fader(df)
        if weekly_fader != 'green':
            return None

        # === TRADE STRUCTURE (from range) ===
        entry = range_info['levels']['L25']
        stop = range_info['levels']['L0']
        target = range_info['levels']['L75']
        risk = entry - stop
        reward = target - entry
        rr = reward / risk if risk > 0 else 0

        # === SCORE SYSTEM (indicators on top) ===
        score = 0
        score_breakdown = []

        # 1. Channel consolidation (+25)
        has_channel = detect_channel(df)
        if has_channel:
            score += 25
            score_breakdown.append("Channel +25")

        # 2. EFI price line (normprice) > 0 (+20)
        efi = EFI_Indicator()
        efi_results = efi.calculate(df)
        normprice = efi_results['normalized_price'].iloc[-1]
        force_index = efi_results['force_index'].iloc[-1]
        fi_color = efi_results['fi_color'].iloc[-1]

        if normprice > 0:
            score += 20
            score_breakdown.append("EFI PriceLine>0 +20")

        # 3. EFI force index < 0 = selling exhaustion (+20)
        if force_index < 0:
            score += 20
            score_breakdown.append("EFI FI<0 (exhaustion) +20")

        # 4. Daily Fader green (+15)
        daily_fader = calculate_daily_fader(df)
        if daily_fader == 'green':
            score += 15
            score_breakdown.append("Daily Fader GREEN +15")

        # 5. DMI Stoch near/in oversold (+15)
        dmi_stoch = calculate_dmi_stochastic(df)
        if dmi_stoch <= OVERSOLD:
            score += 15
            score_breakdown.append(f"DMI Stoch OS({dmi_stoch:.0f}) +15")
        elif dmi_stoch <= 25:
            score += 10
            score_breakdown.append(f"DMI Stoch near OS({dmi_stoch:.0f}) +10")

        # 6. Volume above average (+5)
        avg_vol = df['Volume'].iloc[-20:].mean()
        current_vol = df['Volume'].iloc[-1]
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0
        if vol_ratio >= 1.0:
            score += 5
            score_breakdown.append(f"Vol {vol_ratio:.1f}x +5")

        return {
            'ticker': ticker,
            'price': current_price,
            'range': f"${range_info['range_low']}-${range_info['range_high']}",
            'range_low': range_info['range_low'],
            'range_high': range_info['range_high'],
            'position_pct': range_info['position_pct'],
            'entry': entry,
            'stop': stop,
            'target': target,
            'risk': risk,
            'reward': reward,
            'rr': rr,
            'score': score,
            'score_breakdown': score_breakdown,
            'weekly_fader': weekly_fader,
            'daily_fader': daily_fader,
            'has_channel': has_channel,
            'normprice': normprice,
            'force_index': force_index,
            'fi_color': fi_color,
            'dmi_stoch': dmi_stoch,
            'vol_ratio': vol_ratio,
            'date': df.index[-1].strftime('%Y-%m-%d'),
        }

    except Exception:
        return None


def run_scan():
    """Run the full scan."""
    print("=" * 90)
    print("RANGE + SCORE SCANNER")
    print("Range = Trade Structure | Indicators = Quality Score")
    print("=" * 90)
    print()
    print("FILTERS: Price <= $10 | 25% zone | Weekly Fader GREEN")
    print("SCORING: Channel(25) + PriceLine>0(20) + FI<0(20) + DailyFader(15) + DMIStoch(15) + Vol(5)")
    print()

    csv_files = [f for f in os.listdir(CSV_DIR) if f.endswith('.csv')]
    tickers = [f[:-4] for f in csv_files]
    print(f"Scanning {len(tickers)} tickers...")
    print()

    results = []
    scanned = 0

    for ticker in tickers:
        result = scan_stock(ticker)
        if result:
            results.append(result)

        scanned += 1
        if scanned % 500 == 0:
            print(f"  {scanned} scanned... {len(results)} setups found")

    # Sort by score descending
    results.sort(key=lambda x: x['score'], reverse=True)

    print(f"\nScan complete! {scanned} stocks scanned")
    print(f"Found {len(results)} setups (price <= $10, 25% zone, weekly uptrend)")
    print()

    return results


def build_report(results):
    """Build the text report."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    lines = []
    lines.append("=" * 90)
    lines.append(f"RANGE + SCORE DAILY REPORT - {now}")
    lines.append("=" * 90)
    lines.append("")
    lines.append("PHILOSOPHY:")
    lines.append("  Range = Trade (entry, stop, target, R:R)")
    lines.append("  Indicators = Score (how good is the setup)")
    lines.append("")
    lines.append("FILTERS: Price <= $10 | 25% zone | Weekly Fader GREEN")
    lines.append("SCORE:   Channel(25) + PriceLine>0(20) + FI<0(20) + Fader(15) + DMI(15) + Vol(5) = /100")
    lines.append("")
    lines.append(f"Total Setups Found: {len(results)}")
    lines.append("")

    if not results:
        lines.append("No setups found today matching all criteria.")
        return "\n".join(lines)

    # Summary table
    lines.append("=" * 90)
    lines.append(f"{'Ticker':<7} {'Price':>7} {'Range':<9} {'Entry':>7} {'Stop':>7} "
                 f"{'Target':>7} {'R:R':>5} {'Score':>6} {'Key Signals'}")
    lines.append("-" * 90)

    for r in results:
        signals = []
        if r['has_channel']:
            signals.append("CH")
        if r['normprice'] > 0:
            signals.append("PL+")
        if r['force_index'] < 0:
            signals.append("FI-")
        if r['daily_fader'] == 'green':
            signals.append("DF")
        if r['dmi_stoch'] <= OVERSOLD:
            signals.append("OS")
        elif r['dmi_stoch'] <= 25:
            signals.append("nOS")
        if r['vol_ratio'] >= 1.0:
            signals.append(f"V{r['vol_ratio']:.1f}")
        sig_str = " | ".join(signals)

        lines.append(
            f"{r['ticker']:<7} ${r['price']:>6.2f} {r['range']:<9} "
            f"${r['entry']:>6.2f} ${r['stop']:>6.2f} "
            f"${r['target']:>6.2f} {r['rr']:>5.1f} "
            f"{r['score']:>5}/100 {sig_str}"
        )

    lines.append("")

    # Detailed breakdown for top setups
    lines.append("=" * 90)
    lines.append("DETAILED BREAKDOWN - TOP SETUPS")
    lines.append("=" * 90)

    for r in results[:10]:
        lines.append("")
        lines.append(f"--- {r['ticker']} @ ${r['price']:.2f} ---")
        lines.append(f"  Range: {r['range']}  |  Position: {r['position_pct']:.0f}%")
        lines.append(f"  Entry: ${r['entry']:.2f}  |  Stop: ${r['stop']:.2f}  |  Target: ${r['target']:.2f}")
        lines.append(f"  Risk: ${r['risk']:.2f}  |  Reward: ${r['reward']:.2f}  |  R:R = 1:{r['rr']:.1f}")
        lines.append(f"  Weekly Fader: {r['weekly_fader'].upper()}  |  Daily Fader: {r['daily_fader'].upper()}")
        lines.append(f"  EFI PriceLine: {r['normprice']:.3f}  |  Force Index: {r['force_index']:.3f} ({r['fi_color']})")
        lines.append(f"  DMI Stoch: {r['dmi_stoch']:.1f}  |  Channel: {'YES' if r['has_channel'] else 'No'}")
        lines.append(f"  Volume: {r['vol_ratio']:.2f}x avg")
        lines.append(f"  SCORE: {r['score']}/100")
        for s in r['score_breakdown']:
            lines.append(f"    {s}")

    lines.append("")
    lines.append("=" * 90)

    # TradingView list
    tv_list = ",".join(r['ticker'] for r in results)
    lines.append(f"TRADINGVIEW: {tv_list}")
    lines.append("=" * 90)

    return "\n".join(lines)


def save_report(report, results):
    """Save report to files."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Main report
    today = datetime.now().strftime('%Y-%m-%d')
    report_file = os.path.join(OUTPUT_DIR, f'range_score_report_{today}.txt')
    with open(report_file, 'w') as f:
        f.write(report)
    print(f"Report saved to: {report_file}")

    # Also save as latest
    latest_file = os.path.join(OUTPUT_DIR, 'range_score_report_latest.txt')
    with open(latest_file, 'w') as f:
        f.write(report)

    # TradingView list (comma separated)
    tv_file = os.path.join(OUTPUT_DIR, 'tradingview_range_score.txt')
    with open(tv_file, 'w') as f:
        f.write(",".join(r['ticker'] for r in results))
    print(f"TradingView list saved to: {tv_file}")

    return report_file


def send_email(report):
    """
    Send report via email using Gmail SMTP.

    Requires a Gmail App Password (not your regular password).
    Set these environment variables:
      GMAIL_USER = your gmail address
      GMAIL_APP_PASSWORD = your 16-char app password

    To create an App Password:
      1. Go to myaccount.google.com
      2. Security > 2-Step Verification (enable if not already)
      3. App Passwords > Generate
      4. Copy the 16-character password
    """
    gmail_user = os.environ.get('GMAIL_USER')
    gmail_pass = os.environ.get('GMAIL_APP_PASSWORD')

    if not gmail_user or not gmail_pass:
        print("\n  EMAIL NOT SENT - Set environment variables:")
        print("    GMAIL_USER = your.email@gmail.com")
        print("    GMAIL_APP_PASSWORD = your-16-char-app-password")
        print("")
        print("  To create an App Password:")
        print("    1. Go to myaccount.google.com")
        print("    2. Security > 2-Step Verification (enable first)")
        print("    3. App Passwords > Generate")
        print("    4. Then set the env vars:")
        print('    setx GMAIL_USER "your.email@gmail.com"')
        print('    setx GMAIL_APP_PASSWORD "abcd efgh ijkl mnop"')
        return False

    today = datetime.now().strftime('%Y-%m-%d')
    subject = f"Range+Score Daily Scan - {today}"

    msg = MIMEMultipart()
    msg['From'] = gmail_user
    msg['To'] = EMAIL_TO
    msg['Subject'] = subject

    # Use monospace font for alignment
    html_report = f"<pre style='font-family: Consolas, monospace; font-size: 12px;'>{report}</pre>"
    msg.attach(MIMEText(html_report, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, EMAIL_TO, msg.as_string())
        server.quit()
        print(f"Email sent to {EMAIL_TO}")
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False


def main():
    results = run_scan()
    report = build_report(results)

    # Print top results
    if results:
        print("=" * 90)
        print("TOP SETUPS")
        print("=" * 90)
        print(f"{'Ticker':<7} {'Price':>7} {'Range':<9} {'Entry':>7} {'Stop':>7} "
              f"{'Target':>7} {'R:R':>5} {'Score':>6}")
        print("-" * 65)
        for r in results[:15]:
            print(f"{r['ticker']:<7} ${r['price']:>6.2f} {r['range']:<9} "
                  f"${r['entry']:>6.2f} ${r['stop']:>6.2f} "
                  f"${r['target']:>6.2f} {r['rr']:>5.1f} {r['score']:>5}/100")

    # Save report
    save_report(report, results)

    # Send email
    print()
    send_email(report)


if __name__ == "__main__":
    main()
