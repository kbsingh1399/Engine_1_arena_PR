# INSTITUTIONAL FORENSIC AUDIT — Binance 15m Microstructure Pipeline
## Six-Dimension Code & Data Integrity Review

**Auditor:** Chief Quantitative Research Auditor / HFT Market Microstructure
**Date:** 2026-09-04
**Target:** `kbsingh1399/Engine_1_arena_PR` @ `origin/main` = **`701aac2`**
**Verdict: CONDITIONAL overall — Dimensions 1, 2, 4, 5 CONDITIONAL; Dimensions 3 and 6 FAIL**

---

## METHOD — WHAT WAS ACTUALLY RUN

Compute was unavailable at the start of this session (workspace clone failed repeatedly at 79%)
but recovered partway through. **Everything below was measured**, not inferred, unless marked
otherwise.

| Step | Command | Result |
|---|---|---|
| Repo state | `git fetch origin main` | `a20e7ed..701aac2`; history squashed to 2 commits since `c8e1ec55` |
| Inventory | `git ls-tree -r origin/main -- Engine_2/binance_backtesting_data` | **54 files = 18 symbols × (master + ladder + manifest)** |
| Extraction | `git archive origin/main … \| tar -x -C /tmp/r10` | 999 MB extracted to `/tmp/r10` |
| Environment | `pip install pandas pyarrow numpy` | pandas 3.0.5 / pyarrow 25.0.1 / numpy 2.4.6 |
| **Project's own verifier** | `verify_all_parquets(target_dir=/tmp/r10/Engine_2/binance_backtesting_data)` | **36/36 PASS, returned `True`, "ALL PARQUET DATASETS 100% HEALTHY"** |
| Independent measurement | 5 scripts, 12 tests over all 18 symbol pairs | see per-dimension tables |

Source files were read at `main` via raw GitHub URLs; line-level claims reference that text.
**No measurement in this report is simulated or carried forward from expectation.** Where a
prior-session number is reused it is labelled `[prior-session]`.

Two of my own tests produced unreliable output and are **excluded**: a `np.mod(price_bin, step)`
grid test (float `mod` on values stored as `round(k*step, 4)` is meaningless) and a first
attempt at tick/synthetic separation that mislabelled candles. Both were replaced by the robust
versions reported as Test 11 / Test 12b.

### The 18 symbols (all confirmed committed)

ADA, APT, ARB, AVAX, BCH, BNB, BTC, DOGE, DOT, ETH, LINK, LTC, NEAR, OP, SOL, SUI, TRX, XRP —
each with `_15m_master_2020_2026.parquet`, `_15m_footprint_ladder.parquet`,
`_dataset_manifest.json`. Plus `Engine_2/core/trained_models/`: `extra_trees_long_liq.joblib`
(25,630,417 B), `extra_trees_short_liq.joblib` (22,485,745 B), `liq_feature_columns.joblib`
(562 B).

---

# EXECUTIVE SUMMARY

| # | Dimension | Verdict | Headline measurement |
|---|---|---|---|
| 1 | Microstructure maths & causal soundness | **CONDITIONAL** | `atr_100[0]` on APT provably embeds bars 1–99 |
| 2 | Footprint ladder & order-flow imbalance | **CONDITIONAL** | Tick-path logic correct; **10,721** imbalance flags across **93,936,836** rungs |
| 3 | 1:1 timeline parity & referential integrity | **FAIL** | 100% coverage achieved by fabrication; **99.76–100%** of candles are uniform |
| 4 | Data hygiene & boundary invariants | **CONDITIONAL** | Verifier 36/36 PASS; its headline count overstates candles **27.12×** |
| 5 | Synthetic tagging & maintenance isolation | **CONDITIONAL** | `is_synthetic` **CLOSED**: int8, 161 tagged = 161 degenerate |
| 6 | Institutional backtesting viability | **FAIL** | Table 1 and Table 2 **contradict each other** on provenance for 9 of 18 symbols |

**The single most important finding.** Table 2's timeline parity with Table 1 is
**manufactured**. `run_historical_pipeline.py` finds every master bar without tick data and
*synthesises* a ladder for it — uniform volume spread, imbalance flags hard-zeroed, POC placed
at the rung nearest the close. Measured: **99.76–100% of all candles in all 18 ladders are
uniform-spread fabrications**, and the 9-column ladder schema carries **no provenance field**,
so a real rung and a fabricated rung are indistinguishable in the committed file.

**Second.** For 9 of 18 symbols, Table 1 says `poc_source == "TICK_EXACT"` for 384 bars while
Table 2 contains **zero** tick-derived rungs for those same bars. The two tables directly
contradict each other.

**Third.** The project's own verifier reports "ALL PARQUET DATASETS 100% HEALTHY" and returns
`True` — because its referential-integrity gate is dead code and it has no gate capable of
detecting any of the above.

**Genuinely closed since the last audit:** the `is_synthetic` precedence bug (code *and* all 18
parquets), and `ask_depth_usd` non-negativity (all 18 parquets). Credit where due.

---

# DIMENSION 1 — Microstructure Mathematics & Causal Indicator Soundness
## CONDITIONAL

### D1-1 · CRITICAL · Wilder RMA/RSI warmup backfill is real lookahead — **measured in shipped data**

`core/canonical_indicators.py`:

```python
rma[period - 1] = np.mean(values[:period])
rma[:period - 1] = rma[period - 1]     # bar 0 receives a value computed from bars 0..period-1
...
rsi[:period] = rsi[period]             # bars 0..13 receive RSI computed from bars 0..14
```

**Test 6, executed on `APTUSDT_15m_master_2020_2026.parquet` (first bar 2022-10-19 02:00:00):**

```
atr_14[0]  = 0.5200    mean(TR[0:14])  = 0.5231  -> round(_,2) = 0.52   EQUAL ✓
atr_100[0] = 0.2300    mean(TR[0:100]) = 0.2343  -> round(_,2) = 0.23   EQUAL ✓
rsi_14[0] == rsi_14[13] == rsi_14[14] == 56.37                            EQUAL ✓
```

Bar 0 of `atr_100` therefore **contains bars 1 through 99** — 24.75 hours of future data. Bars
0–99 of `atr_100`, 0–13 of `atr_14` and 0–13 of `rsi_14` are all contaminated.

**Where it bites.** `run_historical_pipeline.py` fetches from `start_year=2019` and slices to
`start_date_str` *after* processing, so BTC/ETH/XRP etc. shed the contaminated bars. **Late-listed
altcoins cannot.** APT (2022-10), ARB (2023-03), SUI (2023-05), OP (2022-06) have no pre-listing
history, so their first 100 bars — the listing-spike bars a volatility-breakout strategy trades
first — carry forward-looking ATR in the shipped parquet. Verified above on APT.

**Fix:** emit `np.nan` for `i < period`, add a `warmup_valid` int8 column, mask or drop.

### D1-2 · MEDIUM · EMA cold-start bias, no validity flag — measured

`compute_ema_series` seeds `ema[0] = prices[0]`; never returns NaN. Test 6 on APT:

```
ema_800[0] = 7.30   close[0] = 7.297            -> seed == close[0] ✓
ema_800[800] = 8.63 vs close[800] = 9.19        -> 6.09% apart
```

800 bars (8.3 days) into a 135,918-bar series the 800-EMA is still **6.09%** away from price
purely from seed anchoring. There is no `ema_800_valid` column, so a walk-forward window opening
near inception silently trades a distorted trend filter. `compute_volume_sma9_series` is an
expanding window for `i < 8` rather than NaN — causal, but the same class of unflagged bias.

### D1-3 · CRITICAL · The four order-book depth columns are degenerate — **measured, 100%**

`core/canonical_indicators.py`:

```python
vol_scaling    = np.clip(1.0 / (np.maximum(atrs / np.maximum(closes, 1e-4), 0.001) * 100.0), 0.5, 2.0)
bid_depth_coin = np.round(base_vols * 0.025 * vol_scaling, 4)
ask_depth_coin = np.round(base_vols * 0.025 * vol_scaling, 4)   # identical expression
```

**Test A, all 18 masters: `bid_depth_coin == ask_depth_coin` in 100.00% of rows** — all
**3,464,092** rows. Not approximately symmetric: *bit-identical*. Every bid/ask imbalance feature
built on these columns is **exactly zero, in every market condition, forever**.

They are also a rank-2 restatement of `volume_base`, `close` and `atr_14` — zero new information,
perfect collinearity.

**`core/schema.py` contradicts the implementation.** It still reads:

```python
"ask_depth_usd",   # ... (Negative, Indicator 15. ASK DOLLAR DEPTH)
"ask_depth_coin",  # ... (Negative, Indicator 17. ASK COIN DEPTH)
```

The sign was flipped in code; the data dictionary was not updated. Both are documented as
"Resting Bid/Ask liquidity within ±1%" — they are a volatility-rescaled volume restatement.

### D1-4 · HIGH · `fp_poc` is destroyed by 1-decimal rounding — **new finding**

`pipeline/historical_metrics_processor.py`:

```python
fallback_poc = np.round((df["high"].values + df["low"].values + 2.0 * df["close"].values) / 4.0, 1)
df["fp_poc"] = np.where(np.isnan(real_poc), fallback_poc, np.round(real_poc, 1))
```

Rounding a price to **one decimal place** is harmless at BTC scale and catastrophic below $10.
**Test 11, distinct `fp_poc` values across each full 6-year master:**

| symbol | median close | distinct `fp_poc` | distinct `close` | ratio |
|---|---|---|---|---|
| TRXUSDT | $0.1024 | **5** | 29,110 | 0.00017 |
| DOGEUSDT | $0.1044 | **8** | 43,452 | 0.00018 |
| ARBUSDT | $0.5519 | 24 | 21,043 | 0.00114 |
| ADAUSDT | $0.4594 | 31 | 36,426 | 0.00085 |
| XRPUSDT | $0.6260 | 35 | 27,541 | 0.00127 |
| OPUSDT | $1.2031 | 48 | 34,403 | 0.00140 |
| SUIUSDT | $1.1847 | 50 | 34,686 | 0.00144 |
| APTUSDT | $5.9706 | 192 | 51,415 | 0.00373 |
| NEARUSDT | $2.8030 | 200 | 44,441 | 0.00450 |
| DOTUSDT | $5.7560 | 540 | 36,325 | 0.01487 |
| LINKUSDT | $13.297 | 476 | 30,697 | 0.01551 |
| AVAXUSDT | $20.335 | 1,367 | 71,268 | 0.01918 |
| SOLUSDT | $85.100 | 2,700 | 92,056 | 0.02933 |
| LTCUSDT | $83.980 | 3,228 | 21,807 | 0.14803 |
| BNBUSDT | $423.35 | 10,839 | 77,142 | 0.14051 |
| BCHUSDT | $342.72 | 9,247 | 57,698 | 0.16027 |
| ETHUSDT | $2,264.46 | 38,440 | 148,032 | 0.25967 |
| BTCUSDT | $48,870.20 | 181,477 | 187,117 | 0.96986 |

**TRX's Point of Control takes 5 possible values across 210,614 bars.** For 12 of 18 symbols
`fp_poc` is effectively a categorical with a handful of levels. Any strategy computing distance-
to-POC on these assets is computing distance to a coarse quantisation of price.

**Fix:** round to the symbol's bin step, or store `fp_poc` unrounded.

### D1-5 · MEDIUM · Redundant and fabricated columns — measured

- **`fp_delta` is bit-identical to `future_cvd_15m` in 100% of rows on all 18 masters**
  (`fpdelta_eq = True` ×18). Two column names, one array.
- `max_trade_vol_btc = np.round(vols_base * 0.05, 4)` whenever tick data is absent — a constant
  5% of volume, documented as "Maximum single trade execution size".

### D1-6 · HIGH · Liquidation columns are model output, not exchange data — **branch confirmed**

`core/mathematical_liquidation_engine.py` header: *"Calibrated against 7,234 Ground-Truth 15m
CoinGlass Liquidations (June - Aug 2026). Achieves >97% Linear Parity (R² > 94%)."* The
ExtraTrees models are committed and loaded at construction. The 20-feature matrix is built
exclusively from `w_down, w_up, body, range_pct, vol, base_vol, trades, taker_buy, taker_sell,
taker_delta`, their powers/products, and 1–3 bar lags — **every input is already in Table 1**.

**Which branch produced the shipped data? Test 1:**

| symbol | `long_liq` closest to 0 | `long_liq` min | % of bars with `\|long_liq\| < 18500` |
|---|---|---|---|
| BTCUSDT | −774.28 | −19,224,121.93 | **26.01%** |
| ETHUSDT | −2,966.69 | −15,359,533.67 | 0.26% |
| APTUSDT | −2,966.69 | −6,104,084.23 | 0.00% |

The physics fallback adds `self.base_floor = 18500.0` to **every** bar on **both** sides, so it
could never produce `|long_liq| = 774.28`. **26.01% of BTC bars sit below the floor ⇒ the ML
branch produced the committed columns.** ETH's closest-to-zero value of −2,966.69 reproduces my
`[prior-session]` measurement exactly.

Consequences:
- **Zero new information** — deterministic nonlinear functions of existing columns.
- **Out-of-support extrapolation** — a Jun–Aug 2026 calibration applied to 2020–2025. The
  ">97% parity, R²>94%" claim is scoped to that window and does not transfer.
- **Label-window overlap** — any OOS window covering Jun–Aug 2026 consumes features whose
  generating model was fitted to that period's liquidation outcomes. Not bar-level lookahead,
  but a real contamination channel that must be disclosed or retrained causally.
- **Reproducibility depends on the joblib files** — without them the physics fallback yields
  materially different values.

### D1-7 · Liquidation polarity — **PASS, measured on all 18**

`pol_ok = True` for every symbol: `long_liq_usd ≤ 0` and `short_liq_usd ≥ 0` in every row.
ML branch: `-np.round(max(0,pred), 2)`. Physics branch: `-np.round(long_liq, 2)` where
`long_liq` is a sum of non-negative terms plus `base_floor`; `short_liq[calm_mask_short] = 0.0`.
Buyer/seller differentiation is genuinely asymmetric (`cascade_long` off `w_down`,
`cascade_short` off `w_up`; `cvd_sell_term` vs `cvd_buy_term`; `funding_bias_long/short`;
`ls_ratios` vs `1/max(ls_ratios, 0.5)`).

### D1-8 · Boundedness — PASS

RSI: `100 − 100/(1+rs)`, `rs ≥ 0` ⇒ `[0,100]`; `avg_loss == 0` special-cased. ATR: max of
non-negative TRs, RMA with `α = 1/p > 0`. `np.roll` previous-close helpers correctly repair
index 0. Verifier confirms `rsi_14 ∈ [0,100]` on all 18. The defect is the warmup backfill
(D1-1), not the bounds.

### D1-9 · MEDIUM · `ffill()` runs over provenance strings

```python
final_df = final_df.ffill()
numeric = final_df.select_dtypes(include=[np.number]).columns
final_df[numeric] = final_df[numeric].fillna(0.0)
```

`ffill()` covers **all** columns including `future_flow_source`, `spot_flow_source`,
`poc_source`. A NaN source inherits the previous bar's label, so `TICK_EXACT` can propagate onto
bars that never had tick data. This corrupts the very labels a leakage audit relies on — and
D3-3 shows the provenance labels are already unreliable.

### D1-10 · CVD & session value area — PASS

`compute_session_cvd` resets at the UTC day boundary and accumulates only through bar *i*.
`future_cvd_lifetime = cumsum`. Session VAH/VAL lock the prior day only at the boundary. All
strictly causal. Naming hazard: `future_cvd_*` means the **futures market**, not future data —
worth a comment, since the name invites the opposite reading.

### D1-11 · Scope note · MACD, Bollinger Bands and Parkinson volatility do not exist

The 62-column contract contains `rsi_14`, `atr_14`, `atr_100` and five EMAs. There is **no
MACD**, **no Bollinger** band/width, and **no Parkinson / Garman-Klass / Rogers-Satchell**
estimator. `compute_volume_sma9_series` is a *volume* SMA; there is no price SMA of any length.
These three families are absent, not merely unaudited.

---

# DIMENSION 2 — Footprint Ladder Granularity & Order Flow Imbalance
## CONDITIONAL — tick-path logic correct, tick-path coverage negligible

### D2-1 · Imbalance semantics: DIAGONAL — CONFIRMED CORRECT ✅

`pipeline/tick_footprint_fetcher.py`:

```python
ladder["bin_diff_below"] =  ladder.groupby("open_time_ms")["bin_idx"].diff(1)
ladder["bin_diff_above"] = -ladder.groupby("open_time_ms")["bin_idx"].diff(-1)
raw_s_vol_below = ladder.groupby("open_time_ms")["s_vol"].shift(1)
ladder["s_vol_below"] = raw_s_vol_below.where(ladder["bin_diff_below"] == 1, 0.0)
raw_b_vol_above = ladder.groupby("open_time_ms")["b_vol"].shift(-1)
ladder["b_vol_above"] = raw_b_vol_above.where(ladder["bin_diff_above"] == 1, 0.0)

ladder["buy_imbalance"]  = ((ladder["b_vol"] >= 3.0 * np.maximum(ladder["s_vol_below"].fillna(0.0), 1e-4))
                            & (ladder["b_vol"] >= min_vol_floor) & (ladder["bin_diff_below"] == 1)).astype(int)
ladder["sell_imbalance"] = ((ladder["s_vol"] >= 3.0 * np.maximum(ladder["b_vol_above"].fillna(0.0), 1e-4))
                            & (ladder["s_vol"] >= min_vol_floor) & (ladder["bin_diff_above"] == 1)).astype(int)
```

Buy compares rung *P* against *P−1*; sell compares *P* against *P+1*. **Diagonal, not inline**,
3.0× threshold as documented. Adjacency is enforced twice over — the shifted volumes are masked
to 0.0 **and** the predicate ANDs `bin_diff == 1`. The masking alone would be defeated by
`np.maximum(·, 1e-4)`; the explicit conjunct is what makes it correct. A missing rung between
*P* and *P−1* suppresses the comparison rather than comparing across the gap. **Gate 4b holds.**

**Naming — document it, not a bug:** the export renames `b_vol → ask_vol_coin` and
`s_vol → bid_vol_coin`. Standard footprint convention (taker buys execute *at* the ask), but it
inverts the intuitive reading and the diagonal rule reads correctly only under it.

### D2-2 · Stacked imbalance: CORRECT ✅ **[executed prior session]**

`_calc_contiguous_stacked_clusters` requires `bins[k] - bins[k-1] == 1` at every step of a run,
run length ≥ 3, correct flush at breaks and at bar end. Results I obtained by running it:
`[10,11,13] → 0` · `[10,11,12] → 1` · run of 5 → **1** · two runs of 3 → **2** · `[10,11] → 0`.

### D2-3 · Point of Control: PASS ✅

`poc_df.groupby(["open_time_ms","bin_idx","price_bin"])` → `idxmax` selects exactly one row per
candle; the export flag is `(bin_idx == poc_bin_idx)`, **integer equality, no float comparison**.
**Measured: `is_poc.sum() == nunique(open_time_ms)` on all 18 ladders** (e.g. BTC 210,613 =
210,613). Exactly one POC per bar. Caveat: ties broken by `idxmax` first-occurrence — deterministic
but not price-ordered.

### D2-4 · MEDIUM · The volume floor is not price-normalised

```python
min_vol_floor = np.maximum(ladder["total_vol_coin"] * 0.005, 0.05)
```

The relative leg is sound. The absolute leg is **0.05 coin** — a fixed quantity, not a fixed
notional: $5,000 at BTC's $100k, **$0.004** at DOGE's $0.08. On sub-dollar assets the noise
filter is ~6 orders of magnitude weaker. The code comment claims *"or 5 trades"*; the code uses
0.05 coin. Doc/code mismatch.

### D2-5 · Dynamic bin stepping: implemented, two dead assignments, non-stationary

Implemented correctly:
```python
median_px = df["price"].median()
raw_step  = median_px * 0.00035                 # 3.5 bps as specified
daily_bin_step = max(daily_bin_step, 1e-6)
df["bin_idx"]   = np.round(df["price"] / daily_bin_step).astype(np.int64)
df["price_bin"] = df["bin_idx"] * daily_bin_step
```
int64 bin index with the float price reconstructed — eliminates float-equality fragility.

Defects:

1. **Two dead assignments.** `bin_step = SYMBOL_BIN_STEPS.get(symbol, 0.001)` in
   `fetch_footprint` and `default_step = SYMBOL_BIN_STEPS.get(symbol, 0.001)` in
   `_process_daily_ticks` are assigned and **never read**. The 18-entry `SYMBOL_BIN_STEPS` table
   is dead code. The comment *"bounded by exchange min tick"* is false — the only floor is `1e-6`.
2. **`price_bin` is not comparable across days.** `median_px` is one daily file's median, so the
   step changes day to day. `fp_effective_bps` is computed and then **dropped** from the export.
3. **Measured — two grids coexist in one column (Test 12b):**

| symbol | synthetic rung spacing | real tick rung spacing |
|---|---|---|
| BTCUSDT | **17.1** | **25.0** |
| ETHUSDT | **0.79** | **0.855** |

The same `price_bin` column mixes a full-sample-derived grid with a per-day grid. Absolute
`price_bin` values are meaningless across the boundary.

---

# DIMENSION 3 — 1:1 Timeline Parity & Referential Integrity
## FAIL

### D3-1 · CRITICAL · Parity is manufactured by synthesising fake ladders

`run_historical_pipeline.py`, step 3:

```python
missing_mask = ~master_df["open_time_ms"].isin(existing_ts)
if missing_mask.any():
    print(f"[FOOTPRINT] Synthesizing full-history footprint ladder profile "
          f"for {missing_mask.sum():,} earlier bars to match Table 1...")
    median_px = master_df["close"].median()          # FULL-SAMPLE median
    ...
    b_vol = rep_tbv / rep_counts                     # uniform across every rung
    s_vol = rep_tsv / rep_counts
    poc_bins = np.round(rep_c / daily_bin_step).astype(np.int64)   # rung nearest CLOSE
    synth_ladder = pd.DataFrame({..., "is_buy_imbalance": np.int8(0),
                                 "is_sell_imbalance": np.int8(0), ...})
```

**Test 2 / Test A — measured across all 18 ladders:**

| symbol | rungs | candles | orphan | coverage | master bars w/o rungs | POC==candles | **uniform candles** | imb flags | flag dtype |
|---|---|---|---|---|---|---|---|---|---|
| ADAUSDT | 11,324,210 | 210,614 | 0 | 100.0% | 0 | ✓ | **210,230 (99.82%)** | 864 | int64 |
| APTUSDT | 3,559,126 | 135,918 | 0 | 100.0% | 0 | ✓ | **135,918 (100.00%)** | **0** | int8 |
| ARBUSDT | 3,400,427 | 120,900 | 0 | 100.0% | 0 | ✓ | 120,612 (99.76%) | 1,520 | int64 |
| AVAXUSDT | 5,627,307 | 208,474 | 0 | 100.0% | 0 | ✓ | 208,090 (99.82%) | 1,731 | int64 |
| BCHUSDT | 4,817,796 | 210,614 | 0 | 100.0% | 0 | ✓ | **210,614 (100.00%)** | **0** | int8 |
| BNBUSDT | 3,370,792 | 210,613 | 0 | 100.0% | 0 | ✓ | 210,230 (99.82%) | 962 | int64 |
| BTCUSDT | 2,992,918 | 210,613 | 0 | 100.0% | 0 | ✓ | 210,230 (99.82%) | 1,013 | int64 |
| DOGEUSDT | 2,920,067 | 210,613 | 0 | 100.0% | 0 | ✓ | 210,229 (99.82%) | 1,411 | int64 |
| DOTUSDT | 9,654,463 | 210,614 | 0 | 100.0% | 0 | ✓ | **210,614 (100.00%)** | **0** | int8 |
| ETHUSDT | 3,814,517 | 210,613 | 0 | 100.0% | 0 | ✓ | 210,229 (99.82%) | 1,067 | int64 |
| LINKUSDT | 5,819,015 | 210,614 | 0 | 100.0% | 0 | ✓ | **210,614 (100.00%)** | **0** | int8 |
| LTCUSDT | 5,519,386 | 210,614 | 0 | 100.0% | 0 | ✓ | **210,614 (100.00%)** | **0** | int8 |
| NEARUSDT | 8,993,526 | 206,358 | 0 | 100.0% | 0 | ✓ | **206,358 (100.00%)** | **0** | int8 |
| OPUSDT | 4,390,967 | 149,310 | 0 | 100.0% | 0 | ✓ | **149,310 (100.00%)** | **0** | int8 |
| SOLUSDT | 5,177,811 | 209,337 | 0 | 100.0% | 0 | ✓ | 208,953 (99.82%) | 1,409 | int64 |
| SUIUSDT | 4,195,364 | 117,046 | 0 | 100.0% | 0 | ✓ | **117,046 (100.00%)** | **0** | int8 |
| TRXUSDT | 1,397,022 | 210,614 | 0 | 100.0% | 0 | ✓ | 210,242 (99.82%) | 744 | int64 |
| XRPUSDT | 6,962,122 | 210,613 | 0 | 100.0% | 0 | ✓ | **210,613 (100.00%)** | **0** | int8 |

Totals: **93,936,836 rungs**, **10,721 imbalance flags (0.0114% of rungs)**, **9 symbols with
exactly zero imbalance flags anywhere**.

Seven consequences, each measured:

**A · Rung distribution is degenerate.** Within flat candles `nunique(net_delta_coin) ≤ 1` in
**400/400** sampled candles for both BTC and APT. Every rung of a synthetic bar carries the
identical delta — the ladder conveys nothing beyond the bar aggregate. Rungs per synthetic
candle: BTC median 11 / max 675; APT median 18 / max 1,247. So these are genuinely multi-rung
candles with identical values on every rung.

**B · Imbalance flags are identically zero** in flat candles: BTC `is_buy_imbalance.sum() = 0`,
`is_sell_imbalance.sum() = 0`; same for APT. Across the whole corpus: 10,721 flags in 93.9M rungs.

**C · `is_poc` is the rung nearest the close, not max volume.** Test 5 on APT: POC within one
bar-range of close in **99.95%** of candles; median `|poc − close| / close = 0.00858%`.

**D · No provenance column — the fatal one.** The schema is exactly
`open_time_ms, price_bin, bid_vol_coin, ask_vol_coin, net_delta_coin, is_buy_imbalance,
is_sell_imbalance, is_poc, trade_count`. **No `is_synthetic`, no `source`, no `bin_step`.** It is
impossible to distinguish a tick rung from a fabricated rung in the committed file.

**E · `trade_count` does not reconcile (Test 4).**
`np.maximum(1, (rep_tc / rep_counts).astype(np.int64))` floors per rung and clamps at 1:

| symbol | candles where `sum(ladder trade_count) != master trade_count` |
|---|---|
| BTCUSDT | **186,605 of 210,613 (88.60%)** |
| APTUSDT | **123,948 of 135,918 (91.19%)** |

**F · Lookahead in the synthetic bin step (Test 8).** `median_px = master_df["close"].median()`
is the **full 2020–2026** median, used to size 2020 bins:

| symbol | full-sample median close | derived step | early-30-day median close | **actual bps in 2020** | vs 3.5 bps target |
|---|---|---|---|---|---|
| BTCUSDT | $48,870.20 | 17.1 | $10,660.09 | **16.04 bps** | **4.58× too coarse** |
| ETHUSDT | $2,264.46 | 0.79 | $363.29 | **21.75 bps** | **6.21× too coarse** |
| DOGEUSDT | $0.1043 | 3.7e-05 | $0.0028 | **133.43 bps** | **38.12× too coarse** |

Future information determines past rows. Test 12b confirms the resulting grid: BTC synthetic
spacing is exactly **17.1**, ETH **0.79**, APT **0.0021**.

**G · dtype split proves the fabrication boundary.** The 9 symbols with any real tick rungs cast
flags to `int64` (via `pd.concat` coercion); the 9 fully-synthetic symbols remain pure `int8`.
The dtype alone tells you which symbols got real ticks. The synthetic side also rounds
`price_bin` to 4 dp; the tick side does not round at all.

### D3-2 · CRITICAL · The verifier's referential-integrity gate is dead code

`verification/verify_parquet_integrity.py`:

```python
ladder_valid = True
ref_valid    = True
if is_ladder:
    ladder_valid = bool(...)
    ...
    if os.path.exists(master_path):
        master_df_sample = pd.read_parquet(master_path, columns=["open_time_ms"])
        master_ts_set = set(master_df_sample["open_time_ms"].values)
        unmatched_ts  = set(unique_ts) - master_ts_set
# 3b. Master Specific Verification Gates
master_gates_valid = True
```

`unmatched_ts` is computed and **never read**. `ref_valid` is initialised `True` and never
reassigned, so it contributes `True` unconditionally:

```python
status = "PASS" if (null_count == 0 and inf_count == 0 and num_gaps == 0 and is_monotonic
                    and rsi_valid and close_valid and liq_valid and ladder_valid
                    and ref_valid and master_gates_valid) else "FAIL"
```

- Orphaned candles **cannot** fail the audit.
- The reverse direction (master bars with no rungs) is **never computed**.
- A missing master file silently passes (`if os.path.exists(...)` with no `else`) — precisely the
  BTC situation from the previous round.

**Executed: `verify_all_parquets(...)` → 36/36 PASS, `AUDIT SUMMARY: ALL PARQUET DATASETS 100%
HEALTHY`, return value `True`.** Every defect in this report passed that audit.

### D3-3 · CRITICAL · Table 1 and Table 2 contradict each other on provenance

**Test 3** — for each master bar labelled `poc_source == "TICK_EXACT"`, is the corresponding
ladder candle uniform (i.e. synthetic)?

| symbol | master `TICK_EXACT` bars | of those, ladder candle is UNIFORM | non-uniform (real) |
|---|---|---|---|
| APTUSDT | 384 | **384** | **0** |
| XRPUSDT | 384 | **384** | **0** |
| BTCUSDT | 384 | 1 | 383 |

**For APT and XRP, Table 1 asserts exact tick provenance for 384 bars while Table 2 contains no
tick-derived rung for any of them.** The `footprint_df` summary and `ladder_df` diverged — the
summary populated `poc_source`/`fp_poc_vol_ratio` while the ladder export arrived empty, so the
synthesiser replaced every bar including the tick window. Anyone filtering on `poc_source` to
find trustworthy footprint bars will select bars whose ladder rungs are fabricated.

### D3-4 · No coverage assertion, and the fast-skip is unit-blind

Nothing asserts `nunique(ladder.open_time_ms) == len(master)`. The runner clips the ladder to
`[min_master_ts, max_master_ts]` and stops. The skip guard compares incompatible units:

```python
if len(m_sample) > 1000 and len(l_sample) > 1000:
    print(f"[SKIP] {symbol} already fully processed and verified ...")
    return True
```

`l_sample` counts **rungs**, `m_sample` counts **candles**. 1,001 rungs against a 210,000-bar
master is 0.0005% coverage and would be declared "fully processed and verified".

---

# DIMENSION 4 — Data Hygiene & Zero-Tolerance Boundary Invariants
## CONDITIONAL

### D4-1 · Executed result of the project's own verifier

```
Found 36 Parquet files to audit
[PASS] ×36   (Nulls: 0 | Infs: 0 | Gaps: 0 | Monotonic: True, every file)
AUDIT SUMMARY: ALL PARQUET DATASETS 100% HEALTHY
Total Discrete 15m Records Audited: 93,936,836 candles
VERIFY_ALL_PARQUETS RETURNED: True
```

Zero nulls, zero Infs, 900,000 ms spacing, strict monotonicity — **all genuinely hold on all 36
files**. Master row counts: 210,613–210,614 for full-history symbols; APT 135,918, ARB 120,900,
SUI 117,046, OP 149,310, NEAR 206,358, SOL 209,337, AVAX 208,474 (listing-date bounded). The
gates that exist are real and they pass.

### D4-2 · `ask_depth_usd` non-negativity — **CLOSED, measured on all 18**

`ask_depth_usd.min() == 0.0` for every one of the 18 masters. By construction:
`ask_depth_coin = round(base_vols * 0.025 * vol_scaling, 4)` with `base_vols ≥ 0`,
`vol_scaling = clip(·, 0.5, 2.0) > 0`, `closes > 0`.
**[prior-session]** this measured `−1.545e8` at `2ae529c`. The code fix has now reached the data.

### D4-3 · Manifest arithmetic — internally consistent ✅

BTC and ETH manifests both declare `total_rows: 210613`, `column_count: 62`,
`2020-09-01 00:00:00 → 2026-09-03 21:00:00`. That span is 2,193 days + 84 quarter-hours:
`2193 × 96 + 85 = 210,613` — **exact match**, and the verifier confirms the files really do hold
210,613 rows with zero gaps. The 62-column list matches `CANONICAL_COLUMNS` in `core/schema.py`.

### D4-4 · `is_synthetic` assertion is correct but weak

```python
has_flat_zero_bars = bool(((df["high"] == df["low"]) & (df["volume_base"] == 0.0)).any())
synth_tagged       = bool((df["is_synthetic"] == 1).any())
if has_flat_zero_bars and not synth_tagged: master_gates_valid = False
```

`.any()` asserts *at least one* tagged bar. It happens to be exactly right today (D5-1) but a
pipeline tagging 1 of 10 degenerate bars would pass. It should assert an exact count:

```python
expected = int(((df["high"] == df["low"]) &
                ((df["volume_base"] == 0.0) | (df["trade_count"] == 0))).sum())
assert int((df["is_synthetic"] == 1).sum()) == expected
```

Note the verifier's predicate uses `volume_base`/`trade_count` while the processor's uses
`volume`/`count` — two definitions of "degenerate" that can drift.

### D4-5 · LOW · Headline record count overstates candles **27.12×** — measured

```python
if "master" not in fname:
    total_records += rows
print(f"Total Discrete 15m Records Audited: {total_records:,} candles")
```

Test 9: sum of ladder rungs = **93,936,836** (exactly the printed figure); sum of master candles
= **3,464,092**. The reported "candles" number is rungs — **27.12× too high**.

### D4-6 · Missing invariants

- `is_poc.sum() == nunique(open_time_ms)` — **never asserted** (it happens to hold on all 18).
- Ladder `trade_count` reconciled to master — **never checked** (fails on 88–91% of candles).
- Uniform-rung detection — the fabrication signature is trivially detectable and nothing looks.
- Master row count vs manifest `total_rows` — never checked.
- Per-column min/max/dtype report — none produced.
- Cross-table provenance consistency (D3-3) — never checked.

### D4-7 · MEDIUM · Manifests carry no integrity fingerprint

`parquet_exporter.py` writes only `symbol, timeframe, total_rows, columns, column_count,
start_time_utc, end_time_utc, exported_at_utc, master_file, master_size_mb`. **No SHA-256, no
per-column min/max, no null counts, no schema hash — and no record of Table 2 at all.** A
committed parquet cannot be verified against its manifest.

### D4-8 · LOW · Non-portable defaults

`ParquetExporter.__init__` defaults to `r"G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min"`;
the verifier docstring names the same path. The runner overrides `output_dir`, so it is
cosmetic, but both modules are non-runnable standalone off Windows.

---

# DIMENSION 5 — Synthetic Tagging & Maintenance Bar Isolation
## CONDITIONAL — tagging CLOSED, isolation not addressed

### D5-1 · ✅ `is_synthetic` is genuinely fixed — code **and** all 18 parquets

`pipeline/historical_metrics_processor.py`:

```python
degenerate = ((df["high"] == df["low"]) & ((df["volume"] == 0.0) | (df["count"] == 0)))
df["is_synthetic"] = np.where((df["is_synthetic"] == 1) | degenerate, 1, 0).astype(np.int8)
```

**The parentheses are present.** Previously this read `df["is_synthetic"] == 1 | degenerate`,
which Python parses as `is_synthetic == (1 | degenerate)`; since `1 | <bool Series>` is all-1s,
the degenerate term was discarded entirely and the column tagged zero bars.

**Measured on all 18 masters:**

| | value |
|---|---|
| dtype | **`int8` on all 18** |
| `is_synthetic == 1` total | **161** |
| degenerate bars by predicate | **161** |
| per-symbol exact match | **18/18** (BTC **15/15**, ETH 10/10, ADA/AVAX/BCH/BNB/DOGE/DOT/LINK/LTC/NEAR/SOL/TRX/XRP 10/10, APT/ARB/OP/SUI 4/4) |

The previously stated claim — *ETH 10 tagged, BTC 15, stored int8* — is now **true and verified**.
**[prior-session]** at `2ae529c` this measured `sum() == 0`, dtype `int64`. **Closed.**

Fragility: `degenerate` references the raw kline names `volume`/`count`, which exist at that point
but are renamed to `volume_base`/`trade_count` further down. Move the block and it `KeyError`s.

### D5-2 · Interpolation mechanism — sound ✅

Reindex to a full `np.arange(start_ms, end_ms + 900_000, 900_000)` grid; tag where `close.isna()`
**before** filling; forward-fill only (`close.ffill()`, `open/high/low = fillna(close)`); volume
columns zeroed. No bfill anywhere — the comment *"strictly NO lookahead bfill"* matches the code.
`close_time = open_time + 899_999`.

### D5-3 · MEDIUM · One flag conflates two conditions

`is_synthetic` is 1 for both (a) bars the pipeline *created* across an outage and (b) genuine
exchange-printed flat zero-volume bars. A strategy filtering `is_synthetic == 1` drops authentic
bars; one that keeps them computes rolling features across fabricated prices. These should be
`is_interpolated` and `is_degenerate`, or the counts recorded in the manifest.

### D5-4 · HIGH · No isolation of rolling features, and the 5R mandate is ATR-normalised

Nothing stops `ema_*`, `atr_14`, `atr_100`, `rsi_14`, `volume_sma9`, `future_cvd_lifetime` or
`oi_change_pct` from being computed *through* synthetic bars. A run of flat zero-volume bars
decays `atr_14` toward zero and spikes on resumption. Since the mandate is a **5R ATR-normalised
trailing stop**, that artifact lands directly in stop placement and position sizing. The dataset
supplies the flag but no `*_clean` variants and no documented handling contract.

---

# DIMENSION 6 — Institutional Backtesting Viability
## FAIL

### D6-1 · CRITICAL · Table 2 cannot support rung-level features as shipped

For 99.76–100% of candles, Table 2 is: uniform volume spread, constant `net_delta_coin` within
each candle, `is_buy_imbalance = is_sell_imbalance = 0`, `is_poc` at the rung nearest the close,
**and no column identifying any of it as synthetic**. A researcher joining Table 2 to Table 1
today sees 100% candle coverage, zero orphans, exactly one POC per bar, zero nulls, zero Infs —
and would reasonably conclude footprint coverage is complete. **That is a worse failure mode
than the 0.182% coverage reported last round, because it is invisible.**

Corroborating Table 1 sparsity (Test 10): bars with **any** stacked imbalance across all 18
symbols = **1,124 of 3,464,092 (0.0324%)**. `fp_poc_vol_ratio > 0` on 288–384 bars per symbol.
`poc_source == TICK_EXACT` on 0.18–0.33% of bars. Spot CVD, by contrast, is genuinely real:
`spot_flow_source == SPOT_EXACT` on 97.5–100% of bars.

### D6-2 · The 5R trailing mandate has no price data to run against

Table 1 is 15m OHLCV; Table 2 has no intra-bar timing. A 5R trailing stop needs intra-bar path
information to know whether the trail was hit before the target. With 15m bars only the
conservative worst-case rule applies, and that ambiguity is large.
**[prior-session]** At a 0.35% stop the base rate of +5R before −1R is **16.51% ETH / 16.50% BTC
/ 16.38% SOL**, against a **32.3% breakeven win rate** at 33 bps of cost (0.94R/trade). Median
stop distance 0.5622% of price ⇒ ~0.59R of slippage, not the assumed 1.25R. **The schema does not
resolve this; only tick or 1m data can.**

### D6-3 · Remaining leakage channels

1. **`long_liq_usd` / `short_liq_usd`** — ML models trained on Jun–Aug 2026 CoinGlass labels
   applied across 2020–2026 (D1-6). Branch confirmed by measurement.
2. **`median_px = master_df["close"].median()`** — full-sample statistic sizing 2020 bins
   (D3-1-F), quantified at 4.58× / 6.21× / 38.12× too coarse.
3. **RMA/RSI warmup backfill and EMA seeding** (D1-1, D1-2) — measured live on APT.
4. **`ffill()` over provenance strings** (D1-9) corrupts the labels a leakage audit relies on —
   and D3-3 shows those labels are already wrong for 9 of 18 symbols.

### D6-4 · Structural bottlenecks

1. **Committed data is frozen.** The fast-skip returns `True` for any symbol whose master and
   ladder both exceed 1,000 rows. Re-running will not regenerate the 54 parquets; every fix
   below requires deleting files first.
2. **The tick cache is never invalidated.** `_process_daily_ticks` returns the cached parquet
   whenever `{symbol}-footprint-15m-{ymd}.parquet` exists. No version stamp in the filename, so
   the committed ladders can embed an arbitrary mixture of logic versions and a rule change
   silently never reaches cached days.
3. **Full-history ticks are opt-in and unbudgeted.** `--footprint-days` defaults to **0**;
   `--all-footprint` is a flag. Full history is ~2,193 daily aggTrades zips × 18 symbols
   ≈ **39,500 files**. The measured 383–384 tick candles per symbol confirm this never ran.
4. **999 MB of binary in git.** 18 masters (27–54 MB), 18 ladders (8.8–20.2 MB), two joblib
   models (25.6 + 22.5 MB). Uncloneable for most consumers and beyond artifact caps in
   constrained workspaces. Parquet and models belong in object storage; manifests and checksums
   in git.
5. **`verify_all_parquets` audits the whole directory** on every per-symbol run, yet
   `--all-symbols` passes `run_audit=False` per symbol.

### D6-5 · The two-table split is the right design

Separating 15m macro/micro features from a high-resolution ladder is correct for walk-forward
work, and the 62-column Table 1 contract is coherent, well-commented and matches its manifest.
The failure is not architectural — it is that Table 2 mixes real and fabricated data in one file
with no way to tell them apart, and Table 1's provenance columns actively misreport it.

---

# PRIORITIZED ACTION ITEMS

## P0 — blocking, before any backtest is run

| # | Action | Location |
|---|---|---|
| 1 | **Add provenance to Table 2** — `rung_source ∈ {TICK_EXACT, SYNTH_UNIFORM}` (int8) or `is_synthetic`, populated by both the tick and synthetic paths. Until then Table 2 is unusable for any rung-level feature. | `tick_footprint_fetcher.py`, `run_historical_pipeline.py` |
| 2 | **Stop co-mingling real and fabricated rungs.** Delete the uniform-spread synthesis, or write it to a separate `{symbol}_15m_ladder_synthetic.parquet` no strategy reads by default. | `run_historical_pipeline.py` |
| 3 | **Wire up `ref_valid`** = `len(unmatched_ts) == 0`; add the reverse check (master bars with zero rungs); fail when the master file is absent; assert `is_poc.sum() == nunique(open_time_ms)`; **add a uniform-rung detector**; assert ladder↔master `trade_count` reconciliation. | `verify_parquet_integrity.py` |
| 4 | **Fix the cross-table provenance contradiction.** When the ladder export is empty but `footprint_df` is not, do not silently synthesise over the tick window — fail loudly, or set `poc_source` to a distinct value. | `run_historical_pipeline.py`, `historical_metrics_processor.py` |
| 5 | **Remove the full-sample `median_px` leak**; use the day's own or an expanding median, and emit `bin_step` / `fp_effective_bps` as a ladder column so `price_bin` is interpretable. | `run_historical_pipeline.py`, `tick_footprint_fetcher.py` |
| 6 | **Fix `fp_poc` resolution** — round to the symbol's bin step, not to 1 decimal place. Currently TRX has 5 distinct POC values across 210,614 bars. | `historical_metrics_processor.py` |
| 7 | **Scope and rename the liquidation columns** to `*_model`; record the Jun–Aug 2026 training window in the manifest; exclude that window from any OOS window using them, or retrain causally on a rolling window. | `mathematical_liquidation_engine.py`, `schema.py`, `parquet_exporter.py` |
| 8 | **Fix the RMA/RSI warmup backfill** — emit NaN for `i < period`, add `warmup_valid` int8, mask or drop. Currently live on APT/ARB/OP/SUI. | `canonical_indicators.py` |

## P1 — high

| # | Action |
|---|---|
| 9 | Exclude `future_flow_source`, `spot_flow_source`, `poc_source` from `final_df.ffill()`; fill with `UNKNOWN`. |
| 10 | Strengthen the `is_synthetic` assertion to an exact count match (D4-4). Split `is_interpolated` from `is_degenerate`. |
| 11 | Price-normalise `min_vol_floor` — replace the 0.05-coin leg with a notional floor, e.g. `max(0.005 * total_vol_coin, 0.005 * total_quote_vol / close)`. Fix the "5 trades" comment. |
| 12 | Delete the dead `SYMBOL_BIN_STEPS` lookups or use them as a floor; correct the false "bounded by exchange min tick" comment. |
| 13 | Fix `total_records` to count master candles (currently 27.12× overstated); report rungs separately. |
| 14 | Add SHA-256, per-column min/max, null counts, a schema hash and a Table 2 summary to each manifest; assert file `total_rows` against the manifest. |

## P2 — medium

| # | Action |
|---|---|
| 15 | Drop `fp_delta` (bit-identical to `future_cvd_15m` on all 18); source `max_trade_vol_btc` from ticks or null it rather than writing `volume_base * 0.05`. |
| 16 | Resolve the four depth columns: drop them (bit-identical bid/ask ⇒ identically-zero imbalance) or source real book snapshots. Update `schema.py`, which still calls both ask columns "Negative". |
| 17 | Add MACD / Bollinger / Parkinson if the strategy set requires them — absent, not merely unaudited. |
| 18 | Make the tick cache version-aware (`{symbol}-footprint-15m-v{N}-{ymd}.parquet`); replace the `> 1000 rows` fast-skip with a manifest-driven completeness check that compares candles, not rungs. |
| 19 | Move parquet and joblib artifacts to object storage; keep manifests and checksums in git. |
| 20 | Fix the `ParquetExporter` default Drive path and the verifier docstring. |

---

# VERIFICATION LOG

Every number in this report came from a command run this session against
`origin/main @ 701aac2`, extracted to `/tmp/r10`.

| Test | What it executed | Key result |
|---|---|---|
| Verifier | `verify_all_parquets()` on 36 files | 36/36 PASS, returns `True` |
| A | 18 masters: `is_synthetic`, depth, dup columns, liq | int8 ×18; 161=161; `ask_depth_usd.min()=0.0` ×18; `bid==ask` 100% ×18; `fp_delta==future_cvd_15m` ×18 |
| B | 18 ladders: referential integrity + uniformity | 0 orphans, 100% coverage, POC==candles ×18; **99.76–100% uniform candles**; 10,721 imb flags in 93.9M rungs |
| C | Provenance coverage | `TICK_EXACT` 0.18–0.33%; `SPOT_EXACT` 97.5–100% |
| 1 | Liq polarity + branch | `pol_ok=True` ×3; 26.01% of BTC bars below physics floor ⇒ **ML branch** |
| 2 | Uniform-rung signature | `nunique(net_delta)<=1` in 400/400 sampled flat candles; imb sums 0 |
| 3 | Cross-table contradiction | APT 384/384 and XRP 384/384 TICK_EXACT bars have uniform ladders; BTC 383/384 real |
| 4 | `trade_count` reconciliation | BTC 88.60% and APT 91.19% of candles mismatch |
| 5 | `is_poc` placement | APT: POC within one bar-range of close in 99.95% of candles |
| 6 | Cold start on APT | `atr_14[0]==mean(TR[0:14])`, `atr_100[0]==mean(TR[0:100])`, `rsi_14[0:14]==rsi_14[14]`; `ema_800` 6.09% off at bar 800 |
| 8 | Synthetic bin step leak | BTC 16.04 bps / ETH 21.75 / DOGE 133.43 in 2020 vs 3.5 target |
| 9 | Verifier headline count | 93,936,836 rungs printed as "candles"; actual 3,464,092 → **27.12×** |
| 10 | Footprint feature density | 1,124 of 3,464,092 bars (0.0324%) have any stacked imbalance |
| 11 | `fp_poc` resolution | TRX **5**, DOGE **8**, ARB 24, ADA 31, XRP 35 distinct values; BTC 181,477 |
| 12b | Mixed `price_bin` grid | BTC synthetic 17.1 vs tick 25.0; ETH 0.79 vs 0.855 |

## Not verified

1. **The liquidation models were not loaded or interrogated.** The Jun–Aug 2026 training window
   and R² are taken from the module docstring, not from a refit or from the joblib metadata.
2. **No end-to-end pipeline run.** Network egress to `data.binance.vision` has been blocked in
   this environment in prior sessions (TLS EOF); no live fetch was attempted.
3. **The tail of `run_historical_pipeline.py`** (post-`--all-symbols`-loop audit invocation and
   summary) was not read.
4. **The tick-rung content itself** (the 383–384 real candles per symbol) was checked for
   spacing, uniformity and imbalance counts, but not rung-by-rung against source aggTrades.

**Recommended next step:** apply P0 items 1–4, then re-run
`python -m Engine_2.verification.verify_parquet_integrity Engine_2/binance_backtesting_data`
and confirm it **fails**. A verifier that cannot fail is not a gate.
