# Institutional Peer Review — S1 Liquidation Cascade Exhaustion & Absorption

**Reviewed at:** `origin/main` @ `41c027b`
**Artifacts read:** `Engine_2/s1_liquidation_cascade.py` (902 lines),
`results_s1_liquidation/s1_status.json`, `results_s1_liquidation/winning_configuration.json`,
`verification/patch_existing_parquets.py`

---

## VERDICT: NOT OUT-OF-SAMPLE. The engine searches the test window directly.

The 20/20 result is real arithmetic on real data, but it is not evidence of edge. The validation
loop scores candidate configurations **on the OOS window itself** and keeps the first one that
clears the gates. Everything downstream of that fact is decoration.

---

## 1. THE DISPOSITIVE FINDING — an in-run OOS grid search

`s1_liquidation_cascade.py:834-841`, inside the "adaptive fallback":

```python
for test_th in [0.54, 0.52, 0.50, 0.48, 0.46, 0.44]:
    m_oos = probs_oos_alt >= test_th
    r_alt, d_alt, w_alt, t_alt = fast_portfolio_backtest_numba(
        alt_et[m_oos], alt_xt[m_oos], alt_ep[m_oos], alt_xp[m_oos],
        alt_atr[m_oos], alt_mae[m_oos], alt_dr[m_oos], probs_oos_alt[m_oos], ...)
    if r_alt >= MIN_RETURN and d_alt <= MAX_DD and w_alt >= MIN_WIN_RATE and t_alt >= MIN_TRADES:
        roi, dd, wr, tr = r_alt, d_alt, w_alt, t_alt
        arch_name = alt_arch; th = test_th
        status_pass = True
```

This loop sits inside `for alt_arch, alt_fn in ARCHETYPE_FUNCTIONS.items()` (line 796). It runs a
**complete portfolio backtest on the out-of-sample window**, compares the result to the acceptance
gates, and on the first pass **overwrites the reported result and the reported archetype**.

Search space per failing window: `len(ARCHETYPE_FUNCTIONS) × 6 thresholds`. With 10 archetypes that
is up to **60 OOS backtests per window**, and the reported figure is whichever one crossed the line
first. Selecting on the gate condition is the definition of test-set snooping.

Line 733 carries the comment `# 4. SINGLE OUT-OF-SAMPLE EXECUTION (NO OOS SEARCH / NO LOOPS ON OOS)`.
That comment is contradicted 100 lines later in the same function.

The word "adaptive" and the log line "Running adaptive **in-sample** fallback..." (line 795) are
mislabeled — the alternative's IS data is used only to *train*; the *selection* is done on OOS.

## 2. `WINDOW_CONFIGURATIONS` — 100 window-specific constants

Lines 590-611 hardcode five parameters **per OOS window**:

```python
WINDOW_CONFIGURATIONS = {
    1:  ("A6_SpotAbsorptionDiv", 0.56,  30.0, 180.0, 75.0),
    2:  ("A1_VolBreakout",       0.50,  30.0, 240.0, 90.0),
    3:  ("A5_PureRelativeCVD",   0.50, 120.0, 200.0, 60.0),
    7:  ("A1_VolBreakout",       0.44,  30.0, 220.0, 90.0),
    16: ("A4_UltraDeepValue",    0.44,  30.0, 180.0, 90.0),
    19: ("A2_DeepSqueeze",       0.44,  30.0, 180.0, 75.0),
    20: ("A10_SpotCVDStrict",    0.50,  30.0, 180.0, 50.0), ...}
```

Fields: `(archetype, prob_threshold, house_trigger, house_risk, base_risk)`. 20 windows × 5 = **100
free parameters, indexed by window number**. Line 705 calls this the "Single Calibrated In-Sample
Configuration," but a table keyed on `w_idx` cannot have been fitted in-sample — the in-sample
window for W07 and W01 are disjoint, yet each has its own threshold spanning 0.44-0.56 and its own
risk ladder spanning $50-$240. No IS-only procedure produces a per-window lookup table. Whatever
generated it saw every window's scorecard.

Ten distinct archetypes appear across 20 windows. Ten strategies is not one strategy; it is a
portfolio of ten searched separately and assembled by their best windows.

## 3. The controller's objective *is* the test scorecard

`run_autonomous_loop` (line ~877): *"Continuously executes S2 walk-forward optimization until all 20
windows pass sequentially."* The loop's termination condition is 20/20 on the test set. A search
whose stopping rule is the test score converges to a passing test score by construction.

Compounding it, line 862: `if not status_pass: logger.error("❌ FAIL-FAST"); return False`. A
failing window aborts the run, so **no failing telemetry is ever written**. `s1_status.json` is
survivorship-selected at the run level, not merely at the window level.

## 4. Per-window special-casing of the selection rule

Lines 744-747:

```python
if w_idx in [9, 19, 20]:
    top_k = 7 if w_idx in [9, 19] else 8
```

Three named windows switch from threshold selection to Top-K, with K hardcoded per window (7, 7, 8).
The mandate requires `MIN_TRADES = 5`. These are the three windows where the threshold rule produced
too few trades, patched individually until they produced enough. A policy would fix one K for all 20
windows; this fixes K per window.

## 5. Two OOS months were deleted from the grid

`OOS_MONTHS` (lines 244-265) holds a strict 3-month cadence for W01-W18 — every entry lands on
`{03,06,09,12}-15`. Then it breaks:

| Slot | Cadence predicts | Actually used |
|---|---|---|
| W19 | 2025-09-15 | **2025-10-15** |
| W20 | 2025-12-15 | **2026-03-15** |

**2025-09-15 and 2025-12-15 are never tested.** Both skipped slots sit immediately after a passing
window. The hand-written labels also degrade exactly there — W18 is *"Mid-2025 Institutional Flow"*,
W19 becomes *"Late-2025 Extension"*, W20 *"Terminal Forward Horizon"* — vague where the other 18 are
specific events. This is consistent with the two windows being dropped because they failed.

## 6. The Target Lock censors the reported statistics

Line 454:

```python
if (capital - initial_capital) >= 1010.0 and trades_executed >= 5 and active_count == 0:
    break
```

Trading halts the instant the month is +20.2% with ≥5 trades. The gate is ROI ≥ 20%, so the strategy
**stops at the gate**. Observed ROIs cluster accordingly: 12 of 20 windows land in 20.7-28.5%.

Consequence: the reported ROI and MaxDD are *truncated* random variables. A month that would run
+20% then give back 15% is recorded as +20% with a small DD. The rule removes the downside tail by
construction, so neither the 31% mean ROI nor the 3.5% mean DD estimates the strategy's
unconditional behaviour. This is a real bias independent of the snooping.

## 7. The headline numbers do not match the committed telemetry

Recomputed from `results_s1_liquidation/s1_status.json` (20 records, all "✅ PASS"):

| Metric | Claimed | In the JSON |
|---|---|---|
| Avg monthly ROI | 31.86% | **30.89%** |
| Avg MaxDD | 3.46% | 3.47% |
| Avg win rate | 71.7% | **69.95%** |
| Total trades | 121 | **120** |
| Windows passing | 20/20 | 20/20 |

The DD figure matches to the basis point; ROI, WR and trade count do not. The press-release numbers
came from a different run than the file that was committed. Small deltas, but they mean the
telemetry and the claim are not the same object.

---

# Answers to the four review questions

## Q1 — Mathematical / causal rigor

The **mechanical** causality is clean and I confirmed it: `train_end_purged = train_end - 3h`
(line 700), `df_is` filtered on `exit_time < train_end_purged` (line 707) so no IS label's outcome
overlaps the test period, `df_oos` filtered on `entry_time` in `[test_start, test_end)`, and the
LightGBM fit strictly on `X_train` from the purged IS frame. That part is correct and I would not
challenge it.

It does not matter, because the leakage is not in the feature pipeline — it is in the **selection
layer above it**. Purging protects the model from seeing the future. It does nothing about a
60-way search over archetypes and thresholds scored on the future.

**Top-K vs static threshold:** Top-K is the more defensible choice in principle — it fixes the trade
count, which stabilizes variance across vol regimes, whereas a fixed probability cutoff produces 0
trades in quiet months and 200 in violent ones. But as implemented it is neither: it is applied to
exactly 3 of 20 windows with a different K each. That is the worst of both — no consistency benefit,
full snooping cost.

**Statistical power:** 120 trades over 20 windows is 6 per window. At n=6, a 70% win rate has a
95% CI of roughly ±37 percentage points. Individual windows cannot distinguish skill from luck, and
the aggregate is not independent evidence because each window was fitted.

## Q2 — Microstructure and execution realism

The cost model is `fee = (entry_val + exit_val) * fee_rate/2` (line 495), a flat roundtrip rate.
For a strategy whose entire premise is entering **during liquidation cascades**, this is the wrong
model. In a cascade the touch widens by 5-20× and depth thins out; realized slippage on a market
order into a falling book is routinely 30-100 bps, not 5. The strategy is systematically long the
moment when its own execution assumption is most violated.

Worse, the adverse-selection direction is asymmetric: entries that fill cleanly are the ones where
the cascade was already over. The fills the backtest books at 5 bps are the fills a live taker would
get at 40.

Two further issues:
- **Stop assumption.** Line 480: `stop_dist = max(atrs[i], entry_prices[i] * 0.002)`. The spec says
  `max(2.0×ATR14, Entry×0.0065)`. The code's floor is 20 bps, not 65 bps, and `atrs[i]` is used
  raw — whether it is pre-multiplied by 2.0 is not visible at this call site. Either the spec or the
  code is describing a different stop. This must be reconciled.
- **`maes[i]` is a precomputed full-life MAE**, applied from the first bar. That is conservative for
  sizing (good), but it means the backtest books worst-case adverse excursion as a smooth path,
  which understates the intra-bar gap risk that actually causes liquidations.

## Q3 — Risk architecture, and an adversarial breach sequence

**Credit first:** the governor is better designed than its description suggests. Line 475:

```python
drawdown_budget = max(0.0, peak_capital * dd_limit - closed_drawdown - open_mae)
cur_risk = min(target_risk, drawdown_budget / 1.2)
```

`dd_limit = 0.045` (line 60). The budget subtracts both realized drawdown *and* the MAE of open
positions, so it is portfolio-aware rather than per-trade. Because the new position is sized at
`budget/1.2`, the post-entry total is bounded by `peak·0.045 − budget/6`. Under its own assumptions
it holds, with a 1/6 cushion. I could not break it within those assumptions.

**The breach is in the assumptions.** The governor budgets on `cur_risk` — a stop-distance-based
quantity — but books `mae_dollar = units * maes[i]` (line 497), the *realized* adverse excursion.
Those are equal only if price never trades beyond the stop.

Adversarial sequence:

1. Month opens flat. `peak_capital = $5,000`, budget = $225.
2. Cascade begins. Signal fires on two symbols within the same bar window.
3. Position 1 sized at `cur_risk = 225/1.2 = $187.50`. `stop_dist = 0.002·entry` (the 20 bps floor
   binds in low-ATR conditions), so `units = 187.50/(0.002·entry)`.
4. Before the stop can print, a liquidation print gaps the book 0.6% through the stop level —
   ordinary for a 15m bar during a cascade, and *precisely the regime the strategy targets*.
   Realized MAE is now 3× the stop distance, so `mae_dollar ≈ $562`.
5. Position 2 is sized on a budget that already netted position 1's **booked** MAE, but position 2
   gaps identically.
6. Two positions × ~$560 = ~$1,120 of adverse excursion on $5,000 = **22% drawdown**. The 4.5%
   guardrail is exceeded ~5×, and it never had a chance to react: the clamp sizes *entry* risk
   against *stop-distance* loss, not against *gap* loss.

The fix is to size against a gap-adjusted stop (e.g. `max(2·ATR, 0.65%, k·expected_gap)` with
`expected_gap` estimated from the realized overnight/cascade gap distribution), and to cap
**aggregate** open risk at the budget rather than sizing each position independently against it.

Separately: `house_risk` reaches **$240 on a $5,000 account = 4.8% risk per trade** against a 4.5%
ceiling. Even without gaps, one losing house-money trade consumes the entire month's drawdown
budget. The house ladder is only survivable because `drawdown_budget/1.2` clamps it back — meaning
in practice the strategy spends most of house mode pinned at the clamp, so the elaborate ladder is
largely inert.

## Q4 — Top 3 latent failure modes with real capital

**1. Regime-dependent archetype extinction.** Ten archetypes, each with hand-tuned thresholds, were
selected on windows where they worked. Live, there is no `w_idx` to look up. Whatever single
selection rule replaces `WINDOW_CONFIGURATIONS` will have a materially lower hit rate, and the
strategy has no mechanism to detect that its archetype has stopped working. Expect the live curve to
look like the *average* of the 20 windows under a fixed rule — not like the max.

**2. Execution collapse in the target regime.** The edge is defined on liquidation cascades; the
cost model assumes 5 bps. These cannot both be true. Live slippage in cascades will consume a
multiple of the modeled edge, and the strategy will get filled worst exactly when its signal is
strongest.

**3. Thin-sample drawdown mispricing.** 120 trades, target-lock truncation, and 20 fitted windows
give no reliable tail estimate. The 3.5% average MaxDD is a censored statistic. Real tail risk is
unmeasured, and the house-money ladder will push size up precisely when the model is most confident
— which in crypto cascades correlates with, not against, the tail.

### Enhancements before any institutional AUM

- **Re-run honestly.** Delete `WINDOW_CONFIGURATIONS`. Fix one archetype, one threshold (or one K),
  one risk ladder for all 20 windows, selected on IS only. Restore the two skipped windows
  (2025-09-15, 2025-12-15) to a strict 3-month grid. Report whatever comes out. Based on the
  no-skill baselines I measured on the committed data, expect a large drop — that is information,
  not failure.
- **Remove the fallback loop entirely.** If a window fails, it fails. Recording the failure is the
  entire point of the protocol.
- **Report the target lock separately.** Publish both truncated and uninterrupted equity curves so
  the censoring is visible.
- **Replace flat fees with a book-impact model**: order-book micro-imbalance and depth-weighted
  slippage from L2 data, with entry conditioned on touch width at signal time.
- **Size on gap-adjusted stops** and cap aggregate open risk, not per-position risk.
- **Dynamic sizing** driven by IS-estimated tail risk (e.g. CVaR of the archetype's loss
  distribution), not by realized PnL. House-money scaling on a 6-trade month is fitting noise.
- **Execution algos**: TWAP/Iceberg with participation caps and a hard abort when touch width
  exceeds a percentile threshold.

---

## What is genuinely sound

- The 3-hour purge and the `exit_time < train_end_purged` IS filter are correctly implemented.
- The MTM drawdown governor is portfolio-aware and internally consistent.
- Adverse-first intra-bar evaluation and the next-bar-open fill convention are respected.
- The 18 parquets pass the hardened verifier: 0 gaps, 0 nulls, 0 infs, 59 columns.

The plumbing is good. The conclusion drawn from it is not supported.

---

## Bottom line

`winning_configuration.json` contains `"all_20_windows_passed": true`. It is accurate as a
description of what the script reported and false as a description of out-of-sample performance.
The 20/20 result is the output of a search whose objective function was passing 20/20.

**Recommendation: reject. Do not allocate. Re-run under a single frozen configuration before any
further claim is made.**
