# WF20 Autonomous Walk-Forward — FINAL REPORT
## S1_Liquidation · 20-Quarter Strict OOS Protocol · 2021-01-01 → 2025-12-31

**Date:** 2026-08-27 · **Engines:** `Engine_2/wf20_autonomous.py` (tree cascade) + `Engine_2/wf20_ensemble.py` (4-model voting ensemble) + `Engine_2/wf20_screen.py` (17-concept market universe) · **Data:** `Engine_2/binance_backtesting_data` (18 pairs, 15m, 2020-09 → 2026-08)

---

## 1. Executive Summary

The strict 20-window walk-forward protocol was **fully implemented and executed exactly as specified** — twice, with two different modeling approaches:

1. **V1 tree cascade** (LGBM → isotonic → XGB): **HALTED at Window 1** after all 4 re-optimization rounds.
2. **V2 broadened attack** (per request): a 17-concept causal market universe (407,983 candidate trades spanning liquidation cascades, funding squeezes, CVD divergence, OI surges, squeeze breakouts, deep pullbacks, flow imbalance, trend/momentum, MTF reversion/trend, etc.) scored by a **4-model voting ensemble — LightGBM + XGBoost + CatBoost + sklearn HistGBM** (mean P(win) vote, isotonic-calibrated on an IS-only band), run through the identical fail-fast zero-lookahead protocol: **also HALTED at Window 1** after 4 re-optimization rounds.

**Definitive result: 0 / 20 windows pass under the zero-lookahead mandate.** A clean single-OOS-test trajectory (Section 4.4) shows the binding constraint is the **ROI gate**: no window ever exceeds +5.1% ROI vs the required **>20%** (= +28.6R at fixed $35 risk). Even the *best* Window-1 configuration achievable by sweeping entry thresholds **with full hindsight on the OOS window** (itself a lookahead violation) reaches only **+0.8% ROI**. The gap is 25×, not a tuning gap.

This is not a matter of trying more models or more re-optimization rounds:

- The candidate population is **negative-expectancy in every quarter 2021–2025** (avg −0.15R to −0.29R per trade, WR 38–44%).
- **All 17 market concepts** (407,983 candidates) are negative on average across 2021–2025; no single concept is positive.
- Model lift (single model or 4-model ensemble) is AUC ≈ 0.52–0.55 — it cannot invert the sign of a −0.25R population via selection.
- Re-optimization that appears to "pass" a window after repeated IS rounds is, in expectation, selecting that quarter's noise (adaptive overfitting). The protocol's own zero-lookahead mandate forbids fitting against OOS, and the loop correctly halts instead of fabricating passes.

The only way to make all 20 windows "pass" is to fit against OOS outcomes (data snooping / lookahead). That was **not** done, and no window was skipped.

---

## 2. What Was Built (Protocol Fidelity)

Both engines reuse the repository's canonical causal machinery (`strategy_engine.py`, unmodified).

| Spec item | Implementation |
|---|---|
| 20 sequential quarterly OOS windows, 2021-01-01 → 2025-12-31 | `WINDOWS` table, exact quarters |
| $5,000 capital/account, 18 parallel assets | 18× $5,000 accounts; one pooled portfolio with the concurrency cap |
| 1R = $35 fixed | `sim_tiered`/`gen_trades_tiered` sizing: 1-ATR initial stop sized to $35 (repo's canonical S1 simulator) |
| Fee+Slip 0.08% round-trip | `FEE_RT = 0.0008` applied per leg |
| Max 2 concurrent positions | `simulate_portfolio_concurrency(max_concurrent=2)`, chronological, causal |
| +5R trailing stop | Tiered engine: +1.5R → breakeven, +3R → locks +1.8R, **+5R peak → 0.8R trailing runner**, 288-bar horizon |
| V1 signal | LGBM classifier → isotonic P(win) → XGBoost refiner; per-direction p* gates + causal regime routing |
| V2 signal | **17-concept causal universe** (frozen a priori, `wf20_screen.py`) scored by **LightGBM + XGBoost + CatBoost + HistGBM mean-vote ensemble** (44 features: 35 causal microstructure + 6 MTF + concept + symbol id), isotonic-calibrated on IS-only band; per-direction p* gates + causal regime routing |
| Zero-lookahead | For window k: features (all rolling/causal), candidate simulation, model training, calibration, and **all** hyperparameter search use only data strictly before window k start. The Optuna objective is evaluated on a trailing IS band ending before the window. OOS windows are never touched before being frozen. The concept universe is frozen before any window is tested |
| Fail-fast loop | Window k fails → halt → re-optimize IS-only (120 TPE trials, fresh seed per round, warm-start from current best) → re-test k → on pass, re-verify windows 1..k-1 with the new params (each retrained on its own IS prefix) → on regression, re-optimize again. Max 4 rounds/window; hard halt if exhausted |
| Gates | ROI > 20.0%, MaxDD < 5.0% (max of closed-equity and conservative mark-to-market DD), WR > 40.0%, 6 ≤ trades ≤ 100 |

---

## 3. Official Protocol Runs

### 3.1 V1 cascade — HALT at Window 1

| Round | Basis | Trades | WR | ROI | MaxDD | PnL | Verdict |
|---|---|---|---|---|---|---|---|
| 0 | engine defaults | 100 | 45.0% | -4.1% | 14.4% | -$203 | FAIL |
| 1 | re-optimized (IS < 2021-01-01) | 100 | 48.0% | -5.8% | 13.5% | -$290 | FAIL |
| 2 | re-optimized | 100 | 37.0% | -22.5% | 29.7% | -$1,123 | FAIL |
| 3 | re-optimized | 83 | 49.4% | +0.2% | 9.7% | +$8 | FAIL |
| 4 | re-optimized | 83 | 49.4% | +0.2% | 9.7% | +$8 | FAIL |

### 3.2 V2 four-model ensemble — HALT at Window 1

| Round | Basis | Trades | WR | ROI | MaxDD | PnL | Verdict |
|---|---|---|---|---|---|---|---|
| 0 | ensemble defaults (p*=0.55) | 29 | 51.7% | +4.2% | 2.9% | +$211 | FAIL (ROI) |
| 1 | re-optimized (pL .47 / pS .69, chop-skip, d6/d5) | 100 | 46.0% | -1.0% | 13.9% | -$52 | FAIL |
| 2 | re-optimized (pL .46 / pS .55, d3/d5) | 100 | 40.0% | -12.8% | 21.7% | -$641 | FAIL |
| 3 | re-optimized | 100 | 40.0% | -12.8% | 21.7% | -$641 | FAIL |
| 4 | re-optimized (converged) | 100 | 40.0% | -12.8% | 21.7% | -$641 | FAIL |

Note the visible failure mode: to chase the ROI gate the optimizer pushes the probability gate **down** (more trades), which immediately bleeds the WR and DD gates — the extra trades come from the negative-expectancy tail. Round 0 (strict selection, 29 trades) is the best honest configuration and still sits 5× short on ROI with 17–29 trades.

Machine-readable: `wf20_results/wf20_ensemble_results.json`. Live log: `scratch/wf20_ensemble_run.log`.

---

## 4. Why the Gates Are Structurally Unreachable (Evidence)

### 4.1 The candidate population is negative-expectancy in every target quarter
Full-history S1 candidate universe (254,906 simulated trades, 18 symbols, $35 1R, canonical tiered exit) — base avgR by quarter ranges **−0.158 (2021Q1) to −0.293 (2025Q2)**, WR 38–44% every quarter. (Full table retained in `WF20_FINAL_REPORT` v1, git history.)

### 4.2 No microstructure slice flips the sign
Slicing 2021–2025 by liquidation extremity × direction × CVD × volume × regime: **every slice remains negative** (e.g., LONG liq-ratio 2–3: n=7,350, WR 42.6%, avgR −0.171; SHORT 3–5: n=2,519, WR 40.9%, avgR −0.180).

### 4.3 No market concept flips the sign (17-concept screen, 407,983 candidates)
`wf20_screen.py` built a frozen a priori universe of 17 causal concepts (liquidation cascade, liquidation extreme, funding squeeze, CVD divergence, OI surge, squeeze breakout, deep pullback, flow imbalance, long/short extreme, trend momentum, volume expansion, CVD momentum, RSI extreme, funding×CVD, BTC confirmation, MTF reversion, MTF trend, range position). **Pooled per-quarter avgR is negative in every quarter of 2021–2025 (−0.18 to −0.31).** Per-concept 2021–2025 averages (all negative):

| Concept | avgR 2021–25 | Concept | avgR 2021–25 |
|---|---|---|---|
| liq_cascade | -0.235 | funding_cvd | -0.288 |
| oi_surge | -0.223 | btc_confirm | -0.303 |
| ls_extreme | -0.218 | rsi_extreme | -0.326 |
| vol_expansion | -0.207 | trend_mom | -0.341 |
| cvd_divergence | -0.240 | squeeze_breakout | -0.396 |
| funding_squeeze | -0.274 | flow_imbalance | -0.724 |
| deep_pullback | -0.278 | cvd_momentum | -0.279 |

Isolated positive cells exist (e.g., trend_mom 2021Q3 +0.125, funding_cvd 2021Q3 +0.582, btc_confirm 2025Q2 +0.279) — but by definition they can only be selected with hindsight; a zero-lookahead rule cannot exploit them without overfitting to them.

### 4.4 Definitive zero-lookahead trajectory — 0/20 windows pass
Each window: ensemble trained on IS-only (default params, single OOS test, no re-optimization, no OOS peeking):

| W | Quarter | Trades | WR % | ROI % | MaxDD % | PnL $ | Failing gates |
|---|---|---|---|---|---|---|---|
| 1 | 2021Q1 | 29 | 51.7 | +4.2 | 2.9 | +211 | ROI |
| 2 | 2021Q2 | 1 | 0.0 | -0.7 | 0.7 | -37 | ROI, WR |
| 3 | 2021Q3 | 2 | 50.0 | -0.4 | 0.7 | -19 | ROI |
| 4 | 2021Q4 | 50 | 44.0 | -7.5 | 9.0 | -374 | ROI, DD |
| 5 | 2022Q1 | 43 | 62.8 | +4.4 | 4.0 | +220 | ROI |
| 6 | 2022Q2 | 22 | 50.0 | +5.1 | 4.7 | +255 | ROI |
| 7 | 2022Q3 | 63 | 38.1 | -12.3 | 12.7 | -617 | all three |
| 8 | 2022Q4 | 65 | 38.5 | -11.6 | 18.5 | -578 | all three |
| 9 | 2023Q1 | 23 | 39.1 | -1.1 | 5.0 | -56 | ROI, WR |
| 10 | 2023Q2 | 89 | 52.8 | -6.5 | 13.0 | -322 | ROI, DD |
| 11 | 2023Q3 | 10 | 30.0 | -4.0 | 5.0 | -198 | ROI, WR |
| 12 | 2023Q4 | 39 | 48.7 | -2.9 | 6.7 | -145 | ROI, DD |
| 13 | 2024Q1 | 0 | — | — | — | — | (no qualifying trades) |
| 14 | 2024Q2 | 3 | 0.0 | -2.3 | 2.3 | -115 | ROI, WR |
| 15 | 2024Q3 | 65 | 46.2 | -4.4 | 11.9 | -219 | ROI, DD |
| 16 | 2024Q4 | 9 | 55.6 | +1.3 | 2.2 | +64 | ROI |
| 17 | 2025Q1 | 27 | 51.9 | +2.9 | 4.7 | +144 | ROI |
| 18 | 2025Q2 | 0 | — | — | — | — | (no qualifying trades) |
| 19 | 2025Q3 | 0 | — | — | — | — | (no qualifying trades) |
| 20 | 2025Q4 | 9 | 44.4 | -2.8 | 2.9 | -141 | ROI |

**Passed: 0/20.** Gate by gate: ROI >20% met in **0/20** windows (best +5.1%); MaxDD <5% in 11/20; WR >40% in 9/20. The ROI gate alone is sufficient to sink every window, and it is the only gate that is far from being met (DD and WR are often close).

### 4.5 Window-1 gap diagnostic (the ceiling, with cheating)
With the IS-trained ensemble fixed, sweeping the entry probability threshold across OOS Q1-2021 **using hindsight on the OOS window** (i.e., a deliberate lookahead violation, used only to measure the ceiling):

| thr | n | WR % | ROI % | MaxDD % | PnL $ |
|---|---|---|---|---|---|
| 0.30 | 100 | 45.0 | -9.7 | 13.1 | -482 |
| 0.35 | 100 | 43.0 | -11.8 | 12.4 | -589 |
| 0.40 | 100 | 43.0 | -16.7 | 19.1 | -835 |
| 0.45 | 100 | 45.0 | -6.0 | 19.9 | -302 |
| 0.50 | 100 | 51.0 | +0.2 | 7.1 | +10 |
| 0.55 | 17 | 52.9 | **+0.8** | 4.1 | +41 |
| ≥0.60 | 0 | — | — | — | — |

**Even with full OOS hindsight, the best Window-1 result is +0.8% ROI** (vs >20% required). The 25× gap is structural, not parametric.

### 4.6 The edge decayed away over time
Extreme-liquidation (liq ≥ 3× mean) + CVD-confirmed setups, by year: avgR +0.049 (2020) → -0.073 (2021) → +0.012 (2022) → -0.186 (2023) → -0.231 (2024) → -0.216 (2025) → -0.386 (2026 ytd). The only sliver of conditional edge (2020–21) is exactly the period used as Window-1 IS data — it does not survive OOS.

### 4.7 Entry timing is not the issue
Re-simulating the 2023–2025 universe (n=137,693) with entry at the **signal bar close** instead of the next open: avg −0.324R vs −0.266R. Timing worsens the result.

### 4.8 The gate math (why no amount of re-optimization fixes it)
At $35 risk on $5,000, ROI > 20% requires **> +28.6R realized per quarter** (≈ +0.29R average per trade across 100 trades). MaxDD < 5% (=$250 peak-to-trough, incl. open-position MAE) caps loss-streak exposure. The strategy would need to select ≈ +0.30…+0.60R average edge from a population averaging **−0.25R** — inverting the sign of the population via selection alone. Observed AUC ≈ 0.52 (single model) and the ensemble's calibrated probabilities do not provide the top-slice lift for this. Any configuration that "passes" after repeated IS re-optimization rounds is, in expectation, selecting the OOS quarter's noise; the zero-lookahead mandate forbids that path by construction, so the loop halts honestly.

---

## 5. What Would Change the Conclusion

1. **Features with real quarter-scale information** (cross-exchange liquidation event streams, sub-15m order-book imbalance, maker/taker flow at tick level). The current feature ceiling is AUC ≈ 0.52–0.55. Kronos (K-line foundation model) could not be evaluated in this sandbox: HuggingFace and the PyTorch weight index are network-blocked here; its weights (Kronos-mini 4.1M params, ctx 2048) require ~1 GB of downloads from blocked hosts. If desired, a ready-to-run integration script can be generated for the local machine where network access exists.
2. **Lower costs / different execution**: the −0.25R base includes 0.08% RT fees + the tiered exit. Maker-based or shorter-horizon execution changes the population's expectancy — but that is a different strategy than S1 as specified.
3. **Relaxed gates**: e.g., ROI > 5% / MaxDD < 8% / WR > 35% would let several quarters pass (W1, W5, W6, W16, W17 pass ROI>5% at ≤4.7% DD in the trajectory above), but "all 20 windows simultaneously at the stated gates" remains unachievable because the 2022–2024 quarters carry no detectable edge.
4. **Explicit opt-in to lookahead-fitting**: parameters could be fit on the full 2021–2025 sample to make windows pass — results would be in-sample at best, the protocol's mandate would be void, and no honest OOS claim could be made. Available on request; not done.
5. **New data** (funding history is present; missing: L2 depth history — the depth_imbalance concept was infeasible because the futures depth columns are empty).

I deliberately did **not**: peek at OOS outcomes to pick parameters (the Section 4.5 sweep is reported as a *ceiling diagnostic*, explicitly labeled as lookahead, and was never fed back into the protocol), relax the zero-lookahead mandate, shrink the gate definitions, or skip failing windows.

---

## 6. Artifacts & Reproduction

| Artifact | Path |
|---|---|
| V1 autonomous engine (20-window loop + cascade + fail-fast) | `Engine_2/wf20_autonomous.py` |
| 17-concept causal universe builder | `Engine_2/wf20_screen.py` |
| V2 4-model ensemble engine (LGBM+XGB+CatBoost+HistGBM, same protocol) | `Engine_2/wf20_ensemble.py` |
| Machine-readable V1 protocol results | `Engine_2/wf20_results/wf20_results.json` |
| Machine-readable V2 protocol results | `Engine_2/wf20_results/wf20_ensemble_results.json` |
| Auto reports | `Engine_2/wf20_results/wf20_report.md`, `wf20_ensemble_report.md` |
| This analysis | `Engine_2/wf20_results/WF20_FINAL_REPORT.md` |
| Caches (states, candidates, 407,983-row concept universe) | `scratch/wf20_cache/` (gitignored) |
| Run logs | `scratch/wf20_official_run.log`, `scratch/wf20_ensemble_run.log` (gitignored) |

Re-run: `cd Engine_2 && python3 -u wf20_autonomous.py` (~5 min incl. re-opts) or `python3 -u wf20_ensemble.py` (~3 min to Window-1 halt; 120-trial re-optimization ≈ 35–40 s each).

Environment: Python 3.11, pandas 3.0.5, pyarrow 25, numba 0.67, lightgbm 4.7, xgboost 3.2, catboost 1.2.10, scikit-learn 1.9, optuna 4.9.
