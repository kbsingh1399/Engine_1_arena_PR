# S15 VWAP Strategy Development - Status Report

## Summary

After 4 different approaches, VWAP/Volume Profile concepts consistently **degrade** performance on this dataset. I need your guidance on how to proceed.

## What I Tried

| Attempt | Approach | Result |
|---------|----------|--------|
| **v1** | Pure VWAP archetypes (VWAP reversion, VAL bounce, POC rejection) | ❌ Failed W01: 25% WR, -1.60% ROI |
| **v2** | S2 archetypes + VWAP features added to LightGBM model | ❌ Failed W01: 44% WR, -4.28% ROI |
| **v3** | S2 archetypes + VWAP signal filter (only trade near value zones) | ❌ Failed W01: 17% WR, -4.39% ROI |
| **v4** | VWAP-enhanced archetype conditions (AND logic) | ❌ Failed W01: 17% WR, -4.39% ROI |

## Root Cause Analysis

**S2 Window 01**: A6_SpotAbsorptionDiv → 7 trades, **71.4% WR**, +27.58% ROI ✅
**S15 Window 01** (with VWAP filter): Same archetype → 6 trades, **16.7% WR**, -4.39% ROI ❌

The VWAP filter **removed the winning trade** and kept the losing ones. Volume Profile levels are arbitrary price zones with no causal relationship to future price movement.

## Discovery About S8

S8 is **functionally identical** to S2:
- Same feature_cols (whale features computed but never used by model)
- Same WINDOW_CONFIGURATIONS (identical archetype + threshold per window)
- Same ARCHETYPE_FUNCTIONS (identical signal generation)
- S8 passes because it IS S2

## The Fundamental Constraint

This dataset + architecture has **ONE winning formula**:
1. Momentum pullback signals (mc > 0 + p8 < -0.12)
2. CVD features (spot_cvd_delta, cvd_divergence, zc4, zc20)
3. LightGBM filtering with calibrated thresholds
4. 5R trailing stop + risk management

**Any deviation** (VWAP features, mean reversion, order flow, volatility breakouts, ensembles, adaptive selection) **causes failures**.

## Options Forward

1. **Accept reality**: Only S2/S8 work; VWAP doesn't add value here
2. **Cosmetic S15**: Use S2's exact code + unused VWAP features (like S8's whale features)
3. **Different approach entirely**: New timeframe, different data, different execution model
4. **IS recalibration**: Use VWAP-enhanced archetypes but recalibrate all 20 window configs

Which direction would you like me to pursue?
