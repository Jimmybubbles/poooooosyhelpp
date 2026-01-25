# Ultimate Scanner - Channel + EFI Divergence + Fader Setup

## Strategy Overview

The Ultimate Scanner finds high-probability trading setups by combining three powerful technical indicators:

1. **Channel (Consolidation)**
   - Stock must be consolidating for at least 10 days
   - Consolidation range must be tight (< 15%)
   - At least 70% of bars must touch the channel boundaries

2. **EFI Divergence**
   - **EFI Histogram**: MAROON or ORANGE (below 0 - showing selling pressure)
   - **Normalized Price Line**: Above 0 (price in upper half of 20-day range)
   - **DIVERGENCE**: Price showing strength while EFI shows weakness = bullish setup

3. **Fader Signal**
   - Fader must be GREEN (bullish momentum confirmed)
   - Fader combines weighted moving averages and Jurik Moving Average
   - Green = upward momentum, Red = downward momentum

## What This Finds

This scanner looks for **accumulation zones** where:
- Price is consolidating in a tight channel (coiling spring)
- Selling pressure exists (EFI oversold) BUT price refuses to break down (norm > 0)
- Momentum is turning bullish (Fader green)

This combination suggests smart money is accumulating while weak hands sell, setting up for a potential breakout.

## Criteria Breakdown

### Criterion 1: Channel Consolidation (10+ days)
```python
# Dynamic consolidation detection
- Scans 10-60 day windows
- Range must be < 15% (tight consolidation)
- 70%+ bars must touch channel boundaries
- Minimum 10 days consolidation required
```

### Criterion 2: EFI Oversold
```python
# Elder Force Index color coding
MAROON: fi_value < -2.0 * std  # Strongly oversold
ORANGE: fi_value < 0            # Oversold
LIME:   fi_value > 0            # Bullish
GREEN:  fi_value > 2.0 * std    # Strongly bullish

# We want MAROON or ORANGE (selling pressure)
```

### Criterion 3: Normalized Price > 0 (DIVERGENCE)
```python
# Normalized price calculation
highest_20d = High.rolling(20).max()
lowest_20d = Low.rolling(20).min()
norm_price = 2 * ((Close - lowest) / (highest - lowest)) - 1

# Range: -1 to +1
# -1 = at bottom of 20-day range
#  0 = at middle
# +1 = at top of 20-day range

# We want norm_price > 0 (upper half = strength)
# Combined with EFI < 0 = DIVERGENCE
```

### Criterion 4: Fader Signal GREEN
```python
# Fader calculation (simplified)
# Step 1: Multiple WMA smoothing
m1 = WMA(Close, 2)
m2 = WMA(m1, 2)
m3 = WMA(m2, 4)
m4 = WMA(m3, 6)
m5 = WMA(m4, 10)

# Step 2: HMA of final WMA
mavw = HMA(m5, 16)

# Step 3: JMA smoothing
jma = JMA(Close, length=7, phase=126, power=0.89144)

# Step 4: Combine
fader_signal = (mavw + jma) / 2
fader_color = 'green' if signal > prev_signal else 'red'

# We want fader_color == 'green' (bullish)
```

## Quality Scoring (0-100)

The scanner scores each setup based on:

1. **Consolidation Duration** (max 25 points)
   - Longer consolidation = more points
   - Formula: min(25, days / 2)

2. **Oversold Level** (max 25 points)
   - More oversold = more points
   - Formula: min(25, abs(norm_price) * 25)

3. **EFI Strength** (max 25 points)
   - MAROON: 25 points (strongly oversold)
   - ORANGE: 15 points (oversold)

4. **Volume** (max 25 points)
   - Higher volume = more points
   - Formula: min(25, (volume_ratio - 1.0) * 50)

## Running the Scanner

```bash
cd watchlist_Scanner/ultimate_scanner
python UltimateScanner.py
```

## Output Files

1. **ultimate_high_probability_signals.txt**
   - Detailed report with all setups
   - Sorted by quality score (highest first)
   - Includes full analysis for each signal

2. **tradingview_ultimate_list.txt**
   - Comma-separated ticker list
   - Ready to paste into TradingView watchlist

## Example Output

```
Ticker   Score   Days   Range    Pos%   Norm    EFI      Fader   Vol
----------------------------------------------------------------------
KBH      53      10     8.2%     30%    0.09    ORANGE   GREEN   2.7x

SIGNAL #1 - KBH - Quality Score: 53/100
----------------------------------------------------------------------
  Date:                12/18/2025
  Current Price:       $62.75
  Consolidation:       10 days
  Range:               $61.23 - $66.27 (8.2%)
  Position in Range:   30% (lower third = buy zone)
  Normalized Price:    0.09 (DIVERGENCE)
  Force Index:         -169790.69 (ORANGE)
  Fader Signal:        GREEN
  Volume:              2.7x average

  SETUP: KBH consolidating for 10 days,
         DIVERGENCE: EFI oversold (ORANGE) but norm price > 0,
         Fader GREEN confirming bullish momentum.
         Quality score: 53/100
```

## Technical Implementation

### Files Modified
- `UltimateScanner.py` - Main scanner with all 4 criteria
- Removed uptrend requirement (was too restrictive)
- Changed normalized price from > -0.5 to > 0 (true divergence)
- Added Fader indicator (talib-based WMA + HMA + JMA)

### Dependencies
```python
pandas
numpy
talib  # For WMA and technical indicators
```

### Key Functions
- `calculate_elder_force_index()` - EFI with color coding
- `calculate_normalized_price()` - Position in 20-day range
- `find_consolidation_range()` - Dynamic channel detection
- `calculate_fader_signal()` - Fader momentum indicator
- `hma()` - Hull Moving Average
- `jma()` - Jurik Moving Average

## Interpretation

### Bullish Setup
When all 4 criteria are met:
1. Stock has been consolidating (building energy)
2. EFI shows selling pressure (weak hands selling)
3. Price refuses to break down (norm > 0 = accumulation)
4. Fader turns green (momentum shifting bullish)

**Action**: Consider entry in the consolidation range, expecting breakout

### Why This Works
- **Consolidation** = coiled spring ready to release
- **EFI oversold** = selling exhaustion
- **Norm price > 0** = price holding despite selling = strength
- **Fader green** = momentum confirmation

This combination catches stocks transitioning from accumulation to markup phase.

## Notes

- This is a **strict filter** - few stocks will pass all 4 criteria simultaneously
- The divergence between EFI and normalized price is rare but powerful
- Higher quality scores (60+) indicate stronger setups
- Volume confirmation adds conviction
- Not all signals will work - use proper risk management

## Historical Context

The scanner combines concepts from:
- **Dr. Alexander Elder** - Force Index indicator
- **Channel Trading** - Consolidation breakouts
- **Fader System** - Multi-timeframe momentum
- **Divergence Trading** - Price vs. momentum disagreement

Built: January 2026
Last Updated: 2026-01-25
