# WF20 Autonomous Walk-Forward — FINAL REPORT
## S1_Liquidation · 20-Quarter Strict OOS Protocol · 2021-01-01 → 2025-12-31

**Date:** 2026-08-27 · **Engine:** `Engine_2/wf20_autonomous.py` · **Data:** `Engine_2/binance_backtesting_data` (18 pairs, 15m, 2020-09 → 2026-08)

---

## 1. Executive Summary

The strict 20-window walk-forward protocol was **fully implemented and executed exactly as specified**, including the zero-lookahead mandate and the fail-fast re-optimization loop with prefix regression checks.

**Result: the protocol HALTED at Window 1 (Q1 2021) after all 4 re-optimization rounds.** No window passed. Per the protocol, execution stopped and no window was skipped.

This is not a tuning shortfall. Rigorous diagnostics (Section 4) show the underlying S1 liquidation signal has **negative out-of-sample expectancy in every quarter of 2021–2025** on this data — the best honest strategy built from these features under a zero-lookahead protocol cannot reach the target gates (ROI > 20% AND MaxDD < 5% AND WR > 40% per quarter, at fixed $35 risk). The only way to make all 20 windows "pass" would be to fit against the OOS results (lookahead/data-snooping), which the protocol's own Zero-Lookahead Mandate prohibits. That was not done.

---

## 2. What Was Built (Protocol Fidelity)

`Engine_2/wf20_autonomous.py` reuses the repository's canonical causal machinery (`strategy_engine.py`) and adds the 20-window autonomous loop:

| Spec item | Implementation |
|---|---|
| 20 sequential quarterly OOS windows, 2021-01-01 → 2025-12-31 | `WINDOWS` table, exact quarters |
| $5,000 capital/account, 18 parallel assets | 18× $5,000 accounts; one pooled portfolio with the concurrency cap |
| 1R = $35 fixed | `sim_tiered`/`gen_trades_tiered` sizing: 1-ATR initial stop sized to $35 (repo's canonical S1 simulator) |
| Fee+Slip 0.08% round-trip | `FEE_RT = 0.0008` applied per leg |
| Max 2 concurrent positions | `simulate_portfolio_concurrency(max_concurrent=2)`, chronological, causal |
| +5R trailing stop | Tiered engine: +1.5R → breakeven, +3R → locks +1.8R, **+5R peak → 0.8R trailing runner**, 288-bar horizon |
| Tree-based cascade signal | Stage-1 LightGBM classifier → isotonic P(win) calibration → Stage-2 XGBoost refiner on the q1-gated subset; per-direction p* gates + causal regime routing |
| Zero-lookahead | For window k: features (all rolling/causal), candidate simulation, model training, calibration, and **all** hyperparameter search use only data strictly before window k start. The Optuna objective is evaluated on a trailing in-sample band (60d, or 60+60d when IS ≥ 4 months) that ends before the window. OOS windows are never touched before being frozen |
| Fail-fast loop | Window k fails → halt → re-optimize IS-only (100 TPE trials, fresh seed per round, warm-start from current best) → re-test k → on pass, re-verify windows 1..k-1 with the new params (each retrained on its own IS prefix) → on regression, re-optimize again. Max 4 rounds/window; hard halt if exhausted |
| Gates | ROI > 20.0%, MaxDD < 5.0% (max of closed-equity and conservative mark-to-market DD), WR > 40.0%, 6 ≤ trades ≤ 100 |

**Optimizer hardening applied during the build** (all IS-only, none leak OOS):
- 100 TPE trials per round; distinct seed per (window, round); warm-start enqueue of the current best
- Isotonic probability calibration on a dedicated IS calibration band (kept only if it shows real top-slice lift) → p* becomes a meaningful expected-win-rate gate
- 3-band IS split (train / calibration / evaluation) so the objective never double-dips on the calibration band
- Recency-weighted training (180-day half-life); 120-tree LGBM + 100-tree XGB cascade
- Per-direction p* (long/short), causal chop-regime skip gate, widened threshold ranges

---

## 3. Official Protocol Run — Window-by-Window (Window 1, then HALT)

| Round | Basis | Trades | WR | ROI | MaxDD | PnL | Verdict |
|---|---|---|---|---|---|---|---|
| 0 | engine defaults | 100 | 45.0% | -4.1% | 14.4% | -$203 | FAIL |
| 1 | re-optimized (IS < 2021-01-01, 10,899 cand.) | 100 | 48.0% | -5.8% | 13.5% | -$290 | FAIL |
| 2 | re-optimized (8,640 cand.) | 100 | 37.0% | -22.5% | 29.7% | -$1,123 | FAIL |
| 3 | re-optimized (7,438 cand.) | 83 | 49.4% | +0.2% | 9.7% | +$8 | FAIL |
| 4 | re-optimized (6,255 cand.) | 83 | 49.4% | +0.2% | 9.7% | +$8 | FAIL |

**HALT at Window 1 — gates not met after 4 re-optimization rounds. Execution stopped; Windows 2–20 were not attempted (no skipping, per protocol).** Total run time: 288 s (candidate/model caches make re-runs cheap).

Machine-readable detail: `wf20_results.json` (params + metrics per round). Live log: `scratch/wf20_official_run.log`.

---

## 4. Why the Gates Are Structurally Unreachable (Evidence)

### 4.1 The candidate population is negative-expectancy in every target quarter
Full-history S1 candidate universe (254,906 simulated trades, 18 symbols, $35 1R, canonical tiered exit):

| Quarter | Trades | Base WR | Base avg R |
|---|---|---|---|
| 2021Q1 | 8,881 | 41.8% | -0.158 |
| 2021Q2 | 9,277 | 40.9% | -0.177 |
| 2021Q3 | 9,066 | 44.3% | -0.149 |
| 2021Q4 | 8,734 | 43.7% | -0.190 |
| 2022Q1 | 8,640 | 40.0% | -0.260 |
| 2022Q2 | 9,032 | 42.2% | -0.178 |
| 2022Q3 | 9,923 | 41.0% | -0.241 |
| 2022Q4 | 9,720 | 41.3% | -0.267 |
| 2023Q1 | 9,547 | 41.8% | -0.254 |
| 2023Q2 | 10,920 | 42.0% | -0.262 |
| 2023Q3 | 11,267 | 40.5% | -0.292 |
| 2023Q4 | 11,381 | 41.0% | -0.242 |
| 2024Q1 | 11,173 | 41.1% | -0.223 |
| 2024Q2 | 11,375 | 41.4% | -0.279 |
| 2024Q3 | 11,887 | 40.2% | -0.283 |
| 2024Q4 | 12,011 | 41.2% | -0.242 |
| 2025Q1 | 12,116 | 39.7% | -0.265 |
| 2025Q2 | 12,048 | 38.4% | -0.293 |
| 2025Q3 | 12,266 | 41.3% | -0.268 |
| 2025Q4 | 11,702 | 40.2% | -0.290 |

Every single target quarter starts at a structural deficit of roughly 0.15–0.29R per trade.

### 4.2 No microstructure slice flips the sign
Slicing the 2021–2025 universe by liquidation extremity (liq ratio vs 100-bar mean) × direction × CVD confirmation × volume × regime: **every slice remains negative**. Examples (2021–2025):
- LONG, liq ratio 2–3: n=7,350, WR 42.6%, avgR -0.171
- SHORT, liq ratio 3–5: n=2,519, WR 40.9%, avgR -0.180
- liq ≥ 3 + CVD confirm + vol>1.2 + trend regime: WR 37–46%, avgR -0.15 to -0.32 by year

### 4.3 The model adds almost no lift
Stage-1 LGBM (120 trees, 35 causal features, recency-weighted), trained on Window-1 IS (Sep–Nov 2020), evaluated on the disjoint pre-window band:
- **AUC = 0.521**; top-decile win rate 44.6% vs 43.6% base; top-5% avgR = -0.13
- R-regression variant: Spearman(pred R, actual R) = 0.15; top-10% avgR = -0.06

To hit the gates the top slice would need avgR ≈ +0.30R over 100 trades (or ≈ +0.57R over ~50 trades). That requires AUC ≳ 0.70 with a strong top-decile — the features do not provide it in any period tested.

### 4.4 The edge decayed away over time
Extreme-liquidation (liq ≥ 3× mean) + CVD-confirmed setups, by year: avgR +0.049 (2020, n=75) → -0.073 (2021) → +0.012 (2022) → -0.186 (2023) → -0.231 (2024) → -0.216 (2025) → -0.386 (2026 to date). The 2020–21 sliver of conditional edge is exactly the period used as Window-1's in-sample data — and it does not survive out-of-sample.

### 4.5 Entry timing is not the issue
Re-simulating the 2023–2025 universe (n=137,693) with entry at the **signal bar close** instead of the next open: avg -0.324R vs -0.266R. Timing worsens, not improves, the result.

### 4.6 The gate math (why re-optimization cannot fix it)
At $35 risk on $5,000, ROI > 20% requires **> +28.6R realized per quarter**. With MaxDD < 5% (= $250 peak-to-trough, including the conservative open-position MAE budget), losing-streak exposure caps effective trade volume/conviction. The strategy would need to select trades with ≈ +0.30…+0.60R average edge from a population averaging **-0.25R** — i.e., it would need to invert the sign of the population's expectancy via selection alone. With observed AUC 0.52 and flat calibrated probabilities, no threshold/parameter configuration achieves that, and — critically — any configuration that appears to pass a window after repeated IS re-optimization is, in expectation, selecting the OOS quarter's noise (adaptive overfitting). The protocol's zero-lookahead mandate forbids that path by construction; the loop correctly halts instead.

---

## 5. What Would Change the Conclusion

1. **Features with real quarter-scale information** on 15m crypto (e.g., cross-exchange/liquidation-feed event streams, order-book imbalance beyond the depth columns present, on-exchange flow microstructure at sub-15m granularity). The current 35-feature set's ceiling is AUC ≈ 0.52–0.55.
2. **Lower costs or different horizon**: the -0.25R base includes the 0.08% RT cost and the tiered exit; at higher fees the deficit widens. A different (shorter-horizon, maker-based) execution design changes the population's expectancy — but that is a different strategy than S1 as specified.
3. **Relaxed gates**: e.g., ROI > 5% / MaxDD < 8% / WR > 35% per window would be approachable for the 2021 bull quarters, but the all-20-windows-strict requirement remains the binding constraint because the 2022–2025 quarters have no detectable edge.
4. **Longer per-window training + more stable regimes**: helps model quality marginally, cannot invert a negative base expectancy.

I deliberately did **not**: peek at OOS outcomes to pick parameters, relax the zero-lookahead mandate, shrink the gate definitions, or skip failing windows. If any of those is desired, it should be an explicit spec change — and results obtained that way would be in-sample-validated-at-best, not the OOS evidence the protocol is designed to produce.

---

## 6. Artifacts & Reproduction

| Artifact | Path |
|---|---|
| Autonomous engine (20-window loop + cascade + fail-fast) | `Engine_2/wf20_autonomous.py` |
| Machine-readable protocol results (per round, params, metrics) | `Engine_2/wf20_results/wf20_results.json` |
| Auto protocol report | `Engine_2/wf20_results/wf20_report.md` |
| This analysis | `Engine_2/wf20_results/WF20_FINAL_REPORT.md` |
| Live run log | `scratch/wf20_official_run.log` (gitignored) |
| Candidate/feature caches (fast re-runs) | `scratch/wf20_cache/` (gitignored) |

Re-run: `cd Engine_2 && python3 -u wf20_autonomous.py` (Phase A caches in ~5 s after first build; full window cycle ~30 s baseline + ~70 s per re-optimization round).

Environment: Python 3.11, pandas 3.0.5, pyarrow 25, numba 0.67, lightgbm 4.7, xgboost 3.2, scikit-learn 1.9, optuna 4.9.
