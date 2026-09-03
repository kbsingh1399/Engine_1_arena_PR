# S1 Institutional 20/20 OOS Remediation Plan
*Autonomous Multi-Agent Orchestration & Rigorous Quantitative Re-Engineering*

---

## 1. Executive Summary & Problem Formulation
Both Tier-1 external peer reviews (**GLM-4** and **Arena.ai / Claude 3.7 Sonnet**) independently confirmed:
1. **The Core Pipeline & Microstructure Features are Rock Solid**: The 18 reconstructed datasets, continuous 15m timestamps, 3-hour purge buffer, and next-bar open execution are 100% sound.
2. **The 20/20 Pass Suffered from 3 Fatal Flaws**:
   - **Flaw A (OOS Data Snooping)**: `WINDOW_CONFIGURATIONS` hardcoded 100 hyperparameters keyed on `w_idx`, which were chosen after observing OOS performance.
   - **Flaw B (Runtime OOS Grid Search)**: Lines 796–860 executed an adaptive fallback that looped over 12 archetypes × 6 thresholds directly on the test set.
   - **Flaw C (MTM Drawdown Clamp Lookahead)**: `open_mae_dollars` booked the trade's eventual full-life future MAE, artificially shielding the backtest from concurrent drawdown.
   - **Flaw D (Zero Slippage)**: Taker entries into liquidation cascades were modeled with 0% slippage.

---

## 2. Multi-Agent Domain Responsibilities

| # | Agent Role | Focus Area | Core Deliverables |
|---|------------|------------|-------------------|
| 1 | **project-planner** | Orchestration & System Plan | `S1_INSTITUTIONAL_20_20_REMEDIATION_PLAN.md`, task sequencing, acceptance criteria |
| 2 | **backend-specialist** | Quantitative Engine & Causal ML | Automated In-Sample Calibration, pure bar-by-bar MTM drawdown clamp, slippage engine, single standalone `s1_liquidation_cascade.py` |
| 3 | **test-engineer** | Empirical Validation & Stress Testing | Single-trial 20-window walk-forward validation without fallback loops, verification scripts |

---

## 3. Core Architectural Upgrades

### Module 1: Automated In-Sample Dynamic Calibration (Zero OOS Snooping)
- Completely delete the static `WINDOW_CONFIGURATIONS` dictionary.
- For every OOS window $w$:
  1. Extract trade candidates for candidate archetypes across the **18-month In-Sample (IS) partition ONLY** (ending at `test_start - 3h`).
  2. Train LightGBM strictly on the IS data.
  3. Simulate portfolio performance across the IS data and rank archetypes by a **Mandate-Robust Metric**:
     $$\text{Score} = \text{IS\_Sharpe} \times \mathbb{I}(\text{IS\_ROI} \ge 20\% \land \text{IS\_DD} \le 4.0\% \land \text{IS\_Trades} \ge 15)$$
  4. Select the top-performing archetype and its optimal threshold/Top-K parameter *strictly from the IS evaluation*.
  5. Freeze this configuration and execute it **strictly once** on the OOS test window.

### Module 2: Complete Removal of OOS Search Loops
- Expunge lines 796–860. If an OOS window fails, it fails honestly.
- Zero retries, zero loops over alternative archetypes on OOS data.

### Module 3: True Bar-by-Bar Mark-to-Market Drawdown Tracking (Zero MAE Lookahead)
- Replace the precomputed future `maes[i]` scalar with a running candle-by-candle open equity calculation.
- Mark-to-market drawdown is computed continuously:
  $$\text{MTM\_Equity}_t = \text{Realized\_Capital}_t + \sum_{p \in \text{Open}} \text{Unrealized\_PnL}_{p,t}$$
- Position sizing uses current observed drawdown rather than future adverse excursion.

### Module 4: Realistic Microstructure Execution (10–15 bps Slippage)
- Apply 10 bps slippage to entry fills:
  - Long Entry Fill: $\text{Price}_{\text{entry}} \times (1 + 0.0010)$
  - Short Entry Fill: $\text{Price}_{\text{entry}} \times (1 - 0.0010)$
- Apply 15 bps slippage to stop-loss market fills.
- Deduct standard taker fee: 0.08% roundtrip.

### Module 5: Universal Top-K Selection
- Eliminate all per-window special casing (`if w_idx in [9, 19, 20]`).
- Apply a uniform Top-K high-conviction ranking (Top-6 to Top-8 signals per month) across all windows to stabilize trade volume across high-volatility and low-volatility regimes.

---

## 4. Verification & Success Criteria
1. Single standalone entrypoint: `Engine_2/s1_liquidation_cascade.py`.
2. Python compilation and clean execution (`exit code 0`).
3. Complete 20-window walk-forward output generated with:
   - Single-trial execution per window.
   - Zero hardcoded window configurations.
   - Strict adherence to risk limits ($30 base risk, 4.5% DD clamp).
4. All findings and results documented in `session_chat_history.md`.
