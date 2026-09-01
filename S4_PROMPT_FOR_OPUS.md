# S4 Strategy Challenge: 20/20 Walk-Forward Windows

## Repository
**GitHub**: https://github.com/kbsingh1399/Engine_1_arena_PR  
**Branch**: `arena/01a04c57-engine-1-arena-pr`  
**Current Commit**: `730c68c`

---

## Objective

Achieve **20/20 sequential out-of-sample walk-forward windows** passing ALL criteria for Strategy S4 (RSI Extreme Mean Reversion):

### Mandatory Pass Criteria (ALL must be met):
1. **Win Rate ≥ 40%**
2. **Monthly ROI ≥ 20%**
3. **Max MTM Drawdown ≤ 5%**
4. **Minimum 5 trades per month**
5. **Maximum 2 concurrent positions**

### Walk-Forward Windows (20 total):
```
W01: 2021-03-15 to 2021-04-15
W02: 2021-06-15 to 2021-07-15
W03: 2021-09-15 to 2021-10-15
W04: 2021-12-15 to 2022-01-15
W05: 2022-03-15 to 2022-04-15
W06: 2022-06-15 to 2022-07-15
W07: 2022-09-15 to 2022-10-15
W08: 2022-12-15 to 2023-01-15
W09: 2023-03-15 to 2023-04-15
W10: 2023-06-15 to 2023-07-15
W11: 2023-09-15 to 2023-10-15
W12: 2023-12-15 to 2024-01-15
W13: 2024-03-15 to 2024-04-15
W14: 2024-06-15 to 2024-07-15
W15: 2024-09-15 to 2024-10-15
W16: 2024-12-15 to 2025-01-15
W17: 2025-03-15 to 2025-04-15
W18: 2025-06-15 to 2025-07-15
W19: 2025-10-15 to 2025-11-15
W20: 2026-03-15 to 2026-04-15
```

---

## Current State: Maximum 2/20 Achieved

After **70+ unique configurations** tested, the best result is **2 windows passing simultaneously** (W13 + W14 with Logistic Regression).

**No single configuration passes more than 2 windows.**

### Best Individual Window Results:
- **W01**: 23 trades, 47.8% WR, 25.6% ROI (LGBM md=4,ne=80)
- **W07**: 9 trades, 77.8% WR, 38.3% ROI (LGBM md=3,ne=60)
- **W11**: 6 trades, 83.3% WR, 32.3% ROI (LGBM lr=0.05)
- **W13**: 5 trades, 60.0% WR, 27.3% ROI (LogisticRegression)
- **W14**: 9 trades, 55.6% WR, 31.8% ROI (LogisticRegression)

---

## Technical Architecture

### Core Components:
1. **Signal Generation**: RSI-based entry signals with multiple archetypes
2. **Trade Simulation**: Numba-optimized backtester with trailing stops
3. **ML Model**: Predicts trade quality (probability of winning)
4. **Position Sizing**: Risk-based with drawdown limits
5. **Walk-Forward Validation**: Sequential IS→OOS with 12-bar purge

### Key Files:
- `Engine_2/s4.py` - Current implementation (comprehensive scan version)
- `Engine_2/results_s4/s4_full_scan.json` - All test results
- `Engine_2/s2.py` / `Engine_2/s3.py` - Reference implementations (if they exist)

### Data Structure:
- 18 cryptocurrency pairs (BTC, ETH, SOL, etc.)
- 15-minute bars from 2020-2026
- Features: RSI, CVD, liquidation z-scores, funding rate, price position, trend

---

## Approaches Already Attempted (DO NOT REPEAT)

### 1. Stop Loss Width Variations
- **2.0 ATR**: Base WR=28%, more trades (25+), lower WR
- **2.5 ATR**: Base WR=39%, fewer trades (5-13), moderate WR
- **3.0 ATR**: Base WR=39%, very few trades (3-7), position sizing issues

**Result**: Wider stops increase base WR but reduce trade frequency and ROI.

### 2. Archetype Variations (9 tested)
- **A1**: RSI<35 & p8<-0.50 (strict)
- **A3**: RSI<40 & p8<-0.35 & CVD>0 (with CVD filter)
- **A7**: RSI<42 & p8<-0.25 (loose, most signals)
- **ABull**: Adds trend filter (mc==1)
- **ALiq**: Adds liquidation z-score > 1.5
- **AMom**: Momentum exhaustion based
- **AExt**: Extreme quality (RSI<28, p8<-0.80)
- **AQual**: High quality (RSI<32, p8<-0.60)
- **ARange**: Range-bound (p200<-2.0)

**Result**: Looser archetypes (A7) generate more trades but lower base WR. Tighter archetypes have fewer signals.

### 3. ML Model Types
- **LightGBM**: Gradient boosting (md=3-5, ne=60-150, lr=0.02-0.05)
- **Random Forest**: Ensemble of trees (50-100 trees)
- **Logistic Regression**: Linear model (most robust, least overfitting)

**Result**: All models struggle to generalize from IS to OOS. LR slightly better (2/20).

### 4. Model Training Strategies
- **Per-Window IS**: Train on 15-18 months before each window → overfits to local regime
- **Global Model**: Train on ALL data before W01 (only 4,337 samples) → underfits
- **Model-Free Heuristic**: Rule-based scoring (RSI extremity + CVD + liquidation) → lacks discrimination

**Result**: Per-window overfits, global underfits, heuristic too uniform.

### 5. Label Definitions
- **r_mult > 0**: Any positive R = winner (28% base WR)
- **r_mult > 0.5**: At least 0.5R winner (17.8% base WR, too few positives)
- **Rank-Based**: Top 30% by R-multiple (adapts to regime but still fails)

**Result**: Lower threshold = more positives but lower WR. Higher threshold = too few samples.

### 6. Validation Methods
- **Cross-Validation**: Split IS into 60/20/20, require all to pass → too strict, rejects good combos
- **No Validation**: Pure IS optimization → overfits badly
- **Unified Ensemble**: Combine all archetypes → deduplicates too aggressively

**Result**: CV too strict, no validation overfits, ensemble reduces trade count.

### 7. Risk Parameters
- **Conservative**: br=80-100, hr=220-300, DDL=0.045 → insufficient ROI (4-10%)
- **Moderate**: br=110-130, hr=300-400, DDL=0.060 → ROI 10-15%, DD 4-6%
- **Aggressive**: br=200-270, hr=450-600, DDL=0.12 → ROI 20-77%, but DD 6-12% (fails)

**Result**: Cannot achieve both 20%+ ROI AND <5% DD simultaneously.

### 8. Trailing Stop Strategies
- **Standard**: 5R trail, lock at 2.5R → good R:R but 28% base WR
- **Defensive**: Breakeven at 0.5R, lock at 1R → increases base WR to 35% but kills R:R
- **Wide (3ATR)**: More time to work → fewer trades, position sizing issues

**Result**: Defensive stops boost WR but destroy R:R, net negative for ROI.

### 9. Scoring Functions
- **ROI-Based**: Maximize IS ROI → overfits to high-risk combos
- **DD-Penalized**: `ROI * (1 + WR) * (0.05 - DD) / 0.05` → still overfits
- **Trade-Count Weighted**: `ROI * log(trades) * WR` → favors quantity over quality
- **Composite**: Multiple factors weighted by IS performance → no improvement

**Result**: All scoring functions overfit IS, fail OOS.

---

## Fundamental Challenges Identified

### 1. Regime Dependence
Mean reversion works in **~30% of market conditions**:
- ✅ Trending markets with pullbacks (W01, W07, W13-W14)
- ❌ Post-crash choppy (W02, W08-W09)
- ❌ Strong bear trends (W05-W06)
- ❌ Extreme volatility (W15-W16)

The 20 windows span 5 years covering ALL regimes. No single configuration handles all.

### 2. IS→OOS Generalization Gap
Models trained on IS patterns fail when market regime shifts:
- IS WR: 40-60% (model "works")
- OOS WR: 0-30% (model fails)

The model learns IS-specific patterns that don't transfer.

### 3. The Impossible Triangle
Cannot simultaneously achieve:
- **20%+ ROI** → needs aggressive risk (br=200+, hr=500+)
- **<5% DD** → needs conservative risk (br=80-100, hr=220-300)
- **40%+ WR** → needs reliable signal (base WR=28-39%, model adds 10-15%)

These requirements are mutually exclusive with current strategy.

### 4. Base Win Rate Too Low
- Current base WR: 28-39%
- Required OOS WR: 40%+
- Model lift: 10-15% (inconsistent across regimes)
- Gap: 28% + 15% = 43% (only in favorable regimes)

---

## Constraints (Must Respect)

1. **No Lookahead Bias**: Only `next_open = df['open'].shift(-1)` allowed as forward reference
2. **No Centered Windows**: Only backward-looking features, no `.bfill()`, only `.ffill().fillna(0)`
3. **IS/OOS Purge**: 12-bar (3-hour) gap between IS end and OOS start
4. **Fixed Threshold**: Probability threshold calibrated on IS only, applied blind to OOS
5. **No OOS Re-optimization**: Cannot loop over OOS windows to re-select archetypes
6. **Clone S2/S3 Architecture**: Same pbt() function, same position sizing logic
7. **Same 20 Windows**: Must use exact windows listed above

---

## What Has NOT Been Tried (Potential Avenues)

### 1. Regime Detection + Adaptive Strategy
- Detect market regime (bull/bear/choppy) using BTC trend, volatility, correlation
- Switch between mean reversion (bull) and trend-following (bear)
- Use different archetypes per regime

### 2. Ensemble of Multiple Models
- Train 5-10 models on different feature subsets
- Average predictions to reduce variance
- Use model disagreement as uncertainty measure

### 3. Meta-Learning / Transfer Learning
- Train on multiple time periods
- Learn which features predict model success
- Use meta-model to select best archetype/threshold per window

### 4. Reinforcement Learning
- Agent learns optimal (archetype, threshold, risk) policy
- Reward = pass all criteria
- Train on historical data, test on walk-forward

### 5. Alternative Entry Signals
- Volatility breakout (Bollinger Bands, ATR channels)
- Momentum reversal (price momentum + RSI divergence)
- Liquidation cascades (high liq z-score + funding rate flip)

### 6. Dynamic Position Sizing
- Kelly criterion based on model confidence
- Reduce size in unfavorable regimes
- Increase size when multiple signals align

### 7. Multi-Timeframe Confirmation
- Require 15m signal AND 1h trend alignment
- Filter out counter-trend trades
- Use higher timeframe for regime detection

### 8. Feature Engineering
- Interaction features (RSI * CVD, liq * funding)
- Non-linear transforms (RSI^2, log(volume))
- Rolling correlations (RSI vs price, CVD vs volume)

### 9. Alternative ML Architectures
- Neural networks (LSTM for time series)
- XGBoost with custom objectives
- Bayesian optimization for hyperparameters

### 10. Relax Constraints (if allowed)
- Allow 15/20 windows instead of 20/20
- Reduce ROI requirement to 15% or DD to 7%
- Allow regime-specific model selection

---

## Your Mission

**Continue from commit `730c68c` and achieve 20/20 windows passing.**

### Approach Suggestions:
1. **Try regime-adaptive strategy** (detect regime, switch approach)
2. **Implement ensemble models** (reduce variance, improve generalization)
3. **Explore alternative entry signals** (not just RSI mean reversion)
4. **Add multi-timeframe confirmation** (filter counter-trend trades)
5. **Use meta-learning** (learn which config works in which regime)

### Success Criteria:
- ALL 20 windows pass sequentially
- Single configuration (no per-window re-optimization beyond threshold/risk)
- Code is clean, documented, and reproducible
- Results saved to `Engine_2/results_s4/`

### Deliverables:
1. Working `Engine_2/s4.py` that achieves 20/20
2. `Engine_2/results_s4/winning_configuration.json` with all window results
3. Brief report explaining what worked and why
4. Git commits showing progression

---

## Key Insights from Failed Attempts

1. **Base WR of 28-39% is too low** — need strategy with 45%+ base WR
2. **Per-window models overfit** — need global or ensemble approach
3. **Risk and DD are coupled** — cannot optimize independently
4. **Regime matters more than features** — detect regime first, then apply strategy
5. **Simpler models generalize better** — LR > RF > LGBM for OOS performance

---

## Data Location

- **Parquet files**: `Engine_2/binance_backtesting_data/*_15m_master_*.parquet`
- **Symbols**: BTCUSDT, ETHUSDT, SOLUSDT, and 15 others
- **Time range**: 2020-01-01 to 2026-04-30
- **Features per symbol**: ~50 columns (OHLCV, RSI, CVD, liquidation, funding, etc.)

---

## Final Note

This is a **hard problem**. The 20/20 target may be impossible with pure RSI mean reversion. Consider:
- Hybrid strategies (mean reversion + trend following)
- Regime-adaptive approaches
- Alternative entry signals beyond RSI
- Relaxing constraints if 20/20 is truly unachievable

**Do not give up until you've exhausted all creative approaches.** The goal is to find ANY configuration that passes 20/20, even if it requires rethinking the strategy entirely.

Good luck! 🚀
