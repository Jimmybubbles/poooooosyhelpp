# Ultimate High Probability Scanner

## Overview
This is the most advanced scanner combining all the best insights from your trading research.

## What Makes This "Ultimate"?

### 1. **Dynamic Consolidation Detection**
- NO fixed 3-week timeframe
- Automatically finds consolidations from 10-60 days
- Measures: "How long has it been consolidating?"
- Longer consolidation = more energy = bigger potential move

### 2. **Multi-Confirmation System**
Requires ALL 5 criteria to trigger:
1. **Consolidating** - At least 10 days in tight range
2. **Uptrend** - Price above 50 SMA, SMA rising
3. **Buy Zone** - Price in lower 35% of consolidation range
4. **Oversold Momentum** - EFI MAROON or ORANGE
5. **Deep Pullback** - Normalized price < -0.2

### 3. **Quality Scoring (0-100)**
Each signal gets a quality score based on:
- Consolidation duration (longer = better)
- How oversold (deeper = better)
- EFI strength (MAROON > ORANGE)
- Volume confirmation (above average = better)

## Strategy Logic

**What it finds:**
> Stocks in uptrends that are consolidating and getting oversold - buy the dip at the low end of the range.

**Why it works:**
- Uptrend = directional bias (Fader concept)
- Consolidation = defined risk/reward (Channel concept)
- Oversold = timing entry (EFI concept)
- Buy zone = low-risk entry point
- Quality score = filter for best setups

## Output Example

```
SIGNAL #1 - AAPL - Quality Score: 87/100
--------------------------------------------------------------------------------
  Date:                12/23/2025
  Current Price:       $175.50
  Consolidation:       22 days
  Range:               $172.00 - $178.00 (3.4%)
  Position in Range:   25% (lower third = buy zone)
  Normalized Price:    -0.35 (oversold)
  Force Index:         -8.5 (ORANGE)
  Volume:              1.4x average

  SETUP: AAPL consolidating for 22 days in uptrend,
         now oversold (ORANGE EFI) at low end of range.
         Buy zone entry with 87/100 quality score.
```

## Files

- `UltimateScanner.py` - The main scanner
- `UltimateBacktest.py` - Backtest system (coming next)
- `ultimate_high_probability_signals.txt` - Scan results
- `tradingview_ultimate_list.txt` - TradingView watchlist

## How to Run

```bash
python watchlist_Scanner/ultimate_scanner/UltimateScanner.py
```

## Comparison to Other Scanners

| Scanner | Time Constraint | Criteria | Output |
|---------|----------------|----------|--------|
| Channel Scanner | Fixed 3 weeks | Channel only | Shows consolidation |
| EFI Scanner | None | EFI only | Shows oversold |
| Triple Signal | Fixed 3 weeks | 4 criteria | High probability |
| **Ultimate Scanner** | **Dynamic** | **5 criteria + quality score** | **Best setups** |

## Next Steps

1. Run scanner to find current setups
2. Review quality scores (focus on 70+)
3. Backtest to validate historical performance
4. Paper trade top signals to build confidence

## Philosophy

**"Less is more"**
- Fewer, higher quality signals
- All confirmations must align
- Systematic, repeatable process
- Let the market tell you when it's ready (dynamic timeframes)