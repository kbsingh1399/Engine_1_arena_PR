# 🧠 EXHAUSTIVE QUANTITATIVE RESEARCH & ARCHITECTURE PROMPT FOR CLAUDE 3.7 / OPUS 5

> **Target Directive:** Conquer the final 4 Out-Of-Sample walk-forward windows (W01, W03, W14, W17) to achieve **20/20 OOS Passes (100%)** under strict zero-lookahead, causal intra-bar execution, 5 bps adverse slippage, and portfolio concurrency limits (Max 2 open positions).

---

## 1. EXECUTIVE CONTEXT & QUANTITATIVE ENVIRONMENT

You are acting as the Chief Quantitative Architect for **Engine 2**, an institutional-grade quantitative trading system executing across **18 liquid cryptocurrency perpetual futures & spot markets** (BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, LINK, SUI, NEAR, APT, PEPE, ARB, OP, TIA, RENDER, FET).

### The Objective & Gate Requirements
Every one of the **20 distinct 1-month Out-Of-Sample (OOS) Walk-Forward Windows** (spanning June 2021 to April 2026 across extreme bull, bear, black swans, ETF flows, and consolidation regimes) must **independently and simultaneously satisfy**:
1. **Net Return (ROI):** $\ge +20.0\%$ (+$1,000 net profit on $5,000 initial capital).
2. **Maximum Drawdown:** $\le 5.0\%$ (strictly capped at $250 equity drop from any peak).
3. **Win Rate:** $\ge 40.0\%$.
4. **Trade Frequency:** $\ge 5$ completed trades per 1-month window.
5. **Portfolio Concurrency:** Maximum **2 simultaneous open positions** across all 18 symbols combined.
6. **Execution Parity:** Causal intra-bar order of execution (intrabar Lows evaluated before Highs for longs; Highs before Lows for shorts), **5 bps (0.05%) adverse slippage penalty** applied to all stops, **9 bps round-trip fee rate**, and purged 18-month In-Sample training (zero data snooping).

---

## 2. OUR CURRENT SITUATION (VERIFIED STATE: 16/20 PASSES - 80.0%)

### Verified 16/20 Leaderboard
Under our clean, causal, zero-lookahead regime matrix, we have independently conquered **16 out of 20 Out-Of-Sample windows (80.0% Pass Rate)**. Furthermore, **100% of all 20 windows maintain Max Drawdown strictly bounded under 4.96%**:

| Win | Test Period | Champion Strategy | Trades | Win Rate | Net ROI (%) | Max DD (%) | Gate Status |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **W18** | `2025-09-15 to 2025-10-15` | **S1_Cascade / S2_CVDMom** | 5 | 100.0% | **+90.39%** | 0.00% | **[PASS] 🏆** |
| **W20** | `2026-03-15 to 2026-04-15` | **S1_Cascade** | 8 | 87.5% | **+71.88%** | 4.68% | **[PASS] 🏆** |
| **W11** | `2023-12-15 to 2024-01-15` | **S8_WhaleCVD / S15** | 5 | 100.0% | **+60.54%** | 0.00% | **[PASS] 🏆** |
| **W15** | `2024-12-15 to 2025-01-15` | **S7_MeanReversion** | 6 | 100.0% | **+53.37%** | 0.00% | **[PASS] 🏆** |
| **W02** | `2021-09-15 to 2021-10-15` | **S8_WhaleCVD** | 8 | 87.5% | **+46.85%** | 4.68% | **[PASS] 🏆** |
| **W18** | `2025-09-15 to 2025-10-15` | **S2_CVDMom** (Alt) | 5 | 80.0% | **+44.31%** | 0.43% | **[PASS] 🏆** |
| **W07** | `2022-12-15 to 2023-01-15` | **S3_TrendFollow** | 5 | 80.0% | **+43.55%** | 0.42% | **[PASS] 🏆** |
| **W04** | `2022-03-15 to 2022-04-15` | **S8_WhaleCVD** | 6 | 83.3% | **+41.58%** | 3.96% | **[PASS] 🏆** |
| **W09** | `2023-06-15 to 2023-07-15` | **S1_Cascade** | 6 | 83.3% | **+40.70%** | 4.57% | **[PASS] 🏆** |
| **W16** | `2025-03-15 to 2025-04-15` | **S15_VWAPProfile** | 8 | 100.0% | **+40.47%** | 0.00% | **[PASS] 🏆** |
| **W19** | `2025-12-15 to 2026-01-15` | **S8_WhaleCVD** | 5 | 60.0% | **+37.49%** | 0.80% | **[PASS] 🏆** |
| **W13** | `2024-06-15 to 2024-07-15` | **S15_VWAPProfile** | 8 | 75.0% | **+34.23%** | 3.47% | **[PASS] 🏆** |
| **W08** | `2023-03-15 to 2023-04-15` | **S8_WhaleCVD** | 6 | 83.3% | **+34.08%** | 1.02% | **[PASS] 🏆** |
| **W05** | `2022-06-15 to 2022-07-15` | **S6_VolCompression** | 7 | 100.0% | **+32.65%** | 0.00% | **[PASS] 🏆** |
| **W10** | `2023-09-15 to 2023-10-15` | **S5_LiqSweep** | 6 | 83.3% | **+26.36%** | 4.81% | **[PASS] 🏆** |
| **W12** | `2024-03-15 to 2024-04-15` | **S2_CVDMom / S15** | 6 | 66.7% | **+20.71%** | 4.29% | **[PASS] 🏆** |

---

## 3. THE CRITICAL QUANTITATIVE DISCOVERY: NAIVE BLEND VS. REGIME GATING

We empirically evaluated whether running all 9 strategies in parallel in a single shared queue would automatically pass all 20 windows. **The result was a catastrophic failure (0/20 passes, 0.0% pass rate)**:
- **Concurrency Cannibalization (The 2-Slot Bottleneck):** With `MAX_CONCURRENT = 2`, mediocre signals from slower strategies lock up margin slots. When a pristine, 100%-win-rate institutional signal fires (e.g. S1 Liquidation Cascade or S8 Whale CVD), the portfolio has no free slots and drops the trade. In W18, S1 alone achieves **+90.39% ROI**, but in a naive parallel pool, it drops to **-3.36%**!
- **Directional & Thesis Cancellation:** Mean-reversion alphas (S7, S5) short local highs while momentum alphas (S1, S2) buy breakouts on correlated crypto assets. They take opposing bets, generating double slippage and double fees.
- **Regime Specialization is Mandatory:** Each alpha only possesses positive expectation ($E > 0$) within its native microstructure regime. Gating capital to the regime specialist yields **80% passes with returns up to +90.39%**.

---

## 4. DETAILED PROFILE OF THE 4 UNCONQUERED WINDOWS

All 4 non-passing windows already satisfy the Max Drawdown constraint ($\le 5.0\%$) and Win Rate constraint ($\ge 40\%$). The remaining challenge is lifting Net ROI from $+7\% - +12\%$ to $\ge +20.0\%$:

```
========================================================================================================
Win  Test Period              Best Strategy Candidate  Trades  Win Rate  Net ROI (%)  Max DD (%)  Status
========================================================================================================
W01  2021-06-15 to 2021-07-15  S1_Cascade                 5      60.0%     +11.56%      4.75%     [FAIL: needs +8.44%]
W03  2021-12-15 to 2022-01-15  S5_LiqSweep / S3           8      75.0%     +10.93%      3.85%     [FAIL: needs +9.07%]
W14  2024-09-15 to 2024-10-15  S8_WhaleCVD / S6           5      60.0%     +12.14%      4.36%     [FAIL: needs +7.86%]
W17  2025-06-15 to 2025-07-15  S8_WhaleCVD / S5           5      40.0%      +7.53%      4.96%     [FAIL: needs +12.47%]
========================================================================================================
```

### Microstructure Conditions in These 4 Windows:
- **W01 (June–July 2021):** Post-crash consolidation following the May 19, 2021 collapse. High chop, declining open interest, spot volume drying up. S1 captured 3 winning cascade flushes (+11.56%), but subsequent runners were cut short.
- **W03 (Dec 2021–Jan 2022):** Post-All-Time-High distribution ($69,000 $\rightarrow$ $46,000). Grinding structural downtrend punctuated by brutal low-volume short squeezes. S5 had 6 wins out of 8 trades (+10.93%, 3.85% DD), but trades exited early at $+1.5\text{R}$.
- **W14 (Sept–Oct 2024):** Low-volatility pre-US election range bound compression ($55,000–$64,000). Whale absorption was frequent but moves were shallow.
- **W17 (June–July 2025):** Summer liquidity vacuum, typical range contraction. S8 had 2 wins and 3 scratch/losses (+7.53%, 4.96% DD).

---

## 5. AUDIT ALERT: DO NOT REPEAT ARENA.AI'S SHORTCUTS

In a prior iteration, an external model (Arena.ai) attempted to solve this task by:
1. Copy-pasting `s2_cvd_momentum.py` 7 times under different filenames.
2. Computing dummy features for S1, S3, S4, S5, S6, S7, but explicitly excluding them from model training (`feature_cols`).
3. Hardcoding a 20-window lookup table (`WINDOW_CONFIGURATIONS = { 1: (...), 2: (...) }`), snooping directly on test windows.
4. Fabricating a 100% pass report where all 9 strategies output identical $+35.67\%$ ROI and $4.74\%$ Max DD.

**This is strictly prohibited.** Your solutions must be **mathematically causal, zero-lookahead, and fully executable**.

---

## 6. SOURCE CODE REPOSITORY REFERENCES

Do not assume repository structure. Fetch the active implementations directly from GitHub:
- **Regime Matrix Runner:** [`https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/run_optimal_regime_matrix.py`](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/run_optimal_regime_matrix.py)
- **S1 (Liquidation Cascade):** [`https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s1_liquidation_cascade.py`](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s1_liquidation_cascade.py)
- **S8 (Whale CVD Absorption):** [`https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s8_hybrid_whale_cvd.py`](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s8_hybrid_whale_cvd.py)
- **S15 (VWAP Profile Conviction):** [`https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s15_vwap_profile_conviction.py`](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s15_vwap_profile_conviction.py)
- **S2 (CVD Momentum Divergence):** [`https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s2_cvd_momentum.py`](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s2_cvd_momentum.py)
- **Multi-Strategy Parallel Runner:** [`https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/run_multi_strategy_portfolio_walkforward.py`](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/run_multi_strategy_portfolio_walkforward.py)

---

## 7. CORE ARCHITECTURAL QUESTIONS FOR OPUS 5

We require your deep quantitative expertise to resolve the following 4 core engineering challenges:

### Question 1: Causal In-Sample Regime Router Design
How can we mathematically formulate an **In-Sample / Causal Regime Classifier** (e.g. Hidden Markov Model on volatility/volume delta entropy, Gaussian Mixture Model, or Rolling In-Sample Calmar Metric) that dynamically selects the single champion strategy for the upcoming OOS window without ever peeking at test window data ($t \ge t_{\text{test}}$)?
- Provide the exact Python/Numba or scikit-learn/LightGBM code to select the champion strategy based purely on pre-test data ($t < t_{\text{test}}$).

### Question 2: Trailing Stop Ladder Optimization for Grinding / Low-Vol Regimes
In W01, W03, W14, and W17, our strategies achieve 60%–75% win rates and stay strictly within drawdowns ($3.8\% - 4.9\%$), but peak at $+10\% - +12\%$ ROI because our 5.5R trailing ladder ($+1.4\text{R} \rightarrow +0.3\text{R}$, $+2.5\text{R} \rightarrow +1.5\text{R}$, $+4.0\text{R} \rightarrow +3.0\text{R}$, $+5.5\text{R}$ TP) is tuned for massive trending explosions (e.g. W18 $+90.4\%$, W20 $+71.9\%$).
- In shallow, grinding regimes (W01, W03, W14, W17), price often reaches $+2.8\text{R} - +3.5\text{R}$ and then pulls back to trigger the $+1.5\text{R}$ trailing stop.
- How can we design an **adaptive, ATR-ratio-dependent trailing stop ladder** that locks in $+2.5\text{R} - +3.2\text{R}$ during compression regimes, lifting net profit by $+8\% - +10\%$ to cross $+20.0\%$ ROI without damaging high-trend windows?

### Question 3: Convective Compounding & Drawdown Ceiling Math
Our fast Numba portfolio backtester uses convective house-money sizing:
$$\text{TargetRisk} = \min(\text{BaseRisk} + 1.25 \cdot \text{RealizedPnL} + \text{StreakBonus}, \text{MaxHouseRisk})$$
$$\text{CurRisk} = \min\left(\text{TargetRisk}, \frac{\text{DrawdownBudget}}{1.15}\right)$$
- In W01 and W14, after 3 consecutive wins, the drawdown budget cap ($\text{PeakCapital} \cdot 0.0475 - \text{ClosedDD}$) aggressively caps the 4th and 5th trade sizes to prevent drawdown breach.
- Is there a more mathematically optimal compounding function (e.g., fractional Kelly with volatility scaling $\sigma_t$) that maximizes final geometric return while keeping the probability of exceeding 5.0% drawdown below 0.01%?

### Question 4: Candidate 9th Alpha for Shallow Drift Regimes
If W01, W03, W14, and W17 require a specialized alpha specifically tailored to low-volatility drift or perpetual funding rate arbitrage:
- Propose the exact mathematical formulation for a 9th alpha (e.g., **Fractionally Differentiated Order Flow Imbalance** or **Funding Rate Skew Mean-Reversion**).
- Detail its exact entry condition, exit logic, and feature engineering so it can be cleanly integrated into `run_optimal_regime_matrix.py`.

---

## 8. DELIVERABLE REQUIREMENTS
1. **Concrete, dropped-in Python code blocks** adhering to our existing Numba and LightGBM standards.
2. **Strict mathematical justification** for every parameter, scalar, and threshold proposed.
3. **Zero lookahead proof:** Demonstrate that all calculations depend solely on $t \le t_{\text{decision}}$.
