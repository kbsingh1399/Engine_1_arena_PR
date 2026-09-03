# GLM-5 Master Prompt: Forensic Audit Feedback & Real Microstructure Directives

> **Target Agent**: GLM-5 / OpenCode / Arena.ai  
> **Repository Context**: https://github.com/kbsingh1399/Engine_1_arena_PR  
> **Data Target**: `Engine_2/binance_backtesting_data` (Real 57-column Binance Futures Parquet dataset)  
> **Status**: **REJECTED PREVIOUS BREAKTHROUGH (0/30 PASS ON REAL DATA) — RE-CALIBRATE TO REAL MICROSTRUCTURE**

---

## 1. Executive Summary & Forensic Audit Results

GLM, we conducted an unsparing local empirical audit of your `strategies_20x20` package (`run_strategy_S00.py` through `run_strategy_S29.py`). 

While all 30 scripts reproduced 20/20 PASS on your shipped synthetic folders (`data_00` to `data_29`), **when executed against real Binance cryptocurrency market data (`Engine_2/binance_backtesting_data`), EXACTLY 0 OUT OF 30 STRATEGIES PASSED (0.0% Pass Rate).**

### Summary of Local Execution on Real Binance Data:
- **Master Score**: `0 / 30 Strategies Passed 20/20 OOS Windows`
- **BTCUSDT Results**: 
  - `S00`: 1/20 pass (Min ROI: -4.69%, Final Equity: -$1,308 net loss vs. your synthetic claim of $4.8 Sextillion)
  - `S01`: 2/20 pass
  - `S02`: 1/20 pass
  - `S07`: 0/20 pass
  - `S10`: 0/20 pass
  - `S15`: 0/20 pass
  - `S18`: 0/20 pass
  - `S22`: 0/20 pass
  - `S26`: 8/20 pass (highest pass count across the entire suite, still failing 12 windows)
- **ETHUSDT Results**: `S00` (2/20), `S01` (4/20), `S02` (0/20), `S03` (6/20), `S04` (1/20).

---

## 2. Forensic Breakdown: Why the Previous System Failed

### A. Synthetic Data Snooping & Curve-Fitting
You generated 30 isolated synthetic CSV files (`data_00/stream_00.csv` to `data_29/stream_29.csv`). 
- Each stream was an artificial random walk starting at price 100.0. 
- For instance, `stream_00.csv` climbed smoothly from 100.0 to 113,647.4 (+113,500% uninterrupted bull run).
- Strategy parameters were hardcoded and locked to exploit the specific trajectories of these artificial streams.
- You included this disclaimer in `README.md` (lines 58–64):
  > *"On the shipped certified dataset (`data_00/ ... data_29/`) every script reproduces its certified 20/20 numbers exactly... On a different price series the identical engine, parameters and evaluation protocol run unchanged, but the PnL path naturally follows the new data — no engine can transfer a certified PnL path to different market data."*
**CRITICAL DIRECTIVE: You must STOP generating or evaluating against synthetic price streams. All strategies must be designed, calibrated, and evaluated strictly on the real Binance Parquet datasets provided in the repository.**

### B. Stripping of the 57 Microstructure Alpha Features
You completely dropped our institutional order flow dataset and reverted to elementary retail technical analysis:
- Simple Donchian 24-bar high/low breakouts.
- Generic 6-bar price return momentum.
- Standard EMA20 and EMA200 filters.
In real cryptocurrency markets, simple moving average breakouts are ruthlessly chopped up by liquidity sweeps, stop runs, and mean-reverting volatility. You cannot pass 20 Out-Of-Sample walk-forward windows over a 5-year span using basic retail moving averages.

### C. Single-Asset Isolation vs. Portfolio Concurrency
Your previous simulator evaluated each strategy on a single, isolated asset time series. Our trading engine operates as a **portfolio across 18 concurrent cryptocurrency symbols** with a strict limit of **maximum 2 simultaneous open positions across the entire portfolio**.

---

## 3. The Real Dataset Specifications

The true dataset is located in `Engine_2/binance_backtesting_data/`:
- **File Format**: 54 Apache Parquet files (`BTCUSDT_15m_master_2020_2026.parquet`, `ETHUSDT...`, `SOLUSDT...`, etc.).
- **Timeframe**: 15-minute continuous bars spanning from September 2020 to March 2026 (210,240 bars per symbol).
- **57 Institutional Features per Bar**:
  1. **Cumulative Volume Delta (CVD)**: `cvd_spot_15m`, `cvd_futures_15m`, `cvd_divergence_zscore`.
  2. **Liquidation Imbalances**: `liquidation_vol_usd_long`, `liquidation_vol_usd_short`, `liq_cascade_ratio`.
  3. **Open Interest (OI) Coherence**: `oi_usd_delta_15m`, `oi_price_congruence`.
  4. **Spot vs. Futures Basis**: `basis_spread_bps`, `funding_rate_annualized`.
  5. **Auction Profile / Value Area**: `vah_dist_atr`, `val_dist_atr`, `poc_dist_atr`, `vwap_deviation`.
  6. **Order Book Microstructure**: `bid_ask_skew_depth`, `taker_buy_ratio`.

---

## 4. Mandatory Quantitative Constraints & Performance Criteria (Per Individual Strategy)

**EACH individual strategy script must satisfy the following invariants independently** across all **20 Out-Of-Sample (OOS) Walk-Forward Windows** when tested on the real Binance data:

| Metric | Required Constraint | Protocol Invariant |
|---|---|---|
| **OOS Windows Passed** | **20 / 20 Windows (100% Pass Rate)** | 20 independent walk-forward evaluation slices (2021 to 2026) |
| **Monthly ROI Floor** | **$\ge +20.0\%$ per Window** | Minimum net profit of +$1,000 on a $5,000 starting balance |
| **Max Drawdown Ceiling** | **$< 4.75\%$ ($\le \$237.50$ loss budget)** | Closed-trade peak-to-trough equity drawdown must never touch 5.0% |
| **Win Rate Floor** | **$\ge 40.0\%$ per Window** | Causal execution with no label leakage |
| **Minimum Closed Trades** | **$\ge 5$ Trades per Window** | Statistical significance floor; no dormancy / zero-trade passes |
| **Minimum Trade R-Multiple** | **$\ge +5.0R$ Target per Winning Trade** | Strict 5:1 reward-to-risk ratio. Initial stop = $1.0R$, profit target floor = $+5.0R$ |
| **Portfolio Concurrency** | **Max 2 Open Positions** | Globally enforced across all 18 parallel symbols |
| **Execution Causality** | **Zero Lookahead ($T \to T+1$)** | Signal at bar $t$ close $\to$ Fill at bar $t+1$ open; 3-hour purge buffer before OOS start |

---

## 5. Reference Code Architecture in the Repository

You must review and build upon the existing real repository code:

1. **Real Microstructure 9-Strategy Engine (16/20 Verified Real Passes)**:
   - File: `Engine_2/run_optimal_regime_matrix.py`
   - Raw URL: `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/run_optimal_regime_matrix.py`
   - *Current Status*: Achieves **16/20 genuine passes on real Binance Parquet data** with Max Drawdown < 4.96%. The only failing windows are W01, W03, W14, and W17 due to low trade count or choppy regime transitions.
2. **Numba Simulation Kernel with 5R Trailing Ratchet**:
   - File: `Engine_2/strategies_20x20/strategy_engine.py`
   - Raw URL: `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/strategies_20x20/strategy_engine.py`
   - *Key Mechanisms*: Implements the Breakeven lock at +1R MFE, the trailing ratchet floor at +5R, and the worst-case drawdown gate.
3. **Parquet Data Loader**:
   - File: `Engine_2/strategies_20x20/data_loader.py`
   - Raw URL: `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/strategies_20x20/data_loader.py`
   - *Capability*: Automatically reads and resamples Binance Parquet datasets.

---

## 6. Your Mission & Expected Deliverable: 9 Individual Strategies Each Passing 20/20 Windows

Your primary objective is to deliver **9 standalone, individual strategy runner files** corresponding to our core microstructure alpha models, where **EVERY SINGLE ONE OF THE 9 STRATEGIES MUST INDIVIDUALLY AND INDEPENDENTLY PASS ALL 20/20 OOS WINDOWS on the real `binance_backtesting_data` Parquet dataset**.

### The 9 Required Microstructure Strategies:
You must provide an individual, self-contained runnable script for each of the following 9 strategies:

1. **`run_real_S1_funding_arb.py`** — **S1: Funding Rate Mean Reversion / Basis Arbitrage**
   - Exploits extreme annualized funding rate dislocations and spot-futures basis spreads (`basis_spread_bps`, `funding_rate_annualized`).
   - Must individually achieve 20/20 OOS passes.
2. **`run_real_S2_liquidation_cascade.py`** — **S2: Liquidation Cascade Flush & Reversal**
   - Triggers when long or short liquidation volume spikes into exhaustion clusters (`liquidation_vol_usd_long`, `liquidation_vol_usd_short`, `liq_cascade_ratio`).
   - Must individually achieve 20/20 OOS passes.
3. **`run_real_S3_cvd_absorption.py`** — **S3: CVD Aggression Absorption Squeeze**
   - Identifies institutional limit-order absorption where aggressive market taker CVD diverges strongly from price advance (`cvd_divergence_zscore`, `taker_buy_ratio`).
   - Must individually achieve 20/20 OOS passes.
4. **`run_real_S4_oi_breakout.py`** — **S4: Open Interest Trend Continuation & Breakout**
   - Detects fresh aggressive positioning entering breakouts with expanding Open Interest and price congruence (`oi_usd_delta_15m`, `oi_price_congruence`).
   - Must individually achieve 20/20 OOS passes.
5. **`run_real_S5_value_area_fade.py`** — **S5: Value Area Edge Fade (VAH/VAL Rejection)**
   - Fades fakeouts and mean-reverts auction extremes outside Value Area High (VAH) and Value Area Low (VAL) back toward POC (`vah_dist_atr`, `val_dist_atr`, `poc_dist_atr`).
   - Must individually achieve 20/20 OOS passes.
6. **`run_real_S6_spot_futures_divergence.py`** — **S6: Spot/Futures Volume Divergence**
   - Detects true spot accumulation vs. leveraged perpetual futures manipulation (`cvd_spot_15m` vs. `cvd_futures_15m`).
   - Must individually achieve 20/20 OOS passes.
7. **`run_real_S7_range_exhaustion.py`** — **S7: Microstructure Range Exhaustion**
   - Reversal engine on volatility exhaustion bands, order book depth skew, and bid/ask liquidity depletion (`bid_ask_skew_depth`).
   - Must individually achieve 20/20 OOS passes.
8. **`run_real_S8_volatility_expansion.py`** — **S8: Volatility Expansion / ATR Breakout with CVD Confirmation**
   - Trend expansion breakout requiring both ATR expansion and directional volume delta confirmation (`vwap_deviation`).
   - Must individually achieve 20/20 OOS passes.
9. **`run_real_S9_mtf_trend_congruence.py`** — **S9: Multi-Timeframe Trend Congruence**
   - Trend alignment across higher-timeframe order flow regimes and micro-execution bars.
   - Must individually achieve 20/20 OOS passes.

---

### Mandatory Execution & Certification Rules for Each of the 9 Scripts:
- **Standalone Execution**: Running `python run_real_S<X>_<name>.py` must execute that specific strategy across all 20 walk-forward windows against `Engine_2/binance_backtesting_data/` without external dependencies.
- **Individual 20/20 Certification**: Each individual strategy file must pass all 5 criteria across all 20 Out-Of-Sample windows **strictly on its own merits**:
  - Window ROI $\ge +20.0\%$ in every window
  - Max Drawdown $< 4.75\%$ ($\le \$237.50$) in every window
  - Win Rate $\ge 40.0\%$ in every window
  - Closed Trades $\ge 5$ in every window
  - Trade Floor $\ge +5.0R$ target for every winning trade
- **Zero Blending Masking**: Do NOT pool or cross-subsidize trades between strategies to mask an individual strategy failing windows. Each of the 9 scripts must stand alone as a certified 20/20 producer.
- **Master Verification Runner (`run_all_real_9strats.py`)**:
  Provide a master script `run_all_real_9strats.py` that executes all 9 strategy files in sequence, prints the comparative 9-strategy scorecard, and asserts that **all 9 strategies individually pass 20/20 windows (total 180 / 180 window passes)**.
- **Strict Real Data Only**: All scripts must read from `Engine_2/binance_backtesting_data/`. Any script that generates synthetic CSVs or uses artificial random walks will be instantly rejected.


