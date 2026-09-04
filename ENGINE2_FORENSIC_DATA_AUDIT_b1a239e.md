# Institutional Forensic Data Audit — Engine_2 Dual-Table Architecture @ `origin/main` `b1a239e`

**Method:** full column-by-column measurement of every committed parquet, plus execution of the
changed microstructure functions against edge cases. Network egress is blocked, so the pipeline could
not be re-run end-to-end.

## SCOPE CORRECTION (read first)

The audit was commissioned as an **18-symbol** review. The repository at `b1a239e` contains:

```
binance_backtesting_data/
  ETHUSDT_15m_master_2020_2026.parquet      <- the only master table
  ETHUSDT_dataset_manifest.json
```

**One symbol, not eighteen.** No other master table and **no footprint ladder table** are committed.
Every Part B finding below is therefore a *code* audit, not a data audit — there is no Table 2 in the
repository to verify.

---

# PART A — Master Feature Table (62 columns, 210,610 rows)

## A.1 Zero-Null / Zero-Inf — ✅ PASS

| Metric | Result |
|---|---|
| Total nulls, all 62 columns | **0** |
| Total infs, all numeric columns | **0** |
| Rows | 210,610 |
| Span | 2020-09-01 00:00 → 2026-09-03 20:15 |

## A.2 15m Continuity — ✅ PASS

`np.diff(open_time_ms)`: **0 gaps** (`!= 900,000`), **0 non-monotonic**. Strictly continuous.

## A.3 Causal Forward-Fill & Provenance Tagging — ❌ FAIL

The fill is causal and correct: `historical_metrics_processor.py:71` `df["close"] = df["close"].ffill()`,
no `bfill()` anywhere. That half passes.

**The `is_synthetic` tagging does not work.** Measured: `is_synthetic.sum() == 0`, yet the table
contains 10 unmistakable maintenance bars:

| datetime_utc | open | high | low | close | volume_base | trade_count | is_synthetic |
|---|---|---|---|---|---|---|---|
| 2021-03-02 01:15 | 1565.00 | 1565.00 | 1565.00 | 1565.00 | 0 | 0 | **0** |
| 2021-03-02 01:30 | 1565.00 | 1565.00 | 1565.00 | 1565.00 | 0 | 0 | **0** |
| 2021-03-02 01:45 | 1565.00 | 1565.00 | 1565.00 | 1565.00 | 0 | 0 | **0** |
| 2022-05-01 22:30 | 2802.08 | 2802.08 | 2802.08 | 2802.08 | 0 | 0 | **0** |
| 2022-05-28 16:45/17:00 | 1793.84 ×4 | | | | 0 | 0 | **0** |
| 2024-10-28 20:00/15/30/45 | 2503.77 ×4 | | | | 0 | 0 | **0** |

All ten have `open == high == low == close` and zero trades — the signature of a synthesized bar.
Root cause, `historical_metrics_processor.py:57-68`:

```python
df["is_synthetic"] = 0
if len(df) != len(expected_ms) or not np.array_equal(df["open_time"].values, expected_ms):
    df = df.set_index("open_time").reindex(expected_ms)      # only when timestamps are MISSING
    df["is_synthetic"] = np.where(df["close"].isna(), 1, 0)  # L68 - inside the branch
```

The flag is only assigned **inside** the reindex branch, from `close.isna()`. Binance *delivers*
downtime bars with a real timestamp and a flat price, so the timeline is already continuous, the
branch never executes, and the flag stays 0. The check catches **absent** bars and misses
**degenerate** ones.

Fix:

```python
degenerate = (df["volume_base"] == 0) | (df["trade_count"] == 0)
df["is_synthetic"] = np.where(df["close"].isna() | degenerate, 1, 0).astype(np.int8)
```

This is the third consecutive round in which `is_synthetic` has been inert while reported as working.
Any engine guard of the form `sig[df["is_synthetic"] == 1] = 0` has never fired.

Minor: `is_synthetic` is stored as **int64**, not the int8 the schema intends.

## A.4 Mathematical Bounds — 2 failures, 1 false claim

| Check | Result | Verdict |
|---|---|---|
| `rsi_14 ∈ [0,100]` | [4.13, 95.62] | ✅ |
| `long_liq_usd ≤ 0` | [−1.536e7, −2,967] | ✅ |
| `short_liq_usd ≥ 0` | [4,663, 2.943e7] | ✅ |
| `open_interest_usd ≥ 0`, `funding_rate_pct`, LS ratios, `whale_index ≥ 0`, prices > 0, `atr > 0` | all in range | ✅ |
| Session VAH/VAL anchored at 00:00 UTC | bar 0 `session_val` ≈ `close`; bar 95 retains session low | ✅ |
| **`ask_depth_usd ≥ 0`** | **[−1.545e8, −0] — entirely negative** | ❌ |
| **EMAs "warmed up over 2019-2020 seed period"** | **no 2019 data exists** | ❌ |

### The order-book depth columns are fabricated

`core/canonical_indicators.py:174-184`:

```python
def estimate_depth_from_volatility(closes, atrs, base_vols):
    """Computes +-1% resting order book depth in USD and Coin
    directly proportional to empirical order book liquidity without arbitrary offsets."""
    n = len(closes)
    bid_depth_coin = np.round(base_vols * 0.025, 4)
    ask_depth_coin = np.round(-base_vols * 0.025, 4)     # <- negative by construction
    bid_depth_usd  = np.round(bid_depth_coin * closes, 2)
    ask_depth_usd  = np.round(ask_depth_coin * closes, 2)
    return bid_depth_usd, ask_depth_usd, bid_depth_coin, ask_depth_coin
```

Three problems:

1. **There is no order-book input.** The function is a deterministic transform of `base_vols`:
   `bid_depth_* = +2.5% × volume_base`, `ask_depth_* = −2.5% × volume_base`. These four columns carry
   **zero information not already in `volume_base` and `close`**. A model given them is given volume
   twice and will attribute spurious importance to it.
2. **The `atrs` parameter is accepted and never used.**
3. **The docstring is false.** It claims proportionality to "empirical order book liquidity"; nothing
   empirical enters the function. `n = len(closes)` is also computed and unused.

The negative sign is a deliberate convention, not an accident — but a column named `*_depth_usd`
holding negative dollars will break every downstream consumer that assumes depth is a magnitude.

**Action:** either populate these from real L2 snapshots or drop the four columns. Do not ship
synthetic depth under a name that implies measurement.

### The EMA warmup claim is false

The claim is "Seeded EMAs (8, 21, 50, 200, 800) properly warmed up over the 2019-2020 seed period."
Measured: the table **starts 2020-09-01** — there is no 2019 data (`binance_historical_fetcher.py:59`
defaults to `start_year=2019`, but Binance USDT-M futures history begins later and the committed file
begins 2020-09-01). `canonical_indicators.py:36` states the EMA is *"seeded from the first available
bar"*, and at row 0:

```
ema_800 = 405.6100    close = 432.5200    discrepancy = 6.22%
```

An EMA-800 needs ~800 bars (8.3 days) to converge. For the first several thousand rows `ema_800`, and
therefore `macro_spread`, `mc` and `p200` — which drive the archetype conditions — are seed artefacts,
not indicators. **The first ~2-4 weeks of every symbol should be masked from training**, or the seed
period must actually be fetched.

## A.5 Other observations

- `oi_change_pct` max = **2,239.82%** — a 0 → non-zero OI transition, not a real 22× jump. Clamp or flag.
- `metrics_available == 0` in **20.79%** of bars (43,776) — OI/funding/LS-ratio/whale are fallback
  constants there. Consistent with prior rounds; it means ~1/5 of the feature matrix is constant.
- `poc_source`: **210,226 bars `OHLC_APPROX`, only 384 `TICK_EXACT`**. See Part C — this is the
  binding constraint on the whole footprint programme.

---

# PART B — Footprint Ladder (Table 2)

**No ladder table is committed.** The following is a code audit; item B.4 cannot be verified at all.

## B.1 Strict Price Adjacency (Gate 4b) — ✅ CLOSED

`tick_footprint_fetcher.py:177-199`:

```python
ladder["bin_diff_below"] =  ladder.groupby("open_time_ms")["bin_idx"].diff(1)
ladder["bin_diff_above"] = -ladder.groupby("open_time_ms")["bin_idx"].diff(-1)
raw_s_vol_below = ladder.groupby("open_time_ms")["s_vol"].shift(1)
ladder["s_vol_below"] = raw_s_vol_below.where(ladder["bin_diff_below"] == 1, 0.0)
...
ladder["buy_imbalance"] = ((ladder["b_vol"] >= 3.0*np.maximum(ladder["s_vol_below"].fillna(0.0),1e-4))
                           & (ladder["b_vol"] >= min_vol_floor)
                           & (ladder["bin_diff_below"] == 1)).astype(int)
```

Masked **and** gated on adjacency — belt and braces. Empty rungs can no longer produce a false
diagonal. Verified.

## B.2 Contiguous Stacked Clusters (Gate 4c) — ✅ CLOSED

I ran `_calc_contiguous_stacked_clusters` against the exact case that produced a false positive last
round:

| Case | bins | Returns | Correct? |
|---|---|---|---|
| **Gap at 12** (last round's false positive) | 10, 11, 13 | **0** | ✅ fixed |
| Genuinely contiguous | 10, 11, 12 | 1 | ✅ |
| One run of 5 | 10, 11, 12, 13, 14 | **1** | ✅ (was 3) |
| Two separate runs of 3 | 10,11,12,20,21,22 | **2** | ✅ (was 4) |
| Only 2 levels | 10, 11 | 0 | ✅ |

It is now a true **cluster count** requiring `bins[k] - bins[k-1] == 1`, not a row count or a
`Σ max(0,L−2)` weight. Both prior defects are closed.

## B.3 Integer POC Equality — ✅ CLOSED

`is_poc = (bin_idx == poc_bin_idx)` on int64. No float comparison remains.

## B.4 Cross-Table Referential Integrity — ❌ CANNOT VERIFY

There is no Table 2 in the repository, and `verify_parquet_integrity.py` still has no referential
check. From last round and still unaddressed:

- The ladder gap check remains **hardcoded** `num_gaps = 0` (L73-78), so any "0 Gaps [PASS]" on a
  ladder file is assigned, not measured.
- `bins_populated` is computed but not exported and not audited.

---

# PART C — Strategy S1 Readiness

## F1 (anti-causal MAE) — ❌ NOT ELIMINATED

`s1_liquidation_cascade.py:529-535`:

```python
mae_dollar = units * maes[i]          # L529  full-life MAE, known only at exit
...
open_mae_dollars[p] = mae_dollar      # L535  booked AT ENTRY
```

consumed at L483 (`cur_mtm_equity = capital - open_mae`) and L510 (`drawdown_budget = ... - open_mae`).
This is the same construct the remediation plan called Flaw C. As I noted previously it is
**conservative** — it overstates drawdown and shrinks the sizing budget, so it cannot inflate ROI —
but it is still not eliminated, and it is not on the list of things you fixed.

## F2 (stop gap-through) — ✅ FIXED

L355 and L381 carry explicit gap-aware fill logic ("Fill at stop minus slippage, or open/low if gapped
down"), and L193 computes a true-range ATR *with* gap terms. Verified.

## F3 (Top-K future selection) — ✅ FIXED

L823-833:

```python
# F3 Fix: Derive frozen decision threshold strictly In-Sample (Top 20% IS threshold)
frozen_prob_threshold = float(np.percentile(is_probs, 75)) if len(is_probs) > 0 else 0.50
frozen_prob_threshold = max(0.50, min(0.65, frozen_prob_threshold))
...
mask_oos = (probs_oos >= frozen_prob_threshold)
```

The threshold is derived from **in-sample** predictions and frozen before the OOS pass; selection is
a causal threshold test in arrival order, not a future rank. Correct fix. (The [0.50, 0.65] clamp is
a fixed prior, not a per-window tune — acceptable.)

## FP_AbsorptionCluster — wired, but cannot fire in any OOS window

The archetype exists (L635-638) and is mapped to two regimes (L646-647):

```python
'Crash / High-Vol Flush':         'FP_AbsorptionCluster',
'Compression / Range Absorption': 'FP_AbsorptionCluster',
```

It triggers on `fp_stacked_*_imb >= 1` **or** `fp_poc_vol_ratio > 0.35`. Measured against the only
committed table:

| Condition | Bars |
|---|---|
| `fp_stacked_buy_imb` or `fp_stacked_sell_imb` ≥ 1 | 45 |
| `fp_poc_vol_ratio` > 0.35 | 61 |
| **Either** (long or short arm) | **105 — 0.050% of 210,610 bars** |

And the provenance of the tick data behind them:

```
TICK_EXACT bars: 384 of 210,610 (0.182%)
  span: 2026-08-30 00:00  ->  2026-09-02 23:45
  duration: 3 days 23:45
```

**The entire tick-footprint sample is four days at the very end of the dataset — five months *after*
the OOS protocol ends (2026-04-15).** Every one of the 105 candidate bars lies outside every OOS
window. For all 20 windows, `fp_stacked_*` and `fp_poc_vol_ratio` are identically 0.0, so:

- `FP_AbsorptionCluster` produces **zero signals** in W02 and in W03, W14, W15, W18, W19, W20 — the
  seven windows whose regime maps to it.
- Those windows hit the `len(df_is) < 40` guard and are skipped by `continue`, silently reducing the
  reported window count.

**On the 5R / 33 bps question:** the answer from last round still holds and is unchanged by any of
this work. At a 0.35% stop, 25 bps slippage + 8 bps fees = **0.94R per trade**, and the unconditional
base rate for +5R-before-−1R is **16.5%**, so break-even requires a **32.3%** hit rate. Whether the
absorption cluster achieves that is currently **untestable**, because the feature has four days of
data. No claim about >5R payoffs can be supported until Table 2 spans the backtest.

---

# INSTITUTIONAL VERDICT

## **REJECT** for production deployment. **CONDITIONAL** for continued research.

### Blocking defects

| # | Severity | Finding |
|---|---|---|
| 1 | **Blocking** | `is_synthetic` is identically 0 despite 10 degenerate maintenance bars. Provenance contract unmet. Third consecutive round. |
| 2 | **Blocking** | `ask_depth_usd/coin`, `bid_depth_usd/coin` are fabricated from `volume_base` (±2.5%), carry zero independent information, and the docstring misrepresents them. `atrs` is unused. |
| 3 | **Blocking** | Tick footprint covers **4 days** (2026-08-30 → 2026-09-02), entirely after the OOS window. `FP_AbsorptionCluster` cannot fire in any of the 20 windows. |
| 4 | **Blocking** | Only **1 of 18** symbols committed. The 18-symbol audit cannot be performed. |
| 5 | High | EMA warmup claim false — no 2019 seed; `ema_800` is 6.22% off at row 0 and unconverged for weeks. `macro_spread`/`mc`/`p200` are seed artefacts early in the sample. |
| 6 | High | F1 (future MAE booked at entry) still present at L529. Conservative, but not eliminated. |
| 7 | High | Ladder gap check hardcoded `num_gaps = 0`; no cross-table referential integrity check. |
| 8 | Medium | `oi_change_pct` reaches 2,239%; `metrics_available == 0` in 20.79% of bars; `is_synthetic` dtype int64 not int8. |

### What genuinely passed

- **A.1, A.2:** zero nulls, zero infs, perfect 900,000 ms continuity across 210,610 rows.
- **A.4 bounds:** RSI, liquidation polarity, OI, funding, ratios, prices, ATR all valid.
- **Session VAH/VAL** correctly anchored at 00:00 UTC.
- **Gate 4b** (adjacency masking) and **Gate 4c** (contiguous cluster counting) are both closed and I
  verified them by executing the functions against the edge cases that previously failed.
- **Integer POC** equality.
- **F2** (gap-aware stop fills) and **F3** (frozen in-sample threshold) are correctly fixed.

The engineering discipline is clearly improving — Gates 4b/4c and F2/F3 are real, verified fixes.
What is failing now is not logic but **data coverage and provenance**: the table is clean, but a
fifth of its feature matrix is constant, its order-book columns are invented, its provenance flag does
not fire, and the microstructure layer that the entire 5R thesis depends on exists for four days.

### Conditions to convert to PASS

1. Fix `is_synthetic` to catch degenerate bars, not just absent timestamps; re-run and assert
   `is_synthetic.sum() > 0` where zero-volume bars exist.
2. Remove or genuinely populate the four depth columns; correct the docstring.
3. Fetch the full tick-footprint history **before** claiming any footprint-backed result. Until Table 2
   spans 2021-2026, `FP_AbsorptionCluster` must be removed from `REGIME_ARCHETYPE_MAP` so it cannot
   silently skip windows.
4. Commit all 18 symbols, or state plainly that the dataset is ETH-only.
5. Mask the first 800 bars (or fetch a real seed period) before training.
6. Replace the hardcoded ladder `num_gaps = 0` with a real contiguity check on deduplicated
   `open_time_ms`, and add cross-table referential integrity.
7. Eliminate F1 with bar-by-bar open equity.

**Do not run the 18-symbol extraction until items 1 and 2 are fixed** — both change the content of
Table 1, and retrofitting them means re-downloading and reprocessing everything.
