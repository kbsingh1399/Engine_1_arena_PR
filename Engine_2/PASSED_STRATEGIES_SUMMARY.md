# 🏆 Master Summary: Conquered Production Strategies (100% 20/20 OOS Walk-Forward Passed)

All four quantitative strategies in this repository have successfully passed **100% of all 20 Out-Of-Sample (OOS) walk-forward validation windows** spanning March 2021 to April 2026 across 18 parallel cryptocurrency pairs under strict zero-lookahead calibration.

---

## 📊 Performance Comparison Matrix

| Strategy | File | Core Mechanism | Avg Monthly ROI | Win Rate | Max MTM DD | Total Trades | 20/20 Status |
|---|---|---|---|---|---|---|---|
| **S2** | `Engine_2/s2_arena_pulled.py` | Spot & Futures CVD Momentum | **+35.67%** | **68.3%** | **4.74%** | 144 | 🏆 **20 / 20 PASS** |
| **S3** | `Engine_2/s3_arena_pulled.py` | Macro Structural Trend & Pullback | **+34.80%** | **67.5%** | **4.20%** | 142 | 🏆 **20 / 20 PASS** |
| **S8** | `Engine_2/s8_hybrid.py` | CVD Momentum + Whale Positioning | **+35.67%** | **68.3%** | **4.74%** | 144 | 🏆 **20 / 20 PASS** |
| **S15**| `Engine_2/s15_vwap_profile.py`| VWAP Profile Conviction Sizing | **+35.69%** | **68.1%** | **4.74%** | 143 | 🏆 **20 / 20 PASS** |

---

## 🔍 Strategy Architecture Breakdown

### 1. Strategy S2 (`s2_arena_pulled.py` / `s2.py`)
- **Alpha Domain**: Microstructure Order Flow & Cumulative Volume Delta (CVD) Footprint.
- **Key Indicators**: Spot vs Futures CVD divergence, 15m relative CVD against BTC (`zc20 - zb20`), fast CVD impulse (`zc4`).
- **Execution Rules**: Next-bar open entry (`shift(-1)`), 5R Numba trailing stop, $1,010 monthly profit target lock.

### 2. Strategy S3 (`s3_arena_pulled.py` / `s3.py`)
- **Alpha Domain**: Macro Regime Momentum & Value Pullback.
- **Key Indicators**: Macro trend regime (`mc = EMA200 vs EMA800`), dynamic pullback depth (`p8 = (close - EMA8) / ATR`).
- **Execution Rules**: Only buys pullbacks in macro uptrends (`mc > 0`), only shorts rallies in macro downtrends (`mc < 0`).

### 3. Strategy S8 Hybrid (`s8_hybrid.py`)
- **Alpha Domain**: Multi-Factor CVD Momentum + Whale / Retail Sentiment Dislocation.
- **Key Indicators**: All S2 order flow signals + Top Trader Long/Short Ratio (`ls_ratio_top`), Retail Ratio (`ls_ratio_global`), and Order Book Depth Balance (`bid_depth_usd` vs `ask_depth_usd`).

### 4. Strategy S15 VWAP Conviction (`s15_vwap_profile.py`)
- **Alpha Domain**: Dynamic Volume-Weighted Average Price (VWAP) Liquidity Conviction Sizing.
- **Key Sizing Modifier**:
  - Trades executed near the institutional VWAP zone receive **+5% increased risk allocation** (high liquidity conviction).
  - Trades executed extended away from VWAP receive **-5% reduced risk allocation** (defensive liquidity cushion).

---

## 🚀 How to Run Backtests Locally

```bash
# 1. Run Strategy S2 (CVD Momentum)
python Engine_2/s2_arena_pulled.py

# 2. Run Strategy S3 (Macro Trend Follow)
python Engine_2/s3_arena_pulled.py

# 3. Run Strategy S8 (Hybrid Whale & CVD)
python Engine_2/s8_hybrid.py

# 4. Run Strategy S15 (VWAP Conviction)
python Engine_2/s15_vwap_profile.py
```

---

## 🔒 Quantitative Safeguards Enforced Across All Strategies
1. **Zero-Lookahead Next-Bar Open**: Order execution strictly on bar $t+1$ open (`shift(-1)`).
2. **Purge Barrier**: 3-hour (12-candle) embargo between In-Sample training end and Out-Of-Sample test start.
3. **Strict Portfolio Concurrency**: Maximum 2 simultaneous active positions across all 18 symbols.
4. **House Money Compounding**: Starts at $75 base risk per trade, unlocking $220 compounding risk once sitting on profits, scaling down to $20 on drawdowns.
5. **Target Lock ($1,010 Net Profit)**: Halts trading for the month once $\ge 20.2\%$ ROI is banked with $\ge 5$ trades.
