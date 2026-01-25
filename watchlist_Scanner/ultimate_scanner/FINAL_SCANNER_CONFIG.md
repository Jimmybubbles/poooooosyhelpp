# Ultimate Scanner - Final Configuration

## ✅ COMPLETED - TradingView EFI Method Implemented

The scanner now uses the **exact same calculations** as your TradingView EFI indicator.

---

## Scanning Criteria (All 4 Must Be TRUE)

### 1. Channel Consolidation ✓
- Dynamic consolidation detection (10-60 day windows)
- Range must be < 15% (tight consolidation)
- 70%+ bars must touch channel boundaries
- **No minimum duration** - any consolidation length accepted

### 2. EFI Oversold (MAROON or ORANGE) ✓
Uses TradingView's custom EFI calculation:
```python
# Volume proxy using ATR
atr = ATR(high, low, close, 11)
vw = (close * atr) / atr

# Force Index
forceindex = (close - close[1]) * vw / SMA(vw, 1) * 13
fi_ema = EMA(forceindex, 13)

# Color coding
MAROON: change < 0 and fi_ema < 0
ORANGE: change ≥ 0 and fi_ema < 0
TEAL:   change ≤ 0 and fi_ema > 0
LIME:   change > 0 and fi_ema > 0
```

We want: **MAROON or ORANGE** (selling pressure)

### 3. Normalized Price > 0 (DIVERGENCE) ✓
**TradingView Method:**
```python
basis = EMA(close, 68)  # 68-period EMA
normprice = close - basis

# Criterion: normprice > 0
# Meaning: Price is ABOVE the 68 EMA
```

**This creates DIVERGENCE when:**
- EFI is oversold (selling pressure)
- BUT price is above 68 EMA (showing strength)
- = Price refusing to break down despite selling

### 4. Fader Signal GREEN ✓
Multi-layered momentum indicator:
```python
# Weighted Moving Averages (5 layers)
m1 = WMA(close, 2)
m2 = WMA(m1, 2)
m3 = WMA(m2, 4)
m4 = WMA(m3, 6)
m5 = WMA(m4, 10)

# Hull Moving Average
mavw = HMA(m5, 16)

# Jurik Moving Average
jma = JMA(close, 7, phase=126, power=0.89144)

# Fader Signal
fader = (mavw + jma) / 2
color = GREEN if fader > fader[1] else RED
```

We want: **GREEN** (bullish momentum)

---

## Example: SRRK - January 9, 2026

**Analysis Results:**
```
Close Price:              $42.18
Bollinger Basis (68 EMA): $39.78

✓ Channel:       YES (14 days, 13.1% range, $41.00-$46.38)
✓ EFI Oversold:  YES (ORANGE, -2.37)
✓ Norm Price:    YES (2.40 - price $2.40 above 68 EMA)
✗ Fader:         NO  (RED - bearish momentum)

Status: 3/4 criteria met - NOT a valid setup
```

**Why it's close but not valid:**
- Shows perfect DIVERGENCE (price strong, EFI weak)
- Price holding above 68 EMA despite selling pressure
- BUT Fader is still RED - momentum hasn't confirmed
- **If Fader turns GREEN, this becomes a complete setup!**

---

## Files Modified

### Main Scanner
**UltimateScanner.py**
- ✅ Replaced old normalized price calculation
- ✅ Now uses: `normprice = close - EMA(close, 68)`
- ✅ Integrated TradingView EFI method
- ✅ Added Fader indicator (WMA + HMA + JMA)
- ✅ Removed uptrend requirement
- ✅ Removed "price in lower 35%" requirement
- ✅ Fixed all timezone warnings

### Analysis Tools
**analyze_srrk_tradingview.py**
- Complete analysis tool for individual stocks
- Matches TradingView calculations exactly
- Shows all 4 criteria with pass/fail status

**chart_srrk.py**
- Visual chart generation
- Shows Price, EFI Histogram, Normalized Price, Fader
- Marks target date with red line

---

## Running the Scanner

```bash
cd watchlist_Scanner/ultimate_scanner
python UltimateScanner.py
```

**Output Files:**
1. `ultimate_high_probability_signals.txt` - Detailed analysis
2. `tradingview_ultimate_list.txt` - Comma-separated ticker list

---

## Analyze Individual Stock

```bash
cd watchlist_Scanner/ultimate_scanner

# Edit analyze_srrk_tradingview.py to change:
# - Ticker symbol
# - Target date

python analyze_srrk_tradingview.py
```

---

## Understanding the Strategy

### What We're Looking For

**DIVERGENCE SETUP:**
1. Stock is **consolidating** (coiled spring)
2. EFI shows **selling pressure** (ORANGE/MAROON)
3. But price **holds above 68 EMA** (strength)
4. Fader turns **GREEN** (momentum confirmation)

### Why This Works

This combination catches **accumulation zones**:
- Smart money accumulating (price holds)
- Weak hands selling (EFI oversold)
- Momentum about to shift (Fader turning green)
- Ready to break out of consolidation

### The Divergence Concept

**Classic Divergence:**
- Indicator shows weakness
- Price shows strength
- Disagreement = potential reversal

**Your Setup:**
- EFI (momentum) = weakness (oversold)
- Normalized Price (position vs 68 EMA) = strength (above basis)
- Fader = confirmation (green = go)

---

## Technical Details

### TradingView Indicator Match

Your scanner now **exactly matches** the TradingView indicator:
```
//@version=6
indicator(shorttitle = 'EFI Priceline', title = 'volfurce', overlay = false)

bollperiod = 68
fiperiod = 13
fisf = 13
sens = 11

basis = EMA(close, bollperiod)
normprice = close - basis
```

### Key Parameters
- **Bollinger Period:** 68 (EMA)
- **Force Index Period:** 13 (EMA)
- **Force Index Scale:** 13
- **ATR Sensitivity:** 11
- **Fader Parameters:** Default (2,2,7,126,0.89144)

---

## Current Market Status

As of the latest scan:
- **0 setups found** meeting all 4 criteria
- This is expected - the divergence setup is **rare by design**
- High-probability but low-frequency signal
- When a setup appears, it's significant

---

## Quality Scoring (0-100)

When setups are found, they're scored based on:

1. **Consolidation Duration** (max 25 points)
   - Longer = higher score

2. **Normalized Price Value** (max 25 points)
   - Further above 68 EMA = higher score

3. **EFI Strength** (max 25 points)
   - MAROON (deeply oversold) = 25 points
   - ORANGE (oversold) = 15 points

4. **Volume** (max 25 points)
   - Higher volume = higher score

**Scores 60+** = Very strong setup

---

## Notes

- Scanner is strict - all 4 criteria must pass
- Zero results is normal when market conditions don't align
- The combination ensures only highest-quality setups
- Use proper risk management on all trades
- Not every signal will work - this is probability, not certainty

---

## Version History

**v2.0 - January 25, 2026**
- ✅ Implemented TradingView EFI method
- ✅ Normalized price = Close - 68 EMA
- ✅ Removed uptrend filter
- ✅ Removed position-in-range filter
- ✅ Added full Fader indicator
- ✅ Fixed all warnings

**v1.0 - Previous**
- Used generic normalized price (-1 to +1 range)
- Different calculation method
- Less accurate to TradingView

---

**Last Updated:** 2026-01-25
**Status:** ✅ Production Ready
