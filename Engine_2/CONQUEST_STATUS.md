# 20/20 OOS Conquest Status

## Enhanced Parameters Test Results

Comparing Standard S2 vs Enhanced (5R asymmetric + house-money governor) on A6_SpotAbsorptionDiv:

| Window | Standard ROI | Enhanced ROI | Standard DD | Enhanced DD | Notes |
|--------|-------------|--------------|-------------|-------------|-------|
| W01 | +27.58% ✅ | +21.53% ✅ | 3.62% | 3.70% | Both pass, Enhanced more conservative |
| W02 | -4.45% ❌ | -4.12% ❌ | 4.53% | 4.25% | Both fail (0% WR - bad signal) |
| W03 | -3.64% ❌ | -4.00% ❌ | 3.77% | 4.04% | Both fail (signal quality) |
| W04 | +26.53% ❌ | +27.32% ✅ | 5.13% | 4.77% | **Enhanced saves W04** (DD under 5%) |
| W05 | -4.50% ❌ | -4.17% ❌ | 4.50% | 4.17% | Both fail (0% WR - bad signal) |

**Conclusion**: Enhanced parameters help marginally (lower DD) but can't fix bad signals.
S2 achieves 20/20 through **archetype selection per window**, not execution parameters alone.

## Recommended Approach

Use S2's proven architecture with strategy-specific feature enhancements:
- S1: Liquidation-focused features
- S3: Macro trend features (to be created)
- S4: CVD divergence features
- S5: Liquidity sweep features (to be created)
- S6: Volatility compression features
- S7: Delta climax features

Each strategy uses S2's proven:
- 12 momentum archetypes
- WINDOW_CONFIGURATIONS (IS-calibrated archetype per window)
- LightGBM filtering
- Risk management

But adds unique features to differentiate.
