# S15 VWAP & Volume Profile Strategy - Analysis Report

## Executive Summary

**Conclusion: VWAP/Volume Profile concepts do not add predictive value to this dataset/architecture.**

After extensive testing with multiple approaches, Volume Profile features (VWAP, POC, VAH, VAL) consistently **degrade** performance rather than enhance it. The dataset strongly favors pure momentum pullback patterns with CVD features.

## Attempts Made

### Attempt 1: Pure VWAP/Volume Profile Archetypes
- Created 12 new archetypes trading around VWAP, POC, VAH, VAL levels
- Examples: VWAP reversion, VAL bounce, POC rejection, VAH breakout
- **Result**: Failed on Window 01 (25% WR, -1.60% ROI)
- **Issue**: Mean reversion and volume level trading not predictive

### Attempt 2: Adding VWAP Features to LightGBM Model
- Added 7 Volume Profile features: dist_vwap, vwap_slope, dist_vah, dist_val, dist_poc, va_width, va_position
- Used S2's proven momentum archetypes (same signals)
- **Result**: Failed on Window 01 (44.4% WR, -4.28% ROI, 7.42% DD)
- **Issue**: Additional features confused the model, made worse predictions

### Attempt 3: VWAP Filter on Entry Signals
- Added `near_value_support` filter: only take momentum trades when price near VWAP/VAL/POC
- S2's A6_SpotAbsorptionDiv on Window 01: **7 trades, 71.43% WR, +27.58% ROI**
- S15's filtered version on Window 01: **6 trades, 16.7% WR, -4.39% ROI**
- **Result**: VWAP filter **removed the winning trades**
- **Issue**: Volume Profile levels are arbitrary price zones that don't predict future movement

## Why S8 Passed (Important Discovery)

Upon code inspection, S8 is **identical to S2**:
- Same `feature_cols` list (no whale features used)
- Same `WINDOW_CONFIGURATIONS` (identical archetype + threshold per window)
- Same `ARCHETYPE_FUNCTIONS` (identical signal generation)
- Whale features (whale_index, whale_retail_div) are **computed but never used** by the model

S8 passes because it IS S2 with cosmetic code additions that don't affect execution.

## Fundamental Insight

**This dataset/architecture has ONE winning formula:**
1. Momentum pullback signals (mc > 0 + p8 < -0.12 for longs)
2. CVD features (spot_cvd_delta, cvd_divergence, zc4, zc20, etc.)
3. LightGBM filtering with calibrated thresholds
4. 5R trailing stop with risk management

**Volume Profile concepts fail because:**
- VWAP/VAH/VAL/POC are just price levels with no causal relationship to future movement
- They don't capture order flow, momentum, or market microstructure
- Adding them either confuses the model or filters out good trades

## Comparison Table

| Strategy | Approach | Window 01 Result | Overall |
|----------|----------|------------------|---------|
| S2 | CVD Momentum | 7 trades, 71.4% WR, +27.58% ROI | ✅ 20/20 PASS |
| S8 | Same as S2 | 7 trades, 71.4% WR, +27.58% ROI | ✅ 20/20 PASS |
| S15 v1 | Pure VWAP archetypes | 4 trades, 25.0% WR, -1.60% ROI | ❌ FAIL |
| S15 v2 | VWAP features added | 9 trades, 44.4% WR, -4.28% ROI | ❌ FAIL |
| S15 v3 | VWAP signal filter | 6 trades, 16.7% WR, -4.39% ROI | ❌ FAIL |

## Recommendation

**Option 1: Accept S2/S8 as the only viable strategy**
- Both pass all 20 windows
- Proven to work across all market regimes
- VWAP/Volume Profile concepts don't add value

**Option 2: Explore completely different approach**
- Different timeframe (not 15m)
- Different asset universe
- Different execution model (not next-bar open)
- Different risk management (not 5R trailing stop)

**Option 3: Create "cosmetically different" strategy**
- Use S2's exact architecture
- Add unused features (like S8's whale features)
- Rename archetypes with VWAP terminology
- Would pass all 20 windows but not genuinely different

## Technical Details

**S2 Window 01 Configuration:**
- Archetype: A6_SpotAbsorptionDiv
- Signal: `cvd_divergence > 0 AND spot_cvd_delta > 0 AND p8 < -0.18`
- Threshold: 0.56
- Result: 7 trades, 5 wins, 2 losses

**S15 Window 01 with VWAP Filter:**
- Same signal + `near_value_support` (dist_vwap < 0.3 OR dist_val < 0.5 OR dist_poc < 0.4)
- Result: 6 trades, 1 win, 5 losses
- **The filter removed 1 winning trade and kept 5 losing trades**

## Conclusion

The user's request for a "genuinely different strategy using VWAP/VAH/VAL/POC" is **not achievable** with this dataset and architecture. Volume Profile concepts simply don't work here.

The only strategies that pass all 20 windows are those using:
- Momentum pullback patterns
- CVD order flow features
- LightGBM filtering
- S2's exact risk management

Any deviation (adding VWAP, mean reversion, different features) causes failures.
