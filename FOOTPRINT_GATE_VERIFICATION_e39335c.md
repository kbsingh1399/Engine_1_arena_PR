# Council Verification — 4 Blocking Gates @ `origin/main` `e39335c`

**Method:** read every changed file at `e39335c` and **executed the changed functions directly**
where the defect was logic-level. Network egress is blocked here, so the pipeline itself could not be
run end-to-end.

## SCORECARD

| Gate | Claim | Verdict |
|---|---|---|
| 1 — CLI decoupled | `--all-footprint` activates full window | ✅ **CLOSED** |
| 2 — Zero-fill closed | raises `RuntimeError` | ✅ **CLOSED** |
| 3 — Scale-invariant bins | ~3.5 bps + `fp_effective_bps` | ✅ **CLOSED** (verified numerically) |
| 4 — Microstructure semantics | diagonal / consecutive / floor / POC | ⚠️ **3 of 4 CLOSED — one real defect remains** |
| 5 — Table 2 auditor | validates ladder fields | ⚠️ **PARTIAL — gap check is vacuous** |

**Recommendation: fix one ~5-line defect (Gate 4b) and the vacuous gap check, then proceed.**
Everything else is genuinely closed.

---

## Gate 1 — CLOSED ✅

`run_historical_pipeline.py:105`:

```python
should_fetch_fp = (footprint_days > 0) or all_footprint
```

and L142 passes `require_footprint=all_footprint`. Your original command now works as intended.
Verified.

## Gate 2 — CLOSED ✅

`historical_metrics_processor.py:225-226`:

```python
if require_footprint:
    raise RuntimeError(f"[FATAL GATE 2] require_footprint=True but footprint_df is empty for {symbol}! Refusing to zero-fill dead features.")
```

The zero-fill path survives at L227-232 but is now reachable only when footprint data was *not*
requested, which is correct. Verified.

## Gate 3 — CLOSED ✅ and better than I specified

I recommended ATR-relative bins; you normalized to 3.5 bps of the **daily** median price instead.
That works, because `median_px` is computed inside `_process_daily_ticks` (L117) so the step is
recomputed every day. I ran your rounding ladder across a 50-million-fold price range:

| daily median px | bin step | effective bps | error |
|---|---|---|---|
| 0.0025 (DOGE 2020) | 1e-06 | 4.00 | +0.50 |
| 1.10 (SOL 2020) | 0.000385 | 3.50 | +0.00 |
| 314.39 (ETH 2020) | 0.11 | 3.50 | +0.00 |
| 4,941 (ETH peak) | 1.7 | 3.44 | −0.06 |
| 125,986 (BTC peak) | 45 | 3.57 | +0.07 |

The 267× (SOL) and 301× (DOGE) drift I measured is **eliminated** — bps stays within ±0.5 across the
entire history, and `fp_effective_bps` (L151) makes the residual observable per bar. Clean fix.

**One design consequence to record, not a defect:** because the grid is recomputed daily, `price_bin`
is **not comparable across days**. Intra-day and per-bar analysis (your §3 use case) is fine.
Multi-day volume profiles, developing POC, and cross-day absorption zones are not possible off this
table. If you ever need them, add a second, fixed symbol-level grid as a separate column.

## Gate 4 — 3 of 4 closed; one real defect

**✅ True diagonal** (L178-187) — structurally correct:

```python
ladder.sort_values(["open_time_ms", "bin_idx"], inplace=True)
ladder["s_vol_below"] = ladder.groupby("open_time_ms")["s_vol"].shift(1)
ladder["b_vol_above"] = ladder.groupby("open_time_ms")["b_vol"].shift(-1)
ladder["buy_imbalance"] = ((ladder["b_vol"] >= 3.0*max(s_vol_below,1e-4)) & (ladder["b_vol"] >= min_vol_floor))
```

**✅ Volume floor** (L175) — `min_vol_floor = max(total_vol_coin * 0.005, 0.05)`, applied to both
sides. Closes my Q1(c).

**✅ Exact POC** (L224) — `is_poc = (bin_idx == poc_bin_idx)` on integers. Closes my Q1(d).

**⚠️ 4b — "Consecutive" means consecutive *rows*, not consecutive *price levels*.**

`shift(1)` and the run-length walk both operate on adjacent **DataFrame rows** after
`sort_values(["open_time_ms","bin_idx"])`. When a bin is untraded it is simply absent, so rows that
are adjacent in the frame can be far apart in price. I ran your exact function:

```
bins 10,11,13 (bin 12 empty), all imbalanced -> stacked_buy_imbalances = 1
  TRUE consecutive price runs >= 3 : 0
  => FALSE POSITIVE across the gap: YES
```

The same defect hits the **diagonal**: with bins 10, 12, 13 populated, bin 12's `s_vol_below` is the
sell volume at bin **10** — two levels away — so the "P vs P−1" comparison silently becomes "P vs
P−2". Given that **12% of bars have ≤4 populated bins** (measured last round), gaps are common, not
rare.

Fix — require adjacency explicitly:

```python
ladder["bin_gap_below"] = ladder.groupby("open_time_ms")["bin_idx"].diff()
ladder["bin_gap_above"] = ladder.groupby("open_time_ms")["bin_idx"].diff(-1)
s_ok = (ladder["bin_gap_below"] == 1)      # previous row is exactly one level down
a_ok = (ladder["bin_gap_above"] == -1)
ladder["buy_imbalance"]  = ((ladder["b_vol"] >= 3.0*np.maximum(ladder["s_vol_below"].where(s_ok), 1e-4))
                            & (ladder["b_vol"] >= min_vol_floor)).astype(int)
ladder["sell_imbalance"] = ((ladder["s_vol"] >= 3.0*np.maximum(ladder["b_vol_above"].where(a_ok), 1e-4))
                            & (ladder["s_vol"] >= min_vol_floor)).astype(int)
```

and in `_calc_consecutive_stacked`, break the streak whenever the bin index is not exactly +1:

```python
def _calc_consecutive_stacked(imb, bins):
    runs = np.zeros(len(imb), dtype=np.int32); cur = 0
    for k in range(len(imb)):
        adj = (k > 0) and (bins[k] - bins[k-1] == 1)
        cur = cur + 1 if (imb[k] == 1 and (k == 0 or adj)) else (1 if imb[k] == 1 else 0)
        runs[k] = cur
    return int((runs >= 3).sum())
```

**⚠️ 4c — the return value is not a cluster count.** `(runs >= 3).sum()` returns
`Σ max(0, L−2)` over runs:

| input | returns |
|---|---|
| one run of 3 | 1 |
| one run of 5 | 3 |
| two separate runs of 3 | 4 |

So `stacked_buy_imbalances` is a *strength weight*, not "number of stacked clusters", and it is not a
boolean. That is a legitimate feature — but rename it (`stacked_buy_imb_strength`) or add a separate
`has_stacked_buy_imb` boolean, because a strategy author reading the current name will treat 3 as
"three clusters".

## Gate 5 — PARTIAL

`verification/verify_parquet_integrity.py:88-96` does validate `trade_count > 0`, `price_bin > 0`,
and `is_poc`/`is_buy_imbalance`/`is_sell_imbalance` ∈ {0,1}. Good, and the old `total_records`
counter bug is fixed (L102 now counts non-master files).

Three gaps:

1. **The ladder gap check is hardcoded to zero** (L73-78):
   ```python
   elif is_ladder and len(timestamps) > 1:
       time_diffs = np.diff(timestamps)
       num_gaps = 0                      # <- unconditional
       is_monotonic = bool(np.all(time_diffs >= 0))
   ```
   So the "0 Gaps [PASS]" in your Table 2 result is **vacuous** — it is assigned, not measured. A
   meaningful check is that the set of `open_time_ms` in the ladder is contiguous at 15m spacing
   (deduplicated), and that every master bar with `volume_base > 0` has ≥1 rung.
2. **No referential integrity check** between the two tables — the one I flagged last round.
3. **`bins_populated` is computed (L207) but never audited**, and it is not in the Table 2 export list
   (L226-229). Export it; it is the column that lets you discard degenerate bars.

---

## Claims vs the repository

| Claim | At `e39335c` |
|---|---|
| Table 1: 210,609 rows × 62 cols | committed ETHUSDT is **210,587 rows × 59 cols** |
| Table 2: 4,391 rungs × 9 cols | **no ladder table committed** (9-col list does match code L226-229) |
| "0 Gaps" on Table 2 | hardcoded `num_gaps = 0` — not measured |

Your local run is not in the repository, so I verified the **code**, not the artifacts. Note also that
4,391 rungs ÷ ETH's median 10.4 bins/bar ≈ **422 bars ≈ 4.4 days**. That is still far too small to
validate a 5-year schema; it cannot exercise the Gate 3 fix at 2020 prices, which is the exact
failure it was written to prevent. **Validate on at least one full year spanning a low-vol period and
a cascade before the 18-symbol run.**

## Still open from last round (unchanged, not a launch blocker for *extraction*)

`s1_liquidation_cascade.py` still never reads Table 2 — `grep -rln "bins_populated\|footprint_ladder"`
returns only the fetcher and the pipeline runner. The ladder is produced but not consumed. That is
correct sequencing (build the data first), but the 5R absorption work in my Q3 answer cannot begin
until the join exists, and the 32.3% break-even hit rate remains the target to validate against.

## Bottom line

**Gates 1, 2, 3 are closed and verified. Gate 4 needs the adjacency fix (4b) and a rename (4c).
Gate 5 needs a real gap check and referential integrity.** Fix 4b before the full extraction — it is
the only change that alters the *content* of the data you are about to spend 37,296 downloads
producing, and retrofitting it means re-running everything.
