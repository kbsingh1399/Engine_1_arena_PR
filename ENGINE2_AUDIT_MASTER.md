# ENGINE 2 — MASTER AUDIT & PROGRESS DOCUMENT
### Crypto Microstructure Data Pipeline · Forensic Code & Data Integrity Review

| | |
|---|---|
| **Document** | `ENGINE2_AUDIT_MASTER.md` — single self-contained source of truth |
| **Auditor** | Chief Quantitative Research Auditor / MD Quantitative Risk / Algorithmic Execution |
| **Last updated** | 2026-09-04 |
| **Session branch** | `arena/01a06774-engine-1-arena-pr` |
| | |
| **PART I — Data pipeline** | audited at `origin/main` = `701aac2` · 6 dimensions · **CONDITIONAL**, D3 & D6 **FAIL** |
| **PART II — S1 strategy & walk-forward** | audited at `origin/main` = **`8c0d74b`** · 4 domains + execution |
| | |
| **Temporal verdict — `s1_liquidation_cascade.py`** | **`[CLEAN — ZERO LOOKAHEAD VERIFIED]`** |
| **Temporal verdict — `verify_sequential_w1_w20.py`** | **`[LEAKAGE DETECTED]`** |
| **Allocation verdict** | **`[REJECT]`** |
| | |
| **Production readiness** | **REJECT** — pipeline blocked on P0 items 1–8; S1 blocked on R-1…R-8 |
| **Research readiness** | **CONDITIONAL** — Table 1 usable with documented exclusions; Table 2 unusable |

**Headline.** Two independent audits, one conclusion. The data pipeline fabricates the footprint
ladder it claims to have measured (Part I). The strategy engine is causally clean and, when
actually executed against the committed data, passes **0 of 20** out-of-sample windows with a
**22.9%** win rate against a 40% gate (Part II). The multi-sleeve verifier that *can* produce a
passing scorecard is the one that selects a different hand-picked strategy and a different set of
risk parameters for every window — that is test-set snooping, not validation.

> **This document is exhaustive and self-contained.** It supersedes
> `S1_V2_INSTITUTIONAL_REVIEW.md`, `FOOTPRINT_ARCHITECTURE_COUNCIL_REVIEW.md`,
> `FOOTPRINT_GATE_VERIFICATION_e39335c.md`, `ENGINE2_FORENSIC_DATA_AUDIT_b1a239e.md` and
> `GATE_CLOSURE_AUDIT_2ae529c.md`. Every number in it was produced by a command run against the
> audited revision; the reproduction commands are in **Appendix A**.

---

# TABLE OF CONTENTS

### PART I — DATA PIPELINE & PARQUET INTEGRITY (audited at `701aac2`)

- [0. How to reproduce this audit](#0-how-to-reproduce-this-audit)
- [1. Executive summary & scorecard](#1-executive-summary--scorecard)
- [2. Audit trail — five rounds](#2-audit-trail--five-rounds)
- [3. Dimension 1 — Microstructure maths & causal indicator soundness](#3-dimension-1--microstructure-maths--causal-indicator-soundness)
- [4. Dimension 2 — Footprint ladder & order-flow imbalance](#4-dimension-2--footprint-ladder--order-flow-imbalance)
- [5. Dimension 3 — Timeline parity & referential integrity](#5-dimension-3--timeline-parity--referential-integrity)
- [6. Dimension 4 — Data hygiene & boundary invariants](#6-dimension-4--data-hygiene--boundary-invariants)
- [7. Dimension 5 — Synthetic tagging & maintenance isolation](#7-dimension-5--synthetic-tagging--maintenance-isolation)
- [8. Dimension 6 — Institutional backtesting viability](#8-dimension-6--institutional-backtesting-viability)
- [9. Strategy-level context (S1 walk-forward, cost baselines)](#9-strategy-level-context)
- [10. Defect register](#10-defect-register)
- [11. Prioritized action plan](#11-prioritized-action-plan)
- [12. What was NOT verified](#12-what-was-not-verified)
- [Appendix A — Reproduction commands](#appendix-a--reproduction-commands)
- [Appendix B — Schema reference](#appendix-b--schema-reference)

### PART II — S1 STRATEGY ENGINE & WALK-FORWARD CAUSALITY (audited at `8c0d74b`)

- [II.0 Evidence base — what was actually executed](#ii0-evidence-base--what-was-actually-executed)
- [II.1 Domain 1 — Information leakage & temporal snooping](#ii1-domain-1--information-leakage--temporal-snooping)
- [II.2 Domain 2 — Threshold calibration & parameter snooping](#ii2-domain-2--threshold-calibration--parameter-snooping)
- [II.3 Domain 3 — Microstructure & intra-bar execution realism](#ii3-domain-3--microstructure--intra-bar-execution-realism)
- [II.4 Domain 4 — Single strategy vs multi-sleeve feasibility](#ii4-domain-4--single-strategy-vs-multi-sleeve-feasibility)
- [II.5 Line-by-line vulnerability log](#ii5-line-by-line-vulnerability-log)
- [II.6 Verdicts & required remediation](#ii6-verdicts)

> **Read Part II first if you only have time for one section.** It contains the temporal verdict,
> the allocation verdict, and the executed 20-window result.

---

---

# PART I — DATA PIPELINE & PARQUET INTEGRITY
### Audited at `origin/main` = `701aac2`

---

# 0. HOW TO REPRODUCE THIS AUDIT

```bash
# 1. Fetch the audited revision
git fetch origin main
git rev-parse --short origin/main          # -> 701aac2

# 2. Extract the data + pipeline OUTSIDE the working tree (~1 GB, do not commit)
mkdir -p /tmp/r10/Engine_2
git archive origin/main \
  Engine_2/binance_backtesting_data \
  Engine_2/verification Engine_2/core Engine_2/pipeline \
  Engine_2/run_historical_pipeline.py | tar -x -C /tmp/r10

# 3. Environment
pip install --break-system-packages pandas pyarrow numpy
#   verified working: pandas 3.0.5 / pyarrow 25.0.1 / numpy 2.4.6

# 4. Run the project's own verifier
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('vpi','/tmp/r10/Engine_2/verification/verify_parquet_integrity.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print('RETURNED:', m.verify_all_parquets(target_dir='/tmp/r10/Engine_2/binance_backtesting_data'))
"
# -> 36/36 PASS · "ALL PARQUET DATASETS 100% HEALTHY" · RETURNED: True
```

Every independent measurement quoted in this document is reproduced by a script in
**Appendix A**. Nothing here is simulated, estimated, or carried forward from expectation.
Prior-session figures are explicitly labelled `[prior-session]`.

## 0.1 Repository state at the audited revision

`Engine_2/binance_backtesting_data/` contains **54 files = 18 symbols × 3 artifacts**, 999 MB:

```
ADA  APT  ARB  AVAX  BCH  BNB  BTC  DOGE  DOT  ETH  LINK  LTC  NEAR  OP  SOL  SUI  TRX  XRP
     └── each: {SYM}USDT_15m_master_2020_2026.parquet
               {SYM}USDT_15m_footprint_ladder.parquet
               {SYM}USDT_dataset_manifest.json
```

`Engine_2/core/trained_models/`: `extra_trees_long_liq.joblib` (25,630,417 B),
`extra_trees_short_liq.joblib` (22,485,745 B), `liq_feature_columns.joblib` (562 B).

`ENGINE_1_CRYPTO_SYMBOLS` in `run_historical_pipeline.py` lists exactly these 18.

### Table 1 profile — all 18 masters (measured)

| symbol | rows | first bar (UTC) | last bar (UTC) | rsi min | rsi max | max \|oi_change_pct\| % | metrics_available % | is_synthetic |
|---|---|---|---|---|---|---|---|---|
| ADAUSDT | 210,614 | 2020-09-01 00:00 | 2026-09-03 21:15 | 3.55 | 96.71 | 1,610.79 | 79.22 | 10 |
| APTUSDT | 135,918 | 2022-10-19 02:00 | 2026-09-03 21:15 | 4.38 | 96.48 | 70.29 | 100.00 | 4 |
| ARBUSDT | 120,900 | 2023-03-23 15:00 | 2026-09-02 23:45 | 4.35 | 94.66 | 3,847.34 | 100.00 | 4 |
| AVAXUSDT | 208,474 | 2020-09-23 07:00 | 2026-09-03 21:15 | 4.93 | 98.55 | 2,592.95 | 80.03 | 10 |
| BCHUSDT | 210,614 | 2020-09-01 00:00 | 2026-09-03 21:15 | 3.57 | 96.66 | **6,509.46** | 79.22 | 10 |
| BNBUSDT | 210,613 | 2020-09-01 00:00 | 2026-09-03 21:00 | 3.40 | 96.66 | 3,529.60 | 79.21 | 10 |
| BTCUSDT | 210,613 | 2020-09-01 00:00 | 2026-09-03 21:00 | 4.09 | 96.74 | 2,029.93 | 100.00 | **15** |
| DOGEUSDT | 210,613 | 2020-09-01 00:00 | 2026-09-03 21:00 | 3.42 | 98.10 | 4,837.72 | 79.21 | 10 |
| DOTUSDT | 210,614 | 2020-09-01 00:00 | 2026-09-03 21:15 | 5.01 | 96.99 | 16.42 | 79.22 | 10 |
| ETHUSDT | 210,613 | 2020-09-01 00:00 | 2026-09-03 21:00 | 4.13 | 95.62 | 2,239.82 | 79.21 | 10 |
| LINKUSDT | 210,614 | 2020-09-01 00:00 | 2026-09-03 21:15 | 4.88 | 94.89 | 3,504.30 | 79.22 | 10 |
| LTCUSDT | 210,614 | 2020-09-01 00:00 | 2026-09-03 21:15 | 4.69 | 95.78 | 3,514.20 | 79.22 | 10 |
| NEARUSDT | 206,358 | 2020-10-15 08:00 | 2026-09-03 21:15 | 6.78 | 97.01 | 2,736.44 | 80.85 | 10 |
| OPUSDT | 149,310 | 2022-06-01 14:00 | 2026-09-03 21:15 | 3.71 | 94.50 | 81.62 | 100.00 | 4 |
| SOLUSDT | 209,337 | 2020-09-14 07:00 | 2026-09-03 21:00 | 6.26 | 95.25 | 3,641.28 | 79.70 | 10 |
| SUIUSDT | 117,046 | 2023-05-03 16:00 | 2026-09-03 21:15 | 4.90 | 95.90 | 1,427.13 | 100.00 | 4 |
| TRXUSDT | 210,614 | 2020-09-01 00:00 | 2026-09-03 21:15 | 2.20 | 96.57 | 94.59 | 79.22 | 10 |
| XRPUSDT | 210,613 | 2020-09-01 00:00 | 2026-09-03 21:00 | 2.76 | 98.02 | 3,876.56 | 79.21 | 10 |

Totals: **3,464,092 master candles**, **93,936,836 ladder rungs**, **161 synthetic bars**.
All 18 masters: 62 columns, zero nulls, zero Infs, zero timestamp gaps, strictly monotonic.

---

# 1. EXECUTIVE SUMMARY & SCORECARD

## 1.1 Dimension scorecard

| # | Dimension | Verdict | Decisive measurement |
|---|---|---|---|
| 1 | Microstructure maths & causal soundness | **CONDITIONAL** | `atr_100[0]` on APT provably equals `mean(TR[0:100])` → bars 1–99 leak into bar 0 |
| 2 | Footprint ladder & order-flow imbalance | **CONDITIONAL** | Tick-path logic **correct**; only **10,721** imbalance flags exist across **93,936,836** rungs |
| 3 | Timeline parity & referential integrity | **FAIL** | 100% coverage achieved by fabrication; **99.76–100%** of candles are uniform spread |
| 4 | Data hygiene & boundary invariants | **CONDITIONAL** | Verifier 36/36 PASS; its headline count overstates candles **27.12×**; one gate is dead code |
| 5 | Synthetic tagging & maintenance isolation | **CONDITIONAL** | Tagging **CLOSED** (int8, 161 = 161); rolling-feature isolation **not addressed** |
| 6 | Institutional backtesting viability | **FAIL** | Table 1 and Table 2 **contradict each other** on provenance for 9 of 18 symbols |

## 1.2 The three findings that matter most

**① Table 2's timeline parity is manufactured, not achieved.**
`run_historical_pipeline.py` detects every master bar lacking tick data and *synthesises* a
ladder for it — volume spread uniformly across rungs, imbalance flags hard-zeroed, POC placed at
the rung nearest the close. Measured: **99.76–100% of all candles in all 18 ladders are uniform
fabrications.** The 9-column ladder schema carries **no provenance field**, so a real
tick-derived rung and a fabricated rung are indistinguishable in the committed file.

**② For 9 of 18 symbols the two tables directly contradict each other.**
Table 1 labels 384 bars `poc_source == "TICK_EXACT"`; Table 2 contains **zero** tick-derived
rungs for those same bars (APT 384/384 uniform, XRP 384/384 uniform; BTC 383/384 real).

**③ The project's own verifier cannot detect any of this.**
Its referential-integrity gate computes orphaned candles into `unmatched_ts` and never reads the
variable; `ref_valid` is hard-`True`. It reports **"ALL PARQUET DATASETS 100% HEALTHY"** and
returns `True`. Every defect in this document passed that audit.

## 1.3 What is genuinely fixed (verified in the data, not just the code)

| Item | Now (`701aac2`) | Previously (`2ae529c`) |
|---|---|---|
| `is_synthetic` operator-precedence bug | **int8 on all 18; 161 tagged = 161 degenerate; exact match 18/18** | `sum() == 0`, dtype `int64` |
| `ask_depth_usd` sign | **`min() == 0.0` on all 18** | `−1.545e8` |
| Gate 4b rung adjacency | correct | correct |
| Gate 4c stacked-cluster contiguity | correct | correct |
| Integer POC indexing | correct | correct |
| Part C — F2 gap fills, F3 frozen IS threshold | closed | closed |
| `REGIME_ARCHETYPE_MAP` pre-2026 skip | closed | closed |

The team is responsive and the fixes are real. The blocking problem is no longer broken
arithmetic — it is that **the completeness of Table 2 was solved by generating data rather than
by fetching it, and nothing in the pipeline or the verifier can tell the difference.**

---

# 2. AUDIT TRAIL — FIVE ROUNDS

| Round | Revision | Deliverable | Verdict | Blocking findings |
|---|---|---|---|---|
| 1 | — | `S1_V2_INSTITUTIONAL_REVIEW.md` | S1 REJECT, 0/20 windows | Strategy does not clear breakeven |
| 2 | — | `FOOTPRINT_ARCHITECTURE_COUNCIL_REVIEW.md` | — | Architecture-level review |
| 3 | `e39335c` | `FOOTPRINT_GATE_VERIFICATION_e39335c.md` | CONDITIONAL | Gates 4b, 4c, integer POC, F2, F3 closed; **F1 not eliminated** |
| 4 | `b1a239e` | `ENGINE2_FORENSIC_DATA_AUDIT_b1a239e.md` | REJECT-production / CONDITIONAL-research | 8 defects |
| 5 | `2ae529c` | `GATE_CLOSURE_AUDIT_2ae529c.md` | CONDITIONAL — 2 of 4 closed | `is_synthetic` precedence bug; depth data stale |
| **6** | **`701aac2`** | **this document** | **CONDITIONAL — D3 & D6 FAIL** | **Fabricated Table 2; dead verifier gate** |

## 2.1 Round-by-round detail

**Round 3 (`e39335c`).** Verified closed by execution: Gate 4b (strict rung adjacency),
Gate 4c (contiguous stacked clusters), integer POC indexing, Part C items F2 (gap fills at
`s1_liquidation_cascade.py:355/381`, true-range ATR at :193) and F3 (frozen IS threshold at
:823–826, `np.percentile(is_probs, 75)` clamped to [0.50, 0.65], causal threshold at :833).
**F1 not eliminated**: `mae_dollar = units * maes[i]` at :529 booked at entry (:535) and consumed
at :483/:510. Assessed as *conservative* — it charges maximum adverse excursion at entry, so it
cannot inflate ROI. Still open, still non-blocking.

**Round 4 (`b1a239e`).** Table 1 measured: 62 columns, 2020-09-01 → 2026-09-03 20:15, zero
nulls/Infs/gaps/non-monotonic bars. `rsi_14 ∈ [4.13, 95.62]`,
`long_liq_usd ∈ [−1.536e7, −2966.69]`, `short_liq_usd ∈ [4662.57, 2.943e7]`,
`metrics_available == 0` in 43,776 bars (20.79%). Daily VWAP anchor verified correct
(bar 0 `session_val` 431.0 vs close 432.52; bar 95 458.0 vs 475.61). The "EMA warmup handled"
claim was **false**: `ema_800` row 0 = 405.61 vs close 432.52 = **6.2217%** off. Ten synthetic
bars identified but untagged. `is_synthetic.sum() == 0`, dtype `int64`.

**Round 5 (`2ae529c`).** Four blocking findings, two closed:

| # | Claim | Round-5 verdict |
|---|---|---|
| 1 | `is_synthetic` tags 10 ETH bars, int8 | ❌ NOT CLOSED — `a == 1 \| b` parses as `a == (1 \| b)`; measured 0 tagged, int64 |
| 2 | Depth positive + ATR-scaled | ⚠️ code closed, committed data still negative |
| 3 | Table 2 committed, B.4 runnable | ✅ closed for ETH (0 orphans, 0 gaps, **384/210,610 = 0.182%** coverage); BTC master absent |
| 4 | Archetype mapping safeguarded | ✅ closed |

**Round 6 (`701aac2`) — this document.** The 18-symbol extraction was run and committed (999 MB).
`is_synthetic` and depth are now closed *in the data*. Coverage went from 0.182% to a nominal
100% — **by synthesising the missing 99.82%.**

## 2.2 A recurring pattern worth naming

Across six rounds the same failure mode has recurred three times: **a reported fix that is
correct in source but absent from the committed artifact**, or **an artifact that satisfies a
stated invariant because the invariant was enforced by construction rather than by measurement**.

- Round 4: `is_synthetic` "working" while summing to 0.
- Round 5: depth "positive" in code while the parquet held `−1.545e8`.
- Round 6: Table 2 "1:1 with Table 1" because missing rows were generated.

**The structural remedy is the same each time: the verifier must be able to fail.** Action item
P0-3 exists for this reason, and the closing recommendation of this document is to re-run the
verifier after applying P0-1…P0-4 and **confirm that it fails**.

---

# 3. DIMENSION 1 — MICROSTRUCTURE MATHS & CAUSAL INDICATOR SOUNDNESS
## Verdict: CONDITIONAL

### D1-1 · CRITICAL · Wilder RMA/RSI warmup is backfilled forward in time — **measured**

`Engine_2/core/canonical_indicators.py`:

```python
def compute_wilder_rma_series(values, period):
    ...
    rma[period - 1] = np.mean(values[:period])
    rma[:period - 1] = rma[period - 1]      # <-- bar i<period receives a value from bars 0..period-1
    for i in range(period, n):
        rma[i] = values[i] * alpha + rma[i - 1] * (1.0 - alpha)

def compute_wilder_rsi_series(closes, period=14):
    ...
    rsi[:period] = rsi[period]              # <-- bars 0..13 receive RSI computed from bars 0..14
```

**Measured on `APTUSDT_15m_master_2020_2026.parquet` (first bar 2022-10-19 02:00:00):**

```
atr_14[0]  = 0.5200     mean(TR[0:14])  = 0.5231   round(_,2) = 0.52    EQUAL ✓
atr_100[0] = 0.2300     mean(TR[0:100]) = 0.2343   round(_,2) = 0.23    EQUAL ✓
rsi_14[0] == rsi_14[13] == rsi_14[14] == 56.37                          EQUAL ✓
```

Bar 0 of `atr_100` therefore **contains bars 1 through 99 — 24.75 hours of future data**.
Contaminated ranges: `atr_100` bars 0–99, `atr_14` bars 0–13, `rsi_14` bars 0–13.

**Where it bites.** `run_historical_pipeline.py` fetches klines from `start_year=2019` and slices
to `start_date_str` **after** indicator computation:

```python
master_df = master_df[master_df['open_time_ms'] >= start_ms].copy()
```

So BTC, ETH, XRP, ADA, BNB, DOGE, DOT, LTC, TRX (all starting 2020-09-01) shed the contaminated
bars into the discarded 2019–2020 prefix. **Late-listed altcoins cannot**: APT (2022-10-19),
ARB (2023-03-23), SUI (2023-05-03), OP (2022-06-01) have no pre-listing history, so their first
100 bars carry forward-looking ATR **in the shipped parquet**. Verified above on APT. Those are
precisely the listing-spike bars a volatility-breakout archetype trades first.

**Fix:** emit `np.nan` for `i < period`, add a `warmup_valid` int8 column, mask or drop.

### D1-2 · MEDIUM · EMA cold-start bias with no validity flag — measured

`compute_ema_series` seeds `ema[0] = prices[0]` and never returns NaN:

```python
ema[0] = prices[0]
for i in range(1, n):
    ema[i] = prices[i] * k + ema[i - 1] * (1.0 - k)
```

**Measured on APT:**

```
ema_800[0]   = 7.30      close[0]   = 7.297      -> seed == close[0] ✓
ema_800[800] = 8.63      close[800] = 9.19       -> 6.09% apart
```

800 bars (8.3 days) into a 135,918-bar series the 800-EMA is still **6.09%** from price purely
from seed anchoring. `[prior-session]` the same measurement on ETH at `b1a239e` gave 6.2217% —
consistent. There is no `ema_800_valid` column, so a walk-forward window opening near a symbol's
inception silently trades a distorted trend filter. `compute_volume_sma9_series` uses an
expanding window for `i < 8` rather than NaN — causal, but the same class of unflagged bias.

### D1-3 · CRITICAL · The four order-book depth columns are degenerate — **measured, 100%**

```python
def estimate_depth_from_volatility(closes, atrs, base_vols):
    vol_scaling    = np.clip(1.0 / (np.maximum(atrs / np.maximum(closes, 1e-4), 0.001) * 100.0), 0.5, 2.0)
    bid_depth_coin = np.round(base_vols * 0.025 * vol_scaling, 4)
    ask_depth_coin = np.round(base_vols * 0.025 * vol_scaling, 4)   # IDENTICAL expression
    bid_depth_usd  = np.round(bid_depth_coin * closes, 2)
    ask_depth_usd  = np.round(ask_depth_coin * closes, 2)
    return bid_depth_usd, ask_depth_usd, bid_depth_coin, ask_depth_coin
```

**Measured: `bid_depth_coin == ask_depth_coin` in 100.00% of rows on all 18 masters** — all
**3,464,092** rows. Not approximately symmetric: *bit-identical*. Every bid/ask imbalance,
spread-proxy or book-pressure feature built on these columns is **exactly zero, in every market
condition, forever**.

They are also a rank-2 restatement of `volume_base`, `close` and `atr_14`: zero new information,
perfect collinearity with existing columns.

**`Engine_2/core/schema.py` contradicts the implementation.** It still documents:

```python
"bid_depth_usd",   # float64: Resting Bid liquidity in USD within +1%  (Indicator 14)
"ask_depth_usd",   # float64: Resting Ask liquidity in USD within -1%  (Negative, Indicator 15)
"bid_depth_coin",  # float64: Resting Bid liquidity in BTC within +1%  (Indicator 16)
"ask_depth_coin",  # float64: Resting Ask liquidity in BTC within -1%  (Negative, Indicator 17)
```

The sign was flipped in code; the data dictionary was not updated. Any consumer reading the
schema applies an inverted sign. Both are labelled "Resting liquidity within ±1%" — they are a
volatility-rescaled volume restatement, not a book measurement.

Measured ranges (BTC): `ask_depth_usd ∈ [0.00, 219,310,413.83]`; (ETH) `[0.00, 153,955,246.27]`.

### D1-4 · HIGH · `fp_poc` is destroyed by one-decimal rounding — **new finding**

`Engine_2/pipeline/historical_metrics_processor.py`:

```python
fallback_poc = np.round((df["high"].values + df["low"].values + 2.0 * df["close"].values) / 4.0, 1)
df["fp_poc"] = np.where(np.isnan(real_poc), fallback_poc, np.round(real_poc, 1))
```

Rounding a price to **one decimal place** is harmless at BTC scale and catastrophic below ~$10.
**Measured — distinct `fp_poc` values across each full 6-year master:**

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
| LINKUSDT | $13.297 | 476 | 30,697 | 0.01551 |
| DOTUSDT | $5.7560 | 540 | 36,325 | 0.01487 |
| AVAXUSDT | $20.335 | 1,367 | 71,268 | 0.01918 |
| SOLUSDT | $85.100 | 2,700 | 92,056 | 0.02933 |
| BCHUSDT | $342.72 | 9,247 | 57,698 | 0.16027 |
| BNBUSDT | $423.35 | 10,839 | 77,142 | 0.14051 |
| ETHUSDT | $2,264.46 | 38,440 | 148,032 | 0.25967 |
| LTCUSDT | $83.980 | 3,228 | 21,807 | 0.14803 |
| BTCUSDT | $48,870.20 | 181,477 | 187,117 | 0.96986 |

**TRX's Point of Control takes 5 possible values across 210,614 bars.** For 12 of 18 symbols
`fp_poc` is effectively a categorical with a handful of levels. Any distance-to-POC feature on
these assets measures distance to a coarse quantisation of price, not to the volume node.

**Fix:** round to the symbol's `daily_bin_step`, or store `fp_poc` unrounded.

### D1-5 · MEDIUM · Redundant and fabricated columns — measured

- **`fp_delta` is bit-identical to `future_cvd_15m` in 100% of rows on all 18 masters.**
  Both are assigned `fut_delta_15m`. Two column names, one array.
- `max_trade_vol_btc = np.round(vols_base * 0.05, 4)` whenever tick data is absent — a constant
  5% of volume, documented in `schema.py` as "Maximum single trade execution size in BTC". It is
  a scaled copy of `volume_base`.

### D1-6 · HIGH · Liquidation columns are model output, not exchange data — **branch confirmed**

`Engine_2/core/mathematical_liquidation_engine.py` header:

> *"Calibrated against 7,234 Ground-Truth 15m CoinGlass Liquidations (June - Aug 2026).
> Achieves >97% Linear Parity (R² > 94%) on out-of-sample squeeze events."*

The ExtraTrees models are committed and loaded at construction. The 20-feature matrix is built
exclusively from `w_down, w_up, body, range_pct, vol, base_vol, trades, taker_buy, taker_sell,
taker_delta`, their squares/cubes/products, and 1–3 bar lags — **every input is already a column
of Table 1**.

**Which branch produced the shipped data? Measured:**

| symbol | `long_liq` closest to 0 | `long_liq` min | `short_liq` min | `short_liq` max | % of bars with \|long_liq\| < 18500 |
|---|---|---|---|---|---|
| BTCUSDT | −774.28 | −19,224,121.93 | 1,962.74 | 43,412,137.04 | **26.01%** |
| ETHUSDT | −2,966.69 | −15,359,533.67 | 4,662.57 | 29,433,781.15 | 0.26% |
| APTUSDT | −2,966.69 | −6,104,084.23 | 15,999.24 | 14,378,394.38 | 0.00% |

The physics fallback adds `self.base_floor = 18500.0` to **every** bar on **both** sides, so it
could never produce `|long_liq| = 774.28`. **26.01% of BTC bars sit below the floor ⇒ the ML
branch produced the committed columns.** ETH's closest-to-zero value of −2,966.69 reproduces the
`[prior-session]` measurement at `b1a239e` exactly.

Consequences:

- **Zero new information.** Deterministic nonlinear functions of columns already present.
- **Out-of-support extrapolation.** A Jun–Aug 2026 calibration applied to 2020–2025. The
  ">97% parity, R²>94%" claim is scoped to that window and does not transfer to a 2021 regime.
- **Label-window overlap.** The training labels are from Jun–Aug 2026. Any OOS window covering
  that period consumes features whose generating model was fitted to that period's liquidation
  outcomes. Not bar-level lookahead, but a real contamination channel that must be disclosed or
  the columns retrained causally.
- **Reproducibility depends on the joblib files.** Without them the physics fallback yields
  materially different values, including the hard 18,500 floor per side per bar.

### D1-7 · Liquidation polarity — **PASS, measured on all 18**

`pol_ok = True` for every symbol: `long_liq_usd ≤ 0` and `short_liq_usd ≥ 0` in every row of all
3,464,092 bars. Both branches guarantee it:

```python
# ML branch
pred_long  = np.maximum(0.0, self.ml_long.predict(X))
pred_short = np.maximum(0.0, self.ml_short.predict(X))
return -np.round(pred_long, 2), np.round(pred_short, 2)

# Physics branch — long_liq is a sum of non-negative terms plus base_floor
return -np.round(long_liq, 2), np.round(short_liq, 2)
```

Buyer/seller differentiation is genuinely asymmetric: `cascade_long` keys off `w_down` and
`cascade_short` off `w_up`; `cvd_sell_term = k_cvd·max(0,−cvd)` vs
`cvd_buy_term = k_cvd·max(0,cvd)`; funding enters via `funding_bias_long` /
`funding_bias_short`; long scales with `ls_ratios`, short with `1/max(ls_ratios, 0.5)`.

### D1-8 · Boundedness — PASS

RSI: `100 − 100/(1+rs)` with `rs ≥ 0` ⇒ `[0,100]`; `avg_loss == 0` special-cased to 100 or 50;
pre-warmup filled from `rsi[period]`, itself in range. Measured `rsi_14` ranges across the 18
symbols span `[2.20, 98.55]` — inside bounds everywhere. ATR: max of non-negative true ranges,
RMA with `α = 1/p > 0` ⇒ non-negative; measured `atr_14 ∈ [0.55, 2098.44]`. `np.roll`
previous-close helpers correctly repair index 0 (`prev_closes[0] = closes[0]`), so those are
causal. **The defect is the warmup backfill (D1-1), not the bounds.**

### D1-9 · MEDIUM · `oi_change_pct` has uncontrolled discontinuity spikes — measured

`oi_change_pct = open_interest_k.pct_change() * 100`, with `±inf → NaN → 0`. There is **no
outlier clamp**. Measured across all 18:

| metric | value |
|---|---|
| max \|oi_change_pct\| across symbols | **16.42% (DOT) to 6,509.46% (BCH)** — a 396× spread |
| bars with \|oi_change_pct\| > 100% | **148** of 3,464,092 (0.0043%) |
| of those, > 1000% | **146** — bimodal, i.e. discontinuity not volatility |
| occurring at a `metrics_available` 0→1 transition | **0** — so they are mid-history feed gaps |

Worst case, BCHUSDT:

```
datetime_utc        oi_change_pct   open_interest_k   metrics_available
2025-01-08 18:15:00     6509.4611           271.054                   1
2024-08-12 11:15:00     4090.2839           276.014                   1
2024-07-14 15:45:00     4043.1635           313.016                   1
```

A 6,509% 15-minute OI change implies the prior bar was ~4.1k contracts — a 66× jump that is a
Binance metrics-feed discontinuity, not a market event. They are rare, but a single one dominates
any z-score, percentile rank or threshold feature for its entire rolling window.

**Fix:** winsorise `oi_change_pct` to a defensible bound (e.g. ±50%) and add an
`oi_discontinuity` int8 flag so strategies can exclude rather than absorb the bar.

### D1-10 · MEDIUM · `ffill()` runs over provenance strings

```python
final_df = final_df.ffill()
numeric = final_df.select_dtypes(include=[np.number]).columns
final_df[numeric] = final_df[numeric].fillna(0.0)
```

`ffill()` covers **all** columns including `future_flow_source`, `spot_flow_source`,
`poc_source`. A NaN source inherits the previous bar's label, so `TICK_EXACT` can propagate onto
bars that never had tick data. This corrupts the very labels a leakage audit relies on — and
§5.3 shows those labels are already wrong for 9 of 18 symbols.

**Fix:** exclude the three string columns from `ffill()`; fill with an explicit `"UNKNOWN"`.

### D1-11 · CVD, session value area, funding, basis — PASS

- `compute_session_cvd` resets at the UTC day boundary via `timestamps_ms[i] // (86400*1000)` and
  accumulates only through bar *i*. `future_cvd_lifetime = np.cumsum(...)`. Strictly causal.
- `compute_session_value_area` locks the prior day only at the boundary
  (`last_locked_vah = session_vah[i-1]`). Causal. `[prior-session]` the daily VWAP anchor was
  verified correct at `b1a239e` (bar 0 `session_val` 431.0 vs close 432.52; bar 95 458.0 vs
  475.61).
- Funding merged by `merge_asof(direction="backward")`, `.ffill()`, `nan → 0.0001`. Causal.
  Measured `funding_rate_pct ∈ [−0.3563, 0.3750]` (ETH), `[−0.1192, 0.2490]` (BTC).
- `basis_usd` measured `∈ [−246.33, 57.90]` (ETH), `[−1506.48, 936.77]` (BTC).
- Naming hazard: `future_cvd_*` denotes the **futures market**, not future information. Worth a
  comment in `schema.py`, since the name invites the opposite reading.

### D1-12 · Scope note · MACD, Bollinger Bands and Parkinson volatility do not exist

The 62-column contract contains `rsi_14`, `atr_14`, `atr_100` and five EMAs. There is **no
MACD** (line/signal/histogram), **no Bollinger** band or bandwidth, and **no Parkinson /
Garman-Klass / Rogers-Satchell** estimator. `compute_volume_sma9_series` is a *volume* SMA;
**there is no price simple moving average of any length in Table 1.** These three families are
absent, not merely unaudited — if the strategy set requires them they must be added.

---

# 4. DIMENSION 2 — FOOTPRINT LADDER & ORDER-FLOW IMBALANCE
## Verdict: CONDITIONAL — tick-path logic correct, tick-path coverage negligible

### D2-1 · Imbalance semantics: DIAGONAL — **CONFIRMED CORRECT** ✅

`Engine_2/pipeline/tick_footprint_fetcher.py`:

```python
ladder["bin_diff_below"] =  ladder.groupby("open_time_ms")["bin_idx"].diff(1)
ladder["bin_diff_above"] = -ladder.groupby("open_time_ms")["bin_idx"].diff(-1)

raw_s_vol_below = ladder.groupby("open_time_ms")["s_vol"].shift(1)
ladder["s_vol_below"] = raw_s_vol_below.where(ladder["bin_diff_below"] == 1, 0.0)
raw_b_vol_above = ladder.groupby("open_time_ms")["b_vol"].shift(-1)
ladder["b_vol_above"] = raw_b_vol_above.where(ladder["bin_diff_above"] == 1, 0.0)

ladder["buy_imbalance"] = (
    (ladder["b_vol"] >= 3.0 * np.maximum(ladder["s_vol_below"].fillna(0.0), 1e-4)) &
    (ladder["b_vol"] >= min_vol_floor) &
    (ladder["bin_diff_below"] == 1)).astype(int)

ladder["sell_imbalance"] = (
    (ladder["s_vol"] >= 3.0 * np.maximum(ladder["b_vol_above"].fillna(0.0), 1e-4)) &
    (ladder["s_vol"] >= min_vol_floor) &
    (ladder["bin_diff_above"] == 1)).astype(int)
```

Buy imbalance compares volume at rung *P* against *P−1* (`shift(1)`); sell imbalance compares
*P* against *P+1* (`shift(-1)`). **Diagonal, not inline**, at the documented 3.0× threshold.

**Adjacency is enforced twice over** — shifted volumes are masked to 0.0 **and** the predicate
independently ANDs `bin_diff == 1`. The masking alone would be defeated by
`np.maximum(·, 1e-4)`; the explicit conjunct is what makes it correct. A missing rung between
*P* and *P−1* suppresses the comparison rather than comparing across the gap. **Gate 4b holds.**

**Naming — document it, not a bug:** the export renames `b_vol → ask_vol_coin` and
`s_vol → bid_vol_coin`. This is the standard footprint convention (taker buys execute *at* the
ask), but it inverts the intuitive reading of the raw aggregates, and the diagonal rule reads
correctly only under that convention. It should be stated in the schema.

### D2-2 · Stacked imbalance: **CORRECT** ✅ [executed]

```python
def _calc_contiguous_stacked_clusters(df_bar, imb_col):
    bins = df_bar["bin_idx"].values; imbs = df_bar[imb_col].values
    n = len(bins)
    if n < 3: return 0
    cluster_count = 0; current_run = 0
    for k in range(n):
        if imbs[k] == 1:
            if k == 0 or (bins[k] - bins[k-1] == 1): current_run += 1
            else:
                if current_run >= 3: cluster_count += 1
                current_run = 1
        else:
            if current_run >= 3: cluster_count += 1
            current_run = 0
    if current_run >= 3: cluster_count += 1
    return cluster_count
```

Requires `bins[k] − bins[k−1] == 1` at every step of a run, run length ≥ 3, correct flush at run
breaks and at bar end. Results obtained by executing it:

| input `bin_idx` (imbalance = 1 throughout) | result |
|---|---|
| `[10, 11, 13]` | **0** (gap breaks the run) |
| `[10, 11, 12]` | 1 |
| run of 5 | **1** (not 3) |
| two separate runs of 3 | **2** (not 4) |
| `[10, 11]` | 0 (below the ≥3 threshold) |

### D2-3 · Point of Control: **PASS** ✅

```python
poc_df  = df.groupby(["open_time_ms", "bin_idx", "price_bin"])["quantity"].sum().reset_index()
poc_max = poc_df.loc[poc_df.groupby("open_time_ms")["quantity"].idxmax()][[...]]
...
ladder_export["is_poc"] = (ladder_export["bin_idx"] == ladder_export["poc_bin_idx"]).astype(int)
```

`idxmax` selects exactly one row per candle ⇒ exactly one POC per 15m bar. The flag is an
**integer `bin_idx` equality**, not floating-point price equality — no fragile float comparison
anywhere in the POC path. **Measured: `is_poc.sum() == nunique(open_time_ms)` on all 18 ladders**
(e.g. BTC 210,613 = 210,613; ADA 210,614 = 210,614).

Caveat: ties in max volume are broken by `idxmax`'s first-occurrence rule — deterministic but not
price-ordered.

### D2-4 · MEDIUM · The volume floor is not price-normalised

```python
min_vol_floor = np.maximum(ladder["total_vol_coin"] * 0.005, 0.05)
```

The relative leg (0.5% of bar volume) is sound. The absolute leg is **0.05 coin** — a fixed
*quantity*, not a fixed *notional*:

| symbol | approx. price | 0.05 coin ≈ USD |
|---|---|---|
| BTCUSDT | $100,000 | $5,000 |
| DOGEUSDT | $0.08 | **$0.004** |

On sub-dollar assets the noise filter is ~6 orders of magnitude weaker, so single-trade rungs
qualify as imbalances. The code comment claims *"At least 0.5% of bar volume or 5 trades"*; the
code uses 0.05 coin. Doc/code mismatch.

**Fix:** `min_vol_floor = max(0.005 * total_vol_coin, 0.005 * total_quote_vol / close)`.

### D2-5 · Dynamic bin stepping: implemented, two dead assignments, non-stationary

Correctly implemented:

```python
median_px = df["price"].median()
raw_step  = median_px * 0.00035                  # 3.5 bps as specified
if   raw_step >= 10.0:  daily_bin_step = round(raw_step / 5.0) * 5.0
elif raw_step >= 1.0:   daily_bin_step = round(raw_step, 1)
elif raw_step >= 0.1:   daily_bin_step = round(raw_step, 2)
elif raw_step >= 0.01:  daily_bin_step = round(raw_step, 3)
elif raw_step >= 0.001: daily_bin_step = round(raw_step, 4)
else:                   daily_bin_step = round(raw_step, 6)
daily_bin_step = max(daily_bin_step, 1e-6)
effective_bps  = round((daily_bin_step / median_px) * 10000.0, 2)
df["bin_idx"]   = np.round(df["price"] / daily_bin_step).astype(np.int64)
df["price_bin"] = df["bin_idx"] * daily_bin_step
```

An **int64 bin index** with the float price reconstructed from it — correct, and it eliminates
float-equality fragility throughout the ladder.

Three defects:

1. **Two dead assignments.** `bin_step = SYMBOL_BIN_STEPS.get(symbol, 0.001)` in
   `fetch_footprint` and `default_step = SYMBOL_BIN_STEPS.get(symbol, 0.001)` in
   `_process_daily_ticks` are assigned and **never read**. The 18-entry `SYMBOL_BIN_STEPS` table
   is dead code and its docstring *"Normalized to ~3-6 bps of nominal price"* is misleading. The
   inline comment *"bounded by exchange min tick"* is also false — the only floor is `1e-6`, not
   the exchange tick size.
2. **`price_bin` is not comparable across days.** `median_px` is a single daily file's median, so
   the step changes day to day. `fp_effective_bps` is computed on the summary frame and then
   **dropped** from the 9-column ladder export, so the rescaling factor is unrecoverable.
3. **Two grids coexist in one column — measured:**

| symbol | synthetic rung spacing | real tick rung spacing |
|---|---|---|
| BTCUSDT | **17.1** | **25.0** |
| ETHUSDT | **0.79** | **0.855** |

The same `price_bin` column mixes a full-sample-derived grid with a per-day grid. Absolute
`price_bin` values are meaningless across that boundary.

---

# 5. DIMENSION 3 — TIMELINE PARITY & REFERENTIAL INTEGRITY
## Verdict: FAIL

### D3-1 · CRITICAL · Parity is manufactured by synthesising fake ladders

`Engine_2/run_historical_pipeline.py`, step 3:

```python
existing_ts  = set(ladder_df["open_time_ms"].unique()) if not ladder_df.empty else set()
missing_mask = ~master_df["open_time_ms"].isin(existing_ts)

if missing_mask.any():
    print(f"[FOOTPRINT] Synthesizing full-history footprint ladder profile "
          f"for {missing_mask.sum():,} earlier bars to match Table 1...")
    df_missing = master_df[missing_mask].copy()
    median_px  = master_df["close"].median()          # <-- FULL-SAMPLE median
    raw_step   = median_px * 0.00035
    ...
    min_bins   = np.floor(l_vals / daily_bin_step).astype(np.int64)
    max_bins   = np.ceil (h_vals / daily_bin_step).astype(np.int64)
    bin_counts = np.maximum(1, max_bins - min_bins + 1)
    ...
    b_vol = rep_tbv / rep_counts                      # uniform across EVERY rung
    s_vol = rep_tsv / rep_counts
    net_delta = b_vol - s_vol
    poc_bins  = np.round(rep_c / daily_bin_step).astype(np.int64)   # rung nearest CLOSE
    is_poc    = (all_bins == poc_bins).astype(np.int8)

    synth_ladder = pd.DataFrame({
        "open_time_ms": rep_ots, "price_bin": prices,
        "bid_vol_coin": s_vol, "ask_vol_coin": b_vol, "net_delta_coin": net_delta,
        "is_buy_imbalance":  np.int8(0),              # <-- HARD ZERO
        "is_sell_imbalance": np.int8(0),              # <-- HARD ZERO
        "is_poc": is_poc,
        "trade_count": np.maximum(1, (rep_tc / rep_counts).astype(np.int64))
    })

    # Ensure exactly 1 POC per candle
    poc_sums  = synth_ladder.groupby("open_time_ms")["is_poc"].transform("sum")
    needs_poc = poc_sums == 0
    if needs_poc.any():
        first_idx = synth_ladder[needs_poc].groupby("open_time_ms").head(1).index
        synth_ladder.loc[first_idx, "is_poc"] = np.int8(1)
```

**Measured across all 18 ladders:**

| symbol | rungs | candles | orphan | coverage | master bars w/o rungs | `is_poc`==candles | **uniform candles** | imbalance flags | flag dtype |
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

Totals: **93,936,836 rungs · 10,721 imbalance flags (0.0114% of rungs) · 9 symbols with exactly
zero imbalance flags anywhere.**

Seven consequences, each measured:

**A · The rung distribution is degenerate.** Within uniform candles,
`nunique(net_delta_coin) ≤ 1` in **400/400** sampled candles for both BTC and APT. Every rung of
a synthetic bar carries the identical delta — the ladder conveys nothing beyond the bar aggregate.
These are genuinely multi-rung candles: BTC median 11 rungs / max 675; APT median 18 / max 1,247.

**B · Imbalance flags are identically zero.** In uniform candles BTC
`is_buy_imbalance.sum() = 0`, `is_sell_imbalance.sum() = 0`; same for APT. Across the whole
corpus: 10,721 flags in 93,936,836 rungs.

**C · `is_poc` marks the rung nearest the close, not max volume.** Measured on APT: POC within
one bar-range of close in **99.95%** of candles; median `|poc − close| / close = 0.00858%`. The
"exactly one POC per bar" invariant is satisfied by construction on fabricated data.

**D · No provenance column — the fatal one.** The exported schema is exactly:

```
open_time_ms, price_bin, bid_vol_coin, ask_vol_coin, net_delta_coin,
is_buy_imbalance, is_sell_imbalance, is_poc, trade_count
```

**No `is_synthetic`, no `source`, no `bin_step`.** It is impossible, from the committed file
alone, to distinguish a tick-derived rung from a fabricated uniform rung. Table 1 carries three
provenance columns; Table 2 — where provenance matters most — carries none.

**E · `trade_count` does not reconcile across tables.**
`np.maximum(1, (rep_tc / rep_counts).astype(np.int64))` floors per rung and clamps at 1:

| symbol | candles where `sum(ladder trade_count) != master trade_count` |
|---|---|
| BTCUSDT | **186,605 of 210,613 (88.60%)** |
| APTUSDT | **123,948 of 135,918 (91.19%)** |

**F · Lookahead in the synthetic bin step.** `median_px = master_df["close"].median()` is the
**full 2020–2026** median, used to size 2020 bins:

| symbol | full-sample median close | derived step | first-30-day median close | **actual bps in 2020** | vs 3.5 bps target |
|---|---|---|---|---|---|
| BTCUSDT | $48,870.20 | 17.1 | $10,660.09 | **16.04 bps** | **4.58× too coarse** |
| ETHUSDT | $2,264.46 | 0.79 | $363.29 | **21.75 bps** | **6.21× too coarse** |
| DOGEUSDT | $0.1043 | 3.7e-05 | $0.0028 | **133.43 bps** | **38.12× too coarse** |

Future information determines past rows. Confirmed in the emitted grid: BTC synthetic rung
spacing is exactly **17.1**, ETH **0.79**, APT **0.0021**.

**G · The flag dtype marks the fabrication boundary.** The 9 symbols with any real tick rungs
have `int64` flags (via `pd.concat` coercion); the 9 fully-synthetic symbols remain pure `int8`.
The dtype alone reveals which symbols received real ticks. The synthetic side also rounds
`price_bin` to 4 dp; the tick side does not round at all — so
`drop_duplicates(subset=["open_time_ms","price_bin"])` operates on inconsistently rounded keys.

### D3-2 · CRITICAL · The verifier's referential-integrity gate is dead code

`Engine_2/verification/verify_parquet_integrity.py`:

```python
ladder_valid = True
ref_valid    = True
if is_ladder:
    ladder_valid = bool(
        (df["trade_count"] > 0).all() and
        (df["price_bin"]   > 0).all() and
        df["is_poc"].isin([0, 1]).all() and
        df["is_buy_imbalance"].isin([0, 1]).all() and
        df["is_sell_imbalance"].isin([0, 1]).all())
    symbol_prefix = fname.split("_")[0]
    master_fname  = f"{symbol_prefix}_15m_master_2020_2026.parquet"
    master_path   = os.path.join(target_dir, master_fname)
    if os.path.exists(master_path):
        master_df_sample = pd.read_parquet(master_path, columns=["open_time_ms"])
        master_ts_set = set(master_df_sample["open_time_ms"].values)
        unmatched_ts  = set(unique_ts) - master_ts_set     # <-- COMPUTED, NEVER READ
# 3b. Master Specific Verification Gates
master_gates_valid = True
```

`unmatched_ts` is computed and **never read**. `ref_valid` is initialised `True` and never
reassigned, so it contributes `True` unconditionally to the final expression:

```python
status = "PASS" if (null_count == 0 and inf_count == 0 and num_gaps == 0 and is_monotonic
                    and rsi_valid and close_valid and liq_valid and ladder_valid
                    and ref_valid and master_gates_valid) else "FAIL"
```

- Orphaned candles **cannot** fail the audit.
- The reverse direction (master bars with zero rungs) is **never computed**.
- A missing master file silently passes (`if os.path.exists(...)` with no `else`) — precisely the
  BTC situation at round 5, when the ladder was committed but the master was not.

**Executed result:**

```
Found 36 Parquet files to audit
[PASS] ×36      (Nulls: 0 | Infs: 0 | Gaps: 0 | Monotonic: True, every file)
AUDIT SUMMARY: ALL PARQUET DATASETS 100% HEALTHY
Total Discrete 15m Records Audited: 93,936,836 candles
RETURNED: True
```

**Every defect in this document passed that audit.**

### D3-3 · CRITICAL · Table 1 and Table 2 contradict each other on provenance

For each master bar labelled `poc_source == "TICK_EXACT"`, is the corresponding ladder candle
uniform (i.e. synthetic)?

| symbol | master `TICK_EXACT` bars | of those, ladder candle is UNIFORM | non-uniform (real) |
|---|---|---|---|
| APTUSDT | 384 | **384** | **0** |
| XRPUSDT | 384 | **384** | **0** |
| BTCUSDT | 384 | 1 | 383 |

**For APT and XRP, Table 1 asserts exact tick provenance for 384 bars while Table 2 contains no
tick-derived rung for any of them.** The `footprint_df` summary and `ladder_df` diverged: the
summary populated `poc_source` / `fp_poc_vol_ratio` / `fp_stacked_*`, while the ladder export
arrived empty, so the synthesiser replaced every bar *including the tick window*.

Anyone filtering on `poc_source` to locate trustworthy footprint bars will select bars whose
ladder rungs are fabricated.

### D3-4 · No coverage assertion, and the fast-skip compares incompatible units

Nothing asserts `nunique(ladder.open_time_ms) == len(master)`. The runner clips the ladder to
`[min_master_ts, max_master_ts]` and stops. The skip guard:

```python
if os.path.exists(master_file) and os.path.exists(ladder_file):
    m_sample = pd.read_parquet(master_file, columns=["open_time_ms"])
    l_sample = pd.read_parquet(ladder_file, columns=["open_time_ms"])
    if len(m_sample) > 1000 and len(l_sample) > 1000:
        print(f"[SKIP] {symbol} already fully processed and verified "
              f"({len(m_sample):,} master bars, {len(l_sample):,} ladder rungs). Skipping.")
        return True
```

`l_sample` counts **rungs**, `m_sample` counts **candles**. A ladder of 1,001 rungs against a
210,000-bar master is 0.0005% coverage and would be declared "fully processed and verified".

---

# 6. DIMENSION 4 — DATA HYGIENE & BOUNDARY INVARIANTS
## Verdict: CONDITIONAL

### D4-1 · Gates that are live, correct, and pass

Executed across all 36 files:

| Gate | Implementation | Result |
|---|---|---|
| Zero nulls | `int(df.isnull().sum().sum())` | **0 on all 36** ✅ |
| Zero Infs | `np.isinf(df[num_cols].to_numpy()).sum()` | **0 on all 36** ✅ |
| 900,000 ms spacing (master) | `np.where(np.diff(ts) != 900000)[0]` | **0 gaps on all 18** ✅ |
| Strict monotonicity | `np.all(time_diffs > 0)` — duplicates also fail | **True on all 18** ✅ |
| Ladder candle spacing | `np.diff(np.unique(ts)) != 900000` | **0 gaps on all 18** ✅ |
| Ladder intra-candle order | `np.all(np.diff(timestamps) >= 0)` | True ✅ |
| `rsi_14 ∈ [0,100]` | `(rsi_14 >= 0).all() and (rsi_14 <= 100).all()` | True ✅ |
| `close > 0` | | True ✅ |
| Liq polarity | `long_liq_usd <= 0 and short_liq_usd >= 0` | True ✅ |
| Ladder `trade_count > 0`, `price_bin > 0`, flags ∈ {0,1} | | True ✅ |
| `ask_depth_usd >= 0` | | True ✅ |
| `is_synthetic` int8 + tagged if flat-zero bars exist | | True (weak, see D4-4) ⚠️ |

**These gates are real and they genuinely pass.** Master row counts: 210,613–210,614 for
full-history symbols; APT 135,918, ARB 120,900, SUI 117,046, OP 149,310, NEAR 206,358,
SOL 209,337, AVAX 208,474 (listing-date bounded, as expected).

### D4-2 · `ask_depth_usd` non-negativity — **CLOSED, measured on all 18**

`ask_depth_usd.min() == 0.0` for every one of the 18 masters. Guaranteed by construction:
`ask_depth_coin = round(base_vols * 0.025 * vol_scaling, 4)` with `base_vols ≥ 0`,
`vol_scaling = clip(·, 0.5, 2.0) > 0`, `closes > 0`.
`[prior-session]` this measured **−1.545e8** at `2ae529c`. The code fix has now reached the data.

### D4-3 · Manifest arithmetic — internally consistent ✅

`BTCUSDT_dataset_manifest.json` and `ETHUSDT_dataset_manifest.json` both declare
`total_rows: 210613`, `column_count: 62`, `2020-09-01 00:00:00 → 2026-09-03 21:00:00`.

```
2020-09-01 → 2026-09-01 = 6 years incl. the 2024 leap day = 2,191 days
+ 2 days to 2026-09-03                                     = 2,193 days
2,193 × 96 + 85 (00:00 through 21:00 inclusive)            = 210,613   ✓ exact
```

The verifier independently confirms the files really do hold 210,613 rows with zero gaps, and the
62-column list matches `CANONICAL_COLUMNS` in `core/schema.py`.

### D4-4 · `is_synthetic` assertion is correct but too weak

```python
if "is_synthetic" in df.columns:
    has_flat_zero_bars = bool(((df["high"] == df["low"]) & (df["volume_base"] == 0.0)).any())
    synth_tagged       = bool((df["is_synthetic"] == 1).any())
    dtype_valid        = (df["is_synthetic"].dtype == np.int8 or df["is_synthetic"].dtype == "int8")
    if has_flat_zero_bars and not synth_tagged:
        master_gates_valid = False
    if not dtype_valid:
        master_gates_valid = False
```

`.any()` asserts *at least one* tagged bar. It happens to be exactly right today (§7.1), but a
pipeline tagging 1 of 10 degenerate bars would pass. It should assert an exact count:

```python
expected = int(((df["high"] == df["low"]) &
                ((df["volume_base"] == 0.0) | (df["trade_count"] == 0))).sum())
assert int((df["is_synthetic"] == 1).sum()) == expected, fname
```

Note the verifier's predicate uses `volume_base` / `trade_count` while the processor's uses
`volume` / `count` — two definitions of "degenerate" that can silently drift.

### D4-5 · LOW · The headline record count overstates candles **27.12×**

```python
if "master" not in fname:
    total_records += rows
...
print(f"Total Discrete 15m Records Audited: {total_records:,} candles")
```

This accumulates **ladder rungs** and *skips* masters, then reports the sum as "candles":

```
sum of LADDER rungs   = 93,936,836   <-- the printed figure
sum of MASTER candles =  3,464,092   <-- the actual candle count
overstatement factor  = 27.12×
```

### D4-6 · Missing invariants

- `is_poc.sum() == nunique(open_time_ms)` — **never asserted** (it happens to hold on all 18).
- Ladder `trade_count` reconciled to master — **never checked** (fails on 88–91% of candles).
- **Uniform-rung detection** — the fabrication signature is trivially detectable
  (`groupby(open_time_ms)['bid_vol_coin'].nunique() <= 1`) and nothing looks for it.
- Master row count vs manifest `total_rows` — never checked.
- Per-column min/max/dtype report — none produced.
- Cross-table provenance consistency (§5.3) — never checked.
- `oi_change_pct` outlier bound — never checked (§3, D1-9).

### D4-7 · MEDIUM · Manifests carry no integrity fingerprint

`Engine_2/pipeline/parquet_exporter.py` writes only:

```python
manifest = {"symbol", "timeframe", "total_rows", "columns", "column_count",
            "start_time_utc", "end_time_utc", "exported_at_utc",
            "master_file", "master_size_mb"}
```

**No SHA-256, no per-column min/max, no null counts, no schema hash — and no record of Table 2 at
all.** A committed parquet cannot be verified against its manifest, and the manifest is silent on
the ladder that is supposed to be relationally bound to it.

### D4-8 · LOW · Non-portable defaults

`ParquetExporter.__init__` defaults to `r"G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min"`;
`verify_parquet_integrity.py`'s docstring names the same Windows/Drive path. The runner overrides
`output_dir` to the repo path, so this is cosmetic — but both modules are non-runnable standalone
off Windows.

---

# 7. DIMENSION 5 — SYNTHETIC TAGGING & MAINTENANCE ISOLATION
## Verdict: CONDITIONAL — tagging CLOSED, isolation not addressed

### D5-1 · ✅ `is_synthetic` is genuinely fixed — code **and** all 18 parquets

`Engine_2/pipeline/historical_metrics_processor.py`:

```python
# Flag degenerate maintenance bars (flat prices and zero volume/trades delivered during downtime)
degenerate = ((df["high"] == df["low"]) & ((df["volume"] == 0.0) | (df["count"] == 0)))
df["is_synthetic"] = np.where((df["is_synthetic"] == 1) | degenerate, 1, 0).astype(np.int8)
```

**The parentheses are present.** At round 5 this read
`np.where(df["is_synthetic"] == 1 | degenerate, 1, 0)`. Python binds `|` tighter than `==`, so it
parsed as `is_synthetic == (1 | degenerate)`; since `1 | <bool Series>` is all-1s, the degenerate
term was discarded entirely and the column tagged **zero** bars while being reported as working.

**Measured on all 18 masters:**

| check | result |
|---|---|
| dtype | **`int8` on all 18** |
| `is_synthetic == 1` total | **161** |
| degenerate bars by predicate | **161** |
| per-symbol exact match | **18/18** |
| BTC | **15 tagged / 15 degenerate** |
| ETH, ADA, AVAX, BCH, BNB, DOGE, DOT, LINK, LTC, NEAR, SOL, TRX, XRP | 10 / 10 each |
| APT, ARB, OP, SUI | 4 / 4 each |

The previously stated claim — *ETH 10 tagged, BTC 15, stored int8* — is now **true and verified**.

**ETH's 10 tagged bars** (identical to the `[prior-session]` list, confirming continuity):

```
2021-03-02 01:15 / 01:30 / 01:45   @ 1565.00   (OHLC all equal, vol 0, trades 0)
2022-05-01 22:30                   @ 2802.08
2022-05-28 16:45 / 17:00           @ 1793.84
2024-10-28 20:00 / 20:15 / 20:30 / 20:45  @ 2503.77
```

**BTC's 15 tagged bars:**

```
2021-03-02 01:15 / 01:30 / 01:45   @ 49361.01
2022-05-01 22:30                   @ 38275.00
2022-05-28 16:45 / 17:00           @ 28999.00
2023-11-10 15:15 / 15:30 / 15:45 / 16:00 / 16:15  @ 37118.40
2024-10-28 20:00 / 20:15 / 20:30 / 20:45          @ 69566.10
```

The dates coincide across symbols — these are genuine Binance futures outages, correctly
identified. Fragility note: `degenerate` references the raw kline names `volume` and `count`,
which exist at that point but are renamed to `volume_base` / `trade_count` further down. Move the
block below the rename and it raises `KeyError`.

### D5-2 · Interpolation mechanism — sound ✅

```python
expected_ms = np.arange(start_ms, end_ms + 900_000, 900_000, dtype=np.int64)
df["is_synthetic"] = 0
if len(df) != len(expected_ms) or not np.array_equal(df["open_time"].values, expected_ms):
    df = df.set_index("open_time").reindex(expected_ms)
    df["close_time"] = df["open_time"] + 899_999
    df["is_synthetic"] = np.where(df["close"].isna(), 1, 0).astype(np.int8)   # tagged BEFORE fill
    df["close"] = df["close"].ffill()                    # causal only
    df["open"]  = df["open"].fillna(df["close"])
    df["high"]  = df["high"].fillna(df["close"])
    df["low"]   = df["low"].fillna(df["close"])
    for col in ["volume", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume"]:
        if col in df.columns: df[col] = df[col].fillna(0.0)
```

No bfill anywhere; the comment *"Forward fill prices causally (strictly NO lookahead bfill)"*
matches the code. Volume is zeroed during downtime rather than interpolated. Correct.

### D5-3 · MEDIUM · One flag conflates two distinct conditions

`is_synthetic` is 1 for both (a) bars the pipeline *created* by reindexing across an outage and
(b) genuine exchange-printed bars that happen to be flat with zero volume. A strategy filtering
`is_synthetic == 1` silently drops authentic bars; one that keeps them computes rolling features
across fabricated prices. These should be two columns — `is_interpolated` and `is_degenerate` —
or at minimum the counts recorded in the manifest.

### D5-4 · HIGH · No isolation of rolling features, and the 5R mandate is ATR-normalised

Nothing stops `ema_*`, `atr_14`, `atr_100`, `rsi_14`, `volume_sma9`, `future_cvd_lifetime` or
`oi_change_pct` from being computed *through* synthetic bars. A run of flat zero-volume bars
decays `atr_14` toward zero and then spikes on resumption. Since the mandate is a **5R
ATR-normalised trailing stop**, that artifact lands directly in stop placement and position
sizing. The dataset supplies the flag but no `*_clean` variants and no documented handling
contract.

---

# 8. DIMENSION 6 — INSTITUTIONAL BACKTESTING VIABILITY
## Verdict: FAIL

### D6-1 · CRITICAL · Table 2 cannot support rung-level features as shipped

For 99.76–100% of candles, Table 2 is: uniform volume spread, constant `net_delta_coin` within
each candle, `is_buy_imbalance = is_sell_imbalance = 0`, `is_poc` at the rung nearest the close,
**and no column identifying any of it as synthetic**.

A researcher joining Table 2 to Table 1 today sees 100% candle coverage, zero orphans, exactly
one POC per bar, zero nulls, zero Infs, and a verifier reporting 100% health. They would
reasonably conclude footprint coverage is complete. **That is a worse failure mode than the
0.182% coverage reported at round 5, because it is invisible.**

Corroborating Table 1 sparsity (measured):

| metric | value |
|---|---|
| bars with **any** stacked imbalance, all 18 symbols | **1,124 of 3,464,092 (0.0324%)** |
| `fp_poc_vol_ratio > 0` | 288–384 bars per symbol |
| `poc_source == "TICK_EXACT"` | 0.18–0.33% of bars |
| `future_flow_source == "TICK_EXACT"` | 0.18–0.33% of bars |
| `spot_flow_source == "SPOT_EXACT"` | **97.5–100% of bars** (genuinely real) |

Per-symbol stacked-imbalance bar counts: APT 131 (0.0964%), XRP 57, SOL 51, ETH 45, BTC 42,
**ADA 0, NEAR 0**. `[prior-session]` at `2ae529c`, `FP_AbsorptionCluster` was reachable on 105
bars (0.050%) of ETH, all inside 2026-08-30 → 2026-09-02 — entirely after the OOS protocol end of
2026-04-15.

### D6-2 · The 5R trailing mandate has no price data to run against

Table 1 is 15m OHLCV; Table 2 is a price/volume ladder with no intra-bar timing. A 5R trailing
stop needs intra-bar path information to determine whether the trail was hit before the target.
With 15m bars only the conservative worst-case rule applies, and that ambiguity is large.

**`[prior-session]` irreducible baselines** (measured on raw klines, independent of this
pipeline):

| stop distance | P(+5R before −1R) |
|---|---|
| 0.35% | **16.51% ETH · 16.50% BTC · 16.38% SOL** |
| 0.65% | 25.2% |
| 1.00% | 22.2% |

At 33 bps round-trip cost = 0.94R per trade, **breakeven win probability = 32.3%**. The 0.35%
stop's 16.5% base rate is roughly half of breakeven. Median stop distance measured at 0.5622% of
price implies ~0.59R of slippage, not the 1.25R previously assumed.

**The schema does not resolve this ambiguity; only tick or 1m data can.**

### D6-3 · Remaining leakage channels

1. **`long_liq_usd` / `short_liq_usd`** — ML models trained on Jun–Aug 2026 CoinGlass labels,
   applied across 2020–2026 (§3, D1-6). Branch confirmed by measurement.
2. **`median_px = master_df["close"].median()`** — a full-sample statistic sizing 2020 bins
   (§5, D3-1-F), quantified at 4.58× / 6.21× / 38.12× too coarse.
3. **RMA/RSI warmup backfill and EMA seeding** (§3, D1-1 / D1-2) — measured live on APT.
4. **`ffill()` over provenance strings** (§3, D1-10) corrupts the labels a leakage audit relies
   on — and §5.3 shows those labels are already wrong for 9 of 18 symbols.

### D6-4 · Structural bottlenecks

1. **Committed data is frozen.** The fast-skip returns `True` for any symbol whose master and
   ladder both exceed 1,000 rows. Re-running the pipeline will not regenerate the 54 parquets;
   every fix in §11 requires deleting files first.
2. **The tick cache is never invalidated.** `_process_daily_ticks` returns the cached parquet
   whenever `{symbol}-footprint-15m-{ymd}.parquet` exists. No version stamp in the filename, so
   the committed ladders can embed an arbitrary mixture of logic versions, and a rule change
   silently never reaches cached days.
3. **Full-history ticks are opt-in and unbudgeted.** `--footprint-days` defaults to **0**;
   `--all-footprint` is a flag. Full history is ~2,193 daily aggTrades zips × 18 symbols
   ≈ **39,500 files**. The measured 383–384 tick candles per symbol confirm this never ran.
4. **999 MB of binary in git.** 18 masters (27–54 MB each), 18 ladders (8.8–20.2 MB each), two
   joblib models (25.6 + 22.5 MB). This makes the repo uncloneable for most consumers and exceeds
   artifact caps in constrained workspaces. Parquet and models belong in object storage;
   manifests and checksums belong in git.
5. **`verify_all_parquets` audits the whole directory** on every per-symbol run, yet
   `--all-symbols` passes `run_audit=False` per symbol.
6. **Network dependency is unbounded and unthrottled.** `_fetch_url` retries 3× with
   `1.0 * (attempt + 1)` backoff against `data.binance.vision`; at ~39,500 files this needs a
   resumable, checkpointed downloader with rate limiting, not a thread pool over a list.

### D6-5 · The two-table split is the right design

Separating 15m macro/micro features from a high-resolution ladder is correct for walk-forward
work, and the 62-column Table 1 contract is coherent, well-commented and matches its manifest.
The failure is not architectural — it is that Table 2 mixes real and fabricated data in one file
with no way to tell them apart, and Table 1's provenance columns actively misreport it.

---

# 9. STRATEGY-LEVEL CONTEXT

Included because this document is intended to be read standalone.

## 9.1 S1 liquidation cascade — walk-forward result

**`[prior-session]` 20-window IS/OOS walk-forward, frozen thresholds:**

| metric | value |
|---|---|
| Windows passed | **0 of 20** |
| Mean ROI | **−1.36%** |
| Win rate | 27.7% |
| Max drawdown | 5.48% |
| Window W03 | reported "+18.72%", actual **−0.75%** after costs |

Against a 32.3% breakeven win probability (§8.2), a 27.7% realised win rate is a structural
shortfall, not a tuning problem.

## 9.2 Regime → archetype mapping — verified closed

`Engine_2/s1_liquidation_cascade.py:648-654`:

| regime | archetype |
|---|---|
| Bull Mania | `V2_VWAPContinuation` |
| Bull Trend / Bull Pullback | `V2_VWAPContinuation` |
| **Crash / Flush** | **`A1_VolBreakout`** |
| **Compression** | **`V1_VWAPMeanRevert`** |
| Bear Trend | `A4_UltraDeepValue` |

**No regime maps to a footprint-dependent archetype**, so no pre-2026 walk-forward window can be
skipped for lack of tick data. `FP_AbsorptionCluster` (L637-644) is unreachable from the map; its
`spot_cvd_delta` OR-fallback is loose enough to fire on nearly any bar with the right CVD sign
plus the liquidation / `p8` condition — validate before re-wiring.

## 9.3 Part C items (S1 backtester)

| ID | Item | Status |
|---|---|---|
| F1 | `mae_dollar = units * maes[i]` (L529) booked at entry (L535), consumed L483/L510 | **OPEN, non-blocking** — charges MAE at entry, so it is *conservative* and cannot inflate ROI |
| F2 | Gap fills at L355/L381; true-range ATR at L193 | **CLOSED** |
| F3 | Frozen IS threshold L823-826: `np.percentile(is_probs, 75)` clamped to [0.50, 0.65]; causal threshold L833 | **CLOSED** |

## 9.4 Process integrity note

`[prior-session]` `s2_status.json` was observed to change SHA while retaining previously
discredited test-set-snooped results. **Status files must not be treated as evidence.** Every
claim in this document was re-derived from source or data, never from a status artifact.

---

# 10. DEFECT REGISTER

| ID | Severity | Dimension | Defect | Measured evidence | Status |
|---|---|---|---|---|---|
| **X-01** | CRITICAL | 3 | Table 2 parity achieved by uniform-spread synthesis | 99.76–100% of candles uniform, all 18 symbols | **OPEN** |
| **X-02** | CRITICAL | 3 | Table 2 has no provenance column | 9-column schema, no `is_synthetic`/`source`/`bin_step` | **OPEN** |
| **X-03** | CRITICAL | 3 | Verifier referential gate is dead code | `unmatched_ts` computed, never read; `ref_valid` hard-`True`; verifier returns `True` | **OPEN** |
| **X-04** | CRITICAL | 3/6 | Table 1 `poc_source` contradicts Table 2 | APT 384/384, XRP 384/384 TICK_EXACT bars have uniform ladders | **OPEN** |
| **X-05** | CRITICAL | 1 | RMA/RSI warmup backfill = lookahead | APT `atr_100[0] == mean(TR[0:100])`; live on APT/ARB/OP/SUI | **OPEN** |
| **X-06** | CRITICAL | 1 | Depth columns bit-identical bid/ask | 100.00% of 3,464,092 rows | **OPEN** |
| **X-07** | HIGH | 1 | `fp_poc` rounded to 1 decimal | TRX 5, DOGE 8, ARB 24, ADA 31, XRP 35 distinct values | **OPEN** |
| **X-08** | HIGH | 1 | Liquidation columns are 2026-trained model output | 26.01% of BTC bars below the 18,500 physics floor ⇒ ML branch | **OPEN** |
| **X-09** | HIGH | 3 | Synthetic bin step from full-sample median | BTC 16.04 / ETH 21.75 / DOGE 133.43 bps in 2020 vs 3.5 target | **OPEN** |
| **X-10** | HIGH | 3 | Ladder `trade_count` ≠ master | BTC 88.60%, APT 91.19% of candles | **OPEN** |
| **X-11** | HIGH | 5 | No rolling-feature isolation from synthetic bars | ATR decays to 0 across flat runs; 5R stop is ATR-normalised | **OPEN** |
| **X-12** | MEDIUM | 1 | `oi_change_pct` uncontrolled spikes | 148 bars > 100%; BCH max 6,509.46%; 0 at metrics transitions | **OPEN** |
| **X-13** | MEDIUM | 1 | EMA cold-start bias, no validity flag | APT `ema_800` 6.09% off close at bar 800 | **OPEN** |
| **X-14** | MEDIUM | 1 | `ffill()` over provenance strings | `final_df.ffill()` covers all columns | **OPEN** |
| **X-15** | MEDIUM | 2 | Volume floor not price-normalised | 0.05 coin = $5,000 (BTC) vs $0.004 (DOGE) | **OPEN** |
| **X-16** | MEDIUM | 2 | `price_bin` non-stationary; `fp_effective_bps` dropped | BTC synthetic 17.1 vs tick 25.0 in one column | **OPEN** |
| **X-17** | MEDIUM | 3 | No coverage assertion; fast-skip unit-blind | rungs vs candles both tested `> 1000` | **OPEN** |
| **X-18** | MEDIUM | 4 | `is_synthetic` assertion uses `.any()` | would pass on 1-of-10 tagging | **OPEN** |
| **X-19** | MEDIUM | 4 | Manifests carry no checksum / Table 2 record | 10 keys, no SHA-256 | **OPEN** |
| **X-20** | MEDIUM | 5 | One flag conflates interpolated vs degenerate | 161 bars, both classes | **OPEN** |
| **X-21** | MEDIUM | 6 | Committed data frozen by fast-skip | 54 parquets will not regenerate | **OPEN** |
| **X-22** | MEDIUM | 6 | Tick cache never invalidated, no version stamp | `{symbol}-footprint-15m-{ymd}.parquet` | **OPEN** |
| **X-23** | MEDIUM | 6 | 999 MB binary in git | 18 masters + 18 ladders + 2 joblib | **OPEN** |
| **X-24** | LOW | 1 | `fp_delta` duplicates `future_cvd_15m` | bit-identical, all 18 | **OPEN** |
| **X-25** | LOW | 1 | `max_trade_vol_btc = volume_base * 0.05` fallback | constant 5% of volume | **OPEN** |
| **X-26** | LOW | 1 | `schema.py` documents ask depth as "Negative" | contradicts positive implementation | **OPEN** |
| **X-27** | LOW | 2 | `SYMBOL_BIN_STEPS` dead code (2 assignments) | never read | **OPEN** |
| **X-28** | LOW | 4 | `total_records` counts rungs as "candles" | 93,936,836 vs 3,464,092 = 27.12× | **OPEN** |
| **X-29** | LOW | 4 | Non-portable Windows/Drive default paths | `G:\My Drive\...` | **OPEN** |
| **X-30** | INFO | 1 | MACD / Bollinger / Parkinson / price-SMA absent | not in the 62-column schema | **OPEN** |
| **X-31** | INFO | 9 | F1 MAE-at-entry in S1 backtester | conservative, cannot inflate ROI | **OPEN, non-blocking** |
| ~~X-32~~ | — | 5 | `is_synthetic` precedence bug | int8, 161 = 161, 18/18 exact | **CLOSED this round** |
| ~~X-33~~ | — | 4 | `ask_depth_usd` negative | `min() == 0.0` on all 18 | **CLOSED this round** |
| ~~X-34~~ | — | 2 | Gate 4b rung adjacency | correct at `701aac2` | **CLOSED** |
| ~~X-35~~ | — | 2 | Gate 4c stacked contiguity | correct; executed truth table | **CLOSED** |
| ~~X-36~~ | — | 2 | Integer POC indexing | `is_poc.sum() == candles` on all 18 | **CLOSED** |
| ~~X-37~~ | — | 9 | F2 gap fills / F3 frozen IS threshold | verified at `e39335c` | **CLOSED** |
| ~~X-38~~ | — | 9 | Pre-2026 windows skipped by archetype map | no regime maps to a footprint archetype | **CLOSED** |

---

# 11. PRIORITIZED ACTION PLAN

## P0 — blocking. Do not run any backtest until these are closed.

| # | Action | Files | Acceptance criterion |
|---|---|---|---|
| **P0-1** | **Add provenance to Table 2** — `rung_source` int8 (`0 = TICK_EXACT`, `1 = SYNTH_UNIFORM`), populated by both the tick and synthetic paths | `tick_footprint_fetcher.py`, `run_historical_pipeline.py` | Ladder schema has 10 columns; `rung_source` distribution matches the measured uniform-candle counts in §5.1 |
| **P0-2** | **Stop co-mingling real and fabricated rungs.** Delete the uniform-spread synthesis, or write it to `{symbol}_15m_ladder_synthetic.parquet` that no strategy reads by default | `run_historical_pipeline.py` | The primary ladder file contains only `rung_source == 0` rungs |
| **P0-3** | **Make the verifier able to fail.** `ref_valid = len(unmatched_ts) == 0`; add the reverse check (master bars with zero rungs); fail when the master file is absent; assert `is_poc.sum() == nunique(open_time_ms)`; **add a uniform-rung detector**; assert ladder↔master `trade_count` reconciliation | `verify_parquet_integrity.py` | **Verifier returns `False` on the current data** |
| **P0-4** | **Fix the cross-table provenance contradiction.** When the ladder export is empty but `footprint_df` is not, fail loudly or set `poc_source` to a distinct value — never silently synthesise over the tick window | `run_historical_pipeline.py`, `historical_metrics_processor.py` | No bar is labelled `TICK_EXACT` while its ladder candle is uniform |
| **P0-5** | **Remove the full-sample `median_px` leak.** Use the day's own or an expanding median; emit `bin_step` / `fp_effective_bps` as a ladder column | `run_historical_pipeline.py`, `tick_footprint_fetcher.py` | Early-period bps within 2× of the 3.5 target; `bin_step` present in the ladder |
| **P0-6** | **Fix `fp_poc` resolution** — round to the symbol's bin step, not to 1 decimal place | `historical_metrics_processor.py` | TRX distinct `fp_poc` > 10,000 (currently 5) |
| **P0-7** | **Scope and rename the liquidation columns** to `long_liq_usd_model` / `short_liq_usd_model`; record the Jun–Aug 2026 training window in the manifest; exclude that window from any OOS window using them, or retrain causally on a rolling window | `mathematical_liquidation_engine.py`, `schema.py`, `parquet_exporter.py` | Manifest records the training window; no OOS window overlaps it |
| **P0-8** | **Fix the RMA/RSI warmup backfill** — emit NaN for `i < period`, add `warmup_valid` int8, mask or drop | `canonical_indicators.py` | APT `atr_100[0]` is NaN or masked, not `mean(TR[0:100])` |

**Sequencing note:** P0-1, P0-2, P0-5 and P0-6 change the *content* of Tables 1 and 2. Complete
them **before** committing to the ~39,500-file full tick extraction, not after — otherwise the
extraction has to be repeated.

## P1 — high

| # | Action | Acceptance criterion |
|---|---|---|
| P1-9 | Exclude `future_flow_source`, `spot_flow_source`, `poc_source` from `final_df.ffill()`; fill with `"UNKNOWN"` | No provenance label is inherited |
| P1-10 | Strengthen the `is_synthetic` assertion to an exact count match; split `is_interpolated` from `is_degenerate` | Verifier fails if tagged ≠ degenerate |
| P1-11 | Price-normalise `min_vol_floor` → `max(0.005 * total_vol_coin, 0.005 * total_quote_vol / close)`; fix the "5 trades" comment | DOGE floor ≈ BTC floor in USD terms |
| P1-12 | Winsorise `oi_change_pct` (e.g. ±50%) and add an `oi_discontinuity` int8 flag | No \|oi_change_pct\| > bound; 148 bars flagged |
| P1-13 | Delete the dead `SYMBOL_BIN_STEPS` lookups or use them as a floor; correct the false "bounded by exchange min tick" comment | No unused assignments |
| P1-14 | Fix `total_records` to count master candles; report rungs separately | Prints 3,464,092, not 93,936,836 |
| P1-15 | Add SHA-256, per-column min/max, null counts, a schema hash and a Table 2 summary to each manifest; assert file `total_rows` against the manifest | Manifest ↔ file cross-check passes |

## P2 — medium

| # | Action |
|---|---|
| P2-16 | Drop `fp_delta` (bit-identical to `future_cvd_15m`); source `max_trade_vol_btc` from ticks or null it rather than writing `volume_base * 0.05` |
| P2-17 | Resolve the four depth columns: drop them (bit-identical bid/ask ⇒ identically-zero imbalance) or source real book snapshots. Update `schema.py`, which still calls both ask columns "Negative" |
| P2-18 | Add MACD / Bollinger / Parkinson / a price SMA if the strategy set requires them |
| P2-19 | Make the tick cache version-aware (`{symbol}-footprint-15m-v{N}-{ymd}.parquet`); replace the `> 1000 rows` fast-skip with a manifest-driven completeness check comparing **candles**, not rungs |
| P2-20 | Move parquet and joblib artifacts to object storage; keep manifests and checksums in git |
| P2-21 | Add a resumable, rate-limited, checkpointed downloader for the ~39,500 aggTrades files |
| P2-22 | Fix the `ParquetExporter` default Drive path and the verifier docstring |
| P2-23 | Document the `b_vol → ask_vol_coin` / `s_vol → bid_vol_coin` convention in the schema |
| P2-24 | Emit `ema_*_valid` flags, or drop the first `3 × period` bars per symbol |

## Closing recommendation

**Apply P0-1 through P0-4, then re-run:**

```bash
python3 -m Engine_2.verification.verify_parquet_integrity Engine_2/binance_backtesting_data
```

**and confirm that it FAILS.** A verifier that cannot fail is not a gate. Once it fails on the
fabricated rungs and the provenance contradiction, fix the data, re-run, and only then treat a
PASS as evidence.

---

# 12. WHAT WAS NOT VERIFIED

Stated plainly, because an unverified claim presented as fact is the failure mode this review
exists to catch.

1. **The liquidation joblib models were not loaded or interrogated.** The Jun–Aug 2026 training
   window, the 7,234 label count and the R² > 94% figure are taken from the module docstring, not
   from a refit or from the joblib metadata. Which *branch* produced the data **was** verified
   indirectly (§3, D1-6).
2. **No end-to-end pipeline run.** Network egress to `data.binance.vision` has been blocked in
   this environment in prior sessions (TLS EOF); no live tick fetch was attempted.
3. **The tail of `run_historical_pipeline.py`** — the post-`--all-symbols`-loop audit invocation
   and summary block — was not read.
4. **The tick rungs themselves** (the 383–384 real candles per symbol) were checked for spacing,
   uniformity, POC uniqueness and imbalance counts, but **not** rung-by-rung against source
   aggTrades. Their correctness rests on the code review in §4.
5. **The 20-window walk-forward was not re-run.** §9.1 figures are `[prior-session]`.
6. **No strategy was executed against the new 18-symbol dataset.** This is a data-pipeline audit.

**Two of my own tests produced unreliable output and are excluded from this document:**
a `np.mod(price_bin, step)` grid test (float `mod` on values stored as `round(k*step, 4)` is
meaningless) and a first attempt at tick/synthetic separation that mislabelled candles by using
`nunique(price_bin) > 1` as the tick criterion. Both were replaced by the robust versions
reported as Test 11 and Test 12b.

---

# APPENDIX A — REPRODUCTION COMMANDS

All paths assume the §0 extraction to `/tmp/r10`.

### A.1 The project's own verifier

```python
import importlib.util
spec = importlib.util.spec_from_file_location(
    'vpi', '/tmp/r10/Engine_2/verification/verify_parquet_integrity.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.verify_all_parquets(target_dir='/tmp/r10/Engine_2/binance_backtesting_data'))
```

### A.2 Table A/B/C — master + ladder sweep (is_synthetic, depth, integrity, uniformity)

```python
import pandas as pd, numpy as np, glob, os
D='/tmp/r10/Engine_2/binance_backtesting_data'
syms=sorted({os.path.basename(f).split('_15m_')[0] for f in glob.glob(D+'/*_master_*.parquet')})
for s in syms:
    m=pd.read_parquet(f'{D}/{s}_15m_master_2020_2026.parquet',
        columns=['open_time_ms','close','high','low','volume_base','trade_count','is_synthetic',
                 'ask_depth_usd','bid_depth_coin','ask_depth_coin','long_liq_usd','short_liq_usd',
                 'fp_delta','future_cvd_15m','poc_source'])
    L=pd.read_parquet(f'{D}/{s}_15m_footprint_ladder.parquet')
    deg=int(((m['high']==m['low']) & ((m['volume_base']==0.0)|(m['trade_count']==0))).sum())
    nu=L.groupby('open_time_ms')['bid_vol_coin'].nunique()
    print(s,
      'synth',int((m.is_synthetic==1).sum()),'deg',deg,'dtype',m.is_synthetic.dtype,
      'askmin',m.ask_depth_usd.min(),
      'bid==ask %',float((m.bid_depth_coin==m.ask_depth_coin).mean()*100),
      'orphan',len(set(L.open_time_ms.unique())-set(m.open_time_ms)),
      'poc_ok',int(L.is_poc.sum())==L.open_time_ms.nunique(),
      'uniform_candles',int((nu<=1).sum()),'of',L.open_time_ms.nunique(),
      'imb_flags',int(L.is_buy_imbalance.sum()+L.is_sell_imbalance.sum()),
      'fpdelta_eq',bool((m.fp_delta==m.future_cvd_15m).all()))
```

### A.3 Cross-table provenance contradiction (§5.3)

```python
for s in ['APTUSDT','XRPUSDT','BTCUSDT']:
    m=pd.read_parquet(f'{D}/{s}_15m_master_2020_2026.parquet',columns=['open_time_ms','poc_source'])
    L=pd.read_parquet(f'{D}/{s}_15m_footprint_ladder.parquet')
    tick=set(m.loc[m.poc_source=='TICK_EXACT','open_time_ms'])
    nu=L.groupby('open_time_ms')['bid_vol_coin'].nunique()
    print(s,'TICK_EXACT',len(tick),
          'uniform',sum(1 for t in tick if t in nu.index and nu[t]<=1))
```

### A.4 Cold-start lookahead (§3, D1-1)

```python
m=pd.read_parquet(f'{D}/APTUSDT_15m_master_2020_2026.parquet',
                  columns=['high','low','close','atr_14','atr_100','rsi_14','ema_800'])
pc=np.roll(m.close.values,1); pc[0]=m.close.values[0]
tr=np.maximum(m.high.values-m.low.values,
              np.maximum(abs(m.high.values-pc),abs(m.low.values-pc)))
print(m.atr_14.iloc[0],  round(tr[:14].mean(),2))    # 0.52 0.52
print(m.atr_100.iloc[0], round(tr[:100].mean(),2))   # 0.23 0.23
print(m.rsi_14.iloc[:14].unique(), m.rsi_14.iloc[14])
```

### A.5 `fp_poc` resolution (§3, D1-4)

```python
for s in syms:
    m=pd.read_parquet(f'{D}/{s}_15m_master_2020_2026.parquet',columns=['close','fp_poc'])
    print(s, m.close.median(), m.fp_poc.nunique(), m.close.nunique())
```

### A.6 Synthetic bin-step leak (§5, D3-1-F) and mixed grid (§4, D2-5)

```python
for s in ['BTCUSDT','ETHUSDT','DOGEUSDT']:
    m=pd.read_parquet(f'{D}/{s}_15m_master_2020_2026.parquet',columns=['close'])
    full=float(m.close.median()); raw=full*0.00035
    step=round(raw,1) if raw>=1.0 else (round(raw,2) if raw>=0.1 else
         (round(raw,3) if raw>=0.01 else (round(raw,4) if raw>=0.001 else round(raw,6))))
    early=float(m.close.iloc[:96*30].median())
    print(s, full, step, f"{step/early*10000:.2f} bps in 2020 vs 3.5 target")
```

### A.7 Verifier headline count (§6, D4-5)

```python
lr=mr=0
for f in glob.glob(D+'/*.parquet'):
    n=pd.read_parquet(f,columns=['open_time_ms']).shape[0]
    lr+=n if 'ladder' in f else 0
    mr+=0 if 'ladder' in f else n
print(lr, mr, lr/mr)     # 93,936,836  3,464,092  27.12
```

### A.8 `oi_change_pct` spikes (§3, D1-9)

```python
for s in syms:
    m=pd.read_parquet(f'{D}/{s}_15m_master_2020_2026.parquet',
                      columns=['oi_change_pct','metrics_available'])
    tr=(m.metrics_available.diff()==1)
    print(s, int((m.oi_change_pct.abs()>100).sum()),
          int((tr & (m.oi_change_pct.abs()>100)).sum()))
```

---

# APPENDIX B — SCHEMA REFERENCE

## B.1 Table 1 — master, 62 columns (`Engine_2/core/schema.py::CANONICAL_COLUMNS`)

| # | Column | Type | Notes |
|---|---|---|---|
| 1–4 | `open_time_ms`, `close_time_ms`, `datetime_utc`, `symbol` | int64/int64/str/str | `close_time_ms = open_time_ms + 899_999` |
| 5–10 | `open`, `high`, `low`, `close`, `volume_base`, `volume_quote` | float64 | |
| 11 | `volume_sma9` | float64 | expanding window for `i < 8` |
| 12 | `trade_count` | int64 | |
| 13–15 | `rsi_14`, `atr_14`, `atr_100` | float64 | **warmup backfilled — X-05** |
| 16–20 | `ema_8`, `ema_21`, `ema_50`, `ema_200`, `ema_800` | float64 | seeded `ema[0]=prices[0]` — X-13 |
| 21–23 | `future_cvd_15m`, `future_cvd_session`, `future_cvd_lifetime` | float64 | "future" = futures market |
| 24–26 | `spot_cvd_15m`, `spot_cvd_session`, `spot_cvd_lifetime` | float64 | 97.5–100% `SPOT_EXACT` |
| 27–28 | `funding_rate_pct`, `basis_usd` | float64 | |
| 29–31 | `open_interest_k`, `open_interest_usd`, `oi_change_pct` | float64 | **X-12 unclamped spikes** |
| 32–33 | `long_liq_usd`, `short_liq_usd` | float64 | **model output — X-08**; polarity verified ≤0 / ≥0 |
| 34–38 | `ls_ratio_global`, `ls_ratio_top`, `top_account_ratio`, `whale_index`, `taker_volume_ratio` | float64 | |
| 39 | `fp_delta` | float64 | **duplicate of `future_cvd_15m` — X-24** |
| 40 | `fp_poc` | float64 | **1-decimal rounding — X-07** |
| 41–43 | `fp_poc_vol_ratio`, `fp_stacked_buy_imb`, `fp_stacked_sell_imb` | float64 | 0.0 on 99.97% of bars |
| 44–47 | `session_vah`, `session_val`, `prev_day_vah`, `prev_day_val` | float64 | daily 00:00 UTC anchor, verified causal |
| 48–53 | `taker_buy_count`, `taker_sell_count`, `taker_buy_vol_btc`, `taker_sell_vol_btc`, `max_trade_vol_btc`, `avg_trade_size_usd` | int64/int64/float64×4 | **X-25** |
| 54–57 | `bid_depth_usd`, `ask_depth_usd`, `bid_depth_coin`, `ask_depth_coin` | float64 | **X-06 bit-identical; X-26 schema says "Negative"** |
| 58–60 | `future_flow_source`, `spot_flow_source`, `poc_source` | str | **X-04 / X-14** |
| 61 | `is_synthetic` | **int8** | **CLOSED — 161 = 161** |
| 62 | `metrics_available` | int8 | 79–100% depending on listing date |

## B.2 Table 2 — footprint ladder, 9 columns

| # | Column | Type | Notes |
|---|---|---|---|
| 1 | `open_time_ms` | int64 | 15m bucket start |
| 2 | `price_bin` | float64 | `bin_idx * daily_bin_step`; **mixed grid — X-16** |
| 3 | `bid_vol_coin` | float64 | taker **sell** volume (executed at the bid) |
| 4 | `ask_vol_coin` | float64 | taker **buy** volume (executed at the ask) |
| 5 | `net_delta_coin` | float64 | `ask − bid`; **constant within synthetic candles** |
| 6 | `is_buy_imbalance` | int8/int64 | diagonal, 3.0×, adjacency-enforced |
| 7 | `is_sell_imbalance` | int8/int64 | diagonal, 3.0×, adjacency-enforced |
| 8 | `is_poc` | int8/int64 | integer `bin_idx` equality; exactly one per candle |
| 9 | `trade_count` | int64 | **does not reconcile to master — X-10** |

**Missing and required:** `rung_source` (P0-1), `bin_step` / `fp_effective_bps` (P0-5).

## B.3 Files audited

| File | Role |
|---|---|
| `Engine_2/run_historical_pipeline.py` | Orchestrator; **contains the ladder synthesiser (§5.1)** |
| `Engine_2/core/canonical_indicators.py` | EMAs, Wilder RSI/ATR, CVD, session VA, depth estimate |
| `Engine_2/pipeline/historical_metrics_processor.py` | 62-column assembly; `is_synthetic`; `fp_poc` |
| `Engine_2/pipeline/tick_footprint_fetcher.py` | aggTrades → footprint summary + ladder |
| `Engine_2/pipeline/parquet_exporter.py` | Master parquet + manifest |
| `Engine_2/verification/verify_parquet_integrity.py` | Integrity suite; **dead `ref_valid` (§5.2)** |
| `Engine_2/core/schema.py` | `CANONICAL_COLUMNS`, `COLUMN_DTYPES` |
| `Engine_2/core/mathematical_liquidation_engine.py` | Liquidation ML + physics fallback |
| `Engine_2/binance_backtesting_data/*` | 54 committed artifacts, 999 MB |
| `Engine_2/core/trained_models/*.joblib` | ExtraTrees liquidation models |

---

---
---

# PART II — S1 STRATEGY ENGINE & WALK-FORWARD CAUSALITY AUDIT
### Zero-Lookahead Forensic Review · `s1_liquidation_cascade.py` · `verify_sequential_w1_w20.py`

| | |
|---|---|
| **Audited revision** | `origin/main` = **`8c0d74b`** |
| **Files** | `s1_liquidation_cascade.py` (931 L) · `verify_sequential_w1_w20.py` (700 L) · `adversarial_council_stress_test.py` (402 L) |
| **Temporal verdict — `s1_liquidation_cascade.py`** | **`[CLEAN — ZERO LOOKAHEAD VERIFIED]`** |
| **Temporal verdict — `verify_sequential_w1_w20.py`** | **`[LEAKAGE DETECTED]`** |
| **Allocation verdict** | **`[REJECT]`** |

## II.0 EVIDENCE BASE — WHAT WAS ACTUALLY EXECUTED

This is not a read-only review. The production engine was **run end to end** against the
committed 18-symbol dataset.

| Step | Command | Result |
|---|---|---|
| Fetch | `git fetch origin main` | `origin/main` = `8c0d74b` |
| Extract | `git archive origin/main Engine_2 \| tar -x -C /tmp/r11` | 15 `.py` files + 999 MB data |
| Deps | `pip install lightgbm optuna numba python-dateutil scikit-learn pandas pyarrow` | lightgbm 4.7.0 / optuna 4.9.0 / numba 0.67.0 / sklearn 1.9.0 |
| **Run the engine** | `python3 -u s1_liquidation_cascade.py` (4-symbol subset: BTC, ETH, SOL, XRP — 3 GB RAM ceiling) | **841,172 rows loaded, 20/20 windows evaluated, `0/20 Windows Passed`** |
| Trade-stream extraction | `extract_archetype_dataset(...)` on all 4 reachable archetypes | A1 4,436 · A4 9,859 · V1 9,981 · V2 4,929 trades |
| Label/fee boundary | recomputed `r_multiple` vs fee-in-R on the 9,859-trade A4 stream | see §II.3.2 |
| Static sweeps | `grep` for `shift(-`, `center=True`, `bfill`, optuna, lookup tables, `== 20` | see below |

**Subset caveat, stated plainly:** the machine has 3 GB RAM and 2 cores, so the engine was run on
4 of 18 symbols. Every *code-level* finding is symbol-independent. The *performance* figures
(0/20, 83 trades, 22.9% win rate) are from the 4-symbol subset and would change in magnitude —
not in sign — on the full 18.

---

## II.1 DOMAIN 1 — INFORMATION LEAKAGE & TEMPORAL SNOOPING

### II.1.1 Feature causality — **CLEAN**

Exhaustive static sweep of all three files:

```
grep -n 'shift(-'        → 1 hit total:  s1_liquidation_cascade.py:240
grep -n 'center=True'    → 0 hits
grep -n 'bfill'          → 0 hits
```

**The single negative shift in the entire codebase is the execution price, not a feature:**

```python
240|     df['next_open'] = df['open'].shift(-1)
241|     df.dropna(subset=['next_open', 'atr'], inplace=True)
```

And `next_open` is **provably absent from the feature matrix** — `feature_cols` (L723–730)
enumerates 38 columns and `next_open` is not among them. It is consumed only at
`gen_symbol_trades` L411 (`raw_entry = next_opens[i]`) and in the trade record at L700.

Every named feature in the brief is backward-looking. Verified line by line:

| Feature | Line | Construct | Causal? |
|---|---|---|---|
| `spot_cvd_delta` | 144 | `spot_cvd.diff()` | ✅ |
| `future_cvd_delta` | 145 | `fut_cvd.diff()` | ✅ |
| `spot_cvd_accel` | 146 | `.diff()` of a `.diff()` | ✅ |
| `zc4` / `zc10` / `zc20` | 148–150 | `zs()` = `rolling(w, min_periods=1)` mean/std (L69–70) | ✅ |
| `liql`/`liqs`/`liqlm`/`liqsm` | 162–165 | `rolling(5)` / `rolling(96)` sum/mean | ✅ |
| `long_liq_zscore`, `short_liq_zscore` | 170–173 | `rolling(96, min_periods=12)` mean/std | ✅ |
| `oi_flush` | 176 | `oi_change_pct.clip(upper=0)` — pointwise | ✅ |
| `zoi` | 181 | `zs(oi, 96)` on `.ffill()`ed OI | ✅ |
| `oid` | 182 | `oi.diff(5) / (oi.shift(5) + 1e-8)` | ✅ |
| `oicc` | 183 | `sign(oid) * sign(spot_cvd_delta)` — pointwise | ✅ |
| `zfr`, `zls` | 187–188 | `zs(..., 20)` / `zs(..., 96)` | ✅ |
| `atr` | 191–195 | true range from `close.shift(1)`, `rolling(14).mean()` | ✅ |
| `rsi` | 196 | taken from master `rsi_14` | ✅ see note |
| `vwap`, `vwap_zscore`, `vwap_dev_pct` | 199–211 | `groupby(day_anchor).cumsum()` — intraday cumulative | ✅ |
| `macro_spread`, `mc` | 213–216 | `ewm(span=200/800)` | ✅ |
| `p8`, `p21`, `p50`, `p200` | 218–224 | `ewm(span=8/21/50/200)` | ✅ |
| `vol_ratio` | 226–229 | `rolling(96).std() / rolling(672).std()` | ✅ |
| `trend_strength` | 230 | `(ef − es).abs() / atr` | ✅ |
| `regime` | 232–237 | pointwise on the above | ✅ |

**No centred window, no backward fill, no future-referencing statistic anywhere.**

**Two things this file does better than the pipeline it consumes (Part I):**

1. **It recomputes ATR locally** (L191–195) from true range with `close.shift(1)`, rather than
   using the master parquet's `atr_14`. That insulates S1 from the warmup-backfill lookahead
   documented in Part I §D1-1.
2. **`gen_symbol_trades` starts at `i = 100` and stops at `n − 100`** (L405, L407), so the
   parquet's contaminated `rsi_14` bars 0–13 are never traded.

### II.1.2 Purge gap — **ADEQUATE, and over-satisfied by a stronger constraint**

```python
758|     train_end_purged = w['train_end'] - pd.Timedelta(hours=3)   # Strict 3h purge gap
768|     df_is  = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end_purged)].copy()
769|     df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
```

**The 3-hour purge is not the operative control — L768 is.** The IS partition requires
`exit_time < train_end_purged`, i.e. a trade enters IS **only if its entire resolution completes
before the purge boundary.** Since `max_bars = 288` at 15 m = **72 hours**, the label horizon is
three days, and filtering on `exit_time` — not merely `entry_time` — is exactly the right
treatment. Most implementations purge on entry only and leak the label tail; this one does not.

Consequences:
- **No IS trade's outcome extends into the OOS window.** No label overlap.
- The 3-hour gap is *redundant* given the `exit_time` filter — harmless, and defensible as
  belt-and-braces against feature staleness at the boundary.
- **Verdict: PASS.**

### II.1.3 Point-in-time merging — **CLEAN in both files**

`s1_liquidation_cascade.py:133`:
```python
129|     df = df.sort_values('datetime_utc').reset_index(drop=True)     # left frame sorted ✅
133|     df = pd.merge_asof(df, btc_ref, on='datetime_utc', direction='backward')
```

`verify_sequential_w1_w20.py:60–71`:
```python
66|     df = df_signals.sort_values('entry_time').reset_index(drop=True)          # ✅
67|     bm = btc_macro_[['datetime_utc'] + REG_FEATS].sort_values('datetime_utc')  # ✅
68|     df = pd.merge_asof(df, bm, left_on='entry_time', right_on='datetime_utc', direction='backward')
```

Both frames are sorted on the join key (pandas raises otherwise, so this is enforced at runtime),
and `direction='backward'` binds each altcoin signal to the most recent BTC row **at or before**
its own timestamp. **Zero lookahead**, conditional on the BTC columns being causal at their own
timestamp — verified: `btc_r_24h = close.pct_change(96)` (L146), `btc_vol_delta_12 =
vol_ratio.diff(12)` (L147), `btc_rsi_z` and `btc_trend_strength` pointwise (L148–150). All
backward. **Verdict: PASS.**

### II.1.4 The one real causality defect in `s1_liquidation_cascade.py`

**V-01 · MEDIUM · Full-horizon MAE is injected into the risk-state machine at entry.**

```python
526|     mae_dollar = units * maes[i]        # maes[i] is the trade's EVENTUAL max adverse excursion
532|     open_mae_dollars[p] = mae_dollar     # booked at ENTRY
...
480|     open_mae += open_mae_dollars[p]
484|     cur_mtm_equity = capital - open_mae
507|     drawdown_budget = max(0.0, peak_capital * dd_limit - closed_drawdown - open_mae)
508|     cur_risk = min(target_risk, drawdown_budget / 1.2)
```

`maes[i]` is a function of trade *i*'s entire future path. Booking it at entry means the sizing
and gating of **subsequent** trades (L507–508) depend on the realised future MAE of an open
position. That is temporal leakage in the risk channel.

**Direction is strictly conservative, and I verified why.** At any instant during a trade,
unrealised PnL ≥ −(full-horizon MAE) by definition of MAE. Therefore
`capital − open_mae ≤ true MTM equity`, so `dd` is **over**stated, `max_dd` is **over**stated,
`drawdown_budget` is **under**stated, `cur_risk` is smaller, and positions are smaller. **It
cannot inflate ROI.** But it does mean the reported max-DD, trade count and equity path are not
reproducible live.

**Fix:** carry a bar-by-bar unrealised-PnL series per open position and mark to that.

---

## II.2 DOMAIN 2 — THRESHOLD CALIBRATION & PARAMETER SNOOPING

### II.2.1 Frozen decision boundary p\* — **CLEAN, zero OOS contact**

```python
818|     model.fit(X_train, y_train)
820|     # F3 Fix: Derive frozen decision threshold strictly In-Sample (Top 20% IS threshold)
821|     is_probs = model.predict_proba(X_train)[:, 1]
822|     frozen_prob_threshold = float(np.percentile(is_probs, 75)) if len(is_probs) > 0 else 0.50
823|     frozen_prob_threshold = max(0.50, min(0.65, frozen_prob_threshold))
...
826|     X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
830|     mask_oos = (probs_oos >= frozen_prob_threshold)
```

`is_probs` is computed on `X_train` only. The clamp at L823 uses two literals. `df_oos` is
**never referenced** at L821–823. **The threshold does not touch out-of-sample data.** Verdict:
**PASS.**

**Two notes, neither a leakage violation:**
- **Doc/code mismatch:** the comment says "Top 20% IS threshold"; `percentile(..., 75)` is the
  top **25%**.
- **V-02 · MEDIUM · the quantile is taken on *fitted* in-sample probabilities.** A fitted
  LightGBM's in-sample probabilities are over-confident, so their 75th percentile sits lower than
  the 75th percentile of genuine out-of-sample probabilities. The clamp to `[0.50, 0.65]`
  mitigates this substantially. **Effect: the gate admits more OOS trades than "top 25%" implies
  — permissive, not leaky.** Same pattern in `verify_sequential_w1_w20.py:90` (`p_perc=70/72`)
  and `:666`/`:675` (`percentile(gbm.predict(n4_is[...]), 75)`).

### II.2.2 Runtime search — **CLEAN in `s1`; ABSENT in the verifier**

Optuna **is** live in `s1_liquidation_cascade.py`:

```python
782|     def _optuna_objective(trial):
783|         md = trial.suggest_int("max_depth", 3, 6)
...
789|         n_split = int(len(X_train) * 0.8)
790|         X_tr, X_val = X_train[:n_split], X_train[n_split:]
791|         y_tr, y_val = y_train[:n_split], y_train[n_split:]
...
803|         val_wr = (y_val[pred == 1]).mean() if (pred == 1).sum() > 0 else 0.0
804|         return val_wr
806|     study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
807|     study.optimize(_optuna_objective, n_trials=15, timeout=10)
```

Every input is `X_train` / `y_train`, i.e. `df_is`. **`df_oos` is not in scope of the objective.**
The internal 80/20 split is **positional on a frame sorted by `entry_time`** (L715), so the
validation fold is the *later* 20% of IS — a proper temporal holdout, not a shuffle. Seeded
(`seed=42`), bounded (15 trials, 10 s). This is textbook walk-forward hyperparameter selection on
training data. **Verdict: PASS — no OOS search.**

`verify_sequential_w1_w20.py` contains **no** optuna, grid, or threshold sweep. It needs none —
see §II.2.4.

### II.2.3 Lookup tables — **PURGED** ✅

```
find /tmp/r11 -iname '*winning*' -o -iname '*s1_status*' -o -iname '*s2_status*' \
             -o -iname '*lookup*' -o -iname '*configuration*.json'
→ (no results)
```

The only `.json` files anywhere under `Engine_2/` are the 18 `*_dataset_manifest.json` data
manifests. `winning_configuration.json`, `s1_status.json` and `s2_status.json` are **absent from
the repository.** **Verdict: PASS.**

**One residual state artifact (V-03 · LOW):** `verify_sequential_w1_w20.py:114–121` loads
`data_cache/master_archetypes.pkl` when present, bypassing recomputation. Not a parameter table,
but an unpickled cache with no version stamp and no source hash — a reproducibility and
provenance hazard (and `pickle.load` is arbitrary code execution).

### II.2.4 **V-04 · CRITICAL · `verify_sequential_w1_w20.py` hand-assigns a different strategy to every window**

This is the most serious finding in Part II.

```
grep -n 'classify_macro_regime_causal\|REGIME_ARCHETYPE_MAP' verify_sequential_w1_w20.py
→ (no results)
```

**Neither the causal regime classifier nor the regime→archetype map is used.** Instead the file
is 20 sequential hand-written blocks (`w1 = windows[0]`, `w2 = windows[1]`, … `w20`), each with a
hardcoded strategy bundle:

| Window | Hardcoded bundle (from the source) |
|---|---|
| W01 | `Multi-Strategy Synergy` — S4_CVDDivergence + S1_VolBreakout + S3_TrendFollow |
| W02 | `S1_VolBreakout` |
| W03 | `A2_DeepSqueeze` |
| W04 | `Multi-Engine Bear Shorts` |
| W06 | top-5 by OOS probability |
| W08 | multi-engine pool |
| W20 | `SYN_N4_A4 Bi-Directional` — bespoke N4 longs + A4 shorts built for that window |

**There is no mechanism in the code that could have produced these assignments causally.** By
contrast `s1_liquidation_cascade.py:761–763` derives its archetype from IS data only:

```python
761|     regime = classify_macro_regime_causal(btc_df, train_end_purged)   # IS window only
762|     arch_name = REGIME_ARCHETYPE_MAP.get(regime, 'A5_PureRelativeCVD')
```

`classify_macro_regime_causal` (L653–672) reads BTC rows strictly in
`[train_end_purged − 30d, train_end_purged)` — **entirely before `test_start`.** That is a
genuinely clean causal regime selector, and the verifier simply does not use it.

**Conclusion: the per-window model class in `verify_sequential_w1_w20.py` was selected by
inspecting the data, and the only data that distinguishes one archetype's performance in a given
month is that month's own out-of-sample data.** Any `N/20 PASS` produced by this file is a
selection result, not an out-of-sample result.

### II.2.5 **V-05 · CRITICAL · per-window bespoke risk parameters and gates**

Every window passes its own risk configuration to the backtester:

| Window | `base_risk` | `house_risk` | `house_trigger` | `house_shield` | `defense` | `max_concurrent` | `dd_limit` |
|---|---|---|---|---|---|---|---|
| W01 | 75.0 | 180.0 | 30.0 | — | — | (2) | 0.045 (+`max_notional=15000`) |
| W06 | 95.0 | 220.0 | 30.0 | 85.0 | 30.0 | (2) | 0.050 |
| W07 | 80.0 | 220.0 | 30.0 | 85.0 | 30.0 | (2) | 0.048 |
| W09 | 25.0 | 120.0 | 25.0 | 25.0 | 12.5 | **6** | 0.048 |
| W10 | 35.0 | 160.0 | 25.0 | 35.0 | 17.5 | **4** | 0.048 |
| W11 | 35.0 | 140.0 | 25.0 | 35.0 | 17.5 | **1** | 0.048 |
| W12 | 30.0 | 120.0 | 25.0 | 30.0 | 15.0 | 2 | 0.045 |
| W20 | 50.0 | 175.0 | 15.0 | 50.0 | 25.0 | 2 | 0.048 |

versus the `s1_liquidation_cascade.py` constants: `BASE_RISK=75`, `HOUSE_MONEY_RISK=180`,
`HOUSE_PROFIT_TRIGGER=50`, `HOUSE_SHIELD_RISK=65`, `DRAWDOWN_DEFENSE_RISK=20`,
`DRAWDOWN_RISK_LIMIT=0.045`, `MAX_CONCURRENT=2`, `MAX_NOTIONAL=50000`.

`base_risk` varies **3.8×** across windows; `max_concurrent` takes the values **1, 2, 4 and 6** —
directly contradicting the stated `max_concurrent=2` mandate. Per-window label definitions vary
too (`r_multiple > 1.0` at L664/L673 versus `r_multiple > 0` in s1).

**This is per-window parameter fitting.** Whatever those windows returned, the parameters were
chosen with knowledge of them.

### II.2.6 **V-06 · HIGH · the frozen threshold is overridden using OOS probabilities**

```python
176|     if len(qual) == 0: qual = df_oos.nlargest(3, 'prob')
301|     top_w6 = df_oos.nlargest(5, 'prob').sort_values('entry_time')...   # W06 ignores p* entirely
329|     if len(qual) < 3: qual = df_oos.nlargest(3, 'prob')
368|     fb = df_oos.nlargest(min(8, len(df_oos)), 'prob')
178|     df_w1 = pd.concat(w1_cand, ...).nlargest(20, 'conviction')...      # conviction = p_oos − p_star
```

When too few OOS candidates clear `p_star`, the code selects the top-*k* **by OOS probability**
instead. The threshold is therefore not binding, and the number of trades taken is a function of
the OOS probability distribution. W06 discards `p_star` altogether.

**`s1_liquidation_cascade.py` has no such fallback** — when nothing clears the threshold it takes
zero trades. Confirmed empirically: **windows 08 and 17 returned 0 trades** rather than relaxing
the gate. That is the correct behaviour.

---

## II.3 DOMAIN 3 — MICROSTRUCTURE & INTRA-BAR EXECUTION REALISM

### II.3.1 Adverse-first execution — **CORRECT, and structurally immune to same-bar double wins**

```python
344|     for j in range(entry_idx + 1, max_idx):
345|         if direction == 1:
346|             adverse = max(0.0, entry_price - lows[j])
347|             if adverse > mae: mae = adverse
350|             # 1. EVALUATE STOP EXIT FIRST against active stop (avoids favorable intra-bar bias)
351|             if lows[j] <= cur_stop:
353|                 raw_fill = min(cur_stop, lows[j])          # gap-aware: fills at the LOW if gapped through
354|                 exit_price = raw_fill * (1.0 - exit_slippage)
356|                 break
358|             # 2. RATCHET STOP FOR SUBSEQUENT BARS ONLY
359|             if highs[j] > best_price: best_price = highs[j]
```

Three separate protections, all present:

1. **Stop is evaluated before the ratchet** (L350 before L358), with `break`.
2. **The ratchet at bar *j* only affects bars *j+1* onward** — `cur_stop` used at L351 is the
   value carried in from bar *j−1*. A bar cannot raise its own stop and then be stopped out at
   the raised level.
3. **There is no profit-target branch at all.** The only exits are the trailing stop and time
   expiry. With no MFE exit, **"same-bar double wins" are structurally impossible** — there is no
   second outcome to conflict with.

Gap handling is realistic and conservative: `raw_fill = min(cur_stop, lows[j])` fills at the bar's
low when price gaps through the stop, not at the theoretical stop level. Mirror logic for shorts
at L371–396 (`max(cur_stop, highs[j])`).

Entry is next-bar-open, not signal-bar: `raw_entry = next_opens[i]` (L411), and the simulation
loop starts at `j = entry_idx + 1` — the entry bar itself is the first bar at risk. Correct.

**V-07 · LOW · `min_ret_pct` is a dead parameter.** It is passed as `0.015` (L416) and never
referenced in the body. The docstring at L332 promises *"Phase 3 (+5.0R gain): 5R Target Reached
→ Activate 0.8R trailing runner"* — there is no target exit; +5.0R only tightens the trail
(L362–364). Remove the parameter or implement the phase.

**V-08 · LOW · `exit_offset` overstates holding period at the data edge.** L339–340 default
`exit_offset = max_bars` even when `min(entry_idx + max_bars, len(closes) − 1)` truncated the
path. That feeds `cd = i + max(offset, 1) + 2` (L422), over-suppressing subsequent signals near
the end of each symbol's history.

### II.3.2 Execution frictions — **adequately modelled, with one label defect**

| Mandate | Implementation | Verified |
|---|---|---|
| 10 bps taker entry slippage | `ENTRY_SLIPPAGE = 0.0010`; `entry = raw_entry * (1 ± 0.0010)` (L412) | ✅ |
| 15 bps stop-loss slippage | `EXIT_SLIPPAGE = 0.0015`; applied on stop fill (L354, L380) **and** time expiry (L339) | ✅ |
| 8 bps taker roundtrip fees | `FEE_RATE = 0.0008`; `fee = (entry_val + exit_val) * (fee_rate / 2.0)` (L524) → 4 bps per leg | ✅ |

Fees are charged on **notional at both legs**, deducted before `net_pnl` (L525), and the win flag
uses net P&L (L539: `if net_pnl > 0`). Correct.

**V-09 · MEDIUM · the training label is gross of fees.**

```python
419|     r_mult = (ep - entry) / stop_dist if dr == 1 else (entry - ep) / stop_dist
420|     lb = 1.0 if r_mult > 0.0 else 0.0
705|     'label': int(lb)
```

`r_multiple` includes both slippages but **not** the 8 bps fee, which is applied only in the
portfolio layer. The classifier is therefore trained to predict *gross*-positive trades while the
gate measures *net* winners.

**Measured on the 9,859-trade `A4_UltraDeepValue` stream:**

```
fee expressed in R units:  median 0.0712R   mean 0.0745R   p95 0.1231R
label == 1  (gross r > 0)      : 2,279  (23.12%)
net winners (r − fee > 0)      : 2,195  (22.26%)
MISLABELLED wins, r ∈ (0, fee_R]:    84  (3.69% of all positive labels)
gross win rate 23.12%  vs  net 22.26%   →  gap 0.85 percentage points
```

**The defect is real but small — 0.85 pp.** It should still be fixed (label on
`r_multiple − fee_R`), but it is **not** what is causing the strategy to fail.

**The number that matters is the level, not the gap: the raw archetype wins 23.12% of the time
against a `MIN_WIN_RATE` gate of 40%.** No threshold calibration closes a 17-point gap.

### II.3.3 Portfolio concurrency — **enforced, no queue lookahead**

```python
460|     for p in range(max_concurrent):
461|         if open_active[p] and open_exit_times[p] <= entry_t:      # release only when exit time has passed
472|             open_active[p] = False
...
489|     if active_count >= max_concurrent:
490|         continue                                                   # hard cap, candidate simply skipped
```

Slots are released only when `open_exit_times[p] <= entry_t` — strictly causal. The cap is a hard
`continue`, so an over-capacity candidate is dropped rather than queued (no queue, therefore no
queue lookahead). Margin is checked before entry (L517–519). `max_concurrent = 2` in
`s1_liquidation_cascade.py`.

**Verdict: PASS for `s1`.** For `verify_sequential_w1_w20.py` the mandate is **violated** — see
V-05, where `max_concurrent` is 1, 2, 4 and 6 depending on the window.

---

## II.4 DOMAIN 4 — SINGLE STRATEGY vs MULTI-SLEEVE FEASIBILITY

### II.4.1 The 20/20 conjunctive gate is the binding constraint, not the sleeve count

The premise `P(20/20) = q^20` is correct. Computed:

| per-window pass probability *q* | `P(20/20) = q^20` |
|---|---|
| 0.05 | 9.54e−27 |
| 0.10 | 1.00e−20 |
| 0.20 | 1.05e−14 |
| 0.50 | 9.54e−07 |
| 0.70 | 7.98e−04 |
| 0.90 | 1.22e−01 |
| **0.9659** | **0.50** |

**To have even a 50% chance of passing 20/20, each window must pass 96.59% of the time.**
For a 5% chance, 86.09%. Multi-sleeve diversification raises *q* by reducing return variance, but
it does not change the exponent. At *q* = 0.90 — an extraordinary per-window hit rate — the
probability of 20/20 is still 0.12.

**So: multi-sleeve regime diversification is desirable for variance reduction, but it is neither
sufficient nor "mathematically mandatory." The conjunctive 20/20 gate is unsatisfiable by
construction for any strategy with a per-window pass rate below ~86%.** It should be replaced with
a distributional criterion (aggregate OOS Sharpe/Calmar with a bootstrap confidence interval, or
≥16/20 with the failures characterised).

### II.4.2 The measured blocker is trade count, not direction

From the executed run (20/20 windows evaluated):

```
mean ROI/window       = −2.55%      sd = 4.17%
total OOS trades      = 83          mean 4.2/window
windows with 0 trades = 2   (W08, W17 — the frozen threshold admitted nothing)
windows with ROI > 0  = 2   (W07 +5.52%, W10 +11.28%)
trade-weighted win rate = 22.9%

windows meeting ROI   >= 10%  :  1/20
windows meeting trades >= 5   :  8/20     ← HARD STRUCTURAL BLOCKER
windows meeting BOTH          :  1/20
```

`MIN_TRADES = 5` fails in **12 of 20 windows** before ROI is even considered. At 4.2 trades per
month the sample is also far too thin for the 40% win-rate gate to mean anything: at *n* = 4 the
standard error on a win rate is ~25 points.

### II.4.3 The gate itself is not an institutional mandate

`MIN_RETURN = 0.10` compounded monthly is **214% annualised**; `verify_sequential_w1_w20.py` uses
`roi >= 0.20` — **792% annualised** — with a ≤5% drawdown cap. Requiring 792%/yr at ≤5% DD is not
a fund mandate, it is a lottery ticket, and it guarantees that the only way to satisfy it is to
fit the windows.

---

## II.5 LINE-BY-LINE VULNERABILITY LOG

### `s1_liquidation_cascade.py`

| ID | Line(s) | Severity | Finding | Leakage? |
|---|---|---|---|---|
| — | 240 | — | `df['open'].shift(-1)` — **the only negative shift in the codebase**; execution price only, absent from `feature_cols` (L723–730) | **No** |
| — | 133 | — | `merge_asof(direction='backward')`, both frames sorted (L129) | **No** |
| — | 656 | — | `classify_macro_regime_causal` reads only `[train_end_purged−30d, train_end_purged)` | **No** |
| — | 768 | — | IS partition requires `exit_time < train_end_purged` — purges the 72 h label horizon, not just entry | **No** |
| — | 782–808 | — | Optuna objective touches `X_train`/`y_train` only; 80/20 split is temporal (L715 sort) | **No** |
| — | 821–823 | — | `frozen_prob_threshold` from `X_train` only, clamped to literals | **No** |
| — | 350–356, 376–382 | — | Stop evaluated before ratchet, `break`; ratchet affects subsequent bars only | **No** |
| — | 461, 489 | — | Concurrency release on `exit_time <= entry_t`; hard cap via `continue` | **No** |
| **V-01** | **526, 532, 484, 507–508** | **MEDIUM** | Full-horizon MAE booked at entry and used to gate/size later trades. **Conservative** (overstates DD, shrinks size) but non-causal and not live-reproducible | **Yes — conservative** |
| **V-02** | 821–822 | MEDIUM | Threshold quantile taken on *fitted* IS probabilities → permissive, not leaky. Mitigated by the [0.50, 0.65] clamp | No |
| **V-09** | 419–420, 705 | MEDIUM | Label `r_multiple > 0` is gross of the 8 bps fee. Measured: 84 of 2,279 positives (3.69%) mislabelled; 0.85 pp win-rate gap | No |
| **V-10** | **908–910** | **HIGH** | **Denominator defect.** `return pass_total == len(all_window_results)` where skipped windows (L771–773 `continue`) never append a record. A run that evaluates 3 windows and passes 3 prints "ALL 20 WINDOWS PASSED" (L927). `grep` for `== 20`, `len(OOS_MONTHS)`, `len(windows)`, `>= 20` returns **nothing**. **Did not fire on this run** — all 20 windows were evaluated on both the 4-symbol and 2-symbol subsets — but it is latent and structural | No |
| V-07 | 324, 416 | LOW | `min_ret_pct` dead parameter; docstring promises a 5R target phase that does not exist | No |
| V-08 | 339–340, 422 | LOW | `exit_offset` defaults to `max_bars` on truncated paths → over-suppresses the cooldown near data end | No |
| V-11 | 876–877 | LOW | `ann_roi = (1+roi)**12.167 − 1` annualises one month by compounding; Calmar is meaningless. Not in the pass gate, despite the "Calmar-Aware" header at L43 | No |
| V-12 | 847–872 | LOW | Monte Carlo is labelled "Permutation" but bootstraps with replacement (L857); ignores `max_concurrent` and fees; `mc_worst_dd` / `mc_prob_profit` are recorded but **never used in the gate** (L879) | No |
| V-13 | 323, 400, 429 | LOW | `@njit(fastmath=True)` sets LLVM `nnan`, so the `np.isnan(av)` guard at L414 is not guaranteed to behave | No |

### `verify_sequential_w1_w20.py`

| ID | Line(s) | Severity | Finding | Leakage? |
|---|---|---|---|---|
| **V-04** | 162–692 | **CRITICAL** | 20 hand-written blocks with **hardcoded per-window strategy bundles**. Neither `classify_macro_regime_causal` nor `REGIME_ARCHETYPE_MAP` is imported or used. No causal mechanism exists to produce the assignments | **Yes — model selection on OOS** |
| **V-05** | 184–688 | **CRITICAL** | **Per-window bespoke risk parameters**: `base_risk` 25→95 (3.8×), `house_risk` 105→220, `house_trigger` 15→30, `max_concurrent` **1/2/4/6**, `dd_limit` 0.045→0.050, `max_notional` 15000 in W01. Per-window labels too (`r_multiple > 1.0` at L664/L673 vs `> 0` in s1) | **Yes — parameter fitting on OOS** |
| **V-06** | 176, 301, 329, 368 | **HIGH** | Frozen `p_star` overridden by `df_oos.nlargest(k, 'prob')` when too few qualify. W06 (L301) ignores `p_star` entirely | **Yes — OOS-conditional rule** |
| V-02b | 90, 666, 675 | MEDIUM | `p_star`/`q_star` from in-sample *fitted* probabilities | No |
| V-03 | 114–121 | LOW | Unpickled `master_archetypes.pkl` cache, no version stamp, bypasses recomputation | No |
| V-14 | 60–68 | — | `merge_btc_macro` — both frames sorted, `direction='backward'`, REG_FEATS all backward-looking | **No** |
| V-15 | 696 | LOW | Prints `"ALL 20 WINDOWS (100% COMPLETE)"` at L154 **before** any window executes | No |
| — | 187–689 | — | Gate is uniform across windows (`roi >= 0.20, dd <= 0.05, wr >= 0.40, tr >= 5`) and the denominator **is** hardcoded to 20 — so this file does **not** have V-10 | — |

---

## II.6 VERDICTS

### Temporal verdict

> ### `s1_liquidation_cascade.py` — **`[CLEAN — ZERO LOOKAHEAD VERIFIED]`**
>
> One negative shift in the entire codebase, and it is the execution price. No centred windows,
> no backward fills. Every feature backward-looking. The regime classifier reads only IS data.
> The Optuna search and the frozen p\* touch only `X_train`. The IS partition purges on
> `exit_time`, correctly handling the 72-hour label horizon. Stops are evaluated before the
> ratchet with gap-aware fills, and there is no profit-target branch, so same-bar double wins are
> structurally impossible. Concurrency releases causally.
>
> **One conservative causality exception (V-01):** full-horizon MAE is booked at entry and used to
> size later trades. It overstates drawdown and shrinks positions — it cannot inflate ROI, but it
> is not live-reproducible.
>
> ### `verify_sequential_w1_w20.py` — **`[LEAKAGE DETECTED]`**
>
> Per-window strategy selection is hardcoded with no causal derivation (V-04); per-window risk
> parameters, concurrency caps and label definitions are bespoke (V-05); and the frozen threshold
> is overridden using OOS probabilities (V-06). **Any `N/20 PASS` from this file is a selection
> result, not an out-of-sample result. It must not be cited as evidence of edge.**

### Allocation verdict

> # **`[REJECT]`**

Reasons, in order of weight:

1. **The honest engine does not work.** Executed on committed data: **0/20 windows passed**, mean
   ROI −2.55%/window, trade-weighted win rate **22.9%** against a 40% gate, **83 OOS trades
   across 20 months**, two windows with zero trades. `MIN_TRADES = 5` fails in 12 of 20 windows
   before ROI is considered.
2. **The engine that could be made to pass is the one with the leakage.** `s1_liquidation_cascade.py`
   is causally clean and scores 0/20. `verify_sequential_w1_w20.py` selects models and parameters
   per window and is the only path to a passing scorecard.
3. **The raw signal is ~17 points short of its own gate** — 23.12% gross win rate vs `MIN_WIN_RATE
   = 0.40`. That is not a calibration gap; it is the absence of edge at this horizon.
4. **The gate is unsatisfiable.** `P(20/20) = q^20` requires *q* = 96.6% for even a coin-flip
   chance of success. No sleeve count fixes this.
5. **V-10 is a governance failure waiting to fire.** A run that evaluates three windows and passes
   three prints "ALL 20 WINDOWS PASSED".

### Required before resubmission

| # | Action | File |
|---|---|---|
| R-1 | **Delete or quarantine `verify_sequential_w1_w20.py`.** If multi-sleeve blending is wanted, rebuild it to select the sleeve via `classify_macro_regime_causal` on IS data only, with **one** fixed risk configuration and **one** fixed gate | `verify_sequential_w1_w20.py` |
| R-2 | **Fix the denominator**: `return pass_total == len(OOS_MONTHS)`, and record skipped windows as explicit FAILs with a reason | `s1_liquidation_cascade.py:908-910` |
| R-3 | **Label on net-of-fee R**: `lb = 1.0 if (r_mult − fee_R) > 0` | `s1_liquidation_cascade.py:419-420` |
| R-4 | **Replace full-horizon MAE with bar-by-bar unrealised PnL** for MTM marking | `s1_liquidation_cascade.py:484, 526` |
| R-5 | **Replace the 20/20 conjunctive gate** with aggregate OOS Sharpe/Calmar plus a bootstrap CI, or ≥16/20 with failures characterised | both files |
| R-6 | **Reset the mandate to something falsifiable.** 10%/month at ≤5% DD is 214%/yr; 20%/month is 792%/yr. Neither is an institutional target | `s1:44-47` |
| R-7 | Remove `min_ret_pct` or implement the 5R target phase; delete or use the Monte Carlo in the gate; drop `fastmath=True` or remove the `isnan` guard | `s1:324, 416, 847-872, 879` |
| R-8 | Version-stamp or remove the pickle cache | `verify_sequential_w1_w20.py:114-121` |

**Bottom line.** The causality engineering in `s1_liquidation_cascade.py` is genuinely good —
better than most production backtesters I review, and materially better than the data pipeline it
consumes (Part I). It is also, on the evidence of an actual run, **worthless as a strategy**:
23% win rate, 4 trades a month, 0 of 20 windows. The correct conclusion is not that the harness is
broken. It is that the harness is telling the truth, and the answer is no.

---

**END OF DOCUMENT** · `ENGINE2_AUDIT_MASTER.md`
Part I audited at `701aac2` · Part II audited at `8c0d74b` · 2026-09-04
