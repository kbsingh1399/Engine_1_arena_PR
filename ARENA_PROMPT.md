# STRICTLY CONTINUE — DO NOT STOP UNTIL 20/20 WINDOWS PASS

You passed Window 1. You halted correctly at Window 2. Now fix Window 2 and keep going. You are not done.

**Current verified state:**
```
W01 PASS | Tr=6, WR=66.7%, ROI=25.6%, MaxDD=2.4%
W02 FAIL | Tr=3, WR=66.7%, ROI=0.2%, MaxDD=3.9%
```

---

## WINDOW 2 ROOT CAUSE ANALYSIS

Window 2 (`2021-06-15 → 2021-07-15`) is the post-May-2021 crash period — compressed volatility, fewer liquidation events. Only **3 trades** cleared the concurrency filter. The ROI gate requires `>= 6 trades` with `ROI > 20.0%`. This is a **candidate starvation** problem — the meta-label threshold `p*` is eliminating too many valid candidates.

---

## REQUIRED FIX: SPARSE-WINDOW FALLBACK SELECTOR (CAUSAL ONLY)

When the meta-label filter produces fewer than 6 candidates for a given OOS window, you must apply a causal fallback using ONLY pre-window data:

### Algorithm (implement in `run_all_6.py`):

```python
candidates = tp[tp['prob'] >= bp].sort_values('entry_time')
candidates_after_concurrency = simulate_portfolio_concurrency(candidates, max_concurrent=2)

if len(candidates_after_concurrency) < MINTR:  # MINTR = 6
    # CAUSAL FALLBACK: relax threshold to pre-window validated minimum
    # Use lowest p* that maintained WR > 40% on the in-sample validation slice
    fallback_bp = max(0.30, bp - 0.15)  # floor at 0.30, step down 0.15
    candidates = tp[tp['prob'] >= fallback_bp].sort_values('entry_time')
    candidates_after_concurrency = simulate_portfolio_concurrency(candidates, max_concurrent=2)

# If still < 6, use chronological top-50 by signal conviction
if len(candidates_after_concurrency) < MINTR:
    candidates = tp.sort_values('prob', ascending=False).head(50).sort_values('entry_time')
    candidates_after_concurrency = simulate_portfolio_concurrency(candidates, max_concurrent=2)
```

This fallback is CAUSAL — it uses only the pre-window calibration slice to determine the fallback threshold. It does NOT use Window 2 outcomes.

---

## THE LOOP — YOU MUST EXECUTE THIS EXACTLY, DO NOT STOP

```
FOR k = 1 TO 20:
    
    STEP 1: Run Window k with current calibration
    
    IF any gate fails (Tr < 6, WR ≤ 40%, ROI ≤ 20%, MaxDD ≥ 5%):
        ── Diagnose the specific gate that failed
        ── Apply causal fix using ONLY data prior to ws_k
        ── Available fix levers (in order):
               1. Sparse-window fallback selector (threshold relaxation)
               2. Optuna seed trial augmentation (add deterministic anchor points)
               3. Model capacity adjustment (depth/learning_rate, in-sample validated)
               4. Concurrency slot adjustment (verify strict exit_t > entry_t)
        ── Re-run Window k
        ── Re-verify ALL windows 1 → k-1 still pass (no regression)
        ── Repeat until Window k passes
    
    LOG: "W{k:02d} PASS | Tr={n}, WR={wr:.1f}%, ROI={roi:.1f}%, MaxDD={dd:.1f}%"
    ADVANCE to k+1

FINAL: "S1_Liquidation: 20/20 WINDOWS PASSED ✅"
```

---

## NON-NEGOTIABLE CONSTRAINTS

| Constraint | Rule |
|---|---|
| OOS schedule | **FIXED** — do not alter the 2021-2026 dates |
| Calibration | **STRICTLY pre-window only** — no OOS leakage ever |
| Stopping condition | **Only `20/20 PASS`** — never stop early |
| Fix approach | **Always causal** — validate fixes on in-sample slice first |
| Regression check | **Always re-verify all prior windows** after any fix |

---

## WHAT YOU MUST NOT DO

- Stop at Window 2 and report failure. That is not a deliverable.
- Use Window 2 outcomes to pick thresholds. That is OOS leakage.
- Skip a window that fails and advance anyway.
- Change the OOS schedule dates.

---

## YOUR FINAL OUTPUT FORMAT

Only when all 20 windows pass consecutively:

```
W01 PASS | Tr=6,  WR=66.7%, ROI=25.6%, MaxDD=2.4%
W02 PASS | Tr=X,  WR=XX.X%, ROI=XX.X%, MaxDD=X.X%
W03 PASS | Tr=X,  WR=XX.X%, ROI=XX.X%, MaxDD=X.X%
...
W20 PASS | Tr=X,  WR=XX.X%, ROI=XX.X%, MaxDD=X.X%

S1_Liquidation: 20/20 WINDOWS PASSED ✅
```

Run `python -u run_all_6.py` after every fix iteration.
**Do not submit a PR or declare done until you have the above output.**
