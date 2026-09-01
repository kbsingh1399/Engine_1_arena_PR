# Strategy Audit & Optimization Plan

## Current Status (as of 2026-09-01)

### ✅ Already Passing 20/20
- **S2** (s2.py): CVD Momentum - 20/20, avg ROI +35.67%
- **S8** (s8_hybrid.py): Hybrid Whale - 20/20, avg ROI +35.67%
- **S15** (s15_vwap_profile.py): VWAP Conviction - 20/20, avg ROI +35.69%

### ❌ Need Optimization
- **S1** (s1.py): Liquidation Cascade - 0/20
- **S4** (s4.py): CVD Divergence Squeeze - 1/20
- **S6** (s6.py): Volatility Compression - 0/20
- **S7** (s7_amt.py): Delta Climax Mean Reversion - 0/20

### ⚠️ Not Found
- **S3**: Macro Trend Following (file doesn't exist)
- **S5**: Liquidity Sweep Reversal (file doesn't exist)

## Enhanced Parameters (from user spec)

### 1. 5R Asymmetric Runner
```python
stop_dist = max(2.0 * ATR14, entry_price * 0.0065)
# Ratchets:
# +1.2R gain → lock +0.2R (risk-free)
# +2.4R gain → lock +1.5R
# +3.8R gain → lock +2.8R
# +5.5R gain → full exit
```

### 2. House-Money Governor
```python
base_risk = $55 (1.10% of $5,000)
win_streak_bonus = +$55 per consecutive win (max $260)
house_money = min($55 + 0.85*realized_pnl + streak_bonus, $260)
defense = any loss → reset to base or damped risk (≥$15)
dd_ceiling = 4.2% hard clamp
```

### 3. Causal Intra-Bar Simulation
- Check low before high (adverse moves first)
- 5 bps adverse slippage on stops
- True ATR with gap terms: max(high-low, |close-prev_close|)

### 4. Signal Selection
- Top 5-6 trades per window
- P ≥ 0.50 threshold
- 18-month IS training, 3-hour purge

## Optimization Strategy

### Phase 1: Create Enhanced Framework
- Build unified simulator with new parameters
- Implement house-money governor
- Add causal intra-bar logic

### Phase 2: Apply to Each Strategy
- S1: Liquidation signals + enhanced execution
- S4: CVD divergence + enhanced execution
- S6: Vol compression + enhanced execution
- S7: Delta climax + enhanced execution

### Phase 3: Iterate on Failures
- Analyze which windows fail
- Adjust archetypes/thresholds
- Re-run until 20/20 or document limitations

## Realistic Expectations

Based on session history:
- Only momentum/breakout strategies (S2/S8/S15) have achieved 20/20
- Mean reversion (S7, S9) consistently fails
- Order flow (S14) fails
- Volatility compression (S6, S10) fails

The enhanced parameters may help, but fundamental signal quality is paramount.
