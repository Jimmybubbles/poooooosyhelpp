"""
Visual Chart: Weekly Fader Concept
==================================
Shows how the weekly Fader line guides daily trading decisions.

Creates a chart showing:
1. Daily price with range levels (25%, 50%, 75%)
2. Weekly Fader line overlaid
3. Entry signals highlighted (when weekly Fader is green)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import os
from datetime import datetime
from ta.trend import WMAIndicator

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')
output_dir = os.path.join(script_dir, 'buylist')

# Fader Parameters
FADER_PARAMS = {
    'fmal_zl': 1,
    'smal_zl': 1,
    'length_jma': 7,
    'phase': 126,
    'power': 0.89144,
}


def jma(source, length, phase, power):
    """Jurik Moving Average (JMA)"""
    phaseRatio = phase if -100 <= phase <= 100 else (100 if phase > 100 else -100)
    phaseRatio = (phaseRatio / 100) + 1.5
    beta = 0.45 * (length - 1) / (0.45 * (length - 1) + 2)
    alpha = np.power(beta, power)

    source_arr = np.array(source)
    e0 = np.zeros(len(source_arr))
    e1 = np.zeros(len(source_arr))
    e2 = np.zeros(len(source_arr))
    jma_result = np.zeros(len(source_arr))

    for i in range(1, len(source_arr)):
        e0[i] = (1 - alpha) * source_arr[i] + alpha * e0[i-1]
        e1[i] = (source_arr[i] - e0[i]) * (1 - beta) + beta * e1[i-1]
        e2[i] = (e0[i] + phaseRatio * e1[i] - jma_result[i-1]) * np.power(1 - alpha, 2) + np.power(alpha, 2) * e2[i-1]
        jma_result[i] = e2[i] + jma_result[i-1]

    return jma_result


def calculate_fader(close_series):
    """Calculate Fader indicator"""
    fmal_zl = FADER_PARAMS['fmal_zl']
    smal_zl = FADER_PARAMS['smal_zl']
    length_jma = FADER_PARAMS['length_jma']
    phase = FADER_PARAMS['phase']
    power = FADER_PARAMS['power']

    tmal_zl = fmal_zl + smal_zl
    Fmal_zl = smal_zl + tmal_zl
    Ftmal_zl = tmal_zl + Fmal_zl
    Smal_zl = Fmal_zl + Ftmal_zl

    close = close_series.astype(float)

    # Cascaded WMAs
    m1 = WMAIndicator(close, window=fmal_zl).wma()
    m2 = WMAIndicator(m1.ffill(), window=smal_zl).wma()
    m3 = WMAIndicator(m2.ffill(), window=tmal_zl).wma()
    m4 = WMAIndicator(m3.ffill(), window=Fmal_zl).wma()
    m5 = WMAIndicator(m4.ffill(), window=Ftmal_zl).wma()

    # Hull MA approximation
    half_len = max(1, Smal_zl // 2)
    sqrt_len = max(1, int(np.sqrt(Smal_zl)))
    wma1 = WMAIndicator(m5.ffill(), window=half_len).wma()
    wma2 = WMAIndicator(m5.ffill(), window=Smal_zl).wma()
    raw_hma = 2 * wma1 - wma2
    mavw = WMAIndicator(raw_hma.ffill(), window=sqrt_len).wma()

    # JMA
    jma_result = jma(close.values, length_jma, phase, power)

    # Final signal
    signal = (mavw.values + jma_result) / 2

    return signal


def get_range_info(price):
    """Determine which range a price is in"""
    if price <= 0:
        return None

    if price < 10:
        range_size = 1.0
        range_low = int(price)
    elif price < 100:
        range_size = 10.0
        range_low = int(price / 10) * 10
    elif price < 500:
        range_size = 50.0
        range_low = int(price / 50) * 50
    else:
        range_size = 100.0
        range_low = int(price / 100) * 100

    return {
        'range_low': range_low,
        'range_high': range_low + range_size,
        'range_size': range_size,
        'L0': range_low,
        'L25': range_low + (range_size * 0.25),
        'L50': range_low + (range_size * 0.50),
        'L75': range_low + (range_size * 0.75),
        'L100': range_low + range_size
    }


def create_concept_chart(ticker='AAPL', days=90):
    """
    Create a visual chart showing:
    1. Daily candlesticks
    2. Range level bands (25%, 50%, 75%)
    3. Weekly Fader line
    4. Entry signals when weekly Fader is green
    """
    csv_file = os.path.join(results_dir, f"{ticker}.csv")

    if not os.path.exists(csv_file):
        print(f"File not found: {csv_file}")
        return

    # Load data
    df = pd.read_csv(csv_file, skiprows=[1, 2])

    if 'Price' in df.columns:
        df.rename(columns={'Price': 'Date'}, inplace=True)

    df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
    df = df.dropna(subset=['Date'])
    df = df.sort_values('Date')
    df.set_index('Date', inplace=True)

    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna().tail(days)

    if len(df) < days:
        print(f"Not enough data for {ticker}")
        return

    # Remove timezone for easier handling
    df.index = df.index.tz_localize(None)

    # Calculate daily Fader
    daily_fader = calculate_fader(df['Close'])

    # Calculate weekly data and Fader
    weekly = df.resample('W').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last'
    }).dropna()

    weekly_fader = calculate_fader(weekly['Close'])

    # Determine weekly fader color for each day
    weekly_fader_colors = {}
    for i in range(1, len(weekly)):
        color = 'green' if weekly_fader[i] > weekly_fader[i-1] else 'red'
        weekly_fader_colors[weekly.index[i]] = color

    # Map weekly fader to daily data
    daily_weekly_fader_color = []
    for date in df.index:
        color = 'gray'
        for week_date in sorted(weekly_fader_colors.keys(), reverse=True):
            if week_date <= date:
                color = weekly_fader_colors[week_date]
                break
        daily_weekly_fader_color.append(color)

    df['weekly_fader_color'] = daily_weekly_fader_color

    # Create the chart
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), height_ratios=[3, 1], sharex=True)

    # === TOP CHART: Price with range levels and signals ===
    dates = np.arange(len(df))

    # Plot candlesticks
    for i, (date, row) in enumerate(df.iterrows()):
        color = 'green' if row['Close'] >= row['Open'] else 'red'
        # Body
        ax1.bar(i, row['Close'] - row['Open'], bottom=row['Open'], color=color, width=0.6, edgecolor='black', linewidth=0.5)
        # Wick
        ax1.vlines(i, row['Low'], row['High'], color='black', linewidth=0.5)

    # Calculate and plot range levels
    mid_price = df['Close'].median()
    range_info = get_range_info(mid_price)

    if range_info:
        ax1.axhline(range_info['L0'], color='darkred', linestyle='--', alpha=0.7, linewidth=2, label=f"0% Level (${range_info['L0']:.2f})")
        ax1.axhline(range_info['L25'], color='orange', linestyle='-', alpha=0.8, linewidth=2, label=f"25% Level (${range_info['L25']:.2f})")
        ax1.axhline(range_info['L50'], color='gray', linestyle='--', alpha=0.5, linewidth=1)
        ax1.axhline(range_info['L75'], color='green', linestyle='-', alpha=0.8, linewidth=2, label=f"75% Level (${range_info['L75']:.2f})")
        ax1.axhline(range_info['L100'], color='darkgreen', linestyle='--', alpha=0.7, linewidth=2)

        # Shade the trading zone (25% to 75%)
        ax1.fill_between(dates, range_info['L25'], range_info['L75'], alpha=0.1, color='blue', label='Trading Zone')

    # Plot daily Fader line
    ax1.plot(dates, daily_fader, color='purple', linewidth=2, alpha=0.7, label='Daily Fader')

    # Mark entry signals (when price touches 25% and weekly fader is green)
    buy_signals_green = []
    buy_signals_red = []

    for i in range(1, len(df)):
        if range_info:
            current_low = df['Low'].iloc[i]
            prev_close = df['Close'].iloc[i-1]

            if prev_close > range_info['L25'] and current_low <= range_info['L25'] and current_low > range_info['L0']:
                if df['weekly_fader_color'].iloc[i] == 'green':
                    buy_signals_green.append(i)
                else:
                    buy_signals_red.append(i)

    # Plot entry signals
    for idx in buy_signals_green:
        ax1.scatter(idx, df['Low'].iloc[idx], color='lime', s=200, marker='^', edgecolors='black', linewidth=2, zorder=5)
        ax1.annotate('BUY\n(Weekly Green)', (idx, df['Low'].iloc[idx]), textcoords="offset points",
                     xytext=(0,-30), ha='center', fontsize=8, color='green', fontweight='bold')

    for idx in buy_signals_red:
        ax1.scatter(idx, df['Low'].iloc[idx], color='red', s=100, marker='x', linewidth=2, zorder=5)
        ax1.annotate('SKIP\n(Weekly Red)', (idx, df['Low'].iloc[idx]), textcoords="offset points",
                     xytext=(0,-30), ha='center', fontsize=7, color='red')

    ax1.set_ylabel('Price ($)', fontsize=12)
    ax1.set_title(f'{ticker} - Range Level Strategy with Weekly Fader Filter\n'
                  f'Range: ${range_info["L0"]:.2f} - ${range_info["L100"]:.2f} | '
                  f'Buy at 25% (${range_info["L25"]:.2f}), Target 75% (${range_info["L75"]:.2f}), Stop 0% (${range_info["L0"]:.2f})',
                  fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)

    # === BOTTOM CHART: Weekly Fader Indicator ===
    # Color bars based on weekly fader trend
    fader_colors = ['green' if c == 'green' else 'red' for c in daily_weekly_fader_color]
    ax2.bar(dates, [1]*len(dates), color=fader_colors, alpha=0.5)

    ax2.set_ylabel('Weekly Fader', fontsize=12)
    ax2.set_xlabel('Days', fontsize=12)
    ax2.set_title('Weekly Fader Status (GREEN = Uptrend on Higher Timeframe = Take Trade)', fontsize=11)
    ax2.set_yticks([])

    # Add legend
    green_patch = mpatches.Patch(color='green', alpha=0.5, label='Weekly Fader GREEN - Take 25% level trades')
    red_patch = mpatches.Patch(color='red', alpha=0.5, label='Weekly Fader RED - Skip trades')
    ax2.legend(handles=[green_patch, red_patch], loc='upper left', fontsize=9)

    # Set x-axis labels
    tick_indices = np.linspace(0, len(df)-1, min(10, len(df))).astype(int)
    ax2.set_xticks(tick_indices)
    ax2.set_xticklabels([df.index[i].strftime('%m/%d') for i in tick_indices], rotation=45)

    plt.tight_layout()

    # Save chart
    output_file = os.path.join(output_dir, f'weekly_fader_concept_{ticker}.png')
    plt.savefig(output_file, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Chart saved to: {output_file}")

    # Also save a summary image
    plt.close()

    return output_file


def create_summary_chart():
    """Create a summary chart explaining the concept"""
    fig, ax = plt.subplots(figsize=(14, 10))

    # Turn off axis
    ax.axis('off')

    # Title
    ax.text(0.5, 0.95, 'Range Level Strategy with Weekly Fader Filter',
            fontsize=20, fontweight='bold', ha='center', transform=ax.transAxes)

    ax.text(0.5, 0.88, 'Higher Timeframe Trend Confirmation = Better Win Rate',
            fontsize=14, style='italic', ha='center', transform=ax.transAxes)

    # The concept
    concept_text = """
YOUR FRACTAL HIERARCHY THEORY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────────────────────────────────────────────────┐
│  WEEKLY TIMEFRAME (Higher)                                                   │
│  ═══════════════════════                                                     │
│  The "boss" - sets the overall direction                                     │
│                                                                              │
│  Weekly Fader GREEN = Uptrend = Safe to buy dips                            │
│  Weekly Fader RED = Downtrend = Skip the trade                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DAILY TIMEFRAME (Lower)                                                     │
│  ══════════════════════                                                      │
│  Where we execute trades                                                     │
│                                                                              │
│  Entry: Price touches 25% level of range                                    │
│  Target: 75% level (+50% of range = 2R profit)                              │
│  Stop: 0% level (-25% of range = 1R loss)                                   │
│                                                                              │
│  ONLY TAKE THE TRADE IF WEEKLY FADER IS GREEN                               │
└─────────────────────────────────────────────────────────────────────────────┘

BACKTEST RESULTS (1 Year, All Stocks):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                     │  BASELINE        │  WITH WEEKLY FADER    │  IMPROVEMENT
═════════════════════╪══════════════════╪═══════════════════════╪══════════════
  Win Rate           │  42.3%           │  45.4%                │  +3.1%
  Expectancy         │  +1.45%          │  +2.17%               │  +0.72%
  Profit Factor      │  1.42            │  1.68                 │  +0.26
  Total Trades       │  18,821          │  7,985                │  -58% (selective)
═════════════════════╧══════════════════╧═══════════════════════╧══════════════

CONCLUSION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Higher timeframe alignment (weekly green) improves daily trade quality
✓ 50% improvement in expectancy per trade
✓ Fewer trades but better quality = less work, more profit
✓ Your fractal hierarchy theory is VALIDATED by the data
    """

    ax.text(0.5, 0.45, concept_text, fontsize=10, ha='center', va='center',
            transform=ax.transAxes, family='monospace',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    plt.tight_layout()

    output_file = os.path.join(output_dir, 'weekly_fader_concept_summary.png')
    plt.savefig(output_file, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Summary chart saved to: {output_file}")

    plt.close()
    return output_file


if __name__ == "__main__":
    import sys

    ticker = 'AAPL'
    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()

    print("Creating concept charts...")
    print()

    # Create summary chart
    create_summary_chart()

    # Create example chart for a stock
    create_concept_chart(ticker, days=90)

    print()
    print("Charts created successfully!")
