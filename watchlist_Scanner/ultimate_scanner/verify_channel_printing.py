"""Quick verification that channel is printing on current day"""
import pandas as pd
import numpy as np
import talib

# Test VCYT
ticker = 'VCYT'
df = pd.read_csv(f'../updated_Results_for_scan/{ticker}.csv', skiprows=[1, 2])
df.columns = df.columns.str.strip()
df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
df = df.dropna(subset=['Date'])
df = df.sort_values('Date')
df.set_index('Date', inplace=True)

for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df = df.dropna()

# Calculate Jimmy Channel
ema1 = talib.EMA(df['Close'].values, timeperiod=5)
ema2 = talib.EMA(df['Close'].values, timeperiod=26)
atr = talib.ATR(df['High'].values, df['Low'].values, df['Close'].values, timeperiod=50) * 0.4

# Squeeze condition
ema_diff = np.abs(ema2 - ema1)
in_squeeze = ema_diff < atr

# Channel boundaries
SqLup = ema2 + atr
SqLdn = ema2 - atr

# Check last 5 days
print(f"\n{ticker} - Last 5 Days Channel Status:")
print(f"{'Date':<12} {'Close':>8} {'EMA5':>8} {'EMA26':>8} {'Diff':>8} {'ATR':>8} {'Squeeze':>8} {'SqLup':>8} {'SqLdn':>8}")
print("-" * 100)

for i in range(len(df) - 5, len(df)):
    date = df.index[i].strftime('%Y-%m-%d')
    close = df['Close'].iloc[i]
    e1 = ema1[i]
    e2 = ema2[i]
    diff = ema_diff[i]
    atr_val = atr[i]
    squeeze = "YES" if in_squeeze[i] else "NO"
    up = SqLup[i]
    dn = SqLdn[i]

    print(f"{date:<12} ${close:>7.2f} ${e1:>7.2f} ${e2:>7.2f} ${diff:>7.2f} ${atr_val:>7.2f} {squeeze:>8} ${up:>7.2f} ${dn:>7.2f}")

print()
if in_squeeze[-1]:
    print(f"✓ CHANNEL IS PRINTING on {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Upper Channel: ${SqLup[-1]:.2f}")
    print(f"  Lower Channel: ${SqLdn[-1]:.2f}")
    print(f"  Current Close: ${df['Close'].iloc[-1]:.2f}")
else:
    print(f"✗ Channel NOT printing - EMAs too far apart")
