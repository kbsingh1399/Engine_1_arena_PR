# 🏛️ INSTITUTIONAL QUANT COUNCIL: MASTER STRATEGY GENERATION PROMPT (S1 FRESH BUILD)
# Target: Engineering Production-Grade `s1_liquidation_cascade.py` & `test_all_20_regimes.py` Across 20 Walk-Forward OOS Regimes (2021–2026)
# Dataset: 18 Binance USDT-M Perpetuals (3,464,074 15-Minute Bars, Table 1 & Table 2 Footprint Parquet) in `Engine_2/binance_backtesting_data/`
# Architecture Grounding: Second Brain Knowledge Base v15.0 (Nodes 1–100) & FABLE 5 Zero-Lookahead Protocols

---

## 1. EXECUTIVE MISSION & CORE ARCHITECTURAL DIRECTIVE

You are the Lead Quantitative Architect and Chief Risk Officer at an institutional systematic crypto hedge fund. Your mission is to write clean, complete, production-grade Python code for the fresh S1 strategy suite:
1. **`Engine_2/s1_liquidation_cascade.py`**: The self-contained alpha generation, feature engineering, Numba execution simulator, and portfolio risk management engine.
2. **`Engine_2/test_all_20_regimes.py`**: The sequential walk-forward evaluation harness running all 20 Out-Of-Sample (OOS) quarterly regimes (2021–2026).
3. **`Engine_2/STRATEGY_SPEC.md`**: The quantitative architecture specification document detailing the mathematical formulation, risk rules, and empirical validation gates.

### Mandatory Git Repository Context (FETCH DIRECTLY VIA RAW GITHUB URLs)
Do NOT guess column names, parameters, or file layouts. Fetch context directly:
- **Second Brain Knowledge Base v17.0 (112 Structured Nodes)**:  
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/memory/architecture/trading_knowledge_base.md`
- **Master Agent Enforcement & Institutional Anti-Lookahead Rules**:  
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/rules/AGENTS.md`
- **Lethal 13-Step Bug Hunt & Part 14 Zero-Hallucination Blacklist**:  
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/rules/FABLE5_CHECKLIST.md`
- **Institutional Multi-Sleeve Architecture & Root-Cause Audit**:  
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/ENGINE2_AUDIT_MASTER.md`
- **Turn-0 Operational Context & Verified Invariants**:  
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/rules/ACTIVE_CONTEXT.md`

---

## 2. POST-MORTEM ROOT CAUSE DIAGNOSTICS: WHY PRIOR RUNS FAILED

A previous implementation attempt reported 0/20 passes due to three fatal structural design flaws that you MUST permanently eradicate:

### Flaw 1: The "5.0R All-or-Nothing" Retracement Trap
- **The Bug**: Trade holding logic forced an arbitrary $+5.0\text{R}$ target while keeping the stop loss frozen at $-1.0\text{R}$.
- **Microstructure Reality (Nodes 32, 51, 83)**: On 15-minute crypto perpetuals, violent liquidation bounces expand $+1.2\text{R}$ to $+2.5\text{R}$ within 2 to 8 bars ($30\text{m}$ to $2\text{h}$) before entering consolidation or mean-reverting. Demanding $5.0\text{R}$ without moving stops caused **85.8% of winning moves to retrace into full stop-outs**.
- **The Mandatory Fix (Nodes 51 & 94 — Dynamic 4-Tier Ratchet & Snell Stopping Bound)**:
  1. **Phase 0 Breakeven Lock**: At $+0.80\text{R}$ price gain $\to$ trail active stop to Entry $+0.15\text{R}$ (securing round-trip taker fees and slippage).
  2. **Phase 1 Profit Lock**: At $+1.50\text{R}$ price gain $\to$ trail active stop to Entry $+0.80\text{R}$.
  3. **Target Exit**: Close $80\%$ of position at $+2.0\text{R} \dots +2.5\text{R}$ (or Yang-Zhang ATR target), trailing the remaining $20\%$ runner with a $0.80\text{R}$ trail.
  4. **The 24-Bar (6-Hour) Snell Envelope Time Stop**: If the trade fails to achieve at least $+0.20\text{R}$ within 24 bars ($6\text{h}$), exit immediately at market. Beyond 24 bars, open positions transition into supermartingales with decaying edge and rising funding fee drag.

### Flaw 2: Single-Sleeve Trade Starvation in Quiet Regimes
- **The Bug**: Restricting candidates solely to simultaneous extreme conditions (`long_liq_zs > 1.8 ∧ zc_div > 0.8 ∧ RSI < 40 ∧ vwap_z < -0.5`) produced only 2–3 trades in entire quarters (e.g. W03, W04), failing the minimum statistical trade count ($\ge 6$).
- **The Mandatory Fix (Multi-Sleeve Confluence from Nodes 71–100)**:
  Extract candidate opportunities across 4 complementary quantitative sleeves across the 18 symbols:
  - **Sleeve 1 (Liquidation Cascade Flush)**: Extreme liquidation volume (`long_liq_zs > 1.5`) + spot absorption divergence (`zc_div > 0.6`).
  - **Sleeve 2 (Spot CVD Absorption & Basis Snapback)**: Futures CVD aggressively selling ($\Delta\text{CVD}_{\text{fut}} < 0$) while spot CVD aggressively accumulates ($\Delta\text{CVD}_{\text{spot}} > 0$) with negative basis dislocation.
  - **Sleeve 3 (Extreme VWAP Overshoot Mean Reversion)**: Price excursion $\text{vwap\_z} < -0.8$ with $\text{RSI}_{14} < 35$ and volume expansion $>1.5\times$ rolling 20-bar average.
  - **Sleeve 4 (Deep Squeeze & Volatility Expansion)**: Bollinger Band width contracting inside Keltner Channel with subsequent upside volume expansion and positive spot delta.
  *Yield*: Generates 15 to 45 high-probability trade opportunities per quarter, completely curing trade starvation.

### Flaw 3: Sizing Asymmetry & Drawdown Circuit Breakers
- **The Bug**: Aggressively jumping position risk to $\$160.0$ on a tiny profit trigger of $\$25.0$. With a hard drawdown limit of $4.5\%$ ($\$225.0$ on a $\$5,000.0$ bankroll), two consecutive stop-outs breached the circuit breaker and halted trading for the rest of the quarter.
- **The Mandatory Fix (Fixed Risk Budget Invariants)**:
  - `INITIAL_CAPITAL = 5000.0`
  - `BASE_RISK = 25.0` ($0.50\%$ of bankroll; requires 9 consecutive max stop-outs to breach $4.5\%$).
  - `HOUSE_MONEY_RISK = 50.0` ($1.00\%$ max risk, active ONLY when net closed profit $\ge \$50.0$).
  - `DRAWDOWN_DEFENSE_RISK = 15.0` ($0.30\%$ defensive risk when drawdown exceeds $2.5\%$).
  - `DRAWDOWN_RISK_LIMIT = 0.045` ($4.5\%$ / $\$225.0$ emergency circuit breaker).
  - `MAX_CONCURRENT = 2` (maximum 2 open positions across all 18 symbols).

---

## 3. MASTER DATA ARCHITECTURE & 18-ASSET UNIVERSE

- **Data Path**: `Engine_2/binance_backtesting_data/`
- **18 Institutional Symbols**:
  `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `DOGEUSDT`, `ADAUSDT`, `AVAXUSDT`, `LINKUSDT`, `SUIUSDT`, `NEARUSDT`, `APTUSDT`, `PEPEUSDT`, `WIFUSDT`, `TIAUSDT`, `ARBUSDT`, `OPUSDT`, `INJUSDT`.
- **Granularity**: 15-minute OHLCV candles (3,464,074 rows, 0 nulls, strictly monotonic timestamps).
- **Table 1 Core Fields**:
  `timestamp`, `open`, `high`, `low`, `close`, `volume`, `quote_volume`, `taker_buy_base_volume`, `taker_buy_quote_volume`, `spot_volume`, `spot_taker_buy_volume`, `future_cvd_15m`, `spot_cvd_15m`, `long_liq_usd`, `short_liq_usd`, `oi_close`, `oi_change_pct`, `funding_rate`, `basis_bps`, `bid_depth_usd`, `ask_depth_usd`, `depth_imbalance`, `whale_index`, `trade_count`, `avg_trade_size_usd`.
- **Table 2 Footprint Fields (optional enhancement)**:
  `fp_poc`, `fp_val`, `fp_vah`, `fp_delta`, `fp_min_delta`, `fp_max_delta`, `fp_imbalance_buy_count`, `fp_imbalance_sell_count`, `fp_stacked_buy_imbalance`, `fp_stacked_sell_imbalance`, `fp_unfinished_auction_high`, `fp_unfinished_auction_low`.

---

## 4. MATHEMATICAL FEATURE EQUATIONS (GROUNDED IN SECOND BRAIN v15.0)

Every indicator must be computed causally using strictly historical bars ($t, t-1, \dots$):

1. **Liquidation Volume Z-Score (`long_liq_zs`)** (Node 1):
   $$\text{long\_liq\_zs}_t = \frac{\text{long\_liq\_usd}_t - \mu_{20}(\text{long\_liq\_usd})}{\sigma_{20}(\text{long\_liq\_usd}) + \epsilon}$$
2. **Spot-Futures CVD Divergence (`zc_div`)** (Node 71):
   $$D_t = \Delta\text{CVD}_{\text{spot}, t} - \gamma \Delta\text{CVD}_{\text{futures}, t}, \quad \text{zc\_div}_t = \frac{D_t - \mu_{20}(D)}{\sigma_{20}(D) + \epsilon}$$
   *(where $\gamma = \frac{\text{Mean}(\text{Spot Volume})}{\text{Mean}(\text{Futures Volume})} \approx 0.35$)*.
3. **Anchored VWAP Z-Score (`vwap_z`)** (Node 72):
   $$\text{AVWAP}_t = \frac{\sum_{\tau=t_0}^t P_{\tau} \cdot V_{\tau}}{\sum_{\tau=t_0}^t V_{\tau}}, \quad \text{vwap\_z}_t = \frac{P_t - \text{AVWAP}_t}{\sigma_{\text{VWAP}, t} + \epsilon}$$
   *(with daily anchor reset at 00:00 UTC / 05:30 IST)*.
4. **Volume-Synchronized Probability of Toxicity (VPIN)** (Node 77):
   $$\text{VPIN} = \frac{\sum_{\tau=1}^N |V_\tau^B - V_\tau^S|}{N \cdot V}, \quad \Delta\text{VPIN} < -0.20 \implies \text{absorption confirmed}$$
5. **Depth Replenishment Velocity ($\dot{L}_{\text{replenish}}$)** (Node 89):
   $$\dot{L}_{\text{replenish}, t} = \frac{\text{bid\_depth\_usd}_t - \text{bid\_depth\_usd}_{t-1}}{\Delta t} > 2.5 \times \text{EMA}_{20}(\dot{L})$$
6. **Cross-Asset Priority Score ($\Psi_i$) for Concurrent Allocation** (Node 76):
   $$\Psi_i = \frac{\text{long\_liq\_zs}_i \cdot \text{zc\_div}_i}{\sigma_{\text{YZ}, i}} \quad \text{for top 2 concurrent slots}$$
7. **Yang-Zhang Volatility ($\sigma_{\text{YZ}}$) & Stop Sizing**:
   $$\sigma_{\text{YZ}}^2 = \sigma_{\text{Overnight}}^2 + k \sigma_{\text{OpenToClose}}^2 + (1-k) \sigma_{\text{RS}}^2$$
   $$\text{stop\_dist} = \max(1.5 \times \text{ATR}_{14}, 2.0 \times \sigma_{\text{YZ}} \cdot P_t) + \text{EVT\_buffer}$$
   *(where EVT buffer $= 0.15 \times \text{ATR}_{14}$ prevents false stopouts on wick extremes)*.

---

## 5. THE 20 CAUSAL WALK-FORWARD OOS WINDOWS (2021–2026)

All 20 windows are strictly non-overlapping test periods. In-sample training or calibration MUST end strictly at $t_{\text{purge}} = t_{\text{start}} - 72\text{h}$ to prevent trade resolution leakage.

| Window | Test Start | Test End | In-Sample Training Interval | Regime Macro Environment |
|---|---|---|---|---|
| **W01** | 2021-01-01 | 2021-03-31 | 2020-01-01 to 2020-12-29 | Post-Halving Bull Expansion |
| **W02** | 2021-04-01 | 2021-06-30 | 2020-01-01 to 2021-03-29 | Historic May 2021 Cascades |
| **W03** | 2021-07-01 | 2021-09-30 | 2020-01-01 to 2021-06-28 | Summer Liquidity Drain |
| **W04** | 2021-10-01 | 2021-12-31 | 2020-01-01 to 2021-09-28 | All-Time-High Blow-Off |
| **W05** | 2022-01-01 | 2022-03-31 | 2020-01-01 to 2021-12-29 | Fed Hawkish Bear Pivot |
| **W06** | 2022-04-01 | 2022-06-30 | 2020-01-01 to 2022-03-29 | Luna/Terra Death Spiral |
| **W07** | 2022-07-01 | 2022-09-30 | 2020-01-01 to 2022-06-28 | Post-Contagion Dead Drift |
| **W08** | 2022-10-01 | 2022-12-31 | 2020-01-01 to 2022-09-28 | FTX Collapse & Liquidity Void |
| **W09** | 2023-01-01 | 2023-03-31 | 2020-01-01 to 2022-12-29 | SVB Bank Run & Short Squeeze |
| **W10** | 2023-04-01 | 2023-06-30 | 2020-01-01 to 2023-03-29 | SEC Regulatory Crackdown |
| **W11** | 2023-07-01 | 2023-09-30 | 2020-01-01 to 2023-06-28 | August 17 Flash Cascade |
| **W12** | 2023-10-01 | 2023-12-31 | 2020-01-01 to 2023-09-28 | ETF Speculation Momentum |
| **W13** | 2024-01-01 | 2024-03-31 | 2020-01-01 to 2023-12-29 | Spot ETF Inflow Explosion |
| **W14** | 2024-04-01 | 2024-06-30 | 2020-01-01 to 2024-03-29 | Halving Chop & Consolidation |
| **W15** | 2024-07-01 | 2024-09-30 | 2020-01-01 to 2024-06-28 | Yen Carry Unwind Panic |
| **W16** | 2024-10-01 | 2024-12-31 | 2020-01-01 to 2024-09-28 | Post-Election Liquidity Rally |
| **W17** | 2025-01-01 | 2025-03-31 | 2020-01-01 to 2024-12-29 | Institutional Altcoin Rotation |
| **W18** | 2025-04-01 | 2025-06-30 | 2020-01-01 to 2025-03-29 | Macro De-Risking Volatility |
| **W19** | 2025-07-01 | 2025-09-30 | 2020-01-01 to 2025-06-28 | Autumn Leverage Flush |
| **W20** | 2025-10-01 | 2025-12-31 | 2020-01-01 to 2025-09-28 | 2025 Year-End Macro Regime |

---

## 6. INSTITUTIONAL PERFORMANCE GATES & ZERO-LOOKAHEAD BLACKLIST

### Target Pass Criteria (Per OOS Window):
- $\text{ROI} \ge 10.0\%$ (Target: $\ge 20.0\%$)
- $\text{Max Drawdown (MTM)} \le 5.0\%$
- $\text{Win Rate} \ge 40.0\%$
- $\text{Total Closed Trades} \ge 6$

### Mandatory Institutional Execution Realism:
1. **Frictions**: Real Binance taker fee $\ge 8\text{ bps}$ ($0.08\%$), Entry slippage $\ge 10\text{ bps}$, Stop-loss slippage $\ge 15\text{ bps}$.
2. **Causal Stop Arming**: Ratchet updates take effect strictly on bar $j+1$ after trigger bar $j$.
3. **Gap-Through Fills**: If a bar opens below the stop price, fill execution at `open - slippage`, never at the theoretical stop.
4. **Mark-to-Market Drawdown**: Track bar-by-bar unrealized equity; never use future trade MAE.

### Anti-Lookahead Blacklist (Part 14 of `FABLE5_CHECKLIST.md`):
- ⛔ **NO `winning_configuration.json` or `s1_status.json`**.
- ⛔ **NO hardcoded per-window parameter lookup tables (`WINDOW_CONFIGURATIONS[w_idx]`)**.
- ⛔ **NO loops iterating over candidate parameters on OOS data**.
- ⛔ **NO early breaks upon reaching target ROI**.

---

## 7. CODE DELIVERABLE REQUIREMENTS

Deliver the following three complete, production-grade files:

### Deliverable 1: `Engine_2/s1_liquidation_cascade.py`
- Must import and vectorize calculations over `Engine_2/binance_backtesting_data/*.parquet`.
- Implement `@njit` trade path simulator with gap-aware fills, 4-tier ratchet, and 24-bar time stop.
- Implement causal portfolio backtester with MTM equity tracking and $25/$50/$15 risk governor.
- Must run cleanly with zero missing imports or external lookup dependencies.

### Deliverable 2: `Engine_2/test_all_20_regimes.py`
- Standalone execution runner iterating through Windows 1 to 20.
- Prints live console scorecard for each window with ROI, MaxDD, WinRate, Trade Count, and Status (`[PASS]` / `[FAIL]`).
- Exports verified results to `Engine_2/results/s1_oos_window_results.csv`.
- Returns exit code 0 if all 20 windows pass.

### Deliverable 3: `Engine_2/STRATEGY_SPEC.md`
- Complete formal architecture document defining the strategy mathematical specification, feature dictionary, risk constraints, and validation results.

*OUTPUT ONLY PURE, EXECUTABLE, HIGH-PERFORMANCE PYTHON CODE AND COMPLETE MARKDOWN SPECIFICATION. ZERO PLACEHOLDERS.*
