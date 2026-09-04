# 🏛️ INSTITUTIONAL QUANT COUNCIL: THE FRESH S1 LIQUIDATION-CASCADE STRATEGY PROMPT
# Target: Production-Grade S1 Strategy Module across 20 Walk-Forward Out-Of-Sample (OOS) Windows (2021–2026)
# Dataset: 18 Binance USDT-M Perpetuals (3.46M 15m bars, Table 1 & Table 2 Parquet) in `Engine_2/binance_backtesting_data/`

---

## 1. EXECUTIVE MISSION & CORE QUANTITATIVE MANDATE

You are the Lead Quantitative Architect and Chief Risk Officer tasked with engineering a clean-slate, production-grade quantitative trading strategy: **`Engine_2/s1_liquidation_cascade.py`** and its walk-forward evaluation harness **`Engine_2/test_all_20_regimes.py`**.

### Verified Strategy Repository & Context References (DO NOT GUESS — FETCH VIA RAW GIT URLs)
- **Second Brain Knowledge Base v11.0 (Nodes 1–76)**:
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/memory/architecture/trading_knowledge_base.md`
- **Master Agent Enforcement & Institutional Anti-Lookahead Rules**:
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/rules/AGENTS.md`
- **Lethal 13-Step Bug Hunt & Part 14 Zero-Hallucination Blacklist**:
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/rules/FABLE5_CHECKLIST.md`
- **Institutional Multi-Sleeve Architecture & Root-Cause Diagnostics**:
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/ENGINE2_AUDIT_MASTER.md`

---

## 2. ROOT-CAUSE POST-MORTEM: WHY PRIOR IMPLEMENTATIONS FAILED

A previous exploratory PR attempted to fit S1 and reported 0/20 passes due to three structural design blunders that MUST be strictly eliminated:

### Blunder 1: The "5.0R All-or-Nothing" Retracement Trap
- **The Failure**: Holding 15-minute liquidation bounce trades until an arbitrary $+5.0\text{R}$ target while keeping the stop loss frozen at $-1.0\text{R}$.
- **The Empirical Reality**: Microstructure liquidation snapbacks expand $+1.2\text{R}$ to $+2.5\text{R}$ within 2 to 8 bars ($30\text{m}$ to $2\text{h}$) before entering consolidation or mean-reverting. Holding out for $5.0\text{R}$ caused $85.8\%$ of winning moves to retrace into full stop-outs!
- **The Solution (Node 51 & Node 70)**:
  1. **Phase 0 Breakeven Lock**: At $+0.80\text{R}$ gain $\to$ trail stop to Entry $+0.15\text{R}$ (securing round-trip taker fees and slippage).
  2. **Phase 1 Profit Lock**: At $+1.50\text{R}$ gain $\to$ trail stop to Entry $+0.80\text{R}$.
  3. **Target Scaling**: Take partial/full profit at $+2.0\text{R} \dots +2.5\text{R}$ (or dynamic Yang-Zhang ATR target), allowing a $20\%$ runner to trail with a $0.8\text{R}$ kinetic trail.
  4. **Time Decay Exit**: Exit at market if trade fails to gain at least $+0.20\text{R}$ within 24 bars (6 hours).

### Blunder 2: Trade Starvation from Overly Constrained Single-Sleeve Logic
- **The Failure**: Restricting candidate selection solely to simultaneous extreme conditions (`long_liq_zs > 1.8 ∧ zc_div > 0.8 ∧ RSI < 40 ∧ vwap_z < -0.5`), which generated only 2–3 events in entire quarters (e.g. W03, W04), failing the minimum statistical sample size.
- **The Solution (Multi-Sleeve Confluence from `ENGINE2_AUDIT_MASTER.md`)**:
  Build an ensemble of complementary quantitative sleeves across the 18 symbols:
  - **Sleeve 1 (Liquidation Cascade Flush)**: Extreme liquidation spike (`long_liq_zs > 1.5`) + spot absorption divergence (`zc_div > 0.6`).
  - **Sleeve 2 (Spot CVD Absorption & Basis Snapback)**: Severe futures selling ($\Delta\text{CVD}_{\text{futures}} < 0$) absorbed by spot aggressive bidding ($\Delta\text{CVD}_{\text{spot}} > 0$) with negative basis dislocation.
  - **Sleeve 3 (Extreme VWAP Overshoot Mean Reversion)**: Price excursion $\text{vwap\_z} < -0.8$ with RSI $< 35$ and volume expansion.
  - **Sleeve 4 (Deep Squeeze & Volatility Expansion)**: Keltner/Bollinger volatility squeeze breakout in oversold conditions.
  This produces 15 to 45 robust candidate opportunities per quarterly window.

### Blunder 3: Sizing Asymmetry & Drawdown Circuit Breakers
- **The Failure**: Aggressively jumping position risk to $\$160$ on a tiny profit, causing 2 losses to breach the $\$225$ hard drawdown limit ($4.5\%$).
- **The Solution (Nodes 63, 69 & Settled Invariants)**:
  - `INITIAL_CAPITAL = 5000.0`
  - `BASE_RISK = 25.0` ($0.50\%$ of equity; requires 9 consecutive max stop-outs to breach $4.5\%$).
  - `HOUSE_MONEY_RISK = 50.0` ($1.00\%$ max risk, active ONLY when net closed profit $\ge \$50.0$).
  - `DRAWDOWN_DEFENSE_RISK = 15.0` ($0.30\%$ risk when drawdown exceeds $2.5\%$).
  - `DRAWDOWN_RISK_LIMIT = 0.045` ($4.5\%$ / $\$225.0$ emergency halt).
  - `MAX_CONCURRENT = 2` (maximum 2 open positions across all 18 symbols).

---

## 3. DATA ARCHITECTURE & 18-ASSET MASTER UNIVERSE

- **Data Path**: `Engine_2/binance_backtesting_data/`
- **18 Institutional Symbols**:
  `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `DOGEUSDT`, `ADAUSDT`, `AVAXUSDT`, `LINKUSDT`, `SUIUSDT`, `NEARUSDT`, `APTUSDT`, `PEPEUSDT`, `WIFUSDT`, `TIAUSDT`, `ARBUSDT`, `OPUSDT`, `INJUSDT`.
- **Granularity**: 15-minute OHLCV candles (3,464,074 total rows, 0 nulls, monotonic timestamps).
- **Table 1 Fields**: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `quote_volume`, `taker_buy_base_volume`, `taker_buy_quote_volume`, `spot_volume`, `spot_taker_buy_volume`, `future_cvd_15m`, `spot_cvd_15m`, `long_liq_usd`, `short_liq_usd`, `oi_close`, `oi_change_pct`, `funding_rate`, `basis_bps`, `bid_depth_usd`, `ask_depth_usd`, `depth_imbalance`, `whale_index`, `trade_count`, `avg_trade_size_usd`.
- **Table 2 Footprint Fields (if used)**: `fp_poc`, `fp_val`, `fp_vah`, `fp_delta`, `fp_min_delta`, `fp_max_delta`, `fp_imbalance_buy_count`, `fp_imbalance_sell_count`, `fp_stacked_buy_imbalance`, `fp_stacked_sell_imbalance`, `fp_unfinished_auction_high`, `fp_unfinished_auction_low`.

---

## 4. THE 20 CAUSAL WALK-FORWARD OOS WINDOWS (2021–2026)

Every window represents a continuous 1-month or 1-quarter test regime. Training data MUST strictly end at $t_{\text{purge}} = t_{\text{start}} - 72\text{h}$.

| Window | Test Start | Test End | In-Sample Training Interval | Regime Description |
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

## 5. INSTITUTIONAL PERFORMANCE GATES & ANTI-LOOKAHEAD BLACKLIST

### Target Pass Criteria (per OOS window):
- $\text{ROI} \ge 10.0\%$ (Target: $\ge 20.0\%$)
- $\text{Max Drawdown (MTM)} \le 5.0\%$
- $\text{Win Rate} \ge 40.0\%$
- $\text{Total Closed Trades} \ge 6$

### Institutional Execution Realism (Mandatory):
1. **Frictions**: Real taker fee $\ge 8\text{ bps}$ ($0.08\%$), Entry slippage $\ge 10\text{ bps}$, Stop-loss slippage $\ge 15\text{ bps}$.
2. **Causal Stop Arms**: Ratchet rungs take effect strictly on bar $j+1$ after the trigger bar.
3. **Gap-Through Fills**: If bar open gaps below the stop price, the trade fills at the bar open price minus slippage, never at the theoretical stop.
4. **Mark-to-Market Drawdown**: Track bar-by-bar unrealized equity; never use future trade MAE.

### Anti-Lookahead Blacklist (Part 14 of FABLE5_CHECKLIST.md):
- ⛔ **NO `winning_configuration.json` or `s1_status.json`**.
- ⛔ **NO hardcoded per-window parameter tables (`WINDOW_CONFIGURATIONS[w_idx]`)**.
- ⛔ **NO loops iterating over OOS data to find a passing candidate**.
- ⛔ **NO early breaks upon reaching target ROI**.

---

## 6. DELIVERABLE SPECIFICATION

Deliver two complete, standalone, production Python modules:
1. **`Engine_2/s1_liquidation_cascade.py`**:
   - Vectorized feature engineering and candidate extraction across the 18 symbols.
   - High-performance Numba-accelerated trade path simulator (`@njit`) with multi-tier ratchet and 24-bar time stop.
   - Portfolio risk manager with causal MTM drawdown tracking and max 2 concurrent positions.
   - Causal in-sample meta-labeling or threshold calibration with strictly purged boundaries ($t_{\text{start}} - 72\text{h}$).
2. **`Engine_2/test_all_20_regimes.py`**:
   - Sequential walk-forward evaluation harness iterating through all 20 OOS windows.
   - Live terminal reporting of Window ROI, MaxDD, WinRate, Trade Count, and Pass/Fail status.
   - Saves verified results to `Engine_2/results/s1_oos_window_results.csv`.

*Output ONLY pure, executable, production Python code with complete implementations. Zero placeholders.*
