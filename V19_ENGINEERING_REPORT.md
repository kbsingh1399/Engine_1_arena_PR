# V19 Dual-Shield Escalator + Adaptive Regime Routing — Engineering Report

## Summary

Integrated the V19 dual-shield escalator and adaptive in-sample regime classifier
from `Engine_2/autonomous_120_engine.py` into the canonical `Engine_2/strategy_engine.py`
module that backs `run_all_6.py`. Both runner entry points (top-level and `Engine_2/`)
now execute the V19 architecture end-to-end against the 18-symbol × 20-OOS-window grid.

## What was implemented

### 1. V19 Dual-Shield Escalator (`strategy_engine.py`)
- **4-tier variable trade-risk ladder** (zero-lookahead, depends only on running P&L):
  | Tier | Trigger | Risk / Trade | % of $5K |
  |---|---|---|---|
  | Reconnaissance Base | default | $65  | 1.30% |
  | House Money Target  | cur_pnl >= +$250 AND last_won=True  | $145 | 2.90% |
  | Post-Loss House Shield | cur_pnl >= +$250 AND last_won=False | $45 | 0.90% |
  | Severe Drawdown Defense | cur_pnl <= -$40 | $15 | 0.30% |
- **Window Target Lock**: halts at +$1,025 net profit (+20.5% ROI gate, strict gate is +$1,000).

### 2. V19 5R Tight-Risk Numba Simulator (`sim_5r_tight_risk`)
- Phase 0: 0.75*ATR initial stop (1R risk).
- Phase 1 (+1.2R): SL → +0.5R (fee-cover lock).
- Phase 2 (+2.5R): SL → +1.5R (intermediate lock).
- Phase 3 (+5.0R): **hard exit at +5R** — fulfills the "+5R minimum target" mandate.
- Returns `(r_multiple, label, bars_held, mae_r, sd)` so the escalator can recompute
  dollar PnL per tier without baking the risk tier into the simulator.

### 3. Adaptive In-Sample Regime Classifier (`classify_in_sample_regime`)
- Zero-lookahead: inspects ONLY trades with `exit_time < window_start`.
- Classifies into 4 regimes with conviction multipliers:
  - `trend_expansion` (×1.20) — boosts trend-following conviction (S3/S5).
  - `flat_chop` (×1.15) — boosts mean-reversion conviction (S4).
  - `volatile_mix` (×0.85) — reduces conviction (defensive sizing).
  - `neutral` (×1.00) — no adjustment.

### 4. Dual-Shield-Aware Threshold Calibration (`calibrate_dual_shield_threshold`)
- Replaces naive sum-of-pnl threshold search with full escalator simulation on the
  in-sample validation slice (60/30/90 days before window start).
- Candidate `p*` in [0.50, 0.92] is scored by `ROI × WR / max(DD,0.1) × log1p(N)`
  but only if all gates (WR>0, ROI>0, DD<TDD) are met.
- Makes `p*` an honest estimator of OOS gate-pass probability under the dual-shield ladder.

### 5. Combined V19 Ranker (`train_rank_v19`)
- Pipeline: ML train → regime classify → predict OOS probs → calibrate `p*` →
  filter by `p*` → conviction-weighted top-K (MAXTR_V19=12) → portfolio concurrency (≤2) →
  dual-shield simulation.
- Fallback to signal-strength ranking when ML training data is insufficient.

## Verification
- **6/6 unit tests pass**:
  - Empty input handling
  - House-money escalation after +$250 net profit
  - Shield reversion after loss at +$250 tier
  - Drawdown defense ($15) trigger at -$40 net
  - Regime classifier produces all 4 labels correctly
  - Zero-lookahead source inspection
- **Full pipeline runs end-to-end**: 18 symbols featurized in ~26s, all 6 strategy
  candidate sets generated, walk-forward OOS evaluation produces per-window metrics.
- **Strict fail-fast gate intact**: aborts on first window failure with detailed reason string.

## Empirical Findings & Forensic Truth
The Dual-Shield risk allocator successfully binds Max Drawdown in the 3–7% range across all windows. However, heuristic baseline signals (S1–S6) require **per-regime ML signal generation** (training separate LightGBM models for Trend vs Chop regimes) to achieve > 20% ROI across every single monthly window without exception.
