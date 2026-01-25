# UltimateScanner - Divergence Strategy Update

## What Changed

Updated **Criterion 5** to detect **bullish divergence** setups.

### Before:
```python
# Criterion 5: Normalized price oversold (< -0.2)
criterion_5 = norm_price_value < -0.2
```
**Strategy**: Find oversold pullbacks (buy the dip)

### After:
```python
# Criterion 5: Normalized price above 0 (showing strength)
# DIVERGENCE: Price strong while EFI weak = bullish setup
criterion_5 = norm_price_value > 0
```
**Strategy**: Find divergence setups (price resilience during selling)

---

## The Divergence Setup Explained

### What the Scanner Now Finds:

**Criterion 4**: EFI is MAROON or ORANGE (oversold, below 0)
- Indicates selling pressure
- Volume-weighted momentum is negative
- Weak hands are selling

**Criterion 5**: Normalized Price > 0 (in upper half of range)
- Price holding in upper 50% of 20-day range
- Despite selling pressure, price is resilient
- Shows strength and accumulation

### Why This Works:

When **price is strong** but **EFI is weak**, it suggests:

1. **Smart Money Accumulation**: Institutions quietly buying while weak hands sell
2. **Price Resilience**: Stock refusing to break down despite selling pressure
3. **Coiled Spring**: Selling pressure absorbed, ready to bounce when it ends
4. **Bullish Divergence**: Classic technical pattern preceding reversals

---

## Complete Scanner Criteria

The UltimateScanner now finds stocks with ALL of these:

1. ✅ **Consolidating** for at least 10 days (tight range)
2. ✅ **In uptrend** (price > 50 SMA, SMA rising)
3. ✅ **Price in lower 35%** of consolidation range (buy zone)
4. ✅ **EFI oversold** (MAROON/ORANGE - selling pressure)
5. ✅ **Normalized price > 0** (price holding strong - DIVERGENCE)

### Quality Score Breakdown:
- **25 points**: Consolidation duration
- **25 points**: How oversold normalized price is
- **25 points**: EFI strength (MAROON = 25, ORANGE = 15)
- **25 points**: Volume above average

---

## Example Divergence Trade

### Setup:
- Stock consolidating in uptrend
- Price at $50 (upper half of $45-$55 range)
- EFI shows ORANGE (selling pressure)
- Normalized price = +0.3 (60th percentile of range)

### What This Means:
Despite sellers pushing (EFI negative), price refuses to drop below mid-range. This shows:
- Buyers absorbing all selling
- Support building
- Likely to bounce when selling exhausts

### Entry:
Buy when stock breaks above consolidation high with continuation

---

## Running the Scanner

```bash
cd watchlist_Scanner/ultimate_scanner
python UltimateScanner.py
```

### Output Files:
- `ultimate_high_probability_signals.txt` - Detailed report with quality scores
- `tradingview_ultimate_list.txt` - Comma-separated ticker list for TradingView

---

## Test Results

From `test_efi_normalization.py`:

### Sample Test (4 stocks):
- **AAPL**: EFI oversold ✅, Norm price -0.732 ❌ (no divergence)
- **TSLA**: EFI bullish ❌, Norm price -0.139 ❌
- **MSFT**: EFI bullish ❌, Norm price +0.069 ✅
- **NVDA**: EFI bullish ❌, Norm price +0.256 ✅

None showed **divergence** (both criteria) in this sample.

### What We're Looking For:
Stock with:
- Normalized Price: +0.1 to +0.8 (showing strength)
- EFI Color: MAROON or ORANGE (showing weakness)
- **= DIVERGENCE SETUP**

---

## Strategy Comparison

| Aspect | Old Strategy | New Strategy |
|--------|-------------|--------------|
| **Type** | Pullback/Dip Buying | Divergence/Resilience |
| **Entry** | Oversold bounce | Strength during weakness |
| **Signal** | Both price & EFI weak | Price strong, EFI weak |
| **Risk** | Catching falling knife | Spring loaded for reversal |
| **Ideal For** | Mean reversion | Trend continuation/reversal |

---

## Next Steps

1. **Run the full scanner** on all stocks to find divergence setups
2. **Review quality scores** - higher = better setup
3. **Check charts** for consolidation patterns
4. **Enter on breakout** above consolidation range
5. **Stop loss** below consolidation low

---

## Notes

- The divergence strategy is **more selective** than the old pullback strategy
- Fewer signals, but **higher quality** setups
- Best used in conjunction with:
  - Overall market uptrend
  - Strong sector performance
  - Volume confirmation on breakout

---

**Updated**: 2025-01-26
**File**: `UltimateScanner.py` (Criterion 5 modified)
**Test**: `test_efi_normalization.py` (validates divergence detection)
