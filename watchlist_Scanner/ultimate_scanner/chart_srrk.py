import pandas as pd
import numpy as np
import talib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

def hma(data, period):
    """Calculate Hull Moving Average (HMA)"""
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    wma_half = talib.WMA(data, timeperiod=half_period)
    wma_full = talib.WMA(data, timeperiod=period)
    raw_hma = 2 * wma_half - wma_full
    hma_result = talib.WMA(raw_hma, timeperiod=sqrt_period)
    return hma_result

def jma(data, length, phase, power, source):
    """Jurik Moving Average (JMA)"""
    phaseRatio = phase if -100 <= phase <= 100 else (100 if phase > 100 else -100)
    phaseRatio = (phaseRatio / 100) + 1.5
    beta = 0.45 * (length - 1) / (0.45 * (length - 1) + 2)
    alpha = np.power(beta, power)

    e0 = np.zeros_like(source)
    e1 = np.zeros_like(source)
    e2 = np.zeros_like(source)
    jma_result = np.zeros_like(source)

    for i in range(1, len(source)):
        e0[i] = (1 - alpha) * source[i] + alpha * e0[i-1]
        e1[i] = (source[i] - e0[i]) * (1 - beta) + beta * e1[i-1]
        e2[i] = (e0[i] + phaseRatio * e1[i] - jma_result[i-1]) * np.power(1 - alpha, 2) + np.power(alpha, 2) * e2[i-1]
        jma_result[i] = e2[i] + jma_result[i-1]

    return jma_result

def calculate_fader_signal(df):
    """Calculate Fader signal"""
    fmal_zl, smal_zl = 2, 2
    tmal_zl = fmal_zl + smal_zl
    Fmal_zl = smal_zl + tmal_zl
    Ftmal_zl = tmal_zl + Fmal_zl
    Smal_zl = Fmal_zl + Ftmal_zl

    close_array = df['Close'].values
    m1_zl = talib.WMA(close_array, timeperiod=fmal_zl)
    m2_zl = talib.WMA(m1_zl, timeperiod=smal_zl)
    m3_zl = talib.WMA(m2_zl, timeperiod=tmal_zl)
    m4_zl = talib.WMA(m3_zl, timeperiod=Fmal_zl)
    m5_zl = talib.WMA(m4_zl, timeperiod=Ftmal_zl)
    mavw_zl = hma(m5_zl, Smal_zl)
    jma_result = jma(close_array, 7, 126, 0.89144, close_array)
    signal = (mavw_zl + jma_result) / 2
    return pd.Series(signal, index=df.index)

def calculate_force_index(df):
    """Calculate Elder Force Index"""
    force = (df['Close'] - df['Close'].shift(1)) * df['Volume']
    return force.ewm(span=13, adjust=False).mean()

def calculate_normalized_price(df, lookback=20):
    """Calculate normalized price (-1 to +1)"""
    highest = df['High'].rolling(window=lookback).max()
    lowest = df['Low'].rolling(window=lookback).min()
    range_size = highest - lowest
    range_size = range_size.replace(0, np.nan)
    normalized = 2 * ((df['Close'] - lowest) / range_size) - 1
    return normalized

def calculate_normalized_price_alt(df, lookback=20):
    """Calculate normalized price alternative (0 to 100)"""
    highest = df['High'].rolling(window=lookback).max()
    lowest = df['Low'].rolling(window=lookback).min()
    range_size = highest - lowest
    range_size = range_size.replace(0, np.nan)
    normalized = ((df['Close'] - lowest) / range_size) * 100
    return normalized

# Load SRRK data
df = pd.read_csv('../updated_Results_for_scan/SRRK.csv')
df['Date'] = pd.to_datetime(df['Date'])
df = df.sort_values('Date')
df = df.dropna()

# Only show last 60 days for clarity
df = df.tail(60).copy()
df = df.reset_index(drop=True)

# Calculate indicators
force_index = calculate_force_index(df)
norm_price_neg1to1 = calculate_normalized_price(df, 20)
norm_price_0to100 = calculate_normalized_price_alt(df, 20)
fader = calculate_fader_signal(df)

# Find Jan 9, 2026
target_date = pd.to_datetime('2026-01-09')
target_idx = df[df['Date'] == target_date].index
if len(target_idx) > 0:
    target_idx = target_idx[0]
    target_price = df.loc[target_idx, 'Close']
else:
    target_idx = None

# Create chart
fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
fig.suptitle('SRRK - Channel + EFI + Fader Analysis', fontsize=16, fontweight='bold')

# Panel 1: Price with Channel
ax1 = axes[0]
ax1.plot(df['Date'], df['Close'], 'b-', linewidth=1.5, label='Close')
ax1.set_ylabel('Price ($)', fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.legend(loc='upper left')

if target_idx is not None:
    ax1.axvline(df.loc[target_idx, 'Date'], color='red', linestyle='--', alpha=0.7, label='Jan 9, 2026')
    ax1.plot(df.loc[target_idx, 'Date'], target_price, 'ro', markersize=10)

# Panel 2: EFI Histogram
ax2 = axes[1]
colors = ['maroon' if x < force_index.std() * -2 else 'orange' if x < 0 else 'lime' if x < force_index.std() * 2 else 'green' for x in force_index]
ax2.bar(df['Date'], force_index, color=colors, alpha=0.7)
ax2.axhline(0, color='black', linestyle='-', linewidth=0.5)
ax2.set_ylabel('EFI Histogram', fontweight='bold')
ax2.grid(True, alpha=0.3)

if target_idx is not None:
    ax2.axvline(df.loc[target_idx, 'Date'], color='red', linestyle='--', alpha=0.7)

# Panel 3: Normalized Price (both scales)
ax3 = axes[2]
ax3_twin = ax3.twinx()

# Plot -1 to +1 scale
ax3.plot(df['Date'], norm_price_neg1to1, 'purple', linewidth=2, label='Norm Price (-1 to +1)')
ax3.axhline(0, color='black', linestyle='-', linewidth=1)
ax3.axhline(-1, color='gray', linestyle=':', linewidth=0.5)
ax3.axhline(1, color='gray', linestyle=':', linewidth=0.5)
ax3.set_ylabel('Normalized (-1 to +1)', fontweight='bold', color='purple')
ax3.tick_params(axis='y', labelcolor='purple')
ax3.grid(True, alpha=0.3)

# Plot 0 to 100 scale
ax3_twin.plot(df['Date'], norm_price_0to100, 'green', linewidth=2, alpha=0.5, label='Norm Price (0 to 100)')
ax3_twin.set_ylabel('Normalized (0 to 100)', fontweight='bold', color='green')
ax3_twin.tick_params(axis='y', labelcolor='green')

if target_idx is not None:
    ax3.axvline(df.loc[target_idx, 'Date'], color='red', linestyle='--', alpha=0.7)
    norm_val_neg1 = norm_price_neg1to1.iloc[target_idx]
    norm_val_0to100 = norm_price_0to100.iloc[target_idx]
    ax3.plot(df.loc[target_idx, 'Date'], norm_val_neg1, 'ro', markersize=10)
    ax3.text(df.loc[target_idx, 'Date'], norm_val_neg1, f'  {norm_val_neg1:.2f}',
             verticalalignment='center', color='purple', fontweight='bold')
    ax3_twin.text(df.loc[target_idx, 'Date'], norm_val_0to100, f'  {norm_val_0to100:.1f}',
                  verticalalignment='bottom', color='green', fontweight='bold')

# Panel 4: Fader
ax4 = axes[3]
fader_colors = ['green' if fader.iloc[i] > fader.iloc[i-1] else 'red' for i in range(1, len(fader))]
fader_colors.insert(0, 'red')
ax4.plot(df['Date'], fader, color='blue', linewidth=2, label='Fader Signal')
for i in range(len(df)):
    ax4.axvspan(df.iloc[i-1]['Date'] if i > 0 else df.iloc[i]['Date'],
                df.iloc[i]['Date'],
                alpha=0.2, color=fader_colors[i])
ax4.set_ylabel('Fader', fontweight='bold')
ax4.set_xlabel('Date', fontweight='bold')
ax4.grid(True, alpha=0.3)

if target_idx is not None:
    ax4.axvline(df.loc[target_idx, 'Date'], color='red', linestyle='--', alpha=0.7, label='Jan 9, 2026')

# Format x-axis
ax4.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
ax4.xaxis.set_major_locator(mdates.DayLocator(interval=5))
plt.xticks(rotation=45)

plt.tight_layout()
plt.savefig('SRRK_analysis_chart.png', dpi=150, bbox_inches='tight')
print("Chart saved as 'SRRK_analysis_chart.png'")

# Print values for Jan 9, 2026
if target_idx is not None:
    print(f"\nSRRK - January 9, 2026 Values:")
    print(f"  Close Price:           ${df.loc[target_idx, 'Close']:.2f}")
    print(f"  EFI Histogram:         {force_index.iloc[target_idx]:,.0f}")
    print(f"  Norm Price (-1 to +1): {norm_price_neg1to1.iloc[target_idx]:.3f}")
    print(f"  Norm Price (0 to 100): {norm_price_0to100.iloc[target_idx]:.2f}")
    print(f"  Fader Value:           {fader.iloc[target_idx]:.2f}")
    print(f"  Fader Color:           {fader_colors[target_idx].upper()}")
