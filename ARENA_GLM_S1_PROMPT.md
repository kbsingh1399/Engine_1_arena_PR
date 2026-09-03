# 🏛️ ARENA.AI & GLM-5 MASTER DIRECTIVE: STRATEGY S1 (FUNDING RATE MEAN REVERSION & BASIS ARBITRAGE)

> **Execution Paradigm**: 1-Strategy-at-a-time Structured Deep Engineering  
> **Target Strategy**: **Strategy S1: Funding Rate Mean Reversion & Basis Arbitrage**  
> **Repository Context**: https://github.com/kbsingh1399/Engine_1_arena_PR  
> **Master Rulebook**: https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/rules/AGENTS.md  
> **Session History**: https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/memory/session_chat_history.md  
> **Data Target**: `Engine_2/binance_backtesting_data/` (18 Binance Futures symbols, 2020–2026 15m continuous Parquet data, 57 institutional features)

---

## 🔴 MANDATORY PREREQUISITE: AGENTS.MD ENFORCEMENT RULES
Before generating any architecture or code, you MUST fetch and strictly adhere to:
👉 **`https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/rules/AGENTS.md`**

### Non-Negotiable Core Directives from AGENTS.md:
1. **Andrej Karpathy Coding Principles**:
   - **Think Before Coding**: State assumptions explicitly, identify tradeoffs, never assume silently.
   - **Simplicity First**: Minimum code that solves the problem. No single-use bloated abstractions or speculative features.
   - **Surgical Changes**: Every changed line must trace directly to the request.
   - **Goal-Driven Execution**: Define testable success criteria and loop until verified.
2. **Strict Zero-Lookahead & Causal ML Execution**:
   - Signal calculated at bar $t$ close $\to$ Fill executed at bar $t+1$ open.
   - 9 bps round-trip taker fees + 5 bps adverse stop slippage applied to every trade.
   - Intrabar adverse sequence enforced (lows before highs for longs, highs before lows for shorts).
3. **Strict In-Sample Walk-Forward Freezing (Part 8 of AGENTS.md)**:
   - **ZERO TEST-SET SNOOPING**: You are strictly prohibited from evaluating multiple hyperparameter combinations $(\tau, K, \text{base}, \text{direction})$ on the Out-Of-Sample test window (`oos_df`).
   - For every window $W_k$, all models and hyperparameters must be selected **strictly and exclusively on the 18-month In-Sample (IS) window** ($t_{\text{start}} - 18\text{m} \to t_{\text{start}} - 3\text{h}$).
   - The selected configuration must be **FROZEN** before touching $W_k$.
   - Window $W_k$ is simulated **EXACTLY ONCE** with the frozen parameters.
4. **Portfolio Constraints**:
   - Starting Capital: **$5,000 USD**.
   - Max Concurrent Open Positions: **2 simultaneous positions** across all 18 parallel symbols.
   - Minimum Target Floor: **$\ge +5.0R$** for winning runner trades (initial stop = $1.0R$, trailing ratchet floor locks $\ge +5.0R$ once MFE $\ge 5.0R$).

---

## 🛑 STRICT QUANTITATIVE GATES (NON-NEGOTIABLE CRITERIA PER WINDOW)

Every Out-Of-Sample window must independently and strictly satisfy ALL of the following criteria:

| Metric | Strict Threshold | Mathematical / Execution Enforcement |
|---|---|---|
| **Window Return (ROI)** | **$\ge +20.0\%$ per Window** | Minimum +$1,000 profit on $5,000 starting equity in every single 1-month window |
| **Window Win Rate** | **$\ge 40.0\%$ per Window** | Wins / (Wins + Losses) $\ge 0.40$ on closed trades |
| **Max Drawdown** | **$< 5.0\%$ (Target $< 4.75\%$)** | Drawdown from window equity peak must NEVER breach $5.0\%$ ($\le \$237.50$ on $\$5,000$) |
| **Per-Trade R-Multiple** | **$\ge +5.0R$ Target for Winners** | Every winning trade must capture $\ge 5.0R$ net profit. Initial stop = $1.0R$ (`max(sl_mult * ATR14, 0.65% * px)`). |
| **Trailing Stop Mandate** | **Trailing Stop Armed at 5R** | Trailing SL automatically engages the moment Maximum Favorable Excursion (MFE) hits $\ge +5.0R$, locking profit $\ge +5.0R$ and trailing upward |
| **Minimum Closed Trades** | **$\ge 5$ Trades per Window** | Window must have at least 5 closed trades (strictly $\ge 5$ trade opportunities) to ensure statistical significance |
| **Causal & Non-Biased** | **Zero Lookahead ($T \to T+1$)** | Strict zero-lookahead. Signal at bar $t$ close $\to$ filled at bar $t+1$ open. 9 bps taker fees + 5 bps adverse stop slippage. In-sample parameter freezing (NO test-set snooping/sweeping) |
| **Portfolio Concurrency** | **Max 2 Open Positions** | Max 2 simultaneous open positions across all 18 symbols |

---

## 🎯 MISSION: SOLVE STRATEGY S1 INDIVIDUALLY FIRST

We are taking a disciplined, 1-strategy-at-a-time approach. We are NOT blending, cross-subsidizing, or rushing all 9 strategies. We will solve and certify **Strategy S1: Funding Rate Mean Reversion & Basis Arbitrage** to perfection first.

### Strategy S1 Specification:
- **Core Premise**: Exploit extreme pricing dislocations between Binance Perpetual Futures and underlying spot prices, conditioned on institutional funding rates, annualized basis yields, and crowded retail sentiment.
- **Key Microstructure Signals Available in `binance_backtesting_data`**:
  - `funding_rate_pct`: 8-hour perpetual funding rate.
  - `basis_usd`: Difference between Futures Mark Price and Spot Index Price.
  - `funding_rate_annualized`: Annualized cost of carry.
  - `ls_ratio_top`: Top-trader long/short account ratio.
  - `taker_buy_vol_btc` vs. `taker_sell_vol_btc`: Aggressive market taker flow.
  - `open_interest_usd` & `oi_change_pct`: Leverage positioning expansion/unwinding.

---

## 🧠 ADVANCED MULTI-MODEL ENSEMBLE ARCHITECTURE FOR S1

Do NOT rely on a single LightGBM model or single random seed. Build an institutional multi-model stacking architecture:

```
[ 18-Month In-Sample Event Stream (Purged by 3h) ]
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
  [ LightGBM ]  [ CatBoost / ] [ Calibrated  ]
  (Classifier)    [ HistGB ]   [ Logistic / RF]
       │             │             │
       └─────────────┬─────────────┘
                     ▼
       [ Meta-Ensemble Stacking ]
       (Conviction Scoring P_ens)
                     │
                     ▼
  [ In-Sample Calibration Folds (CAL) ]
  (Select optimal τ*, K*, base* on IS only)
                     │
              [ FREEZE CFG* ]
                     │
                     ▼
  [ Out-Of-Sample Test Window W_k ]
  (Simulated EXACTLY ONCE with Frozen CFG*)
```

1. **Diverse Model Stack**:
   - Model A: LightGBM Classifier (fast gradient boosting with leaf-wise expansion).
   - Model B: Scikit-Learn `HistGradientBoostingClassifier` (or CatBoost / XGBoost) with balanced class weighting.
   - Model C: Calibrated Logistic Regression / Random Forest meta-scorer.
2. **Consensus Ranking**:
   - Blend out-of-fold probability estimates: $P_{\text{ens}} = 0.4 P_{\text{lgbm}} + 0.3 P_{\text{hgb}} + 0.3 P_{\text{meta}}$.
3. **In-Sample Parameter Selection (CAL Folds)**:
   - Split the 18-month IS into a training segment ($t_0 - 18\text{m} \to t_0 - 4\text{m}$) and a 4-month calibration segment ($t_0 - 4\text{m} \to t_0 - 3\text{h}$).
   - Evaluate candidate parameter grids across the in-sample calibration folds.
   - Lock the single champion configuration $(\text{model}^*, \text{variant}^*, \tau^*, K^*, \text{base}^*)$ before stepping into the OOS test window.

---

## 📊 THE 20 WALK-FORWARD OOS WINDOWS
The backtesting data spans 2020-09 to 2026-03 across 18 symbols (`ADAUSDT`, `AVAXUSDT`, `BNBUSDT`, `BTCUSDT`, `DOGEUSDT`, `DOTUSDT`, `ETHUSDT`, `LINKUSDT`, `LTCUSDT`, `NEARUSDT`, `SOLUSDT`, `SUIUSDT`, `TRXUSDT`, `UNIUSDT`, `XLMUSDT`, `XRPUSDT`, `PEPEUSDT`, `1000SHIBUSDT`).

Evaluate across the exact 20 Out-Of-Sample test slices (1 month test, 3-month step):
- W01: 2021-06-15 to 2021-07-15
- W02: 2021-09-15 to 2021-10-15
- W03: 2021-12-15 to 2022-01-15
- W04: 2022-03-15 to 2022-04-15
- W05: 2022-06-15 to 2022-07-15
- W06: 2022-09-15 to 2022-10-15
- W07: 2022-12-15 to 2023-01-15
- W08: 2023-03-15 to 2023-04-15
- W09: 2023-06-15 to 2023-07-15
- W10: 2023-09-15 to 2023-10-15
- W11: 2023-12-15 to 2024-01-15
- W12: 2024-03-15 to 2024-04-15
- W13: 2024-06-15 to 2024-07-15
- W14: 2024-09-15 to 2024-10-15
- W15: 2024-12-15 to 2025-01-15
- W16: 2025-03-15 to 2025-04-15
- W17: 2025-06-15 to 2025-07-15
- W18: 2025-09-15 to 2025-10-15
- W19: 2025-12-15 to 2026-01-15
- W20: 2026-03-15 to 2026-04-15

---

---

## 📦 DELIVERABLE FOR STRATEGY S1

### 🔴 MANDATORY PASS-BEFORE-DELIVERY PROTOCOL:
**You must deliver the complete standalone file (`run_real_S1_funding_arb.py`) ONLY ONCE it genuinely and independently passes all 20 Out-Of-Sample windows with STRICTLY ZERO LOOKAHEAD, NO FUTURE PEEKS, NO TEST-SET SNOOPING, AND NO SURVIVORSHIP/SELECTION BIAS.**

If a configuration does not pass all 20 windows honestly under In-Sample freezing, **do not cheat or sweep on OOS trades**—iterate on the feature interactions, the trade entry trigger, the risk-state machine, or the ensemble architecture until it genuinely passes!

### Deliverable File Specifications:
File Name: **`run_real_S1_funding_arb.py`**

1. **Standalone & Executable**:
   - Must be fully self-contained. Runs cleanly via:
     ```bash
     python run_real_S1_funding_arb.py --data "Engine_2/binance_backtesting_data"
     ```
2. **Strict Zero-Lookahead / Anti-Bias Guarantee**:
   - **No Future Peeking**: Signals at bar $t$ close $\to$ executed at bar $t+1$ open.
   - **No Test-Set Sweeping**: Zero evaluation of hyperparameter grids, directional filters, or threshold variations on `oos_df`.
   - **In-Sample Frozen Execution**: Hyperparameters $(\text{model}^*, \text{variant}^*, \text{dmode}^*, \tau^*, K^*, \text{base}^*)$ must be chosen strictly on the 18-month In-Sample block, printed to console, and executed on OOS **EXACTLY ONCE**.
   - **No Survivorship / Label Leakage**: Purged 3-hour boundary between IS and OOS.
3. **Comprehensive Scorecard Table**:
   - The script must print the complete 20-window scorecard (W01 to W20) displaying:
     - Window ID & Date Range
     - Window ROI (Must be $\ge +20.0\%$ in every window)
     - Max Drawdown (Must be $< 4.75\%$ in every window)
     - Win Rate (Must be $\ge 40.0\%$ in every window)
     - Closed Trades (Must be $\ge 5$ in every window)
     - Frozen In-Sample Parameters
     - Gate Status (`[PASS]`)
4. **Direct Delivery**:
   - Output the complete, un-truncated Python code of `run_real_S1_funding_arb.py` or push directly to git so we can run and verify it locally.
