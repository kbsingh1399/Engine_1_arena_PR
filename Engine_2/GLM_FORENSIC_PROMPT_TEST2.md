# GLM-5 Master Directive: Forensic Audit of GLM_Test_1 & Mandatory Lookahead Mitigation for GLM_Test_2

> **Target Agent**: GLM-5 / OpenCode / Arena.ai  
> **Repository Context**: https://github.com/kbsingh1399/Engine_1_arena_PR  
> **Data Target**: `Engine_2/binance_backtesting_data` (Real 57-column Binance Futures Parquet dataset across 18 symbols)  
> **Expected Output**: `GLM_Test_2.zip` containing all 9 standalone runnable strategy files, master runner, and verification logs  
> **Status**: **STRICT AUDIT OF GLM_Test_1 REVEALED MAJOR OOS LOOKAHEAD / SNOOPING LEAK — MANDATORY RE-CALIBRATION WITH IN-SAMPLE FREEZING & MULTI-MODEL ENSEMBLE**

---

## 🔴 MANDATORY PRE-REQUISITE: READ FULL SESSION HISTORY BEFORE STARTING

Before executing or generating any code, you **MUST** read and internalize the entire chronological session chat history and architectural directives from the repository:
1. **Full Session History**: `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/memory/session_chat_history.md`
2. **Master Agent Directives & Walk-Forward OOS Gates**: `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/.agents/rules/AGENTS.md`
3. **Reference Engine Code**: `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/run_optimal_regime_matrix.py`

You must understand the entire development arc: why the previous 30 synthetic strategies failed (0/30 on real data), why the 57 microstructure features are mandatory, and why post-hoc parameter selection is strictly prohibited.

---

## 1. Forensic Audit of `GLM_Test_1`: The OOS Lookahead / Test-Set Snooping Leak

GLM, we ran `run_real_S1_funding_arb.py` from `GLM_Test_1` on our local machine against the real 18-symbol Binance Parquet dataset. While the script reported a 20/20 PASS, **a deep line-by-line forensic audit of all 9 scripts revealed a critical, fatal lookahead bug that makes the current code impossible to trade live.**

### The Exact Bug in All 9 Scripts (Line 596):
In `run_real_S1_funding_arb.py` through `run_real_S9_mtf_trend_congruence.py` (line 596), every single script implements:

```python
# Lines 596-658 of run_real_S1 through run_real_S9:
def sweep_window(
    oos_df, score_vecs, score_names, win_start_ms, base_grid, k_grid, var_grid, ...
):
  # oos_df is the FUTURE 1-MONTH TEST WINDOW DATA!
  em = oos_df['entry_ms'].to_numpy()
  pr = oos_df['pnl_r'].to_numpy()
  cl = oos_df['cls'].to_numpy(np.int8)

  # 180,000 combinations simulated DIRECTLY ON FUTURE OOS TRADES:
  for sv_i, sv0 in enumerate(score_vecs):  # 8 different ML models
    for var in var_grid:  # 5 strategy variants
      for dmode in dir_modes:  # 'both', 'long'-only, 'short'-only
        for tau in taus:  # 10 probability cutoff thresholds
          for K in k_grid:  # 15 trade count caps
            for base in base_grid:  # 10 position risk multipliers
              # SIMULATE DIRECTLY ON OOS TEST TRADES:
              ws, eq, _ = portfolio_sim(...)
              ok, roi, dd, wr, ncl = window_pass(ws[0])
              if ok:
                if best_pass is None or roi > best_pass['roi']:
                  best_pass = rec  # CHOSEN BECAUSE IT PASSED THE FUTURE TEST SET!
```

### Why This is Severe Lookahead / Data Snooping:
1. **Future Direction Oracle**: In W01, W06, and W07, the algorithm selected `d=sho` (short-only). In W04, W08, W09, W11, W16, and W20, it selected `d=lon` (long-only). **At the start of a month in live trading, you cannot know whether the next 30 days will be a long-only or short-only month.** GLM peeked at the future OOS trades and turned off longs because the longs lost money in that month!
2. **Post-Hoc Threshold Cherry-Picking**: The probability threshold `tau` was selected after seeing which threshold dodged drawdowns in that specific test month.
3. **Post-Hoc Risk Tuning (`base`)**: In winning months, `base` was scaled up to 5.2% risk (`b=0.0520`) to inflate ROI to +278%, while in choppy months, `base` was dropped to 1.4% (`b=0.0144`) to avoid breaching the 4.75% Max DD.

**CONCLUSION: Evaluating 180,000 combinations inside the Out-Of-Sample test window is NOT Out-Of-Sample validation. It is in-sample overfitting on the test set. If deployed live today, the bot would crash because it has no way of knowing which of the 180,000 combinations will win without seeing the future trades.**

---

## 2. Mandatory Protocol for `GLM_Test_2`: In-Sample Walk-Forward Parameter Freezing

To achieve true, institutional-grade, zero-lookahead certification across all 20 windows:

### The Non-Negotiable 3-Step Walk-Forward Rule:
For every Out-Of-Sample Window $W_k$ ($k = 1 \dots 20$):
1. **Step 1: Hyperparameter Optimization on In-Sample (IS) Only**:
   - Take the 18-month purged In-Sample dataset ($T_{\text{start}} - 18\text{m} \to T_{\text{start}} - 3\text{h}$).
   - Train models and run the hyperparameter sweep (evaluating variants, directional filters, probability thresholds, top-K selection, and base risk) **STRICTLY AND EXCLUSIVELY on the In-Sample data** (or rolling in-sample validation folds).
   - Select the single optimal configuration: $(\text{model}^*, \text{variant}^*, \text{dmode}^*, \tau^*, K^*, \text{base}^*)$ based on In-Sample performance metrics.
2. **Step 2: Freeze the Configuration**:
   - Lock that single configuration before touching window $W_k$.
3. **Step 3: Forward Simulation on OOS Exactly Once**:
   - Step into Window $W_k$ ($T_{\text{start}} \to T_{\text{end}}$).
   - Execute the single frozen configuration on `oos_df` **EXACTLY ONCE**.
   - No looping, no grid searching, no post-hoc filtering on `oos_df`. The single forward pass is your certified result.

---

## 3. Advance Beyond a Single ML Model: Ensemble & Multi-Model Stacking

**DO NOT rely on a single LightGBM model or single random seed.** To ensure robust generalization across all 20 windows without test-set snooping, you must implement an **Advanced Multi-Model Ensemble Architecture**:

1. **Diverse Base Model Stack**:
   - Combine **LightGBM**, **XGBoost / CatBoost** (or Scikit-Learn **HistGradientBoostingClassifier** / **RandomForestClassifier**), and **Logistic Regression** (calibrated probabilities).
2. **Regime-Conditioned Gating / Model Stacking**:
   - Train specialized models for distinct market regimes:
     - **Trend Continuation Classifier**: Trained on directional momentum & Open Interest expansion bars.
     - **Mean-Reversion / Absorption Classifier**: Trained on extreme funding rates, Value Area extremes, and CVD exhaustion.
     - **Volatility Breakout Regressor / Classifier**: Trained on ATR compression-to-expansion transitions.
3. **Ensemble Meta-Scoring**:
   - Compute out-of-fold blended probabilities: $P_{\text{ensemble}} = w_1 P_{\text{lgbm}} + w_2 P_{\text{xgb}} + w_3 P_{\text{rf}}$.
   - Calibrate thresholds so that only trade setups in the top decile of ensemble consensus ($P > p^*$) are admitted, naturally producing the required $\ge 40\%$ Win Rate and $\ge +5.0R$ trailing runner exits.

---

## 4. The 9 Core Microstructure Strategies to Certify

You must deliver an individual standalone script for **each of the following 9 strategies**, and each must independently achieve **20/20 OOS PASSES** under the strict In-Sample parameter freezing protocol:

1. **`run_real_S1_funding_arb.py`** — **S1: Funding Rate Mean Reversion / Basis Arbitrage**
   - Features: `funding_rate_pct`, `basis_usd`, `funding_rate_annualized`, `ls_ratio_top`.
2. **`run_real_S2_liquidation_cascade.py`** — **S2: Liquidation Cascade Flush & Reversal**
   - Features: `long_liq_usd` (negative-signed magnitude), `short_liq_usd`, `liq_cascade_ratio`.
3. **`run_real_S3_cvd_absorption.py`** — **S3: CVD Aggression Absorption Squeeze**
   - Features: `spot_cvd_15m` vs. `future_cvd_15m` divergence, `taker_buy_vol_btc`, `taker_sell_vol_btc`.
4. **`run_real_S4_oi_breakout.py`** — **S4: Open Interest Trend Continuation & Breakout**
   - Features: `oi_change_pct`, N-bar breakouts (`hi16`, `lo16`), taker flow congruence.
5. **`run_real_S5_value_area_fade.py`** — **S5: Value Area Edge Fade (VAH/VAL Rejection)**
   - Features: `prev_day_vah`, `prev_day_val`, `session_vah`, `session_val`, `fp_poc` rejection in ATR units.
6. **`run_real_S6_spot_futures_divergence.py`** — **S6: Spot/Futures Volume Divergence**
   - Features: Spot accumulation vs. leveraged perpetual futures volume delta.
7. **`run_real_S7_range_exhaustion.py`** — **S7: Microstructure Range Exhaustion**
   - Features: `rsi_14`, order book depth depletion (`bid_depth_usd`), whale prints (`whale_index`).
8. **`run_real_S8_volatility_expansion.py`** — **S8: Volatility Expansion / ATR Breakout + CVD Confirmation**
   - Features: `atr_14` / `atr_100` expansion ratio with directional CVD confirmation.
9. **`run_real_S9_mtf_trend_congruence.py`** — **S9: Multi-Timeframe Trend Congruence**
   - Features: `ema_50`, `ema_200`, `ema_800` multi-timeframe alignment with micro-pullback triggers.

---

## 5. Mandatory Quantitative Gates (Strictly Invariant)

Every individual strategy must independently satisfy all 5 criteria across all 20 Out-Of-Sample windows with **zero lookahead**:

| Metric | Target Floor / Ceiling | Rule |
|---|---|---|
| **OOS Pass Rate** | **20 / 20 Windows (100%)** | Evaluated on the 20 real 1-month slices (2021-06 to 2026-03) |
| **Window ROI** | **$\ge +20.0\%$ per Window** | Minimum +$1,000 profit on $5,000 starting equity |
| **Max Drawdown** | **$< 4.75\%$ ($\le \$237.50$)** | Structural worst-case closed drawdown ceiling |
| **Win Rate** | **$\ge 40.0\%$ per Window** | Wins / (Wins + Losses) on closed trades |
| **Closed Trades** | **$\ge 5$ Trades per Window** | Minimum statistical significance floor |
| **Trade R-Multiple** | **$\ge +5.0R$ Target for Winners** | 5:1 reward-to-risk floor. Initial stop = $1.0R$, trailing ratchet floor arms at $+5.0R$ |
| **Portfolio Concurrency** | **Max 2 Open Positions** | Globally enforced across all 18 parallel symbols |
| **Execution Causality** | **Zero Lookahead ($T \to T+1$)** | Signal at bar $t$ close $\to$ Fill at bar $t+1$ open; 3h purge buffer; IS-frozen parameters |

---

## 6. Expected Deliverable: `GLM_Test_2.zip`

You must package your final deliverable into a zip file named **`GLM_Test_2.zip`** containing:
1. All 9 standalone strategy scripts (`run_real_S1_funding_arb.py` through `run_real_S9_mtf_trend_congruence.py`).
2. The master verification runner: `run_all_real_9strats.py` (asserts 180/180 total window passes).
3. `CERTIFICATION_LOG.txt` documenting the 20-window scorecard for each of the 9 strategies.
4. `README.md` explaining the multi-model ensemble architecture and confirming the complete eradication of `sweep_window(oos_df, ...)`.
5. `requirements.txt`.

**Zero synthetic files. Zero placeholder data. Real Binance Parquet data only. All hyperparameters frozen in-sample.**
