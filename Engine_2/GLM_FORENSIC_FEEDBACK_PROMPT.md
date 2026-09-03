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

## 6. Your Mission & Expected Deliverable: Individual 20/20 Strategy Files

Your primary objective is to deliver **individual, standalone strategy runner files** where **EACH strategy individually and independently passes all 20/20 OOS windows on the real `binance_backtesting_data` Parquet dataset**.

### Specific Deliverable Requirements:
1. **Individual Executable Strategy Files (`run_real_S01.py`, `run_real_S02.py`, ...)**:
   - Provide a dedicated, standalone runner script for each individual strategy (e.g. `run_real_S01.py` for Funding Rate Arbitrage, `run_real_S02.py` for Liquidation Cascades, etc.).
   - **Standalone Execution**: Running `python run_real_SXX.py` must execute that specific strategy across all 20 walk-forward windows on real Binance Parquet data without requiring any external scaffolding.
   - **Individual 20/20 Certification**: Each individual strategy file must pass all 5 criteria across all 20 Out-Of-Sample windows **on its own merit**:
     - Window ROI $\ge +20.0\%$ in every window
     - Max Drawdown $< 4.75\%$ ($\le \$237.50$) in every window
     - Win Rate $\ge 40.0\%$ in every window
     - Closed Trades $\ge 5$ in every window
     - Trade Floor $\ge +5.0R$ target for winning trades
   - **Zero Blending Masking**: Do NOT aggregate or cross-subsidize trades between strategies to mask an individual strategy failing windows. Every delivered script must stand alone as a certified 20/20 producer.

2. **Master Verification Runner (`run_all_real.py`)**:
   - Provide a master orchestration script `run_all_real.py` that iterates through all individual strategy scripts, runs them across the 20 OOS windows on the real dataset, prints the full per-strategy scorecard, and asserts that 100% of the strategies achieve 20/20 passes.

3. **Step-by-Step Tactical Implementation Directives**:
   - **Leverage the 9 Microstructure Strategies**: Use real order flow, CVD divergence, liquidation flushes, OI acceleration, and Value Area bounds from `BTCUSDT_15m_master_2020_2026.parquet` and the other 17 symbols.
   - **Solve the 4 Failing Windows (W01, W03, W14, W17)**: Apply dynamic regime pacing and multi-asset selection across the 18 symbols so each individual strategy captures at least 5 high-conviction $\ge 5R$ setups during low-volatility and consolidation regimes without triggering the 4.75% drawdown circuit breaker.
   - **Integrate the 5R Trailing Ratchet Kernel**: Enforce the +1R Breakeven lock and the +5R trailing ratchet floor to guarantee that every single winning trade locks in at least +5.0R profit before exit.
   - **Zero Synthetic Data / Zero Placeholders**: All file paths must point to `Engine_2/binance_backtesting_data/`. Any script outputting synthetic CSVs or hardcoding artificial trajectories will be rejected immediately.

